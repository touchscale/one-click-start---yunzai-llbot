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
from onebot_client import init_onebot_client, get_onebot_client
from onebot_handlers import register_all_handlers

# 初始化日志记录器
logger = get_logger()

# 初始化事件管理器
event_manager = get_event_manager()

def run_monitor_loop(config):
    """运行监控循环 - 使用多线程并行监控"""
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
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止监控", extra={'event_type': EventType.PROCESS_STOP, 'reason': 'user_interrupt'})
        event_manager.publish(EventType.PROCESS_STOP, {
            'message': '收到中断信号',
            'reason': 'user_interrupt'
        })
    
    # 设置停止标志
    run_monitor_loop.running = False
    
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

def main():
    """主函数"""
    start_time = time.time()
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
        print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始监控llbot和Yunzai进程...")
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
                'stop_time': __import__('datetime').datetime.now().isoformat(),
                'total_runtime': f"{time.time() - start_time:.3f}s"
            })
            event_manager.publish(EventType.PROCESS_STOP, {
                'message': '监控已停止',
                'reason': 'user_interrupt',
                'total_runtime': f"{time.time() - start_time:.3f}s"
            })
            print(f"\n[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控已停止")
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
            print(f"[{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {3}秒后尝试重启...")
            restart_count += 1
            last_restart_time = current_time
            time.sleep(3)  # 等待3秒后重启

if __name__ == "__main__":
    keep_alive_main()