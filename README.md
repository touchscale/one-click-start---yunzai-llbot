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

首次运行会自动创建 `config.yaml` 并引导配置。

#### 4. 访问Web界面

默认地址: [http://127.0.0.1:5000](http://127.0.0.1:5000)

### 配置文件说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `llbot.path` | String | - | llbot.exe完整路径 |
| `llbot.directory` | String | - | llbot工作目录 |
| `llbot.wait_seconds` | Integer | 5 | 检查间隔(秒) |
| `yunzai.git_bash_path` | String | - | Git Bash路径 |
| `yunzai.bash_directory` | String | - | Yunzai目录 |
| `yunzai.wait_seconds` | Integer | 5 | 检查间隔(秒) |
| `redis.path` | String | - | Redis服务路径 |
| `http_check.url` | String | - | HTTP检查地址 |
| `http_check.timeout` | Integer | 5 | 超时时间(秒) |
| `auto_restart.enabled` | Boolean | true | 是否启用自动重启 |
| `auto_restart.respect_manual_stop` | Boolean | true | 是否尊重手动停止 |
| `web_auth.username` | String | admin | Web登录用户名 |
| `web_auth.password` | String | admin123 | Web登录密码 |
| `onebot.enabled` | Boolean | false | 是否启用OneBot |
| `onebot.ws_url` | String | - | OneBot WebSocket地址 |
| `onebot.access_token` | String | - | 访问令牌 |
| `onebot.authorized_users` | Array | [] | 授权QQ号列表 |

### 开机自启动

使用 PowerShell 脚本创建任务计划程序：

```powershell
.\setup_task_scheduler.ps1
```

---

## 使用指南

### Web管理界面

| 功能 | 说明 |
|------|------|
| 状态查看 | 实时查看各服务运行状态 |
| 启动服务 | 手动启动指定服务 |
| 停止服务 | 手动停止指定服务 |
| 日志查看 | 查看各服务运行日志 |
| 手动检查 | 立即执行服务健康检查 |

### OneBot远程管理

启用后可通过QQ机器人管理：

| 指令 | 说明 |
|------|------|
| `/status` | 查看所有服务状态 |
| `/start <服务>` | 启动指定服务 |
| `/stop <服务>` | 停止指定服务 |
| `/restart <服务>` | 重启指定服务 |
| `/help` | 查看帮助信息 |

---

## 故障排查文档

### 常见问题

#### 1. 服务无法启动

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| llbot启动失败 | 路径错误 | 检查config.yaml中llbot.path是否正确 |
| Yunzai启动失败 | Git Bash路径错误 | 检查yunzai.git_bash_path配置 |
| Redis启动失败 | 端口被占用 | 检查Redis端口是否被其他程序占用 |
| 服务反复重启 | 配置错误或程序崩溃 | 查看logs/monitor.log日志文件 |

#### 2. Web界面无法访问

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 无法连接5000端口 | 端口被占用 | 检查5000端口是否被占用并关闭 |
| 登录失败 | 密码错误 | 检查web_auth.username和password配置 |
| 界面显示异常 | 浏览器缓存 | 清除浏览器缓存或使用无痕模式 |

#### 3. OneBot无法连接

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 连接超时 | WebSocket地址错误 | 检查onebot.ws_url配置 |
| 认证失败 | Token错误 | 检查onebot.access_token配置 |
| 无权限 | 未授权用户 | 将QQ号添加到authorized_users列表 |

#### 4. 图片服务问题

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 图片生成失败 | Node.js未安装 | 安装Node.js 14+版本 |
| 端口占用 | 3000端口被占用 | 修改image_generator配置端口 |
| 模板错误 | 模板文件缺失 | 检查templates目录完整性 |

### 日志位置

| 日志类型 | 位置 | 说明 |
|----------|------|------|
| 监控日志 | `logs/monitor.log` | 监控脚本运行日志（包含服务启动停止、错误信息等） |
| 图片服务日志 | `logs/image_service.log` | 图片生成服务专用日志（启动、停止、健康检查等） |
| 日志轮转 | `logs/*.log.YYYY-MM-DD` | 自动按天轮转，保留最近2天日志 |

### 诊断命令

```bash
# 检查Python环境
python --version

# 检查Node.js环境
node --version

# 检查端口占用
netstat -ano | findstr :5000

# 查看日志文件
type logs\monitor.log
```

### 性能优化

| 优化项 | 建议 |
|--------|------|
| 检查间隔 | 根据需求调整wait_seconds，默认5秒 |
| 日志清理 | 定期清理logs目录，避免磁盘占满 |
| 内存监控 | 定期重启监控脚本，避免内存泄漏 |

---

## 注意事项

- ⚠️ 路径使用双反斜杠 `\\` 或正斜杠 `/`
- 📁 日志保存在 `logs/` 目录
- 📄 PID文件保存在 `pids/` 目录
- 🔐 建议为OneBot设置访问令牌
- 🖼️ 图片服务启动失败时OneBot指令降级为文本格式
- 🔄 监控脚本停止时Web界面会显示提示
- 📋 修改配置后需要重启监控脚本生效