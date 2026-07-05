from datetime import datetime, timedelta
import hmac
from io import BytesIO
import os
import re
import sqlite3
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from openpyxl import Workbook
import qrcode


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE = os.path.join(DATA_DIR, "database.db")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "123456")
SEED_DEMO = os.environ.get("SEED_DEMO", "1") == "1"
PUBLIC_SUBMIT_URL = os.environ.get("PUBLIC_SUBMIT_URL", "")
AMAP_KEY = os.environ.get("AMAP_KEY", "")

SERVICE_TYPES = [
    "开荒保洁",
    "日常保洁",
    "深度保洁",
    "玻璃清洗",
    "地毯清洗",
    "石材结晶",
    "木地板养护",
    "办公室保洁",
    "工程保洁",
    "其他",
]

SOURCES = [
    "微信",
    "朋友圈",
    "小红书",
    "抖音",
    "美团",
    "熟人介绍",
    "电话咨询",
    "其他",
]

ORDER_STATUSES = ["待联系", "已联系", "已成交", "已取消"]
LEGACY_STATUS_MAP = {"已报价": "已联系", "已完成": "已成交"}
STATUS_ORDER_SQL = """
    CASE status
        WHEN '待联系' THEN 1
        WHEN '已联系' THEN 2
        WHEN '已成交' THEN 3
        WHEN '已取消' THEN 4
        ELSE 5
    END
"""
FOLLOW_UP_STATUSES = ["未回访", "已回访", "有复购意向", "无复购意向"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-online")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

LOGIN_ATTEMPTS = {}
MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 600


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    protected_prefixes = (
        "/admin",
        "/api/",
        "/orders/",
        "/stats",
        "/export",
        "/exports",
        "/backup",
        "/appointment-qr",
        "/login",
    )
    if request.path.startswith(protected_prefixes):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def init_db():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            service_type TEXT NOT NULL,
            area TEXT,
            preferred_time TEXT,
            need_invoice TEXT DEFAULT '否',
            source TEXT,
            status TEXT DEFAULT '待联系',
            quote_amount REAL DEFAULT 0,
            deal_amount REAL DEFAULT 0,
            owner TEXT,
            follow_up_status TEXT DEFAULT '未回访',
            remark TEXT,
            is_new INTEGER DEFAULT 0,
            updated_at TEXT,
            deleted_at TEXT
        )
        """
    )
    ensure_column(conn, "orders", "deleted_at", "TEXT")
    ensure_column(conn, "orders", "is_new", "INTEGER DEFAULT 0")
    ensure_column(conn, "orders", "updated_at", "TEXT")
    conn.execute("UPDATE orders SET status = '已联系' WHERE status = '已报价'")
    conn.execute("UPDATE orders SET status = '已成交' WHERE status = '已完成'")
    conn.execute("UPDATE orders SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''")
    conn.execute("UPDATE orders SET is_new = 1 WHERE status = '待联系'")
    conn.execute("UPDATE orders SET is_new = 0 WHERE status <> '待联系' AND (is_new IS NULL OR is_new <> 0)")
    conn.commit()
    conn.close()


def ensure_column(conn, table, column, definition):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def normalize_status(status):
    status = LEGACY_STATUS_MAP.get(status, status)
    return status if status in ORDER_STATUSES else "待联系"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_order_row(row):
    order = dict(row)
    order["status"] = normalize_status(order.get("status"))
    order["is_new"] = 1 if order["status"] == "待联系" or int(order.get("is_new") or 0) else 0
    order["updated_at"] = order.get("updated_at") or order.get("created_at")
    return order


def get_order_counts():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM orders
        WHERE deleted_at IS NULL
        GROUP BY status
        """
    ).fetchall()
    conn.close()
    counts = {status: 0 for status in ORDER_STATUSES}
    for row in rows:
        counts[normalize_status(row["status"])] += row["count"]
    return counts


def order_summary(order):
    if not order:
        return None
    return {
        "id": order["id"],
        "order_no": order["order_no"],
        "created_at": order["created_at"],
        "updated_at": order["updated_at"] or order["created_at"],
        "customer_name": order["customer_name"],
        "phone": order["phone"],
        "service_type": order["service_type"],
        "address": order["address"],
        "status": normalize_status(order["status"]),
        "is_new": int(order["is_new"] or 0),
    }


