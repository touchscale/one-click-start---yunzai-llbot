# -*- coding: utf-8 -*-
"""
Web服务器模块 - 提供Web管理界面
"""
import logging
import threading
import os
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

# Web界面相关 - 只使用Flask
try:
    from flask import Flask as Quart, render_template, jsonify, request, session, redirect, Response
    import secrets
    flask_available = True
    print("使用Flask作为Web框架")
except ImportError:
    flask_available = False
    print("错误: Flask未安装，Web管理界面功能不可用。请运行 'pip install Flask' 安装。")

# 全局变量
app = None
current_config = {}
current_status = {
    'llbot': {'running': False, 'pid': None},
    'yunzai': {'running': False, 'pid': None},
    'redis': {'running': False, 'pid': None},
    'http_check': {'accessible': False, 'configured': False}
}

# 手动停止状态跟踪 - 记录通过Web界面手动停止的进程
manual_stop_status = {
    'llbot': False,
    'yunzai': False,
    'redis': False
}

# 存储最近的日志 - 使用线程安全的列表
recent_logs = []
recent_logs_lock = threading.Lock()

# 线程池用于异步执行耗时操作
_executor = ThreadPoolExecutor(max_workers=8)

# 操作锁，防止并发操作同一进程
_process_locks = {
    'llbot': threading.Lock(),
    'yunzai': threading.Lock(),
    'redis': threading.Lock()
}

# 配置操作锁，防止并发读写配置
_config_lock = threading.Lock()

# 更新操作锁，防止并发执行更新
_update_lock = threading.Lock()

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

def init_web_server(config, status):
    """初始化Web服务器"""
    global app, current_config, current_status
    current_config = config
    current_status = status
    
    if not flask_available:
        return None
    
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    webui_dir = os.path.join(current_dir, 'webui')
    
    # 创建Flask应用，设置模板和静态文件夹路径
    app = Quart(__name__, 
                template_folder=os.path.join(webui_dir, 'templates'),
                static_folder=os.path.join(webui_dir, 'static'))
    # 设置会话密钥
    app.secret_key = secrets.token_hex(16)
    
    # 添加Web日志处理器
    from logger import get_logger
    logger = get_logger()
    web_log_handler = WebLogHandler()
    import logging
    web_log_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d - %(message)s'))
    logging.getLogger().addHandler(web_log_handler)
    
    # 注册路由
    register_routes(app)
    
    return app

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

def get_web_auth_config():
    """获取Web认证配置，如果不存在则返回默认值"""
    auth_config = current_config.get('web_auth', {})
    return {
        'username': auth_config.get('username', 'admin'),
        'password': auth_config.get('password', 'admin123')
    }

