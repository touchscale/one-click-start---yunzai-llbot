# llbot和Yunzai进程监控脚本

这是一个用于监控llbot和Yunzai进程的Python脚本，能够自动检测和重启这些服务。

## 功能特性

- 自动监控llbot和Yunzai服务状态
- 检测HTTP服务是否可访问
- 自动清理相关进程并重启服务
- 支持配置文件自定义监控参数
- 启动时自动获取管理员权限，确保进程终止功能正常工作
- 内置保活机制，监控进程异常退出时自动重启
- 结构化日志记录，便于问题排查和监控
- 异步/多线程 + 事件驱动架构，提高监控效率
- Web管理界面，提供直观的管理方式
- 日志文件自动清理，每天0点自动删除旧日志
- 支持通过Web手动停止后不自动重启，通过配置控制自动重启行为

## 依赖库

运行脚本前需要安装以下Python依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 首次运行

首次运行脚本时，如果配置文件不存在，脚本会启动交互式配置：

```bash
python llbot_yunzai_monitor.py
```

交互式配置会引导您设置以下参数：

#### llbot配置
- llbot.exe路径：llbot可执行文件的完整路径
- llbot目录：llbot所在目录
- llbot检查间隔秒数：检查llbot状态的间隔时间（默认5秒）

#### Yunzai配置
- Git Bash路径：Git Bash可执行文件的路径
- Yunzai目录：Yunzai项目所在目录
- Yunzai检查间隔秒数：检查Yunzai状态的间隔时间（默认5秒）

#### Redis配置
- Redis服务器路径：Redis服务器可执行文件的路径

#### HTTP检查配置
- HTTP检查地址：用于检查服务状态的HTTP地址
- HTTP检查超时秒数：HTTP请求的超时时间（默认5秒）

#### 自动重启配置
- 启用自动重启：控制是否启用自动重启功能（默认true）
- 尊重手动停止：控制是否尊重手动停止操作，当为true时在Web手动停止的进程不会自动重启（默认true）

#### Web认证配置
- 用户名：Web管理界面的登录用户名（默认admin）
- 密码：Web管理界面的登录密码（默认admin123）

### 2. 后续运行

配置完成后，脚本会自动加载配置文件并开始监控。

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
  password: "admin123"      # Web管理界面登录密码
```

### 4. 管理员权限

脚本启动时会自动请求管理员权限，以确保进程终止功能正常运行。

### 5. Web管理界面

脚本启动后会自动运行Web管理界面，访问地址为：[http://127.0.0.1:5000](http://127.0.0.1:5000)

Web管理界面提供以下功能：
- 实时监控llbot、Yunzai和Redis进程状态
- 通过Web界面手动启动/停止各个服务
- 实时查看系统日志
- 执行手动HTTP检查
- 手动停止的服务不会自动重启，直到再次手动启动
- 需要通过Web认证后才能访问管理界面

### 6. 日志管理

- 系统会自动轮转日志文件，每天午夜创建新的日志文件
- 每天0点自动清理超过一天的旧日志文件
- 日志文件保存在 `logs/` 目录下

## 工作原理

1. 检查HTTP服务是否可访问
2. 检查llbot进程是否正在运行
3. 检查Redis和Yunzai进程是否正在运行
4. 如果服务不可访问或进程未运行，则清理相关进程并重启服务
5. 自动更新Web界面状态和日志
6. 定期清理旧日志文件

## 注意事项

- 确保所有路径配置正确
- 脚本启动时会自动获取管理员权限
- 配置文件中的路径请使用双反斜杠 `\\` 或正斜杠 `/` 作为路径分隔符
- Web管理界面默认运行在端口5000，如需修改可在代码中调整
- 如需使用Web管理界面，请确保已安装Flask：`pip install Flask`

## 故障排除

- 如果脚本无法正常终止进程，请确认管理员权限获取成功
- 如果HTTP检查失败，请检查服务是否正常运行
- 如果Redis无法启动，请确保Redis目录和路径配置正确
- 如果Web界面无法访问，请检查端口5000是否被占用