# -*- coding: utf-8 -*-
"""
Web服务器模块 - 提供Web管理界面
"""
import logging
import threading
import os
from datetime import datetime
from functools import wraps

# Web界面相关 - 只使用Flask
try:
    from flask import Flask as Quart, render_template_string, jsonify, request, session, redirect, Response
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
    
    # 创建Flask应用
    app = Quart(__name__)
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
        get_global_manual_stop_status,
        update_global_manual_stop_status
    )
    from monitor import check_and_manage_yunzai_async, async_http_check
    
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
    
    @app.route('/')
    def index():
        """主页"""
        if 'logged_in' not in session:
            return redirect('/login')
        try:
            html_template = get_index_template()
            return render_template_string(html_template)
        except Exception as e:
            logger.error(f"加载主页失败: {str(e)}", extra={'event_type': EventType.ERROR, 'error': str(e)})
            return render_template_string(get_login_template("加载主页失败，请重试。")), 500

    @app.route('/api/status')
    @requires_auth
    def api_status():
        """获取状态API"""
        return jsonify(current_status)

    @app.route('/api/logs')
    @requires_auth
    def api_logs():
        """获取日志API"""
        return jsonify({'logs': recent_logs})

    @app.route('/api/control', methods=['POST'])
    @requires_auth
    def api_control():
        """控制进程API"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'message': '无效的JSON数据'}), 400
            
            process = data.get('process')
            action = data.get('action')
            
            if not process or not action:
                return jsonify({'message': '缺少process或action参数'}), 400
            
            try:
                if process == 'llbot':
                    if action == 'start':
                        # 启动llbot
                        restart_llbot_with_cleanup(current_config)
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
                        # 终止node.exe进程
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止node.exe进程...")
                        terminate_process_by_name("node.exe")
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
                        # 停止yunzai - 终止特定的git-bash.exe进程
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止yunzai的git-bash.exe进程...")
                        from process_manager import terminate_yunzai_git_bash_process
                        terminate_yunzai_git_bash_process()
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
            config_html = get_config_template(safe_config)
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
    
    # 使用Flask内置服务器
    app.run(host=host, port=port, debug=False, use_reloader=False)

# 模板函数
def get_login_template(error_msg=None):
    """获取登录页面模板"""
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

    template = f'''
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
                        <input type="password" class="form-control form-control-with-icon" name="password" placeholder="密码" required>
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
    # 只替换<style>和<script>标签内的双花括号，避免Jinja2模板解析错误
    import re
    
    def replace_braces_in_section(template, start_tag, end_tag):
        """在指定的HTML标签之间替换双花括号"""
        result = []
        pos = 0
        while True:
            # 查找开始标签
            start_idx = template.find(start_tag, pos)
            if start_idx == -1:
                result.append(template[pos:])
                break
            
            # 查找结束标签
            end_idx = template.find(end_tag, start_idx + len(start_tag))
            if end_idx == -1:
                result.append(template[pos:])
                break
            
            # 添加开始标签之前的内容
            result.append(template[pos:start_idx + len(start_tag)])
            
            # 处理标签内的内容
            content = template[start_idx + len(start_tag):end_idx]
            content = content.replace('{{', '{').replace('}}', '}')
            result.append(content)
            
            # 添加结束标签
            result.append(end_tag)
            
            pos = end_idx + len(end_tag)
        
        return ''.join(result)
    
    # 替换style标签内的双花括号
    template = replace_braces_in_section(template, '<style>', '</style>')
    
    # 替换script标签内的双花括号
    template = replace_braces_in_section(template, '<script>', '</script>')
    
    return template


def get_index_template():
    """获取主页模板"""
    # 这里返回主页HTML模板的完整代码
    # 由于代码太长，这里只返回一个简化的版本
    template = '''
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
        body {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            padding-top: 20px;
            padding-bottom: 20px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        .main-container {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            margin-bottom: 20px;
        }}
        .status-card {{
            border-radius: 12px;
            border: none;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            height: 100%;
            background: linear-gradient(145deg, #ffffff, #f8f9fa);
            overflow: hidden;
        }}
        .status-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.2);
        }}
        .status-running {{
            background: linear-gradient(45deg, #28a745, #20c997) !important;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
            box-shadow: 0 0 10px rgba(40, 167, 69, 0.5);
            animation: pulse 2s infinite;
        }}
        .status-stopped {{
            background: linear-gradient(45deg, #dc3545, #fd7e14) !important;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }}
        .status-unknown {{
            background: linear-gradient(45deg, #ffc107, #fd7e14) !important;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }}
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
            100% {{ opacity: 1; }}
        }}
        .btn-action {{
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
        }}
        .btn-action i {{
            margin-right: 8px;
        }}
        .btn-start {{
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
        }}
        .btn-start:hover {{
            background: linear-gradient(45deg, #218838, #1ea085);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(40, 167, 69, 0.4);
        }}
        .btn-stop {{
            background: linear-gradient(45deg, #dc3545, #fd7e14);
            color: white;
        }}
        .btn-stop:hover {{
            background: linear-gradient(45deg, #c82333, #e06b10);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(220, 53, 69, 0.4);
        }}
        .btn-check {{
            background: linear-gradient(45deg, #007bff, #6610f2);
            color: white;
        }}
        .btn-check:hover {{
            background: linear-gradient(45deg, #0056b3, #520dc2);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.4);
        }}
        #http-check-container,
        #http-check-card {{
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: relative !important;
            z-index: 9999 !important;
            pointer-events: auto !important;
            max-height: none !important;
        }}

        /* 强制按钮样式，确保可见且可点击 */
        #http-check-button,
        #http-check-card .btn-check {{
            display: inline-flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: relative !important;
            z-index: 10000 !important;
            pointer-events: auto !important;
        }}

        /* 额外确保HTTP检查卡片及其子元素始终可见（保留以防有其他规则覆盖） */
        #http-check-card *,
        #http-check-container * {{
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }}
        .log-container {{
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
        }}
        .log-entry {{ 
            margin-bottom: 5px; 
            line-height: 1.4;
            padding: 2px 0;
            border-left: 3px solid transparent;
        }}
        .log-entry:hover {{
            background: rgba(255,255,255,0.05);
            padding-left: 8px;
            border-left: 3px solid #4a90e2;
            border-radius: 2px;
        }}
        .log-info {{ 
            color: #87ceeb; 
            border-left-color: #87ceeb;
        }}
        .log-warning {{ 
            color: #ffcc00; 
            border-left-color: #ffcc00;
        }}
        .log-error {{ 
            color: #ff6b6b; 
            border-left-color: #ff6b6b;
        }}
        .log-debug {{ 
            color: #98fb98; 
            border-left-color: #98fb98;
        }}
        .header-title {{
            background: linear-gradient(45deg, #007bff, #6610f2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: 700;
            font-size: 1.8rem;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .card-header {{
            border-bottom: 1px solid rgba(0,0,0,0.05);
            background: linear-gradient(to right, #f8f9fa, #e9ecef) !important;
            border-radius: 12px 12px 0 0 !important;
            padding: 1.2rem 1.5rem !important;
        }}
        .card-body {{
            padding: 1.5rem !important;
        }}
        .process-icon {{
            font-size: 28px;
            margin-right: 12px;
            vertical-align: middle;
            width: 30px;
            text-align: center;
        }}
        .status-text {{
            font-weight: 600;
            font-size: 0.95rem;
        }}
        .alert-box {{
            border-radius: 12px;
            border: none;
            overflow: hidden;
        }}
        .counter-badge {{
            background: linear-gradient(45deg, #6c757d, #495057);
            border-radius: 20px;
            padding: 5px 12px;
            font-size: 0.85em;
            font-weight: 500;
        }}
        .dropdown-menu {{
            border-radius: 12px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.15);
            border: none;
            padding: 8px 0;
        }}
        .dropdown-item {{
            padding: 10px 20px;
            transition: all 0.2s;
        }}
        .dropdown-item:hover {{
            background: rgba(0, 123, 255, 0.1);
        }}
        .password-modal .form-control {{
            border-radius: 8px;
            border: 2px solid #e9ecef;
            padding: 10px 15px;
        }}
        .system-stats {{
            display: flex;
            justify-content: space-around;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .stat-item {{
            text-align: center;
            padding: 15px;
            background: rgba(255,255,255,0.7);
            border-radius: 10px;
            margin: 5px;
            min-width: 120px;
            flex: 1;
        }}
        .stat-value {{
            font-size: 1.8rem;
            font-weight: bold;
            background: linear-gradient(45deg, #007bff, #6610f2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        .stat-label {{
            font-size: 0.9rem;
            color: #6c757d;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #6c757d;
            font-size: 0.9rem;
        }}
        .refresh-indicator {{
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: linear-gradient(45deg, #28a745, #20c997);
            margin-left: 8px;
            animation: blink 1.5s infinite;
        }}
        @keyframes blink {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
            100% {{ opacity: 1; }}
        }}
        .card-title {{
            font-weight: 600;
            color: #495057;
        }}
        
        /* 侧边栏样式 */
        .sidebar {{
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
        }}
        
        .sidebar-header {{
            padding: 0 20px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 20px;
        }}
        
        .sidebar-title {{
            color: white;
            font-size: 1.2rem;
            font-weight: 600;
            margin: 0;
        }}
        
        .sidebar-nav {{
            padding: 0 15px;
        }}
        
        .sidebar-item {{
            margin-bottom: 8px;
        }}
        
        .sidebar-link {{
            display: flex;
            align-items: center;
            padding: 12px 15px;
            color: rgba(255, 255, 255, 0.8);
            text-decoration: none;
            border-radius: 8px;
            transition: all 0.3s ease;
        }}
        
        .sidebar-link:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: white;
            transform: translateX(5px);
        }}
        
        .sidebar-link.active {{
            background: linear-gradient(45deg, #007bff, #6610f2);
            color: white;
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
        }}
        
        .sidebar-link i {{
            width: 24px;
            margin-right: 12px;
            font-size: 1.1rem;
        }}
        
        .sidebar-link span {{
            font-weight: 500;
        }}
        
        .main-content {{
            margin-left: 250px;
            padding: 20px;
            transition: all 0.3s ease;
        }}
        
        @media (max-width: 768px) {{
            .sidebar {{
                width: 70px;
            }}
            
            .sidebar-header {{
                padding: 0 10px 20px;
            }}
            
            .sidebar-title {{
                font-size: 0;
            }}
            
            .sidebar-title:after {{
                content: "☰";
                font-size: 1.5rem;
            }}
            
            .sidebar-link span {{
                display: none;
            }}
            
            .sidebar-link i {{
                margin-right: 0;
                font-size: 1.3rem;
            }}
            
            .main-content {{
                margin-left: 70px;
            }}
        }}
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
        function handleAuthError() {{
            // 如果认证失败，重定向到登录页面
            window.location.href = '/login';
        }}
        
        // 自动更新状态
        function updateStatus() {{
            fetch('/api/status')
                .then(response => {{
                    if (response.status === 401) {{
                        handleAuthError();
                        return;
                    }}
                    return response.json();
                }})
                .then(data => {{
                    if (data && typeof data === 'object') {{
                        updateProcessStatus('llbot', data.llbot);
                        updateProcessStatus('yunzai', data.yunzai);
                        updateProcessStatus('redis', data.redis);
                        
                        const httpStatus = document.getElementById('http-status');
                        const httpIndicator = document.getElementById('http-status-indicator');
                        
                        // HTTP检查卡片总是显示，不需要额外的显示控制
                        // 更新HTTP检查状态
                        if (data.http_check && data.http_check.configured) {{
                            if (data.http_check.accessible) {{
                                httpStatus.textContent = '可访问';
                                httpIndicator.className = 'status-running';
                            }} else {{
                                httpStatus.textContent = '不可访问';
                                httpIndicator.className = 'status-stopped';
                            }}
                        }} else {{
                            httpStatus.textContent = '未配置';
                            httpIndicator.className = 'status-unknown';
                        }}
                        
                        // 更新统计信息
                        updateStats(data);
                        
                        // 确保HTTP检查卡片始终可见
                        ensureHttpCardVisibility();
                    }}
                }})
                .catch(error => {{
                    console.error('获取状态失败:', error);
                    // 即使获取状态失败，也要确保HTTP检查卡片显示
                    const httpCard = document.getElementById('http-check-card');
                    const httpContainer = document.getElementById('http-check-container');
                    
                    if (httpCard) {{
                        httpCard.style.display = 'block';
                        httpCard.style.visibility = 'visible';
                        httpCard.style.opacity = '1';
                        httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                    }}
                    
                    if (httpContainer) {{
                        httpContainer.style.display = 'block';
                        httpContainer.style.visibility = 'visible';
                        httpContainer.style.opacity = '1';
                        httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                    }}
                    
                    // 检查是否是认证错误
                    if (error.message && error.message.includes('401')) {{
                        handleAuthError();
                    }}
                }});
        }}
        
        // 更新统计信息
        function updateStats(data) {{
            const llbotStat = document.getElementById('llbot-stat');
            const yunzaiStat = document.getElementById('yunzai-stat');
            const redisStat = document.getElementById('redis-stat');
            const httpStat = document.getElementById('http-stat');
            
            if(data.llbot && data.llbot.running) {{
                llbotStat.textContent = '运行';
                llbotStat.style.color = '#28a745';
            }} else {{
                llbotStat.textContent = '停止';
                llbotStat.style.color = '#dc3545';
            }}
            
            if(data.yunzai && data.yunzai.running) {{
                yunzaiStat.textContent = '运行';
                yunzaiStat.style.color = '#28a745';
            }} else {{
                yunzaiStat.textContent = '停止';
                yunzaiStat.style.color = '#dc3545';
            }}
            
            if(data.redis && data.redis.running) {{
                redisStat.textContent = '运行';
                redisStat.style.color = '#28a745';
            }} else {{
                redisStat.textContent = '停止';
                redisStat.style.color = '#dc3545';
            }}
            
            // 确保HTTP检查状态总是更新，不管是否有配置
            if(data.http_check && data.http_check.configured) {{
                if(data.http_check.accessible) {{
                    httpStat.textContent = '正常';
                    httpStat.style.color = '#28a745';
                }} else {{
                    httpStat.textContent = '异常';
                    httpStat.style.color = '#dc3545';
                }}
            }} else {{
                httpStat.textContent = '未配置';
                httpStat.style.color = '#6c757d';
            }}
        }}
        
        function updateProcessStatus(process, status) {{
            const statusElement = document.getElementById(process + '-status');
            const indicatorElement = document.getElementById(process + '-status-indicator');
            
            if (status && status.running) {{
                statusElement.textContent = '运行中 (PID: ' + status.pid + ')';
                indicatorElement.className = 'status-running';
            }} else {{
                statusElement.textContent = '已停止';
                indicatorElement.className = 'status-stopped';
            }}
        }}
        
        // 更新日志
        function updateLogs() {{
            fetch('/api/logs')
                .then(response => {{
                    if (response.status === 401) {{
                        handleAuthError();
                        return;
                    }}
                    return response.json();
                }})
                .then(data => {{
                    if (data && data.logs) {{
                        const logsDiv = document.getElementById('logs');
                        logsDiv.innerHTML = '';
                        
                        // 更新日志计数
                        document.getElementById('log-count').textContent = data.logs.length;
                        
                        data.logs.forEach(log => {{
                            const logElement = document.createElement('div');
                            logElement.className = 'log-entry log-' + log.level.toLowerCase();
                            logElement.textContent = log.timestamp + ' [' + log.level + '] ' + log.module + ':' + log.function + ' - ' + log.message;
                            logsDiv.appendChild(logElement);
                        }});
                        
                        // 滚动到最新日志
                        logsDiv.scrollTop = logsDiv.scrollHeight;
                        
                        // 更新最后更新时间
                        document.getElementById('last-update').textContent = new Date().toLocaleString('zh-CN');
                    }}
                }})
                .catch(error => {{
                    console.error('获取日志失败:', error);
                    // 检查是否是认证错误
                    if (error.message && error.message.includes('401')) {{
                        handleAuthError();
                    }}
                }});
        }}
        
        // 清空日志
        function clearLogs() {{
            const logsDiv = document.getElementById('logs');
            logsDiv.innerHTML = '';
            document.getElementById('log-count').textContent = '0';
            document.getElementById('last-update').textContent = '已清空';
            showAlert('日志已清空', 'info');
        }}
        
        // 控制进程（已移除确认框，点击立即执行）
        function controlProcess(process, action) {{
            const actionText = action === 'start' ? '启动' : '停止';
            // 不再弹出确认框，直接执行操作以提高体验。
            
            // 禁用按钮并显示加载状态
            const buttons = document.querySelectorAll(`button[onclick*="controlProcess('${process}'"]`);
            buttons.forEach(btn => {{
                btn.disabled = true;
                const originalHTML = btn.innerHTML;
                btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${{actionText}}中...`;
                
                // 恢复原始内容的函数
                setTimeout(() => {{
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                }}, 5000); // 5秒后恢复，即使没有收到响应
            }});
            
            fetch('/api/control', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    process: process,
                    action: action
                }})
            }})
            .then(response => {{
                if (response.status === 401) {{
                    handleAuthError();
                    return;
                }}
                return response.json();
            }})
            .then(data => {{
                if (data) {{
                    // 重置按钮状态
                    buttons.forEach(btn => {{
                        btn.disabled = false;
                        btn.innerHTML = btn.getAttribute('data-original-content') || btn.innerHTML.replace('<i class="fas fa-spinner fa-spin"></i> ', '');
                    }});
                    
                    // 使用Bootstrap的alert显示消息
                    showAlert(data.message, 'success');
                    updateStatus();
                }}
            }})
            .catch(error => {{
                console.error('控制进程失败:', error);
                // 重置按钮状态
                buttons.forEach(btn => {{
                    btn.disabled = false;
                    btn.innerHTML = btn.getAttribute('data-original-content') || btn.innerHTML.replace('<i class="fas fa-spinner fa-spin"></i> ', '');
                }});
                
                // 检查是否是认证错误
                if (error.message && error.message.includes('401')) {{
                    handleAuthError();
                }} else {{
                    showAlert('操作失败: ' + error, 'danger');
                }}
            }});
        }}
        
        // 手动HTTP检查
        function manualHttpCheck() {{
            // 禁用按钮并显示加载状态
            const button = document.querySelector('button[onclick="manualHttpCheck()"]');
            const originalHTML = button.innerHTML;
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 检查中...';
            
            fetch('/api/manual-check', {{
                method: 'POST',
            }})
            .then(response => {{
                if (response.status === 401) {{
                    handleAuthError();
                    return;
                }}
                return response.json();
            }})
            .then(data => {{
                if (data) {{
                    // 重置按钮状态
                    button.disabled = false;
                    button.innerHTML = originalHTML;
                    
                    showAlert(data.message, 'info');
                    updateStatus();
                }}
            }})
            .catch(error => {{
                console.error('手动检查失败:', error);
                // 重置按钮状态
                button.disabled = false;
                button.innerHTML = originalHTML;
                
                // 检查是否是认证错误
                if (error.message && error.message.includes('401')) {{
                    handleAuthError();
                }} else {{
                    showAlert('检查失败: ' + error, 'danger');
                }}
            }});
        }}
        
        // 显示警告消息
        function showAlert(message, type) {{
            // 创建alert元素
            const alertDiv = document.createElement('div');
            alertDiv.className = 'alert alert-' + type + ' alert-dismissible fade show position-fixed';
            alertDiv.style.top = '20px';
            alertDiv.style.right = '20px';
            alertDiv.style.zIndex = '9999';
            alertDiv.style.minWidth = '300px';
            alertDiv.innerHTML = message + '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
            
            document.body.appendChild(alertDiv);
            
            // 3秒后自动关闭
            setTimeout(() => {{
                alertDiv.remove();
            }}, 3000);
        }}
        
        // 修改密码
        function changePassword() {{
            const currentPassword = document.getElementById('currentPassword').value;
            const newUsername = document.getElementById('newUsername').value;
            const newPassword = document.getElementById('newPassword').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!currentPassword || !newPassword) {{
                showAlert('请填写当前密码和新密码', 'warning');
                return;
            }}
            
            if (newPassword !== confirmPassword) {{
                showAlert('两次输入的新密码不一致', 'warning');
                return;
            }}
            
            if (newPassword.length < 4) {{
                showAlert('新密码长度至少为4位', 'warning');
                return;
            }}
            
            fetch('/api/change-password', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    old_password: currentPassword,
                    new_username: newUsername,
                    new_password: newPassword
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.message) {{
                    showAlert(data.message, 'success');
                    // 关闭模态框
                    const modalEl = document.getElementById('passwordModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) {{
                        modal.hide();
                    }}
                }}
            }})
            .catch(error => {{
                showAlert('修改密码失败: ' + error, 'danger');
            }});
        }}
        
        // 确保HTTP检查卡片始终可见
        function ensureHttpCardVisibility() {{
            const httpCard = document.getElementById('http-check-card');
            const httpContainer = document.getElementById('http-check-container');
            const httpButton = document.getElementById('http-check-button');
            
            if (httpCard) {{
                httpCard.style.display = 'block';
                httpCard.style.visibility = 'visible';
                httpCard.style.opacity = '1';
                httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }}
            
            if (httpContainer) {{
                httpContainer.style.display = 'block';
                httpContainer.style.visibility = 'visible';
                httpContainer.style.opacity = '1';
                httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }}
            
            if (httpButton) {{
                httpButton.style.display = 'inline-flex';
                httpButton.style.visibility = 'visible';
                httpButton.style.opacity = '1';
            }}
        }}
        
        // 页面加载完成后启动自动更新
        document.addEventListener('DOMContentLoaded', function() {{
            updateStatus();
            updateLogs();
            
            // 每5秒更新一次状态
            setInterval(updateStatus, 5000);
            
            // 每5秒更新一次日志
            setInterval(updateLogs, 5000);
            
            // 确保HTTP检查卡片始终可见
            ensureHttpCardVisibility();
        }});
    </script>
</body>
</html>
    '''
    # 只替换<style>和<script>标签内的双花括号，避免Jinja2模板解析错误
    import re
    
    def replace_braces_in_section(template, start_tag, end_tag):
        """在指定的HTML标签之间替换双花括号"""
        result = []
        pos = 0
        while True:
            # 查找开始标签
            start_idx = template.find(start_tag, pos)
            if start_idx == -1:
                result.append(template[pos:])
                break
            
            # 查找结束标签
            end_idx = template.find(end_tag, start_idx + len(start_tag))
            if end_idx == -1:
                result.append(template[pos:])
                break
            
            # 添加开始标签之前的内容
            result.append(template[pos:start_idx + len(start_tag)])
            
            # 处理标签内的内容
            content = template[start_idx + len(start_tag):end_idx]
            content = content.replace('{{', '{').replace('}}', '}')
            result.append(content)
            
            # 添加结束标签
            result.append(end_tag)
            
            pos = end_idx + len(end_tag)
        
        return ''.join(result)
    
    # 替换style标签内的双花括号
    template = replace_braces_in_section(template, '<style>', '</style>')
    
    # 替换script标签内的双花括号
    template = replace_braces_in_section(template, '<script>', '</script>')
    
    return template

def get_config_template(safe_config):
    """获取配置页面模板"""
    # 这里返回配置页面HTML模板的完整代码
    # 由于代码太长，这里只返回一个简化的版本
    template = f'''
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
        body {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            padding-top: 20px;
            padding-bottom: 20px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        .main-container {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            margin-bottom: 20px;
        }}
        .config-card {{
            border-radius: 12px;
            border: none;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            height: 100%;
            background: linear-gradient(145deg, #ffffff, #f8f9fa);
            overflow: hidden;
            margin-bottom: 20px;
        }}
        .config-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 12px 30px rgba(0,0,0,0.2);
        }}
        .card-header {{
            border-bottom: 1px solid rgba(0,0,0,0.05);
            background: linear-gradient(to right, #f8f9fa, #e9ecef) !important;
            border-radius: 12px 12px 0 0 !important;
            padding: 1.2rem 1.5rem !important;
        }}
        .card-body {{
            padding: 1.5rem !important;
        }}
        .form-control {{
            border-radius: 10px;
            padding: 12px 15px;
            border: 2px solid #e9ecef;
            margin-bottom: 15px;
            transition: all 0.3s;
        }}
        .form-control:focus {{
            border-color: #007bff;
            box-shadow: 0 0 0 0.2rem rgba(0,123,255,0.25);
        }}
        .form-label {{
            font-weight: 600;
            color: #495057;
            margin-bottom: 8px;
        }}
        .btn-save {{
            background: linear-gradient(45deg, #28a745, #20c997);
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
        }}
        .btn-save:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4);
        }}
        .btn-cancel {{
            background: linear-gradient(45deg, #dc3545, #fd7e14);
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
        }}
        .btn-cancel:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(220, 53, 69, 0.4);
        }}
        .btn-back {{
            background: linear-gradient(45deg, #007bff, #6610f2);
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
        }}
        .btn-back:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 123, 255, 0.4);
        }}
        .header-title {{
            background: linear-gradient(45deg, #007bff, #6610f2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: 700;
            font-size: 1.8rem;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section-title {{
            font-weight: 600;
            color: #495057;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
        }}
        .alert-box {{
            border-radius: 12px;
            border: none;
            overflow: hidden;
        }}
        .config-icon {{
            font-size: 24px;
            margin-right: 12px;
            vertical-align: middle;
            width: 30px;
            text-align: center;
        }}
        .nav-tabs {{
            border-bottom: 2px solid #e9ecef;
        }}
        .nav-tabs .nav-link {{
            border: none;
            border-radius: 8px 8px 0 0;
            padding: 12px 20px;
            font-weight: 500;
            color: #6c757d;
            transition: all 0.3s;
        }}
        .nav-tabs .nav-link:hover {{
            color: #495057;
            background-color: rgba(0, 123, 255, 0.05);
        }}
        .nav-tabs .nav-link.active {{
            color: #007bff;
            background-color: rgba(0, 123, 255, 0.1);
            border-bottom: 3px solid #007bff;
        }}
        
        /* 侧边栏样式 */
        .sidebar {{
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
        }}
        
        .sidebar-header {{
            padding: 0 20px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 20px;
        }}
        
        .sidebar-title {{
            color: white;
            font-size: 1.2rem;
            font-weight: 600;
            margin: 0;
        }}
        
        .sidebar-nav {{
            padding: 0 15px;
        }}
        
        .sidebar-item {{
            margin-bottom: 8px;
        }}
        
        .sidebar-link {{
            display: flex;
            align-items: center;
            padding: 12px 15px;
            color: rgba(255, 255, 255, 0.8);
            text-decoration: none;
            border-radius: 8px;
            transition: all 0.3s ease;
        }}
        
        .sidebar-link:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: white;
            transform: translateX(5px);
        }}
        
        .sidebar-link.active {{
            background: linear-gradient(45deg, #007bff, #6610f2);
            color: white;
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
        }}
        
        .sidebar-link i {{
            width: 24px;
            margin-right: 12px;
            font-size: 1.1rem;
        }}
        
        .sidebar-link span {{
            font-weight: 500;
        }}
        
        .main-content {{
            margin-left: 250px;
            padding: 20px;
            transition: all 0.3s ease;
        }}
        
        @media (max-width: 768px) {{
            .sidebar {{
                width: 70px;
            }}
            
            .sidebar-header {{
                padding: 0 10px 20px;
            }}
            
            .sidebar-title {{
                font-size: 0;
            }}
            
            .sidebar-title:after {{
                content: "☰";
                font-size: 1.5rem;
            }}
            
            .sidebar-link span {{
                display: none;
            }}
            
            .sidebar-link i {{
                margin-right: 0;
                font-size: 1.3rem;
            }}
            
            .main-content {{
                margin-left: 70px;
            }}
        }}
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

            <!-- 配置内容 -->
            <div class="tab-content" id="configTabContent">
                <!-- llbot 配置 -->
                <div class="tab-pane fade show active" id="llbot" role="tabpanel">
                    <div class="card config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-robot config-icon text-primary"></i>llbot 配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="llbot-path" class="form-label">llbot.exe 路径</label>
                                <input type="text" class="form-control" id="llbot-path" value="{safe_config.get('llbot', {}).get('path', '')}" placeholder="例如: D:\\path\\to\\llbot.exe">
                            </div>
                            <div class="mb-3">
                                <label for="llbot-directory" class="form-label">llbot 目录</label>
                                <input type="text" class="form-control" id="llbot-directory" value="{safe_config.get('llbot', {}).get('directory', '')}" placeholder="例如: D:\\path\\to\\llbot">
                            </div>
                            <div class="mb-3">
                                <label for="llbot-wait-seconds" class="form-label">检查间隔（秒）</label>
                                <input type="number" class="form-control" id="llbot-wait-seconds" value="{safe_config.get('llbot', {}).get('wait_seconds', 5)}" min="1" max="60">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Yunzai 配置 -->
                <div class="tab-pane fade" id="yunzai" role="tabpanel">
                    <div class="card config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-server config-icon text-success"></i>Yunzai 配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="yunzai-git-bash-path" class="form-label">Git Bash 路径</label>
                                <input type="text" class="form-control" id="yunzai-git-bash-path" value="{safe_config.get('yunzai', {}).get('git_bash_path', '')}" placeholder="例如: D:\\path\\git-bash.exe">
                            </div>
                            <div class="mb-3">
                                <label for="yunzai-bash-directory" class="form-label">Yunzai 目录</label>
                                <input type="text" class="form-control" id="yunzai-bash-directory" value="{safe_config.get('yunzai', {}).get('bash_directory', '')}" placeholder="例如: D:\\path\\to\\yunzai">
                            </div>
                            <div class="mb-3">
                                <label for="yunzai-wait-seconds" class="form-label">检查间隔（秒）</label>
                                <input type="number" class="form-control" id="yunzai-wait-seconds" value="{safe_config.get('yunzai', {}).get('wait_seconds', 5)}" min="1" max="60">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Redis 配置 -->
                <div class="tab-pane fade" id="redis" role="tabpanel">
                    <div class="card config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-database config-icon text-info"></i>Redis 配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="redis-path" class="form-label">Redis 服务器路径</label>
                                <input type="text" class="form-control" id="redis-path" value="{safe_config.get('redis', {}).get('path', '')}" placeholder="例如: D:\\path\\to\\redis-server.exe">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- HTTP 检查配置 -->
                <div class="tab-pane fade" id="http" role="tabpanel">
                    <div class="card config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-plug config-icon text-warning"></i>HTTP 检查配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="http-check-url" class="form-label">HTTP 检查地址</label>
                                <input type="text" class="form-control" id="http-check-url" value="{safe_config.get('http_check', {}).get('url', '')}" placeholder="例如: http://localhost:3080">
                            </div>
                            <div class="mb-3">
                                <label for="http-check-timeout" class="form-label">超时时间（秒）</label>
                                <input type="number" class="form-control" id="http-check-timeout" value="{safe_config.get('http_check', {}).get('timeout', 5)}" min="1" max="30">
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 自动重启配置 -->
                <div class="tab-pane fade" id="auto" role="tabpanel">
                    <div class="card config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-redo config-icon text-secondary"></i>自动重启配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="auto-restart-enabled" {'checked' if safe_config.get('auto_restart', {}).get('enabled', True) else ''}>
                                <label class="form-check-label" for="auto-restart-enabled">
                                    启用自动重启
                                </label>
                            </div>
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="auto-restart-respect-manual-stop" {'checked' if safe_config.get('auto_restart', {}).get('respect_manual_stop', True) else ''}>
                                <label class="form-check-label" for="auto-restart-respect-manual-stop">
                                    尊重手动停止状态
                                </label>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Web 认证配置 -->
                <div class="tab-pane fade" id="auth" role="tabpanel">
                    <div class="card config-card">
                        <div class="card-header">
                            <h5 class="card-title mb-0"><i class="fas fa-lock config-icon text-danger"></i>Web 认证配置</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="auth-username" class="form-label">用户名</label>
                                <input type="text" class="form-control" id="auth-username" value="{safe_config.get('web_auth', {}).get('username', 'admin')}">
                            </div>
                            <div class="mb-3">
                                <label for="auth-password" class="form-label">密码</label>
                                <input type="password" class="form-control" id="auth-password" value="{safe_config.get('web_auth', {}).get('password', '***')}">
                                <small class="text-muted">显示 *** 表示保持当前密码不变</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 操作按钮 -->
            <div class="d-flex justify-content-between mt-4">
                <a href="/" class="btn btn-back">
                    <i class="fas fa-arrow-left me-2"></i>返回监控页面
                </a>
                <div>
                    <button class="btn btn-cancel me-2" onclick="location.href='/'">
                        <i class="fas fa-times me-2"></i>取消
                    </button>
                    <button class="btn btn-save" onclick="saveConfig()">
                        <i class="fas fa-save me-2"></i>保存配置
                    </button>
                </div>
            </div>
        </div>
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
        // 显示警告消息
        function showAlert(message, type) {{
            const alertDiv = document.createElement('div');
            alertDiv.className = 'alert alert-' + type + ' alert-dismissible fade show position-fixed';
            alertDiv.style.top = '20px';
            alertDiv.style.right = '20px';
            alertDiv.style.zIndex = '9999';
            alertDiv.style.minWidth = '300px';
            alertDiv.innerHTML = message + '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
            
            document.body.appendChild(alertDiv);
            
            setTimeout(() => {{
                alertDiv.remove();
            }}, 3000);
        }}

        // 保存配置
        async function saveConfig() {{
            const configData = {{
                llbot: {{
                    path: document.getElementById('llbot-path').value,
                    directory: document.getElementById('llbot-directory').value,
                    wait_seconds: parseInt(document.getElementById('llbot-wait-seconds').value)
                }},
                yunzai: {{
                    git_bash_path: document.getElementById('yunzai-git-bash-path').value,
                    bash_directory: document.getElementById('yunzai-bash-directory').value,
                    wait_seconds: parseInt(document.getElementById('yunzai-wait-seconds').value)
                }},
                redis: {{
                    path: document.getElementById('redis-path').value
                }},
                http_check: {{
                    url: document.getElementById('http-check-url').value,
                    timeout: parseInt(document.getElementById('http-check-timeout').value)
                }},
                auto_restart: {{
                    enabled: document.getElementById('auto-restart-enabled').checked,
                    respect_manual_stop: document.getElementById('auto-restart-respect-manual-stop').checked
                }},
                web_auth: {{
                    username: document.getElementById('auth-username').value,
                    password: document.getElementById('auth-password').value
                }}
            }};

            // 验证配置
            if (!configData.llbot.path) {{
                showAlert('llbot路径不能为空', 'warning');
                return;
            }}
            if (!configData.llbot.directory) {{
                showAlert('llbot目录不能为空', 'warning');
                return;
            }}
            if (configData.llbot.wait_seconds < 1 || configData.llbot.wait_seconds > 60) {{
                showAlert('llbot等待时间必须在 1-60 秒之间', 'warning');
                return;
            }}
            
            if (!configData.yunzai.git_bash_path) {{
                showAlert('Git Bash路径不能为空', 'warning');
                return;
            }}
            if (!configData.yunzai.bash_directory) {{
                showAlert('Yunzai目录不能为空', 'warning');
                return;
            }}
            if (configData.yunzai.wait_seconds < 1 || configData.yunzai.wait_seconds > 60) {{
                showAlert('Yunzai等待时间必须在 1-60 秒之间', 'warning');
                return;
            }}
            
            if (!configData.redis.path) {{
                showAlert('Redis路径不能为空', 'warning');
                return;
            }}
            
            if (configData.http_check.url && !configData.http_check.url.startsWith('http://') && !configData.http_check.url.startsWith('https://')) {{
                showAlert('HTTP 检查 URL 应以 http:// 或 https:// 开头', 'warning');
                return;
            }}
            if (configData.http_check.timeout < 1 || configData.http_check.timeout > 30) {{
                showAlert('HTTP 超时时间必须在 1-30 秒之间', 'warning');
                return;
            }}
            
            if (!configData.web_auth.username) {{
                showAlert('用户名不能为空', 'warning');
                return;
            }}
            // 验证密码字段 - only check if the user provided a new password
            if (configData.web_auth.password && configData.web_auth.password !== '***') {{
                // User entered a new password, validate it
                if (configData.web_auth.password.length < 4) {{
                    showAlert('密码长度至少为4位', 'warning');
                    return;
                }}
            }} else {{
                // Password field shows '***' (unchanged), so we'll remove it from the payload to indicate "keep existing"
                delete configData.web_auth.password;
            }}

            // 发送保存请求
            const response = await fetch('/api/config/update', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify(configData)
            }});

            const result = await response.json();

            if (response.ok) {{
                showAlert('配置保存成功！配置已热重载生效。', 'success');
                // 更新密码字段显示
                document.getElementById('auth-password').value = '***';
            }} else {{
                showAlert('保存失败：' + (result.error || '未知错误'), 'danger');
            }}
        }}

        // 修改密码
        function changePassword() {{
            const currentPassword = document.getElementById('currentPassword').value;
            const newUsername = document.getElementById('newUsername').value;
            const newPassword = document.getElementById('newPassword').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!currentPassword || !newPassword) {{
                showAlert('请填写当前密码和新密码', 'warning');
                return;
            }}
            
            if (newPassword !== confirmPassword) {{
                showAlert('两次输入的新密码不一致', 'warning');
                return;
            }}
            
            if (newPassword.length < 4) {{
                showAlert('新密码长度至少为4位', 'warning');
                return;
            }}
            
            fetch('/api/change-password', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{
                    old_password: currentPassword,
                    new_username: newUsername,
                    new_password: newPassword
                }})
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.message) {{
                    showAlert(data.message, 'success');
                    // 关闭模态框
                    const modalEl = document.getElementById('passwordModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) {{
                        modal.hide();
                    }}
                }}
            }})
            .catch(error => {{
                showAlert('修改密码失败: ' + error, 'danger');
            }});
        }}

        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', function() {{
            // 激活第一个选项卡
            const firstTab = document.querySelector('#configTabs .nav-link');
            if (firstTab) {{
                firstTab.click();
            }}
        }});
    </script>
</body>
</html>
    '''
    # 只替换<style>和<script>标签内的双花括号，避免Jinja2模板解析错误
    import re
    
    def replace_braces_in_section(template, start_tag, end_tag):
        """在指定的HTML标签之间替换双花括号"""
        result = []
        pos = 0
        while True:
            # 查找开始标签
            start_idx = template.find(start_tag, pos)
            if start_idx == -1:
                result.append(template[pos:])
                break
            
            # 查找结束标签
            end_idx = template.find(end_tag, start_idx + len(start_tag))
            if end_idx == -1:
                result.append(template[pos:])
                break
            
            # 添加开始标签之前的内容
            result.append(template[pos:start_idx + len(start_tag)])
            
            # 处理标签内的内容
            content = template[start_idx + len(start_tag):end_idx]
            content = content.replace('{{', '{').replace('}}', '}')
            result.append(content)
            
            # 添加结束标签
            result.append(end_tag)
            
            pos = end_idx + len(end_tag)
        
        return ''.join(result)
    
    # 替换style标签内的双花括号
    template = replace_braces_in_section(template, '<style>', '</style>')
    
    # 替换script标签内的双花括号
    template = replace_braces_in_section(template, '<script>', '</script>')
    
    return template
