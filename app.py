from datetime import datetime
from io import BytesIO
import os
import re
import sqlite3

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
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

ORDER_STATUSES = ["待联系", "已联系", "已报价", "已成交", "已完成", "已取消"]
FOLLOW_UP_STATUSES = ["未回访", "已回访", "有复购意向", "无复购意向"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-online")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


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
            deleted_at TEXT
        )
        """
    )
    ensure_column(conn, "orders", "deleted_at", "TEXT")
    conn.commit()
    conn.close()


def ensure_column(conn, table, column, definition):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
            "status": "已报价",
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
            "preferred_time": "已完成",
            "need_invoice": "否",
            "source": "熟人介绍",
            "status": "已完成",
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
            "status": "已报价",
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
                order_no, created_at, customer_name, phone, address, service_type,
                area, preferred_time, need_invoice, source, status, quote_amount,
                deal_amount, owner, follow_up_status, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"BJ{now.strftime('%Y%m%d')}{index:04d}",
                created_at.strftime("%Y-%m-%d %H:%M"),
                item["customer_name"],
                item["phone"],
                item["address"],
                item["service_type"],
                item["area"],
                item["preferred_time"],
                item["need_invoice"],
                item["source"],
                item["status"],
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


def validate_choice(value, options, default):
    return value if value in options else default


def submit_url():
    return PUBLIC_SUBMIT_URL or url_for("submit", _external=True)


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
        params.append(filters["status"])
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

    sql += " ORDER BY created_at DESC, id DESC"
    conn = get_db()
    orders = conn.execute(sql, params).fetchall()
    conn.close()
    return orders


def summarize_orders(orders):
    service_counts = {}
    source_counts = {}
    total_amount = 0
    for order in orders:
        service_counts[order["service_type"]] = service_counts.get(order["service_type"], 0) + 1
        source = order["source"] or "未填写"
        source_counts[source] = source_counts.get(source, 0) + 1
        if order["status"] in ["已成交", "已完成"]:
            total_amount += money(order["deal_amount"])
    return {
        "total": len(orders),
        "waiting": sum(1 for order in orders if order["status"] == "待联系"),
        "quoted": sum(1 for order in orders if order["status"] == "已报价"),
        "dealed": sum(1 for order in orders if order["status"] == "已成交"),
        "done": sum(1 for order in orders if order["status"] == "已完成"),
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
                order_no, created_at, customer_name, phone, address, service_type,
                area, preferred_time, need_invoice, source, status, quote_amount,
                deal_amount, owner, follow_up_status, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '待联系', 0, 0, '', '未回访', ?)
            """,
            (
                make_order_no(),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
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
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("已进入老板后台。", "success")
            return redirect(url_for("admin"))
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
        return redirect(url_for("login"))
    filters = {
        "status": request.args.get("status", "").strip(),
        "service_type": request.args.get("service_type", "").strip(),
        "source": request.args.get("source", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
    }
    orders = get_orders(filters)
    today = datetime.now().strftime("%Y-%m-%d")
    today_new = sum(1 for order in orders if order["created_at"].startswith(today))
    waiting = sum(1 for order in orders if order["status"] == "待联系")
    quoted = sum(1 for order in orders if order["status"] == "已报价")
    deal_amount = sum(money(order["deal_amount"]) for order in orders if order["status"] in ["已成交", "已完成"])
    return render_template(
        "admin.html",
        orders=orders,
        filters=filters,
        today_new=today_new,
        waiting=waiting,
        quoted=quoted,
        deal_amount=deal_amount,
    )


@app.route("/orders/<int:order_id>/update", methods=["POST"])
def update_order(order_id):
    if not require_admin():
        return redirect(url_for("login"))
    status = validate_choice(request.form.get("status"), ORDER_STATUSES, "待联系")
    follow_up_status = validate_choice(request.form.get("follow_up_status"), FOLLOW_UP_STATUSES, "未回访")
    conn = get_db()
    conn.execute(
        """
        UPDATE orders
        SET status = ?, quote_amount = ?, deal_amount = ?, owner = ?,
            follow_up_status = ?, remark = ?
        WHERE id = ?
        """,
        (
            status,
            money(request.form.get("quote_amount")),
            money(request.form.get("deal_amount")),
            clean_text(request.form.get("owner"), 40),
            follow_up_status,
            clean_text(request.form.get("remark"), 500),
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
    conn.execute("UPDATE orders SET deleted_at = ? WHERE id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M"), order_id))
    conn.commit()
    conn.close()
    flash("订单已移入删除记录，数据库中仍保留。", "success")
    return redirect(request.referrer or url_for("admin"))


@app.route("/stats")
def stats():
    if not require_admin():
        return redirect(url_for("login"))
    conn = get_db()
    orders = conn.execute("SELECT * FROM orders WHERE deleted_at IS NULL").fetchall()
    service_counts = conn.execute(
        "SELECT service_type, COUNT(*) AS count FROM orders WHERE deleted_at IS NULL GROUP BY service_type ORDER BY count DESC"
    ).fetchall()
    source_counts = conn.execute(
        "SELECT source, COUNT(*) AS count FROM orders WHERE deleted_at IS NULL GROUP BY source ORDER BY count DESC"
    ).fetchall()
    conn.close()

    month_prefix = datetime.now().strftime("%Y-%m")
    current_month = [order for order in orders if order["created_at"].startswith(month_prefix)]
    month_deals = [order for order in current_month if order["status"] in ["已成交", "已完成"]]
    data = {
        "total": len(orders),
        "waiting": sum(1 for order in orders if order["status"] == "待联系"),
        "quoted": sum(1 for order in orders if order["status"] == "已报价"),
        "dealed": sum(1 for order in orders if order["status"] == "已成交"),
        "done": sum(1 for order in orders if order["status"] == "已完成"),
        "month_total": len(current_month),
        "month_dealed": len(month_deals),
        "month_amount": sum(money(order["deal_amount"]) for order in month_deals),
    }
    return render_template("stats.html", data=data, service_counts=service_counts, source_counts=source_counts)


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
            order["status"],
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
