# -*- coding: utf-8 -*-
"""
YUNZAI 启动失败跟踪模块 - 记录和检测 YUNZAI 的启动失败情况
用于判断是否需要切换到管理员模式启动
"""
import os
import json
import time
from datetime import datetime, timedelta
from logger import get_logger
from constants import EventType

logger = get_logger()

# 跟踪文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRACKER_FILE = os.path.join(SCRIPT_DIR, "pids", "yunzai_restart_tracker.json")

# 默认配置
DEFAULT_CONFIG = {
    'crash_threshold_seconds': 30,  # 进程启动后30秒内退出视为闪退
    'max_crash_count': 3,           # 最多允许3次闪退
    'reset_timeout_hours': 24       # 24小时后重置计数器
}


def load_tracker_data():
    """加载跟踪数据"""
    try:
        if os.path.exists(TRACKER_FILE):
            with open(TRACKER_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"加载 YUNZAI 跟踪数据: {data}", extra={
                    'event_type': EventType.DEBUG,
                    'action': 'load_tracker_data'
                })
                return data
        return {
            'crash_count': 0,
            'last_crash_time': None,
            'last_start_time': None,
            'first_crash_time': None
        }
    except Exception as e:
        logger.warning(f"加载跟踪数据失败: {str(e)}", extra={
            'event_type': EventType.WARNING,
            'error': str(e)
        })
        return {
            'crash_count': 0,
            'last_crash_time': None,
            'last_start_time': None,
            'first_crash_time': None
        }


