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

## 客户端和老板端安全边界

系统现在把客户预约端和老板后台端分开处理：

- 客户端公开页面只开放 `/submit`、`/submit/success` 和 `/submit/reverse-geocode`。
- 老板后台 `/admin`、订单 API `/api/orders`、`/api/order-counts`、订单修改、Excel 导出、数据库备份都必须先登录。
- 后台和 API 响应会设置 `Cache-Control: no-store`，避免订单数据被浏览器缓存。
- 后台页面带 `X-Robots-Tag: noindex, nofollow`，避免被搜索引擎收录。
- 登录失败 5 次会临时锁定 10 分钟，减少暴力猜密码风险。
- 登录会话使用 HttpOnly Cookie，普通页面脚本不能直接读取后台登录 Cookie。

真实交付客户前，建议把 `ADMIN_PASSWORD` 改成强密码，并把 `SECRET_KEY` 设置成随机长字符串。低价演示版可以先用单老板密码，正式商用最好升级为独立账号、操作日志和更严格权限。

## 数据备份

老板后台右上角可以点击“备份数据库”，下载完整的 `database.db`。

建议真实客户每天至少备份一次，尤其是在没有云数据库之前。

## 新订单消息提醒

老板后台打开时，系统会每 5 秒检查一次新订单。如果页面打开后有客户提交新预约，后台会：

- 顶部弹出“有新的客户预约，请尽快联系！”提醒。
- 新订单继续排在订单列表最上方，并显示小红点。
- 浏览器标题在“【新订单】北京东科订单后台”和正常标题之间闪烁。
- 点击“开启声音提醒”后，新订单会播放三声短提示音，并在支持的手机上震动。
- 点击“开启手机消息推送”后，系统会把当前手机登记为接收设备；客户提交新订单时，服务器会主动给手机发系统通知。
- 手机添加到主屏幕后，会显示“东科订单”图标；支持 App Badge 的浏览器会在图标上显示待联系数量。
- 声音提醒会短促响 3 次，避免老板只响一声没听见。
- “提醒设置”里有“测试来单提醒”，第一次装到手机上建议先测试一遍。

声音提醒优先尝试播放：

```text
static/sounds/new-order.wav
```

手机要收到后台消息，推荐这样设置：

1. 用 Safari 或 Chrome 打开老板后台，不要用微信内置浏览器。
2. 把后台添加到手机桌面。
3. 从手机桌面的“东科订单”图标打开。
4. 登录后点“提醒设置”。
5. 点“开启手机消息推送”，并允许通知权限。
6. 点“测试来单提醒”，确认手机通知栏能收到测试消息。

如果音频播放失败，会自动使用网页内置的 Web Audio beep 声作为备用提醒。手机浏览器通常要求用户先点击页面，所以页面声音只作为后台打开时的辅助提醒；真正的手机消息依赖“开启手机消息推送”。

提醒设置默认收起在老板后台顶部的“提醒设置”里，不长期占用订单页面。手机端如果想弹出系统通知，需要从 Safari/Chrome 打开后台、允许通知，最好再添加到主屏幕使用。注意：不同手机系统对网页推送和桌面角标支持不完全一致；如果手机系统不支持 Web Push、用户没有允许通知、或者免费服务器休眠，提醒可能会延迟或失败。Render 免费服务重新部署后，可能需要重新点一次“开启手机消息推送”。

更接近微信消息提醒的后续方案：

1. 网页提醒：改动小、成本低、马上能用；缺点是浏览器关闭后可能不能提醒。
2. PWA 推送通知：更像 App，手机桌面可打开；缺点是不同手机和浏览器支持不完全一致。
3. 微信小程序订阅消息：更接近微信提醒；缺点是需要小程序账号、HTTPS 域名、订阅消息模板、用户授权，正式上线可能需要认证和审核。
4. 企业微信机器人或群提醒：新订单可以推送到企业微信群；缺点是需要客户有企业微信或接受群提醒方案。

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
