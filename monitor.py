# -*- coding: utf-8 -*-
"""
监控模块 - 处理进程监控和HTTP检查
"""
import os
import time
import requests
import psutil
from datetime import datetime
from logger import get_logger
from event_manager import get_event_manager
from process_manager import (
    restart_llbot_with_cleanup, 
    start_yunzai, 
    start_redis,
    get_global_manual_stop_status,
    terminate_process_by_name
)
from constants import EventType

logger = get_logger()
event_manager = get_event_manager()

def async_http_check(url, timeout=5):
    """异步HTTP检查"""
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except:
        return False

def check_qq_status():
    """检查QQ进程状态"""
    try:
        qq_running = False
        found_processes = []
        # 转换为列表避免生成器冲突
        procs = list(psutil.process_iter(['name', 'pid']))
        for proc in procs:
            proc_name = (proc.info['name'] or '').lower()
            if proc_name in ['qq.exe', 'qq', 'qqprotect.exe', 'qqpcrtp.exe']:
                qq_running = True
                found_processes.append({
                    'name': proc.info['name'],
                    'pid': proc.info['pid']
                })
        
        if found_processes:
            logger.info(f"检测到QQ进程正在运行: {len(found_processes)}个进程", extra={
                'event_type': EventType.PROCESS_CHECK,
                'qq_processes': found_processes,
                'count': len(found_processes)
            })
        else:
            logger.info("未检测到QQ进程", extra={
                'event_type': EventType.PROCESS_CHECK,
                'qq_processes': []
            })
        
        return qq_running
    except Exception as e:
        logger.error(f"检测QQ进程时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'error_class': type(e).__name__
        })
        return False

# 用于存储QQ状态
class QQStatusTracker:
    """QQ状态跟踪器"""
    def __init__(self):
        # 初始化时立即获取当前的QQ状态，而不是设置为None
        self.last_qq_status = check_qq_status()

qq_status_tracker = QQStatusTracker()

