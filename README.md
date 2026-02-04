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
- ✅ 启动时自动获取管理员权限，确保进程终止功能正常工作
- ✅ 内置保活机制，监控进程异常退出时自动重启
- ✅ 结构化日志记录，便于问题排查和监控
- ✅ 异步/多线程 + 事件驱动架构，提高监控效率
- ✅ Web管理界面，提供直观的管理方式
- ✅ 日志文件自动清理，每天0点自动删除旧日志
- ✅ 支持通过Web手动停止后不自动重启，通过配置控制自动重启行为
- ✅ 前端资源自动更新检查，支持检查和强制更新Bootstrap等前端库
- ✅ Windows自动登录配置，支持启用或禁用系统自动登录功能
- ✅ Git仓库自动更新检测，定期检测监控脚本仓库是否有更新
- ✅ 支持自动拉取更新并重启监控脚本，或提示用户手动重启
- ✅ OneBot 11 协议支持，通过 QQ 机器人远程管理监控系统（支持 WebSocket 反向连接）

---

## 依赖库

运行脚本前需要安装以下Python依赖：

```bash
pip install -r requirements.txt
```

---

## 模块化架构

本项目采用模块化设计，将功能拆分为独立的模块，便于维护和扩展：

### 核心模块

<details>
<summary><b>📄 main.py - 主入口文件</b></summary>

- 程序启动和初始化
- 监控循环管理
- 多线程协调
- 保活机制实现

</details>

<details>
<summary><b>⚙️ config.py - 配置管理模块</b></summary>

- 配置文件加载和保存
- 交互式配置向导
- 配置验证和默认值处理
- 支持 YAML 格式配置文件

</details>

<details>
<summary><b>📌 constants.py - 常量定义模块</b></summary>

- 默认配置常量
- 事件类型枚举定义
- 全局常量管理

</details>

<details>
<summary><b>📝 logger.py - 日志处理模块</b></summary>

- 结构化日志记录（JSON格式）
- 日志文件自动轮转（按天）
- 控制台和文件双输出
- 自动清理旧日志文件
- 自定义日志格式化器

</details>

<details>
<summary><b>🔔 event_manager.py - 事件管理器模块</b></summary>

- 事件驱动架构实现
- 事件订阅和发布机制
- 异步事件处理
- 线程安全的事件队列

</details>

<details>
<summary><b>👁️ monitor.py - 监控模块</b></summary>

- llbot进程监控和HTTP检查
- Yunzai进程监控
- Redis进程监控
- QQ状态跟踪
- 自动重启逻辑

</details>

<details>
<summary><b>🔄 process_manager.py - 进程管理模块</b></summary>

- 进程启动、停止、重启
- 进程清理和终止
- 管理员权限管理
- 手动停止状态跟踪
- 精确的进程树管理

</details>

<details>
<summary><b>🔄 update_checker.py - 前端资源更新检查模块</b></summary>

- 自动检查Bootstrap等前端库的更新
- 支持SHA256哈希对比验证文件完整性
- 提供检查更新和强制更新两种模式
- 自动下载并更新本地前端资源文件

</details>

<details>
<summary><b>🔄 git_update_checker.py - Git仓库更新检测模块</b></summary>

- 定期检测当前监控脚本仓库是否有更新
- 支持自动拉取最新代码
- 支持自动重启监控脚本或提示用户手动重启
- 可配置检测间隔时间和自动重启行为

</details>

<details>
<summary><b>🔐 password_crypt.py - 密码加密存储模块</b></summary>

- 使用 Fernet 对称加密算法对密码进行加密存储
- 基于 PBKDF2 密钥派生函数，使用盐值增强安全性
- 支持自定义主密码或使用系统默认密钥
- 提供密码哈希和验证功能
- 自动检测密码是否已加密

</details>

<details>
<summary><b>🛡️ password_validator.py - 密码强度验证模块</b></summary>

- 提供密码强度验证和评分功能（0-100分）
- 支持五种强度级别：非常弱、弱、中等、强、非常强
- 检查密码长度、大小写字母、数字、特殊字符等要求
- 检测常见弱密码、连续重复字符、连续序列等安全问题
- 提供详细的密码强度信息和错误提示

</details>

<details>
<summary><b>🆔 pid_manager.py - 进程PID文件管理模块</b></summary>

