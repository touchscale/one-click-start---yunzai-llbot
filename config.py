# -*- coding: utf-8 -*-
"""
配置管理模块
"""
import os
import yaml
from datetime import datetime
from constants import DEFAULT_CONFIG
from logger import get_logger
from password_crypt import PasswordCrypt

logger = get_logger()

def interactive_config():
    """交互式配置函数，让用户输入配置项"""
    logger.info("开始交互式配置", extra={'event_type': 'config_start'})
    print("=" * 60)
    print("开始配置监控参数")
    print("=" * 60)
    
    # 初始化配置结构，使用默认值作为备用
    config = {
        'llbot': {
            'wait_seconds': DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
        },
        'yunzai': {
            'wait_seconds': DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
        },
        'http_check': {
            'timeout': DEFAULT_CONFIG['http_check'].get('timeout', 5)
        }
    }
    
    print("\n【llbot配置】")
    config['llbot']['path'] = input("llbot.exe路径 (例: D:\\path\\to\\llbot.exe): ").strip()
    config['llbot']['directory'] = input("llbot目录 (例: D:\\path\\to\\llbot): ").strip()
    
    wait_seconds_input = input(f"llbot检查间隔秒数 (默认: {config['llbot']['wait_seconds']}，留空使用默认值): ").strip()
    if wait_seconds_input:
        try:
            config['llbot']['wait_seconds'] = int(wait_seconds_input)
        except ValueError:
            print("无效输入，使用默认值")
            logger.warning(f"无效的llbot等待秒数输入: {wait_seconds_input}，使用默认值", 
                          extra={'event_type': 'config_warning'})
    
    print("\n【Yunzai配置】")
    config['yunzai']['git_bash_path'] = input("Git Bash路径 (例: D:\\path\\git-bash.exe): ").strip()
    config['yunzai']['bash_directory'] = input("Yunzai目录 (例: D:\\path\\to\\yunzai): ").strip()
    
    wait_seconds_input = input(f"Yunzai检查间隔秒数 (默认: {config['yunzai']['wait_seconds']}，留空使用默认值): ").strip()
    if wait_seconds_input:
        try:
            config['yunzai']['wait_seconds'] = int(wait_seconds_input)
        except ValueError:
            print("无效输入，使用默认值")
            logger.warning(f"无效的yunzai等待秒数输入: {wait_seconds_input}，使用默认值", 
                          extra={'event_type': 'config_warning'})
    
    print("\n【Redis配置】")
    config['redis'] = {}
    config['redis']['path'] = input("Redis服务器路径 (例: D:\\path\\to\\redis-server.exe): ").strip()
    
    print("\n【HTTP检查配置】")
    config['http_check']['url'] = input("HTTP检查地址 (例: http://localhost:3080): ").strip()
    
    timeout_input = input(f"HTTP检查超时秒数 (默认: {config['http_check']['timeout']}，留空使用默认值): ").strip()
    if timeout_input:
        try:
            config['http_check']['timeout'] = int(timeout_input)
        except ValueError:
            print("无效输入，使用默认值")
            logger.warning(f"无效的HTTP检查超时输入: {timeout_input}，使用默认值", 
                          extra={'event_type': 'config_warning'})
    
    print("\n【Web认证配置】")
    config['web_auth'] = {}
    username_input = input("Web管理界面用户名 (默认: admin，留空使用默认值): ").strip()
    config['web_auth']['username'] = username_input if username_input else "admin"
    password_input = input("Web管理界面密码 (默认: Admin123，留空使用默认值): ").strip()
    config['web_auth']['password'] = password_input if password_input else "Admin123"

    print("\n【自动登录配置】")
    config['auto_login'] = {}
    auto_login_input = input("启用系统自动登录? (Y/N，默认: N): ").strip()
    config['auto_login']['enabled'] = auto_login_input.lower() in ['y', 'yes']
    if config['auto_login']['enabled']:
        auto_login_username = input("自动登录用户名 (留空使用当前用户): ").strip()
        config['auto_login']['username'] = auto_login_username if auto_login_username else ""
        auto_login_password = input("自动登录密码: ").strip()
        config['auto_login']['password'] = auto_login_password if auto_login_password else ""
    else:
        config['auto_login']['username'] = ""
        config['auto_login']['password'] = ""

    print("\n【Git仓库更新检测配置】")
    config['git_update'] = {}
    git_update_input = input("启用Git仓库自动更新检测? (Y/N，默认: N): ").strip()
    config['git_update']['enabled'] = git_update_input.lower() in ['y', 'yes']
    if config['git_update']['enabled']:
        check_interval_input = input("检测间隔秒数 (默认: 3600，即1小时): ").strip()
        if check_interval_input:
            try:
                config['git_update']['check_interval'] = int(check_interval_input)
            except ValueError:
                print("无效输入，使用默认值")
                config['git_update']['check_interval'] = 3600
        else:
            config['git_update']['check_interval'] = 3600
        
        auto_pull_input = input("检测到更新后自动拉取并重启? (Y/N，默认: N): ").strip()
        config['git_update']['auto_pull'] = auto_pull_input.lower() in ['y', 'yes']
        
        if config['git_update']['auto_pull']:
            auto_restart_input = input("拉取成功后自动重启监控脚本? (Y/N，默认: N): ").strip()
            config['git_update']['auto_restart'] = auto_restart_input.lower() in ['y', 'yes']
        else:
            config['git_update']['auto_restart'] = False
    else:
        config['git_update']['check_interval'] = 3600
        config['git_update']['auto_pull'] = False
        config['git_update']['auto_restart'] = False

    logger.info("交互式配置完成", extra={'event_type': 'config_complete'})
    print("\n配置完成！")
    return config

