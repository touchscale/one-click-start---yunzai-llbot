<div align="center">

<h1>llbot和Yunzai进程监控脚本</h1>

自动监控和重启llbot、Yunzai、Redis服务的Python脚本

</div>

---

## 功能特性

| 特性 | 说明 |
|------|------|
| 服务监控 | 自动监控和重启llbot/Yunzai/Redis服务 |
| HTTP检测 | 定期检查HTTP服务可用性 |
| Web管理 | 提供Web界面进行远程管理 |
| 日志清理 | 自动清理过期日志文件 |
| 手动控制 | 支持手动停止后不自动重启 |
| 停止检测 | 监控脚本停止检测和自动恢复 |
| OneBot支持 | 支持QQ机器人远程管理 |
| 自动登录 | Windows自动登录配置 |
| Git更新 | Git仓库自动更新检测 |
| 图片服务 | 内置图片生成服务(基于Node.js) |
| 密码加密 | 配置文件密码自动加密存储 |
| 单实例保护 | 防止多个监控进程同时运行 |

---

## 部署文档

### 环境要求

| 组件 | 最低版本 | 备注 |
|------|----------|------|
| Python | 3.8+ | 建议使用3.12 |
| Node.js | 14+ | 用于图片服务 |
| Redis | 5.0+ | 可选服务 |
| Git | 2.0+ | 用于Yunzai管理 |
| Windows | 10+ | 支持Windows系统 |

### Python依赖包

项目依赖以下Python包（详见requirements.txt）：

| 包名 | 用途 |
|------|------|
| Flask | Web管理界面框架 |
| psutil | 进程管理和系统监控 |
| PyYAML | 配置文件解析 |
| cryptography | 密码加密(Fernet算法) |
| requests | HTTP请求 |
| websocket-client | OneBot WebSocket连接 |
| schedule | 定时任务调度 |

### 安装步骤

#### 1. 克隆仓库

```bash
git clone https://gitee.com/touchscale_admin/one-click-start---yunzai-llbot.git
```

```bash
cd one-click-start---yunzai-llbot
```

#### 2. 安装Python依赖

```bash
pip install -r requirements.txt
```

如果国内下载较慢，可使用清华镜像源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 3. 安装图片服务依赖

```bash
cd image_generator
```

```bash
npm install
```

```bash
cd ..
```

#### 4. 首次运行配置

```bash
python main.py
```

首次运行会自动创建 `config.yaml` 并引导交互式配置。
程序会提示您输入各服务的路径、用户名、密码等信息。

> **注意**：首次运行需要以管理员权限启动，否则可能无法正常监控进程。

#### 5. 访问Web界面

