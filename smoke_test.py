from io import BytesIO
import re
import sqlite3

from openpyxl import load_workbook

from app import DATABASE, app, init_db, seed_demo_data


def main():
    init_db()
    seed_demo_data(force=True)
    client = app.test_client()

    admin = client.get("/admin", follow_redirects=False)
    assert admin.status_code == 302 and "/login" in admin.headers["Location"]

    bad = client.post("/submit", data={"customer_name": "", "phone": "", "address": ""})
    assert bad.status_code == 400

    test_name = "测试客户自测"
    good = client.post(
        "/submit",
        data={
            "customer_name": test_name,
            "phone": "13900000000",
            "address": "北京市测试区",
            "service_type": "开荒保洁",
            "area": "88㎡",
            "preferred_time": "今天下午",
            "need_invoice": "否",
            "source": "微信",
            "remark": "流程测试",
        },
        follow_redirects=False,
    )
    assert good.status_code == 302 and "/submit/success" in good.headers["Location"]

    login = client.post("/login", data={"password": "123456"}, follow_redirects=True)
    assert login.status_code == 200 and "老板后台".encode("utf-8") in login.data

    qr_page = client.get("/appointment-qr")
    assert qr_page.status_code == 200 and "客户预约链接".encode("utf-8") in qr_page.data
    qr_png = client.get("/appointment-qr.png")
    assert qr_png.status_code == 200 and qr_png.data[:8] == b"\x89PNG\r\n\x1a\n"

    conn = sqlite3.connect(DATABASE)
    order_row = conn.execute(
        "SELECT id FROM orders WHERE customer_name = ? AND deleted_at IS NULL ORDER BY id DESC",
        (test_name,),
    ).fetchone()
    assert order_row is not None
    order_id = order_row[0]
    conn.close()

    update = client.post(
        f"/orders/{order_id}/update",
        data={
            "status": "已成交",
            "quote_amount": "600",
            "deal_amount": "580",
            "owner": "老板",
            "follow_up_status": "已回访",
            "remark": "已成交测试",
        },
    )
    assert update.status_code == 302

    export = client.get("/export", follow_redirects=True)
    assert export.status_code == 200 and "本次导出的订单明细".encode("utf-8") in export.data
    match = re.search(rb'href="([^"]*/exports/download/[^"]+)"', export.data)
    assert match
    download_url = match.group(1).decode("utf-8")
    excel = client.get(download_url)
    assert excel.status_code == 200
    workbook = load_workbook(BytesIO(excel.data))
    assert workbook.active.max_row >= 2

    backup = client.get("/backup/database")
    assert backup.status_code == 200 and len(backup.data) > 1000

    delete = client.post(f"/orders/{order_id}/delete")
    assert delete.status_code == 302
    conn = sqlite3.connect(DATABASE)
    deleted_at = conn.execute("SELECT deleted_at FROM orders WHERE id = ?", (order_id,)).fetchone()[0]
    visible_count = conn.execute("SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL").fetchone()[0]
    conn.close()
    assert deleted_at is not None
    assert visible_count == 5

    seed_demo_data(force=True)
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