def save_config(config, config_path):
    """保存配置到文件，使用原子性写入确保数据完整性"""
    import tempfile
    import shutil

    # 读取现有配置文件以保留原有密码
    existing_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                existing_config = yaml.safe_load(file) or {}
        except Exception as e:
            logger.warning(f"读取现有配置文件失败: {str(e)}", extra={
                'event_type': 'warning',
                'config_path': config_path,
                'error': str(e)
            })

    # 创建配置的副本以避免修改原始配置
    config_to_save = {}
    for key, value in config.items():
        if isinstance(value, dict):
            config_to_save[key] = {}
            for sub_key, sub_value in value.items():
                # 对 web_auth 中的密码进行加密
                if key == 'web_auth' and sub_key == 'password':
                    # 如果密码为 None，从现有配置中保留原有密码
                    if sub_value is None:
                        if key in existing_config and sub_key in existing_config[key]:
                            config_to_save[key][sub_key] = existing_config[key][sub_key]
                        # 否则不保存该字段
                    else:
                        # 检查密码是否已加密
                        if not PasswordCrypt.is_encrypted(sub_value):
                            # 加密密码
                            try:
                                config_to_save[key][sub_key] = PasswordCrypt.encrypt(sub_value)
                            except Exception as e:
                                logger.warning(f"密码加密失败，使用明文保存: {str(e)}", extra={
                                    'event_type': 'warning',
                                    'config_path': config_path,
                                    'error': str(e)
                                })
                                config_to_save[key][sub_key] = sub_value
                        else:
                            # 已经是加密的，直接使用
                            config_to_save[key][sub_key] = sub_value
                # 对 auto_login 中的密码进行加密
                elif key == 'auto_login' and sub_key == 'password':
                    # 如果密码为 None，从现有配置中保留原有密码
                    if sub_value is None:
                        if key in existing_config and sub_key in existing_config[key]:
                            config_to_save[key][sub_key] = existing_config[key][sub_key]
                        # 否则不保存该字段
                    elif sub_value:
                        # 检查密码是否已加密
                        if not PasswordCrypt.is_encrypted(sub_value):
                            # 加密密码
                            try:
                                config_to_save[key][sub_key] = PasswordCrypt.encrypt(sub_value)
                            except Exception as e:
                                logger.warning(f"自动登录密码加密失败，使用明文保存: {str(e)}", extra={
                                    'event_type': 'warning',
                                    'config_path': config_path,
                                    'error': str(e)
                                })
                                config_to_save[key][sub_key] = sub_value
                        else:
                            # 已经是加密的，直接使用
                            config_to_save[key][sub_key] = sub_value
                    # 如果是空字符串，从现有配置中保留原有密码
                    elif key in existing_config and sub_key in existing_config[key]:
                        config_to_save[key][sub_key] = existing_config[key][sub_key]
                else:
                    config_to_save[key][sub_key] = sub_value
        else:
            config_to_save[key] = value

    # 使用临时文件进行原子性写入
    temp_path = None
    try:
        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp(
            prefix='.config_',
            suffix='.tmp',
            dir=os.path.dirname(os.path.abspath(config_path))
        )

        # 写入配置到临时文件
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_file:
            yaml.dump(config_to_save, temp_file, default_flow_style=False, allow_unicode=True)
            # 强制刷新缓冲区到磁盘
            temp_file.flush()
            # 确保数据写入物理磁盘（不仅仅是操作系统缓存）
            os.fsync(temp_file.fileno())

        # 原子性替换原文件
        shutil.move(temp_path, config_path)

        logger.info(f"配置已保存到 {config_path}", extra={'event_type': 'config_save', 'config_path': config_path})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置已保存到 {config_path}")

        # 验证文件是否成功写入
        if not os.path.exists(config_path):
            raise IOError(f"配置文件保存失败: {config_path} 不存在")

        # 验证文件内容是否有效
        with open(config_path, 'r', encoding='utf-8') as file:
            try:
                yaml.safe_load(file)
            except yaml.YAMLError as e:
                raise IOError(f"配置文件内容无效: {str(e)}")

    except Exception as e:
        # 清理临时文件（如果存在）
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        logger.error(f"保存配置失败: {str(e)}", extra={'event_type': 'config_save_error', 'config_path': config_path, 'error': str(e)})
        raise

