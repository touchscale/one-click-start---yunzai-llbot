# -*- coding: utf-8 -*-
"""
常量定义模块
"""

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
    },
    "auto_restart": {
        "enabled": True,
        "respect_manual_stop": True
    },
    "web_auth": {
        "username": "admin",
        "password": "admin123"
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
    DEBUG = "debug"