def register_routes(app):
    """注册所有路由"""
    from constants import EventType
    from logger import get_logger
    from config import save_config
    from process_manager import (
        restart_llbot_with_cleanup, 
        terminate_process_by_name,
        update_global_manual_stop_status
    )
    from monitor import check_and_manage_yunzai_async, async_http_check
    from password_validator import PasswordValidator
    
    logger = get_logger()
    
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
        return render_template("login.html", error_msg="服务器内部错误，已记录。", username_hint=get_web_auth_config().get("username", "admin")), 500

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
            return render_template("login.html", error_msg="内部错误，已记录。", username_hint=get_web_auth_config().get("username", "admin")), 500
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
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.bootcdn.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.bootcdn.net https://cdnjs.cloudflare.com; font-src 'self' https://cdnjs.cloudflare.com https://cdn.bootcdn.net; img-src 'self' data: https:; connect-src 'self' https://cdn.bootcdn.net https://cdnjs.cloudflare.com; manifest-src 'self';"
        
        # 为静态资源添加缓存控制头
        if request.path.startswith('/static/'):
            # JavaScript 和 CSS 文件不缓存，确保用户总是获取最新版本
            if request.path.endswith('.js') or request.path.endswith('.css'):
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
            # 其他静态资源（如字体、图片）可以缓存较长时间
            else:
                response.headers['Cache-Control'] = 'public, max-age=86400'
        
        return response
        
    @app.before_request
    def before_request():
        """请求前处理：安全检查和输入验证"""
        # 允许访问登录页面、健康检查、监控停止页面和静态文件
        if request.endpoint in ['login', 'static_files', 'health_check', 'monitor_stopped', 'api_monitor_status', 'api_monitor_status_file'] or request.path.startswith('/static/') or request.path.startswith('/api/change-password') or request.path.startswith('/api/reset-password') or request.path.startswith('/api/monitor-status') or request.path.startswith('/api/monitor-status-file'):
            return

        # 检查认证状态（对于非登录页面）
        if request.endpoint != 'login' and 'logged_in' not in session and not request.path.startswith('/api/'):
            return redirect('/login')

        # 对于API请求，检查认证（排除无需认证的端点）
        if request.path.startswith('/api/') and request.endpoint not in ['login', 'api_change_password', 'api_reset_password', 'health_check', 'api_monitor_status', 'api_monitor_status_file']:
            if 'logged_in' not in session:
                if request.is_json:
                    return jsonify({'error': '未认证'}), 401
                else:
                    return redirect('/login')

        # 检查监控脚本运行状态，如果未运行则重定向到监控停止页面
        # 但如果是登录页面或已经是监控停止页面，则不重定向
        if request.endpoint != 'login' and request.endpoint != 'monitor_stopped':
            try:
                from monitor_status import is_monitor_running
                if not is_monitor_running():
                    return redirect('/monitor-stopped')
            except Exception as e:
                logger.warning(f"检查监控状态失败: {str(e)}")
            
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
    
    @app.route('/')
    def index():
        """主页"""
        if 'logged_in' not in session:
            return redirect('/login')
        try:
            return render_template("dashboard.html")
        except Exception as e:
            logger.error(f"加载主页失败: {str(e)}", extra={'event_type': EventType.ERROR, 'error': str(e)})
            return render_template("login.html", error_msg="加载主页失败，请重试。", username_hint=get_web_auth_config().get("username", "admin")), 500

    @app.route('/api/status')
    @requires_auth
    def api_status():
        """获取状态API"""
        return jsonify(current_status)

    @app.route('/api/logs')
    @requires_auth
    def api_logs():
        """获取日志API，支持按等级过滤"""
        # 获取查询参数中的日志等级
        levels = request.args.getlist('levels')

        # 如果没有指定等级或包含'all'，返回所有日志
        if not levels or 'all' in levels:
            return jsonify({'logs': recent_logs})

        # 过滤指定等级的日志
        filtered_logs = []
        with recent_logs_lock:
            for log in recent_logs:
                log_level = log.get('level', '').lower()
                if log_level in [level.lower() for level in levels]:
                    filtered_logs.append(log)

        return jsonify({'logs': filtered_logs})

    @app.route('/api/clear-logs', methods=['POST'])
    @requires_auth
    def api_clear_logs():
        """清空日志API"""
        global recent_logs
        with recent_logs_lock:
            recent_logs.clear()
        logger.info("通过Web界面清空日志", extra={
            'event_type': EventType.LOG_CLEAR
        })
        return jsonify({'message': '日志已清空'})

    @app.route('/api/control', methods=['POST'])
    @requires_auth
    def api_control():
        """控制进程API - 使用异步处理避免阻塞"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'message': '无效的JSON数据'}), 400
            
            process = data.get('process')
            action = data.get('action')
            
            if not process or not action:
                return jsonify({'message': '缺少process或action参数'}), 400
            
            # 检查该进程是否已有操作在进行
            if process in _process_locks:
                if not _process_locks[process].acquire(blocking=False):
                    return jsonify({'message': f'{process} 正在执行操作，请稍后再试'}), 429
            else:
                return jsonify({'message': f'未知进程: {process}'}), 400
            
            try:
                # 记录操作开始时间
                logger.info(f"Web界面请求: {process} {action}", extra={
                    'event_type': EventType.INFO,
                    'action': 'api_control_received',
                    'target_process': process,
                    'source': 'web_interface'
                })
                
                # 立即返回成功，让客户端知道请求已被接受
                return jsonify({'message': f'{process} {action} 请求已接收，正在处理...'}), 202
            finally:
                # 在新线程中执行实际操作
                def execute_operation():
                    try:
                        if process == 'llbot':
                            if action == 'start':
                                restart_llbot_with_cleanup(current_config)
                                manual_stop_status['llbot'] = False
                                try:
                                    update_global_manual_stop_status('llbot', False)
                                except:
                                    pass
                                logger.info(f"通过Web界面启动llbot", extra={
                                    'event_type': EventType.PROCESS_START,
                                    'target_process': 'llbot',
                                    'source': 'web_interface',
                                    'action': 'start'
                                })
                            elif action == 'stop':
                                from process_manager import terminate_llbot_process_tree
                                terminate_llbot_process_tree(current_config.get('llbot', {}).get('path'))
                                manual_stop_status['llbot'] = True
                                try:
                                    update_global_manual_stop_status('llbot', True)
                                except:
                                    pass
                                logger.info(f"通过Web界面停止llbot", extra={
                                    'event_type': EventType.PROCESS_STOP,
                                    'target_process': 'llbot',
                                    'source': 'web_interface',
                                    'action': 'stop'
                                })
                        elif process == 'yunzai':
                            if action == 'start':
                                check_and_manage_yunzai_async(current_config)
                                manual_stop_status['yunzai'] = False
                                try:
                                    update_global_manual_stop_status('yunzai', False)
                                except:
                                    pass
                                logger.info(f"通过Web界面启动yunzai", extra={
                                    'event_type': EventType.PROCESS_START,
                                    'target_process': 'yunzai',
                                    'source': 'web_interface',
                                    'action': 'start'
                                })
                            elif action == 'stop':
                                from process_manager import terminate_yunzai_git_bash_process
                                terminate_yunzai_git_bash_process()
                                manual_stop_status['yunzai'] = True
                                try:
                                    update_global_manual_stop_status('yunzai', True)
                                except:
                                    pass
                                logger.info(f"通过Web界面停止yunzai", extra={
                                    'event_type': EventType.PROCESS_STOP,
                                    'target_process': 'yunzai',
                                    'source': 'web_interface',
                                    'action': 'stop'
                                })
                        elif process == 'redis':
                            if action == 'start':
                                check_and_manage_yunzai_async(current_config)
                                manual_stop_status['redis'] = False
                                try:
                                    update_global_manual_stop_status('redis', False)
                                except:
                                    pass
                                logger.info(f"通过Web界面启动redis", extra={
                                    'event_type': EventType.PROCESS_START,
                                    'target_process': 'redis',
                                    'source': 'web_interface',
                                    'action': 'start'
                                })
                            elif action == 'stop':
                                terminate_process_by_name(os.path.basename(current_config['redis']['path']) if current_config.get('redis', {}).get('path') else 'redis-server.exe')
                                manual_stop_status['redis'] = True
                                try:
                                    update_global_manual_stop_status('redis', True)
                                except:
                                    pass
                                logger.info(f"通过Web界面停止redis", extra={
                                    'event_type': EventType.PROCESS_STOP,
                                    'target_process': 'redis',
                                    'source': 'web_interface',
                                    'action': 'stop'
                                })
                    except Exception as inner_e:
                        logger.error(f"执行{process} {action}操作时失败: {str(inner_e)}", extra={
                            'event_type': EventType.ERROR,
                            'target_process': process,
                            'action': action,
                            'error': str(inner_e)
                        })
                    finally:
                        # 释放锁
                        if process in _process_locks:
                            _process_locks[process].release()
                
                _executor.submit(execute_operation)
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
                return jsonify({'message': f"HTTP检查完成，结果: {'成功' if result else '失败'}"})
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
                    return render_template("login.html", error_msg="请输入用户名和密码", username_hint=get_web_auth_config().get("username", "admin"))

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
                    return render_template("login.html", error_msg="用户名或密码错误", username_hint=get_web_auth_config().get("username", "admin"))
            else:
                return render_template("login.html", username_hint=get_web_auth_config().get("username", "admin"))
        except Exception as e:
            import traceback as _tb
            tb = _tb.format_exc()
            logger.error(f"登录页面渲染或处理失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'traceback': tb
            })
            # 返回用户友好的错误页面
            return render_template("login.html", error_msg="内部错误，已记录。", username_hint=get_web_auth_config().get("username", "admin")), 500

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
            
            # 验证新密码强度
            is_valid, errors = PasswordValidator.validate(new_password)
            if not is_valid:
                return jsonify({'message': '密码不符合安全要求', 'errors': errors}), 400
            
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
            
            # 验证新密码强度
            is_valid, errors = PasswordValidator.validate(new_password)
            if not is_valid:
                return jsonify({'message': '密码不符合安全要求', 'errors': errors}), 400
            
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
        # Flask 会自动处理静态文件请求，这个路由主要用于认证检查
        # 如果需要认证才能访问静态文件，可以在这里添加检查
        return app.send_static_file(filename)
    
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

            # 确保 auto_login 配置项存在
            if 'auto_login' not in safe_config:
                safe_config['auto_login'] = {
                    'enabled': False,
                    'username': '',
                    'password': '***'
                }
            else:
                # 确保 auto_login 的所有子字段都存在
                if 'enabled' not in safe_config['auto_login']:
                    safe_config['auto_login']['enabled'] = False
                if 'username' not in safe_config['auto_login']:
                    safe_config['auto_login']['username'] = ''
                if 'password' not in safe_config['auto_login']:
                    safe_config['auto_login']['password'] = '***'

            # 确保 git_update 配置项存在
            if 'git_update' not in safe_config:
                safe_config['git_update'] = {
                    'enabled': False,
                    'check_interval': 3600,
                    'auto_pull': False,
                    'auto_restart': False
                }
            else:
                # 确保 git_update 的所有子字段都存在
                if 'enabled' not in safe_config['git_update']:
                    safe_config['git_update']['enabled'] = False
                if 'check_interval' not in safe_config['git_update']:
                    safe_config['git_update']['check_interval'] = 3600
                if 'auto_pull' not in safe_config['git_update']:
                    safe_config['git_update']['auto_pull'] = False
                if 'auto_restart' not in safe_config['git_update']:
                    safe_config['git_update']['auto_restart'] = False

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
    
    # 添加监控脚本状态检查端点
    @app.route('/api/monitor-status')
    def api_monitor_status():
        """检查监控脚本运行状态，不需要认证"""
        try:
            # 使用 monitor_status 模块获取状态
            from monitor_status import is_monitor_running, load_monitor_status

            # 获取当前运行状态
            monitor_status = is_monitor_running()

            # 从文件加载详细状态信息
            file_status = load_monitor_status()

            return jsonify({
                'monitor_running': monitor_status,
                'last_update': file_status.get('last_update'),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"检查监控状态失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return jsonify({
                'monitor_running': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }), 500
    
    # 监控脚本停止提示页面
    @app.route('/monitor-stopped')
    def monitor_stopped():
        """显示监控脚本停止的提示页面"""
        try:
            return render_template("monitor_stopped.html")
        except Exception as e:
            logger.error(f"加载监控停止页面失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            # 如果模板不存在，返回简单的HTML页面
            return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>监控脚本已停止</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        }
        h1 {
            font-size: 2.5em;
            margin-bottom: 20px;
        }
        p {
            font-size: 1.2em;
            margin-bottom: 30px;
        }
        .spinner {
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-top: 4px solid white;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="spinner"></div>
        <h1>监控脚本已停止</h1>
        <p>检测到监控脚本已停止运行，正在等待恢复...</p>
        <p id="status">正在检查监控脚本状态...</p>
    </div>
    <script>
        function checkMonitorStatus() {
            fetch('/api/monitor-status')
                .then(response => response.json())
                .then(data => {
                    if (data.monitor_running) {
                        document.getElementById('status').textContent = '监控脚本已恢复，正在跳转到登录页面...';
                        setTimeout(() => {
                            window.location.href = '/login';
                        }, 1500);
                    } else {
                        document.getElementById('status').textContent = '监控脚本仍未运行，3秒后再次检查...';
                        setTimeout(checkMonitorStatus, 3000);
                    }
                })
                .catch(error => {
                    console.error('检查监控状态失败:', error);
                    document.getElementById('status').textContent = '检查失败，3秒后再次尝试...';
                    setTimeout(checkMonitorStatus, 3000);
                });
        }
        
        // 页面加载后立即开始检查
        setTimeout(checkMonitorStatus, 1000);
    </script>
</body>
</html>
            """, 200

    # 监控状态文件检查端点（用于前端检查监控是否恢复）
    @app.route('/api/monitor-status-file')
    def api_monitor_status_file():
        """通过文件检查监控脚本运行状态，不需要认证"""
        try:
            from monitor_status import is_monitor_recovered, load_monitor_status

            # 检查监控是否已恢复
            recovered = is_monitor_recovered(check_threshold=10)

            # 从文件加载状态信息
            file_status = load_monitor_status()

            return jsonify({
                'monitor_recovered': recovered,
                'monitor_running': file_status.get('monitor_running', False),
                'last_update': file_status.get('last_update'),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"检查监控状态文件失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return jsonify({
                'monitor_recovered': False,
                'monitor_running': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }), 500

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

            # 确保 auto_login 配置项存在
            if 'auto_login' not in safe_config:
                safe_config['auto_login'] = {
                    'enabled': False,
                    'username': '',
                    'password': '***'
                }
            else:
                # 确保 auto_login 的所有子字段都存在
                if 'enabled' not in safe_config['auto_login']:
                    safe_config['auto_login']['enabled'] = False
                if 'username' not in safe_config['auto_login']:
                    safe_config['auto_login']['username'] = ''
                if 'password' not in safe_config['auto_login']:
                    safe_config['auto_login']['password'] = '***'

            # 确保 git_update 配置项存在
            if 'git_update' not in safe_config:
                safe_config['git_update'] = {
                    'enabled': False,
                    'check_interval': 3600,
                    'auto_pull': False,
                    'auto_restart': False
                }
            else:
                # 确保 git_update 的所有子字段都存在
                if 'enabled' not in safe_config['git_update']:
                    safe_config['git_update']['enabled'] = False
                if 'check_interval' not in safe_config['git_update']:
                    safe_config['git_update']['check_interval'] = 3600
                if 'auto_pull' not in safe_config['git_update']:
                    safe_config['git_update']['auto_pull'] = False
                if 'auto_restart' not in safe_config['git_update']:
                    safe_config['git_update']['auto_restart'] = False

            # 确保 yunzai.crash_detection 配置项存在
            if 'yunzai' not in safe_config:
                safe_config['yunzai'] = {}
            if 'crash_detection' not in safe_config['yunzai']:
                safe_config['yunzai']['crash_detection'] = {
                    'crash_threshold_seconds': 30,
                    'max_crash_count': 3,
                    'reset_timeout_hours': 24
                }
            else:
                # 确保 crash_detection 的所有子字段都存在
                if 'crash_threshold_seconds' not in safe_config['yunzai']['crash_detection']:
                    safe_config['yunzai']['crash_detection']['crash_threshold_seconds'] = 30
                if 'max_crash_count' not in safe_config['yunzai']['crash_detection']:
                    safe_config['yunzai']['crash_detection']['max_crash_count'] = 3
                if 'reset_timeout_hours' not in safe_config['yunzai']['crash_detection']:
                    safe_config['yunzai']['crash_detection']['reset_timeout_hours'] = 24

            # 渲染配置页面
            return render_template("config.html", config=safe_config)
        except Exception as e:
            logger.error(f"加载配置页面失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            return render_template("login.html", error_msg="加载配置页面失败，请重试。", username_hint=get_web_auth_config().get("username", "admin")), 500

    # 配置更新API
    @app.route('/api/config/update', methods=['POST'])
    @requires_auth
    def api_config_update():
        """更新配置信息 - 使用配置锁防止并发写入"""
        # 尝试获取配置锁，如果正在更新则立即返回
        if not _config_lock.acquire(blocking=False):
            return jsonify({'error': '配置正在更新中，请稍后再试'}), 429

        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': '无效的JSON数据'}), 400

            # 验证配置数据
            required_sections = ['llbot', 'yunzai', 'http_check', 'auto_restart', 'auto_login', 'web_auth', 'git_update']
            for section in required_sections:
                if section not in data:
                    return jsonify({'error': f'缺少配置项: {section}'}), 400

            # 验证具体配置值
            if not isinstance(data['llbot'].get('wait_seconds'), (int, float)) or data['llbot']['wait_seconds'] < 1:
                return jsonify({'error': 'llbot等待时间必须大于0'}), 400
            if not isinstance(data['yunzai'].get('wait_seconds'), (int, float)) or data['yunzai']['wait_seconds'] < 1:
                return jsonify({'error': 'yunzai等待时间必须大于0'}), 400

            # 验证 crash_detection 配置
            if 'crash_detection' in data['yunzai']:
                crash_detection = data['yunzai']['crash_detection']
                if not isinstance(crash_detection.get('crash_threshold_seconds'), (int, float)) or crash_detection['crash_threshold_seconds'] < 5:
                    return jsonify({'error': '闪退阈值必须大于等于5秒'}), 400
                if not isinstance(crash_detection.get('max_crash_count'), (int, float)) or crash_detection['max_crash_count'] < 1:
                    return jsonify({'error': '最大闪退次数必须大于等于1'}), 400
                if not isinstance(crash_detection.get('reset_timeout_hours'), (int, float)) or crash_detection['reset_timeout_hours'] < 1:
                    return jsonify({'error': '重置超时必须大于等于1小时'}), 400
            if not isinstance(data['http_check'].get('timeout'), (int, float)) or data['http_check']['timeout'] < 1:
                return jsonify({'error': 'HTTP超时时间必须大于0'}), 400
            if not isinstance(data['auto_restart'].get('enabled'), bool):
                return jsonify({'error': '自动重启启用状态必须是布尔值'}), 400
            if not isinstance(data['auto_restart'].get('respect_manual_stop'), bool):
                return jsonify({'error': '尊重手动停止状态必须是布尔值'}), 400
            if not isinstance(data['auto_login'].get('enabled'), bool):
                return jsonify({'error': '自动登录启用状态必须是布尔值'}), 400
            # 如果启用了自动登录，验证用户名和密码
            if data['auto_login'].get('enabled'):
                if not data['auto_login'].get('username'):
                    # 用户名为空时使用当前用户
                    data['auto_login']['username'] = ''
                # 如果密码字段不存在，保持现有密码不变
                if 'password' not in data['auto_login']:
                    # 从现有配置中保留密码
                    existing_password = current_config.get('auto_login', {}).get('password')
                    if existing_password:
                        data['auto_login']['password'] = existing_password
                    else:
                        # 如果现有配置中也没有密码，设置为 None 以保持现有配置不变
                        data['auto_login']['password'] = None
                # 如果密码字段存在但为空字符串，说明用户想要清除密码（这不应该发生，但为了健壮性）
                elif data['auto_login'].get('password') == '':
                    return jsonify({'error': '启用自动登录时密码不能为空'}), 400
                # 如果密码字段存在且为 '***'，保持现有密码不变
                elif data['auto_login'].get('password') == '***':
                    existing_password = current_config.get('auto_login', {}).get('password')
                    data['auto_login']['password'] = existing_password if existing_password else None
            # Only validate username if it's provided in the request (meaning user wants to change it)
            # If username is not provided, we'll keep the existing username
            if 'username' in data['web_auth'] and not data['web_auth'].get('username'):
                return jsonify({'error': '用户名不能为空'}), 400

            # 验证 git_update 配置
            if not isinstance(data['git_update'].get('enabled'), bool):
                return jsonify({'error': 'Git更新检测启用状态必须是布尔值'}), 400
            if not isinstance(data['git_update'].get('check_interval'), (int, float)) or data['git_update']['check_interval'] < 1:
                return jsonify({'error': 'Git更新检测间隔必须大于0'}), 400
            if not isinstance(data['git_update'].get('auto_pull'), bool):
                return jsonify({'error': 'Git自动拉取启用状态必须是布尔值'}), 400
            if not isinstance(data['git_update'].get('auto_restart'), bool):
                return jsonify({'error': 'Git自动重启启用状态必须是布尔值'}), 400

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
                    # New password provided, validate its strength
                    is_valid, errors = PasswordValidator.validate(password_value)
                    if not is_valid:
                        return jsonify({'error': '密码不符合安全要求', 'errors': errors}), 400
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
                config_path = "config.yaml"
                save_config(current_config, config_path)

                # 验证文件是否成功写入
                import os
                if not os.path.exists(config_path):
                    raise IOError(f"配置文件保存失败: {config_path} 不存在")

                # 验证文件内容是否与当前配置一致
                import yaml
                with open(config_path, 'r', encoding='utf-8') as file:
                    saved_config = yaml.safe_load(file)
                    if saved_config is None:
                        saved_config = {}

                    # 验证关键配置项是否正确保存
                    verification_errors = []
                    for section in ['llbot', 'yunzai', 'http_check', 'auto_restart', 'auto_login', 'web_auth', 'git_update']:
                        if section in current_config:
                            if section not in saved_config:
                                verification_errors.append(f"配置节 {section} 未保存到文件")
                            else:
                                for key, value in current_config[section].items():
                                    if key not in saved_config[section]:
                                        verification_errors.append(f"配置项 {section}.{key} 未保存到文件")
                                    # 跳过密码字段的直接比较，因为保存的是加密后的密码
                                    elif (section == 'web_auth' and key == 'password') or (section == 'auto_login' and key == 'password'):
                                        # 验证保存的密码是否为加密格式
                                        from password_crypt import PasswordCrypt
                                        if not PasswordCrypt.is_encrypted(saved_config[section][key]):
                                            verification_errors.append(f"配置项 {section}.{key} 保存的密码格式错误，应为加密格式")
                                    elif saved_config[section][key] != value:
                                        verification_errors.append(f"配置项 {section}.{key} 值不一致: 期望 {value}, 实际 {saved_config[section][key]}")
                    if verification_errors:
                        error_msg = "配置验证失败: " + "; ".join(verification_errors)
                        logger.error(error_msg, extra={
                            'event_type': EventType.ERROR,
                            'error': error_msg,
                            'action': 'config_verification_failure'
                        })
                        return jsonify({'error': error_msg}), 500

                logger.info("配置已更新并验证成功", extra={
                    'event_type': 'config_update',
                    'action': 'full_config_update'
                })

                # 立即重新加载配置以应用新设置
                try:
                    # 重新加载配置以确保所有更改生效
                    from config import load_config
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
        finally:
            _config_lock.release()

    @app.route('/api/check-updates', methods=['POST'])
    @requires_auth
    def api_check_updates():
        """手动检查并更新前端资源 - 使用更新锁防止并发调用"""
        if not _update_lock.acquire(blocking=False):
            return jsonify({'error': '更新操作正在进行中，请稍后再试'}), 429

        try:
            from update_checker import check_and_update_resources
            result = check_and_update_resources()
            return jsonify({
                'message': f'更新检查完成: 更新 {result["updated"]} 个, 跳过 {result["skipped"]} 个, 失败 {result["failed"]} 个',
                'result': result
            })
        except Exception as e:
            logger.error(f"检查更新失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'action': 'manual_update_check_failure'
            })
            return jsonify({'error': f'检查更新失败: {str(e)}'}), 500
        finally:
            _update_lock.release()

    @app.route('/api/force-updates', methods=['POST'])
    @requires_auth
    def api_force_updates():
        """强制更新所有前端资源 - 使用更新锁防止并发调用"""
        if not _update_lock.acquire(blocking=False):
            return jsonify({'error': '更新操作正在进行中，请稍后再试'}), 429

        try:
            from update_checker import force_update_resources
            result = force_update_resources()
            return jsonify({
                'message': f'强制更新完成: 成功 {result["updated"]} 个, 失败 {result["failed"]} 个',
                'result': result
            })
        except Exception as e:
            logger.error(f"强制更新失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'action': 'force_update_failure'
            })
            return jsonify({'error': f'强制更新失败: {str(e)}'}), 500
        finally:
            _update_lock.release()

    @app.route('/api/check-git-updates', methods=['POST'])
    @requires_auth
    def api_check_git_updates():
        """手动检查Git仓库更新 - 使用更新锁防止并发调用"""
        if not _update_lock.acquire(blocking=False):
            return jsonify({'error': '更新操作正在进行中，请稍后再试'}), 429

        try:
            from git_update_checker import check_repo_update, get_current_branch, get_local_commit, get_remote_commit, get_latest_commit_message
            import os

            # 获取当前脚本所在目录
            current_dir = os.path.dirname(os.path.abspath(__file__))

            # 检查当前目录是否是Git仓库
            from git_update_checker import is_git_repo
            if not is_git_repo(current_dir):
                return jsonify({
                    'message': '当前目录不是Git仓库',
                    'has_update': False,
                    'branch': None,
                    'local_commit': None,
                    'remote_commit': None,
                    'latest_commit_message': None
                }), 400

            # 获取当前分支
            branch = get_current_branch(current_dir)

            # 获取本地和远程提交哈希
            local_commit = get_local_commit(current_dir)
            remote_commit = get_remote_commit(current_dir)

            # 获取最新提交信息
            latest_commit_message = get_latest_commit_message(current_dir)

            # 检查是否有更新
            has_update, status_output = check_repo_update(current_dir)

            logger.info(f"手动检查Git仓库更新: {current_dir}, 分支: {branch}, 有更新: {has_update}", extra={
                'event_type': EventType.INFO,
                'repo_path': current_dir,
                'branch': branch,
                'has_update': has_update
            })

            if has_update:
                return jsonify({
                    'message': f'Git仓库检测到更新！当前分支: {branch}',
                    'has_update': True,
                    'branch': branch,
                    'local_commit': local_commit,
                    'remote_commit': remote_commit,
                    'latest_commit_message': latest_commit_message,
                    'status_output': status_output
                })
            else:
                return jsonify({
                    'message': f'Git仓库已是最新版本。当前分支: {branch}',
                    'has_update': False,
                    'branch': branch,
                    'local_commit': local_commit,
                    'remote_commit': remote_commit,
                    'latest_commit_message': latest_commit_message,
                    'status_output': status_output
                })
        except Exception as e:
            logger.error(f"检查Git仓库更新失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e),
                'action': 'manual_git_update_check_failure'
            })
            return jsonify({'error': f'检查Git仓库更新失败: {str(e)}'}), 500
        finally:
            _update_lock.release()

def start_web_server(host='127.0.0.1', port=5000):
    """启动Web服务器"""
    from logger import get_logger
    logger = get_logger()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Web管理界面启动在 http://{host}:{port}")
    logger.info(f"Web管理界面启动", extra={
        'event_type': 'web_server',
        'action': 'started',
        'address': f'http://{host}:{port}'
    })
    
    # 使用Flask内置服务器，启用多线程支持并发请求
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)