def get_latest_new_order():
    conn = get_db()
    row = conn.execute(
        f"""
        SELECT * FROM orders
        WHERE deleted_at IS NULL AND status = '待联系'
        ORDER BY
            COALESCE(NULLIF(updated_at, ''), created_at) DESC,
            created_at DESC,
            id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return order_summary(normalize_order_row(row)) if row else None


def order_count_payload():
    counts = get_order_counts()
    latest_order = get_latest_new_order()
    return {
        "counts": counts,
        "pending_count": counts["待联系"],
        "new_count": counts["待联系"],
        "today_new": count_today_orders(),
        "latest_order_id": latest_order["id"] if latest_order else 0,
        "latest_order_time": latest_order["created_at"] if latest_order else "",
        "latest_order": latest_order,
    }


def count_today_orders():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) AS count FROM orders WHERE deleted_at IS NULL AND created_at LIKE ?",
        (f"{today}%",),
    ).fetchone()["count"]
    conn.close()
    return count


def make_order_no():
    return "BJ" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]


def row_count():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) AS count FROM orders").fetchone()["count"]
    conn.close()
    return count


def seed_demo_data(force=False):
    init_db()
    if row_count() and not force:
        return
    conn = get_db()
    if force:
        conn.execute("DELETE FROM orders")

    now = datetime.now()
    demo_orders = [
        {
            "customer_name": "张先生",
            "phone": "13800000001",
            "address": "北京市朝阳区望京某小区",
            "service_type": "开荒保洁",
            "area": "120㎡",
            "preferred_time": "本周六上午",
            "need_invoice": "否",
            "source": "微信",
            "status": "待联系",
            "quote_amount": 0,
            "deal_amount": 0,
            "owner": "老板",
            "follow_up_status": "未回访",
            "remark": "装修后首次开荒，重点看地面和窗槽。",
        },
        {
            "customer_name": "李女士",
            "phone": "13800000002",
            "address": "北京市海淀区中关村办公室",
            "service_type": "玻璃清洗",
            "area": "办公室",
            "preferred_time": "明天下午",
            "need_invoice": "是",
            "source": "小红书",
            "status": "已联系",
            "quote_amount": 800,
            "deal_amount": 0,
            "owner": "王师傅",
            "follow_up_status": "未回访",
            "remark": "办公室外窗和内隔断玻璃。",
        },
        {
            "customer_name": "王先生",
            "phone": "13800000003",
            "address": "北京市丰台区科技园",
            "service_type": "地毯清洗",
            "area": "300㎡",
            "preferred_time": "周五晚间",
            "need_invoice": "是",
            "source": "电话咨询",
            "status": "已成交",
            "quote_amount": 1200,
            "deal_amount": 1200,
            "owner": "刘师傅",
            "follow_up_status": "未回访",
            "remark": "办公地毯清洗，要求不影响白天办公。",
        },
        {
            "customer_name": "刘女士",
            "phone": "13800000004",
            "address": "北京市通州区运河商务区",
            "service_type": "深度保洁",
            "area": "90㎡",
            "preferred_time": "已服务",
            "need_invoice": "否",
            "source": "熟人介绍",
            "status": "已成交",
            "quote_amount": 500,
            "deal_amount": 500,
            "owner": "李师傅",
            "follow_up_status": "已回访",
            "remark": "厨房、卫生间深度清洁，客户反馈满意。",
        },
        {
            "customer_name": "赵经理",
            "phone": "13800000005",
            "address": "北京市大兴区亦庄办公楼",
            "service_type": "办公室保洁",
            "area": "500㎡",
            "preferred_time": "下周一",
            "need_invoice": "是",
            "source": "抖音",
            "status": "已联系",
            "quote_amount": 1800,
            "deal_amount": 0,
            "owner": "老板",
            "follow_up_status": "未回访",
            "remark": "希望长期合作，先做一次试单。",
        },
    ]

    for index, item in enumerate(demo_orders, start=1):
        created_at = now.replace(hour=max(8, now.hour - index), minute=15, second=0, microsecond=0)
        conn.execute(
            """
            INSERT INTO orders (
                order_no, created_at, updated_at, is_new, customer_name, phone, address, service_type,
                area, preferred_time, need_invoice, source, status, quote_amount,
                deal_amount, owner, follow_up_status, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"BJ{now.strftime('%Y%m%d')}{index:04d}",
                created_at.strftime("%Y-%m-%d %H:%M"),
                created_at.strftime("%Y-%m-%d %H:%M"),
                1 if normalize_status(item["status"]) == "待联系" else 0,
                item["customer_name"],
                item["phone"],
                item["address"],
                item["service_type"],
                item["area"],
                item["preferred_time"],
                item["need_invoice"],
                item["source"],
                normalize_status(item["status"]),
                item["quote_amount"],
                item["deal_amount"],
                item["owner"],
                item["follow_up_status"],
                item["remark"],
            ),
        )
    conn.commit()
    conn.close()


