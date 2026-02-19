<div align="center">

<h1>llbot和Yunzai进程监控脚本</h1>

自动监控和重启llbot、Yunzai、Redis服务的Python脚本

</div>

---

## 功能特性

- 自动监控和重启服务（llbot/Yunzai/Redis）
- HTTP服务可用性检测
- Web管理界面
- 日志自动清理
- 支持手动停止后不自动重启
- 监控脚本停止检测和自动恢复
- OneBot 11 协议支持（QQ机器人远程管理）
- Windows自动登录配置
- Git仓库自动更新检测

---

## 快速开始

### 1. 安装依赖

```bash
# Python依赖
pip install -r requirements.txt

# 图片服务依赖
cd image_generator
npm install
cd ..
```

### 2. 运行

```bash
python main.py
```

首次运行会引导配置，后续运行自动加载配置。

### 3. 访问Web界面

访问 [http://127.0.0.1:5000](http://127.0.0.1:5000) 进行管理。

---

## 配置说明

配置文件 `config.yaml` 主要配置项：

```yaml
# 服务配置
llbot:
  path: ""                # llbot.exe路径
  directory: ""          # llbot目录
  wait_seconds: 5        # 检查间隔

yunzai:
  git_bash_path: ""      # Git Bash路径
  bash_directory: ""     # Yunzai目录
  wait_seconds: 5        # 检查间隔

redis:
  path: ""               # Redis路径

# HTTP检查
http_check:
  url: ""                # 检查地址
  timeout: 5             # 超时秒数

# 自动重启
auto_restart:
  enabled: true          # 是否启用
  respect_manual_stop: true  # 是否尊重手动停止

# Web认证
web_auth:
  username: "admin"      # 用户名
  password: "admin123"   # 密码

# OneBot（可选）
onebot:
  enabled: false         # 是否启用
  ws_url: ws://localhost:8080
  access_token: ""       # 访问令牌
  authorized_users: []   # 授权用户QQ号
```

---

## 使用指南

### Web管理界面

- 查看服务状态
- 手动启动/停止服务
- 查看日志
- 执行手动检查

### OneBot远程管理

启用后可通过QQ机器人管理：

- `/status` - 查看状态
- `/start <服务>` - 启动服务
- `/stop <服务>` - 停止服务
- `/restart <服务>` - 重启服务
- `/help` - 帮助信息

### 监控脚本停止检测

当监控脚本停止时：
- Web界面显示停止提示
- 自动检测监控恢复
- 恢复后自动跳转到登录页面

---

## 开机自启动

使用 PowerShell 脚本创建任务计划程序：

```powershell
.\setup_task_scheduler.ps1
```

---

## 注意事项

- 路径使用双反斜杠 `\\` 或正斜杠 `/`
- 日志保存在 `logs/` 目录
- PID文件保存在 `pids/` 目录
- 建议为OneBot设置访问令牌
- 图片服务启动失败时OneBot指令降级为文本格式