def check_and_manage_llbot_async(config):
    """异步检查并管理llbot进程"""
    global qq_status_tracker
    
    try:
        # 检查QQ状态变化
        current_qq_status = check_qq_status()
        
        # 如果QQ从运行变为停止，需要清理并重启llbot
        if qq_status_tracker.last_qq_status is not None and qq_status_tracker.last_qq_status and not current_qq_status:
            logger.warning("检测到QQ进程已停止，正在清理相关进程并重启llbot", extra={
                'event_type': EventType.WARNING,
                'qq_status': 'stopped',
                'last_qq_status': 'running',
                'action': 'restart_llbot_due_to_qq_stop'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检测到QQ进程已停止，正在清理相关进程并重启llbot...")
            
            # 终止相关进程
            terminate_process_by_name('pmhq-win-x64.exe')
            terminate_process_by_name('flet.exe')
            
            # 清除手动停止状态
            try:
                from process_manager import update_global_manual_stop_status
                update_global_manual_stop_status('llbot', False)
                logger.info("已清除llbot手动停止状态", extra={
                    'event_type': EventType.PROCESS_START,
                    'action': 'clear_manual_stop_status'
                })
            except Exception as e:
                logger.warning(f"清除手动停止状态失败: {str(e)}", extra={
                    'event_type': EventType.WARNING,
                    'error': str(e)
                })
            
            # 重启llbot（带清理）
            logger.info("开始重启llbot进程", extra={
                'event_type': EventType.PROCESS_START,
                'action': 'restart_after_qq_stop'
            })
            restart_llbot_with_cleanup(config)
            
            # 更新QQ状态
            qq_status_tracker.last_qq_status = current_qq_status
            logger.info("QQ状态已更新，跳过本次HTTP检查", extra={
                'event_type': EventType.PROCESS_CHECK,
                'qq_status_updated': current_qq_status,
                'skip_http_check': True
            })
            return  # 完成重启后返回，跳过本次的HTTP检查
        else:
            # 记录QQ状态未变化或从停止到运行的情况
            if qq_status_tracker.last_qq_status != current_qq_status:
                logger.info(f"QQ状态变化: {qq_status_tracker.last_qq_status} -> {current_qq_status}", extra={
                    'event_type': EventType.PROCESS_CHECK,
                    'qq_status_change': f'{qq_status_tracker.last_qq_status}_to_{current_qq_status}'
                })
        
        # 更新QQ状态记录
        qq_status_tracker.last_qq_status = current_qq_status
        
        # 检查自动重启配置
        auto_restart_enabled = config.get('auto_restart', {}).get('enabled', True)
        respect_manual_stop = config.get('auto_restart', {}).get('respect_manual_stop', True)
        
        # 检查是否手动停止了llbot进程
        is_manual_stop = False
        try:
            is_manual_stop = get_global_manual_stop_status('llbot')
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
                # 转换为列表避免生成器冲突
                procs = list(psutil.process_iter(['name', 'pid', 'create_time']))
                for proc in procs:
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

def check_and_manage_yunzai_async(config):
    """异步检查并管理Yunzai进程"""
    try:
        # 检查自动重启配置
        auto_restart_enabled = config.get('auto_restart', {}).get('enabled', True)
        respect_manual_stop = config.get('auto_restart', {}).get('respect_manual_stop', True)
        
        # 检查是否手动停止了yunzai或redis进程
        yunzai_manual_stop = False
        redis_manual_stop = False
        try:
            yunzai_manual_stop = get_global_manual_stop_status('yunzai')
            redis_manual_stop = get_global_manual_stop_status('redis')
        except:
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
                'process_name': redis_process_name
            })
            
            found_redis_processes = []
            # 转换为列表避免生成器冲突
            procs = list(psutil.process_iter(['name', 'pid', 'create_time']))
            for proc in procs:
                if proc.info['name'].lower() == redis_process_name.lower():
                    redis_running = True
                    found_redis_processes.append({
                        'name': proc.info['name'],
                        'pid': proc.info['pid'],
                        'create_time': datetime.fromtimestamp(proc.info['create_time']).isoformat()
                    })
            
            if redis_running:
                logger.info(f"Redis进程正在运行", extra={
                    'event_type': EventType.PROCESS_CHECK, 
                    'process_name': redis_process_name, 
                    'status': 'running',
                    'found_processes': found_redis_processes,
                    'count': len(found_redis_processes)
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 进程正在运行...")
                event_manager.publish(EventType.PROCESS_CHECK, {
                    'process_name': redis_process_name,
                    'status': 'running',
                    'found_processes': found_redis_processes,
                    'count': len(found_redis_processes)
                })
            else:
                # 检查是否手动停止了Redis
                if respect_manual_stop and auto_restart_enabled and redis_manual_stop:
                    logger.debug("redis被手动停止，跳过自动启动", extra={
                        'event_type': 'debug',
                        'target_process': 'redis',
                        'manual_stop': True,
                        'auto_restart_enabled': auto_restart_enabled,
                        'respect_manual_stop': respect_manual_stop
                    })
                else:
                    logger.warning("Redis进程未运行，正在启动", extra={
                        'event_type': EventType.WARNING, 
                        'process_name': redis_process_name,
                        'config_path': config['redis']['path']
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 进程未运行，正在启动...")
                    event_manager.publish(EventType.WARNING, {
                        'message': 'Redis进程未运行，正在启动',
                        'process_name': redis_process_name,
                        'config_path': config['redis']['path']
                    })
                    start_redis(config)
        except psutil.AccessDenied as e:
            logger.error("访问进程信息被拒绝，可能需要管理员权限", extra={
                'event_type': EventType.ERROR, 
                'error_type': 'access_denied',
                'error_details': str(e),
                'process_name': redis_process_name if 'redis_process_name' in locals() else 'unknown',
                'suggestion': '请以管理员权限运行脚本'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问进程信息被拒绝，可能需要管理员权限")
            event_manager.publish(EventType.ERROR, {
                'message': '访问进程信息被拒绝',
                'error_type': 'access_denied',
                'error_details': str(e),
                'process_name': redis_process_name if 'redis_process_name' in locals() else 'unknown',
                'suggestion': '请以管理员权限运行脚本'
            })
        except psutil.NoSuchProcess as e:
            logger.warning("尝试访问不存在的进程", extra={
                'event_type': EventType.WARNING, 
                'error_type': 'no_such_process',
                'error_details': str(e),
                'process_name': redis_process_name if 'redis_process_name' in locals() else 'unknown'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试访问不存在的进程")
            event_manager.publish(EventType.WARNING, {
                'message': '尝试访问不存在的进程',
                'error_type': 'no_such_process',
                'error_details': str(e),
                'process_name': redis_process_name if 'redis_process_name' in locals() else 'unknown'
            })
        except Exception as e:
            logger.error(f"检查Redis进程时发生错误: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'error_type': 'process_check_error', 
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc(),
                'process_name': redis_process_name if 'redis_process_name' in locals() else 'unknown'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Redis进程时发生错误: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'检查Redis进程时发生错误: {str(e)}',
                'error_type': 'process_check_error',
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
            })
        
        # 检查Yunzai是否运行
        if not config['yunzai']['git_bash_path']:
            logger.warning("Git Bash路径未配置", extra={
                'event_type': EventType.WARNING, 
                'check_type': 'git_bash_path',
                'details': '配置中缺少Git Bash路径，无法检查Yunzai进程状态'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Git Bash路径未配置")
            event_manager.publish(EventType.WARNING, {
                'message': 'Git Bash路径未配置',
                'config_item': 'git_bash_path',
                'details': '配置中缺少Git Bash路径，无法检查Yunzai进程状态'
            })
            return
            
        try:
            yunzai_running = False
            process_name = os.path.basename(config['yunzai']['git_bash_path'])
            
            # 记录正在搜索的Yunzai进程
            logger.debug(f"搜索Yunzai进程: {process_name}", extra={
                'event_type': 'debug', 
                'process_name': process_name
            })
            
            found_yunzai_processes = []
            # 转换为列表避免生成器冲突
            procs = list(psutil.process_iter(['name', 'pid', 'create_time']))
            for proc in procs:
                if proc.info['name'].lower() == 'git-bash.exe':
                    yunzai_running = True
                    found_yunzai_processes.append({
                        'name': proc.info['name'],
                        'pid': proc.info['pid'],
                        'create_time': datetime.fromtimestamp(proc.info['create_time']).isoformat()
                    })
            
            if not yunzai_running:
                # 检查是否手动停止了Yunzai
                if respect_manual_stop and auto_restart_enabled and yunzai_manual_stop:
                    logger.debug("yunzai被手动停止，跳过自动启动", extra={
                        'event_type': 'debug',
                        'target_process': 'yunzai',
                        'manual_stop': True,
                        'auto_restart_enabled': auto_restart_enabled,
                        'respect_manual_stop': respect_manual_stop
                    })
                else:
                    logger.warning("Yunzai进程未运行，正在启动", extra={
                        'event_type': EventType.WARNING, 
                        'process_name': process_name,
                        'config_git_bash': config['yunzai']['git_bash_path'],
                        'config_bash_directory': config['yunzai']['bash_directory']
                    })
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 进程未运行，正在启动...")
                    event_manager.publish(EventType.WARNING, {
                        'message': 'Yunzai进程未运行，正在启动',
                        'process_name': process_name,
                        'config_git_bash': config['yunzai']['git_bash_path'],
                        'config_bash_directory': config['yunzai']['bash_directory']
                    })
                    start_yunzai(config)
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
        except psutil.AccessDenied as e:
            logger.error("访问进程信息被拒绝，可能需要管理员权限", extra={
                'event_type': EventType.ERROR, 
                'error_type': 'access_denied',
                'error_details': str(e),
                'process_name': process_name if 'process_name' in locals() else 'unknown',
                'suggestion': '请以管理员权限运行脚本'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 访问进程信息被拒绝，可能需要管理员权限")
            event_manager.publish(EventType.ERROR, {
                'message': '访问进程信息被拒绝',
                'error_type': 'access_denied',
                'error_details': str(e),
                'process_name': process_name if 'process_name' in locals() else 'unknown',
                'suggestion': '请以管理员权限运行脚本'
            })
        except psutil.NoSuchProcess as e:
            logger.warning("尝试访问不存在的进程", extra={
                'event_type': EventType.WARNING, 
                'error_type': 'no_such_process',
                'error_details': str(e),
                'process_name': process_name if 'process_name' in locals() else 'unknown'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试访问不存在的进程")
            event_manager.publish(EventType.WARNING, {
                'message': '尝试访问不存在的进程',
                'error_type': 'no_such_process',
                'error_details': str(e),
                'process_name': process_name if 'process_name' in locals() else 'unknown'
            })
        except Exception as e:
            logger.error(f"检查Yunzai进程时发生错误: {str(e)}", extra={
                'event_type': EventType.ERROR, 
                'error_type': 'process_check_error', 
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc(),
                'process_name': process_name if 'process_name' in locals() else 'unknown'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查Yunzai进程时发生错误: {str(e)}")
            event_manager.publish(EventType.ERROR, {
                'message': f'检查Yunzai进程时发生错误: {str(e)}',
                'error_type': 'process_check_error',
                'error': str(e),
                'error_class': type(e).__name__,
                'traceback': __import__('traceback').format_exc()
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