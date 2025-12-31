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
```

### 4. 管理员权限

脚本启动时会自动请求管理员权限，以确保进程终止功能正常运行。

## 工作原理

1. 检查HTTP服务是否可访问
2. 检查llbot进程是否正在运行
3. 检查Redis和Yunzai进程是否正在运行
4. 如果服务不可访问或进程未运行，则清理相关进程并重启服务

## 注意事项

- 确保所有路径配置正确
- 脚本启动时会自动获取管理员权限
- 配置文件中的路径请使用双反斜杠 `\\` 或正斜杠 `/` 作为路径分隔符

## 故障排除

- 如果脚本无法正常终止进程，请确认管理员权限获取成功
- 如果HTTP检查失败，请检查服务是否正常运行
- 如果Redis无法启动，请确保Redis目录和路径配置正确