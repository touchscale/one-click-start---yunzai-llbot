# -*- coding: utf-8 -*-
"""
监控状态管理模块 - 使用文件持久化监控脚本运行状态
即使 Web 服务器停止，也能通过文件检测监控脚本是否恢复运行
"""
import os
import json
import time
import threading
from datetime import datetime
from logger import get_logger

logger = get_logger()

# 监控状态文件路径
MONITOR_STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pids', 'monitor_status.json')

# 监控状态更新间隔（秒）
STATUS_UPDATE_INTERVAL = 3

class MonitorStatusManager:
    """监控状态管理器 - 使用文件持久化状态"""
    
    def __init__(self):
        self.running = False
        self.status_lock = threading.Lock()
        self._update_thread = None
        self._stop_event = threading.Event()
        
        # 确保状态文件目录存在
        os.makedirs(os.path.dirname(MONITOR_STATUS_FILE), exist_ok=True)
    
    def set_running(self, running):
        """设置监控脚本运行状态"""
        with self.status_lock:
            self.running = running
            self._save_status()
    
    def is_running(self):
        """获取监控脚本运行状态"""
        with self.status_lock:
            return self.running
    
    def _save_status(self):
        """保存监控状态到文件"""
        try:
            status_data = {
                'monitor_running': self.running,
                'last_update': datetime.now().isoformat(),
                'timestamp': time.time()
            }
            
            with open(MONITOR_STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(status_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"保存监控状态失败: {str(e)}", extra={
                'error': str(e)
            })
    
    def load_status(self):
        """从文件加载监控状态"""
        try:
            if not os.path.exists(MONITOR_STATUS_FILE):
                return {
                    'monitor_running': False,
                    'last_update': None,
                    'timestamp': 0
                }
            
            with open(MONITOR_STATUS_FILE, 'r', encoding='utf-8') as f:
                status_data = json.load(f)
                
            return status_data
            
        except Exception as e:
            logger.error(f"加载监控状态失败: {str(e)}", extra={
                'error': str(e)
            })
            return {
                'monitor_running': False,
                'last_update': None,
                'timestamp': 0
            }
    
    def is_monitor_recovered(self, check_threshold=10):
        """
        检查监控脚本是否已恢复运行
        
        Args:
            check_threshold: 时间阈值（秒），如果状态文件在此时间内更新过，认为监控正在运行
        
        Returns:
            bool: 如果监控已恢复返回 True
        """
        try:
            if not os.path.exists(MONITOR_STATUS_FILE):
                return False
            
            status_data = self.load_status()
            
            # 检查监控是否正在运行
            if not status_data.get('monitor_running', False):
                return False
            
            # 检查状态文件是否在阈值时间内更新过
            last_update_time = status_data.get('timestamp', 0)
            current_time = time.time()
            
            if current_time - last_update_time <= check_threshold:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查监控恢复状态失败: {str(e)}", extra={
                'error': str(e)
            })
            return False
    
    def start_status_update(self):
        """启动状态更新线程"""
        if self._update_thread and self._update_thread.is_alive():
            return  # 线程已经在运行
        
        self._stop_event.clear()
        
        def update_loop():
            """状态更新循环"""
            while not self._stop_event.is_set():
                try:
                    with self.status_lock:
                        self._save_status()
                except Exception as e:
                    logger.error(f"更新监控状态失败: {str(e)}", extra={
                        'error': str(e)
                    })
                
                # 等待下一次更新
                self._stop_event.wait(STATUS_UPDATE_INTERVAL)
        
        self._update_thread = threading.Thread(target=update_loop, daemon=True)
        self._update_thread.start()
        
        logger.info("监控状态更新线程已启动", extra={
            'interval': STATUS_UPDATE_INTERVAL
        })
    
    def stop_status_update(self):
        """停止状态更新线程"""
        if self._update_thread and self._update_thread.is_alive():
            self._stop_event.set()
            self._update_thread.join(timeout=5)
            logger.info("监控状态更新线程已停止")
        
        # 保存最终状态
        with self.status_lock:
            self._save_status()
    
    def cleanup(self):
        """清理资源"""
        self.stop_status_update()
        
        # 清理状态文件
        try:
            if os.path.exists(MONITOR_STATUS_FILE):
                os.remove(MONITOR_STATUS_FILE)
                logger.info("监控状态文件已清理")
        except Exception as e:
            logger.warning(f"清理监控状态文件失败: {str(e)}", extra={
                'error': str(e)
            })


# 全局监控状态管理器实例
_monitor_status_manager = None

def get_monitor_status_manager():
    """获取全局监控状态管理器实例"""
    global _monitor_status_manager
    if _monitor_status_manager is None:
        _monitor_status_manager = MonitorStatusManager()
    return _monitor_status_manager


def set_monitor_running(running):
    """设置监控脚本运行状态（便捷函数）"""
    manager = get_monitor_status_manager()
    manager.set_running(running)


def is_monitor_running():
    """获取监控脚本运行状态（便捷函数）"""
    manager = get_monitor_status_manager()
    return manager.is_running()


def is_monitor_recovered(check_threshold=10):
    """检查监控脚本是否已恢复运行（便捷函数）"""
    manager = get_monitor_status_manager()
    return manager.is_monitor_recovered(check_threshold)


def load_monitor_status():
    """从文件加载监控状态（便捷函数）"""
    manager = get_monitor_status_manager()
    return manager.load_status()


def start_monitor_status_update():
    """启动监控状态更新线程（便捷函数）"""
    manager = get_monitor_status_manager()
    manager.start_status_update()


def stop_monitor_status_update():
    """停止监控状态更新线程（便捷函数）"""
    manager = get_monitor_status_manager()
    manager.stop_status_update()


def cleanup_monitor_status():
    """清理监控状态资源（便捷函数）"""
    manager = get_monitor_status_manager()
    manager.cleanup()