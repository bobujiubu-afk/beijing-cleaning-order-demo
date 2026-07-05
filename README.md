# 北京保洁客户预约订单管理系统

这是一个本地可运行的演示版，适合给北京保洁、家政、开荒保洁、地毯清洗、石材结晶、办公室保洁等小商家演示。

## 文件作用

- `app.py`：后端主程序，负责预约提交、订单管理、统计、Excel 导出、演示数据。
- `templates/`：页面模板。
- `templates/submit.html`：客户预约页。
- `templates/admin.html`：老板后台订单页。
- `templates/stats.html`：数据统计页。
- `templates/submit_success.html`：预约提交成功页。
- `templates/base.html`：公共顶部导航和页面基础结构。
- `static/style.css`：页面样式，兼容手机和电脑。
- `database.db`：SQLite 数据库，第一次运行后自动生成。
- `requirements.txt`：需要安装的 Python 依赖。
- `start-demo.cmd`：本机一键启动脚本。
- `smoke_test.py`：基础流程自测脚本。

## 安装依赖

第一次运行前，在项目目录执行：

```powershell
python -m pip install -r requirements.txt
```

如果你的电脑 `python` 命令不可用，可以换成：

```powershell
py -m pip install -r requirements.txt
```

在这台电脑上，已经验证可用的 Python 路径是：

```powershell
& "C:\Users\申\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -r requirements.txt
```

## 本地运行

在项目目录执行：

```powershell
python app.py
```

如果 `python` 命令不可用，可以直接双击：

```text
start-demo.cmd
```

或者执行：

```powershell
& "C:\Users\申\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py
```

看到 `Running on http://127.0.0.1:5000` 后，浏览器打开：

- 客户预约页：http://127.0.0.1:5000/submit
- 老板后台：http://127.0.0.1:5000/admin
- 数据统计：http://127.0.0.1:5000/stats

## 添加测试数据

第一次运行 `python app.py` 时，系统会自动创建数据库并写入演示数据。

如果你想重置演示数据，可以执行：

```powershell
flask --app app seed-demo
```

这会清空当前订单并重新写入 5 条演示订单。

注意：正式使用时不要随便运行 `seed-demo`，它会清空当前订单。

## 导出 Excel

进入老板后台：

```text
http://127.0.0.1:5000/admin
```

点击右上角“导出 Excel”即可下载当前筛选结果。

## 后台登录

第一版已经加了简单后台密码。默认演示密码：

```text
123456
```

如果要给真实商家使用，请先设置新的后台密码：

```powershell
$env:ADMIN_PASSWORD="你的新密码"
.\start-demo.cmd
```

正式部署到服务器时也必须设置 `ADMIN_PASSWORD`，不要用默认密码。

## 数据备份

老板后台右上角可以点击“备份数据库”，下载完整的 `database.db`。

建议真实客户每天至少备份一次，尤其是在没有云数据库之前。

## 自测项目是否正常

在项目目录执行：

```powershell
& "C:\Users\申\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" smoke_test.py
```

看到 `Smoke test passed.` 说明提交、登录、修改、导出、备份、软删除都正常。

## 常见问题排查

1. 如果提示找不到 Flask：
   重新执行 `python -m pip install -r requirements.txt`。

2. 如果端口 5000 被占用：
   打开 `app.py` 最后一行，把 `port=5000` 改成 `port=5001`，然后访问 `http://127.0.0.1:5001`。

3. 如果数据库数据乱了：
   关闭程序，删除 `database.db`，再运行 `python app.py`，会重新生成演示数据。

   正式使用后不要这样做，删除 `database.db` 会丢失订单。正式使用应先从后台下载数据库备份。

4. 如果 Excel 打不开：
   确认安装了 `openpyxl`，重新执行依赖安装命令。

## 后续部署思路

第一版本地演示通过后，线上部署建议走最简单路线：

1. 买一台轻量云服务器。
2. 安装 Python。
3. 上传本项目文件。
4. 安装依赖。
5. 使用 Gunicorn 或 Waitress 启动 Flask。
6. 用 Nginx 绑定域名。
7. 后续再加登录账号、员工账号、短信提醒、微信通知和二维码入口。

正式上线前建议增加：

- 数据备份。
- HTTPS 证书。
- 手机号格式校验。
- 删除订单二次权限确认。
- 员工账号和操作记录。
- 定时自动备份。
- 预约短信或微信提醒。
