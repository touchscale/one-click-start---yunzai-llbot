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
from datetime import datetime
from logging.handlers import RotatingFileHandler
import json
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# 全局事件管理器
event_manager = EventManager()

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
    
    # 文件处理器 - 使用轮转日志
    file_handler = RotatingFileHandler(
        'logs/monitor.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)
    
    # 控制台处理器 - 保持人类可读格式
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(funcName)s:%(lineno)d - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
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
    
    logger.info("交互式配置完成", extra={'event_type': 'config_complete'})
    print("\n配置完成！")
    return config

def save_config(config, config_path):
    """保存配置到文件"""
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)
    logger.info(f"配置已保存到 {config_path}", extra={'event_type': 'config_save', 'config_path': config_path})
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置已保存到 {config_path}")

def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        logger.info("配置文件不存在，启动交互式配置", extra={'event_type': 'config_missing', 'config_path': config_path})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置文件不存在，正在启动交互式配置...")
        config = interactive_config()
        save_config(config, config_path)
        return config
    else:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            
        # 确保配置项完整
        if 'llbot' not in config:
            config['llbot'] = {}
        if 'yunzai' not in config:
            config['yunzai'] = {}
        if 'redis' not in config:
            config['redis'] = {}
        if 'http_check' not in config:
            config['http_check'] = {}
        
        # 为wait_seconds和timeout设置默认值（如果未提供或为空）
        if 'wait_seconds' not in config['llbot'] or not config['llbot']['wait_seconds']:
            config['llbot']['wait_seconds'] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
        if 'wait_seconds' not in config['yunzai'] or not config['yunzai']['wait_seconds']:
            config['yunzai']['wait_seconds'] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
        if 'timeout' not in config['http_check'] or not config['http_check']['timeout']:
            config['http_check']['timeout'] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
        
        # 确保其他必要配置项不为空
        if 'path' not in config['llbot']:
            config['llbot']['path'] = ""
        if 'directory' not in config['llbot']:
            config['llbot']['directory'] = ""
        if 'git_bash_path' not in config['yunzai']:
            config['yunzai']['git_bash_path'] = ""
        if 'bash_directory' not in config['yunzai']:
            config['yunzai']['bash_directory'] = ""
        if 'path' not in config['redis']:
            config['redis']['path'] = ""
        if 'url' not in config['http_check']:
            config['http_check']['url'] = ""
        
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
        terminated_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == process_name.lower():
                pid = proc.info['pid']
                logger.info(f"终止进程 {process_name} (PID: {pid})", extra={'event_type': EventType.PROCESS_STOP, 'process_name': process_name, 'pid': pid})
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在终止进程 {process_name} (PID: {pid})")
                proc.kill()
                terminated_pids.append(pid)
                
        if terminated_pids:
            logger.info(f"成功终止进程 {process_name}", extra={'event_type': EventType.PROCESS_STOP, 'process_name': process_name, 'pids': terminated_pids})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功终止进程 {process_name} (PIDs: {terminated_pids})")
        else:
            logger.info(f"未找到进程 {process_name}", extra={'event_type': EventType.PROCESS_CHECK, 'process_name': process_name})
    except psutil.AccessDenied as e:
        logger.error(f"访问被拒绝，无法终止进程 {process_name}: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': process_name, 'error': str(e), 'error_type': 'access_denied'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问被拒绝，无法终止进程 {process_name}: {str(e)}")
    except psutil.NoSuchProcess as e:
        logger.warning(f"进程不存在，无法终止 {process_name}: {str(e)}", extra={'event_type': EventType.WARNING, 'process_name': process_name, 'error': str(e), 'error_type': 'no_such_process'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 进程不存在，无法终止 {process_name}: {str(e)}")
    except Exception as e:
        logger.error(f"终止进程 {process_name} 时出错: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': process_name, 'error': str(e), 'error_type': 'terminate_error'})
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
        try:
            response = requests.get(url, timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False
    
    # 使用线程池运行HTTP请求，避免阻塞主线程
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(check)
        try:
            result = future.result(timeout=timeout+2)  # 设置额外超时
            return result
        except:
            return False

def check_and_manage_llbot_async(config):
    """异步检查并管理llbot进程"""
    try:
        # 检查必要配置项是否为空
        if not config['http_check']['url']:
            logger.warning("HTTP检查地址未配置", extra={'event_type': EventType.WARNING, 'check_type': 'http_url'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: HTTP检查地址未配置")
            event_manager.publish(EventType.WARNING, {
                'message': 'HTTP检查地址未配置',
                'config_item': 'http_url'
            })
            return
        
        # 异步检查http://localhost:3080是否可访问
        try:
            is_accessible = async_http_check(config['http_check']['url'], config['http_check']['timeout'])
        except requests.exceptions.Timeout:
            logger.warning(f"HTTP检查超时: {config['http_check']['url']}", extra={'event_type': EventType.WARNING, 'url': config['http_check']['url'], 'error_type': 'timeout'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP检查超时: {config['http_check']['url']}")
            event_manager.publish(EventType.WARNING, {
                'message': f'HTTP检查超时: {config['http_check']['url']}',
                'url': config['http_check']['url'],
                'error_type': 'timeout'
            })
            restart_llbot_with_cleanup(config)
            return
        except requests.exceptions.ConnectionError:
            logger.warning(f"HTTP连接错误: {config['http_check']['url']}", extra={'event_type': EventType.WARNING, 'url': config['http_check']['url'], 'error_type': 'connection_error'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP连接错误: {config['http_check']['url']}")
            event_manager.publish(EventType.WARNING, {
                'message': f'HTTP连接错误: {config['http_check']['url']}',
                'url': config['http_check']['url'],
                'error_type': 'connection_error'
            })
            restart_llbot_with_cleanup(config)
            return
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP请求异常: {str(e)}", extra={'event_type': EventType.ERROR, 'url': config['http_check']['url'], 'error_type': 'request_error', 'error': str(e)})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP请求异常: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'HTTP请求异常: {str(e)}',
                'url': config['http_check']['url'],
                'error_type': 'request_error',
                'error': str(e)
            })
            restart_llbot_with_cleanup(config)
            return
        except Exception as e:
            logger.error(f"HTTP检查未知错误: {str(e)}", extra={'event_type': EventType.ERROR, 'url': config['http_check']['url'], 'error_type': 'unknown_error', 'error': str(e)})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] HTTP检查未知错误: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'HTTP检查未知错误: {str(e)}',
                'url': config['http_check']['url'],
                'error_type': 'unknown_error',
                'error': str(e)
            })
            restart_llbot_with_cleanup(config)
            return
        
        if is_accessible:
            logger.info(f"HTTP检查成功: {config['http_check']['url']}", extra={'event_type': EventType.HTTP_CHECK, 'url': config['http_check']['url'], 'status': 'success'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {config['http_check']['url']} 可访问...")
            event_manager.publish(EventType.HTTP_CHECK, {
                'url': config['http_check']['url'],
                'status': 'success'
            })
            
            # 检查llbot.exe或lucky-lillia-desktop.exe是否仍在运行
            if not config['llbot']['path']:
                logger.warning("llbot路径未配置", extra={'event_type': EventType.WARNING, 'check_type': 'llbot_path'})
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot路径未配置")
                return
                
            try:
                llbot_running = False
                llbot_process_name = os.path.basename(config['llbot']['path']).lower()
                # 同时检查原进程名和新进程名
                possible_names = [llbot_process_name, 'lucky-lillia-desktop.exe']
                
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'].lower() in possible_names:
                        llbot_running = True
                        break
                
                if llbot_running:
                    logger.info(f"llbot进程正在运行", extra={'event_type': EventType.PROCESS_CHECK, 'process_name': llbot_process_name, 'status': 'running'})
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {(llbot_process_name or 'llbot')} 进程正在运行...")
                    event_manager.publish(EventType.PROCESS_CHECK, {
                        'process_name': llbot_process_name,
                        'status': 'running'
                    })
                else:
                    # llbot.exe未运行但网站应该可访问，清理相关进程后重新启动它
                    logger.warning("llbot进程未运行但网站可访问，正在重启", extra={'event_type': EventType.WARNING, 'process_name': llbot_process_name})
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {(llbot_process_name or 'llbot')} 进程未运行但网站应该可访问，正在清理相关进程并重启...")
                    event_manager.publish(EventType.WARNING, {
                        'message': 'llbot进程未运行但网站可访问，正在重启',
                        'process_name': llbot_process_name
                    })
                    restart_llbot_with_cleanup(config)
            except psutil.AccessDenied:
                logger.error("访问进程信息被拒绝，可能需要管理员权限", extra={'event_type': EventType.ERROR, 'error_type': 'access_denied'})
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问进程信息被拒绝，可能需要管理员权限")
                event_manager.publish(EventType.ERROR, {
                    'message': '访问进程信息被拒绝',
                    'error_type': 'access_denied'
                })
            except psutil.NoSuchProcess:
                logger.warning("尝试访问不存在的进程", extra={'event_type': EventType.WARNING, 'error_type': 'no_such_process'})
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试访问不存在的进程")
                event_manager.publish(EventType.WARNING, {
                    'message': '尝试访问不存在的进程',
                    'error_type': 'no_such_process'
                })
            except Exception as e:
                logger.error(f"检查llbot进程时发生错误: {str(e)}", extra={'event_type': EventType.ERROR, 'error_type': 'process_check_error', 'error': str(e)})
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查llbot进程时发生错误: {str(e)}")
                event_manager.publish(EventType.ERROR, {
                    'message': f'检查llbot进程时发生错误: {str(e)}',
                    'error_type': 'process_check_error',
                    'error': str(e)
                })
        else:
            logger.warning(f"HTTP检查失败: {config['http_check']['url']}", extra={'event_type': EventType.HTTP_CHECK, 'url': config['http_check']['url'], 'status': 'failure'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {config['http_check']['url']} 不可访问，正在终止相关进程并重启llbot...")
            event_manager.publish(EventType.HTTP_CHECK, {
                'url': config['http_check']['url'],
                'status': 'failure'
            })
            restart_llbot_with_cleanup(config)
    except KeyError as e:
        logger.error(f"配置错误: 缺少必需的配置项 {e}", extra={'event_type': EventType.ERROR, 'error_type': 'config_error', 'missing_key': str(e)})
        event_manager.publish(EventType.ERROR, {
            'message': f'配置错误: 缺少必需的配置项 {e}',
            'missing_key': str(e),
            'error_type': 'config_error'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise
    except Exception as e:
        logger.error(f"检查llbot时发生未知错误: {str(e)}", extra={'event_type': EventType.ERROR, 'error_type': 'unknown_error', 'error': str(e)})
        event_manager.publish(EventType.ERROR, {
            'message': f'检查llbot时发生未知错误: {str(e)}',
            'process': 'llbot',
            'error_type': 'unknown_error',
            'error': str(e)
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查llbot时发生未知错误: {str(e)}")
        raise

def restart_llbot_with_cleanup(config):
    """清理相关进程后重启llbot"""
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 启动成功")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 未找到，请验证路径: {config['llbot']['path']}")
    except KeyError as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise

def check_and_manage_yunzai_async(config):
    """异步检查并管理Yunzai进程"""
    try:
        # 检查Redis是否运行
        if not config['redis']['path']:
            logger.warning("Redis路径未配置", extra={'event_type': EventType.WARNING, 'check_type': 'redis_path'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Redis路径未配置")
            event_manager.publish(EventType.WARNING, {
                'message': 'Redis路径未配置',
                'config_item': 'redis_path'
            })
            return
            
        try:
            redis_running = False
            redis_process_name = os.path.basename(config['redis']['path'])
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == redis_process_name.lower():
                    redis_running = True
                    break
        except psutil.AccessDenied:
            logger.error("访问Redis进程信息被拒绝", extra={'event_type': EventType.ERROR, 'process_name': redis_process_name, 'error_type': 'access_denied'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问Redis进程信息被拒绝")
            event_manager.publish(EventType.ERROR, {
                'message': '访问Redis进程信息被拒绝',
                'process_name': redis_process_name,
                'error_type': 'access_denied'
            })
            redis_running = False  # 假设Redis未运行
        except psutil.NoSuchProcess:
            logger.warning("Redis进程不存在", extra={'event_type': EventType.WARNING, 'process_name': redis_process_name, 'error_type': 'no_such_process'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Redis进程不存在")
            event_manager.publish(EventType.WARNING, {
                'message': 'Redis进程不存在',
                'process_name': redis_process_name,
                'error_type': 'no_such_process'
            })
            redis_running = False
        except Exception as e:
            logger.error(f"检查Redis进程时出错: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': redis_process_name, 'error': str(e), 'error_type': 'process_check_error'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Redis进程时出错: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'检查Redis进程时出错: {str(e)}',
                'process_name': redis_process_name,
                'error': str(e),
                'error_type': 'process_check_error'
            })
            redis_running = False  # 假设Redis未运行
        
        if not redis_running:
            logger.info(f"Redis未运行，正在启动: {redis_process_name}", extra={'event_type': EventType.PROCESS_START, 'process_name': redis_process_name})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 未运行，正在启动Redis服务器...")
            event_manager.publish(EventType.PROCESS_START, {
                'process_name': redis_process_name,
                'action': 'start_redis'
            })
            try:
                redis_dir = os.path.dirname(config['redis']['path'])
                if not os.path.exists(redis_dir):
                    logger.error(f"Redis目录不存在: {redis_dir}", extra={'event_type': EventType.ERROR, 'redis_dir': redis_dir, 'error_type': 'dir_not_found'})
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Redis目录不存在: {redis_dir}")
                    event_manager.publish(EventType.ERROR, {
                        'message': f'Redis目录不存在: {redis_dir}',
                        'redis_dir': redis_dir,
                        'error_type': 'dir_not_found'
                    })
                    return
                    
                os.chdir(redis_dir)
                # 使用管理员权限启动Redis
                result = subprocess.Popen([
                    "powershell", 
                    "-Command", 
                    f"Start-Process '{config['redis']['path']}' -WorkingDirectory '{redis_dir}' -Verb RunAs"
                ])
                time.sleep(3)  # 等待Redis启动
                logger.info("Redis服务器启动成功", extra={'event_type': EventType.PROCESS_START, 'process_name': redis_process_name})
                event_manager.publish(EventType.PROCESS_START, {
                    'process_name': redis_process_name,
                    'status': 'success'
                })
            except FileNotFoundError:
                logger.error(f"Redis可执行文件未找到: {config['redis']['path']}", extra={'event_type': EventType.ERROR, 'process_name': redis_process_name, 'error_type': 'file_not_found', 'file_path': config['redis']['path']})
                event_manager.publish(EventType.ERROR, {
                    'message': f'Redis可执行文件未找到: {config['redis']['path']}',
                    'process_name': redis_process_name,
                    'error_type': 'file_not_found',
                    'file_path': config['redis']['path']
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Redis可执行文件未找到: {config['redis']['path']}")
            except subprocess.SubprocessError as e:
                logger.error(f"启动Redis服务器时出错: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': redis_process_name, 'error': str(e), 'error_type': 'subprocess_error'})
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Redis服务器时出错: {str(e)}',
                    'process_name': redis_process_name,
                    'error': str(e),
                    'error_type': 'subprocess_error'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Redis服务器时出错: {str(e)}")
            except Exception as e:
                logger.error(f"启动Redis服务器时发生未知错误: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': redis_process_name, 'error': str(e), 'error_type': 'unknown_error'})
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Redis服务器时发生未知错误: {str(e)}',
                    'process_name': redis_process_name,
                    'error': str(e),
                    'error_type': 'unknown_error'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Redis服务器时发生未知错误: {str(e)}")
        else:
            logger.info("Redis已在运行", extra={'event_type': EventType.PROCESS_CHECK, 'process_name': redis_process_name, 'status': 'running'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 已在运行...")
            event_manager.publish(EventType.PROCESS_CHECK, {
                'process_name': redis_process_name,
                'status': 'running'
            })
        
        # 检查Yunzai是否运行
        # 使用固定的process_name而不从配置中获取
        process_name = 'git-bash.exe'
        
        try:
            yunzai_running = False
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == process_name.lower():
                    yunzai_running = True
                    break
        except psutil.AccessDenied:
            logger.error("访问Yunzai进程信息被拒绝", extra={'event_type': EventType.ERROR, 'process_name': process_name, 'error_type': 'access_denied'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问Yunzai进程信息被拒绝")
            event_manager.publish(EventType.ERROR, {
                'message': '访问Yunzai进程信息被拒绝',
                'process_name': process_name,
                'error_type': 'access_denied'
            })
            yunzai_running = False  # 假设Yunzai未运行
        except psutil.NoSuchProcess:
            logger.warning("Yunzai进程不存在", extra={'event_type': EventType.WARNING, 'process_name': process_name, 'error_type': 'no_such_process'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程不存在")
            event_manager.publish(EventType.WARNING, {
                'message': 'Yunzai进程不存在',
                'process_name': process_name,
                'error_type': 'no_such_process'
            })
            yunzai_running = False
        except Exception as e:
            logger.error(f"检查Yunzai进程时出错: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': process_name, 'error': str(e), 'error_type': 'process_check_error'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Yunzai进程时出错: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'检查Yunzai进程时出错: {str(e)}',
                'process_name': process_name,
                'error': str(e),
                'error_type': 'process_check_error'
            })
            yunzai_running = False  # 假设Yunzai未运行
        
        if not yunzai_running:
            logger.info("Yunzai未运行，正在启动", extra={'event_type': EventType.PROCESS_START, 'process_name': process_name})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程...")
            event_manager.publish(EventType.PROCESS_START, {
                'process_name': process_name,
                'action': 'start_yunzai'
            })
            try:
                if not config['yunzai']['git_bash_path']:
                    logger.warning("Git Bash路径未配置", extra={'event_type': EventType.WARNING, 'check_type': 'git_bash_path'})
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Git Bash路径未配置")
                    return
                if not config['yunzai']['bash_directory']:
                    logger.warning("Yunzai目录未配置", extra={'event_type': EventType.WARNING, 'check_type': 'bash_directory'})
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Yunzai目录未配置")
                    return
                if not os.path.exists(config['yunzai']['bash_directory']):
                    logger.error(f"Yunzai目录不存在: {config['yunzai']['bash_directory']}", extra={'event_type': EventType.ERROR, 'bash_directory': config['yunzai']['bash_directory'], 'error_type': 'dir_not_found'})
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai目录不存在: {config['yunzai']['bash_directory']}")
                    return
                
                # 使用git-bash启动Yunzai，使用固定命令"node app"
                result = subprocess.Popen([
                    config['yunzai']['git_bash_path'],
                    "-c",
                    f"cd '{config['yunzai']['bash_directory']}' && node app"
                ])
                logger.info("Yunzai进程已启动", extra={'event_type': EventType.PROCESS_START, 'process_name': process_name})
                event_manager.publish(EventType.PROCESS_START, {
                    'process_name': process_name,
                    'status': 'success'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已启动")
            except FileNotFoundError as e:
                logger.error(f"Git Bash可执行文件或Yunzai目录未找到: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': process_name, 'error': str(e), 'error_type': 'file_not_found'})
                event_manager.publish(EventType.ERROR, {
                    'message': f'Git Bash可执行文件或Yunzai目录未找到: {str(e)}',
                    'process_name': process_name,
                    'error': str(e),
                    'error_type': 'file_not_found'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Git Bash可执行文件或Yunzai目录未找到: {str(e)}")
            except subprocess.SubprocessError as e:
                logger.error(f"启动Yunzai进程时出错: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': process_name, 'error': str(e), 'error_type': 'subprocess_error'})
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Yunzai进程时出错: {str(e)}',
                    'process_name': process_name,
                    'error': str(e),
                    'error_type': 'subprocess_error'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时出错: {str(e)}")
            except Exception as e:
                logger.error(f"启动Yunzai进程时发生未知错误: {str(e)}", extra={'event_type': EventType.ERROR, 'process_name': process_name, 'error': str(e), 'error_type': 'unknown_error'})
                event_manager.publish(EventType.ERROR, {
                    'message': f'启动Yunzai进程时发生未知错误: {str(e)}',
                    'process_name': process_name,
                    'error': str(e),
                    'error_type': 'unknown_error'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时发生未知错误: {str(e)}")
        else:
            logger.info("Yunzai已在运行", extra={'event_type': EventType.PROCESS_CHECK, 'process_name': process_name, 'status': 'running'})
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已在运行...")
            event_manager.publish(EventType.PROCESS_CHECK, {
                'process_name': process_name,
                'status': 'running'
            })
    except KeyError as e:
        logger.error(f"配置错误: 缺少必需的配置项 {e}", extra={'event_type': EventType.ERROR, 'missing_key': str(e), 'error_type': 'config_error'})
        event_manager.publish(EventType.ERROR, {
            'message': f'配置错误: 缺少必需的配置项 {e}',
            'missing_key': str(e),
            'error_type': 'config_error'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise
    except Exception as e:
        logger.error(f"检查Yunzai时发生未知错误: {str(e)}", extra={'event_type': EventType.ERROR, 'error': str(e), 'process': 'yunzai', 'error_type': 'unknown_error'})
        event_manager.publish(EventType.ERROR, {
            'message': f'检查Yunzai时发生未知错误: {str(e)}',
            'process': 'yunzai',
            'error': str(e),
            'error_type': 'unknown_error'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Yunzai时发生未知错误: {str(e)}")
        raise

def run_monitor_loop(config):
    """运行监控循环 - 使用多线程并行监控"""
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
    
    llbot_thread.start()
    yunzai_thread.start()
    
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
    # 启动事件管理器
    event_manager.start()
    
    # 加载配置
    config = load_config()

    # 检查管理员权限，如果未以管理员权限运行则请求权限
    if not is_admin():
        logger.info("检查到未以管理员权限运行，请求管理员权限", extra={'event_type': EventType.PROCESS_CHECK, 'status': 'not_admin'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 脚本需要管理员权限才能正常工作")
        if not run_as_admin():
            logger.error("无法获取管理员权限，脚本退出", extra={'event_type': EventType.ERROR, 'reason': 'cannot_acquire'})
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
    
    logger.info("开始监控llbot和Yunzai进程", extra={'event_type': EventType.PROCESS_START})
    event_manager.publish(EventType.PROCESS_START, {
        'message': '开始监控llbot和Yunzai进程'
    })
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始监控llbot和Yunzai进程...")
    print("按 Ctrl+C 退出监控")
    
    # 设置运行标志
    run_monitor_loop.running = True
    
    try:
        # 运行监控循环
        run_monitor_loop(config)
    except KeyboardInterrupt:
        logger.info("监控已停止 (用户中断)", extra={'event_type': EventType.PROCESS_STOP, 'reason': 'user_interrupt'})
        event_manager.publish(EventType.PROCESS_STOP, {
            'message': '监控已停止',
            'reason': 'user_interrupt'
        })
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控已停止")
    except Exception as e:
        logger.error(f"监控循环中发生错误: {str(e)}", extra={'event_type': EventType.ERROR, 'error': str(e)})
        event_manager.publish(EventType.ERROR, {
            'message': f'监控循环中发生错误: {str(e)}',
            'error': str(e)
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控循环中发生错误: {str(e)}")

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
