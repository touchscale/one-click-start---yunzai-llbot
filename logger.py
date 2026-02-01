# -*- coding: utf-8 -*-
"""
日志处理模块
"""
import os
import sys
import logging
import re
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
import glob
import json

# 全局日志记录器
logger = None

class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""
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

def clean_old_log_files():
    """清理超过一天的旧日志文件"""
    logger = get_logger()
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
            'event_type': 'error',
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
            import time
            time.sleep(time_to_wait)
            
            # 执行清理
            clean_old_log_files()
    
    import threading
    # 启动清理线程
    cleanup_thread = threading.Thread(target=run_daily_cleanup, daemon=True)
    cleanup_thread.start()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 日志清理任务已调度")

def setup_structured_logging():
    """设置结构化日志记录"""
    # 创建logs目录（如果不存在）
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
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
    file_handler.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # 匹配日期格式（必须用 re.compile）
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

def get_logger():
    """获取全局日志记录器实例"""
    global logger
    if logger is None:
        logger = setup_structured_logging()
    return logger