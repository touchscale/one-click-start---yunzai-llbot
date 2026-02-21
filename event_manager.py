# -*- coding: utf-8 -*-
"""
事件管理器模块 - 用于异步事件驱动架构
"""
import queue
import threading

# 全局事件管理器
event_manager = None

class EventManager:
    """事件管理器 - 用于异步事件驱动架构"""
    def __init__(self):
        self.handlers = {}
        self.event_queue = queue.Queue()
        self.running = False
    
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
                            from logger import get_logger
                            logger = get_logger()
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

def get_event_manager():
    """获取全局事件管理器实例"""
    global event_manager
    if event_manager is None:
        event_manager = EventManager()
    return event_manager