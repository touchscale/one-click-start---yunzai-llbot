# -*- coding: utf-8 -*-
import os
import sys
import time
import subprocess
import threading
import requests
import psutil
import yaml
import logging
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
import json
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob

# Web界面相关
try:
    from quart import Quart, render_template_string, jsonify, request, session, redirect
    from quart import Response
    from functools import wraps
    import secrets
    flask_available = True
except ImportError:
    # 尝试Flask作为备选
    try:
        from flask import Flask as Quart, render_template_string, jsonify, request, session, redirect
        from flask import Response
        from functools import wraps
        import secrets
        flask_available = True
    except ImportError:
        flask_available = False
        print("警告: Quart/Flask未安装，Web管理界面功能不可用。请运行 'pip install Quart' 安装。")

# 默认配置
DEFAULT_CONFIG = {
    "llbot": {
        "wait_seconds": 5
    },
    "yunzai": {
        "wait_seconds": 5
    },
    "http_check": {
        "timeout": 5
    },
    "auto_restart": {
        "enabled": True,
        "respect_manual_stop": True
    },
    "web_auth": {
        "username": "admin",
        "password": "admin123"
    }
}

# 事件类型枚举
class EventType:
    PROCESS_CHECK = "process_check"
    PROCESS_START = "process_start"
    PROCESS_STOP = "process_stop"
    HTTP_CHECK = "http_check"
    CONFIG_LOAD = "config_load"
    ERROR = "error"
    WARNING = "warning"