- 精确跟踪和管理进程PID（llbot、yunzai、redis）
- PID文件持久化存储，包含进程启动时间
- 验证PID有效性，自动清理无效PID文件
- 提供进程信息查询功能
- 通过PID文件快速判断进程运行状态

</details>

<details>
<summary><b>🔑 auto_login.py - Windows自动登录配置模块</b></summary>

- 启用或禁用Windows系统自动登录功能
- 通过修改注册表配置自动登录参数
- 支持配置用户名和密码
- 提供自动登录状态查询功能
- 从配置字典应用自动登录设置
- 需要管理员权限才能执行

</details>

<details>
<summary><b>🌐 web_server.py - Web服务器模块</b></summary>

- Flask Web管理界面
- RESTful API端点
- 用户认证和会话管理
- 实时状态监控
- 配置管理界面
- 日志查看功能

</details>

<details>
<summary><b>🤖 onebot_client.py - OneBot 11 客户端模块</b></summary>

- WebSocket 反向连接支持
- 自动重连机制
- 指令消息接收和解析
- 支持私聊和群聊消息
- 用户权限验证
- 异步消息处理

</details>

<details>
<summary><b>📋 onebot_handlers.py - OneBot 指令处理器模块</b></summary>

- 状态查询指令处理
- 服务控制指令（启动/停止/重启）
- 更新管理指令
- 指令路由和参数解析
- 错误处理和友好提示

</details>

### 模块间关系

```
main.py (主入口)
  ├── config.py (配置加载)
  ├── logger.py (日志初始化)
  ├── event_manager.py (事件系统)
  ├── process_manager.py (进程管理)
  │   └── pid_manager.py (PID文件管理)
  ├── monitor.py (监控逻辑)
  ├── update_checker.py (前端资源更新)
  ├── git_update_checker.py (Git更新检测)
  ├── password_crypt.py (密码加密)
  ├── password_validator.py (密码验证)
  ├── auto_login.py (自动登录配置)
  ├── web_server.py (Web界面)
  ├── onebot_client.py (OneBot客户端)
  └── onebot_handlers.py (OneBot指令处理)
```

### 设计特点

1. **单一职责原则**：每个模块专注于特定功能
2. **事件驱动**：通过事件管理器实现模块间解耦
3. **线程安全**：使用锁和线程安全的数据结构
4. **可扩展性**：易于添加新功能模块
5. **配置驱动**：所有参数通过配置文件管理

---

## 使用方法

### 快速开始

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 首次运行

**重要**：本项目采用模块化架构，必须使用 `main.py` 作为入口文件。首次运行脚本时，如果配置文件不存在，脚本会启动交互式配置：

```bash
python main.py
```

### 交互式配置

交互式配置会引导您设置以下参数：

<details>
<summary><b>🤖 llbot配置</b></summary>

- llbot.exe路径：llbot可执行文件的完整路径
- llbot目录：llbot所在目录
- llbot检查间隔秒数：检查llbot状态的间隔时间（默认5秒）

</details>

<details>
<summary><b>☁️ Yunzai配置</b></summary>

- Git Bash路径：Git Bash可执行文件的路径
- Yunzai目录：Yunzai项目所在目录
- Yunzai检查间隔秒数：检查Yunzai状态的间隔时间（默认5秒）

</details>

<details>
<summary><b>💾 Redis配置</b></summary>

- Redis服务器路径：Redis服务器可执行文件的路径

</details>

<details>
<summary><b>🌐 HTTP检查配置</b></summary>

- HTTP检查地址：用于检查服务状态的HTTP地址
- HTTP检查超时秒数：HTTP请求的超时时间（默认5秒）

</details>

<details>
<summary><b>🔄 自动重启配置</b></summary>

- 启用自动重启：控制是否启用自动重启功能（默认true）
- 尊重手动停止：控制是否尊重手动停止操作，当为true时在Web手动停止的进程不会自动重启（默认true）

</details>

<details>
<summary><b>🔐 Web认证配置</b></summary>

- 用户名：Web管理界面的登录用户名（默认admin）
- 密码：Web管理界面的登录密码（默认admin123）

</details>

<details>
<summary><b>🔑 Windows自动登录配置</b></summary>

- 启用自动登录：是否启用Windows系统自动登录（默认false）
- 自动登录用户名：Windows自动登录的用户名
- 自动登录密码：Windows自动登录的密码（会在保存时自动加密）