def money(value):
    try:
        result = float(value or 0)
        return result if result >= 0 else 0
    except ValueError:
        return 0


def clean_text(value, max_length=200):
    return (value or "").strip()[:max_length]


def require_admin():
    return session.get("admin_logged_in") is True


def client_ip_key():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def login_lock_remaining():
    record = LOGIN_ATTEMPTS.get(client_ip_key())
    if not record:
        return 0
    locked_until = record.get("locked_until", 0)
    remaining = int(locked_until - time.time())
    if remaining <= 0:
        if locked_until:
            LOGIN_ATTEMPTS.pop(client_ip_key(), None)
        return 0
    return remaining


def record_login_failure():
    key = client_ip_key()
    record = LOGIN_ATTEMPTS.setdefault(key, {"count": 0, "locked_until": 0})
    record["count"] += 1
    if record["count"] >= MAX_LOGIN_FAILURES:
        record["locked_until"] = time.time() + LOGIN_LOCK_SECONDS


def clear_login_failures():
    LOGIN_ATTEMPTS.pop(client_ip_key(), None)


def validate_choice(value, options, default):
    return value if value in options else default


def submit_url():
    return PUBLIC_SUBMIT_URL or url_for("submit", _external=True)


def fetch_json(url, timeout=8):
    request_obj = Request(url, headers={"User-Agent": "BeijingCleaningOrderDemo/1.0"})
    with urlopen(request_obj, timeout=timeout) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def reverse_geocode_with_amap(latitude, longitude):
    if not AMAP_KEY:
        return ""
    params = {
        "key": AMAP_KEY,
        "location": f"{longitude},{latitude}",
        "radius": 1000,
        "extensions": "base",
        "output": "json",
    }
    data = fetch_json("https://restapi.amap.com/v3/geocode/regeo?" + urlencode(params))
    if data.get("status") != "1":
        return ""
    regeocode = data.get("regeocode") or {}
    return regeocode.get("formatted_address") or ""


def reverse_geocode_with_osm(latitude, longitude):
    params = {
        "format": "jsonv2",
        "accept-language": "zh-CN",
        "lat": latitude,
        "lon": longitude,
    }
    data = fetch_json("https://nominatim.openstreetmap.org/reverse?" + urlencode(params))
    return data.get("display_name") or ""


def validate_submit_form(form):
    data = {
        "customer_name": clean_text(form.get("customer_name"), 40),
        "phone": clean_text(form.get("phone"), 30),
        "address": clean_text(form.get("address"), 160),
        "service_type": validate_choice(form.get("service_type"), SERVICE_TYPES, SERVICE_TYPES[0]),
        "area": clean_text(form.get("area"), 40),
        "preferred_time": clean_text(form.get("preferred_time"), 80),
        "need_invoice": validate_choice(form.get("need_invoice"), ["是", "否"], "否"),
        "source": validate_choice(form.get("source"), SOURCES, "其他"),
        "remark": clean_text(form.get("remark"), 500),
    }
    errors = []
    if not data["customer_name"]:
        errors.append("请填写客户姓名。")
    if not data["phone"]:
        errors.append("请填写联系电话。")
    elif len(data["phone"]) < 6:
        errors.append("联系电话看起来太短，请检查。")
    if not data["address"]:
        errors.append("请填写服务地址。")
    return data, errors