class EventManager:
    """事件管理器 - 用于异步事件驱动架构"""
    def __init__(self):
        self.handlers = {}
        self.event_queue = queue.Queue()
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    def subscribe(self, event_type, handler):
        """订阅事件"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    def publish(self, event_type, data=None):
        """发布事件"""
        self.event_queue.put((event_type, data))
    
    def process_events(self):
        """处理事件队列"""
        while self.running:
            try:
                event_type, data = self.event_queue.get(timeout=1)
                if event_type in self.handlers:
                    for handler in self.handlers[event_type]:
                        try:
                            handler(event_type, data)
                        except Exception as e:
                            logger.error(f"处理事件 {event_type} 时出错: {str(e)}", 
                                       extra={'event_type': 'event_error', 'error': str(e)})
            except queue.Empty:
                continue
    
    def start(self):
        """启动事件处理器"""
        self.running = True
        self.event_thread = threading.Thread(target=self.process_events, daemon=True)
        self.event_thread.start()
    
    def stop(self):
        """停止事件处理器"""
        self.running = False

# 全局手动停止状态跟踪 - 记录通过Web界面手动停止的进程
global_manual_stop_status = {
    'llbot': False,
    'yunzai': False,
    'redis': False
}

def update_global_manual_stop_status(process, value):
    """安全更新全局手动停止状态"""
    global global_manual_stop_status
    global_manual_stop_status[process] = value

def get_global_manual_stop_status(process):
    """安全获取全局手动停止状态"""
    global global_manual_stop_status
    return global_manual_stop_status.get(process, False)

# 全局事件管理器
event_manager = EventManager()

# Web服务器
if flask_available:
    # 创建Quart应用（异步Flask）
    app = Quart(__name__)
    # 设置会话密钥
    app.secret_key = secrets.token_hex(16)
    
    # Basic Auth认证函数（用于验证凭据）
    def check_auth(username, password):
        """检查用户名密码是否正确"""
        # 在配置中获取认证凭据，如果未配置则使用默认值
        auth_config = current_config.get('web_auth', {})
        correct_username = auth_config.get('username', 'admin')
        correct_password = auth_config.get('password', 'admin123')
        return username == correct_username and password == correct_password

    def authenticate():
        """发送认证请求"""
        return Response(
        '请提供用户名和密码进行认证。\n'
        '请使用 "Basic" 认证方案.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

    def requires_auth(f):
        """需要认证的装饰器 - 用于API端点"""
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'logged_in' not in session:
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated

    def requires_basic_auth(f):
        """Basic Auth认证装饰器 - 保留用于兼容性"""
        @wraps(f)
        def decorated(*args, **kwargs):
            auth = request.authorization
            if not auth or not check_auth(auth.username, auth.password):
                return authenticate()
            return f(*args, **kwargs)
        return decorated

    @app.errorhandler(Exception)
    async def handle_exception(e):
        """全局异常处理：记录完整 traceback，并对 API/页面给出友好提示"""
        import traceback as _tb
        tb = _tb.format_exc()
        # 将 traceback 直接包含到日志消息中，以便结构化文件记录中可见完整堆栈
        logger.error(f"Unhandled exception: {str(e)}\n{tb}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        # API 请求返回 JSON 错误
        try:
            if hasattr(request, 'path') and str(request.path).startswith('/api/'):
                return jsonify({'message': '内部错误，已记录。'}), 500
        except Exception:
            pass
        # 页面请求返回友好错误页面（防止二次异常）
        try:
            return (await render_template_string(get_login_template("内部错误，已记录。"))), 500
        except Exception:
            return "Internal Server Error", 500
    
    # 存储配置和状态的全局变量
    current_config = {}
    current_status = {
        'llbot': {'running': False, 'pid': None},
        'yunzai': {'running': False, 'pid': None},
        'redis': {'running': False, 'pid': None},
        'http_check': {'accessible': False}
    }

    # Web认证配置 - 从全局current_config获取，如果没有则返回默认值
    def get_web_auth_config():
        """获取Web认证配置，如果不存在则返回默认值"""
        auth_config = current_config.get('web_auth', {})
        return {
            'username': auth_config.get('username', 'admin'),
            'password': auth_config.get('password', 'admin123')
        }

    # 登录页面模板
    def get_login_template(error_msg=None):
        error_html = ''
        if error_msg:
            error_html = f'''
            <div class="alert alert-danger error-message" role="alert">
                <i class="fas fa-exclamation-circle"></i> {error_msg}
            </div>
            '''
        else:
            error_html = '<!-- No error messages -->'
        # 获取当前配置中的 web_auth 用户名以供提示
        try:
            username_hint = get_web_auth_config().get('username', 'admin')
        except Exception:
            username_hint = 'admin'

        return f'''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 - llbot Yunzai 监控系统</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        .login-container {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            overflow: hidden;
            width: 100%;
            max-width: 450px;
        }}
        .login-header {{
            background: linear-gradient(45deg, #007bff, #6610f2);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .login-header h2 {{
            margin: 0;
            font-weight: 600;
        }}
        .login-header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        .login-body {{
            padding: 40px;
        }}
        .form-control {{
            border-radius: 10px;
            padding: 12px 15px;
            border: 2px solid #e9ecef;
            margin-bottom: 20px;
            transition: all 0.3s;
        }}
        .form-control:focus {{
            border-color: #007bff;
            box-shadow: 0 0 0 0.2rem rgba(0,123,255,0.25);
        }}
        .btn-login {{
            background: linear-gradient(45deg, #007bff, #6610f2);
            border: none;
            border-radius: 10px;
            padding: 12px;
            font-weight: 600;
            font-size: 16px;
            width: 100%;
            transition: all 0.3s;
        }}
        .btn-login:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,123,255,0.4);
        }}
        .error-message {{
            background: #f8d7da;
            color: #721c24;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #f5c6cb;
        }}
        .input-group-text {{
            background: #f8f9fa;
            border-radius: 10px 0 0 10px;
            border-right: none;
        }}
        .form-control-with-icon {{
            border-radius: 0 10px 10px 0;
        }}
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h2><i class="fas fa-lock"></i> 系统登录</h2>
            <p>请输入您的凭据以访问监控系统</p>
        </div>
        <div class="login-body">
            {error_html}
            <form method="post" action="/login">
                <div class="mb-3">
                    <div class="input-group">
                        <span class="input-group-text"><i class="fas fa-user"></i></span>
                        <input type="text" class="form-control form-control-with-icon" name="username" placeholder="用户名" required value="admin">
                    </div>
                </div>
                <div class="mb-3">
                    <div class="input-group">
                        <span class="input-group-text"><i class="fas fa-key"></i></span>
                        <input type="password" class="form-control form-control-with-icon" name="password" placeholder="密码" required value="admin123">
                    </div>
                </div>
                <button type="submit" class="btn btn-primary btn-login">
                    <i class="fas fa-sign-in-alt"></i> 登录
                </button>
            </form>
            <div class="text-center mt-3 text-muted" style="font-size: 0.85em;">
                <p>当前登录用户名: {username_hint}</p>
                <p>若忘记密码，请编辑 <strong>config.yaml</strong> 中的 <code>web_auth.password</code> 并重启监控程序。</p>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 如果有错误消息，5秒后自动隐藏
        document.addEventListener('DOMContentLoaded', function() {{
            const errorDiv = document.querySelector('.error-message');
            if (errorDiv) {{
                setTimeout(function() {{
                    errorDiv.style.display = 'none';
                }}, 5000);
            }}
        }});
    </script>
</body>
</html>
        '''
    
    # 手动停止状态跟踪 - 记录通过Web界面手动停止的进程
    manual_stop_status = {
        'llbot': False,
        'yunzai': False,
        'redis': False
    }
    
    # 存储最近的日志 - 使用线程安全的列表
    import threading
    recent_logs = []
    recent_logs_lock = threading.Lock()
    
    def add_log_entry(log_entry):
        """向日志列表添加日志条目"""
        with recent_logs_lock:
            recent_logs.append(log_entry)
            # 限制日志数量为100条，移除最旧的日志
            if len(recent_logs) > 100:
                recent_logs.pop(0)
    
    class WebLogHandler(logging.Handler):
        """自定义日志处理器，用于将日志发送到Web界面"""
        def emit(self, record):
            # 使用record的内置方法来获取格式化时间
            import time
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created))
            
            log_entry = {
                'timestamp': timestamp,
                'level': record.levelname,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName
            }
            add_log_entry(log_entry)
    
    # 添加Web日志处理器
    web_log_handler = WebLogHandler()
    web_log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d - %(message)s'))
    logging.getLogger().addHandler(web_log_handler)
    
    @app.route('/')
    async def index():
        """主页"""
        if 'logged_in' not in session:
            return redirect('/login')
        try:
            html_template = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>llbot Yunzai 监控系统</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            padding-top: 20px;
            padding-bottom: 20px;
        }
        .main-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
        }
        .status-card {
            border-radius: 12px;
            border: none;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            height: 100%;
            background: linear-gradient(145deg, #ffffff, #f8f9fa);
        }
        .status-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }
        .status-running {
            background-color: #28a745 !important;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
            box-shadow: 0 0 10px rgba(40, 167, 69, 0.5);
        }
        .status-stopped {
            background-color: #dc3545 !important;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .status-unknown {
            background-color: #6c757d !important;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .btn-action {
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: 500;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .btn-action i {
            margin-right: 5px;
        }
        .btn-start {
            background: linear-gradient(45deg, #28a745, #20c997);
            border: none;
        }
        .btn-start:hover {
            background: linear-gradient(45deg, #218838, #1ea085);
            transform: translateY(-2px);
        }
        .btn-stop {
            background: linear-gradient(45deg, #dc3545, #fd7e14);
            border: none;
        }
        .btn-stop:hover {
            background: linear-gradient(45deg, #c82333, #e06b10);
            transform: translateY(-2px);
        }
        .btn-check {
            background: linear-gradient(45deg, #007bff, #6610f2);
            border: none;
        }
        .btn-check:hover {
            background: linear-gradient(45deg, #0056b3, #520dc2);
            transform: translateY(-2px);
        }
        .log-container {
            background: #1a1a1a;
            border-radius: 10px;
            padding: 15px;
            height: 400px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            box-shadow: inset 0 0 10px rgba(0,0,0,0.3);
        }
        .log-entry { 
            margin-bottom: 5px; 
            line-height: 1.4;
        }
        .log-info { color: #87ceeb; }
        .log-warning { color: #ffa500; }
        .log-error { color: #ff6b6b; }
        .log-debug { color: #98fb98; }
        .header-title {
            background: linear-gradient(45deg, #007bff, #6610f2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: bold;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card-header {
            border-bottom: 1px solid rgba(0,0,0,0.1);
            background: linear-gradient(to right, #f8f9fa, #e9ecef) !important;
            border-radius: 12px 12px 0 0 !important;
        }
        .card-body {
            padding: 1.5rem;
        }
        .process-icon {
            font-size: 24px;
            margin-right: 10px;
            vertical-align: middle;
        }
        .status-text {
            font-weight: 500;
        }
        .alert-box {
            border-radius: 10px;
            border: none;
        }
        .counter-badge {
            background: linear-gradient(45deg, #6c757d, #495057);
            border-radius: 20px;
            padding: 3px 10px;
            font-size: 0.8em;
        }
        .dropdown-menu {
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .password-modal .form-control {
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <!-- 顶部导航栏 -->
        <div class="d-flex justify-content-between align-items-center mb-4 px-3">
            <h1 class="header-title mb-0">
                <i class="fas fa-tachometer-alt"></i> llbot Yunzai 监控系统
            </h1>
            <div class="dropdown">
                <button class="btn btn-outline-primary dropdown-toggle" type="button" id="userMenu" data-bs-toggle="dropdown" aria-expanded="false">
                    <i class="fas fa-user-circle"></i> 账户
                </button>
                <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userMenu">
                    <li><a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#passwordModal"><i class="fas fa-key me-2"></i>修改密码</a></li>
                    <li><hr class="dropdown-divider"></li>
                    <li><a class="dropdown-item text-danger" href="/logout"><i class="fas fa-sign-out-alt me-2"></i>退出登录</a></li>
                </ul>
            </div>
        </div>

        <div class="main-container p-4">
            <!-- 状态卡片区域 -->
            <div class="row g-4 mb-4">
                <div class="col-lg-3 col-md-6">
                    <div class="card status-card">
                        <div class="card-header d-flex align-items-center">
                            <i class="fas fa-robot process-icon text-primary"></i>
                            <h5 class="card-title mb-0">llbot 状态</h5>
                        </div>
                        <div class="card-body">
                            <div class="d-flex align-items-center mb-3">
                                <span id="llbot-status-indicator" class="status-unknown"></span>
                                <span id="llbot-status" class="status-text">未知</span>
                            </div>
                            <div class="control-buttons d-grid gap-2">
                                <button class="btn btn-start btn-action" onclick="controlProcess('llbot', 'start')">
                                    <i class="fas fa-play"></i> 启动 llbot
                                </button>
                                <button class="btn btn-stop btn-action" onclick="controlProcess('llbot', 'stop')">
                                    <i class="fas fa-stop"></i> 停止 llbot
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-3 col-md-6">
                    <div class="card status-card">
                        <div class="card-header d-flex align-items-center">
                            <i class="fas fa-server process-icon text-success"></i>
                            <h5 class="card-title mb-0">Yunzai 状态</h5>
                        </div>
                        <div class="card-body">
                            <div class="d-flex align-items-center mb-3">
                                <span id="yunzai-status-indicator" class="status-unknown"></span>
                                <span id="yunzai-status" class="status-text">未知</span>
                            </div>
                            <div class="control-buttons d-grid gap-2">
                                <button class="btn btn-start btn-action" onclick="controlProcess('yunzai', 'start')">
                                    <i class="fas fa-play"></i> 启动 Yunzai
                                </button>
                                <button class="btn btn-stop btn-action" onclick="controlProcess('yunzai', 'stop')">
                                    <i class="fas fa-stop"></i> 停止 Yunzai
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-3 col-md-6">
                    <div class="card status-card">
                        <div class="card-header d-flex align-items-center">
                            <i class="fas fa-database process-icon text-info"></i>
                            <h5 class="card-title mb-0">Redis 状态</h5>
                        </div>
                        <div class="card-body">
                            <div class="d-flex align-items-center mb-3">
                                <span id="redis-status-indicator" class="status-unknown"></span>
                                <span id="redis-status" class="status-text">未知</span>
                            </div>
                            <div class="control-buttons d-grid gap-2">
                                <button class="btn btn-start btn-action" onclick="controlProcess('redis', 'start')">
                                    <i class="fas fa-play"></i> 启动 Redis
                                </button>
                                <button class="btn btn-stop btn-action" onclick="controlProcess('redis', 'stop')">
                                    <i class="fas fa-stop"></i> 停止 Redis
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-3 col-md-6">
                    <div class="card status-card">
                        <div class="card-header d-flex align-items-center">
                            <i class="fas fa-plug process-icon text-warning"></i>
                            <h5 class="card-title mb-0">HTTP 检查</h5>
                        </div>
                        <div class="card-body">
                            <div class="d-flex align-items-center mb-3">
                                <span id="http-status-indicator" class="status-unknown"></span>
                                <span id="http-status" class="status-text">未知</span>
                            </div>
                            <div class="control-buttons d-grid gap-2">
                                <button class="btn btn-check btn-action" onclick="manualHttpCheck()">
                                    <i class="fas fa-sync-alt"></i> 手动检查
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 日志区域 -->
            <div class="card alert-box">
                <div class="card-header d-flex align-items-center">
                    <i class="fas fa-terminal me-2"></i>
                    <h5 class="card-title mb-0">实时日志</h5>
                    <span class="ms-auto counter-badge">
                        <i class="fas fa-list me-1"></i>
                        <span id="log-count">0</span> 条
                    </span>
                </div>
                <div class="card-body p-0">
                    <div id="logs" class="log-container"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- 密码修改模态框 -->
    <div class="modal fade" id="passwordModal" tabindex="-1" aria-labelledby="passwordModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="passwordModalLabel"><i class="fas fa-key me-2"></i>修改密码</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <form id="passwordForm">
                        <div class="mb-3">
                            <label for="currentPassword" class="form-label">当前密码</label>
                            <input type="password" class="form-control" id="currentPassword" required>
                        </div>
                        <div class="mb-3">
                            <label for="newUsername" class="form-label">新用户名 (可选)</label>
                            <input type="text" class="form-control" id="newUsername" placeholder="保持当前用户名请留空">
                        </div>
                        <div class="mb-3">
                            <label for="newPassword" class="form-label">新密码</label>
                            <input type="password" class="form-control" id="newPassword" required>
                        </div>
                        <div class="mb-3">
                            <label for="confirmPassword" class="form-label">确认新密码</label>
                            <input type="password" class="form-control" id="confirmPassword" required>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="button" class="btn btn-primary" onclick="changePassword()">保存更改</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 检查认证状态的辅助函数
        function handleAuthError() {
            // 如果认证失败，重定向到登录页面
            window.location.href = '/login';
        }
        
        // 自动更新状态
        function updateStatus() {
            fetch('/api/status')
                .then(response => {
                    if (response.status === 401) {
                        handleAuthError();
                        return;
                    }
                    return response.json();
                })
                .then(data => {
                    if (data && typeof data === 'object') {
                        updateProcessStatus('llbot', data.llbot);
                        updateProcessStatus('yunzai', data.yunzai);
                        updateProcessStatus('redis', data.redis);
                        
                        const httpStatus = document.getElementById('http-status');
                        const httpIndicator = document.getElementById('http-status-indicator');
                        
                        if (data.http_check.accessible) {
                            httpStatus.textContent = '可访问';
                            httpIndicator.className = 'status-running';
                        } else {
                            httpStatus.textContent = '不可访问';
                            httpIndicator.className = 'status-stopped';
                        }
                    }
                })
                .catch(error => {
                    console.error('获取状态失败:', error);
                    // 检查是否是认证错误
                    if (error.message && error.message.includes('401')) {
                        handleAuthError();
                    }
                });
        }
        
        function updateProcessStatus(process, status) {
            const statusElement = document.getElementById(process + '-status');
            const indicatorElement = document.getElementById(process + '-status-indicator');
            
            if (status && status.running) {
                statusElement.textContent = '运行中 (PID: ' + status.pid + ')';
                indicatorElement.className = 'status-running';
            } else {
                statusElement.textContent = '已停止';
                indicatorElement.className = 'status-stopped';
            }
        }
        
        // 更新日志
        function updateLogs() {
            fetch('/api/logs')
                .then(response => {
                    if (response.status === 401) {
                        handleAuthError();
                        return;
                    }
                    return response.json();
                })
                .then(data => {
                    if (data && data.logs) {
                        const logsDiv = document.getElementById('logs');
                        logsDiv.innerHTML = '';
                        
                        // 更新日志计数
                        document.getElementById('log-count').textContent = data.logs.length;
                        
                        data.logs.forEach(log => {
                            const logElement = document.createElement('div');
                            logElement.className = 'log-entry log-' + log.level.toLowerCase();
                            logElement.textContent = log.timestamp + ' [' + log.level + '] ' + log.module + ':' + log.function + ' - ' + log.message;
                            logsDiv.appendChild(logElement);
                        });
                        
                        // 滚动到最新日志
                        logsDiv.scrollTop = logsDiv.scrollHeight;
                    }
                })
                .catch(error => {
                    console.error('获取日志失败:', error);
                    // 检查是否是认证错误
                    if (error.message && error.message.includes('401')) {
                        handleAuthError();
                    }
                });
        }
        
        // 控制进程
        function controlProcess(process, action) {
            const actionText = action === 'start' ? '启动' : '停止';
            fetch('/api/control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    process: process,
                    action: action
                })
            })
            .then(response => {
                if (response.status === 401) {
                    handleAuthError();
                    return;
                }
                return response.json();
            })
            .then(data => {
                if (data) {
                    // 使用Bootstrap的alert显示消息
                    showAlert(data.message, 'success');
                    updateStatus();
                }
            })
            .catch(error => {
                console.error('控制进程失败:', error);
                // 检查是否是认证错误
                if (error.message && error.message.includes('401')) {
                    handleAuthError();
                } else {
                    showAlert('操作失败: ' + error, 'danger');
                }
            });
        }
        
        // 手动HTTP检查
        function manualHttpCheck() {
            fetch('/api/manual-check', {
                method: 'POST',
            })
            .then(response => {
                if (response.status === 401) {
                    handleAuthError();
                    return;
                }
                return response.json();
            })
            .then(data => {
                if (data) {
                    showAlert(data.message, 'info');
                    updateStatus();
                }
            })
            .catch(error => {
                console.error('手动检查失败:', error);
                // 检查是否是认证错误
                if (error.message && error.message.includes('401')) {
                    handleAuthError();
                } else {
                    showAlert('检查失败: ' + error, 'danger');
                }
            });
        }
        
        // 显示警告消息
        function showAlert(message, type) {
            // 创建alert元素
            const alertDiv = document.createElement('div');
            alertDiv.className = 'alert alert-' + type + ' alert-dismissible fade show position-fixed';
            alertDiv.style.cssText = 'top: 20px; right: 20px; min-width: 300px; z-index: 9999;';
            alertDiv.innerHTML = `
                <strong>` + (type.charAt(0).toUpperCase() + type.slice(1)) + `:</strong> ` + message + `
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;
            
            document.body.appendChild(alertDiv);
            
            // 3秒后自动移除
            setTimeout(() => {
                if(alertDiv.parentNode) {
                    alertDiv.parentNode.removeChild(alertDiv);
                }
            }, 3000);
        }

        // 修改密码功能
        function changePassword() {
            const currentPassword = document.getElementById('currentPassword').value;
            const newUsername = document.getElementById('newUsername').value.trim() || null;
            const newPassword = document.getElementById('newPassword').value;
            const confirmPassword = document.getElementById('confirmPassword').value;

            if (newPassword !== confirmPassword) {
                showAlert('新密码与确认密码不匹配', 'danger');
                return;
            }

            if (newPassword.length < 6) {
                showAlert('新密码长度至少为6位', 'danger');
                return;
            }

            const payload = {
                old_password: currentPassword,
                new_password: newPassword
            };

            if (newUsername) {
                payload.new_username = newUsername;
            }

            fetch('/api/change-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            })
            .then(response => {
                if (response.ok) {
                    return response.json().then(data => {
                        showAlert(data.message, 'success');
                        // 清空表单
                        document.getElementById('passwordForm').reset();
                        // 关闭模态框
                        bootstrap.Modal.getInstance(document.getElementById('passwordModal')).hide();
                        // 提示用户重新登录
                        setTimeout(() => {
                            if (confirm('密码已更新，是否现在退出登录并使用新凭据重新登录？')) {
                                window.location.href = '/logout';
                            }
                        }, 2000);
                    });
                } else {
                    return response.json().then(data => {
                        showAlert(data.message, 'danger');
                    });
                }
            })
            .catch(error => {
                showAlert('修改密码失败: ' + error, 'danger');
            });
        }
        
        // 定期更新
        setInterval(updateStatus, 5000);  // 每5秒更新一次状态
        setInterval(updateLogs, 2000);    // 每2秒更新一次日志
        
        // 初始加载
        updateStatus();
        updateLogs();
    </script>
</body>
</html>
        '''
            return await render_template_string(html_template)
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            logger.error(f"index render error: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'traceback': tb
            })
            # 返回简短错误页面并确保日志已记录
            try:
                return (await render_template_string('<h1>渲染错误</h1><pre>{}</pre>'.format(str(e)))), 500
            except Exception:
                return "Internal Server Error", 500
    
    @app.route('/api/status')
    async def api_status():
        """获取当前状态"""
        if 'logged_in' not in session:
            return jsonify({'error': '未认证'}), 401
        return jsonify(current_status)
    
    @app.route('/api/logs')
    async def api_logs():
        """获取最近的日志"""
        if 'logged_in' not in session:
            return jsonify({'error': '未认证'}), 401
        with recent_logs_lock:
            # 创建日志副本以避免在序列化时被其他线程修改
            logs = recent_logs.copy()
        
        # 只返回最近的50条日志
        logs = logs[-50:] if len(logs) > 50 else logs
        return jsonify({'logs': logs})
    
    @app.route('/api/control', methods=['POST'])
    async def api_control():
        """控制进程"""
        if 'logged_in' not in session:
            return jsonify({'error': '未认证'}), 401
        try:
            data = await request.get_json()
            if not data:
                return jsonify({'message': '无效的JSON数据'}), 400
                
            process = data.get('process')
            action = data.get('action')
            
            if not process or not action:
                return jsonify({'message': '缺少必要的参数'}), 400
                
            if process not in ['llbot', 'yunzai', 'redis']:
                return jsonify({'message': '无效的进程名称'}), 400
                
            if action not in ['start', 'stop']:
                return jsonify({'message': '无效的操作'}), 400
            
            try:
                if process == 'llbot':
                    if action == 'start':
                        # 启动llbot
                        restart_llbot(current_config)
                        # 清除手动停止状态
                        manual_stop_status['llbot'] = False
                        try:
                            update_global_manual_stop_status('llbot', False)
                        except:
                            pass  # 如果全局变量不存在，跳过
                        logger.info(f"通过Web界面启动llbot", extra={
                            'event_type': EventType.PROCESS_START,
                            'target_process': 'llbot',
                            'source': 'web_interface',
                            'action': 'start'
                        })
                        return jsonify({'message': 'llbot启动命令已发送'})
                    elif action == 'stop':
                        # 停止llbot - 同时终止可能的进程名
                        llbot_process_name = os.path.basename(current_config['llbot']['path']) if current_config.get('llbot', {}).get('path') else 'llbot.exe'
                        terminate_process_by_name(llbot_process_name)
                        # 也终止可能的lucky-lillia-desktop.exe进程
                        terminate_process_by_name('lucky-lillia-desktop.exe')
                        # 终止pmhq-win-x64.exe进程（llbot依赖进程）
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止pmhq-win-x64.exe进程...")
                        terminate_process_by_name("pmhq-win-x64.exe")
                        # 终止flet.exe进程（llbot的GUI组件）
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止flet.exe进程...")
                        terminate_process_by_name("flet.exe")
                        # 终止QQ相关进程
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止QQ相关进程...")
                        qq_processes = ["QQ", "QQProtect", "QQPCRTP"]
                        for qq_process in qq_processes:
                            terminate_process_by_name(qq_process)
                        
                        # 设置手动停止状态
                        manual_stop_status['llbot'] = True
                        try:
                            update_global_manual_stop_status('llbot', True)
                        except:
                            pass  # 如果全局变量不存在，跳过
                        logger.info(f"通过Web界面停止llbot", extra={
                            'event_type': EventType.PROCESS_STOP,
                            'target_process': 'llbot',
                            'source': 'web_interface',
                            'action': 'stop'
                        })
                        return jsonify({'message': 'llbot停止命令已发送'})
                elif process == 'yunzai':
                    if action == 'start':
                        # 启动yunzai
                        check_and_manage_yunzai_async(current_config)
                        # 清除手动停止状态
                        manual_stop_status['yunzai'] = False
                        try:
                            update_global_manual_stop_status('yunzai', False)
                        except:
                            pass  # 如果全局变量不存在，跳过
                        logger.info(f"通过Web界面启动yunzai", extra={
                            'event_type': EventType.PROCESS_START,
                            'target_process': 'yunzai',
                            'source': 'web_interface',
                            'action': 'start'
                        })
                        return jsonify({'message': 'Yunzai启动命令已发送'})
                    elif action == 'stop':
                        # 停止yunzai - 终止所有相关进程
                        terminate_process_by_name('git-bash.exe')
                        # 也终止可能的node进程
                        terminate_process_by_name('node.exe')
                        # 设置手动停止状态
                        manual_stop_status['yunzai'] = True
                        try:
                            update_global_manual_stop_status('yunzai', True)
                        except:
                            pass  # 如果全局变量不存在，跳过
                        logger.info(f"通过Web界面停止yunzai", extra={
                            'event_type': EventType.PROCESS_STOP,
                            'target_process': 'yunzai',
                            'source': 'web_interface',
                            'action': 'stop'
                        })
                        return jsonify({'message': 'Yunzai停止命令已发送'})
                elif process == 'redis':
                    if action == 'start':
                        # 启动redis
                        check_and_manage_yunzai_async(current_config)  # 这会启动Redis
                        # 清除手动停止状态
                        manual_stop_status['redis'] = False
                        try:
                            update_global_manual_stop_status('redis', False)
                        except:
                            pass  # 如果全局变量不存在，跳过
                        logger.info(f"通过Web界面启动redis", extra={
                            'event_type': EventType.PROCESS_START,
                            'target_process': 'redis',
                            'source': 'web_interface',
                            'action': 'start'
                        })
                        return jsonify({'message': 'Redis启动命令已发送'})
                    elif action == 'stop':
                        # 停止redis
                        terminate_process_by_name(os.path.basename(current_config['redis']['path']) if current_config.get('redis', {}).get('path') else 'redis-server.exe')
                        # 设置手动停止状态
                        manual_stop_status['redis'] = True
                        try:
                            update_global_manual_stop_status('redis', True)
                        except:
                            pass  # 如果全局变量不存在，跳过
                        logger.info(f"通过Web界面停止redis", extra={
                            'event_type': EventType.PROCESS_STOP,
                            'target_process': 'redis',
                            'source': 'web_interface',
                            'action': 'stop'
                        })
                        return jsonify({'message': 'Redis停止命令已发送'})
            except Exception as inner_e:
                logger.error(f"执行{process} {action}操作时失败: {str(inner_e)}", extra={
                    'event_type': EventType.ERROR,
                    'target_process': process,
                    'action': action,
                    'error': str(inner_e)
                })
                return jsonify({'message': f'执行操作失败: {str(inner_e)}'}), 500
        except Exception as e:
            logger.error(f"Web界面控制进程失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return jsonify({'message': f'操作失败: {str(e)}'}), 500
    
    @app.route('/api/manual-check', methods=['POST'])
    async def api_manual_check():
        """手动HTTP检查"""
        if 'logged_in' not in session:
            return jsonify({'error': '未认证'}), 401
        try:
            if current_config.get('http_check', {}).get('url'):
                result = async_http_check(current_config['http_check']['url'], current_config['http_check'].get('timeout', 5))
                return jsonify({'message': f'HTTP检查完成，结果: {"成功" if result else "失败"}'})
            else:
                return jsonify({'message': 'HTTP检查URL未配置'})
        except Exception as e:
            logger.error(f"手动HTTP检查失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return jsonify({'message': f'HTTP检查失败: {str(e)}'}), 500

    @app.route('/logout')
    async def logout():
        """登出功能"""
        session.pop('logged_in', None)
        session.pop('username', None)
        logger.info("用户已登出", extra={'event_type': 'auth', 'action': 'logout'})
        return redirect('/login')

    @app.route('/login', methods=['GET', 'POST'])
    async def login():
        """自定义登录页面"""
        try:
            if request.method == 'POST':
                form = await request.form
                username = (form.get('username') or '').strip()
                password = form.get('password') or ''

                if not username or not password:
                    logger.warning("登录失败：缺少用户名或密码", extra={'event_type': 'auth', 'action': 'login_failed'})
                    return await render_template_string(get_login_template("请输入用户名和密码"))

                if check_auth(username, password):
                    session['logged_in'] = True
                    session['username'] = username
                    logger.info(f"用户登录成功: {username}", extra={
                        'event_type': 'auth',
                        'action': 'login',
                        'username': username
                    })
                    return redirect('/')
                else:
                    logger.warning(f"登录失败: {username}", extra={
                        'event_type': 'auth',
                        'action': 'login_failed',
                        'username': username
                    })
                    return await render_template_string(get_login_template("用户名或密码错误"))
            else:
                return await render_template_string(get_login_template())
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            logger.error(f"登录页面渲染或处理失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'traceback': tb
            })
            # 返回用户友好的错误页面
            return (await render_template_string(get_login_template("内部错误，已记录。"))), 500

    @app.route('/api/change-password', methods=['POST'])
    @requires_auth
    async def api_change_password():
        """更改密码API端点"""
        try:
            data = await request.get_json()
            if not data:
                return jsonify({'message': '无效的JSON数据'}), 400
            
            current_username = session.get('username', '')
            old_password = data.get('old_password')
            new_username = data.get('new_username', current_username)
            new_password = data.get('new_password')
            
            if not new_password:
                return jsonify({'message': '新密码不能为空'}), 400
            
            # 验证当前凭据
            if not check_auth(current_username, old_password):
                return jsonify({'message': '当前密码错误'}), 401
            
            # 更新当前配置中的认证信息
            if 'web_auth' not in current_config:
                current_config['web_auth'] = {}
            current_config['web_auth']['username'] = new_username
            current_config['web_auth']['password'] = new_password
            
            # 保存配置到文件
            try:
                save_config(current_config, "config.yaml")
                logger.info(f"密码已更新，新用户名: {new_username}", extra={
                    'event_type': 'config_update',
                    'action': 'password_change',
                    'target_user': new_username
                })
                return jsonify({'message': '密码更新成功，请使用新凭据重新登录'})
            except Exception as e:
                logger.error(f"保存配置失败: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'error': str(e),
                    'action': 'password_save_failure'
                })
                return jsonify({'message': f'保存配置失败: {str(e)}'}), 500
                
        except Exception as e:
            logger.error(f"更改密码失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'action': 'password_change_failure'
            })
            return jsonify({'message': f'更改密码失败: {str(e)}'}), 500

    def start_web_server(host='127.0.0.1', port=5000):
        """启动Web服务器"""
        import asyncio
        import sys
        import os
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Web管理界面启动在 http://{host}:{port}")
        logger.info(f"Web管理界面启动", extra={
            'event_type': 'web_server',
            'action': 'started',
            'address': f'http://{host}:{port}'
        })
        
        if hasattr(app, 'run_task'):
            import hypercorn.asyncio, asyncio
            from hypercorn.config import Config
            config = Config()
            config.bind = [f"{host}:{port}"]
            config.accesslog = config.errorlog = None
            
            if os.name == 'nt' and sys.version_info >= (3, 8):
                try:
                    from asyncio import WindowsProactorEventLoopPolicy, WindowsSelectorEventLoopPolicy
                    if isinstance(asyncio.get_event_loop_policy(), WindowsProactorEventLoopPolicy):
                        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
                except ImportError: pass
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.add_signal_handler = lambda *a: None
                shutdown_event = asyncio.Event()
                
                try:
                    loop.run_until_complete(
                        hypercorn.asyncio.serve(app, config, shutdown_trigger=lambda: shutdown_event.wait())
                    )
                finally:
                    loop.close()
            else:
                asyncio.run(hypercorn.asyncio.serve(app, config))
        else:
            app.run(host=host, port=port, debug=False, use_reloader=False)

def clean_old_log_files():
    """清理超过一天的旧日志文件"""
    try:
        # 获取logs目录中的所有日志文件
        log_files = glob.glob("logs/monitor.log.*")
        current_time = datetime.now()
        
        for log_file in log_files:
            # 获取文件的修改时间
            file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
            
            # 如果文件修改时间超过1天，则删除该文件
            if (current_time - file_time).days >= 1:
                os.remove(log_file)
                logger.info(f"删除旧日志文件: {log_file}", extra={
                    'event_type': 'log_cleanup',
                    'file_path': log_file,
                    'action': 'deleted',
                    'file_age_days': (current_time - file_time).days
                })
        
        # 同时也删除monitor.log主文件（如果存在）的备份，保留今天和昨天的
        main_log_files = glob.glob("logs/monitor.log.*")
        logger.info(f"清理旧日志完成，共处理了 {len(main_log_files)} 个日志文件", extra={
            'event_type': 'log_cleanup',
            'total_files_processed': len(main_log_files),
            'action': 'completed'
        })
    except Exception as e:
        logger.error(f"清理旧日志文件时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'error_type': 'log_cleanup_error',
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })

def schedule_log_cleanup():
    """调度日志清理任务 - 每天0点执行"""
    def run_daily_cleanup():
        while True:
            now = datetime.now()
            # 计算到明天0点的时间间隔
            next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            time_to_wait = (next_midnight - now).total_seconds()
            
            # 等待到0点
            time.sleep(time_to_wait)
            
            # 执行清理
            clean_old_log_files()
    
    # 启动清理线程
    cleanup_thread = threading.Thread(target=run_daily_cleanup, daemon=True)
    cleanup_thread.start()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 日志清理任务已调度")

def setup_structured_logging():
    """设置结构化日志记录"""
    # 创建logs目录（如果不存在）
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 配置日志格式
    class StructuredFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                'timestamp': self.formatTime(record),
                'level': record.levelname,
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'message': record.getMessage(),
                'process_type': getattr(record, 'process_type', None),
                'event_type': getattr(record, 'event_type', None),
            }
            
            # 移除空值
            log_entry = {k: v for k, v in log_entry.items() if v is not None}
            
            return json.dumps(log_entry, ensure_ascii=False)
    
    # 创建日志记录器
    logger = logging.getLogger('monitor')
    logger.setLevel(logging.INFO)
    
    # 避免重复添加处理器
    if logger.handlers:
        logger.handlers.clear()
    
    # 文件处理器 - 使用时间轮转日志，每天0点轮转，保留1天的日志
    file_handler = TimedRotatingFileHandler(
        'logs/monitor.log',
        when='midnight',  # 每天午夜轮转
        interval=1,       # 间隔1天
        backupCount=1,    # 只保留1个备份，即只保留前一天的日志
        encoding='utf-8',
        atTime=datetime.strptime("00:00", "%H:%M").time()  # 在00:00轮转
    )
    # 设置不创建.suffix后缀，直接覆盖旧日志文件
    file_handler.suffix = "%Y-%m-%d"  # 日期格式
    file_handler.extMatch = r"^\d{4}-\d{2}-\d{2}$"  # 匹配日期格式
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)
    
    # 控制台处理器 - 保持人类可读格式
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 启动日志清理调度
    schedule_log_cleanup()
    
    return logger

# 初始化日志记录器
logger = setup_structured_logging()

def interactive_config():
    """交互式配置函数，让用户输入配置项"""
    logger.info("开始交互式配置", extra={'event_type': 'config_start'})
    print("=" * 60)
    print("开始配置监控参数")
    print("=" * 60)
    
    # 初始化配置结构，使用默认值作为备用
    config = {
        'llbot': {
            'wait_seconds': DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
        },
        'yunzai': {
            'wait_seconds': DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
        },
        'http_check': {
            'timeout': DEFAULT_CONFIG['http_check'].get('timeout', 5)
        }
    }
    
    print("\n【llbot配置】")
    config['llbot']['path'] = input("llbot.exe路径 (例: D:\\\\path\\\\to\\\\llbot.exe): ").strip()
    config['llbot']['directory'] = input("llbot目录 (例: D:\\\\path\\\\to\\\\llbot): ").strip()
    
    wait_seconds_input = input(f"llbot检查间隔秒数 (默认: {config['llbot']['wait_seconds']}，留空使用默认值): ").strip()
    if wait_seconds_input:
        try:
            config['llbot']['wait_seconds'] = int(wait_seconds_input)
        except ValueError:
            print("无效输入，使用默认值")
            logger.warning(f"无效的llbot等待秒数输入: {wait_seconds_input}，使用默认值", 
                          extra={'event_type': 'config_warning'})
    
    print("\n【Yunzai配置】")
    config['yunzai']['git_bash_path'] = input("Git Bash路径 (例: D:\\\\path\\\\git-bash.exe): ").strip()
    config['yunzai']['bash_directory'] = input("Yunzai目录 (例: D:\\\\path\\\\to\\\\yunzai): ").strip()
    
    wait_seconds_input = input(f"Yunzai检查间隔秒数 (默认: {config['yunzai']['wait_seconds']}，留空使用默认值): ").strip()
    if wait_seconds_input:
        try:
            config['yunzai']['wait_seconds'] = int(wait_seconds_input)
        except ValueError:
            print("无效输入，使用默认值")
            logger.warning(f"无效的yunzai等待秒数输入: {wait_seconds_input}，使用默认值", 
                          extra={'event_type': 'config_warning'})
    
    print("\n【Redis配置】")
    config['redis'] = {}
    config['redis']['path'] = input("Redis服务器路径 (例: D:\\\\path\\\\to\\\\redis-server.exe): ").strip()
    
    print("\n【HTTP检查配置】")
    config['http_check']['url'] = input("HTTP检查地址 (例: http://localhost:3080): ").strip()
    
    timeout_input = input(f"HTTP检查超时秒数 (默认: {config['http_check']['timeout']}，留空使用默认值): ").strip()
    if timeout_input:
        try:
            config['http_check']['timeout'] = int(timeout_input)
        except ValueError:
            print("无效输入，使用默认值")
            logger.warning(f"无效的HTTP检查超时输入: {timeout_input}，使用默认值", 
                          extra={'event_type': 'config_warning'})
    
    print("\n【Web认证配置】")
    config['web_auth'] = {}
    username_input = input("Web管理界面用户名 (默认: admin，留空使用默认值): ").strip()
    config['web_auth']['username'] = username_input if username_input else "admin"
    password_input = input("Web管理界面密码 (默认: admin123，留空使用默认值): ").strip()
    config['web_auth']['password'] = password_input if password_input else "admin123"
    
    logger.info("交互式配置完成", extra={'event_type': 'config_complete'})
    print("\n配置完成！")
    return config

def save_config(config, config_path):
    """保存配置到文件"""
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)
    logger.info(f"配置已保存到 {config_path}", extra={'event_type': 'config_save', 'config_path': config_path})
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置已保存到 {config_path}")

def validate_config(config, config_path="config.yaml"):
    """验证配置文件的完整性，检查所有必需的配置项"""
    required_fields = {
        'llbot': {
            'path': str,
            'directory': str,
            'wait_seconds': int
        },
        'yunzai': {
            'git_bash_path': str,
            'bash_directory': str,
            'wait_seconds': int
        },
        'redis': {
            'path': str
        },
        'http_check': {
            'url': str,
            'timeout': int
        },
        'auto_restart': {
            'enabled': bool,
            'respect_manual_stop': bool
        },
        'web_auth': {
            'username': str,
            'password': str
        }
    }
    
    missing_fields = []
    invalid_types = []
    
    # 检查顶级配置项
    for section, fields in required_fields.items():
        if section not in config:
            config[section] = {}  # 创建空字典以避免KeyError
            for field, expected_type in fields.items():
                missing_fields.append(f"{section}.{field}")
                # 为新创建的section设置默认值
                if expected_type == str:
                    config[section][field] = ""
                elif expected_type == int:
                    if section == 'llbot' and field == 'wait_seconds':
                        config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                    elif section == 'yunzai' and field == 'wait_seconds':
                        config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                    elif section == 'http_check' and field == 'timeout':
                        config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                elif expected_type == bool:
                    if section == 'auto_restart' and field == 'enabled':
                        config[section][field] = DEFAULT_CONFIG['auto_restart'].get('enabled', True)
                    elif section == 'auto_restart' and field == 'respect_manual_stop':
                        config[section][field] = DEFAULT_CONFIG['auto_restart'].get('respect_manual_stop', True)
        else:
            # 检查该部分中的字段
            for field, expected_type in fields.items():
                if field not in config[section]:
                    missing_fields.append(f"{section}.{field}")
                    # 设置默认值
                    if expected_type == str:
                        config[section][field] = ""
                    elif expected_type == int:
                        if section == 'llbot' and field == 'wait_seconds':
                            config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                        elif section == 'yunzai' and field == 'wait_seconds':
                            config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                        elif section == 'http_check' and field == 'timeout':
                            config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                    elif expected_type == bool:
                        if section == 'auto_restart' and field == 'enabled':
                            config[section][field] = DEFAULT_CONFIG['auto_restart'].get('enabled', True)
                        elif section == 'auto_restart' and field == 'respect_manual_stop':
                            config[section][field] = DEFAULT_CONFIG['auto_restart'].get('respect_manual_stop', True)
                else:
                    # 验证字段类型
                    actual_value = config[section][field]
                    if actual_value is None:
                        # 如果值为None，设置默认值
                        if expected_type == str:
                            config[section][field] = ""
                        elif expected_type == int:
                            if section == 'llbot' and field == 'wait_seconds':
                                config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                            elif section == 'yunzai' and field == 'wait_seconds':
                                config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                            elif section == 'http_check' and field == 'timeout':
                                config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                        elif expected_type == bool:
                            if section == 'auto_restart' and field == 'enabled':
                                config[section][field] = DEFAULT_CONFIG['auto_restart'].get('enabled', True)
                            elif section == 'auto_restart' and field == 'respect_manual_stop':
                                config[section][field] = DEFAULT_CONFIG['auto_restart'].get('respect_manual_stop', True)
                    elif not isinstance(actual_value, expected_type) or (expected_type == int and isinstance(actual_value, bool)):
                        # 特别处理：布尔值不是整数，即使Python中bool是int的子类
                        invalid_types.append(f"{section}.{field} (期望 {expected_type.__name__}，实际 {type(actual_value).__name__})")
                        # 尝试转换类型或设置默认值
                        if expected_type == str:
                            config[section][field] = str(actual_value) if actual_value is not None else ""
                        elif expected_type == int:
                            try:
                                config[section][field] = int(actual_value) if actual_value is not None and not isinstance(actual_value, bool) else (
                                    DEFAULT_CONFIG[section].get(field, 5) if section in DEFAULT_CONFIG and field in DEFAULT_CONFIG[section] else 5
                                )
                                # 如果原始值是布尔值，使用默认值而不是转换
                                if isinstance(actual_value, bool):
                                    if section == 'llbot' and field == 'wait_seconds':
                                        config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                                    elif section == 'yunzai' and field == 'wait_seconds':
                                        config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                                    elif section == 'http_check' and field == 'timeout':
                                        config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                                    else:
                                        config[section][field] = 5  # 默认整数值
                            except (ValueError, TypeError):
                                # 如果转换失败，使用默认值
                                if section == 'llbot' and field == 'wait_seconds':
                                    config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                                elif section == 'yunzai' and field == 'wait_seconds':
                                    config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                                elif section == 'http_check' and field == 'timeout':
                                    config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                                else:
                                    config[section][field] = 5  # 默认整数值
                        elif expected_type == bool:
                            # 将各种值转换为布尔值
                            if isinstance(actual_value, str):
                                config[section][field] = actual_value.lower() in ['true', '1', 'yes', 'on']
                            else:
                                config[section][field] = bool(actual_value)
    
    # 记录验证结果
    if missing_fields:
        logger.warning(f"配置文件中缺少以下字段，已设置默认值: {', '.join(missing_fields)}", extra={
            'event_type': EventType.WARNING,
            'missing_fields': missing_fields,
            'config_path': config_path,
            'action': 'set_defaults'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 配置文件中缺少以下字段，已设置默认值: {', '.join(missing_fields)}")
    
    if invalid_types:
        logger.warning(f"配置文件中以下字段类型不正确，已尝试修复: {', '.join(invalid_types)}", extra={
            'event_type': EventType.WARNING,
            'invalid_types': invalid_types,
            'config_path': config_path,
            'action': 'fix_types'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 配置文件中以下字段类型不正确，已尝试修复: {', '.join(invalid_types)}")
    
    # 额外的业务逻辑验证
    validation_warnings = []
    
    # 检查HTTP URL格式
    http_url = config.get('http_check', {}).get('url', '')
    # 确保http_url是字符串
    if not isinstance(http_url, str):
        http_url = str(http_url) if http_url is not None else ""
    if http_url and not http_url.startswith(('http://', 'https://')):
        validation_warnings.append("HTTP检查URL应以http://或https://开头")
    
    # 检查路径是否存在（仅对非空路径检查）
    llbot_path = config.get('llbot', {}).get('path', '')
    # 确保llbot_path是字符串
    if not isinstance(llbot_path, str):
        llbot_path = str(llbot_path) if llbot_path is not None else ""
    if llbot_path and llbot_path != "" and not os.path.exists(llbot_path):
        validation_warnings.append(f"llbot路径不存在: {llbot_path}")
    
    yunzai_dir = config.get('yunzai', {}).get('bash_directory', '')
    # 确保yunzai_dir是字符串
    if not isinstance(yunzai_dir, str):
        yunzai_dir = str(yunzai_dir) if yunzai_dir is not None else ""
    if yunzai_dir and yunzai_dir != "" and not os.path.exists(yunzai_dir):
        validation_warnings.append(f"Yunzai目录不存在: {yunzai_dir}")
    
    redis_path = config.get('redis', {}).get('path', '')
    # 确保redis_path是字符串
    if not isinstance(redis_path, str):
        redis_path = str(redis_path) if redis_path is not None else ""
    if redis_path and redis_path != "" and not os.path.exists(os.path.dirname(redis_path)):
        validation_warnings.append(f"Redis路径不存在: {redis_path}")
    
    if validation_warnings:
        logger.warning(f"配置文件存在以下问题: {', '.join(validation_warnings)}", extra={
            'event_type': EventType.WARNING,
            'validation_warnings': validation_warnings,
            'config_path': config_path
        })
        for warning in validation_warnings:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: {warning}")
    
    return config


def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        logger.info("配置文件不存在，启动交互式配置", extra={'event_type': 'config_missing', 'config_path': config_path})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置文件不存在，正在启动交互式配置...")
        config = interactive_config()
        save_config(config, config_path)
        # 验证新创建的配置
        config = validate_config(config, config_path)
        return config
    else:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            
        # 验证并完善配置
        config = validate_config(config, config_path)
        
        logger.info(f"配置文件已加载: {config_path}", extra={'event_type': 'config_load', 'config_path': config_path})
        return config

def save_default_config(config_path):
    """保存默认配置到文件"""
    # 创建默认配置，只保留wait_seconds和timeout的默认值，其他留空
    full_default_config = {
        "llbot": {
            "path": "",
            "directory": "",
            "wait_seconds": 5
        },
        "yunzai": {
            "git_bash_path": "",
            "bash_directory": "",
            "wait_seconds": 5
        },
        "redis": {
            "path": ""
        },
        "http_check": {
            "url": "",
            "timeout": 5
        },
        "auto_restart": {
            "enabled": True,
            "respect_manual_stop": True
        },
        "web_auth": {
            "username": "admin",
            "password": "admin123"
        }
    }
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(full_default_config, file, default_flow_style=False, allow_unicode=True)

def is_admin():
    """检查当前是否以管理员权限运行"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """以管理员权限重新运行脚本"""
    if is_admin():
        logger.info("已以管理员权限运行", extra={'event_type': 'admin_check', 'status': 'already_admin'})
        return True
    
    logger.info("正在请求管理员权限", extra={'event_type': 'admin_request'})
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在请求管理员权限...")
    try:
        # 重新运行脚本并请求管理员权限
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([script] + sys.argv[1:])
        subprocess.run([
            "powershell", 
            "-Command", 
            f"Start-Process python -ArgumentList '{params}' -Verb RunAs"
        ])
        logger.info("管理员权限请求已发送", extra={'event_type': 'admin_request_sent'})
        return False  # 原始进程应该退出
    except Exception as e:
        logger.error(f"请求管理员权限时出错: {str(e)}", extra={'event_type': 'admin_error'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 请求管理员权限时出错: {str(e)}")
        return False

def check_admin():
    """检查是否以管理员权限运行"""
    if is_admin():
        logger.info("以管理员权限运行", extra={'event_type': 'admin_check', 'status': 'admin'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 以管理员权限运行 - 进程终止功能应正常工作")
        return True
    else:
        logger.warning("未以管理员权限运行", extra={'event_type': 'admin_check', 'status': 'not_admin'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 未以管理员权限运行")
        return False

def terminate_process_by_name(process_name):
    """通过名称终止进程"""
    try:
        start_time = time.time()
        terminated_pids = []
        searched_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'create_time', 'exe']):
            current_process_info = {
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'create_time': datetime.fromtimestamp(proc.info['create_time']).isoformat() if proc.info['create_time'] else 'unknown',
                'exe': proc.info['exe'] if proc.info['exe'] else 'unknown'
            }
            searched_processes.append(current_process_info)
            
            if proc.info['name'].lower() == process_name.lower():
                pid = proc.info['pid']
                logger.info(f"终止进程 {process_name} (PID: {pid})", extra={
                    'event_type': EventType.PROCESS_STOP, 
                    'process_name': process_name, 
                    'pid': pid,
                    'create_time': current_process_info['create_time'],
                    'exe': current_process_info['exe']
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在终止进程 {process_name} (PID: {pid})")
                proc.kill()
                terminated_pids.append(pid)
        
        end_time = time.time()
        search_duration = end_time - start_time
        
        if terminated_pids:
            logger.info(f"成功终止进程 {process_name}", extra={
                'event_type': EventType.PROCESS_STOP, 
                'process_name': process_name, 
                'pids': terminated_pids,
                'terminated_count': len(terminated_pids),
                'search_duration': f"{search_duration:.3f}s",
                'total_processes_searched': len(searched_processes)
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功终止进程 {process_name} (PIDs: {terminated_pids})")
        else:
            logger.info(f"未找到进程 {process_name}", extra={
                'event_type': EventType.PROCESS_CHECK, 
                'process_name': process_name,
                'search_duration': f"{search_duration:.3f}s",
                'total_processes_searched': len(searched_processes),
                'processes_found': [p['name'] for p in searched_processes[:10]]  # 只记录前10个找到的进程名
            })
    except psutil.AccessDenied as e:
        logger.error(f"访问被拒绝，无法终止进程 {process_name}: {str(e)}", extra={
            'event_type': EventType.ERROR, 
            'process_name': process_name, 
            'error': str(e), 
            'error_type': 'access_denied',
            'error_class': type(e).__name__,
            'suggestion': '请以管理员权限运行脚本'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问被拒绝，无法终止进程 {process_name}: {str(e)}")
    except psutil.NoSuchProcess as e:
        logger.warning(f"进程不存在，无法终止 {process_name}: {str(e)}", extra={
            'event_type': EventType.WARNING, 
            'process_name': process_name, 
            'error': str(e), 
            'error_type': 'no_such_process',
            'error_class': type(e).__name__
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 进程不存在，无法终止 {process_name}: {str(e)}")
    except Exception as e:
        logger.error(f"终止进程 {process_name} 时出错: {str(e)}", extra={
            'event_type': EventType.ERROR, 
            'process_name': process_name, 
            'error': str(e), 
            'error_type': 'terminate_error',
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 终止进程 {process_name} 时出错: {str(e)}")

def terminate_processes_by_powershell(names):
    """使用PowerShell终止多个相关进程"""
    for name in names:
        try:
            result = subprocess.run([
                "powershell", 
                "-Command", 
                f"Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Stop-Process -Force"
            ], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功终止 {name} 进程")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {name} 进程不存在或终止失败")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 终止 {name} 进程时出错: {str(e)}")

def async_http_check(url, timeout=5):
    """使用线程池异步HTTP检查函数"""
    def check():
        start_time = time.time()
        try:
            logger.debug(f"开始HTTP检查", extra={
                'event_type': 'debug',
                'url': url,
                'timeout': timeout,
                'start_time': datetime.fromtimestamp(start_time).isoformat()
            })
            
            response = requests.get(url, timeout=timeout)
            end_time = time.time()
            response_time = end_time - start_time
            
            result = response.status_code == 200
            logger.debug(f"HTTP检查完成", extra={
                'event_type': 'debug',
                'url': url,
                'status_code': response.status_code,
                'response_time': f"{response_time:.3f}s",
                'result': result,
                'end_time': datetime.fromtimestamp(end_time).isoformat()
            })
            
            return result
        except Exception as e:
            end_time = time.time()
            response_time = end_time - start_time
            
            logger.debug(f"HTTP检查异常", extra={
                'event_type': 'debug',
                'url': url,
                'response_time': f"{response_time:.3f}s",
                'error_type': type(e).__name__,
                'error': str(e),
                'end_time': datetime.fromtimestamp(end_time).isoformat()
            })
            raise  # 重新抛出异常，让调用者处理
    
    # 使用线程池运行HTTP请求，避免阻塞主线程
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(check)
        try:
            result = future.result(timeout=timeout+2)  # 设置额外超时
            return result
        except Exception as e:
            logger.warning(f"HTTP检查执行超时或出错", extra={
                'event_type': EventType.WARNING,
                'url': url,
                'error_type': type(e).__name__,
                'error': str(e),
                'timeout_setting': timeout+2
            })
            return False

# 异步HTTP检查函数，使用aiohttp
async def async_http_check_async(url, timeout=5):
    """异步HTTP检查函数，使用aiohttp库（如果可用）"""
    try:
        import aiohttp
    except ImportError:
        # 如果aiohttp不可用，使用原来的线程池方法
        return async_http_check(url, timeout)
    
    start_time = time.time()
    try:
        logger.debug(f"开始异步HTTP检查", extra={
            'event_type': 'debug',
            'url': url,
            'timeout': timeout,
            'start_time': datetime.fromtimestamp(start_time).isoformat()
        })
        
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.get(url) as response:
                end_time = time.time()
                response_time = end_time - start_time
                
                result = response.status == 200
                logger.debug(f"异步HTTP检查完成", extra={
                    'event_type': 'debug',
                    'url': url,
                    'status_code': response.status,
                    'response_time': f"{response_time:.3f}s",
                    'result': result,
                    'end_time': datetime.fromtimestamp(end_time).isoformat()
                })
                
                return result
    except Exception as e:
        end_time = time.time()
        response_time = end_time - start_time
        
        logger.debug(f"异步HTTP检查异常", extra={
            'event_type': 'debug',
            'url': url,
            'response_time': f"{response_time:.3f}s",
            'error_type': type(e).__name__,
            'error': str(e),
            'end_time': datetime.fromtimestamp(end_time).isoformat()
        })
        return False

def check_and_manage_llbot_async(config):
    """异步检查并管理llbot进程"""
    try:
        # 检查自动重启配置
        auto_restart_enabled = config.get('auto_restart', {}).get('enabled', True)
        respect_manual_stop = config.get('auto_restart', {}).get('respect_manual_stop', True)
        
        # 检查是否手动停止了llbot进程
        # 优先使用全局变量，如果不可用则使用局部变量
        is_manual_stop = False
        try:
            is_manual_stop = get_global_manual_stop_status('llbot')
        except:
            # 如果在Flask应用内部，尝试使用Flask应用的变量
            try:
                is_manual_stop = manual_stop_status.get('llbot', False)
            except:
                # 如果都不是，使用默认值
                is_manual_stop = False
        
        if respect_manual_stop and auto_restart_enabled and is_manual_stop:
            logger.debug("llbot被手动停止，跳过自动重启", extra={
                'event_type': 'debug',
                'target_process': 'llbot',
                'manual_stop': True,
                'auto_restart_enabled': auto_restart_enabled,
                'respect_manual_stop': respect_manual_stop
            })
            return  # 如果是手动停止且配置为尊重手动停止，则跳过自动重启
        
        # 检查必要配置项是否为空
        if not config['http_check']['url']:
            logger.warning("HTTP检查地址未配置", extra={'event_type': EventType.WARNING, 'check_type': 'http_url', 'details': '配置中缺少HTTP检查地址，无法进行连通性检查'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: HTTP检查地址未配置")
            event_manager.publish(EventType.WARNING, {
                'message': 'HTTP检查地址未配置',
                'config_item': 'http_url',
                'details': '配置中缺少HTTP检查地址，无法进行连通性检查'
            })
            return
        
        # 异步检查http://localhost:3080是否可访问
        try:
            start_time = time.time()
            is_accessible = async_http_check(config['http_check']['url'], config['http_check']['timeout'])
            end_time = time.time()
            response_time = end_time - start_time
            
            logger.info(f"HTTP检查完成", extra={
                'event_type': EventType.HTTP_CHECK, 
                'url': config['http_check']['url'], 
                'status': 'success' if is_accessible else 'failure',
                'response_time': f"{response_time:.3f}s",
                'timeout': config['http_check']['timeout']
            })
        except requests.exceptions.Timeout as e:
            logger.warning(f"HTTP检查超时: {config['http_check']['url']}", extra={
                'event_type': EventType.WARNING, 
                'url': config['http_check']['url'], 
                'error_type': 'timeout',
                'timeout_seconds': config['http_check']['timeout'],
                'error_details': str(e),
                'timestamp': time.time()
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP检查超时: {config['http_check']['url']}")
            event_manager.publish(EventType.WARNING, {
                'message': f'HTTP检查超时: {config['http_check']['url']}',
                'url': config['http_check']['url'],
                'error_type': 'timeout',
                'timeout_seconds': config['http_check']['timeout'],
                'error_details': str(e)
            })
            # 检查是否手动停止了llbot进程
            is_manual_stop = False
            try:
                is_manual_stop = get_global_manual_stop_status('llbot')
            except:
                try:
                    is_manual_stop = manual_stop_status.get('llbot', False)
                except:
                    is_manual_stop = False
            
            # 只有在未手动停止时才重启
            if not (respect_manual_stop and auto_restart_enabled and is_manual_stop):
                restart_llbot_with_cleanup(config)
            else:
                logger.debug("llbot被手动停止，跳过自动重启", extra={
                    'event_type': 'debug',
                    'target_process': 'llbot',
                    'manual_stop': True,
                    'auto_restart_enabled': auto_restart_enabled,
                    'respect_manual_stop': respect_manual_stop
                })
            return
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"HTTP连接错误: {config['http_check']['url']}", extra={
                'event_type': EventType.WARNING, 
                'url': config['http_check']['url'], 
                'error_type': 'connection_error',
                'error_details': str(e),
                'timestamp': time.time()
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP连接错误: {config['http_check']['url']}")
            event_manager.publish(EventType.WARNING, {
                'message': f'HTTP连接错误: {config['http_check']['url']}',
                'url': config['http_check']['url'],
                'error_type': 'connection_error',
                'error_details': str(e)
            })
            # 检查是否手动停止了llbot进程
            is_manual_stop = False
            try:
                is_manual_stop = get_global_manual_stop_status('llbot')
            except:
                try:
                    is_manual_stop = manual_stop_status.get('llbot', False)
                except:
                    is_manual_stop = False
            
            # 只有在未手动停止时才重启
            if not (respect_manual_stop and auto_restart_enabled and is_manual_stop):
                restart_llbot_with_cleanup(config)
            else:
                logger.debug("llbot被手动停止，跳过自动重启", extra={
                    'event_type': 'debug',
                    'target_process': 'llbot',
                    'manual_stop': True,
                    'auto_restart_enabled': auto_restart_enabled,
                    'respect_manual_stop': respect_manual_stop
                })
            return
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP请求异常: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'url': config['http_check']['url'], 
                'error_type': 'request_error', 
                'error': str(e),
                'error_class': type(e).__name__,
                'timestamp': time.time()
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP请求异常: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'HTTP请求异常: {str(e)}',
                'url': config['http_check']['url'],
                'error_type': 'request_error',
                'error': str(e),
                'error_class': type(e).__name__
            })
            # 检查是否手动停止了llbot进程
            is_manual_stop = False
            try:
                is_manual_stop = get_global_manual_stop_status('llbot')
            except:
                try:
                    is_manual_stop = manual_stop_status.get('llbot', False)
                except:
                    is_manual_stop = False
            
            # 只有在未手动停止时才重启
            if not (respect_manual_stop and auto_restart_enabled and is_manual_stop):
                restart_llbot_with_cleanup(config)
            else:
                logger.debug("llbot被手动停止，跳过自动重启", extra={
                    'event_type': 'debug',
                    'target_process': 'llbot',
                    'manual_stop': True,
                    'auto_restart_enabled': auto_restart_enabled,
                    'respect_manual_stop': respect_manual_stop
                })
            return
        except Exception as e:
            logger.error(f"HTTP检查未知错误: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'url': config['http_check']['url'], 
                'error_type': 'unknown_error', 
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc(),
                'timestamp': time.time()
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP检查未知错误: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'HTTP检查未知错误: {str(e)}',
                'url': config['http_check']['url'],
                'error_type': 'unknown_error',
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
            # 检查是否手动停止了llbot进程
            is_manual_stop = False
            try:
                is_manual_stop = get_global_manual_stop_status('llbot')
            except:
                try:
                    is_manual_stop = manual_stop_status.get('llbot', False)
                except:
                    is_manual_stop = False
            
            # 只有在未手动停止时才重启
            if not (respect_manual_stop and auto_restart_enabled and is_manual_stop):
                restart_llbot_with_cleanup(config)
            else:
                logger.debug("llbot被手动停止，跳过自动重启", extra={
                    'event_type': 'debug',
                    'target_process': 'llbot',
                    'manual_stop': True,
                    'auto_restart_enabled': auto_restart_enabled,
                    'respect_manual_stop': respect_manual_stop
                })
            return
        
        if is_accessible:
            logger.info(f"HTTP检查成功: {config['http_check']['url']}", extra={
                'event_type': EventType.HTTP_CHECK, 
                'url': config['http_check']['url'], 
                'status': 'success',
                'response_time': f"{response_time:.3f}s"
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {config['http_check']['url']} 可访问...")
            event_manager.publish(EventType.HTTP_CHECK, {
                'url': config['http_check']['url'],
                'status': 'success',
                'response_time': f"{response_time:.3f}s"
            })
            
            # 检查llbot.exe或lucky-lillia-desktop.exe是否仍在运行
            if not config['llbot']['path']:
                logger.warning("llbot路径未配置", extra={
                    'event_type': EventType.WARNING, 
                    'check_type': 'llbot_path',
                    'details': '配置中缺少llbot可执行文件路径，无法检查进程状态'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot路径未配置")
                return
                
            try:
                llbot_running = False
                llbot_process_name = os.path.basename(config['llbot']['path']).lower()
                # 同时检查原进程名和新进程名
                possible_names = [llbot_process_name, 'lucky-lillia-desktop.exe']
                
                # 记录正在搜索的进程名称
                logger.debug(f"搜索进程: {possible_names}", extra={
                    'event_type': 'debug', 
                    'process_names': possible_names,
                    'search_path': config['llbot']['path']
                })
                
                found_processes = []
                for proc in psutil.process_iter(['name', 'pid', 'create_time']):
                    if proc.info['name'].lower() in possible_names:
                        llbot_running = True
                        found_processes.append({
                            'name': proc.info['name'],
                            'pid': proc.info['pid'],
                            'create_time': datetime.fromtimestamp(proc.info['create_time']).isoformat()
                        })
                
                if llbot_running:
                    logger.info(f"llbot进程正在运行", extra={
                        'event_type': EventType.PROCESS_CHECK, 
                        'process_name': llbot_process_name, 
                        'status': 'running',
                        'found_processes': found_processes,
                        'count': len(found_processes)
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {(llbot_process_name or 'llbot')} 进程正在运行...")
                    event_manager.publish(EventType.PROCESS_CHECK, {
                        'process_name': llbot_process_name,
                        'status': 'running',
                        'found_processes': found_processes,
                        'count': len(found_processes)
                    })
                else:
                    # 检查是否手动停止了llbot进程
                    is_manual_stop = False
                    try:
                        is_manual_stop = get_global_manual_stop_status('llbot')
                    except:
                        try:
                            is_manual_stop = manual_stop_status.get('llbot', False)
                        except:
                            is_manual_stop = False
                    
                    if respect_manual_stop and auto_restart_enabled and is_manual_stop:
                        logger.debug("llbot被手动停止，跳过自动重启", extra={
                            'event_type': 'debug',
                            'target_process': 'llbot',
                            'manual_stop': True,
                            'auto_restart_enabled': auto_restart_enabled,
                            'respect_manual_stop': respect_manual_stop
                        })
                    else:
                        # llbot.exe未运行但网站应该可访问，清理相关进程后重新启动它
                        logger.warning("llbot进程未运行但网站可访问，正在重启", extra={
                            'event_type': EventType.WARNING, 
                            'process_name': llbot_process_name,
                            'details': '进程未运行但HTTP服务可访问，需要重启服务',
                            'config_path': config['llbot']['path'],
                            'config_directory': config['llbot']['directory']
                        })
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {(llbot_process_name or 'llbot')} 进程未运行但网站应该可访问，正在清理相关进程并重启...")
                        event_manager.publish(EventType.WARNING, {
                            'message': 'llbot进程未运行但网站可访问，正在重启',
                            'process_name': llbot_process_name,
                            'config_path': config['llbot']['path'],
                            'config_directory': config['llbot']['directory']
                        })
                        restart_llbot_with_cleanup(config)
            except psutil.AccessDenied as e:
                logger.error("访问进程信息被拒绝，可能需要管理员权限", extra={
                    'event_type': EventType.ERROR, 
                    'error_type': 'access_denied',
                    'error_details': str(e),
                    'process_name': llbot_process_name if 'llbot_process_name' in locals() else 'unknown',
                    'suggestion': '请以管理员权限运行脚本'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问进程信息被拒绝，可能需要管理员权限")
                event_manager.publish(EventType.ERROR, {
                    'message': '访问进程信息被拒绝',
                    'error_type': 'access_denied',
                    'error_details': str(e),
                    'process_name': llbot_process_name if 'llbot_process_name' in locals() else 'unknown',
                    'suggestion': '请以管理员权限运行脚本'
                })
            except psutil.NoSuchProcess as e:
                logger.warning("尝试访问不存在的进程", extra={
                    'event_type': EventType.WARNING, 
                    'error_type': 'no_such_process',
                    'error_details': str(e),
                    'process_name': llbot_process_name if 'llbot_process_name' in locals() else 'unknown'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试访问不存在的进程")
                event_manager.publish(EventType.WARNING, {
                    'message': '尝试访问不存在的进程',
                    'error_type': 'no_such_process',
                    'error_details': str(e),
                    'process_name': llbot_process_name if 'llbot_process_name' in locals() else 'unknown'
                })
            except Exception as e:
                logger.error(f"检查llbot进程时发生错误: {str(e)}", extra={
                    'event_type': EventType.ERROR, 
                    'error_type': 'process_check_error', 
                    'error': str(e),
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc(),
                    'process_name': llbot_process_name if 'llbot_process_name' in locals() else 'unknown'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查llbot进程时发生错误: {str(e)}")
                event_manager.publish(EventType.ERROR, {
                    'message': f'检查llbot进程时发生错误: {str(e)}',
                    'error_type': 'process_check_error',
                    'error': str(e),
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc()
                })
        else:
            logger.warning(f"HTTP检查失败: {config['http_check']['url']}", extra={
                'event_type': EventType.HTTP_CHECK, 
                'url': config['http_check']['url'], 
                'status': 'failure',
                'response_time': f"{response_time:.3f}s",
                'action_taken': 'restart_llbot_with_cleanup'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {config['http_check']['url']} 不可访问，正在终止相关进程并重启llbot...")
            event_manager.publish(EventType.HTTP_CHECK, {
                'url': config['http_check']['url'],
                'status': 'failure',
                'response_time': f"{response_time:.3f}s",
                'action_taken': 'restart_llbot_with_cleanup'
            })
            restart_llbot_with_cleanup(config)
    except KeyError as e:
        logger.error(f"配置错误: 缺少必需的配置项 {e}", extra={
            'event_type': EventType.ERROR, 
            'error_type': 'config_error', 
            'missing_key': str(e),
            'available_keys': list(config.keys()) if 'config' in locals() else [],
            'traceback': __import__('traceback').format_exc()
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'配置错误: 缺少必需的配置项 {e}',
            'missing_key': str(e),
            'error_type': 'config_error',
            'available_keys': list(config.keys()) if 'config' in locals() else [],
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise
    except Exception as e:
        logger.error(f"检查llbot时发生未知错误: {str(e)}", extra={
            'event_type': EventType.ERROR, 
            'error_type': 'unknown_error', 
            'error': str(e),
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc(),
            'config_keys': list(config.keys()) if 'config' in locals() else []
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'检查llbot时发生未知错误: {str(e)}',
            'target_process': 'llbot',
            'error_type': 'unknown_error',
            'error': str(e),
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查llbot时发生未知错误: {str(e)}")
        raise

def restart_llbot_with_cleanup(config):
    """清理相关进程后重启llbot"""
    # 终止pmhq-win-x64.exe进程
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止pmhq-win-x64.exe进程...")
    terminate_process_by_name("pmhq-win-x64.exe")
    
    # 终止flet.exe进程
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止flet.exe进程...")
    terminate_process_by_name("flet.exe")
    
    # 终止QQ相关进程
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止QQ相关进程...")
    qq_processes = ["QQ", "QQProtect", "QQPCRTP"]
    terminate_processes_by_powershell(qq_processes)
    
    # 使用taskkill额外清理
    for name in ["QQ.exe", "QQProtect.exe", "QQPCRTP.exe"]:
        try:
            subprocess.run(["taskkill", "/f", "/im", name, "/t"], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    
    # 额外等待确保进程完全终止
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 等待进程完全终止...")
    time.sleep(3)
    
    # 重新启动llbot
    restart_llbot(config)

def restart_llbot(config):
    """重启llbot"""
    try:
        if not config['llbot']['path']:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot路径未配置")
            return
            
        process_name = os.path.basename(config['llbot']['path'])
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动 {process_name}...")
        
        if os.path.exists(config['llbot']['path']):
            if not config['llbot']['directory']:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot目录未配置")
                return
                
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到 {process_name}，正在目录中启动: {config['llbot']['directory']}")
            os.chdir(config['llbot']['directory'])
            subprocess.Popen([config['llbot']['path']])
            # 清除手动停止状态
            try:
                update_global_manual_stop_status('llbot', False)
            except:
                pass  # 如果全局变量不存在，跳过
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 启动成功")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 未找到，请验证路径: {config['llbot']['path']}")
    except KeyError as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise

def check_and_manage_yunzai_async(config):
    """异步检查并管理Yunzai进程"""
    try:
        # 检查自动重启配置
        auto_restart_enabled = config.get('auto_restart', {}).get('enabled', True)
        respect_manual_stop = config.get('auto_restart', {}).get('respect_manual_stop', True)
        
        # 检查是否手动停止了yunzai或redis进程
        # 优先使用全局变量，如果不可用则使用局部变量
        yunzai_manual_stop = False
        redis_manual_stop = False
        try:
            yunzai_manual_stop = get_global_manual_stop_status('yunzai')
            redis_manual_stop = get_global_manual_stop_status('redis')
        except:
            # 如果在Flask应用内部，尝试使用Flask应用的变量
            try:
                yunzai_manual_stop = manual_stop_status.get('yunzai', False)
                redis_manual_stop = manual_stop_status.get('redis', False)
            except:
                # 如果都不是，使用默认值
                yunzai_manual_stop = False
                redis_manual_stop = False
        
        if respect_manual_stop and auto_restart_enabled:
            # 检查Redis是否被手动停止
            if redis_manual_stop:
                logger.debug("redis被手动停止，跳过自动重启", extra={
                    'event_type': 'debug',
                    'target_process': 'redis',
                    'manual_stop': True,
                    'auto_restart_enabled': auto_restart_enabled,
                    'respect_manual_stop': respect_manual_stop
                })
                # 标记Redis为已手动停止
                skip_redis_check = True
            else:
                skip_redis_check = False
                
            # 检查Yunzai是否被手动停止
            if yunzai_manual_stop:
                logger.debug("yunzai被手动停止，跳过自动重启", extra={
                    'event_type': 'debug',
                    'target_process': 'yunzai',
                    'manual_stop': True,
                    'auto_restart_enabled': auto_restart_enabled,
                    'respect_manual_stop': respect_manual_stop
                })
                # 标记Yunzai为已手动停止
                skip_yunzai_check = True
            else:
                skip_yunzai_check = False
            
            # 如果yunzai和redis都被手动停止，则跳过整个检查
            if skip_yunzai_check and skip_redis_check:
                return
        
        # 检查Redis是否运行
        if not config['redis']['path']:
            logger.warning("Redis路径未配置", extra={
                'event_type': EventType.WARNING, 
                'check_type': 'redis_path',
                'details': '配置中缺少Redis可执行文件路径，无法检查Redis进程状态'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Redis路径未配置")
            event_manager.publish(EventType.WARNING, {
                'message': 'Redis路径未配置',
                'config_item': 'redis_path',
                'details': '配置中缺少Redis可执行文件路径，无法检查Redis进程状态'
            })
            return
            
        try:
            redis_running = False
            redis_process_name = os.path.basename(config['redis']['path'])
            
            # 记录正在搜索的Redis进程
            logger.debug(f"搜索Redis进程: {redis_process_name}", extra={
                'event_type': 'debug', 
                'process_name': redis_process_name,
                'search_path': config['redis']['path']
            })
            
            found_redis_processes = []
            for proc in psutil.process_iter(['name', 'pid', 'create_time']):
                if proc.info['name'].lower() == redis_process_name.lower():
                    redis_running = True
                    found_redis_processes.append({
                        'name': proc.info['name'],
                        'pid': proc.info['pid'],
                        'create_time': datetime.fromtimestamp(proc.info['create_time']).isoformat()
                    })
        except psutil.AccessDenied as e:
            logger.error("访问Redis进程信息被拒绝", extra={
                'event_type': EventType.ERROR, 
                'process_name': redis_process_name, 
                'error_type': 'access_denied',
                'error_details': str(e),
                'suggestion': '请以管理员权限运行脚本'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问Redis进程信息被拒绝")
            event_manager.publish(EventType.ERROR, {
                'message': '访问Redis进程信息被拒绝',
                'process_name': redis_process_name,
                'error_type': 'access_denied',
                'error_details': str(e),
                'suggestion': '请以管理员权限运行脚本'
            })
            redis_running = False  # 假设Redis未运行
        except psutil.NoSuchProcess as e:
            logger.warning("Redis进程不存在", extra={
                'event_type': EventType.WARNING, 
                'process_name': redis_process_name, 
                'error_type': 'no_such_process',
                'error_details': str(e)
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Redis进程不存在")
            event_manager.publish(EventType.WARNING, {
                'message': 'Redis进程不存在',
                'process_name': redis_process_name,
                'error_type': 'no_such_process',
                'error_details': str(e)
            })
            redis_running = False
        except Exception as e:
            logger.error(f"检查Redis进程时出错: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'process_name': redis_process_name, 
                'error': str(e), 
                'error_type': 'process_check_error',
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Redis进程时出错: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'检查Redis进程时出错: {str(e)}',
                'process_name': redis_process_name,
                'error': str(e),
                'error_type': 'process_check_error',
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
            redis_running = False  # 假设Redis未运行
        
        if not redis_running and not skip_redis_check:  # 只有在Redis未被手动停止时才启动
            logger.info(f"Redis未运行，正在启动: {redis_process_name}", extra={
                'event_type': EventType.PROCESS_START, 
                'process_name': redis_process_name,
                'action': 'start_redis',
                'config_path': config['redis']['path'],
                'status_before': 'not_running'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 未运行，正在启动Redis服务器...")
            event_manager.publish(EventType.PROCESS_START, {
                'process_name': redis_process_name,
                'action': 'start_redis',
                'config_path': config['redis']['path'],
                'status_before': 'not_running'
            })
            try:
                redis_dir = os.path.dirname(config['redis']['path'])
                if not os.path.exists(redis_dir):
                    logger.error(f"Redis目录不存在: {redis_dir}", extra={
                        'event_type': EventType.ERROR, 
                        'redis_dir': redis_dir, 
                        'error_type': 'dir_not_found',
                        'config_path': config['redis']['path'],
                        'suggestion': '请检查Redis路径配置是否正确'
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Redis目录不存在: {redis_dir}")
                    event_manager.publish(EventType.ERROR, {
                        'message': f'Redis目录不存在: {redis_dir}',
                        'redis_dir': redis_dir,
                        'error_type': 'dir_not_found',
                        'config_path': config['redis']['path'],
                        'suggestion': '请检查Redis路径配置是否正确'
                    })
                    return
                    
                logger.debug(f"切换到Redis目录: {redis_dir}", extra={
                    'event_type': 'debug',
                    'directory': redis_dir,
                    'current_dir': os.getcwd()
                })
                os.chdir(redis_dir)
                
                # 记录启动Redis的命令
                start_command = [
                    "powershell", 
                    "-Command", 
                    f"Start-Process '{config['redis']['path']}' -WorkingDirectory '{redis_dir}' -Verb RunAs"
                ]
                logger.debug(f"Redis启动命令: {start_command}", extra={
                    'event_type': 'debug',
                    'command': start_command,
                    'working_directory': redis_dir
                })
                
                # 使用管理员权限启动Redis
                result = subprocess.Popen(start_command)
                logger.info(f"Redis启动命令已执行，PID: {result.pid}", extra={
                    'event_type': EventType.PROCESS_START,
                    'process_name': redis_process_name,
                    'pid': result.pid,
                    'start_time': datetime.now().isoformat()
                })
                
                time.sleep(3)  # 等待Redis启动
                # 清除手动停止状态
                try:
                    update_global_manual_stop_status('redis', False)
                except:
                    pass  # 如果全局变量不存在，跳过
                
                logger.info("Redis服务器启动成功", extra={
                    'event_type': EventType.PROCESS_START, 
                    'process_name': redis_process_name,
                    'status': 'success',
                    'wait_time': 3
                })
                event_manager.publish(EventType.PROCESS_START, {
                    'process_name': redis_process_name,
                    'status': 'success',
                    'pid': result.pid if 'result' in locals() else None
                })
            except FileNotFoundError as e:
                logger.error(f"Redis可执行文件未找到: {config['redis']['path']}", extra={
                    'event_type': EventType.ERROR, 
                    'process_name': redis_process_name, 
                    'error_type': 'file_not_found', 
                    'file_path': config['redis']['path'],
                    'error_details': str(e),
                    'suggestion': '请检查Redis路径配置是否正确'
                })
                event_manager.publish(EventType.ERROR, {
                    'message': f'Redis可执行文件未找到: {config['redis']['path']}',
                    'process_name': redis_process_name,
                    'error_type': 'file_not_found',
                    'file_path': config['redis']['path'],
                    'error_details': str(e),
                    'suggestion': '请检查Redis路径配置是否正确'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Redis可执行文件未找到: {config['redis']['path']}")
            except subprocess.SubprocessError as e:
                logger.error(f"启动Redis服务器时出错: {str(e)}", extra={
                    'event_type': EventType.ERROR, 
                    'process_name': redis_process_name, 
                    'error': str(e), 
                    'error_type': 'subprocess_error',
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc()
                })
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Redis服务器时出错: {str(e)}',
                    'process_name': redis_process_name,
                    'error': str(e),
                    'error_type': 'subprocess_error',
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc()
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Redis服务器时出错: {str(e)}")
            except Exception as e:
                logger.error(f"启动Redis服务器时发生未知错误: {str(e)}", extra={
                    'event_type': EventType.ERROR, 
                    'process_name': redis_process_name, 
                    'error': str(e), 
                    'error_type': 'unknown_error',
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc()
                })
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Redis服务器时发生未知错误: {str(e)}',
                    'process_name': redis_process_name,
                    'error': str(e),
                    'error_type': 'unknown_error',
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc()
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Redis服务器时发生未知错误: {str(e)}")
        else:
            logger.info("Redis已在运行", extra={
                'event_type': EventType.PROCESS_CHECK, 
                'process_name': redis_process_name, 
                'status': 'running',
                'found_processes': found_redis_processes,
                'count': len(found_redis_processes)
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 已在运行...")
            event_manager.publish(EventType.PROCESS_CHECK, {
                'process_name': redis_process_name,
                'status': 'running',
                'found_processes': found_redis_processes,
                'count': len(found_redis_processes)
            })
        
        # 检查Yunzai是否运行
        # 使用固定的process_name而不从配置中获取
        process_name = 'git-bash.exe'
        
        try:
            yunzai_running = False
            
            # 记录正在搜索的Yunzai进程
            logger.debug(f"搜索Yunzai进程: {process_name}", extra={
                'event_type': 'debug', 
                'process_name': process_name
            })
            
            found_yunzai_processes = []
            for proc in psutil.process_iter(['name', 'pid', 'create_time']):
                if proc.info['name'].lower() == process_name.lower():
                    yunzai_running = True
                    found_yunzai_processes.append({
                        'name': proc.info['name'],
                        'pid': proc.info['pid'],
                        'create_time': datetime.fromtimestamp(proc.info['create_time']).isoformat()
                    })
        except psutil.AccessDenied as e:
            logger.error("访问Yunzai进程信息被拒绝", extra={
                'event_type': EventType.ERROR, 
                'process_name': process_name, 
                'error_type': 'access_denied',
                'error_details': str(e),
                'suggestion': '请以管理员权限运行脚本'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问Yunzai进程信息被拒绝")
            event_manager.publish(EventType.ERROR, {
                'message': '访问Yunzai进程信息被拒绝',
                'process_name': process_name,
                'error_type': 'access_denied',
                'error_details': str(e),
                'suggestion': '请以管理员权限运行脚本'
            })
            yunzai_running = False  # 假设Yunzai未运行
        except psutil.NoSuchProcess as e:
            logger.warning("Yunzai进程不存在", extra={
                'event_type': EventType.WARNING, 
                'process_name': process_name, 
                'error_type': 'no_such_process',
                'error_details': str(e)
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程不存在")
            event_manager.publish(EventType.WARNING, {
                'message': 'Yunzai进程不存在',
                'process_name': process_name,
                'error_type': 'no_such_process',
                'error_details': str(e)
            })
            yunzai_running = False
        except Exception as e:
            logger.error(f"检查Yunzai进程时出错: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'process_name': process_name, 
                'error': str(e), 
                'error_type': 'process_check_error',
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Yunzai进程时出错: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'检查Yunzai进程时出错: {str(e)}',
                'process_name': process_name,
                'error': str(e),
                'error_type': 'process_check_error',
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
            yunzai_running = False  # 假设Yunzai未运行
        
        if not yunzai_running and not skip_yunzai_check:  # 只有在Yunzai未被手动停止时才启动
            logger.info("Yunzai未运行，正在启动", extra={
                'event_type': EventType.PROCESS_START, 
                'process_name': process_name,
                'action': 'start_yunzai',
                'config_git_bash': config['yunzai']['git_bash_path'],
                'config_bash_directory': config['yunzai']['bash_directory'],
                'status_before': 'not_running'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程...")
            event_manager.publish(EventType.PROCESS_START, {
                'process_name': process_name,
                'action': 'start_yunzai',
                'config_git_bash': config['yunzai']['git_bash_path'],
                'config_bash_directory': config['yunzai']['bash_directory'],
                'status_before': 'not_running'
            })
            try:
                if not config['yunzai']['git_bash_path']:
                    logger.warning("Git Bash路径未配置", extra={
                        'event_type': EventType.WARNING, 
                        'check_type': 'git_bash_path',
                        'details': '配置中缺少Git Bash路径，无法启动Yunzai'
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Git Bash路径未配置")
                    return
                if not config['yunzai']['bash_directory']:
                    logger.warning("Yunzai目录未配置", extra={
                        'event_type': EventType.WARNING, 
                        'check_type': 'bash_directory',
                        'details': '配置中缺少Yunzai目录路径，无法启动Yunzai'
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Yunzai目录未配置")
                    return
                if not os.path.exists(config['yunzai']['bash_directory']):
                    logger.error(f"Yunzai目录不存在: {config['yunzai']['bash_directory']}", extra={
                        'event_type': EventType.ERROR, 
                        'bash_directory': config['yunzai']['bash_directory'], 
                        'error_type': 'dir_not_found',
                        'suggestion': '请检查Yunzai目录路径配置是否正确'
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai目录不存在: {config['yunzai']['bash_directory']}")
                    return
                
                logger.debug(f"启动Yunzai命令", extra={
                    'event_type': 'debug',
                    'command': f"cd '{config['yunzai']['bash_directory']}' && node app",
                    'git_bash_path': config['yunzai']['git_bash_path'],
                    'working_directory': config['yunzai']['bash_directory']
                })
                
                # 使用git-bash启动Yunzai，使用固定命令"node app"
                start_command = [
                    config['yunzai']['git_bash_path'],
                    "-c",
                    f"cd '{config['yunzai']['bash_directory']}' && node app"
                ]
                result = subprocess.Popen(start_command)
                
                logger.info(f"Yunzai启动命令已执行，PID: {result.pid}", extra={
                    'event_type': EventType.PROCESS_START,
                    'process_name': process_name,
                    'pid': result.pid,
                    'start_time': datetime.now().isoformat(),
                    'command': start_command
                })
                
                # 清除手动停止状态
                try:
                    update_global_manual_stop_status('yunzai', False)
                except:
                    pass  # 如果全局变量不存在，跳过
                
                logger.info("Yunzai进程已启动", extra={
                    'event_type': EventType.PROCESS_START, 
                    'process_name': process_name,
                    'status': 'success',
                    'pid': result.pid
                })
                event_manager.publish(EventType.PROCESS_START, {
                    'process_name': process_name,
                    'status': 'success',
                    'pid': result.pid,
                    'command_used': start_command
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已启动")
            except FileNotFoundError as e:
                logger.error(f"Git Bash可执行文件或Yunzai目录未找到: {str(e)}", extra={
                    'event_type': EventType.ERROR, 
                    'process_name': process_name, 
                    'error': str(e), 
                    'error_type': 'file_not_found',
                    'config_git_bash': config['yunzai']['git_bash_path'],
                    'config_bash_directory': config['yunzai']['bash_directory'],
                    'suggestion': '请检查Git Bash路径和Yunzai目录配置是否正确'
                })
                event_manager.publish(EventType.ERROR, {
                    'message': f'Git Bash可执行文件或Yunzai目录未找到: {str(e)}',
                    'process_name': process_name,
                    'error': str(e),
                    'error_type': 'file_not_found',
                    'config_git_bash': config['yunzai']['git_bash_path'],
                    'config_bash_directory': config['yunzai']['bash_directory'],
                    'suggestion': '请检查Git Bash路径和Yunzai目录配置是否正确'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Git Bash可执行文件或Yunzai目录未找到: {str(e)}")
            except subprocess.SubprocessError as e:
                logger.error(f"启动Yunzai进程时出错: {str(e)}", extra={
                    'event_type': EventType.ERROR, 
                    'process_name': process_name, 
                    'error': str(e), 
                    'error_type': 'subprocess_error',
                    'error_class': type(e).__name__,
                    'command_used': start_command if 'start_command' in locals() else None,
                    'working_directory': config['yunzai']['bash_directory'] if 'config' in locals() else None
                })
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Yunzai进程时出错: {str(e)}',
                    'process_name': process_name,
                    'error': str(e),
                    'error_type': 'subprocess_error',
                    'error_class': type(e).__name__,
                    'command_used': start_command if 'start_command' in locals() else None,
                    'working_directory': config['yunzai']['bash_directory'] if 'config' in locals() else None
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时出错: {str(e)}")
            except Exception as e:
                logger.error(f"启动Yunzai进程时发生未知错误: {str(e)}", extra={
                    'event_type': EventType.ERROR, 
                    'process_name': process_name, 
                    'error': str(e), 
                    'error_type': 'unknown_error',
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc(),
                    'config_keys': list(config.get('yunzai', {}).keys()) if 'config' in locals() else []
                })
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Yunzai进程时发生未知错误: {str(e)}',
                    'process_name': process_name,
                    'error': str(e),
                    'error_type': 'unknown_error',
                    'error_class': type(e).__name__,
                    'traceback': __import__('traceback').format_exc()
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时发生未知错误: {str(e)}")
        else:
            logger.info("Yunzai已在运行", extra={
                'event_type': EventType.PROCESS_CHECK, 
                'process_name': process_name, 
                'status': 'running',
                'found_processes': found_yunzai_processes,
                'count': len(found_yunzai_processes)
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已在运行...")
            event_manager.publish(EventType.PROCESS_CHECK, {
                'process_name': process_name,
                'status': 'running',
                'found_processes': found_yunzai_processes,
                'count': len(found_yunzai_processes)
            })
    except KeyError as e:
        logger.error(f"配置错误: 缺少必需的配置项 {e}", extra={
            'event_type': EventType.ERROR, 
            'missing_key': str(e), 
            'error_type': 'config_error',
            'available_keys': list(config.keys()) if 'config' in locals() else [],
            'traceback': __import__('traceback').format_exc()
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'配置错误: 缺少必需的配置项 {e}',
            'missing_key': str(e),
            'error_type': 'config_error',
            'available_keys': list(config.keys()) if 'config' in locals() else [],
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise
    except Exception as e:
        logger.error(f"检查Yunzai时发生未知错误: {str(e)}", extra={
            'event_type': EventType.ERROR, 
            'error': str(e), 
            'process': 'yunzai', 
            'error_type': 'unknown_error',
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc(),
            'config_keys': list(config.keys()) if 'config' in locals() else []
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'检查Yunzai时发生未知错误: {str(e)}',
            'target_process': 'yunzai',
            'error': str(e),
            'error_type': 'unknown_error',
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Yunzai时发生未知错误: {str(e)}")
        raise

def run_monitor_loop(config):
    """运行监控循环 - 使用多线程并行监控"""
    def update_status_periodically():
        """定期更新状态信息"""
        while getattr(run_monitor_loop, 'running', True):
            try:
                # 检查llbot进程状态
                if config['llbot'].get('path'):
                    llbot_process_name = os.path.basename(config['llbot']['path']).lower()
                    possible_names = [llbot_process_name, 'lucky-lillia-desktop.exe']
                    
                    llbot_running = False
                    llbot_pid = None
                    for proc in psutil.process_iter(['name', 'pid']):
                        if proc.info['name'].lower() in possible_names:
                            llbot_running = True
                            llbot_pid = proc.info['pid']
                            break
                    
                    # 检查是否手动停止了llbot，如果是，则状态显示为停止
                    try:
                        is_llbot_manually_stopped = get_global_manual_stop_status('llbot')
                        if is_llbot_manually_stopped:
                            llbot_running = False
                            llbot_pid = None
                    except:
                        # 如果获取手动停止状态失败，使用默认行为
                        pass
                    
                    current_status['llbot'] = {'running': llbot_running, 'pid': llbot_pid}
                
                # 检查yunzai进程状态 (git-bash.exe)
                yunzai_running = False
                yunzai_pid = None
                for proc in psutil.process_iter(['name', 'pid']):
                    if proc.info['name'].lower() == 'git-bash.exe':
                        yunzai_running = True
                        yunzai_pid = proc.info['pid']
                        break
                
                # 检查是否手动停止了yunzai，如果是，则状态显示为停止
                try:
                    is_yunzai_manually_stopped = get_global_manual_stop_status('yunzai')
                    if is_yunzai_manually_stopped:
                        yunzai_running = False
                        yunzai_pid = None
                except:
                    # 如果获取手动停止状态失败，使用默认行为
                    pass
                
                current_status['yunzai'] = {'running': yunzai_running, 'pid': yunzai_pid}
                
                # 检查redis进程状态
                if config['redis'].get('path'):
                    redis_process_name = os.path.basename(config['redis']['path']).lower()
                    
                    redis_running = False
                    redis_pid = None
                    for proc in psutil.process_iter(['name', 'pid']):
                        if proc.info['name'].lower() == redis_process_name:
                            redis_running = True
                            redis_pid = proc.info['pid']
                            break
                    
                    # 检查是否手动停止了redis，如果是，则状态显示为停止
                    try:
                        is_redis_manually_stopped = get_global_manual_stop_status('redis')
                        if is_redis_manually_stopped:
                            redis_running = False
                            redis_pid = None
                    except:
                        # 如果获取手动停止状态失败，使用默认行为
                        pass
                    
                    current_status['redis'] = {'running': redis_running, 'pid': redis_pid}
                
                # 检查HTTP状态
                if config['http_check'].get('url'):
                    try:
                        is_accessible = async_http_check(config['http_check']['url'], config['http_check'].get('timeout', 5))
                        current_status['http_check'] = {'accessible': is_accessible}
                    except:
                        current_status['http_check'] = {'accessible': False}
                
                # 同步手动停止状态 - 从Flask应用同步到全局变量
                try:
                    global global_manual_stop_status
                    for key, value in manual_stop_status.items():
                        global_manual_stop_status[key] = value
                except:
                    pass  # 如果同步失败，继续运行
                
                time.sleep(3)  # 每3秒更新一次状态
            except Exception as e:
                logger.error(f"更新状态时出错: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'error': str(e),
                    'error_type': 'status_update_error'
                })
                time.sleep(5)
    
    def llbot_monitor():
        """llbot监控线程"""
        while getattr(run_monitor_loop, 'running', True):
            try:
                check_and_manage_llbot_async(config)
                time.sleep(config['llbot']['wait_seconds'])
            except KeyError as e:
                logger.error(f"llbot监控配置错误: 缺少配置项 {str(e)}", extra={'event_type': EventType.ERROR, 'thread': 'llbot_monitor', 'error_type': 'config_error', 'missing_key': str(e)})
                event_manager.publish(EventType.ERROR, {
                    'message': f'llbot监控配置错误: 缺少配置项 {str(e)}',
                    'thread': 'llbot_monitor',
                    'error_type': 'config_error',
                    'missing_key': str(e)
                })
                time.sleep(5)  # 出错后等待5秒再试
            except Exception as e:
                logger.error(f"llbot监控线程错误: {str(e)}", extra={'event_type': EventType.ERROR, 'thread': 'llbot_monitor', 'error': str(e), 'error_type': 'unknown_error'})
                event_manager.publish(EventType.ERROR, {
                    'message': f'llbot监控线程错误: {str(e)}',
                    'thread': 'llbot_monitor',
                    'error': str(e),
                    'error_type': 'unknown_error'
                })
                time.sleep(5)  # 出错后等待5秒再试
    
    def yunzai_monitor():
        """yunzai监控线程"""
        while getattr(run_monitor_loop, 'running', True):
            try:
                check_and_manage_yunzai_async(config)
                time.sleep(config['yunzai']['wait_seconds'])
            except KeyError as e:
                logger.error(f"yunzai监控配置错误: 缺少配置项 {str(e)}", extra={'event_type': EventType.ERROR, 'thread': 'yunzai_monitor', 'error_type': 'config_error', 'missing_key': str(e)})
                event_manager.publish(EventType.ERROR, {
                    'message': f'yunzai监控配置错误: 缺少配置项 {str(e)}',
                    'thread': 'yunzai_monitor',
                    'error_type': 'config_error',
                    'missing_key': str(e)
                })
                time.sleep(5)  # 出错后等待5秒再试
            except Exception as e:
                logger.error(f"yunzai监控线程错误: {str(e)}", extra={'event_type': EventType.ERROR, 'thread': 'yunzai_monitor', 'error': str(e), 'error_type': 'unknown_error'})
                event_manager.publish(EventType.ERROR, {
                    'message': f'yunzai监控线程错误: {str(e)}',
                    'thread': 'yunzai_monitor',
                    'error': str(e),
                    'error_type': 'unknown_error'
                })
                time.sleep(5)  # 出错后等待5秒再试
    
    # 启动监控线程
    llbot_thread = threading.Thread(target=llbot_monitor, daemon=True)
    yunzai_thread = threading.Thread(target=yunzai_monitor, daemon=True)
    status_thread = threading.Thread(target=update_status_periodically, daemon=True)
    
    llbot_thread.start()
    yunzai_thread.start()
    status_thread.start()
    
    # 启动Web服务器（如果Flask可用）
    if flask_available:
        web_thread = threading.Thread(target=start_web_server, daemon=True)
        web_thread.start()
    
    # 保持主线程运行
    try:
        while getattr(run_monitor_loop, 'running', True):
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止监控", extra={'event_type': EventType.PROCESS_STOP, 'reason': 'user_interrupt'})
        event_manager.publish(EventType.PROCESS_STOP, {
            'message': '收到中断信号',
            'reason': 'user_interrupt'
        })
    
    # 设置停止标志
    run_monitor_loop.running = False

def main():
    """主函数"""
    start_time = time.time()
    logger.info("监控程序开始启动", extra={
        'event_type': EventType.PROCESS_START,
        'start_time': datetime.fromtimestamp(start_time).isoformat(),
        'script_version': '2.0',
        'python_version': sys.version
    })
    
    # 启动事件管理器
    event_manager.start()
    
    try:
        # 加载配置
        logger.info("开始加载配置", extra={
            'event_type': EventType.CONFIG_LOAD,
            'action': 'load_config_start'
        })
        config = load_config()
        
        # 更新全局配置变量
        global current_config
        current_config = config
        
        logger.info("配置加载完成", extra={
            'event_type': EventType.CONFIG_LOAD,
            'action': 'load_config_complete',
            'config_keys': list(config.keys()) if config else [],
            'load_duration': f"{time.time() - start_time:.3f}s"
        })

        # 检查管理员权限，如果未以管理员权限运行则请求权限
        is_admin_now = is_admin()
        logger.info(f"管理员权限检查", extra={
            'event_type': EventType.PROCESS_CHECK,
            'is_admin': is_admin_now,
            'check_time': datetime.now().isoformat()
        })
        
        if not is_admin_now:
            logger.info("检查到未以管理员权限运行，请求管理员权限", extra={
                'event_type': EventType.PROCESS_CHECK, 
                'status': 'not_admin',
                'suggestion': '以管理员权限运行以获得完整功能'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 脚本需要管理员权限才能正常工作")
            if not run_as_admin():
                logger.error("无法获取管理员权限，脚本退出", extra={
                    'event_type': EventType.ERROR, 
                    'reason': 'cannot_acquire',
                    'exit_time': datetime.now().isoformat()
                })
                event_manager.publish(EventType.ERROR, {
                    'message': '无法获取管理员权限',
                    'reason': 'cannot_acquire'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 无法获取管理员权限，脚本退出")
                return
            # 如果当前进程不是管理员权限，则退出，让新启动的管理员进程继续
            if not is_admin():
                return
    
        print("=" * 60)
        print("llbot和Yunzai进程监控脚本")
        print("=" * 60)
        
        # 检查管理员权限
        admin_status = check_admin()
        
        logger.info("开始监控llbot和Yunzai进程", extra={
            'event_type': EventType.PROCESS_START,
            'monitored_processes': ['llbot', 'yunzai', 'redis'],
            'config_summary': {
                'llbot_configured': bool(config.get('llbot', {}).get('path')),
                'yunzai_configured': bool(config.get('yunzai', {}).get('git_bash_path')),
                'redis_configured': bool(config.get('redis', {}).get('path')),
                'http_check_configured': bool(config.get('http_check', {}).get('url'))
            }
        })
        event_manager.publish(EventType.PROCESS_START, {
            'message': '开始监控llbot和Yunzai进程',
            'monitored_processes': ['llbot', 'yunzai', 'redis'],
            'config_summary': {
                'llbot_configured': bool(config.get('llbot', {}).get('path')),
                'yunzai_configured': bool(config.get('yunzai', {}).get('git_bash_path')),
                'redis_configured': bool(config.get('redis', {}).get('path')),
                'http_check_configured': bool(config.get('http_check', {}).get('url'))
            }
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始监控llbot和Yunzai进程...")
        print("按 Ctrl+C 退出监控")
        
        # 设置运行标志
        run_monitor_loop.running = True
        
        try:
            # 运行监控循环
            run_monitor_loop(config)
        except KeyboardInterrupt:
            logger.info("监控已停止 (用户中断)", extra={
                'event_type': EventType.PROCESS_STOP, 
                'reason': 'user_interrupt',
                'stop_time': datetime.now().isoformat(),
                'total_runtime': f"{time.time() - start_time:.3f}s"
            })
            event_manager.publish(EventType.PROCESS_STOP, {
                'message': '监控已停止',
                'reason': 'user_interrupt',
                'total_runtime': f"{time.time() - start_time:.3f}s"
            })
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控已停止")
        except Exception as e:
            logger.error(f"监控循环中发生错误: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc(),
                'error_time': datetime.now().isoformat(),
                'total_runtime_until_error': f"{time.time() - start_time:.3f}s"
            })
            event_manager.publish(EventType.ERROR, {
                'message': f'监控循环中发生错误: {str(e)}',
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控循环中发生错误: {str(e)}")
    except Exception as e:
        logger.error(f"主程序启动失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc(),
            'startup_duration': f"{time.time() - start_time:.3f}s"
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'主程序启动失败: {str(e)}',
            'error': str(e),
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 主程序启动失败: {str(e)}")
        raise

def keep_alive_main():
    """带保活机制的主函数"""
    logger.info("启动带保活机制的监控程序", extra={'event_type': EventType.PROCESS_START})
    event_manager.publish(EventType.PROCESS_START, {
        'message': '启动带保活机制的监控程序'
    })
    max_restarts = 5  # 最大重启次数
    restart_count = 0
    last_restart_time = time.time()
    
    while True:
        try:
            main()
            logger.info("主程序正常退出", extra={'event_type': EventType.PROCESS_STOP, 'status': 'normal'})
            event_manager.publish(EventType.PROCESS_STOP, {
                'message': '主程序正常退出',
                'status': 'normal'
            })
            break  # 如果main函数正常退出，则退出保活循环
        except KeyboardInterrupt:
            logger.info("收到中断信号，退出保活机制", extra={'event_type': EventType.PROCESS_STOP, 'reason': 'user_interrupt'})
            event_manager.publish(EventType.PROCESS_STOP, {
                'message': '收到中断信号，退出保活机制',
                'reason': 'user_interrupt'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 收到中断信号，退出保活机制")
            break
        except Exception as e:
            current_time = time.time()
            # 如果在1分钟内重启次数过多，则退出
            if current_time - last_restart_time < 60:
                if restart_count >= max_restarts:
                    logger.error("短时间内重启次数过多，可能存在严重问题", extra={'event_type': EventType.ERROR, 'reason': 'too_many_restarts', 'restart_count': restart_count})
                    event_manager.publish(EventType.ERROR, {
                        'message': '短时间内重启次数过多，可能存在严重问题',
                        'reason': 'too_many_restarts',
                        'restart_count': restart_count
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 短时间内重启次数过多，可能存在严重问题，退出保活机制")
                    break
            else:
                restart_count = 0  # 重置重启计数
                
            logger.error(f"主程序异常退出: {str(e)}", extra={'event_type': EventType.ERROR, 'error': str(e)})
            event_manager.publish(EventType.ERROR, {
                'message': f'主程序异常退出: {str(e)}',
                'error': str(e)
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 主程序异常退出: {str(e)}")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {3}秒后尝试重启...")
            restart_count += 1
            last_restart_time = current_time
            time.sleep(3)  # 等待3秒后重启

if __name__ == "__main__":
    keep_alive_main()