</details>

<details>
<summary><b>🔄 Git仓库更新检测配置</b></summary>

- 启用Git仓库自动更新检测：是否启用定期检测仓库更新（默认false）
- 检测间隔秒数：检测仓库更新的间隔时间（默认900秒，即15分钟）
- 检测到更新后自动拉取：检测到更新后是否自动执行git pull（默认false）
- 拉取成功后自动重启：拉取成功后是否自动重启监控脚本（默认false）

</details>

<details>
<summary><b>🤖 OneBot 11 配置</b></summary>

- 启用OneBot功能：是否启用OneBot 11协议支持（默认false）
- WebSocket地址：OneBot实现端的WebSocket反向连接地址（例如：ws://localhost:8080）
- 访问令牌：连接OneBot所需的访问令牌（可选，但强烈推荐设置）
- 重连间隔：断线重连的间隔时间（默认5秒）
- 授权用户列表：允许使用OneBot指令的QQ号码列表（为空则允许所有用户）

</details>

### 2. 后续运行

配置完成后，后续运行时脚本会自动加载配置文件并开始监控：

```bash
python main.py
```

**注意**：
- 始终使用 `main.py` 作为入口文件，不要直接运行其他模块文件
- `main.py` 会自动初始化所有必要的模块（配置、日志、事件管理器、进程管理器、监控器、Web服务器）
- 程序支持保活机制，异常退出时会自动重启（最多5次/分钟）

### 3. 配置文件

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
  respect_manual_stop: true # 是否尊重手动停止操作，不自动重启在Web被手动停止的进程

# Web认证设置
web_auth:
  username: "admin"         # Web管理界面登录用户名
  password: "Admin123"      # Web管理界面登录密码（会在保存时自动加密）

# Windows自动登录设置
auto_login:
  enabled: false            # 是否启用Windows自动登录
  username: ""              # 自动登录用户名
  password: ""              # 自动登录密码（会在保存时自动加密）

# Git仓库更新检测设置
git_update:
  enabled: false            # 是否启用Git仓库自动更新检测
  check_interval: 900       # 检测间隔秒数（默认900秒，即15分钟）
  auto_pull: false          # 检测到更新后是否自动拉取
  auto_restart: false       # 拉取成功后是否自动重启监控脚本

# OneBot 11 协议配置（通过 QQ 机器人远程管理）
onebot:
  enabled: false                          # 是否启用 OneBot 功能
  ws_url: ws://localhost:8080             # OneBot WebSocket 反向连接地址
  access_token: ""                        # 访问令牌（可选，推荐设置）
  reconnect_interval: 5                   # 重连间隔（秒）
  authorized_users: []                    # 授权用户 QQ 号列表，为空则允许所有用户使用