def validate_config(config, config_path="config.yaml"):
    """验证配置文件的完整性，检查所有必需的配置项"""
    required_fields = {
        'llbot': {
            'path': str,
            'directory': str,
            'wait_seconds': int
        },
        'yunzai': {
            'git_bash_path': str,
            'bash_directory': str,
            'wait_seconds': int
        },
        'redis': {
            'path': str
        },
        'http_check': {
            'url': str,
            'timeout': int
        },
        'auto_restart': {
            'enabled': bool,
            'respect_manual_stop': bool
        },
        'auto_login': {
            'enabled': bool,
            'username': str,
            'password': str
        },
        'web_auth': {
            'username': str,
            'password': str
        },
        'git_update': {
            'enabled': bool,
            'check_interval': int,
            'auto_pull': bool,
            'auto_restart': bool
        }
    }
    
    missing_fields = []
    invalid_types = []
    
    # 检查顶级配置项
    for section, fields in required_fields.items():
        if section not in config:
            config[section] = {}  # 创建空字典以避免KeyError
            for field, expected_type in fields.items():
                missing_fields.append(f"{section}.{field}")
                # 为新创建的section设置默认值
                if expected_type == str:
                    # 特殊处理：密码字段不设置默认值，保持为 None
                    if field == 'password' and section in ['auto_login', 'web_auth']:
                        config[section][field] = None
                    else:
                        config[section][field] = ""
                elif expected_type == int:
                    if section == 'llbot' and field == 'wait_seconds':
                        config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                    elif section == 'yunzai' and field == 'wait_seconds':
                        config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                    elif section == 'http_check' and field == 'timeout':
                        config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                    elif section == 'git_update' and field == 'check_interval':
                        config[section][field] = DEFAULT_CONFIG['git_update'].get('check_interval', 3600)
                elif expected_type == bool:
                    if section == 'auto_restart' and field == 'enabled':
                        config[section][field] = DEFAULT_CONFIG['auto_restart'].get('enabled', True)
                    elif section == 'auto_restart' and field == 'respect_manual_stop':
                        config[section][field] = DEFAULT_CONFIG['auto_restart'].get('respect_manual_stop', True)
                    elif section == 'git_update':
                        if field == 'enabled':
                            config[section][field] = DEFAULT_CONFIG['git_update'].get('enabled', False)
                        elif field == 'auto_pull':
                            config[section][field] = DEFAULT_CONFIG['git_update'].get('auto_pull', False)
                        elif field == 'auto_restart':
                            config[section][field] = DEFAULT_CONFIG['git_update'].get('auto_restart', False)
        else:
            # 检查该部分中的字段
            for field, expected_type in fields.items():
                if field not in config[section]:
                    missing_fields.append(f"{section}.{field}")
                    # 设置默认值
                    if expected_type == str:
                        # 特殊处理：密码字段不设置默认值，保持为 None
                        if field == 'password' and section in ['auto_login', 'web_auth']:
                            config[section][field] = None
                        else:
                            config[section][field] = ""
                    elif expected_type == int:
                        if section == 'llbot' and field == 'wait_seconds':
                            config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                        elif section == 'yunzai' and field == 'wait_seconds':
                            config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                        elif section == 'http_check' and field == 'timeout':
                            config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                    elif expected_type == bool:
                        if section == 'auto_restart' and field == 'enabled':
                            config[section][field] = DEFAULT_CONFIG['auto_restart'].get('enabled', True)
                        elif section == 'auto_restart' and field == 'respect_manual_stop':
                            config[section][field] = DEFAULT_CONFIG['auto_restart'].get('respect_manual_stop', True)
                else:
                    # 验证字段类型
                    actual_value = config[section][field]
                    if actual_value is None:
                        # 如果值为None，设置默认值
                        if expected_type == str:
                            # 特殊处理：密码字段保持为 None，不设置默认值
                            if field == 'password' and section in ['auto_login', 'web_auth']:
                                config[section][field] = None
                            else:
                                config[section][field] = ""
                        elif expected_type == int:
                            if section == 'llbot' and field == 'wait_seconds':
                                config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                            elif section == 'yunzai' and field == 'wait_seconds':
                                config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                            elif section == 'http_check' and field == 'timeout':
                                config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                        elif expected_type == bool:
                            if section == 'auto_restart' and field == 'enabled':
                                config[section][field] = DEFAULT_CONFIG['auto_restart'].get('enabled', True)
                            elif section == 'auto_restart' and field == 'respect_manual_stop':
                                config[section][field] = DEFAULT_CONFIG['auto_restart'].get('respect_manual_stop', True)
                    elif not isinstance(actual_value, expected_type) or (expected_type == int and isinstance(actual_value, bool)):
                        # 特别处理：布尔值不是整数，即使Python中bool是int的子类
                        invalid_types.append(f"{section}.{field} (期望 {expected_type.__name__}，实际 {type(actual_value).__name__})")
                        # 尝试转换类型或设置默认值
                        if expected_type == str:
                            config[section][field] = str(actual_value) if actual_value is not None else ""
                        elif expected_type == int:
                            try:
                                config[section][field] = int(actual_value) if actual_value is not None and not isinstance(actual_value, bool) else (
                                    DEFAULT_CONFIG[section].get(field, 5) if section in DEFAULT_CONFIG and field in DEFAULT_CONFIG[section] else 5
                                )
                                # 如果原始值是布尔值，使用默认值而不是转换
                                if isinstance(actual_value, bool):
                                    if section == 'llbot' and field == 'wait_seconds':
                                        config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                                    elif section == 'yunzai' and field == 'wait_seconds':
                                        config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                                    elif section == 'http_check' and field == 'timeout':
                                        config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                                    else:
                                        config[section][field] = 5  # 默认整数值
                            except (ValueError, TypeError):
                                # 如果转换失败，使用默认值
                                if section == 'llbot' and field == 'wait_seconds':
                                    config[section][field] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
                                elif section == 'yunzai' and field == 'wait_seconds':
                                    config[section][field] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
                                elif section == 'http_check' and field == 'timeout':
                                    config[section][field] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
                                else:
                                    config[section][field] = 5  # 默认整数值
                        elif expected_type == bool:
                            # 将各种值转换为布尔值
                            if isinstance(actual_value, str):
                                config[section][field] = actual_value.lower() in ['true', '1', 'yes', 'on']
                            else:
                                config[section][field] = bool(actual_value)
    
    # 记录验证结果（排除 auto_login.password 字段，因为该字段不应该有默认值）
    non_password_missing_fields = [field for field in missing_fields if field != 'auto_login.password']
    if non_password_missing_fields:
        logger.warning(f"配置文件中缺少以下字段，已设置默认值: {', '.join(non_password_missing_fields)}", extra={
            'event_type': 'warning',
            'missing_fields': non_password_missing_fields,
            'config_path': config_path,
            'action': 'set_defaults'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 配置文件中缺少以下字段，已设置默认值: {', '.join(non_password_missing_fields)}")
    
    if invalid_types:
        logger.warning(f"配置文件中以下字段类型不正确，已尝试修复: {', '.join(invalid_types)}", extra={
            'event_type': 'warning',
            'invalid_types': invalid_types,
            'config_path': config_path,
            'action': 'fix_types'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 配置文件中以下字段类型不正确，已尝试修复: {', '.join(invalid_types)}")
    
    # 额外的业务逻辑验证
    validation_warnings = []
    
    # 检查HTTP URL格式
    http_url = config.get('http_check', {}).get('url', '')
    # 确保http_url是字符串
    if not isinstance(http_url, str):
        http_url = str(http_url) if http_url is not None else ""
    if http_url and not http_url.startswith(('http://', 'https://')):
        validation_warnings.append("HTTP检查URL应以http://或https://开头")
    
    # 检查路径是否存在（仅对非空路径检查）
    llbot_path = config.get('llbot', {}).get('path', '')
    # 确保llbot_path是字符串
    if not isinstance(llbot_path, str):
        llbot_path = str(llbot_path) if llbot_path is not None else ""
    if llbot_path and llbot_path != "" and not os.path.exists(llbot_path):
        validation_warnings.append(f"llbot路径不存在: {llbot_path}")
    
    yunzai_dir = config.get('yunzai', {}).get('bash_directory', '')
    # 确保yunzai_dir是字符串
    if not isinstance(yunzai_dir, str):
        yunzai_dir = str(yunzai_dir) if yunzai_dir is not None else ""
    if yunzai_dir and yunzai_dir != "" and not os.path.exists(yunzai_dir):
        validation_warnings.append(f"Yunzai目录不存在: {yunzai_dir}")
    
    redis_path = config.get('redis', {}).get('path', '')
    # 确保redis_path是字符串
    if not isinstance(redis_path, str):
        redis_path = str(redis_path) if redis_path is not None else ""
    if redis_path and redis_path != "" and not os.path.exists(os.path.dirname(redis_path)):
        validation_warnings.append(f"Redis路径不存在: {redis_path}")
    
    if validation_warnings:
        logger.warning(f"配置文件存在以下问题: {', '.join(validation_warnings)}", extra={
            'event_type': 'warning',
            'validation_warnings': validation_warnings,
            'config_path': config_path
        })
        for warning in validation_warnings:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: {warning}")
    
    return config


def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        logger.info("配置文件不存在，启动交互式配置", extra={'event_type': 'config_missing', 'config_path': config_path})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置文件不存在，正在启动交互式配置...")
        config = interactive_config()
        save_config(config, config_path)
        # 验证新创建的配置
        config = validate_config(config, config_path)
        return config
    else:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        # 验证并完善配置
        config = validate_config(config, config_path)

        # 解密 web_auth 中的密码（如果已加密）
        if 'web_auth' in config and 'password' in config['web_auth']:
            encrypted_password = config['web_auth']['password']
            if PasswordCrypt.is_encrypted(encrypted_password):
                try:
                    decrypted_password = PasswordCrypt.decrypt(encrypted_password)
                    config['web_auth']['password'] = decrypted_password
                    logger.debug("密码已解密", extra={'event_type': 'config_load', 'config_path': config_path})
                except Exception as e:
                    logger.warning(f"密码解密失败，使用原始值: {str(e)}", extra={
                        'event_type': 'warning',
                        'config_path': config_path,
                        'error': str(e)
                    })

        # 解密 auto_login 中的密码（如果已加密）
        if 'auto_login' in config and 'password' in config['auto_login'] and config['auto_login']['password']:
            encrypted_password = config['auto_login']['password']
            if PasswordCrypt.is_encrypted(encrypted_password):
                try:
                    decrypted_password = PasswordCrypt.decrypt(encrypted_password)
                    config['auto_login']['password'] = decrypted_password
                    logger.debug("自动登录密码已解密", extra={'event_type': 'config_load', 'config_path': config_path})
                except Exception as e:
                    logger.warning(f"自动登录密码解密失败，使用原始值: {str(e)}", extra={
                        'event_type': 'warning',
                        'config_path': config_path,
                        'error': str(e)
                    })

        logger.info(f"配置文件已加载: {config_path}", extra={'event_type': 'config_load', 'config_path': config_path})
        return config

def save_default_config(config_path):
    """保存默认配置到文件"""
    # 创建默认配置，只保留wait_seconds和timeout的默认值，其他留空
    full_default_config = {
        "llbot": {
            "path": "",
            "directory": "",
            "wait_seconds": 5
        },
        "yunzai": {
            "git_bash_path": "",
            "bash_directory": "",
            "wait_seconds": 5
        },
        "redis": {
            "path": ""
        },
        "http_check": {
            "url": "",
            "timeout": 5
        },
        "auto_restart": {
            "enabled": True,
            "respect_manual_stop": True
        },
        "auto_login": {
            "enabled": False,
            "username": "",
            "password": ""
        },
        "web_auth": {
            "username": "admin",
            "password": "Admin123"
        },
        "git_update": {
            "enabled": False,
            "check_interval": 3600,
            "auto_pull": False,
            "auto_restart": False
        }
    }
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(full_default_config, file, default_flow_style=False, allow_unicode=True)
