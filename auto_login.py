# -*- coding: utf-8 -*-
"""
自动登录配置模块
用于配置和管理 Windows 系统自动登录功能
"""
import winreg
from logger import get_logger

logger = get_logger()

# 注册表路径
REG_PATH = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"


def is_admin():
    """检查是否具有管理员权限"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def enable_auto_login(username, password):
    """
    启用 Windows 自动登录
    
    Args:
        username (str): 用户名
        password (str): 密码
    
    Returns:
        dict: 操作结果 {'success': bool, 'message': str}
    """
    if not is_admin():
        logger.warning("启用自动登录需要管理员权限", extra={'event_type': 'warning', 'operation': 'enable_auto_login'})
        return {
            'success': False,
            'message': '需要管理员权限才能启用自动登录'
        }
    
    try:
        # 打开注册表
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_SET_VALUE)
        
        # 设置注册表项
        winreg.SetValueEx(key, "DefaultUserName", 0, winreg.REG_SZ, username)
        winreg.SetValueEx(key, "DefaultPassword", 0, winreg.REG_SZ, password)
        winreg.SetValueEx(key, "AutoAdminLogon", 0, winreg.REG_SZ, "1")
        
        winreg.CloseKey(key)
        
        logger.info(f"自动登录已启用，用户: {username}", extra={
            'event_type': 'auto_login_enabled',
            'username': username
        })
        
        return {
            'success': True,
            'message': f'自动登录已启用，用户: {username}'
        }
    except Exception as e:
        logger.error(f"启用自动登录失败: {str(e)}", extra={
            'event_type': 'error',
            'operation': 'enable_auto_login',
            'error': str(e)
        })
        return {
            'success': False,
            'message': f'启用自动登录失败: {str(e)}'
        }


def disable_auto_login():
    """
    禁用 Windows 自动登录
    
    Returns:
        dict: 操作结果 {'success': bool, 'message': str}
    """
    if not is_admin():
        logger.warning("禁用自动登录需要管理员权限", extra={'event_type': 'warning', 'operation': 'disable_auto_login'})
        return {
            'success': False,
            'message': '需要管理员权限才能禁用自动登录'
        }
    
    try:
        # 打开注册表
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_SET_VALUE)
        
        # 禁用自动登录
        winreg.SetValueEx(key, "AutoAdminLogon", 0, winreg.REG_SZ, "0")
        
        # 可选：删除密码字段以提高安全性
        try:
            winreg.DeleteValue(key, "DefaultPassword")
        except FileNotFoundError:
            pass  # 密码字段不存在，忽略
        
        winreg.CloseKey(key)
        
        logger.info("自动登录已禁用", extra={'event_type': 'auto_login_disabled'})
        
        return {
            'success': True,
            'message': '自动登录已禁用'
        }
    except Exception as e:
        logger.error(f"禁用自动登录失败: {str(e)}", extra={
            'event_type': 'error',
            'operation': 'disable_auto_login',
            'error': str(e)
        })
        return {
            'success': False,
            'message': f'禁用自动登录失败: {str(e)}'
        }


def get_auto_login_status():
    """
    获取当前自动登录状态
    
    Returns:
        dict: 自动登录状态 {'enabled': bool, 'username': str}
    """
    try:
        # 打开注册表
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_READ)
        
        # 读取自动登录状态
        auto_admin_logon = winreg.QueryValueEx(key, "AutoAdminLogon")[0]
        enabled = auto_admin_logon == "1"
        
        username = ""
        try:
            username = winreg.QueryValueEx(key, "DefaultUserName")[0]
        except FileNotFoundError:
            pass
        
        winreg.CloseKey(key)
        
        return {
            'enabled': enabled,
            'username': username
        }
    except Exception as e:
        logger.error(f"获取自动登录状态失败: {str(e)}", extra={
            'event_type': 'error',
            'operation': 'get_auto_login_status',
            'error': str(e)
        })
        return {
            'enabled': False,
            'username': ''
        }


def apply_config_from_dict(config):
    """
    从配置字典应用自动登录设置
    
    Args:
        config (dict): 包含 auto_login 配置的字典
    
    Returns:
        dict: 操作结果 {'success': bool, 'message': str, 'enabled': bool}
    """
    auto_login_config = config.get('auto_login', {})
    enabled = auto_login_config.get('enabled', False)
    username = auto_login_config.get('username', '')
    password = auto_login_config.get('password', '')
    
    if not enabled:
        # 禁用自动登录
        result = disable_auto_login()
        result['enabled'] = False
        return result
    
    if not username or not password:
        logger.warning("自动登录已启用但缺少用户名或密码", extra={
            'event_type': 'warning',
            'operation': 'apply_config'
        })
        return {
            'success': False,
            'message': '自动登录已启用但缺少用户名或密码',
            'enabled': False
        }
    
    # 启用自动登录
    result = enable_auto_login(username, password)
    result['enabled'] = result['success']
    return result


def print_status():
    """打印当前自动登录状态"""
    status = get_auto_login_status()
    
    print("=" * 50)
    print("自动登录状态")
    print("=" * 50)
    print(f"状态: {'已启用' if status['enabled'] else '已禁用'}")
    print(f"用户名: {status['username'] if status['username'] else '未设置'}")
    print("=" * 50)
    
    return status


if __name__ == "__main__":
    # 命令行测试
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "status":
            print_status()
        
        elif command == "enable":
            if len(sys.argv) >= 4:
                username = sys.argv[2]
                password = sys.argv[3]
                result = enable_auto_login(username, password)
                print(result['message'])
            else:
                print("用法: python auto_login.py enable <用户名> <密码>")
        
        elif command == "disable":
            result = disable_auto_login()
            print(result['message'])
        
        else:
            print("可用命令:")
            print("  python auto_login.py status      - 查看自动登录状态")
            print("  python auto_login.py enable     - 启用自动登录")
            print("  python auto_login.py disable    - 禁用自动登录")
    else:
        print_status()