```

### 4. OneBot 远程管理（可选）

如果启用了 OneBot 功能，可以通过 QQ 机器人远程管理监控系统。支持的指令包括：

<details>
<summary><b>📋 指令列表</b></summary>

- `/status` - 查看所有服务状态
- `/start <服务>` - 启动指定服务（llbot/yunzai/redis/all）
- `/stop <服务>` - 停止指定服务（llbot/yunzai/redis/all）
- `/restart <服务>` - 重启指定服务（llbot/yunzai/redis/all）
- `/check_update` - 检查更新（frontend/git/all）
- `/update <类型>` - 执行更新（frontend/git）
- `/help` - 显示帮助信息

</details>

**使用示例：**
```
/status                    # 查看状态
/start all                 # 启动所有服务
/restart llbot             # 重启 llbot
/check_update all          # 检查所有更新
/update git                # 拉取 Git 更新
```

### 5. 管理员权限

脚本启动时会自动请求管理员权限，以确保进程终止功能正常运行。

### 6. Web管理界面

脚本启动后会自动运行Web管理界面，访问地址为：[http://127.0.0.1:5000](http://127.0.0.1:5000)

Web管理界面提供以下功能：
- 实时监控llbot、Yunzai和Redis进程状态
- 通过Web界面手动启动/停止各个服务
- 实时查看系统日志
- 执行手动HTTP检查
- 手动停止的服务不会自动重启，直到再次手动启动
- 前端资源更新检查：检查并更新Bootstrap等前端库
- 需要通过Web认证后才能访问管理界面

### 7. 日志管理

- 系统会自动轮转日志文件，每天午夜创建新的日志文件
- 每天0点自动清理超过一天的旧日志文件
- 日志文件保存在 `logs/` 目录下

---

## 工作原理

### 主程序流程（main.py）

<details>
<summary><b>1. 初始化阶段</b></summary>

- 加载配置文件（config.py）
- 初始化日志系统（logger.py）
- 启动事件管理器（event_manager.py）
- 检查并获取管理员权限（process_manager.py）

</details>

<details>
<summary><b>2. 监控阶段</b></summary>

- 启动多线程监控循环：
  - llbot监控线程（monitor.py）
  - Yunzai监控线程（monitor.py）
  - 状态更新线程
  - Web服务器线程（web_server.py）
- 每个监控线程独立运行，互不干扰

</details>

<details>
<summary><b>3. 监控逻辑（monitor.py）</b></summary>

- llbot监控：定期检查HTTP服务可访问性和进程状态
- Yunzai监控：定期检查Git Bash和Redis进程状态
- QQ状态跟踪：检测QQ进程变化，自动清理相关进程

</details>

<details>
<summary><b>4. 进程管理（process_manager.py）</b></summary>

- 进程启动、停止、重启
- 进程清理和终止
- 手动停止状态跟踪

</details>

<details>
<summary><b>5. 事件处理（event_manager.py）</b></summary>

- 发布和订阅系统事件
- 异步事件处理
- 模块间解耦通信

</details>

<details>
<summary><b>6. Web管理（web_server.py）</b></summary>

- 提供RESTful API接口
- 实时状态监控
- 手动控制服务启停
- 日志查看功能
- 前端资源更新检查接口
- 用户认证和会话管理（使用密码加密和验证模块）

</details>

<details>
<summary><b>7. 密码加密（password_crypt.py）</b></summary>

- 使用 Fernet 对称加密算法加密存储密码
- 基于 PBKDF2 密钥派生函数，使用盐值增强安全性
- 支持自定义主密码或使用系统默认密钥
- 提供密码哈希和验证功能，用于Web认证

</details>

<details>
<summary><b>8. 密码验证（password_validator.py）</b></summary>

- 提供密码强度验证和评分功能
- 检查密码是否符合强密码策略
- 检测常见弱密码和安全隐患
- 为Web界面提供密码强度提示

</details>

<details>
<summary><b>9. PID文件管理（pid_manager.py）</b></summary>

- 精确跟踪和管理进程PID
- PID文件持久化存储，包含进程启动时间
- 验证PID有效性，自动清理无效PID文件
- 支持进程信息查询和状态检查

</details>

<details>
<summary><b>10. 自动登录配置（auto_login.py）</b></summary>

- 启用或禁用Windows系统自动登录功能
- 通过修改注册表配置自动登录参数
- 支持配置用户名和密码
- 提供自动登录状态查询功能
- 从配置字典应用自动登录设置
- 需要管理员权限才能执行

</details>

<details>
<summary><b>11. 前端资源更新（update_checker.py）</b></summary>

- 检查Bootstrap等前端库的更新
- 使用SHA256哈希验证文件完整性
- 支持检查更新和强制更新两种模式
- 自动下载并更新本地资源文件

</details>

<details>
<summary><b>12. Git仓库更新检测（git_update_checker.py）</b></summary>

- 定期检测当前脚本仓库是否有更新
- 支持自动拉取最新代码
- 支持自动重启监控脚本或提示用户手动重启
- 通过配置控制检测间隔和自动重启行为

</details>

<details>
<summary><b>13. 日志管理（logger.py）</b></summary>

- 结构化日志记录
- 按天自动轮转
- 自动清理旧日志

</details>

<details>
<summary><b>14. OneBot 客户端（onebot_client.py）</b></summary>

- WebSocket 反向连接到 OneBot 实现端
- 自动重连机制，确保连接稳定
- 接收和解析 QQ 消息指令
- 用户权限验证
- 异步消息处理和回复

</details>

<details>
<summary><b>15. OneBot 指令处理（onebot_handlers.py）</b></summary>

- 处理状态查询指令
- 处理服务控制指令（启动/停止/重启）
- 处理更新管理指令
- 指令路由和参数解析
- 错误处理和友好提示

</details>

---

## 注意事项

- **模块化使用**：始终使用 `main.py` 作为入口文件，不要直接运行其他模块文件
- 确保所有路径配置正确
- 脚本启动时会自动获取管理员权限
- 配置文件中的路径请使用双反斜杠 `\\` 或正斜杠 `/` 作为路径分隔符
- Web管理界面默认运行在端口5000，如需修改可在代码中调整
- 如需使用Web管理界面，请确保已安装Flask：`pip install Flask`
- 如需使用OneBot功能，请确保已安装websockets：`pip install websockets`
- OneBot功能使用WebSocket反向连接，需要配置正确的OneBot实现端地址
- 建议为OneBot连接设置访问令牌以确保安全性
- 可以通过配置`authorized_users`限制只有特定QQ用户可以使用OneBot指令
- 所有模块之间的通信通过事件管理器实现，确保线程安全
- 日志文件保存在 `logs/` 目录下，每天自动轮转
- PID文件保存在 `pids/` 目录下，用于精确跟踪进程状态
- 密码加密模块使用系统相关信息生成默认密钥，确保密码安全存储
- 密码验证模块强制要求密码长度8-64位，必须包含大小写字母和数字
- Windows自动登录功能需要管理员权限，启用时会修改系统注册表
- 启用自动登录后，系统会在重启时自动使用配置的用户名和密码登录
- Git更新检测功能会监控当前脚本仓库
- 启用auto_pull后，检测到更新会自动执行git pull
- 启用auto_restart后，拉取成功会自动重启监控脚本，否则会提示用户手动重启

---

## Windows 任务计划程序设置

为了实现监控程序的开机自启动和异常保护，可以使用 `setup_task_scheduler.ps1` 脚本创建 Windows 任务计划程序。

### 使用方法

<details>
<summary><b>1. 以管理员身份运行 PowerShell</b></summary>

右键点击 PowerShell，选择"以管理员身份运行"。

</details>

<details>
<summary><b>2. 执行设置脚本</b></summary>

```powershell
.\setup_task_scheduler.ps1
```

</details>

<details>
<summary><b>3. 确认任务创建</b></summary>

脚本会自动创建一个名为 `YunzaiLLBotMonitor` 的任务计划程序，具有以下特性：

- **触发器**：每分钟检查一次（首次运行有30秒延迟）
- **重试机制**：每10秒重试一次，无限次（实际重启次数由脚本内部控制）
- **运行账户**：当前用户账户（交互式登录）
- **权限级别**：最高权限
- **执行限制**：无限制运行时间
- **电池设置**：允许使用电池，电池时不停止

</details>

### 任务管理命令

创建任务后，可以使用以下命令管理任务：

```powershell
# 查看任务状态
Get-ScheduledTask -TaskName 'YunzaiLLBotMonitor'