默认地址: [http://127.0.0.1:5000](http://127.0.0.1:5000)

默认登录账号：
- 用户名：`admin`
- 密码：`Admin123`

### 开机自启动

使用 PowerShell 脚本创建任务计划程序：

```powershell
.\setup_task_scheduler.ps1
```

该脚本会创建一个计划任务，在系统启动时自动运行监控脚本。

---

## 配置文件说明

配置文件位于项目根目录的 `config.yaml`，采用YAML格式。

### 完整配置项列表

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| **llbot 配置** | | | |
| `llbot.path` | String | - | llbot.exe完整路径 |
| `llbot.directory` | String | - | llbot工作目录 |
| `llbot.wait_seconds` | Integer | 5/10 | 检查间隔(秒) |
| **Yunzai 配置** | | | |
| `yunzai.git_bash_path` | String | - | Git Bash路径 |
| `yunzai.bash_directory` | String | - | Yunzai目录 |
| `yunzai.wait_seconds` | Integer | 5 | 检查间隔(秒) |
| **Redis 配置** | | | |
| `redis.path` | String | - | Redis服务可执行文件路径 |
| **HTTP 检查配置** | | | |
| `http_check.url` | String | - | HTTP检查地址(如 http://localhost:3080) |
| `http_check.timeout` | Integer | 5/10 | 请求超时时间(秒) |
| **自动重启配置** | | | |
| `auto_restart.enabled` | Boolean | true | 是否启用自动重启功能 |
| `auto_restart.respect_manual_stop` | Boolean | true | 是否尊重手动停止(手动停止后不自动重启) |
| **自动登录配置** | | | |
| `auto_login.enabled` | Boolean | false | 是否启用Windows自动登录 |
| `auto_login.username` | String | - | 自动登录的Windows用户名 |
| `auto_login.password` | String | - | 自动登录的Windows密码(加密存储) |
| **Web 认证配置** | | | |
| `web_auth.username` | String | admin | Web管理界面登录用户名 |
| `web_auth.password` | String | Admin123 | Web管理界面登录密码(加密存储) |
| **Git 更新检测配置** | | | |
| `git_update.enabled` | Boolean | false | 是否启用Git仓库自动更新检测 |
| `git_update.check_interval` | Integer | 900 | 检测间隔(秒)，默认15分钟 |
| `git_update.auto_pull` | Boolean | false | 检测到更新后是否自动执行git pull |
| `git_update.auto_restart` | Boolean | false | 拉取成功后是否自动重启监控脚本 |
| **OneBot 配置** | | | |
| `onebot.enabled` | Boolean | false | 是否启用OneBot机器人远程管理 |
| `onebot.ws_url` | String | ws://localhost:8080 | OneBot反向WebSocket地址 |
| `onebot.access_token` | String | - | 访问令牌，用于验证OneBot连接 |
| `onebot.reconnect_interval` | Integer | 5 | 连接断开后重连间隔(秒) |
| `onebot.authorized_users` | Array | [] | 授权的QQ号列表(只有列表中的QQ号可发送指令) |

### 配置文件示例

```yaml
llbot:
  path: "D:\\llbot\\llbot.exe"
  directory: "D:\\llbot"
  wait_seconds: 10
yunzai:
  git_bash_path: "D:\\Program Files\\Git\\bin\\bash.exe"
  bash_directory: "D:\\yunzai"
  wait_seconds: 5
redis:
  path: "D:\\redis\\redis-server.exe"
http_check:
  url: "http://localhost:3080"
  timeout: 10
auto_restart:
  enabled: true
  respect_manual_stop: true
auto_login:
  enabled: false
  username: ""
  password: ""
web_auth:
  username: admin
  password: "gAAAAABh...(加密后的密码)"
git_update:
  enabled: false
  check_interval: 900
  auto_pull: false
  auto_restart: false
onebot:
  enabled: false
  ws_url: "ws://localhost:8080"
  access_token: ""
  reconnect_interval: 5
  authorized_users: []
```

### 配置文件修改方法

#### 方法一：通过Web界面修改（推荐）

1. 登录Web管理界面 [http://127.0.0.1:5000](http://127.0.0.1:5000)
2. 进入"配置"页面
3. 修改对应配置项
4. 点击"保存配置"
5. 重启监控脚本使配置生效

#### 方法二：直接编辑config.yaml

1. 使用文本编辑器打开 `config.yaml`
2. 修改对应配置项（注意密码字段为加密格式，建议通过Web界面修改密码）
3. 保存文件
4. 重启监控脚本

> **路径格式提示**：Windows路径请使用双反斜杠 `\\` 或正斜杠 `/`，例如：
> - 正确：`D:\\llbot\\llbot.exe` 或 `D:/llbot/llbot.exe`
> - 错误：`D:\llbot\llbot.exe`（反斜杠需转义）

---

## 使用指南

### 启动与停止

#### 启动监控

```bash
python main.py
```

#### 停止监控

- **方法一**：在运行窗口按 `Ctrl + C`
- **方法二**：通过Web管理界面点击"停止监控"
- **方法三**：通过OneBot发送 `/stop` 指令

### Web管理界面

#### 登录

1. 打开浏览器访问 [http://127.0.0.1:5000](http://127.0.0.1:5000)
2. 输入用户名和密码登录

#### 功能概览

| 功能模块 | 说明 |
|---------|------|
| 仪表盘/状态查看 | 实时查看各服务运行状态、PID、CPU/内存占用 |
| 启动服务 | 手动启动指定服务（llbot/Yunzai/Redis） |
| 停止服务 | 手动停止指定服务（设置手动停止标记，不会被自动重启） |
| 重启服务 | 停止并重新启动指定服务 |
| 日志查看 | 查看各服务运行日志，支持按关键字过滤 |
| 配置管理 | 修改配置文件并保存 |
| 手动检查 | 立即执行一次服务健康检查（跳过等待间隔） |

#### 仪表盘说明

仪表盘显示以下信息：
- **llbot状态**：运行中/已停止，显示进程PID
- **Yunzai状态**：运行中/已停止，显示进程PID
- **Redis状态**：运行中/已停止，显示进程PID
- **HTTP检测**：可达/不可达/未配置
- **自动重启**：启用/禁用
- **图片服务状态**：运行中/已停止
- **监控脚本状态**：运行中/已停止

### OneBot远程管理

启用OneBot后，可通过QQ机器人远程管理服务。

#### 启用步骤

1. 配置OneBot客户端（如 go-cqhttp、NapCat 等）的反向WebSocket
2. 在 `config.yaml` 中设置 `onebot.enabled: true`
3. 配置 `onebot.ws_url` 指向OneBot客户端的WebSocket地址
4. 配置 `onebot.authorized_users` 添加授权的QQ号
5. 重启监控脚本

#### 指令列表

| 指令 | 说明 |
|------|------|
| `/help` | 查看帮助信息和所有可用指令 |
| `/status` | 查看所有服务当前状态 |
| `/start llbot` | 启动llbot服务 |
| `/start yunzai` | 启动Yunzai服务 |
| `/start redis` | 启动Redis服务 |
| `/stop llbot` | 停止llbot服务 |
| `/stop yunzai` | 停止Yunzai服务 |
| `/stop redis` | 停止Redis服务 |
| `/restart llbot` | 重启llbot服务 |
| `/restart yunzai` | 重启Yunzai服务 |
| `/restart redis` | 重启Redis服务 |
| `/check` | 立即执行一次健康检查 |
| `/log` | 查看最近的日志记录 |

#### 指令使用示例

```
> /status

【服务状态】
llbot: 运行中 (PID: 12345)
Yunzai: 运行中 (PID: 12346)
Redis: 已停止
HTTP: 可达
自动重启: 启用
```

### 图片服务

图片服务用于OneBot指令返回的图片渲染，由Node.js驱动。

- 默认端口：`3001`
- 默认地址：`http://localhost:3001`
- 启动方式：监控脚本启动时自动拉起
- 日志文件：`logs/image_service.log`

如果图片服务启动失败，OneBot指令将降级为纯文本格式返回（不影响核心功能）。

---

## 故障排查文档

### 常见问题

#### 1. 服务无法启动

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| llbot启动失败 | 路径配置错误 | 检查config.yaml中llbot.path是否正确，路径应指向llbot.exe |
| llbot启动失败 | 缺少管理员权限 | 以管理员身份运行监控脚本 |
| llbot启动失败 | llbot本身异常 | 手动双击运行llbot.exe，查看是否能正常启动 |
| Yunzai启动失败 | Git Bash路径错误 | 检查yunzai.git_bash_path是否指向正确的bash.exe |
| Yunzai启动失败 | Yunzai目录错误 | 检查yunzai.bash_directory是否为Yunzai项目根目录 |
| Yunzai启动失败 | npm依赖未安装 | 在Yunzai目录下运行 `npm install` 安装依赖 |
| Redis启动失败 | 端口被占用 | 默认端口6379被占用，检查并关闭占用程序 |
| Redis启动失败 | 配置文件错误 | 检查redis.windows.conf或redis.conf配置 |
| 服务反复重启 | 配置错误或程序崩溃 | 查看logs/monitor.log日志文件定位具体错误 |
| 服务反复重启 | 端口冲突 | 检查各服务使用的端口是否冲突 |

#### 2. Web界面无法访问

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 浏览器显示"无法连接" | 监控脚本未运行 | 检查python main.py是否正常启动 |
| 浏览器显示"无法连接" | 5000端口被占用 | 运行 `netstat -ano | findstr :5000` 查看占用进程 |
| 登录失败 | 密码错误 | 检查web_auth.username和password配置 |
| 登录失败 | 密码未加密 | 通过Web界面或交互式配置重新设置密码 |
| 界面显示异常 | 浏览器缓存 | 清除浏览器缓存或使用无痕模式访问 |
| 界面显示异常 | 静态资源加载失败 | 检查webui/static目录是否完整 |
| 局域网其他设备无法访问 | 防火墙拦截 | 在Windows防火墙中放行Python程序或开放5000端口 |

#### 3. OneBot无法连接

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 日志显示"连接超时" | WebSocket地址错误 | 检查onebot.ws_url是否与OneBot客户端配置一致 |
| 日志显示"认证失败" | Token错误 | 检查onebot.access_token是否与OneBot客户端配置一致 |
| 发送指令无响应 | 未授权用户 | 将您的QQ号添加到authorized_users列表 |
| 连接频繁断开 | 网络不稳定 | 检查reconnect_interval设置，或检查本地网络 |
| 图片消息发送失败 | 图片服务异常 | 检查image_generator服务是否正常运行，查看image_service.log |

#### 4. 图片服务问题

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 图片生成失败 | Node.js未安装 | 安装Node.js 14+版本，执行 `node -v` 验证 |
| 图片生成失败 | npm依赖未安装 | 在image_generator目录下执行 `npm install` |
| 端口占用 | 3001端口被占用 | 修改image_generator配置端口或关闭占用程序 |
| 模板错误 | 模板文件缺失 | 检查image_generator/templates目录完整性 |
| 图片服务反复重启 | Node.js版本过低 | 升级到Node.js 16+版本 |

#### 5. 密码加密问题

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 配置文件密码字段为乱码 | 正常现象 | 密码使用Fernet算法加密存储，属于正常情况 |
| Web登录提示密码错误 | 密码加密密钥不匹配 | 删除config.yaml重新配置，或通过交互式配置重置 |
| 修改明文密码后无法登录 | 密码未加密 | 不要直接修改config.yaml中的password字段，通过Web界面修改 |

#### 6. Git更新检测问题

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 检测失败 | Git未安装或未配置环境变量 | 安装Git并确保可在命令行执行 `git --version` |
| 检测失败 | 项目未使用Git管理 | 确保项目目录是一个Git仓库（存在.git目录） |
| auto_pull失败 | 存在未提交的更改 | 手动处理本地修改或提交后再自动拉取 |
| auto_pull失败 | 网络问题 | 检查是否能正常访问Git远程仓库 |

#### 7. 权限问题

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 启动时提示"需要管理员权限" | 未以管理员身份运行 | 右键点击"以管理员身份运行"启动脚本 |
| 无法结束其他进程 | 权限不足 | 以管理员身份运行监控脚本 |
| 无法写入PID文件 | 目录权限不足 | 确保pids目录可写，或手动创建pids目录 |

#### 8. 日志文件问题

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 日志文件过大 | 未启用日志轮转 | 默认按天轮转，保留最近2天日志，可手动清理logs目录 |
| 日志乱码 | 编码问题 | 使用支持UTF-8编码的编辑器打开（如VS Code） |
| 无法生成日志 | logs目录不存在或无权限 | 手动创建logs目录，确保有写入权限 |

### 日志位置与说明

| 日志文件 | 位置 | 说明 |
|----------|------|------|
| 监控日志 | `logs/monitor.log` | 监控脚本运行日志（包含服务启动停止、错误信息等） |
| 图片服务日志 | `logs/image_service.log` | 图片生成服务专用日志（启动、停止、健康检查等） |
| 日志轮转 | `logs/*.log.YYYY-MM-DD` | 自动按天轮转，历史日志文件 |

### 诊断命令

```bash
# 检查Python环境和版本
python --version

# 检查Node.js环境和版本
node --version

# 检查Git是否安装
git --version

# 检查5000端口占用（Web界面端口）
netstat -ano | findstr :5000

# 检查6379端口占用（Redis默认端口）
netstat -ano | findstr :6379

# 检查3001端口占用（图片服务端口）
netstat -ano | findstr :3001

# 查看监控日志（Windows PowerShell）
Get-Content logs\monitor.log -Tail 50

# 查看监控日志（Git Bash / Linux）
tail -f logs/monitor.log

# 查看所有Python进程
tasklist | findstr python

# 结束指定PID的进程
taskkill /PID <进程PID> /F
```

### 健康检查清单

当遇到问题时，请按以下顺序检查：

- [ ] Python 3.8+ 已正确安装：`python --version`
- [ ] Node.js 14+ 已正确安装：`node --version`
- [ ] 所有Python依赖已安装：`pip list`
- [ ] 图片服务依赖已安装：检查 image_generator/node_modules 目录
- [ ] 以管理员身份运行脚本
- [ ] config.yaml 格式正确（可使用在线YAML校验工具验证）
- [ ] 各服务路径配置正确，路径使用双反斜杠或正斜杠
- [ ] 5000、6379、3001等端口未被占用
- [ ] logs 和 pids 目录存在且可写
- [ ] 检查 monitor.log 中的 ERROR 和 WARNING 级别日志

---

## 注意事项

### 安全提示

- 🔐 **密码安全**：配置文件中的密码使用Fernet算法加密存储，但仍建议妥善保管config.yaml文件，不要上传到公开代码仓库
- 🔐 **OneBot安全**：为OneBot设置access_token，并严格配置authorized_users列表，防止未授权用户控制服务
- 🔐 **Web界面密码**：首次登录后及时修改默认密码admin/Admin123
- 🔐 **局域网访问**：如果开放Web界面到局域网，建议设置防火墙规则仅允许可信IP访问

### 使用提示

- ⚠️ **路径格式**：路径使用双反斜杠 `\\` 或正斜杠 `/`，不要使用单反斜杠
- ⚠️ **管理员权限**：建议始终以管理员身份运行监控脚本，避免权限不足导致监控失效
- ⚠️ **配置修改生效**：修改配置后需要重启监控脚本才能生效
- 📁 **日志目录**：日志保存在 `logs/` 目录，定期检查日志可发现潜在问题
- 📄 **PID文件**：PID文件保存在 `pids/` 目录，用于单实例检测，不要手动删除
- 🖼️ **图片服务降级**：图片服务启动失败时，OneBot指令会自动降级为纯文本格式返回
- 🔄 **脚本重启**：监控脚本停止时，Web界面会显示提示信息，需手动重新启动
- 🪟 **自动登录限制**：自动登录仅支持Windows本地账户，微软账户（Microsoft Account）无法使用

### 维护建议

- 📅 **定期检查日志**：每周检查一次 monitor.log，关注错误和警告信息
- 🧹 **定期清理日志**：日志文件会自动轮转，可手动清理超过3天的历史日志
- 🔄 **定期更新依赖**：每月检查一次Python和npm依赖更新，修复安全漏洞
- 💾 **备份配置文件**：定期备份config.yaml，避免配置丢失
- 📊 **监控资源占用**：关注监控脚本本身的CPU和内存占用，如异常可重启脚本

### 已知限制

1. **系统平台**：目前主要针对Windows系统优化，Linux/Mac系统部分功能（如自动登录）不可用
2. **进程检测**：进程检测依赖进程名匹配，如果有同名其他进程可能造成误判
3. **Yunzai版本**：Yunzai启动方式基于Miao-Yunzai/TRSS-Yunzai等主流版本，自定义版本可能需要调整
4. **Web界面并发**：Web界面面向单机管理场景，不建议同时多个用户操作

---

## 项目目录结构

```
project-root/
├── main.py                  # 主入口文件，启动监控
├── config.py                # 配置管理模块（加载、保存、验证、加密）
├── constants.py             # 常量定义（默认配置、事件类型枚举）
├── monitor.py               # 进程监控核心逻辑（检测、启动、停止）
├── monitor_status.py        # 监控状态管理
├── process_manager.py       # 进程管理和权限管理
├── onebot_client.py         # OneBot客户端连接管理
├── onebot_handlers.py       # OneBot指令处理器
├── web_server.py            # Flask Web服务器
├── auto_login.py            # Windows自动登录配置模块
├── password_crypt.py        # 密码加密解密模块（Fernet）
├── password_validator.py    # 密码强度验证
├── git_update_checker.py    # Git仓库更新检测模块
├── update_checker.py        # 前端资源更新检查
├── image_service_manager.py # 图片服务管理
├── puppeteer_generator.py   # 图片生成（Puppeteer）
├── event_manager.py         # 事件发布订阅管理器
├── pid_manager.py           # PID文件管理
├── logger.py                # 日志模块封装
├── yunzai_restart_tracker.py # Yunzai重启追踪
├── config.yaml              # 配置文件（首次运行后生成）
├── requirements.txt         # Python依赖列表
├── setup_task_scheduler.ps1 # Windows计划任务脚本
├── image_generator/         # 图片生成服务（Node.js）
│   ├── index.js             # 服务入口
│   ├── package.json         # Node.js依赖
│   └── templates/           # 图片模板（HTML）
├── webui/                   # Web管理界面
│   ├── templates/           # HTML模板
│   │   ├── dashboard.html   # 仪表盘/状态页
│   │   ├── config.html      # 配置页
│   │   ├── login.html       # 登录页
│   │   └── monitor_stopped.html # 监控停止提示页
│   └── static/              # 静态资源
│       ├── css/             # 样式文件
│       └── js/              # 前端脚本
├── logs/                    # 日志目录（运行时自动创建）
└── pids/                    # PID文件目录（运行时自动创建）
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端核心 | Python 3.8+ |
| Web框架 | Flask |
| 配置管理 | PyYAML |
| 进程管理 | psutil |
| 密码加密 | cryptography (Fernet) |
| WebSocket | websocket-client |
| 定时任务 | schedule |
| 图片服务 | Node.js + Express |
| 前端框架 | Bootstrap 5 + 原生JavaScript |
| 事件系统 | 发布订阅模式 (EventManager) |

---

## License

本项目遵循相应的开源许可协议，请在使用时遵守相关条款。
