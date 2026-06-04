# -*- coding: utf-8 -*-
"""
llbot Yunzai 监控系统 - 主入口文件
用于监控和管理 llbot、Yunzai 和 Redis 进程
"""
import os
import sys
import time
import threading
import psutil
from datetime import datetime

# 导入自定义模块
from constants import EventType
from logger import get_logger
from event_manager import get_event_manager
from config import load_config
from process_manager import (
    is_admin,
    run_as_admin,
    check_admin,
    get_global_manual_stop_status
)
from monitor import check_and_manage_llbot_async, check_and_manage_yunzai_async, async_http_check
from monitor_status import (
    set_monitor_running,
    start_monitor_status_update,
    stop_monitor_status_update,
    cleanup_monitor_status
)
from web_server import (
    flask_available,
    init_web_server,
    start_web_server,
    current_config,
    current_status,
    manual_stop_status
)
from update_checker import check_and_update_resources
from auto_login import apply_config_from_dict, get_auto_login_status
from git_update_checker import start_git_update_monitor, stop_git_update_monitor
from onebot_client import init_onebot_client
from onebot_handlers import register_all_handlers
from image_service_manager import get_image_service_manager

# 初始化日志记录器
logger = get_logger()

# 初始化事件管理器
event_manager = get_event_manager()

def run_monitor_loop(config):
    """运行监控循环 - 使用多线程并行监控"""
    # 设置监控状态为运行
    set_monitor_running(True)

    # 启动监控状态更新线程
    start_monitor_status_update()
    
    def update_status_periodically():
        """定期更新状态信息"""
        while getattr(run_monitor_loop, 'running', True):
            try:
                # 使用全局current_config以确保获取最新的配置
                local_config = current_config
                
                # 一次性获取所有进程信息，避免多次调用 psutil.process_iter() 导致的迭代器冲突
                try:
                    all_procs = []
                    for proc in psutil.process_iter(['name', 'pid']):
                        try:
                            all_procs.append(proc)
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            continue
                except Exception as e:
                    logger.warning(f"获取进程列表失败: {str(e)}", extra={
                        'event_type': EventType.WARNING,
                        'error': str(e),
                        'error_type': 'process_iter_error'
                    })
                    time.sleep(5)
                    continue
                
                # 检查llbot进程状态
                if local_config['llbot'].get('path'):
                    llbot_process_name = os.path.basename(local_config['llbot']['path']).lower()
                    possible_names = [llbot_process_name, 'lucky-lillia-desktop.exe']

                    llbot_running = False
                    llbot_pid = None
                    for proc in all_procs:
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
                for proc in all_procs:
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
                    for proc in all_procs:
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
                
                # 更新自动重启状态
                auto_restart_enabled = local_config.get('auto_restart', {}).get('enabled', True)
                current_status['auto_restart'] = {'enabled': auto_restart_enabled}

                # 检查图片服务状态
                try:
                    from image_service_manager import get_image_service_manager
                    image_manager = get_image_service_manager()
                    image_running = image_manager.is_running()
                    image_pid = image_manager.get_pid()
                    current_status['image_service'] = {'running': image_running, 'pid': image_pid}
                except:
                    current_status['image_service'] = {'running': False, 'pid': None}

                # 同步手动停止状态 - 从Flask应用同步到全局变量
                try:
                    from process_manager import global_manual_stop_status
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
    
    # 启动Git更新检测线程（如果启用）
    if config.get('git_update', {}).get('enabled', False):
        start_git_update_monitor(config)
    
    # 启动OneBot客户端（如果启用）
    onebot_client = None
    if config.get('onebot', {}).get('enabled', False):
        try:
            onebot_client = init_onebot_client(config.get('onebot', {}))
            if onebot_client:
                # 注册所有指令处理器
                register_all_handlers(onebot_client)
                # 启动客户端
                onebot_client.start()
                logger.info("OneBot 客户端已启动", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client'
                })
        except Exception as e:
            logger.error(f"OneBot 客户端启动失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
    
    # 启动Web服务器（如果Flask可用）
    if flask_available:
        web_thread = threading.Thread(target=start_web_server, daemon=True)
        web_thread.start()
    
    # 保持主线程运行
    try:
        while getattr(run_monitor_loop, 'running', True):
            # 检查是否需要切换到管理员模式
            try:
                from monitor import get_need_elevate_to_admin
                if get_need_elevate_to_admin():
                    logger.info("检测到需要切换到管理员模式", extra={
                        'event_type': EventType.INFO,
                        'action': 'check_admin_flag',
                        'need_admin': True
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到需要切换到管理员模式,正在切换...")
                    
                    # 停止监控循环
                    run_monitor_loop.running = False
                    
                    # 调用 run_as_admin 并退出
                    run_as_admin()
                    
                    # 延迟退出,给 run_as_admin 时间执行
                    time.sleep(3)
                    sys.exit(0)
            except ImportError:
                # 如果导入失败,跳过检查
                pass
            
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止监控", extra={'event_type': EventType.PROCESS_STOP, 'reason': 'user_interrupt'})
        event_manager.publish(EventType.PROCESS_STOP, {
            'message': '收到中断信号',
            'reason': 'user_interrupt'
        })
    
    # 设置停止标志
    run_monitor_loop.running = False

    # 设置监控状态为停止
    set_monitor_running(False)

    # 停止监控状态更新线程
    stop_monitor_status_update()
    
    # 停止OneBot客户端
    if onebot_client:
        try:
            onebot_client.stop()
            logger.info("OneBot 客户端已停止", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_client'
            })
        except Exception as e:
            logger.error(f"OneBot 客户端停止失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
    
    # 停止Git更新检测线程
    stop_git_update_monitor()

    # 停止图片服务
    try:
        image_service_manager = get_image_service_manager()
        if image_service_manager.is_running():
            image_service_manager.stop()
            logger.info("图片生成服务已停止", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })
    except Exception as e:
        logger.error(f"停止图片服务失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'image_service',
            'error': str(e)
        })

    # 清理监控状态
    try:
        cleanup_monitor_status()
        logger.info("监控状态已清理", extra={
            'event_type': EventType.INFO,
            'feature': 'monitor_status'
        })
    except Exception as e:
        logger.error(f"清理监控状态失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'monitor_status',
            'error': str(e)
        })

