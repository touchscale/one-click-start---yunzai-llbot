# -*- coding: utf-8 -*-
"""
自动登录配置模块
用于配置和管理 Windows 系统自动登录功能
"""
import os
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


def get_current_username():
    """
    自动获取当前登录的用户名（不含域名前缀）
    
    Returns:
        str: 当前用户名，如 'redmi'
    """
    try:
        username = os.environ.get('USERNAME', '')
        if username:
            return username
    except:
        pass
    # 备用方案
    try:
        import ctypes
        size = ctypes.c_uint(256)
        buf = ctypes.create_unicode_buffer(size.value)
        ctypes.windll.user32.GetUserNameW(buf, size)
        return buf.value
    except:
        return ''


def get_current_domain():
    """
    自动获取当前计算机名/域名
    
    Returns:
        str: 计算机名，如 'PC-20260524JRCH'
    """
    try:
        return os.environ.get('USERDOMAIN', '') or os.environ.get('COMPUTERNAME', '')
    except:
        return ''


def enable_auto_login(username=None, password=''):
    """
    启用 Windows 自动登录
    
    Args:
        username (str): 用户名，为空时自动获取当前登录用户
        password (str): 密码，为空字符串表示无密码
    
    Returns:
        dict: 操作结果 {'success': bool, 'message': str}
    """
    if not is_admin():
        logger.warning("启用自动登录需要管理员权限", extra={'event_type': 'warning', 'operation': 'enable_auto_login'})
        return {
            'success': False,
            'message': '需要管理员权限才能启用自动登录'
        }
    
    # 自动获取用户名
    if not username:
        username = get_current_username()
    
    if not username:
        return {
            'success': False,
            'message': '无法自动获取用户名，请手动指定'
        }
    
    try:
        # 打开注册表
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0, winreg.KEY_SET_VALUE)
        
        # 解析用户名：支持 "DOMAIN\user" 或 "MACHINE\user" 格式
        domain_name = ""
        resolved_username = username
        if "\\" in username:
            parts = username.split("\\", 1)
            domain_name = parts[0]
            resolved_username = parts[1]
        elif "/" in username:
            # 兼容错误的 DOMAIN/user 格式
            parts = username.split("/", 1)
            domain_name = parts[0]
            resolved_username = parts[1]
        
        # 设置注册表项
        winreg.SetValueEx(key, "DefaultUserName", 0, winreg.REG_SZ, resolved_username)
        winreg.SetValueEx(key, "DefaultPassword", 0, winreg.REG_SZ, password)
        winreg.SetValueEx(key, "AutoAdminLogon", 0, winreg.REG_SZ, "1")
        # 某些 Windows 版本需要 ForceAutoLogon 才能生效
        winreg.SetValueEx(key, "ForceAutoLogon", 0, winreg.REG_SZ, "1")
        
        # 如果指定了域名/计算机名，单独设置 DefaultDomainName
        if domain_name:
            winreg.SetValueEx(key, "DefaultDomainName", 0, winreg.REG_SZ, domain_name)
        else:
            # 清除可能残留的 DefaultDomainName
            try:
                winreg.DeleteValue(key, "DefaultDomainName")
            except FileNotFoundError:
                pass
        
        winreg.CloseKey(key)
        
        display_user = f"{domain_name}\\{resolved_username}" if domain_name else resolved_username
        logger.info(f"自动登录已启用，用户: {display_user}", extra={
            'event_type': 'auto_login_enabled',
            'username': display_user
        })
        
        return {
            'success': True,
            'message': f'自动登录已启用，用户: {display_user}'
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
        winreg.SetValueEx(key, "ForceAutoLogon", 0, winreg.REG_SZ, "0")
        
        # 删除密码字段以提高安全性
        try:
            winreg.DeleteValue(key, "DefaultPassword")
        except FileNotFoundError:
            pass
        
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
        
        domain = ""
        try:
            domain = winreg.QueryValueEx(key, "DefaultDomainName")[0]
        except FileNotFoundError:
            pass
        
        winreg.CloseKey(key)
        
        display_user = f"{domain}\\{username}" if domain else username
        
        return {
            'enabled': enabled,
            'username': display_user
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
    如果配置中用户名为空，自动获取当前登录用户
    
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
    
    # 用户名为空时自动获取当前登录用户
    if not username:
        username = get_current_username()
        logger.info(f"自动获取当前登录用户: {username}", extra={
            'event_type': 'auto_login_auto_detect',
            'username': username
        })
    
    if not username:
        logger.warning("自动登录已启用但无法获取用户名", extra={
            'event_type': 'warning',
            'operation': 'apply_config'
        })
        return {
            'success': False,
            'message': '自动登录已启用但无法获取用户名',
            'enabled': False
        }
    
    # 启用自动登录（密码可以为空）
    result = enable_auto_login(username, password)
    result['enabled'] = result['success']
    return result


def print_status():
    """打印当前自动登录状态"""
    status = get_auto_login_status()
    
    current_user = get_current_username()
    current_domain = get_current_domain()
    
    print("=" * 50)
    print("自动登录状态")
    print("=" * 50)
    print(f"状态: {'已启用' if status['enabled'] else '已禁用'}")
    print(f"配置用户: {status['username'] if status['username'] else '未设置'}")
    print(f"当前登录用户: {current_domain}\\{current_user}" if current_domain else f"当前登录用户: {current_user}")
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
            # 支持不传参数，自动获取用户名
            username = sys.argv[2] if len(sys.argv) >= 3 else ''
            password = sys.argv[3] if len(sys.argv) >= 4 else ''
            result = enable_auto_login(username, password)
            print(result['message'])
        
        elif command == "disable":
            result = disable_auto_login()
            print(result['message'])
        
        else:
            print("可用命令:")
            print("  python auto_login.py status      - 查看自动登录状态")
            print("  python auto_login.py enable      - 启用自动登录（自动获取用户名）")
            print("  python auto_login.py enable <用户名> <密码> - 指定用户名密码")
            print("  python auto_login.py disable     - 禁用自动登录")
    else:
        print_status()