def get_orders(filters=None):
    filters = filters or {}
    sql = "SELECT * FROM orders WHERE deleted_at IS NULL"
    params = []

    if filters.get("status"):
        sql += " AND status = ?"
        params.append(normalize_status(filters["status"]))
    if filters.get("service_type"):
        sql += " AND service_type = ?"
        params.append(filters["service_type"])
    if filters.get("source"):
        sql += " AND source = ?"
        params.append(filters["source"])
    if filters.get("keyword"):
        sql += " AND (customer_name LIKE ? OR phone LIKE ? OR address LIKE ?)"
        keyword = f"%{filters['keyword']}%"
        params.extend([keyword, keyword, keyword])

    sql += f"""
        ORDER BY
            {STATUS_ORDER_SQL} ASC,
            CASE WHEN status = '待联系' THEN 1 ELSE COALESCE(is_new, 0) END DESC,
            COALESCE(NULLIF(updated_at, ''), created_at) DESC,
            created_at DESC,
            id DESC
    """
    conn = get_db()
    orders = conn.execute(sql, params).fetchall()
    conn.close()
    return [normalize_order_row(order) for order in orders]


def summarize_orders(orders):
    service_counts = {}
    source_counts = {}
    total_amount = 0
    status_counts = {status: 0 for status in ORDER_STATUSES}
    for order in orders:
        status = normalize_status(order["status"])
        status_counts[status] += 1
        service_counts[order["service_type"]] = service_counts.get(order["service_type"], 0) + 1
        source = order["source"] or "未填写"
        source_counts[source] = source_counts.get(source, 0) + 1
        if status == "已成交":
            total_amount += money(order["deal_amount"])
    return {
        "total": len(orders),
        "waiting": status_counts["待联系"],
        "contacted": status_counts["已联系"],
        "dealed": status_counts["已成交"],
        "canceled": status_counts["已取消"],
        "amount": total_amount,
        "service_counts": sorted(service_counts.items(), key=lambda item: item[1], reverse=True),
        "source_counts": sorted(source_counts.items(), key=lambda item: item[1], reverse=True),
    }


@app.context_processor
def inject_options():
    return {
        "service_types": SERVICE_TYPES,
        "sources": SOURCES,
        "order_statuses": ORDER_STATUSES,
        "follow_up_statuses": FOLLOW_UP_STATUSES,
    }


@app.route("/")
def home():
    return redirect(url_for("submit"))


@app.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "POST":
        data, errors = validate_submit_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("submit.html", form_data=data, public_page=True), 400
        conn = get_db()
        conn.execute(
            """
            INSERT INTO orders (
                order_no, created_at, updated_at, is_new, customer_name, phone, address, service_type,
                area, preferred_time, need_invoice, source, status, quote_amount,
                deal_amount, owner, follow_up_status, remark
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, '待联系', 0, 0, '', '未回访', ?)
            """,
            (
                make_order_no(),
                now_text(),
                now_text(),
                data["customer_name"],
                data["phone"],
                data["address"],
                data["service_type"],
                data["area"],
                data["preferred_time"],
                data["need_invoice"],
                data["source"],
                data["remark"],
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("submit_success"))
    return render_template("submit.html", form_data={}, public_page=True)


@app.route("/submit/success")
def submit_success():
    return render_template("submit_success.html", public_page=True)


@app.route("/submit/reverse-geocode", methods=["POST"])
def api_reverse_geocode():
    payload = request.get_json(silent=True) or {}
    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "定位坐标无效"}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"ok": False, "error": "定位坐标超出范围"}), 400

    address = ""
    provider = ""
    try:
        address = reverse_geocode_with_amap(latitude, longitude)
        provider = "amap" if address else ""
    except Exception:
        address = ""

    if not address:
        try:
            address = reverse_geocode_with_osm(latitude, longitude)
            provider = "osm" if address else ""
        except Exception:
            address = ""

    if not address:
        return jsonify({
            "ok": False,
            "error": "暂时没能识别出文字地址，请手动补充小区、楼号或门牌。",
        }), 502

    return jsonify({
        "ok": True,
        "address": address,
        "provider": provider,
        "latitude": latitude,
        "longitude": longitude,
    })


@app.route("/appointment-qr")
def appointment_qr():
    if not require_admin():
        return redirect(url_for("login"))
    return render_template("appointment_qr.html", submit_link=submit_url())


