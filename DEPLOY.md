# 线上部署说明

本项目是 Flask + SQLite 演示版。推荐先部署到 Render 或 Railway 做演示。

## 环境变量

必须设置：

- `ADMIN_PASSWORD`：后台密码，不要使用默认 `123456`。
- `SECRET_KEY`：Flask 会话密钥，随便生成一串长随机字符。

可选设置：

- `SEED_DEMO=1`：自动写入演示数据。演示阶段可开，正式使用建议设为 `0`。
- `DATA_DIR`：数据库和导出文件保存目录。Render 如绑定 Disk，可设为 `/var/data`。
- `PUBLIC_SUBMIT_URL`：客户预约二维码使用的正式网址，例如 `https://你的域名/submit`。

## 启动命令

```bash
gunicorn app:app
```

## 注意

免费平台可能会休眠；没有持久磁盘时，SQLite 数据可能在重新部署后丢失。正式商用前请改成云数据库或绑定持久化磁盘。