def save_tracker_data(data):
    """保存跟踪数据"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
        
        with open(TRACKER_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"保存 YUNZAI 跟踪数据: {data}", extra={
            'event_type': EventType.DEBUG,
            'action': 'save_tracker_data'
        })
        return True
    except Exception as e:
        logger.error(f"保存跟踪数据失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return False


def record_start():
    """记录进程启动时间"""
    try:
        data = load_tracker_data()
        data['last_start_time'] = datetime.now().isoformat()
        save_tracker_data(data)
        logger.info(f"记录 YUNZAI 启动时间: {data['last_start_time']}", extra={
            'event_type': EventType.INFO,
            'action': 'record_start',
            'start_time': data['last_start_time']
        })
        return True
    except Exception as e:
        logger.error(f"记录启动时间失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return False


def check_crash(config=None):
    """
    检查是否为闪退
    
    Args:
        config: 配置字典,包含 crash_threshold_seconds 参数
    
    Returns:
        bool: 是否为闪退
    """
    try:
        # 合并默认配置
        if config is None:
            config = DEFAULT_CONFIG
        else:
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config)
            config = merged_config
        
        crash_threshold = config.get('crash_threshold_seconds', DEFAULT_CONFIG['crash_threshold_seconds'])
        
        data = load_tracker_data()
        
        # 如果没有启动时间记录,不视为闪退
        if not data.get('last_start_time'):
            logger.debug("没有启动时间记录,不视为闪退", extra={
                'event_type': EventType.DEBUG,
                'action': 'check_crash',
                'result': 'no_start_time'
            })
            return False
        
        # 计算存活时间
        start_time = datetime.fromisoformat(data['last_start_time'])
        current_time = datetime.now()
        survival_time = (current_time - start_time).total_seconds()
        
        # 如果存活时间超过阈值,不视为闪退
        if survival_time > crash_threshold:
            logger.info(f"YUNZAI 存活时间 {survival_time:.1f} 秒,超过阈值 {crash_threshold} 秒,不视为闪退", extra={
                'event_type': EventType.INFO,
                'action': 'check_crash',
                'survival_time': survival_time,
                'threshold': crash_threshold,
                'result': 'not_crash'
            })
            return False
        
        # 存活时间在阈值内,视为闪退
        logger.warning(f"检测到 YUNZAI 闪退! 存活时间 {survival_time:.1f} 秒,小于阈值 {crash_threshold} 秒", extra={
            'event_type': EventType.WARNING,
            'action': 'check_crash',
            'survival_time': survival_time,
            'threshold': crash_threshold,
            'result': 'crash_detected'
        })
        return True
        
    except Exception as e:
        logger.error(f"检查闪退时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return False


def record_crash(config=None):
    """
    记录一次闪退,并检查是否需要切换到管理员模式
    
    Args:
        config: 配置字典,包含 max_crash_count 和 reset_timeout_hours 参数
    
    Returns:
        dict: 包含是否需要切换到管理员模式,当前失败次数等信息
    """
    try:
        # 合并默认配置
        if config is None:
            config = DEFAULT_CONFIG
        else:
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(config)
            config = merged_config
        
        max_crash_count = config.get('max_crash_count', DEFAULT_CONFIG['max_crash_count'])
        reset_timeout_hours = config.get('reset_timeout_hours', DEFAULT_CONFIG['reset_timeout_hours'])
        
        data = load_tracker_data()
        current_time = datetime.now()
        
        # 检查是否需要重置计数器(超过重置超时时间)
        if data.get('first_crash_time'):
            first_crash_time = datetime.fromisoformat(data['first_crash_time'])
            hours_since_first_crash = (current_time - first_crash_time).total_seconds() / 3600
            
            if hours_since_first_crash > reset_timeout_hours:
                logger.info(f"距离第一次闪退已超过 {reset_timeout_hours} 小时,重置计数器", extra={
                    'event_type': EventType.INFO,
                    'action': 'reset_counter',
                    'hours_since_first_crash': hours_since_first_crash,
                    'reset_timeout': reset_timeout_hours
                })
                data['crash_count'] = 0
                data['first_crash_time'] = None
        
        # 增加失败计数
        data['crash_count'] = data.get('crash_count', 0) + 1
        data['last_crash_time'] = current_time.isoformat()
        
        # 记录第一次闪退时间
        if not data.get('first_crash_time'):
            data['first_crash_time'] = current_time.isoformat()
        
        # 保存数据
        save_tracker_data(data)
        
        logger.warning(f"记录 YUNZAI 闪退,当前失败次数: {data['crash_count']}/{max_crash_count}", extra={
            'event_type': EventType.WARNING,
            'action': 'record_crash',
            'crash_count': data['crash_count'],
            'max_crash_count': max_crash_count
        })
        
        # 检查是否达到阈值
        need_admin_mode = data['crash_count'] >= max_crash_count
        
        if need_admin_mode:
            logger.warning(f"YUNZAI 闪退次数达到阈值 {max_crash_count},建议切换到管理员模式启动!", extra={
                'event_type': EventType.WARNING,
                'action': 'crash_threshold_reached',
                'crash_count': data['crash_count'],
                'max_crash_count': max_crash_count
            })
        else:
            logger.info(f"YUNZAI 闪退次数未达到阈值 {max_crash_count},继续尝试正常启动", extra={
                'event_type': EventType.INFO,
                'action': 'crash_below_threshold',
                'crash_count': data['crash_count'],
                'max_crash_count': max_crash_count
            })
        
        return {
            'need_admin_mode': need_admin_mode,
            'crash_count': data['crash_count'],
            'max_crash_count': max_crash_count,
            'last_crash_time': data['last_crash_time']
        }
        
    except Exception as e:
        logger.error(f"记录闪退时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return {
            'need_admin_mode': False,
            'crash_count': 0,
            'max_crash_count': config.get('max_crash_count', DEFAULT_CONFIG['max_crash_count']),
            'last_crash_time': None
        }


def reset_counter():
    """重置失败计数器"""
    try:
        data = {
            'crash_count': 0,
            'last_crash_time': None,
            'last_start_time': None,
            'first_crash_time': None
        }
        save_tracker_data(data)
        logger.info("YUNZAI 失败计数器已重置", extra={
            'event_type': EventType.INFO,
            'action': 'reset_counter'
        })
        return True
    except Exception as e:
        logger.error(f"重置计数器失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return False


def get_tracker_info():
    """获取跟踪信息"""
    try:
        data = load_tracker_data()
        return {
            'crash_count': data.get('crash_count', 0),
            'last_crash_time': data.get('last_crash_time'),
            'last_start_time': data.get('last_start_time'),
            'first_crash_time': data.get('first_crash_time')
        }
    except Exception as e:
        logger.error(f"获取跟踪信息失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return {
            'crash_count': 0,
            'last_crash_time': None,
            'last_start_time': None,
            'first_crash_time': None
        }