def check_single_instance():
    """检查单实例，防止多个监控进程同时运行"""
    monitor_pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pids', 'monitor.pid')
    admin_marker_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pids', 'elevating_to_admin.marker')

    def safe_terminate_process(proc, timeout=5, pid=None):
        """安全地终止进程，避免阻塞

        Args:
            proc: psutil.Process 对象
            timeout: 超时时间（秒）
            pid: 进程 ID（用于日志）

        Returns:
            bool: 是否成功终止
        """
        pid = pid or proc.pid
        try:
            proc.terminate()
            # 使用轮询而不是 wait()，避免阻塞
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    if not psutil.pid_exists(pid):
                        logger.info(f"成功终止进程 (PID: {pid})", extra={
                            'event_type': EventType.INFO,
                            'pid': pid,
                            'action': 'process_terminated'
                        })
                        return True
                except:
                    return True  # 进程已不存在
                time.sleep(0.1)

            # 超时后尝试强制终止
            logger.warning(f"终止进程超时 (PID: {pid})，尝试强制终止", extra={
                'event_type': EventType.WARNING,
                'pid': pid,
                'action': 'terminate_timeout'
            })
            try:
                proc.kill()
                # 使用轮询检查进程是否已终止
                start_time = time.time()
                kill_timeout = 3
                while time.time() - start_time < kill_timeout:
                    try:
                        if not psutil.pid_exists(pid):
                            logger.info(f"已强制终止进程 (PID: {pid})", extra={
                                'event_type': EventType.INFO,
                                'pid': pid,
                                'action': 'process_killed'
                            })
                            return True
                    except:
                        return True  # 进程已不存在
                    time.sleep(0.1)
                logger.warning(f"强制终止进程超时 (PID: {pid})，放弃等待", extra={
                    'event_type': EventType.WARNING,
                    'pid': pid,
                    'action': 'kill_timeout'
                })
                return False
            except Exception as e:
                logger.warning(f"强制终止进程失败 (PID: {pid}): {str(e)}", extra={
                    'event_type': EventType.WARNING,
                    'pid': pid,
                    'error': str(e)
                })
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"访问进程失败 (PID: {pid}): {str(e)}", extra={
                'event_type': EventType.WARNING,
                'pid': pid,
                'error': str(e)
            })
            return True  # 进程已不存在或无权限访问，视为成功
        except Exception as e:
            logger.warning(f"终止进程时发生意外错误 (PID: {pid}): {str(e)}", extra={
                'event_type': EventType.WARNING,
                'pid': pid,
                'error': str(e)
            })
            return False

    try:
        # 检查是否有管理员权限提升标记
        if os.path.exists(admin_marker_file):
            try:
                with open(admin_marker_file, 'r') as f:
                    old_pid = int(f.read().strip())
                
                # 等待旧进程退出（最多等待5秒）
                for i in range(5):
                    if not psutil.pid_exists(old_pid):
                        logger.info(f"旧进程 (PID: {old_pid}) 已退出，清理标记文件", extra={
                            'event_type': EventType.INFO,
                            'old_pid': old_pid,
                            'action': 'cleanup_admin_marker'
                        })
                        os.remove(admin_marker_file)
                        break
                    time.sleep(1)
                else:
                    # 超时后强制清理标记文件
                    logger.warning(f"旧进程 (PID: {old_pid}) 未及时退出，强制清理标记文件", extra={
                        'event_type': EventType.WARNING,
                        'old_pid': old_pid,
                        'action': 'force_cleanup_admin_marker'
                    })
                    os.remove(admin_marker_file)
            except Exception as e:
                logger.warning(f"处理管理员标记文件失败: {str(e)}", extra={
                    'event_type': EventType.WARNING,
                    'error': str(e)
                })
                try:
                    os.remove(admin_marker_file)
                except:
                    pass
        
        # 检查 PID 文件是否存在
        old_pid = None  # 初始化 old_pid 变量，避免未定义错误
        if os.path.exists(monitor_pid_file):
            with open(monitor_pid_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    logger.warning("monitor.pid文件内容为空，将被清理", extra={
                        'event_type': EventType.WARNING,
                        'action': 'cleanup_empty_pid_file'
                    })
                    os.remove(monitor_pid_file)
                else:
                    # 只读取第一行作为 PID（忽略可能的时间戳等其他信息）
                    first_line = content.split('\n')[0].strip()
                    # 验证内容是否为有效的数字（防止二进制数据或其他无效内容）
                    if not first_line.isdigit():
                        logger.warning(f"monitor.pid文件内容无效: {repr(first_line)}，将被清理", extra={
                            'event_type': EventType.WARNING,
                            'action': 'cleanup_invalid_pid_content',
                            'invalid_content': repr(first_line)
                        })
                        try:
                            # 尝试查找并终止可能相关的 Python 监控进程
                            # 由于 PID 无效，无法精确定位，但可以尝试查找所有运行 main.py 的 Python 进程
                            current_pid = os.getpid()
                            terminated = False
                            candidates = []

                            # 首先收集所有候选进程，避免在迭代过程中修改进程列表
                            try:
                                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                                    try:
                                        proc_name = proc.info['name'].lower()
                                        if 'python' in proc_name or 'pythonw' in proc_name:
                                            cmdline = proc.info.get('cmdline', [])
                                            if cmdline:
                                                cmdline_str = ' '.join(cmdline).lower()
                                                script_path = os.path.abspath(__file__).lower()
                                                # 检查是否是运行监控脚本的进程
                                                if 'main.py' in cmdline_str or script_path in cmdline_str:
                                                    # 保护当前进程，防止误杀自己
                                                    if proc.info['pid'] != current_pid:
                                                        candidates.append(proc.info['pid'])
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        continue
                                    except Exception as e:
                                        logger.warning(f"处理进程信息时出错: {str(e)}", extra={
                                            'event_type': EventType.WARNING,
                                            'error': str(e)
                                        })
                            except Exception as e:
                                logger.warning(f"遍历进程列表时出错: {str(e)}", extra={
                                    'event_type': EventType.WARNING,
                                    'error': str(e)
                                })

                            # 终止候选进程（只终止一个，避免误杀）
                            for pid in candidates:
                                if terminated:
                                    break
                                try:
                                    proc = psutil.Process(pid)
                                    logger.info(f"终止可能与无效 PID 相关的监控进程 (PID: {pid})", extra={
                                        'event_type': EventType.INFO,
                                        'pid': pid,
                                        'action': 'terminate_related_process'
                                    })
                                    proc.terminate()
                                    # 使用轮询而不是 wait()，避免阻塞
                                    import signal
                                    start_time = time.time()
                                    timeout = 5
                                    while time.time() - start_time < timeout:
                                        try:
                                            if not psutil.pid_exists(pid):
                                                logger.info(f"成功终止进程 (PID: {pid})", extra={
                                                    'event_type': EventType.INFO,
                                                    'pid': pid,
                                                    'action': 'process_terminated'
                                                })
                                                terminated = True
                                                break
                                        except:
                                            break
                                        time.sleep(0.1)

                                    if not terminated and psutil.pid_exists(pid):
                                        logger.warning(f"终止进程超时 (PID: {pid})，尝试强制终止", extra={
                                            'event_type': EventType.WARNING,
                                            'pid': pid,
                                            'action': 'terminate_timeout'
                                        })
                                        try:
                                            proc.kill()
                                            # 使用轮询检查进程是否已终止
                                            start_time = time.time()
                                            timeout = 3
                                            while time.time() - start_time < timeout:
                                                try:
                                                    if not psutil.pid_exists(pid):
                                                        logger.info(f"已强制终止进程 (PID: {pid})", extra={
                                                            'event_type': EventType.INFO,
                                                            'pid': pid,
                                                            'action': 'process_killed'
                                                        })
                                                        terminated = True
                                                        break
                                                except:
                                                    break
                                                time.sleep(0.1)
                                            if not terminated:
                                                logger.warning(f"强制终止进程超时 (PID: {pid})，放弃等待", extra={
                                                    'event_type': EventType.WARNING,
                                                    'pid': pid,
                                                    'action': 'kill_timeout'
                                                })
                                        except Exception as e:
                                            logger.warning(f"强制终止进程失败 (PID: {pid}): {str(e)}", extra={
                                                'event_type': EventType.WARNING,
                                                'pid': pid,
                                                'error': str(e)
                                            })
                                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                                    logger.warning(f"访问进程失败 (PID: {pid}): {str(e)}", extra={
                                        'event_type': EventType.WARNING,
                                        'pid': pid,
                                        'error': str(e)
                                    })
                                except Exception as e:
                                    logger.warning(f"终止进程时发生意外错误 (PID: {pid}): {str(e)}", extra={
                                        'event_type': EventType.WARNING,
                                        'pid': pid,
                                        'error': str(e)
                                    })
                        except Exception as e:
                            logger.warning(f"尝试终止相关进程时出错: {str(e)}", extra={
                                'event_type': EventType.WARNING,
                                'error': str(e)
                            })
                        try:
                            os.remove(monitor_pid_file)
                        except:
                            pass
                    else:
                        old_pid = int(first_line)

                    # 检查旧进程是否仍在运行（只有当 old_pid 被成功赋值时才检查）
                    if old_pid is not None and psutil.pid_exists(old_pid):
                        # 进一步验证进程名称和命令行，确保确实是 Python 监控进程
                        try:
                            proc = psutil.Process(old_pid)
                            proc_name = proc.name().lower()
                            
                            # 验证是否是 Python 进程
                            if 'python' in proc_name or 'pythonw' in proc_name:
                                # 验证命令行参数，确保是监控脚本
                                cmdline = proc.cmdline()
                                is_monitor_process = False
                                
                                if cmdline:
                                    cmdline_str = ' '.join(cmdline).lower()
                                    # 检查命令行中是否包含 main.py 或当前脚本路径
                                    if 'main.py' in cmdline_str or 'main.py' in ' '.join(cmdline).lower():
                                        is_monitor_process = True
                                    # 检查是否包含项目路径（更严格的验证）
                                    script_path = os.path.abspath(__file__).lower()
                                    if script_path in cmdline_str:
                                        is_monitor_process = True
                                
                                if is_monitor_process:
                                    logger.warning(f"监控进程已在运行 (PID: {old_pid})，将终止旧进程并启动新实例", extra={
                                        'event_type': EventType.WARNING,
                                        'existing_pid': old_pid,
                                        'process_name': proc_name,
                                        'action': 'terminate_old_monitor_process'
                                    })
                                    print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控进程已在运行 (PID: {old_pid})，将终止旧进程并启动新实例")
                                    if safe_terminate_process(proc, timeout=10, pid=old_pid):
                                        logger.info(f"已终止旧监控进程 PID: {old_pid}", extra={
                                            'event_type': EventType.INFO,
                                            'old_pid': old_pid,
                                            'action': 'old_monitor_terminated'
                                        })
                                        print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止旧监控进程")
                                    else:
                                        logger.warning(f"终止旧监控进程失败或超时 (PID: {old_pid})，但继续启动新实例", extra={
                                            'event_type': EventType.WARNING,
                                            'old_pid': old_pid,
                                            'action': 'terminate_failed'
                                        })
                                        print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 终止旧监控进程失败或超时，但继续启动新实例")
                                    # 继续执行，不返回 False，允许新实例启动
                                else:
                                    # 是 Python 进程但不是监控脚本，可能是错误的 PID，终止进程并清理文件
                                    logger.info(f"PID {old_pid} 是 Python 进程但不是监控脚本，终止进程并清理 PID 文件", extra={
                                        'event_type': EventType.INFO,
                                        'old_pid': old_pid,
                                        'process_name': proc_name,
                                        'cmdline': cmdline,
                                        'action': 'terminate_and_cleanup_non_monitor_pid'
                                    })
                                    safe_terminate_process(proc, timeout=5, pid=old_pid)
                                    logger.info(f"已终止进程 PID: {old_pid}", extra={
                                        'event_type': EventType.INFO,
                                        'old_pid': old_pid,
                                        'action': 'process_terminated'
                                    })
                                    try:
                                        os.remove(monitor_pid_file)
                                    except:
                                        pass
                            else:
                                # PID 文件中的进程不是 Python 进程，可能是错误的 PID，终止进程并清理文件
                                logger.info(f"PID {old_pid} 不是 Python 进程 (名称: {proc_name})，终止进程并清理 PID 文件", extra={
                                    'event_type': EventType.INFO,
                                    'old_pid': old_pid,
                                    'process_name': proc_name,
                                    'action': 'terminate_and_cleanup_invalid_pid'
                                })
                                safe_terminate_process(proc, timeout=5, pid=old_pid)
                                logger.info(f"已终止进程 PID: {old_pid}", extra={
                                    'event_type': EventType.INFO,
                                    'old_pid': old_pid,
                                    'action': 'process_terminated'
                                })
                                try:
                                    os.remove(monitor_pid_file)
                                except:
                                    pass
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # 进程不存在或无法访问，清理 PID 文件
                            pass
                    else:
                        # 旧进程已不存在，清理 PID 文件
                        if old_pid is not None:
                            logger.info(f"检测到旧的监控进程 (PID: {old_pid}) 已不存在，清理 PID 文件", extra={
                                'event_type': EventType.INFO,
                                'old_pid': old_pid,
                                'action': 'cleanup_old_pid'
                            })
                        else:
                            logger.info("检测到旧的监控进程已不存在，清理 PID 文件", extra={
                                'event_type': EventType.INFO,
                                'action': 'cleanup_old_pid'
                            })
                        try:
                            os.remove(monitor_pid_file)
                        except:
                            pass
        
        # 写入当前进程的 PID
        with open(monitor_pid_file, 'w') as f:
            f.write(str(os.getpid()))
        
        logger.info(f"写入监控进程 PID: {os.getpid()}", extra={
            'event_type': EventType.INFO,
            'current_pid': os.getpid(),
            'pid_file': monitor_pid_file
        })
        return True
        
    except Exception as e:
        logger.error(f"单实例检查失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        # 如果检查失败，允许继续运行（避免因检查失败导致无法启动）
        return True

def cleanup_monitor_pid():
    """清理监控进程的 PID 文件"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # 如果 __file__ 未定义（例如在交互式环境中），使用当前工作目录
        script_dir = os.getcwd()
    
    monitor_pid_file = os.path.join(script_dir, 'pids', 'monitor.pid')
    try:
        if os.path.exists(monitor_pid_file):
            os.remove(monitor_pid_file)
            logger.info(f"已清理监控进程 PID 文件", extra={
                'event_type': EventType.INFO,
                'action': 'cleanup_monitor_pid'
            })
    except Exception as e:
        logger.error(f"清理监控进程 PID 文件失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })

def main():
    """主函数"""
    start_time = time.time()

    def safe_terminate_process_main(pid, timeout=5):
        """安全地终止进程，避免阻塞

        Args:
            pid: 进程 ID
            timeout: 超时时间（秒）

        Returns:
            bool: 是否成功终止
        """
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            # 使用轮询而不是 wait()，避免阻塞
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    if not psutil.pid_exists(pid):
                        logger.info(f"进程已终止 (PID: {pid})", extra={
                            'event_type': EventType.INFO,
                            'pid': pid
                        })
                        return True
                except:
                    return True  # 进程已不存在
                time.sleep(0.1)

            # 超时后尝试强制终止
            logger.warning(f"终止进程超时 (PID: {pid})，尝试强制终止", extra={
                'event_type': EventType.WARNING,
                'pid': pid
            })
            try:
                proc.kill()
                # 使用轮询检查进程是否已终止
                start_time = time.time()
                kill_timeout = 3
                while time.time() - start_time < kill_timeout:
                    try:
                        if not psutil.pid_exists(pid):
                            logger.info(f"进程已被强制终止 (PID: {pid})", extra={
                                'event_type': EventType.INFO,
                                'pid': pid
                            })
                            return True
                    except:
                        return True  # 进程已不存在
                    time.sleep(0.1)
                logger.warning(f"强制终止进程超时 (PID: {pid})，放弃等待", extra={
                    'event_type': EventType.WARNING,
                    'pid': pid
                })
                return False
            except Exception as e:
                logger.warning(f"强制终止进程失败 (PID: {pid}): {str(e)}", extra={
                    'event_type': EventType.WARNING,
                    'pid': pid,
                    'error': str(e)
                })
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"访问进程失败 (PID: {pid}): {str(e)}", extra={
                'event_type': EventType.WARNING,
                'pid': pid,
                'error': str(e)
            })
            return True  # 进程已不存在或无权限访问，视为成功
        except Exception as e:
            logger.warning(f"终止进程时发生意外错误 (PID: {pid}): {str(e)}", extra={
                'event_type': EventType.WARNING,
                'pid': pid,
                'error': str(e)
            })
            return False

    # 单实例检查 - 防止多个监控进程同时运行
    if not check_single_instance():
        return

    # 确保在退出时清理 PID 文件
    import atexit
    atexit.register(cleanup_monitor_pid)

    # 检查是否有旧进程正在关闭
    temp_pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pids', 'restarting_monitor.pid')
    if os.path.exists(temp_pid_file):
        try:
            with open(temp_pid_file, 'r') as f:
                old_pid = int(f.read().strip())

            logger.info(f"检测到旧进程 (PID: {old_pid}) 正在关闭，等待其退出...", extra={
                'event_type': EventType.INFO,
                'old_pid': old_pid
            })
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到旧进程 (PID: {old_pid}) 正在关闭，等待其退出...")

            # 等待旧进程退出，最多等待10秒
            for i in range(10):
                try:
                    if not psutil.pid_exists(old_pid):
                        logger.info(f"旧进程 (PID: {old_pid}) 已退出", extra={
                            'event_type': EventType.INFO,
                            'old_pid': old_pid
                        })
                        break
                except:
                    break
                time.sleep(1)
            else:
                # 超时后强制终止旧进程
                safe_terminate_process_main(old_pid, timeout=5)
                logger.info(f"旧进程 (PID: {old_pid}) 已终止（或尝试终止）", extra={
                    'event_type': EventType.INFO,
                    'old_pid': old_pid
                })

            # 清理临时文件
            try:
                os.remove(temp_pid_file)
            except:
                pass
        except Exception as e:
            logger.warning(f"检查旧进程失败: {str(e)}", extra={
                'event_type': EventType.WARNING,
                'error': str(e)
            })

    logger.info("监控程序开始启动", extra={
        'event_type': EventType.PROCESS_START,
        'start_time': __import__('datetime').datetime.fromtimestamp(start_time).isoformat(),
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
        current_config.clear()
        current_config.update(config)
        
        logger.info("配置加载完成", extra={
            'event_type': EventType.CONFIG_LOAD,
            'action': 'load_config_complete',
            'config_keys': list(config.keys()) if config else [],
            'load_duration': f"{time.time() - start_time:.3f}s"
        })

        # 检查前端资源更新
        logger.info("开始检查前端资源更新", extra={
            'event_type': EventType.INFO,
            'action': 'check_frontend_updates'
        })
        try:
            update_result = check_and_update_resources()
            if update_result['updated'] > 0:
                print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前端资源已更新 {update_result['updated']} 个文件")
            elif update_result['failed'] > 0:
                print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前端资源更新检查失败 {update_result['failed']} 个文件")
            else:
                print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前端资源已是最新版本")
        except Exception as e:
            logger.warning(f"前端资源更新检查失败: {str(e)}", extra={
                'event_type': EventType.WARNING,
                'error': str(e)
            })
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 前端资源更新检查失败，继续启动程序")

        # 自动启动图片生成服务
        logger.info("开始启动图片生成服务", extra={
            'event_type': EventType.INFO,
            'feature': 'image_service'
        })
        try:
            image_service_manager = get_image_service_manager()
            if image_service_manager.start(wait_ready=True, timeout=60):
                print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 图片生成服务启动成功")
                health = image_service_manager.health_check()
                if health.get('ready'):
                    print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 图片服务状态: {health.get('message')}")
                else:
                    print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 图片服务状态检查失败: {health.get('message')}")
            else:
                print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 图片生成服务启动失败")
                logger.warning("图片生成服务启动失败，但程序将继续运行", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'image_service'
                })
        except Exception as e:
            logger.error(f"图片生成服务启动异常: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service',
                'error': str(e)
            })
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 图片生成服务启动异常: {str(e)}")
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 程序将继续运行（部分功能可能不可用）")

        # 初始化Web服务器
        if flask_available:
            init_web_server(config, current_status)

        # 应用自动登录配置（如果配置中启用了）
        if config.get('auto_login', {}).get('enabled', False):
            logger.info("应用自动登录配置", extra={'event_type': 'auto_login_apply'})
            try:
                auto_login_result = apply_config_from_dict(config)
                if auto_login_result['success']:
                    print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 自动登录配置已应用")
                else:
                    print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 自动登录配置应用失败: {auto_login_result['message']}")
            except Exception as e:
                logger.warning(f"自动登录配置应用失败: {str(e)}", extra={'event_type': 'warning', 'error': str(e)})
        else:
            # 检查当前自动登录状态
            auto_login_status = get_auto_login_status()
            if auto_login_status['enabled']:
                logger.info("自动登录当前已启用（非本程序配置）", extra={'event_type': 'auto_login_detected'})

        # 检查管理员权限，如果未以管理员权限运行则请求权限
        is_admin_now = is_admin()
        logger.info(f"管理员权限检查", extra={
            'event_type': EventType.PROCESS_CHECK,
            'is_admin': is_admin_now,
            'check_time': __import__('datetime').datetime.now().isoformat()
        })
        
        if not is_admin_now:
            logger.info("检查到未以管理员权限运行，请求管理员权限", extra={
                'event_type': EventType.PROCESS_CHECK, 
                'status': 'not_admin',
                'suggestion': '以管理员权限运行以获得完整功能'
            })
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 脚本需要管理员权限才能正常工作")
            if not run_as_admin():
                logger.error("无法获取管理员权限，脚本退出", extra={
                    'event_type': EventType.ERROR, 
                    'reason': 'cannot_acquire',
                    'exit_time': __import__('datetime').datetime.now().isoformat()
                })
                event_manager.publish(EventType.ERROR, {
                    'message': '无法获取管理员权限',
                    'reason': 'cannot_acquire'
                })
                print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 无法获取管理员权限，脚本退出")
                cleanup_monitor_pid()
                return
            # 如果当前进程不是管理员权限，则退出，让新启动的管理员进程继续
            if not is_admin():
                # 不要清理 monitor.pid，让新管理员进程接管
                # atexit 会在进程退出时清理，但我们可以提前退出
                # 管理员进程会通过标记文件知道旧进程正在退出
                logger.info("非管理员进程退出，等待管理员进程启动", extra={
                    'event_type': EventType.INFO,
                    'action': 'non_admin_exit'
                })
                # 取消注册 atexit 处理器，避免清理 monitor.pid
                import atexit
                try:
                    atexit.unregister(cleanup_monitor_pid)
                except:
                    pass
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
        print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始监控llbot和Yunzai进程...")
        print("按 Ctrl+C 退出监控")
        
        # 设置运行标志
        run_monitor_loop.running = True
        
        try:
            # 运行监控循环
            run_monitor_loop(config)
            cleanup_monitor_pid()
        except KeyboardInterrupt:
            logger.info("监控已停止 (用户中断)", extra={
                'event_type': EventType.PROCESS_STOP, 
                'reason': 'user_interrupt',
                'stop_time': __import__('datetime').datetime.now().isoformat(),
                'total_runtime': f"{time.time() - start_time:.3f}s"
            })
            event_manager.publish(EventType.PROCESS_STOP, {
                'message': '监控已停止',
                'reason': 'user_interrupt',
                'total_runtime': f"{time.time() - start_time:.3f}s"
            })
            print(f"\n[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控已停止")
            cleanup_monitor_pid()
        except Exception as e:
            logger.error(f"监控循环中发生错误: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc(),
                'error_time': __import__('datetime').datetime.now().isoformat(),
                'total_runtime_until_error': f"{time.time() - start_time:.3f}s"
            })
            event_manager.publish(EventType.ERROR, {
                'message': f'监控循环中发生错误: {str(e)}',
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控循环中发生错误: {str(e)}")
            cleanup_monitor_pid()
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
        print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 主程序启动失败: {str(e)}")
        cleanup_monitor_pid()
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
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 收到中断信号，退出保活机制")
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
                    print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 短时间内重启次数过多，可能存在严重问题，退出保活机制")
                    break
            else:
                restart_count = 0  # 重置重启计数
                
            logger.error(f"主程序异常退出: {str(e)}", extra={'event_type': EventType.ERROR, 'error': str(e)})
            event_manager.publish(EventType.ERROR, {
                'message': f'主程序异常退出: {str(e)}',
                'error': str(e)
            })
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 主程序异常退出: {str(e)}")
            
            # 等待旧进程完全退出，确保PID文件被清理
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 等待旧进程完全退出...")
            monitor_pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pids', 'monitor.pid')
            for i in range(5):  # 最多等待5秒
                if not os.path.exists(monitor_pid_file):
                    logger.info("monitor.pid文件已清理，准备重启", extra={
                        'event_type': EventType.INFO,
                        'action': 'pid_file_cleaned'
                    })
                    break
                time.sleep(1)
            else:
                # 超时后强制清理PID文件
                logger.warning("monitor.pid文件未及时清理，强制清理", extra={
                    'event_type': EventType.WARNING,
                    'action': 'force_cleanup_pid_file'
                })
                try:
                    if os.path.exists(monitor_pid_file):
                        os.remove(monitor_pid_file)
                except:
                    pass
            
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 3秒后尝试重启...")
            restart_count += 1
            last_restart_time = current_time
            time.sleep(3)  # 等待3秒后重启

if __name__ == "__main__":
    keep_alive_main()