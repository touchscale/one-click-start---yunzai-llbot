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

# Web界面相关 - 只使用Flask
try:
    from flask import Flask as Quart, render_template_string, jsonify, request, session, redirect
    from flask import Response
    from functools import wraps
    import secrets
    flask_available = True
    print("使用Flask作为Web框架")
except ImportError:
    flask_available = False
    print("错误: Flask未安装，Web管理界面功能不可用。请运行 'pip install Flask' 安装。")

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
    DEBUG = "debug"

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
    # 创建Flask应用
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

    @app.errorhandler(404)
    def handle_404(e):
        """处理404错误：重定向到登录页面或返回API错误"""
        # API 请求返回 JSON 错误
        if str(request.path).startswith('/api/'):
            logger.warning(f"API端点不存在: {request.path}", extra={
                'event_type': EventType.WARNING,
                'path': request.path,
                'method': request.method
            })
            return jsonify({'error': 'API端点不存在', 'path': request.path}), 404
        
        # 重定向到登录页面
        return redirect('/login')

    @app.errorhandler(500)
    def handle_500(e):
        """处理500错误"""
        logger.error(f"服务器内部错误: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'path': request.path,
            'method': request.method
        })
        if str(request.path).startswith('/api/'):
            return jsonify({'error': '服务器内部错误'}), 500
        return render_template_string(get_login_template("服务器内部错误，已记录。")), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        """全局异常处理：记录完整 traceback，并对 API/页面给出友好提示"""
        import traceback as _tb
        tb = _tb.format_exc()
        # 将 traceback 直接包含到日志消息中，以便结构化文件记录中可见完整堆栈
        logger.error(f"Unhandled exception: {str(e)}\n{tb}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'path': request.path,
            'method': request.method,
            'traceback': tb
        })
        # API 请求返回 JSON 错误
        try:
            if hasattr(request, 'path') and str(request.path).startswith('/api/'):
                return jsonify({'message': '内部错误，已记录。', 'error': type(e).__name__}), 500
        except Exception:
            pass
        # 页面请求返回友好错误页面（防止二次异常）
        try:
            return render_template_string(get_login_template("内部错误，已记录。")), 500
        except Exception:
            return "Internal Server Error", 500
            
    # 添加请求前处理，用于安全检查
    @app.after_request
    def after_request(response):
        """添加安全头部"""
        # 防止点击劫持
        response.headers['X-Frame-Options'] = 'DENY'
        # 防止MIME类型嗅探
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # 防止跨站脚本攻击
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # 内容安全策略 - 完善CDN资源加载权限
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; font-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; img-src 'self' data: https:; connect-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; manifest-src 'self';"
        return response
        
    @app.before_request
    def before_request():
        """请求前处理：安全检查和输入验证"""
        # 允许访问登录页面、健康检查和静态文件
        if request.endpoint in ['login', 'static_files', 'health_check'] or request.path.startswith('/api/change-password') or request.path.startswith('/api/reset-password'):
            return
            
        # 检查认证状态（对于非登录页面）
        if request.endpoint != 'login' and 'logged_in' not in session and not request.path.startswith('/api/'):
            return redirect('/login')
            
        # 对于API请求，检查认证
        if request.path.startswith('/api/') and request.endpoint not in ['login', 'api_change_password', 'api_reset_password', 'health_check']:
            if 'logged_in' not in session:
                if request.is_json:
                    return jsonify({'error': '未认证'}), 401
                else:
                    return redirect('/login')
            
        # 验证输入数据的安全性
        if request.method == 'POST':
            # 防止超大请求体
            content_length = request.content_length
            if content_length and content_length > 1024 * 1024:  # 1MB
                logger.warning(f"请求体过大: {content_length} bytes", extra={
                    'event_type': EventType.WARNING,
                    'path': request.path,
                    'method': request.method
                })
                return jsonify({'error': '请求体过大'}), 413
    
    # 存储配置和状态的全局变量
    current_config = {}
    current_status = {
        'llbot': {'running': False, 'pid': None},
        'yunzai': {'running': False, 'pid': None},
        'redis': {'running': False, 'pid': None},
        'http_check': {'accessible': False, 'configured': False}
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
        .btn-forgot-password {{
            background: linear-gradient(45deg, #6c757d, #5a6268);
            border: none;
            border-radius: 10px;
            padding: 10px;
            font-weight: 500;
            font-size: 14px;
            width: 100%;
            margin-top: 10px;
            transition: all 0.3s;
            color: white;
        }}
        .btn-forgot-password:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(108, 117, 125, 0.4);
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
            <div class="d-grid gap-2 mt-3">
                <button class="btn btn-forgot-password" type="button" data-bs-toggle="modal" data-bs-target="#forgotPasswordModal">
                    <i class="fas fa-question-circle"></i> 忘记密码?
                </button>
            </div>
                <div class="text-center mt-3 text-muted" style="font-size: 0.85em;">
                    <p>当前登录用户名: {username_hint}</p>
                </div>
        </div>
    </div>

    <!-- 忘记密码模态框：提供直接在页面重置密码的表单 -->
    <div class="modal fade" id="forgotPasswordModal" tabindex="-1" aria-labelledby="forgotPasswordModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="forgotPasswordModalLabel"><i class="fas fa-question-circle me-2 text-warning"></i>忘记密码</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div id="resetAlert"></div>
                    <form id="resetPasswordForm">
                        <div class="mb-3">
                            <label for="new_password" class="form-label">新密码</label>
                            <input type="password" class="form-control" id="new_password" name="new_password" placeholder="请输入新密码（建议至少6位）" required minlength="4">
                        </div>
                        <div class="mb-3">
                            <label for="confirm_password" class="form-label">确认新密码</label>
                            <input type="password" class="form-control" id="confirm_password" name="confirm_password" placeholder="请再次输入新密码" required>
                        </div>
                        <div class="form-check mb-3">
                            <input class="form-check-input" type="checkbox" value="1" id="confirmEdit">
                            <label class="form-check-label" for="confirmEdit">我确认将更新 <strong>config.yaml</strong> 中的密码</label>
                        </div>
                        <div class="d-grid">
                            <button type="submit" class="btn btn-primary">重置密码并保存</button>
                        </div>
                    </form>
                    <hr>
                    <p class="text-muted">或者手动编辑 <strong>config.yaml</strong> 并重启程序。</p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 页面初始化：隐藏错误消息并绑定重置表单提交处理
        document.addEventListener('DOMContentLoaded', function() {{
            const errorDiv = document.querySelector('.error-message');
            if (errorDiv) {{
                setTimeout(function() {{
                    errorDiv.style.display = 'none';
                }}, 5000);
            }}

            const form = document.getElementById('resetPasswordForm');
            if (form) {{
                form.addEventListener('submit', async function(event) {{
                    event.preventDefault();
                    const new_password = document.getElementById('new_password').value.trim();
                    const confirm_password = document.getElementById('confirm_password').value.trim();
                    const confirmEdit = document.getElementById('confirmEdit').checked;
                    const alertDiv = document.getElementById('resetAlert');
                    alertDiv.innerHTML = '';

                    if (!new_password || !confirm_password) {{
                        alertDiv.innerHTML = '<div class="alert alert-warning">请输入新密码并确认</div>';
                        return;
                    }}
                    if (new_password !== confirm_password) {{
                        alertDiv.innerHTML = '<div class="alert alert-warning">两次密码输入不一致</div>';
                        return;
                    }}
                    if (new_password.length < 4) {{
                        alertDiv.innerHTML = '<div class="alert alert-warning">密码太短（至少4位）</div>';
                        return;
                    }}
                    if (!confirmEdit) {{
                        alertDiv.innerHTML = '<div class="alert alert-warning">请确认将更新配置文件</div>';
                        return;
                    }}

                    try {{
                        const resp = await fetch('/api/reset-password', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ new_password, confirm_password, confirm_edit: confirmEdit }})
                        }});
                        const data = await resp.json();
                        if (resp.ok) {{
                            alertDiv.innerHTML = '<div class="alert alert-success">' + (data.message || '密码重置成功') + '</div>';
                            setTimeout(function() {{
                                const modalEl = document.getElementById('forgotPasswordModal');
                                const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                                modal.hide();
                            }}, 1200);
                        }} else {{
                            alertDiv.innerHTML = '<div class="alert alert-danger">' + (data.message || '重置失败') + '</div>';
                        }}
                    }} catch (err) {{
                        alertDiv.innerHTML = '<div class="alert alert-danger">请求失败: ' + err + '</div>';
                    }}
                }});
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
    def index():
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
        :root {
            --primary-gradient: linear-gradient(45deg, #007bff, #6610f2);
            --success-gradient: linear-gradient(45deg, #28a745, #20c997);
            --danger-gradient: linear-gradient(45deg, #dc3545, #fd7e14);
            --warning-gradient: linear-gradient(45deg, #ffc107, #fd7e14);
            --info-gradient: linear-gradient(45deg, #17a2b8, #6f42c1);
        }
        
        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            padding-top: 20px;
            padding-bottom: 20px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .main-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            margin-bottom: 20px;
        }
        .status-card {
            border-radius: 12px;
            border: none;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            height: 100%;
            background: linear-gradient(145deg, #ffffff, #f8f9fa);
            overflow: hidden;
        }
        .status-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.2);
        }
        .status-running {
            background: var(--success-gradient) !important;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
            box-shadow: 0 0 10px rgba(40, 167, 69, 0.5);
            animation: pulse 2s infinite;
        }
        .status-stopped {
            background: var(--danger-gradient) !important;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .status-unknown {
            background: var(--warning-gradient) !important;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }
        .btn-action {
            border-radius: 10px;
            padding: 10px 16px;
            font-weight: 500;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border: none;
            width: 100%;
            margin-bottom: 8px;
        }
        .btn-action i {
            margin-right: 8px;
        }
        .btn-start {
            background: var(--success-gradient);
            color: white;
        }
        .btn-start:hover {
            background: linear-gradient(45deg, #218838, #1ea085);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(40, 167, 69, 0.4);
        }
        .btn-stop {
            background: var(--danger-gradient);
            color: white;
        }
        .btn-stop:hover {
            background: linear-gradient(45deg, #c82333, #e06b10);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(220, 53, 69, 0.4);
        }
        .btn-check {
            background: var(--primary-gradient);
            color: white;
        }
        .btn-check:hover {
            background: linear-gradient(45deg, #0056b3, #520dc2);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.4);
        }
        .log-container {
            background: #1e1e1e;
            border-radius: 10px;
            padding: 15px;
            height: 400px;
            overflow-y: auto;
            font-family: 'Courier New', 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            box-shadow: inset 0 0 15px rgba(0,0,0,0.5);
            color: #f5f5f5;
            position: relative;
        }
        .log-entry { 
            margin-bottom: 5px; 
            line-height: 1.4;
            padding: 2px 0;
            border-left: 3px solid transparent;
        }
        .log-entry:hover {
            background: rgba(255,255,255,0.05);
            padding-left: 8px;
            border-left: 3px solid #4a90e2;
            border-radius: 2px;
        }
        .log-info { 
            color: #87ceeb; 
            border-left-color: #87ceeb;
        }
        .log-warning { 
            color: #ffcc00; 
            border-left-color: #ffcc00;
        }
        .log-error { 
            color: #ff6b6b; 
            border-left-color: #ff6b6b;
        }
        .log-debug { 
            color: #98fb98; 
            border-left-color: #98fb98;
        }
        .header-title {
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: 700;
            font-size: 1.8rem;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card-header {
            border-bottom: 1px solid rgba(0,0,0,0.05);
            background: linear-gradient(to right, #f8f9fa, #e9ecef) !important;
            border-radius: 12px 12px 0 0 !important;
            padding: 1.2rem 1.5rem !important;
        }
        .card-body {
            padding: 1.5rem !important;
        }
        .process-icon {
            font-size: 28px;
            margin-right: 12px;
            vertical-align: middle;
            width: 30px;
            text-align: center;
        }
        .status-text {
            font-weight: 600;
            font-size: 0.95rem;
        }
        .alert-box {
            border-radius: 12px;
            border: none;
            overflow: hidden;
        }
        .counter-badge {
            background: linear-gradient(45deg, #6c757d, #495057);
            border-radius: 20px;
            padding: 5px 12px;
            font-size: 0.85em;
            font-weight: 500;
        }
        .dropdown-menu {
            border-radius: 12px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.15);
            border: none;
            padding: 8px 0;
        }
        .dropdown-item {
            padding: 10px 20px;
            transition: all 0.2s;
        }
        .dropdown-item:hover {
            background: rgba(0, 123, 255, 0.1);
        }
        .password-modal .form-control {
            border-radius: 8px;
            border: 2px solid #e9ecef;
            padding: 10px 15px;
        }
        .password-modal .form-control:focus {
            border-color: #80bdff;
            box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
        }
        .system-stats {
            display: flex;
            justify-content: space-around;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        .stat-item {
            text-align: center;
            padding: 15px;
            background: rgba(255,255,255,0.7);
            border-radius: 10px;
            margin: 5px;
            min-width: 120px;
            flex: 1;
        }
        .stat-value {
            font-size: 1.8rem;
            font-weight: bold;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-label {
            font-size: 0.9rem;
            color: #6c757d;
        }
        .footer {
            text-align: center;
            padding: 20px;
            color: #6c757d;
            font-size: 0.9rem;
        }
        .refresh-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: var(--success-gradient);
            margin-left: 8px;
            animation: blink 1.5s infinite;
        }
        @keyframes blink {
            0% { opacity: 1; }
            50% { opacity: 0.3; }
            100% { opacity: 1; }
        }
        .card-title {
            font-weight: 600;
            color: #495057;
        }
        
        /* 确保HTTP检查卡片始终可见并覆盖可能遮挡（增强版） */
        #http-check-container,
        #http-check-card {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: relative !important;
            z-index: 9999 !important;
            pointer-events: auto !important;
            max-height: none !important;
        }

        /* 强制按钮样式，确保可见且可点击 */
        #http-check-button,
        #http-check-card .btn-check {
            display: inline-flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: relative !important;
            z-index: 10000 !important;
            pointer-events: auto !important;
        }

        /* 额外确保HTTP检查卡片及其子元素始终可见（保留以防有其他规则覆盖） */
        #http-check-card *,
        #http-check-container * {
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }
        
        /* 侧边栏样式 */
        .sidebar {
            position: fixed;
            top: 0;
            left: 0;
            height: 100vh;
            width: 250px;
            background: linear-gradient(180deg, #2c3e50 0%, #1a252f 100%);
            box-shadow: 3px 0 15px rgba(0, 0, 0, 0.2);
            z-index: 1000;
            padding-top: 20px;
            transition: all 0.3s ease;
        }
        
        .sidebar-header {
            padding: 0 20px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 20px;
        }
        
        .sidebar-title {
            color: white;
            font-size: 1.2rem;
            font-weight: 600;
            margin: 0;
        }
        
        .sidebar-nav {
            padding: 0 15px;
        }
        
        .sidebar-item {
            margin-bottom: 8px;
        }
        
        .sidebar-link {
            display: flex;
            align-items: center;
            padding: 12px 15px;
            color: rgba(255, 255, 255, 0.8);
            text-decoration: none;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        
        .sidebar-link:hover {
            background: rgba(255, 255, 255, 0.1);
            color: white;
            transform: translateX(5px);
        }
        
        .sidebar-link.active {
            background: linear-gradient(45deg, #007bff, #6610f2);
            color: white;
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
        }
        
        .sidebar-link i {
            width: 24px;
            margin-right: 12px;
            font-size: 1.1rem;
        }
        
        .sidebar-link span {
            font-weight: 500;
        }
        
        .main-content {
            margin-left: 250px;
            padding: 20px;
            transition: all 0.3s ease;
        }
        
        @media (max-width: 768px) {
            .sidebar {
                width: 70px;
            }
            
            .sidebar-header {
                padding: 0 10px 20px;
            }
            
            .sidebar-title {
                font-size: 0;
            }
            
            .sidebar-title:after {
                content: "☰";
                font-size: 1.5rem;
            }
            
            .sidebar-link span {
                display: none;
            }
            
            .sidebar-link i {
                margin-right: 0;
                font-size: 1.3rem;
            }
            
            .main-content {
                margin-left: 70px;
            }
        }
    </style>
</head>
<body>
    <!-- 侧边栏 -->
    <div class="sidebar">
        <div class="sidebar-header">
            <h2 class="sidebar-title">
                <i class="fas fa-tachometer-alt me-2"></i>监控系统
            </h2>
        </div>
        <nav class="sidebar-nav">
            <div class="sidebar-item">
                <a href="/" class="sidebar-link active">
                    <i class="fas fa-home"></i>
                    <span>系统监控</span>
                </a>
            </div>
            <div class="sidebar-item">
                <a href="/config" class="sidebar-link">
                    <i class="fas fa-cogs"></i>
                    <span>配置管理</span>
                </a>
            </div>
        </nav>
    </div>
    
    <!-- 主内容区域 -->
    <div class="main-content">
        <div class="container-fluid">
            <!-- 顶部标题栏 -->
            <div class="d-flex justify-content-between align-items-center mb-4 px-3">
                <div class="d-flex align-items-center">
                    <h1 class="header-title mb-0 me-3">
                        <i class="fas fa-tachometer-alt me-2"></i>llbot Yunzai 监控系统
                    </h1>
                    <span class="refresh-indicator" id="refresh-status" title="实时刷新状态"></span>
                </div>
                <div class="dropdown">
                    <button class="btn btn-outline-primary dropdown-toggle" type="button" id="userMenu" data-bs-toggle="dropdown" aria-expanded="false">
                        <i class="fas fa-user-circle me-1"></i>账户管理
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userMenu">
                        <li><a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#passwordModal"><i class="fas fa-key me-2"></i>修改密码</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item text-danger" href="/logout"><i class="fas fa-sign-out-alt me-2"></i>退出登录</a></li>
                    </ul>
                </div>
            </div>

        <!-- 系统统计信息 -->
        <div class="container-fluid px-4 mb-4">
            <div class="system-stats">
                <div class="stat-item">
                    <div class="stat-value" id="llbot-stat">0</div>
                    <div class="stat-label">llbot 状态</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="yunzai-stat">0</div>
                    <div class="stat-label">Yunzai 状态</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="redis-stat">0</div>
                    <div class="stat-label">Redis 状态</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="http-stat">0</div>
                    <div class="stat-label">HTTP 服务</div>
                </div>
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
                
                <div class="col-lg-3 col-md-6 col-sm-12" id="http-check-container">
                    <div class="card status-card" id="http-check-card">
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
                                <button id="http-check-button" class="btn btn-check btn-action" onclick="manualHttpCheck()" style="display:block !important; visibility:visible !important; opacity:1 !important;">
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
                    <div class="d-flex align-items-center ms-auto">
                        <span class="counter-badge me-3">
                            <i class="fas fa-list me-1"></i>
                            <span id="log-count">0</span> 条
                        </span>
                        <button class="btn btn-sm btn-outline-secondary" onclick="clearLogs()">
                            <i class="fas fa-trash-alt me-1"></i>清空日志
                        </button>
                    </div>
                </div>
                <div class="card-body p-0">
                    <div id="logs" class="log-container"></div>
                </div>
            </div>
        </div>
        
        <!-- 页脚 -->
        <div class="footer">
            <p>llbot Yunzai 监控系统 v2.0 | 实时监控您的服务状态</p>
            <p>最后更新: <span id="last-update"></span> | 自动刷新: <span id="refresh-interval">5秒</span></p>
        </div>
    </div>

    <!-- 密码修改模态框 -->
    <div class="modal fade" id="passwordModal" tabindex="-1" aria-labelledby="passwordModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="passwordModalLabel"><i class="fas fa-key me-2 text-primary"></i>修改账户密码</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <form id="passwordForm">
                        <div class="mb-3">
                            <label for="currentPassword" class="form-label">当前密码</label>
                            <input type="password" class="form-control" id="currentPassword" required placeholder="请输入当前密码">
                        </div>
                        <div class="mb-3">
                            <label for="newUsername" class="form-label">新用户名 (可选)</label>
                            <input type="text" class="form-control" id="newUsername" placeholder="保持当前用户名请留空">
                        </div>
                        <div class="mb-3">
                            <label for="newPassword" class="form-label">新密码</label>
                            <input type="password" class="form-control" id="newPassword" required placeholder="请输入新密码">
                        </div>
                        <div class="mb-3">
                            <label for="confirmPassword" class="form-label">确认新密码</label>
                            <input type="password" class="form-control" id="confirmPassword" required placeholder="请再次输入新密码">
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">取消</button>
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
                        
                        // HTTP检查卡片总是显示，不需要额外的显示控制
                        // 更新HTTP检查状态
                        if (data.http_check && data.http_check.configured) {
                            if (data.http_check.accessible) {
                                httpStatus.textContent = '可访问';
                                httpIndicator.className = 'status-running';
                            } else {
                                httpStatus.textContent = '不可访问';
                                httpIndicator.className = 'status-stopped';
                            }
                        } else {
                            httpStatus.textContent = '未配置';
                            httpIndicator.className = 'status-unknown';
                        }
                        
                        // 更新统计信息
                        updateStats(data);
                        
                        // 确保HTTP检查卡片始终可见
                        ensureHttpCardVisibility();
                    }
                })
                .catch(error => {
                    console.error('获取状态失败:', error);
                    // 即使获取状态失败，也要确保HTTP检查卡片显示
                    const httpCard = document.getElementById('http-check-card');
                    const httpContainer = document.getElementById('http-check-container');
                    
                    if (httpCard) {
                        httpCard.style.display = 'block';
                        httpCard.style.visibility = 'visible';
                        httpCard.style.opacity = '1';
                        httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                    }
                    
                    if (httpContainer) {
                        httpContainer.style.display = 'block';
                        httpContainer.style.visibility = 'visible';
                        httpContainer.style.opacity = '1';
                        httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                    }
                    
                    // 检查是否是认证错误
                    if (error.message && error.message.includes('401')) {
                        handleAuthError();
                    }
                });
        }
        
        // 更新统计信息
        function updateStats(data) {
            const llbotStat = document.getElementById('llbot-stat');
            const yunzaiStat = document.getElementById('yunzai-stat');
            const redisStat = document.getElementById('redis-stat');
            const httpStat = document.getElementById('http-stat');
            
            if(data.llbot && data.llbot.running) {
                llbotStat.textContent = '运行';
                llbotStat.style.color = '#28a745';
            } else {
                llbotStat.textContent = '停止';
                llbotStat.style.color = '#dc3545';
            }
            
            if(data.yunzai && data.yunzai.running) {
                yunzaiStat.textContent = '运行';
                yunzaiStat.style.color = '#28a745';
            } else {
                yunzaiStat.textContent = '停止';
                yunzaiStat.style.color = '#dc3545';
            }
            
            if(data.redis && data.redis.running) {
                redisStat.textContent = '运行';
                redisStat.style.color = '#28a745';
            } else {
                redisStat.textContent = '停止';
                redisStat.style.color = '#dc3545';
            }
            
            // 确保HTTP检查状态总是更新，不管是否有配置
            if(data.http_check && data.http_check.configured) {
                if(data.http_check.accessible) {
                    httpStat.textContent = '正常';
                    httpStat.style.color = '#28a745';
                } else {
                    httpStat.textContent = '异常';
                    httpStat.style.color = '#dc3545';
                }
            } else {
                httpStat.textContent = '未配置';
                httpStat.style.color = '#6c757d';
            }
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
                        
                        // 更新最后更新时间
                        document.getElementById('last-update').textContent = new Date().toLocaleString('zh-CN');
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
        
        // 清空日志
        function clearLogs() {
            const logsDiv = document.getElementById('logs');
            logsDiv.innerHTML = '';
            document.getElementById('log-count').textContent = '0';
            document.getElementById('last-update').textContent = '已清空';
            showAlert('日志已清空', 'info');
        }
        
        // 控制进程（已移除确认框，点击立即执行）
        function controlProcess(process, action) {
            const actionText = action === 'start' ? '启动' : '停止';
            // 不再弹出确认框，直接执行操作以提高体验。
            
            // 禁用按钮并显示加载状态
            const buttons = document.querySelectorAll(`button[onclick*="controlProcess('${process}'"]`);
            buttons.forEach(btn => {
                btn.disabled = true;
                const originalHTML = btn.innerHTML;
                btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${actionText}中...`;
                
                // 恢复原始内容的函数
                setTimeout(() => {
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                }, 3000); // 3秒后恢复，即使没有收到响应
            });
            
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
                    // 重置按钮状态
                    buttons.forEach(btn => {
                        btn.disabled = false;
                        btn.innerHTML = btn.getAttribute('data-original-content') || btn.innerHTML.replace('<i class="fas fa-spinner fa-spin"></i> ', '');
                    });
                    
                    // 使用Bootstrap的alert显示消息
                    showAlert(data.message, 'success');
                    updateStatus();
                }
            })
            .catch(error => {
                console.error('控制进程失败:', error);
                // 重置按钮状态
                buttons.forEach(btn => {
                    btn.disabled = false;
                    btn.innerHTML = btn.getAttribute('data-original-content') || btn.innerHTML.replace('<i class="fas fa-spinner fa-spin"></i> ', '');
                });
                
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
            // 禁用按钮并显示加载状态
            const button = document.querySelector('button[onclick="manualHttpCheck()"]');
            const originalHTML = button.innerHTML;
            button.disabled = true;
            button.innerHTML = `<i class="fas fa-spinner fa-spin"></i> 检查中...`;
            
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
                    // 重置按钮状态
                    button.disabled = false;
                    button.innerHTML = originalHTML;
                    
                    showAlert(data.message, 'info');
                    updateStatus();
                }
            })
            .catch(error => {
                console.error('手动检查失败:', error);
                // 重置按钮状态
                button.disabled = false;
                button.innerHTML = originalHTML;
                
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
            alertDiv.style.cssText = 'top: 20px; right: 20px; min-width: 350px; z-index: 9999; max-width: 350px;';
            alertDiv.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <strong>` + (type.charAt(0).toUpperCase() + type.slice(1)) + `:</strong>
                        <div>` + message + `</div>
                    </div>
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close" style="margin-left: 10px;"></button>
                </div>
            `;
            
            document.body.appendChild(alertDiv);
            
            // 5秒后自动移除
            setTimeout(() => {
                if(alertDiv && alertDiv.parentNode) {
                    const alertInstance = bootstrap.Alert.getOrCreateInstance(alertDiv);
                    alertInstance.close();
                }
            }, 5000);
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

            // 禁用按钮并显示加载状态
            const submitBtn = document.querySelector('#passwordModal .btn-primary');
            const originalText = submitBtn.textContent;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 处理中...';
            submitBtn.disabled = true;

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
                        // 重置按钮
                        submitBtn.innerHTML = originalText;
                        submitBtn.disabled = false;
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
                        // 重置按钮
                        submitBtn.innerHTML = originalText;
                        submitBtn.disabled = false;
                    });
                }
            })
            .catch(error => {
                showAlert('修改密码失败: ' + error, 'danger');
                // 重置按钮
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            });
        }
        
        // 定期更新
        setInterval(updateStatus, 5000);  // 每5秒更新一次状态
        setInterval(updateLogs, 2000);    // 每2秒更新一次日志
        
        // 页面初始化
        function initPage() {
            // 确保HTTP检查卡片始终显示
            const httpCard = document.getElementById('http-check-card');
            const httpContainer = document.getElementById('http-check-container');
            
            if (httpCard) {
                httpCard.style.display = 'block';
                httpCard.style.visibility = 'visible';
                httpCard.style.opacity = '1';
                httpCard.style.maxHeight = 'none';
                httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }
            
            if (httpContainer) {
                httpContainer.style.display = 'block';
                httpContainer.style.visibility = 'visible';
                httpContainer.style.opacity = '1';
                httpContainer.style.maxHeight = 'none';
                httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }
            
            // 确保按钮元素存在
            const httpButton = document.querySelector('#http-check-card .btn-check');
            if (httpButton) {
                httpButton.style.display = 'block';
                httpButton.style.visibility = 'visible';
                httpButton.style.opacity = '1';
                httpButton.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }
            
            // 额外确保所有子元素可见
            if (httpCard) {
                const allChildren = httpCard.querySelectorAll('*');
                allChildren.forEach(child => {
                    if (child.style) {
                        child.style.display = 'block';
                        child.style.visibility = 'visible';
                        child.style.opacity = '1';
                        if (child.classList) {
                            child.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                        }
                    }
                });
            }
        }
        
        // 初始加载
        document.addEventListener('DOMContentLoaded', function() {
            // 延迟执行确保DOM完全加载
            setTimeout(function() {
                initPage();
                updateStatus();
                updateLogs();
            }, 100); // 延迟100毫秒确保DOM渲染完成
        });
        
        // 额外确保页面完全加载后执行初始化
        window.onload = function() {
            // 再次确保HTTP检查卡片显示
            setTimeout(function() {
                const httpCard = document.getElementById('http-check-card');
                const httpContainer = document.getElementById('http-check-container');
                
                if (httpCard) {
                    httpCard.style.display = 'block';
                    httpCard.style.visibility = 'visible';
                    httpCard.style.opacity = '1';
                    httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                }
                
                if (httpContainer) {
                    httpContainer.style.display = 'block';
                    httpContainer.style.visibility = 'visible';
                    httpContainer.style.opacity = '1';
                    httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                }
                
                // 确保按钮元素存在
                const httpButton = document.querySelector('#http-check-card .btn-check');
                if (httpButton) {
                    httpButton.style.display = 'block';
                    httpButton.style.visibility = 'visible';
                    httpButton.style.opacity = '1';
                    httpButton.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                }
            }, 200); // 延迟200毫秒确保所有资源加载完成
        }
        
        // 额外的检查函数，用于在状态更新后确保显示
        function ensureHttpCardVisibility() {
            const httpCard = document.getElementById('http-check-card');
            const httpContainer = document.getElementById('http-check-container');
            
            if (httpCard && httpCard.style.display === 'none') {
                httpCard.style.display = 'block';
                httpCard.style.visibility = 'visible';
                httpCard.style.opacity = '1';
                httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }
            
            if (httpContainer && httpContainer.style.display === 'none') {
                httpContainer.style.display = 'block';
                httpContainer.style.visibility = 'visible';
                httpContainer.style.opacity = '1';
                httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }
        }
    </script>
</body>
</html>
        '''
            return render_template_string(html_template)
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc();
            logger.error(f"index render error: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'traceback': tb
            })
            # 返回简短错误页面并确保日志已记录
            try:
                return render_template_string('<h1>渲染错误</h1><pre>{}</pre>'.format(str(e))), 500
            except Exception:
                return "Internal Server Error", 500
    
    @app.route('/api/status')
    def api_status():
        """获取当前状态"""
        if 'logged_in' not in session:
            return jsonify({'error': '未认证'}), 401
        return jsonify(current_status)
    
    @app.route('/api/logs')
    def api_logs():
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
    def api_control():
        """控制进程"""
        if 'logged_in' not in session:
            return jsonify({'error': '未认证'}), 401
        try:
            data = request.get_json()
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
    def api_manual_check():
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
    def logout():
        """登出功能"""
        session.pop('logged_in', None)
        session.pop('username', None)
        logger.info("用户已登出", extra={'event_type': 'auth', 'action': 'logout'})
        return redirect('/login')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """自定义登录页面"""
        try:
            if request.method == 'POST':
                form = request.form
                username = (form.get('username') or '').strip()
                password = form.get('password') or ''

                if not username or not password:
                    logger.warning("登录失败：缺少用户名或密码", extra={'event_type': 'auth', 'action': 'login_failed'})
                    return render_template_string(get_login_template("请输入用户名和密码"))

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
                    return render_template_string(get_login_template("用户名或密码错误"))
            else:
                return render_template_string(get_login_template())
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            logger.error(f"登录页面渲染或处理失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'traceback': tb
            })
            # 返回用户友好的错误页面
            return render_template_string(get_login_template("内部错误，已记录。")), 500

    @app.route('/api/change-password', methods=['POST'])
    @requires_auth
    def api_change_password():
        """更改密码API端点"""
        try:
            data = request.get_json()
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

    @app.route('/api/reset-password', methods=['POST'])
    def api_reset_password():
        """未登录情况下通过登录页重置密码（将直接更新 config.yaml）。"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'message': '无效的JSON数据'}), 400

            new_password = data.get('new_password')
            confirm_password = data.get('confirm_password')
            confirm_edit = data.get('confirm_edit')

            if not new_password or not confirm_password:
                return jsonify({'message': '请输入新密码并确认'}), 400
            if new_password != confirm_password:
                return jsonify({'message': '两次密码输入不一致'}), 400
            if len(new_password) < 4:
                return jsonify({'message': '密码太短（至少4位）'}), 400
            if not confirm_edit:
                return jsonify({'message': '请确认将更新配置文件'}), 400

            if 'web_auth' not in current_config:
                current_config['web_auth'] = {}
            current_config['web_auth']['password'] = new_password

            try:
                save_config(current_config, "config.yaml")
                logger.info('通过重置页面更新密码', extra={'event_type': 'config_update', 'action': 'password_reset_via_web'})
                return jsonify({'message': '密码重置成功，已保存到 config.yaml，请重启程序或使用新密码登录'})
            except Exception as e:
                logger.error(f"保存配置失败: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'error': str(e),
                    'action': 'password_reset_save_failure'
                })
                return jsonify({'message': f'保存配置失败: {str(e)}'}), 500

        except Exception as e:
            logger.error(f"重置密码失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'action': 'password_reset_failure'
            })
            return jsonify({'message': f'重置密码失败: {str(e)}'}), 500

    # 添加静态文件路由（用于处理CSS、JS等资源）
    @app.route('/static/<path:filename>')
    def static_files(filename):
        """处理静态文件请求"""
        if 'logged_in' not in session:
            return redirect('/login')
        # 由于我们使用的是内联样式和脚本，返回404
        return '', 404
    
    # 添加系统信息API
    @app.route('/api/system-info')
    @requires_auth
    def api_system_info():
        """获取系统信息"""
        import platform
        try:
            system_info = {
                'platform': platform.system(),
                'platform_version': platform.version(),
                'platform_release': platform.release(),
                'architecture': platform.architecture()[0],
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'hostname': platform.node(),
                'timestamp': datetime.now().isoformat()
            }
            return jsonify(system_info)
        except Exception as e:
            logger.error(f"获取系统信息失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return jsonify({'error': '获取系统信息失败'}), 500
    
    # 添加配置信息API
    @app.route('/api/config')
    @requires_auth
    def api_config():
        """获取当前配置信息（敏感信息已脱敏）"""
        try:
            # 创建脱敏后的配置副本
            safe_config = {}
            for key, value in current_config.items():
                if isinstance(value, dict):
                    safe_config[key] = {}
                    for sub_key, sub_value in value.items():
                        # 对敏感信息进行脱敏处理
                        if sub_key in ['password', 'token', 'secret', 'key', 'auth']:
                            safe_config[key][sub_key] = '***'
                        else:
                            safe_config[key][sub_key] = sub_value
                else:
                    safe_config[key] = value
            
            return jsonify(safe_config)
        except Exception as e:
            logger.error(f"获取配置信息失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return jsonify({'error': '获取配置信息失败'}), 500
    
    # 添加健康检查端点
    @app.route('/health')
    def health_check():
        """健康检查端点，不需要认证"""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'service': 'llbot-yunzai-monitor'
        })

    # 配置管理页面
    @app.route('/config')
    @requires_auth
    def config_page():
        """配置管理页面"""
        try:
            # 获取当前配置（脱敏版本）
            safe_config = {}
            for key, value in current_config.items():
                if isinstance(value, dict):
                    safe_config[key] = {}
                    for sub_key, sub_value in value.items():
                        # 对敏感信息进行脱敏处理
                        if sub_key in ['password', 'token', 'secret', 'key', 'auth']:
                            safe_config[key][sub_key] = '***'
                        else:
                            safe_config[key][sub_key] = sub_value
                else:
                    safe_config[key] = value
            
            # 生成配置页面HTML
            config_html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>配置管理 - llbot Yunzai 监控系统</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary-gradient: linear-gradient(45deg, #007bff, #6610f2);
            --success-gradient: linear-gradient(45deg, #28a745, #20c997);
            --danger-gradient: linear-gradient(45deg, #dc3545, #fd7e14);
            --warning-gradient: linear-gradient(45deg, #ffc107, #fd7e14);
            --info-gradient: linear-gradient(45deg, #17a2b8, #6f42c1);
        }
        
        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            padding-top: 20px;
            padding-bottom: 20px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .main-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            margin-bottom: 20px;
        }
        .config-card {
            border-radius: 12px;
            border: none;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            height: 100%;
            background: linear-gradient(145deg, #ffffff, #f8f9fa);
            overflow: hidden;
            margin-bottom: 20px;
        }
        .config-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.2);
        }
        .card-header {
            border-bottom: 1px solid rgba(0,0,0,0.05);
            background: linear-gradient(to right, #f8f9fa, #e9ecef) !important;
            border-radius: 12px 12px 0 0 !important;
            padding: 1.2rem 1.5rem !important;
        }
        .card-body {
            padding: 1.5rem !important;
        }
        .form-control {
            border-radius: 10px;
            padding: 12px 15px;
            border: 2px solid #e9ecef;
            margin-bottom: 15px;
            transition: all 0.3s;
        }
        .form-control:focus {
            border-color: #007bff;
            box-shadow: 0 0 0 0.2rem rgba(0,123,255,0.25);
        }
        .form-label {
            font-weight: 600;
            color: #495057;
            margin-bottom: 8px;
        }
        .form-check-input:checked {
            background-color: #007bff;
            border-color: #007bff;
        }
        .btn-save {
            background: var(--success-gradient);
            border: none;
            border-radius: 10px;
            padding: 12px 24px;
            font-weight: 600;
            font-size: 16px;
            color: white;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .btn-save:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4);
        }
        .btn-cancel {
            background: var(--danger-gradient);
            border: none;
            border-radius: 10px;
            padding: 12px 24px;
            font-weight: 600;
            font-size: 16px;
            color: white;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .btn-cancel:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(220, 53, 69, 0.4);
        }
        .btn-back {
            background: var(--primary-gradient);
            border: none;
            border-radius: 10px;
            padding: 10px 20px;
            font-weight: 500;
            font-size: 14px;
            color: white;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        .btn-back:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 123, 255, 0.4);
        }
        .header-title {
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: 700;
            font-size: 1.8rem;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .section-title {
            font-weight: 600;
            color: #495057;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
        }
        .alert-box {
            border-radius: 12px;
            border: none;
            overflow: hidden;
        }
        .config-icon {
            font-size: 24px;
            margin-right: 12px;
            vertical-align: middle;
            width: 30px;
            text-align: center;
        }
        .nav-tabs {
            border-bottom: 2px solid #e9ecef;
        }
        .nav-tabs .nav-link {
            border: none;
            border-radius: 8px 8px 0 0;
            padding: 12px 20px;
            font-weight: 500;
            color: #6c757d;
            transition: all 0.3s;
        }
        .nav-tabs .nav-link:hover {
            color: #495057;
            background-color: rgba(0, 123, 255, 0.05);
        }
        .nav-tabs .nav-link.active {
            color: #007bff;
            background-color: rgba(0, 123, 255, 0.1);
            border-bottom: 3px solid #007bff;
        }
        
        /* 侧边栏样式 */
        .sidebar {
            position: fixed;
            top: 0;
            left: 0;
            height: 100vh;
            width: 250px;
            background: linear-gradient(180deg, #2c3e50 0%, #1a252f 100%);
            box-shadow: 3px 0 15px rgba(0, 0, 0, 0.2);
            z-index: 1000;
            padding-top: 20px;
            transition: all 0.3s ease;
        }
        
        .sidebar-header {
            padding: 0 20px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 20px;
        }
        
        .sidebar-title {
            color: white;
            font-size: 1.2rem;
            font-weight: 600;
            margin: 0;
        }
        
        .sidebar-nav {
            padding: 0 15px;
        }
        
        .sidebar-item {
            margin-bottom: 8px;
        }
        
        .sidebar-link {
            display: flex;
            align-items: center;
            padding: 12px 15px;
            color: rgba(255, 255, 255, 0.8);
            text-decoration: none;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        
        .sidebar-link:hover {
            background: rgba(255, 255, 255, 0.1);
            color: white;
            transform: translateX(5px);
        }
        
        .sidebar-link.active {
            background: linear-gradient(45deg, #007bff, #6610f2);
            color: white;
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
        }
        
        .sidebar-link i {
            width: 24px;
            margin-right: 12px;
            font-size: 1.1rem;
        }
        
        .sidebar-link span {
            font-weight: 500;
        }
        
        .main-content {
            margin-left: 250px;
            padding: 20px;
            transition: all 0.3s ease;
        }
        
        @media (max-width: 768px) {
            .sidebar {
                width: 70px;
            }
            
            .sidebar-header {
                padding: 0 10px 20px;
            }
            
            .sidebar-title {
                font-size: 0;
            }
            
            .sidebar-title:after {
                content: "☰";
                font-size: 1.5rem;
            }
            
            .sidebar-link span {
                display: none;
            }
            
            .sidebar-link i {
                margin-right: 0;
                font-size: 1.3rem;
            }
            
            .main-content {
                margin-left: 70px;
            }
        }
    </style>
</head>
<body>
    <!-- 侧边栏 -->
    <div class="sidebar">
        <div class="sidebar-header">
            <h2 class="sidebar-title">
                <i class="fas fa-tachometer-alt me-2"></i>监控系统
            </h2>
        </div>
        <nav class="sidebar-nav">
            <div class="sidebar-item">
                <a href="/" class="sidebar-link">
                    <i class="fas fa-home"></i>
                    <span>系统监控</span>
                </a>
            </div>
            <div class="sidebar-item">
                <a href="/config" class="sidebar-link active">
                    <i class="fas fa-cogs"></i>
                    <span>配置管理</span>
                </a>
            </div>
        </nav>
    </div>
    
    <!-- 主内容区域 -->
    <div class="main-content">
        <div class="container-fluid">
            <!-- 顶部标题栏 -->
            <div class="d-flex justify-content-between align-items-center mb-4 px-3">
                <div class="d-flex align-items-center">
                    <h1 class="header-title mb-0 me-3">
                        <i class="fas fa-cogs me-2"></i>配置管理
                    </h1>
                </div>
                <div class="dropdown">
                    <button class="btn btn-outline-primary dropdown-toggle" type="button" id="userMenu" data-bs-toggle="dropdown" aria-expanded="false">
                        <i class="fas fa-user-circle me-1"></i>账户管理
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userMenu">
                        <li><a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#passwordModal"><i class="fas fa-key me-2"></i>修改密码</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item text-danger" href="/logout"><i class="fas fa-sign-out-alt me-2"></i>退出登录</a></li>
                    </ul>
                </div>
            </div>

            <div class="main-container p-4">
            <!-- 配置表单 -->
            <div id="configAlert" class="alert alert-info alert-box mb-4" style="display: none;">
                <i class="fas fa-info-circle me-2"></i>
                <span id="configAlertMessage"></span>
            </div>

            <!-- 配置选项卡 -->
            <ul class="nav nav-tabs mb-4" id="configTabs" role="tablist">
                <li class="nav-item" role="presentation">
                    <button class="nav-link active" id="llbot-tab" data-bs-toggle="tab" data-bs-target="#llbot" type="button" role="tab">
                        <i class="fas fa-robot config-icon"></i>llbot 配置
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="yunzai-tab" data-bs-toggle="tab" data-bs-target="#yunzai" type="button" role="tab">
                        <i class="fas fa-server config-icon"></i>Yunzai 配置
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="redis-tab" data-bs-toggle="tab" data-bs-target="#redis" type="button" role="tab">
                        <i class="fas fa-database config-icon"></i>Redis 配置
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="http-tab" data-bs-toggle="tab" data-bs-target="#http" type="button" role="tab">
                        <i class="fas fa-plug config-icon"></i>HTTP 检查配置
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="auto-tab" data-bs-toggle="tab" data-bs-target="#auto" type="button" role="tab">
                        <i class="fas fa-redo config-icon"></i>自动重启配置
                    </button>
                </li>
                <li class="nav-item" role="presentation">
                    <button class="nav-link" id="auth-tab" data-bs-toggle="tab" data-bs-target="#auth" type="button" role="tab">
                        <i class="fas fa-lock config-icon"></i>Web 认证配置
                    </button>
                </li>
            </ul>

            <div class="tab-content" id="configTabsContent">
                <!-- llbot 配置 -->
                <div class="tab-pane fade show active" id="llbot" role="tabpanel">
                    <div class="config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-robot me-2 text-primary"></i>llbot 进程配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="llbot-path" class="form-label">llbot 可执行文件路径</label>
                                <input type="text" class="form-control" id="llbot-path" 
                                       placeholder="例如: C:\\path\\to\\llbot.exe 或 python main.py"
                                       value="''' + str(safe_config.get('llbot', {}).get('path', '')) + '''">
                                <div class="form-text">llbot 可执行文件的完整路径，可以是 .exe 文件或 Python 脚本</div>
                            </div>
                            <div class="mb-3">
                                <label for="llbot-directory" class="form-label">工作目录</label>
                                <input type="text" class="form-control" id="llbot-directory" 
                                       placeholder="例如: C:\\path\\to\\llbot\\directory"
                                       value="''' + str(safe_config.get('llbot', {}).get('directory', '')) + '''">
                                <div class="form-text">llbot 进程运行的工作目录，通常与可执行文件所在目录相同</div>
                            </div>
                            <div class="mb-3">
                                <label for="llbot-wait-seconds" class="form-label">等待时间（秒）</label>
                                <input type="number" class="form-control" id="llbot-wait-seconds" 
                                       min="1" max="60" step="1" value="''' + str(safe_config.get('llbot', {}).get('wait_seconds', 5)) + '''">
                                <div class="form-text">启动/停止 llbot 后的等待时间，建议 3-10 秒</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Yunzai 配置 -->
                <div class="tab-pane fade" id="yunzai" role="tabpanel">
                    <div class="config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-server me-2 text-success"></i>Yunzai 进程配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="yunzai-git-bash-path" class="form-label">Git Bash 路径</label>
                                <input type="text" class="form-control" id="yunzai-git-bash-path" 
                                       placeholder="例如: C:\\Program Files\\Git\\bin\\bash.exe"
                                       value="''' + str(safe_config.get('yunzai', {}).get('git_bash_path', '')) + '''">
                                <div class="form-text">Git Bash 可执行文件的完整路径，用于运行 Yunzai</div>
                            </div>
                            <div class="mb-3">
                                <label for="yunzai-bash-directory" class="form-label">Yunzai 工作目录</label>
                                <input type="text" class="form-control" id="yunzai-bash-directory" 
                                       placeholder="例如: C:\\path\\to\\yunzai-bot"
                                       value="''' + str(safe_config.get('yunzai', {}).get('bash_directory', '')) + '''">
                                <div class="form-text">Yunzai 项目的工作目录，Git Bash 将在此目录下运行</div>
                            </div>
                            <div class="mb-3">
                                <label for="yunzai-wait-seconds" class="form-label">等待时间（秒）</label>
                                <input type="number" class="form-control" id="yunzai-wait-seconds" 
                                       min="1" max="60" step="1" value="''' + str(safe_config.get('yunzai', {}).get('wait_seconds', 5)) + '''">
                                <div class="form-text">启动/停止 Yunzai 后的等待时间，建议 3-10 秒</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Redis 配置 -->
                <div class="tab-pane fade" id="redis" role="tabpanel">
                    <div class="config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-database me-2 text-warning"></i>Redis 进程配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="redis-path" class="form-label">Redis 可执行文件路径</label>
                                <input type="text" class="form-control" id="redis-path" 
                                       placeholder="例如: C:\\path\\to\\redis-server.exe"
                                       value="''' + str(safe_config.get('redis', {}).get('path', '')) + '''">
                                <div class="form-text">Redis 服务器可执行文件的完整路径</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- HTTP 检查配置 -->
                <div class="tab-pane fade" id="http" role="tabpanel">
                    <div class="config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-plug me-2 text-warning"></i>HTTP 检查配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="http-url" class="form-label">检查 URL</label>
                                <input type="text" class="form-control" id="http-url" 
                                       placeholder="例如: http://localhost:3000 或 https://api.example.com/health"
                                       value="''' + str(safe_config.get('http_check', {}).get('url', '')) + '''">
                                <div class="form-text">用于健康检查的 HTTP URL，应以 http:// 或 https:// 开头</div>
                            </div>
                            <div class="mb-3">
                                <label for="http-timeout" class="form-label">超时时间（秒）</label>
                                <input type="number" class="form-control" id="http-timeout" 
                                       min="1" max="30" step="1" value="''' + str(safe_config.get('http_check', {}).get('timeout', 5)) + '''">
                                <div class="form-text">HTTP 请求超时时间，建议 3-10 秒</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 自动重启配置 -->
                <div class="tab-pane fade" id="auto" role="tabpanel">
                    <div class="config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-redo me-2 text-info"></i>自动重启配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <div class="form-check form-switch">
                                    <input class="form-check-input" type="checkbox" id="auto-restart-enabled" 
                                           ''' + ('checked' if safe_config.get('auto_restart', {}).get('enabled', True) else '') + '''>
                                    <label class="form-check-label" for="auto-restart-enabled">启用自动重启</label>
                                </div>
                                <div class="form-text">当进程异常退出时自动重启</div>
                            </div>
                            <div class="mb-3">
                                <div class="form-check form-switch">
                                    <input class="form-check-input" type="checkbox" id="respect-manual-stop" 
                                           ''' + ('checked' if safe_config.get('auto_restart', {}).get('respect_manual_stop', True) else '') + '''>
                                    <label class="form-check-label" for="respect-manual-stop">尊重手动停止</label>
                                </div>
                                <div class="form-text">如果手动停止了进程，则不自动重启</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Web 认证配置 -->
                <div class="tab-pane fade" id="auth" role="tabpanel">
                    <div class="config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-lock me-2 text-danger"></i>Web 管理界面认证配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="auth-username" class="form-label">用户名</label>
                                <input type="text" class="form-control" id="auth-username" 
                                       value="''' + str(safe_config.get('web_auth', {}).get('username', 'admin')) + '''">
                                <div class="form-text">登录 Web 管理界面的用户名</div>
                            </div>
                            <div class="mb-3">
                                <label for="auth-password" class="form-label">密码</label>
                                <input type="password" class="form-control" id="auth-password" 
                                       value="''' + str(safe_config.get('web_auth', {}).get('password', '***')) + '''">
                                <div class="form-text">登录 Web 管理界面的密码（显示为 *** 表示已设置）</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 操作按钮 -->
            <div class="d-flex justify-content-between mt-4">
                <div>
                    <button class="btn btn-cancel me-2" onclick="resetForm()">
                        <i class="fas fa-undo me-2"></i>重置
                    </button>
                </div>
                <div>
                    <button class="btn btn-outline-secondary me-2" onclick="window.location.href='/'">
                        <i class="fas fa-times me-2"></i>返回监控
                    </button>
                    <button class="btn btn-save" onclick="saveConfig()">
                        <i class="fas fa-save me-2"></i>保存配置
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 显示提示信息
        function showAlert(message, type = 'info') {
            const alertDiv = document.getElementById('configAlert');
            const alertMessage = document.getElementById('configAlertMessage');
            
            alertDiv.className = `alert alert-${type} alert-box`;
            alertMessage.textContent = message;
            alertDiv.style.display = 'block';
            
            // 5秒后自动隐藏
            setTimeout(() => {
                alertDiv.style.display = 'none';
            }, 5000);
        }

        // 重置表单
        function resetForm() {
            if (confirm('确定要重置所有配置吗？未保存的更改将会丢失。')) {
                window.location.reload();
            }
        }

        // 保存配置
        async function saveConfig() {
            try {
                // 收集配置数据
                const configData = {
                    llbot: {
                        path: document.getElementById('llbot-path').value.trim(),
                        directory: document.getElementById('llbot-directory').value.trim(),
                        wait_seconds: parseInt(document.getElementById('llbot-wait-seconds').value) || 5
                    },
                    yunzai: {
                        git_bash_path: document.getElementById('yunzai-git-bash-path').value.trim(),
                        bash_directory: document.getElementById('yunzai-bash-directory').value.trim(),
                        wait_seconds: parseInt(document.getElementById('yunzai-wait-seconds').value) || 5
                    },
                    redis: {
                        path: document.getElementById('redis-path').value.trim()
                    },
                    http_check: {
                        url: document.getElementById('http-url').value.trim(),
                        timeout: parseInt(document.getElementById('http-timeout').value) || 5
                    },
                    auto_restart: {
                        enabled: document.getElementById('auto-restart-enabled').checked,
                        respect_manual_stop: document.getElementById('respect-manual-stop').checked
                    },
                    web_auth: {
                        username: document.getElementById('auth-username').value.trim() || 'admin',
                        password: document.getElementById('auth-password').value
                    }
                };

                // 验证配置
                if (!configData.llbot.path) {
                    showAlert('llbot 可执行文件路径不能为空', 'warning');
                    return;
                }
                if (!configData.llbot.directory) {
                    showAlert('llbot 工作目录不能为空', 'warning');
                    return;
                }
                if (configData.llbot.wait_seconds < 1 || configData.llbot.wait_seconds > 60) {
                    showAlert('llbot 等待时间必须在 1-60 秒之间', 'warning');
                    return;
                }
                
                if (!configData.yunzai.git_bash_path) {
                    showAlert('Git Bash 路径不能为空', 'warning');
                    return;
                }
                if (!configData.yunzai.bash_directory) {
                    showAlert('Yunzai 工作目录不能为空', 'warning');
                    return;
                }
                if (configData.yunzai.wait_seconds < 1 || configData.yunzai.wait_seconds > 60) {
                    showAlert('Yunzai 等待时间必须在 1-60 秒之间', 'warning');
                    return;
                }
                
                if (!configData.redis.path) {
                    showAlert('Redis 可执行文件路径不能为空', 'warning');
                    return;
                }
                
                if (configData.http_check.url && !configData.http_check.url.startsWith('http://') && !configData.http_check.url.startsWith('https://')) {
                    showAlert('HTTP 检查 URL 应以 http:// 或 https:// 开头', 'warning');
                    return;
                }
                if (configData.http_check.timeout < 1 || configData.http_check.timeout > 30) {
                    showAlert('HTTP 超时时间必须在 1-30 秒之间', 'warning');
                    return;
                }
                
                if (!configData.web_auth.username) {
                    showAlert('用户名不能为空', 'warning');
                    return;
                }
                // 验证密码字段 - only check if the user provided a new password
                if (configData.web_auth.password && configData.web_auth.password !== '***') {
                    // User entered a new password, validate it
                    if (configData.web_auth.password.length < 4) {
                        showAlert('密码长度至少为4位', 'warning');
                        return;
                    }
                } else {
                    // Password field shows '***' (unchanged), so we'll remove it from the payload to indicate "keep existing"
                    delete configData.web_auth.password;
                }

                // 发送保存请求
                const response = await fetch('/api/config/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(configData)
                });

                const result = await response.json();

                if (response.ok) {
                    showAlert('配置保存成功！配置已热重载生效。', 'success');
                    // 更新密码字段显示
                    document.getElementById('auth-password').value = '***';
                } else {
                    showAlert('保存失败：' + (result.error || '未知错误'), 'danger');
                }
            } catch (error) {
                console.error('保存配置失败:', error);
                showAlert('保存失败：网络错误或服务器异常', 'danger');
            }
        }



        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', function() {
            // 激活第一个选项卡
            const firstTab = document.querySelector('#configTabs .nav-link');
            if (firstTab) {
                firstTab.click();
            }
        });
    </script>
</body>
</html>
            '''
            return render_template_string(config_html)
        except Exception as e:
            logger.error(f"加载配置页面失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return render_template_string(get_login_template("加载配置页面失败，请重试。")), 500

    # 配置更新API
    @app.route('/api/config/update', methods=['POST'])
    @requires_auth
    def api_config_update():
        """更新配置信息"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': '无效的JSON数据'}), 400

            # 验证配置数据
            required_sections = ['llbot', 'yunzai', 'http_check', 'auto_restart', 'web_auth']
            for section in required_sections:
                if section not in data:
                    return jsonify({'error': f'缺少配置项: {section}'}), 400

            # 验证具体配置值
            if not isinstance(data['llbot'].get('wait_seconds'), (int, float)) or data['llbot']['wait_seconds'] < 1:
                return jsonify({'error': 'llbot等待时间必须大于0'}), 400
            if not isinstance(data['yunzai'].get('wait_seconds'), (int, float)) or data['yunzai']['wait_seconds'] < 1:
                return jsonify({'error': 'yunzai等待时间必须大于0'}), 400
            if not isinstance(data['http_check'].get('timeout'), (int, float)) or data['http_check']['timeout'] < 1:
                return jsonify({'error': 'HTTP超时时间必须大于0'}), 400
            if not isinstance(data['auto_restart'].get('enabled'), bool):
                return jsonify({'error': '自动重启启用状态必须是布尔值'}), 400
            if not isinstance(data['auto_restart'].get('respect_manual_stop'), bool):
                return jsonify({'error': '尊重手动停止状态必须是布尔值'}), 400
            # Only validate username if it's provided in the request (meaning user wants to change it)
            # If username is not provided, we'll keep the existing username
            if 'username' in data['web_auth'] and not data['web_auth'].get('username'):
                return jsonify({'error': '用户名不能为空'}), 400
            
            # First, save the original password in case we need to restore it
            original_password = current_config.get('web_auth', {}).get('password', 'admin123')
            
            # Process username field
            if 'username' in data['web_auth'] and not data['web_auth'].get('username'):
                return jsonify({'error': '用户名不能为空'}), 400

            # Process password field
            if 'password' in data['web_auth']:
                password_value = data['web_auth'].get('password', '')
                # If password is the placeholder '***', restore the original password value
                if password_value == '***':
                    data['web_auth']['password'] = original_password
                elif not password_value:
                    # If password is explicitly empty, validate
                    return jsonify({'error': '密码不能为空'}), 400
            else:
                # If password is not provided, use the original password
                data['web_auth']['password'] = original_password

            # If username is not provided in the update, preserve the existing username
            if 'username' not in data['web_auth'] or data['web_auth']['username'] is None or data['web_auth']['username'] == '':
                existing_username = current_config.get('web_auth', {}).get('username', 'admin')
                data['web_auth']['username'] = existing_username

            # 更新当前配置
            current_config.update(data)
            
            # 保存配置到文件
            try:
                save_config(current_config, "config.yaml")
                logger.info("配置已更新", extra={
                    'event_type': 'config_update',
                    'action': 'full_config_update'
                })
                
                # 立即重新加载配置以应用新设置
                try:
                    # 重新加载配置以确保所有更改生效
                    new_config = load_config()
                    current_config.clear()
                    current_config.update(new_config)
                    
                    logger.info("配置热重载完成", extra={
                        'event_type': 'config_reload',
                        'action': 'hot_reload_after_update'
                    })
                    
                    return jsonify({'message': '配置更新成功并已热重载'})
                except Exception as reload_error:
                    logger.error(f"配置热重载失败: {str(reload_error)}", extra={
                        'event_type': EventType.ERROR,
                        'error': str(reload_error),
                        'action': 'config_reload_failure_after_update'
                    })
                    return jsonify({'message': '配置更新成功，但热重载失败，请重启程序以应用完整配置'})
            except Exception as e:
                logger.error(f"保存配置失败: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'error': str(e),
                    'action': 'config_save_failure'
                })
                return jsonify({'error': f'保存配置失败: {str(e)}'}), 500
                
        except Exception as e:
            logger.error(f"更新配置失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'action': 'config_update_failure'
            })
            return jsonify({'error': f'更新配置失败: {str(e)}'}), 500

    # 配置热重载API


    def start_web_server(host='127.0.0.1', port=5000):
        """启动Web服务器"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Web管理界面启动在 http://{host}:{port}")
        logger.info(f"Web管理界面启动", extra={
            'event_type': 'web_server',
            'action': 'started',
            'address': f'http://{host}:{port}'
        })
        
        # 使用Flask内置服务器
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
            # 增强匹配逻辑：支持带/不带 .exe，以及部分匹配（例如 QQ -> QQ.exe、qqprotect.exe 等）
            proc_name = (proc.info['name'] or '').lower()
            target_name = (process_name or '').lower()
            matched = False
            if proc_name == target_name or proc_name == f"{target_name}.exe":
                matched = True
            elif target_name in proc_name:
                matched = True

            if matched:
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
            # 如果未找到明确的进程，但在 Windows 上可能存在带有不同命名或被保护的进程，尝试使用 taskkill 作为兜底
            try:
                # 使用 /F 强制结束，/T 同时终止子进程。使用模糊匹配时添加通配符
                pattern = process_name if process_name.lower().endswith('.exe') else f"{process_name}*.exe"
                taskkill_cmd = ["taskkill", "/F", "/IM", pattern, "/T"]
                result = subprocess.run(taskkill_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"taskkill 成功终止: {pattern}", extra={'event_type': EventType.PROCESS_STOP, 'pattern': pattern})
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] taskkill 成功终止: {pattern}")
                else:
                    logger.debug(f"taskkill 未找到或终止失败: {pattern} - {result.stderr}", extra={'event_type': EventType.DEBUG})
            except Exception as tk_e:
                logger.error(f"使用 taskkill 终止 {process_name} 时出错: {str(tk_e)}", extra={'event_type': EventType.ERROR, 'error': str(tk_e)})
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

def is_qq_running():
    """
    检测QQ进程是否在运行
    返回: bool - True表示QQ正在运行，False表示QQ已停止
    """
    try:
        qq_process_names = ["QQ", "QQ.exe", "QQProtect.exe", "QQPCRTP.exe", "TXPlatform.exe"]
        found_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                proc_name = (proc.info['name'] or '').lower()
                for qq_name in qq_process_names:
                    if qq_name.lower() in proc_name:
                        found_processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'create_time': proc.info['create_time']
                        })
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if found_processes:
            logger.debug(f"检测到QQ进程正在运行: {len(found_processes)}个进程", extra={
                'event_type': 'debug',
                'qq_processes': found_processes,
                'count': len(found_processes)
            })
            return True
        else:
            logger.debug("未检测到QQ进程", extra={
                'event_type': 'debug',
                'qq_processes': []
            })
            return False
            
    except Exception as e:
        logger.error(f"检测QQ进程时出错: {str(e)}", extra={
            'event_type': 'error',
            'error': str(e),
            'error_class': type(e).__name__
        })
        return False

def async_http_check(url, timeout=5):
    """使用线程池的HTTP检查函数（非阻塞）"""
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

# 异步HTTP检查函数已移除，使用同步版本async_http_check

def check_and_manage_llbot_async(config):
    """异步检查并管理llbot进程"""
    try:
        # QQ状态检测 - 检查QQ是否停止运行
        # 使用函数属性来保存上一次的QQ状态，避免使用全局变量
        if not hasattr(check_and_manage_llbot_async, 'last_qq_status'):
            check_and_manage_llbot_async.last_qq_status = None
        
        current_qq_status = is_qq_running()
        
        # 如果QQ状态发生变化（从运行到停止）
        if check_and_manage_llbot_async.last_qq_status is True and current_qq_status is False:
            logger.warning("检测到QQ已停止运行，准备终止llbot相关进程并重启", extra={
                'event_type': EventType.WARNING,
                'qq_status_change': 'running_to_stopped',
                'action': 'terminate_and_restart_llbot'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到QQ已停止运行，准备终止llbot相关进程并重启...")
            
            # 终止llbot相关进程
            llbot_process_name = os.path.basename(config['llbot']['path']) if config.get('llbot', {}).get('path') else 'llbot.exe'
            terminate_process_by_name(llbot_process_name)
            terminate_process_by_name('lucky-lillia-desktop.exe')
            terminate_process_by_name('pmhq-win-x64.exe')
            terminate_process_by_name('flet.exe')
            
            # 清除手动停止状态
            try:
                update_global_manual_stop_status('llbot', False)
            except:
                pass
            
            # 重启llbot
            restart_llbot(config)
            
            # 更新QQ状态
            check_and_manage_llbot_async.last_qq_status = current_qq_status
            return  # 完成重启后返回，跳过本次的HTTP检查
        
        # 更新QQ状态记录
        check_and_manage_llbot_async.last_qq_status = current_qq_status
        
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
                # 使用全局current_config以确保获取最新的配置
                local_config = current_config
                
                # 检查llbot进程状态
                if local_config['llbot'].get('path'):
                    llbot_process_name = os.path.basename(local_config['llbot']['path']).lower()
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
                if local_config['redis'].get('path'):
                    redis_process_name = os.path.basename(local_config['redis']['path']).lower()
                    
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
                if local_config.get('http_check', {}).get('url'):
                    try:
                        is_accessible = async_http_check(local_config['http_check']['url'], local_config['http_check'].get('timeout', 5))
                        current_status['http_check'] = {'accessible': is_accessible, 'configured': True}
                    except:
                        current_status['http_check'] = {'accessible': False, 'configured': True}
                else:
                    current_status['http_check'] = {'accessible': False, 'configured': False}
                
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
                # 使用全局current_config以确保获取最新的配置
                local_config = current_config
                check_and_manage_llbot_async(local_config)
                time.sleep(local_config['llbot']['wait_seconds'])
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
                # 使用全局current_config以确保获取最新的配置
                local_config = current_config
                check_and_manage_yunzai_async(local_config)
                time.sleep(local_config['yunzai']['wait_seconds'])
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
