# -*- coding: utf-8 -*-
"""
进程PID文件管理模块 - 用于精确跟踪和管理进程PID
"""
import os
import time
from datetime import datetime
from logger import get_logger
from constants import EventType

logger = get_logger()

# PID文件存储目录
PID_DIR = "pids"

# 进程名称映射
PROCESS_NAMES = {
    'llbot': 'llbot.pid',
    'yunzai': 'yunzai.pid',
    'redis': 'redis.pid'
}

def ensure_pid_dir():
    """确保PID目录存在"""
    if not os.path.exists(PID_DIR):
        os.makedirs(PID_DIR)
        logger.info(f"创建PID目录: {PID_DIR}", extra={'event_type': EventType.INFO, 'action': 'create_pid_dir'})

def get_pid_file(process_name):
    """获取指定进程的PID文件路径"""
    ensure_pid_dir()
    filename = PROCESS_NAMES.get(process_name, f"{process_name}.pid")
    return os.path.join(PID_DIR, filename)

def write_pid(process_name, pid):
    """写入进程PID到文件"""
    try:
        pid_file = get_pid_file(process_name)
        with open(pid_file, 'w', encoding='utf-8') as f:
            f.write(str(pid))
            f.write(f"\n{datetime.now().isoformat()}")  # 写入启动时间
        logger.info(f"已写入PID文件: {process_name} -> {pid}", extra={
            'event_type': EventType.PROCESS_START,
            'process_name': process_name,
            'pid': pid,
            'pid_file': pid_file
        })
        return True
    except Exception as e:
        logger.error(f"写入PID文件失败: {process_name} - {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'process_name': process_name
        })
        return False

def read_pid(process_name):
    """从文件读取进程PID"""
    try:
        pid_file = get_pid_file(process_name)
        if not os.path.exists(pid_file):
            return None
        
        with open(pid_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                pid = int(lines[0].strip())
                logger.debug(f"读取PID文件: {process_name} -> {pid}", extra={
                    'event_type': EventType.DEBUG,
                    'process_name': process_name,
                    'pid': pid,
                    'pid_file': pid_file
                })
                return pid
        return None
    except Exception as e:
        logger.error(f"读取PID文件失败: {process_name} - {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'process_name': process_name
        })
        return None

def remove_pid_file(process_name):
    """删除进程PID文件"""
    try:
        pid_file = get_pid_file(process_name)
        if os.path.exists(pid_file):
            os.remove(pid_file)
            logger.info(f"已删除PID文件: {process_name}", extra={
                'event_type': EventType.PROCESS_STOP,
                'process_name': process_name,
                'pid_file': pid_file
            })
            return True
        return False
    except Exception as e:
        logger.error(f"删除PID文件失败: {process_name} - {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'process_name': process_name
        })
        return False

def verify_pid(pid):
    """验证PID是否有效（进程是否存在）"""
    try:
        import psutil
        proc = psutil.Process(pid)
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    except Exception:
        return False

def get_process_info_from_pid(pid):
    """从PID获取进程信息"""
    try:
        import psutil
        proc = psutil.Process(pid)
        return {
            'pid': pid,
            'name': proc.name(),
            'status': proc.status(),
            'create_time': proc.create_time(),
            'cmdline': proc.cmdline()
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.warning(f"获取进程信息失败: PID {pid} - {str(e)}", extra={
            'event_type': EventType.WARNING,
            'error': str(e),
            'pid': pid
        })
        return None
    except Exception as e:
        logger.error(f"获取进程信息时发生错误: PID {pid} - {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'pid': pid
        })
        return None

def cleanup_invalid_pids():
    """清理无效的PID文件（进程已不存在的PID文件）"""
    try:
        ensure_pid_dir()
        cleaned = 0
        
        for process_name, filename in PROCESS_NAMES.items():
            pid_file = os.path.join(PID_DIR, filename)
            if os.path.exists(pid_file):
                pid = read_pid(process_name)
                if pid and not verify_pid(pid):
                    logger.info(f"清理无效PID文件: {process_name} (PID {pid} 不存在)", extra={
                        'event_type': EventType.INFO,
                        'process_name': process_name,
                        'pid': pid,
                        'action': 'cleanup_invalid_pid'
                    })
                    remove_pid_file(process_name)
                    cleaned += 1
        
        if cleaned > 0:
            logger.info(f"已清理 {cleaned} 个无效PID文件", extra={
                'event_type': EventType.INFO,
                'cleaned_count': cleaned,
                'action': 'cleanup_invalid_pids'
            })
        
        return cleaned
    except Exception as e:
        logger.error(f"清理无效PID文件时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return 0

def get_all_pids():
    """获取所有已记录的进程PID"""
    try:
        ensure_pid_dir()
        pids = {}
        
        for process_name, filename in PROCESS_NAMES.items():
            pid = read_pid(process_name)
            if pid:
                pids[process_name] = pid
        
        return pids
    except Exception as e:
        logger.error(f"获取所有PID时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return {}

def is_process_running(process_name):
    """通过PID文件检查进程是否运行"""
    try:
        pid = read_pid(process_name)
        if not pid:
            return False
        
        if verify_pid(pid):
            return True
        else:
            # PID无效，清理PID文件
            logger.info(f"进程 {process_name} 的PID {pid} 无效，清理PID文件", extra={
                'event_type': EventType.INFO,
                'process_name': process_name,
                'pid': pid,
                'action': 'cleanup_invalid_pid'
            })
            remove_pid_file(process_name)
            return False
    except Exception as e:
        logger.error(f"检查进程状态失败: {process_name} - {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'process_name': process_name
        })
        return False