# 手动启动任务
Start-ScheduledTask -TaskName 'YunzaiLLBotMonitor'

# 停止任务
Stop-ScheduledTask -TaskName 'YunzaiLLBotMonitor'

# 删除任务
Unregister-ScheduledTask -TaskName 'YunzaiLLBotMonitor' -Confirm:$false
```

### 图形化管理

也可以通过 Windows 任务计划程序管理界面进行管理：

1. 按 `Win + R`，输入 `taskschd.msc` 并回车
2. 在任务计划程序库中找到 `YunzaiLLBotMonitor` 任务
3. 可以查看任务历史、手动运行/停止、修改设置等

### 注意事项

- 脚本会检查任务是否已存在，如果存在会提示是否删除重建
- 任务计划程序会定期检查监控程序是否运行，如果检测到程序异常退出，会自动重启
- 监控程序内部的保活机制（最多5次/分钟）与任务计划程序的重启机制共同工作，提供双重保护
- 建议在首次运行前先手动测试 `python main.py`，确保配置正确

---

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| 脚本无法正常终止进程 | 请确认管理员权限获取成功 |
| HTTP检查失败 | 请检查服务是否正常运行 |
| Redis无法启动 | 请确保Redis目录和路径配置正确 |
| Web界面无法访问 | 请检查端口5000是否被占用 |
| 任务计划程序无法创建任务 | 请确保以管理员身份运行 PowerShell |
| 任务计划程序无法启动脚本 | 请检查 Python 路径是否在系统 PATH 中 |