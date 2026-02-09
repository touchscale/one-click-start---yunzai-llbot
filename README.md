<div align="center">

<h1>llbot和Yunzai进程监控脚本</h1>

这是一个用于监控llbot和Yunzai进程的Python脚本，能够自动检测和重启这些服务。

</div>

---

## 功能特性

- ✅ 自动监控llbot和Yunzai服务状态
- ✅ 检测HTTP服务是否可访问
- ✅ 自动清理相关进程并重启服务
- ✅ 支持配置文件自定义监控参数
- ✅ 启动时自动获取管理员权限
- ✅ 内置保活机制，监控进程异常退出时自动重启
- ✅ Web管理界面，提供直观的管理方式
- ✅ 日志文件自动清理
- ✅ 支持通过Web手动停止后不自动重启
- ✅ 前端资源自动更新检查
- ✅ Windows自动登录配置
- ✅ Git仓库自动更新检测
- ✅ OneBot 11 协议支持，通过 QQ 机器人远程管理

---

## 安装

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 安装图片服务 Node.js 依赖

图片生成服务需要 Node.js 环境，首次运行前需要安装依赖：

```bash
cd image_generator
npm install
cd ..
```

### 3. 首次运行

首次运行脚本时，如果配置文件不存在，脚本会启动交互式配置：

```bash
python main.py
```

配置完成后，后续运行时会自动加载配置文件：

```bash
python main.py
```

---

## 使用方法

### 交互式配置

首次运行时会引导您设置以下参数：

- **llbot配置**：llbot.exe路径、目录、检查间隔
- **Yunzai配置**：Git Bash路径、Yunzai目录、检查间隔
- **Redis配置**：Redis服务器路径
- **HTTP检查配置**：检查地址、超时时间
- **自动重启配置**：是否启用、是否尊重手动停止
- **Web认证配置**：用户名、密码
- **Windows自动登录配置**：是否启用、用户名、密码
- **Git仓库更新检测配置**：是否启用、检测间隔、自动拉取、自动重启
- **OneBot 11 配置**：是否启用、WebSocket地址、访问令牌、授权用户列表

### Web管理界面

脚本启动后会自动运行Web管理界面，访问地址为：[http://127.0.0.1:5000](http://127.0.0.1:5000)

提供以下功能：
- 实时监控llbot、Yunzai和Redis进程状态
- 手动启动/停止各个服务
- 实时查看系统日志
- 执行手动HTTP检查
- 前端资源更新检查
- 需要通过Web认证后才能访问

### OneBot 远程管理（可选）

如果启用了 OneBot 功能，可以通过 QQ 机器人远程管理监控系统。

支持的指令：
- `/status` - 查看所有服务状态
- `/start <服务>` - 启动指定服务（llbot/yunzai/redis/all）
- `/stop <服务>` - 停止指定服务（llbot/yunzai/redis/all）
- `/restart <服务>` - 重启指定服务（llbot/yunzai/redis/all）
- `/check_update` - 检查更新（frontend/git/all）
- `/update <类型>` - 执行更新（frontend/git）
- `/help` - 显示帮助信息

### 配置文件

配置文件 `config.yaml` 包含以下配置项：

```yaml
# llbot配置
llbot:
  path: ""                    # llbot.exe路径
  directory: ""              # llbot目录
  wait_seconds: 5           # 检查间隔秒数

# Yunzai配置
yunzai:
  git_bash_path: ""         # Git Bash路径
  bash_directory: ""        # Yunzai目录
  wait_seconds: 5          # 检查间隔秒数

# Redis配置
redis:
  path: ""                  # Redis服务器路径

# HTTP检查设置
http_check:
  url: ""  # HTTP检查地址
  timeout: 5               # HTTP检查超时秒数

# 自动重启设置
auto_restart:
  enabled: true             # 是否启用自动重启功能
  respect_manual_stop: true # 是否尊重手动停止操作

# Web认证设置
web_auth:
  username: "admin"         # Web管理界面登录用户名
  password: "Admin123"      # Web管理界面登录密码

# Windows自动登录设置
auto_login:
  enabled: false            # 是否启用Windows自动登录
  username: ""              # 自动登录用户名
  password: ""              # 自动登录密码

# Git仓库更新检测设置
git_update:
  enabled: false            # 是否启用Git仓库自动更新检测
  check_interval: 900       # 检测间隔秒数（默认900秒，即15分钟）
  auto_pull: false          # 检测到更新后是否自动拉取
  auto_restart: false       # 拉取成功后是否自动重启监控脚本

# OneBot 11 协议配置
onebot:
  enabled: false                          # 是否启用 OneBot 功能
  ws_url: ws://localhost:8080             # OneBot WebSocket 反向连接地址
  access_token: ""                        # 访问令牌（可选，推荐设置）
  reconnect_interval: 5                   # 重连间隔（秒）
  authorized_users: []                    # 授权用户 QQ 号列表

# 图片生成服务设置
image_service:
  enabled: True               # 是否启用图片生成服务
  port: 3001                  # 服务端口
  url: http://localhost:3001 # 服务地址
```

### Windows 任务计划程序（可选）

为了实现开机自启动和异常保护，可以使用 `setup_task_scheduler.ps1` 脚本创建 Windows 任务计划程序。

```powershell
.\setup_task_scheduler.ps1
```

### 注意事项

- 始终使用 `main.py` 作为入口文件
- 配置文件中的路径请使用双反斜杠 `\\` 或正斜杠 `/`
- Web管理界面默认运行在端口5000
- 如需使用OneBot功能，请确保已安装websockets：`pip install websockets`
- 建议为OneBot连接设置访问令牌以确保安全性
- 图片生成服务会在程序启动时自动启动，无需手动操作
- 如果图片服务启动失败，OneBot指令会自动降级为文本格式
- 日志文件保存在 `logs/` 目录下，每天自动轮转
- PID文件保存在 `pids/` 目录下