@app.route("/appointment-qr.png")
def appointment_qr_png():
    if not require_admin():
        return redirect(url_for("login"))
    image = qrcode.make(submit_url())
    stream = BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    return send_file(stream, mimetype="image/png")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        remaining = login_lock_remaining()
        if remaining:
            minutes = max(1, remaining // 60)
            flash(f"密码错误次数过多，请约 {minutes} 分钟后再试。", "error")
            return render_template("login.html"), 429

        password = request.form.get("password", "")
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            clear_login_failures()
            session.permanent = True
            session["admin_logged_in"] = True
            flash("已进入老板后台。", "success")
            return redirect(url_for("admin"))
        record_login_failure()
        flash("后台密码不正确。", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("已退出后台。", "success")
    return redirect(url_for("login"))


@app.route("/admin")
def admin():
    if not require_admin():
        return render_template("login.html")
    filters = {
        "status": normalize_status(request.args.get("status", "").strip()) if request.args.get("status", "").strip() else "",
        "service_type": request.args.get("service_type", "").strip(),
        "source": request.args.get("source", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
    }
    orders = get_orders(filters)
    counts = get_order_counts()
    filtered_summary = summarize_orders(orders)
    return render_template(
        "admin.html",
        orders=orders,
        filters=filters,
        today_new=count_today_orders(),
        counts=counts,
        waiting=counts["待联系"],
        filtered_summary=filtered_summary,
        deal_amount=filtered_summary["amount"],
        page_label="老板后台",
    )


@app.route("/api/order-counts")
def api_order_counts():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(order_count_payload())


@app.route("/api/orders")
def api_orders():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    filters = {
        "status": normalize_status(request.args.get("status", "").strip()) if request.args.get("status", "").strip() else "",
        "service_type": request.args.get("service_type", "").strip(),
        "source": request.args.get("source", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
    }
    orders = get_orders(filters)
    payload = order_count_payload()
    latest_updated_at = max((order["updated_at"] or order["created_at"] for order in orders), default="")
    payload.update({
        "latest_updated_at": latest_updated_at,
        "html": render_template("_order_cards.html", orders=orders),
        "summary": summarize_orders(orders),
    })
    return jsonify(payload)


@app.route("/orders/<int:order_id>/update", methods=["POST"])
def update_order(order_id):
    if not require_admin():
        return redirect(url_for("login"))
    status = validate_choice(request.form.get("status"), ORDER_STATUSES, "待联系")
    follow_up_status = validate_choice(request.form.get("follow_up_status"), FOLLOW_UP_STATUSES, "未回访")
    is_new = 1 if status == "待联系" else 0
    conn = get_db()
    conn.execute(
        """
        UPDATE orders
        SET status = ?, quote_amount = ?, deal_amount = ?, owner = ?,
            follow_up_status = ?, remark = ?, is_new = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            money(request.form.get("quote_amount")),
            money(request.form.get("deal_amount")),
            clean_text(request.form.get("owner"), 40),
            follow_up_status,
            clean_text(request.form.get("remark"), 500),
            is_new,
            now_text(),
            order_id,
        ),
    )
    conn.commit()
    conn.close()
    flash("订单已保存。", "success")
    return redirect(request.referrer or url_for("admin"))


@app.route("/orders/<int:order_id>/delete", methods=["POST"])
def delete_order(order_id):
    if not require_admin():
        return redirect(url_for("login"))
    conn = get_db()
    current_time = now_text()
    conn.execute("UPDATE orders SET deleted_at = ?, updated_at = ? WHERE id = ?", (current_time, current_time, order_id))
    conn.commit()
    conn.close()
    flash("订单已移入删除记录，数据库中仍保留。", "success")
    return redirect(request.referrer or url_for("admin"))


@app.route("/stats")
def stats():
    if not require_admin():
        return redirect(url_for("login"))
    conn = get_db()
    orders = [normalize_order_row(order) for order in conn.execute("SELECT * FROM orders WHERE deleted_at IS NULL").fetchall()]
    service_counts = conn.execute(
        "SELECT service_type, COUNT(*) AS count FROM orders WHERE deleted_at IS NULL GROUP BY service_type ORDER BY count DESC"
    ).fetchall()
    source_counts = conn.execute(
        "SELECT source, COUNT(*) AS count FROM orders WHERE deleted_at IS NULL GROUP BY source ORDER BY count DESC"
    ).fetchall()
    conn.close()

    month_prefix = datetime.now().strftime("%Y-%m")
    current_month = [order for order in orders if order["created_at"].startswith(month_prefix)]
    month_deals = [order for order in current_month if normalize_status(order["status"]) == "已成交"]
    status_counts = {status: 0 for status in ORDER_STATUSES}
    for order in orders:
        status_counts[normalize_status(order["status"])] += 1
    data = {
        "total": len(orders),
        "waiting": status_counts["待联系"],
        "contacted": status_counts["已联系"],
        "dealed": status_counts["已成交"],
        "canceled": status_counts["已取消"],
        "month_total": len(current_month),
        "month_dealed": len(month_deals),
        "month_amount": sum(money(order["deal_amount"]) for order in month_deals),
    }
    return render_template("stats.html", data=data, service_counts=service_counts, source_counts=source_counts, page_label="数据统计")


@app.route("/export")
def export_excel():
    if not require_admin():
        return redirect(url_for("login"))
    filters = {
        "status": request.args.get("status", "").strip(),
        "service_type": request.args.get("service_type", "").strip(),
        "source": request.args.get("source", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
    }
    orders = get_orders(filters)
    wb = Workbook()
    ws = wb.active
    ws.title = "预约订单"
    headers = [
        "订单编号",
        "提交时间",
        "客户姓名",
        "联系电话",
        "服务地址",
        "服务类型",
        "房屋面积",
        "期望上门时间",
        "是否需要开票",
        "客户来源",
        "订单状态",
        "报价金额",
        "成交金额",
        "负责人",
        "回访状态",
        "备注",
    ]
    ws.append(headers)
    for order in orders:
        ws.append([
            order["order_no"],
            order["created_at"],
            order["customer_name"],
            order["phone"],
            order["address"],
            order["service_type"],
            order["area"],
            order["preferred_time"],
            order["need_invoice"],
            order["source"],
            normalize_status(order["status"]),
            order["quote_amount"],
            order["deal_amount"],
            order["owner"],
            order["follow_up_status"],
            order["remark"],
        ])

    for column in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 10), 32)

    filename = f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    output_path = os.path.join(EXPORT_DIR, filename)
    wb.save(output_path)
    flash("Excel 已导出，下面已直接显示本次导出的统计结果和订单明细。", "success")
    return redirect(url_for("export_result", filename=filename, **filters))


@app.route("/exports")
def export_list():
    if not require_admin():
        return redirect(url_for("login"))
    os.makedirs(EXPORT_DIR, exist_ok=True)
    files = []
    for filename in sorted(os.listdir(EXPORT_DIR), reverse=True):
        if filename.endswith(".xlsx"):
            path = os.path.join(EXPORT_DIR, filename)
            files.append({
                "filename": filename,
                "size_kb": max(1, round(os.path.getsize(path) / 1024)),
                "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M"),
            })
    return render_template(
        "exports.html",
        files=files,
        current_file=None,
        export_dir=EXPORT_DIR,
        orders=None,
        summary=None,
        filters={},
        page_label="导出记录",
    )


@app.route("/exports/result/<path:filename>")
def export_result(filename):
    if not require_admin():
        return redirect(url_for("login"))
    if os.path.basename(filename) != filename or not filename.endswith(".xlsx"):
        abort(404)
    path = os.path.join(EXPORT_DIR, filename)
    if not os.path.exists(path):
        abort(404)
    files = [{
        "filename": filename,
        "size_kb": max(1, round(os.path.getsize(path) / 1024)),
        "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M"),
    }]
    filters = {
        "status": request.args.get("status", "").strip(),
        "service_type": request.args.get("service_type", "").strip(),
        "source": request.args.get("source", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
    }
    orders = get_orders(filters)
    return render_template(
        "exports.html",
        files=files,
        current_file=filename,
        export_dir=EXPORT_DIR,
        orders=orders,
        summary=summarize_orders(orders),
        filters=filters,
        page_label="导出记录",
    )


@app.route("/exports/download/<path:filename>")
def download_export(filename):
    if not require_admin():
        return redirect(url_for("login"))
    if os.path.basename(filename) != filename or not filename.endswith(".xlsx"):
        abort(404)
    path = os.path.join(EXPORT_DIR, filename)
    if not os.path.exists(path):
        abort(404)
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/backup/database")
def backup_database():
    if not require_admin():
        return redirect(url_for("login"))
    if not os.path.exists(DATABASE):
        init_db()
    filename = f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
    return send_file(DATABASE, as_attachment=True, download_name=filename)


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("数据库已初始化")


@app.cli.command("seed-demo")
def seed_demo_command():
    init_db()
    seed_demo_data(force=True)
    print("演示数据已写入")


init_db()
if SEED_DEMO:
    seed_demo_data()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
