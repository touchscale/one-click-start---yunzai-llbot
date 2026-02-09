# -*- coding: utf-8 -*-
"""
常量定义模块
"""

# 默认配置
DEFAULT_CONFIG = {
    "llbot": {
        "wait_seconds": 10
    },
    "yunzai": {
        "wait_seconds": 5
    },
    "http_check": {
        "timeout": 10
    },
    "auto_restart": {
        "enabled": True,
        "respect_manual_stop": True
    },
    "web_auth": {
        "username": "admin",
        "password": "Admin123"
    },
    "git_update": {
        "enabled": False,
        "check_interval": 900,
        "auto_pull": False,
        "auto_restart": False
    },
    "onebot": {
        "enabled": False,
        "ws_url": "ws://localhost:8080",  # 反向 WebSocket 服务器监听地址，OneBot 会主动连接到此地址
        "access_token": "",  # 访问令牌，用于验证 OneBot 连接
        "reconnect_interval": 5,
        "authorized_users": []
    },
    "image_service": {
        "enabled": True,
        "port": 3001,
        "url": "http://localhost:3001"
    }
}

# 密码加密相关常量
class PasswordEncryption:
    """密码加密配置常量"""
    ALGORITHM = "Fernet"
    PBKDF2_ITERATIONS = 480000
    SALT_LENGTH = 16
    ENABLED = True  # 是否启用密码加密

# 事件类型枚举
class EventType:
    PROCESS_CHECK = "process_check"
    PROCESS_START = "process_start"
    PROCESS_STOP = "process_stop"
    HTTP_CHECK = "http_check"
    CONFIG_LOAD = "config_load"
    LOG_CLEAR = "log_clear"
    ERROR = "error"
    WARNING = "warning"
    DEBUG = "debug"
    INFO = "info"