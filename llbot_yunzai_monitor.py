# -*- coding: utf-8 -*-
import os
import sys
import time
import subprocess
import threading
import requests
import psutil
import yaml
from datetime import datetime

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
    }
}

def interactive_config():
    """交互式配置函数，让用户输入配置项"""
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
    config['llbot']['path'] = input("llbot.exe路径 (例: D:\\\\path\\\\to\\\\llbot.exe): ").strip()
    config['llbot']['directory'] = input("llbot目录 (例: D:\\\\path\\\\to\\\\llbot): ").strip()
    
    wait_seconds_input = input(f"llbot检查间隔秒数 (默认: {config['llbot']['wait_seconds']}，留空使用默认值): ").strip()
    if wait_seconds_input:
        try:
            config['llbot']['wait_seconds'] = int(wait_seconds_input)
        except ValueError:
            print("无效输入，使用默认值")
    
    print("\n【Yunzai配置】")
    config['yunzai']['git_bash_path'] = input("Git Bash路径 (例: D:\\\\Git\\\\git-bash.exe): ").strip()
    config['yunzai']['bash_directory'] = input("Yunzai目录 (例: D:\\\\path\\\\to\\\\yunzai): ").strip()
    
    wait_seconds_input = input(f"Yunzai检查间隔秒数 (默认: {config['yunzai']['wait_seconds']}，留空使用默认值): ").strip()
    if wait_seconds_input:
        try:
            config['yunzai']['wait_seconds'] = int(wait_seconds_input)
        except ValueError:
            print("无效输入，使用默认值")
    
    print("\n【Redis配置】")
    config['redis'] = {}
    config['redis']['path'] = input("Redis服务器路径 (例: D:\\\\path\\\\to\\\\redis-server.exe): ").strip()
    
    print("\n【HTTP检查配置】")
    config['http_check']['url'] = input("HTTP检查地址 (例: http://localhost:3080): ").strip()
    
    timeout_input = input(f"HTTP检查超时秒数 (默认: {config['http_check']['timeout']}，留空使用默认值): ").strip()
    if timeout_input:
        try:
            config['http_check']['timeout'] = int(timeout_input)
        except ValueError:
            print("无效输入，使用默认值")
    
    print("\n配置完成！")
    return config

def save_config(config, config_path):
    """保存配置到文件"""
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(config, file, default_flow_style=False, allow_unicode=True)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置已保存到 {config_path}")

def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置文件不存在，正在启动交互式配置...")
        config = interactive_config()
        save_config(config, config_path)
        return config
    else:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            
        # 确保配置项完整
        if 'llbot' not in config:
            config['llbot'] = {}
        if 'yunzai' not in config:
            config['yunzai'] = {}
        if 'redis' not in config:
            config['redis'] = {}
        if 'http_check' not in config:
            config['http_check'] = {}
        
        # 为wait_seconds和timeout设置默认值（如果未提供或为空）
        if 'wait_seconds' not in config['llbot'] or not config['llbot']['wait_seconds']:
            config['llbot']['wait_seconds'] = DEFAULT_CONFIG['llbot'].get('wait_seconds', 5)
        if 'wait_seconds' not in config['yunzai'] or not config['yunzai']['wait_seconds']:
            config['yunzai']['wait_seconds'] = DEFAULT_CONFIG['yunzai'].get('wait_seconds', 5)
        if 'timeout' not in config['http_check'] or not config['http_check']['timeout']:
            config['http_check']['timeout'] = DEFAULT_CONFIG['http_check'].get('timeout', 5)
        if 'url' not in config['http_check'] or not config['http_check']['url']:
            config['http_check']['url'] = "http://localhost:3080"
        
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
            "url": "http://localhost:3080",
            "timeout": 5
        }
    }
    with open(config_path, 'w', encoding='utf-8') as file:
        yaml.dump(full_default_config, file, default_flow_style=False, allow_unicode=True)

def is_admin():
    """检查当前是否以管理员权限运行"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """以管理员权限重新运行脚本"""
    if is_admin():
        return True
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在请求管理员权限...")
    try:
        # 重新运行脚本并请求管理员权限
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([script] + sys.argv[1:])
        subprocess.run([
            "powershell", 
            "-Command", 
            f"Start-Process python -ArgumentList '{params}' -Verb RunAs"
        ])
        return False  # 原始进程应该退出
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 请求管理员权限时出错: {str(e)}")
        return False

def check_admin():
    """检查是否以管理员权限运行"""
    if is_admin():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 以管理员权限运行 - 进程终止功能应正常工作")
        return True
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 未以管理员权限运行")
        return False

def terminate_process_by_name(process_name):
    """通过名称终止进程"""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == process_name.lower():
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在终止进程 {process_name} (PID: {proc.info['pid']})")
                proc.kill()
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功终止进程 {process_name} (PID: {proc.info['pid']})")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 终止进程 {process_name} 时出错: {str(e)}")

def terminate_processes_by_powershell(names):
    """使用PowerShell终止多个相关进程"""
    for name in names:
        try:
            result = subprocess.run([
                "powershell", 
                "-Command", 
                f"Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Stop-Process -Force"
            ], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功终止 {name} 进程")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {name} 进程不存在或终止失败")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 终止 {name} 进程时出错: {str(e)}")

def check_and_manage_llbot(config):
    """检查并管理llbot进程"""
    try:
        # 检查必要配置项是否为空
        if not config['http_check']['url']:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: HTTP检查地址未配置")
            return
        
        # 检查http://localhost:3080是否可访问
        response = requests.get(config['http_check']['url'], timeout=config['http_check']['timeout'])
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {config['http_check']['url']} 可访问...")
            
            # 检查llbot.exe是否仍在运行
            if not config['llbot']['path']:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot路径未配置")
                return
                
            llbot_running = False
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == os.path.basename(config['llbot']['path']).lower():
                    llbot_running = True
                    break
            
            if llbot_running:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {os.path.basename(config['llbot']['path'])} 进程正在运行...")
            else:
                # llbot.exe未运行但网站应该可访问，清理相关进程后重新启动它
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {os.path.basename(config['llbot']['path'])} 进程未运行但网站应该可访问，正在清理相关进程并重启...")
                restart_llbot_with_cleanup(config)
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {config['http_check']['url']} 不可访问，正在终止相关进程并重启llbot...")
            restart_llbot_with_cleanup(config)
    except requests.RequestException:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {config['http_check']['url']} 不可访问，正在终止相关进程并重启llbot...")
        restart_llbot_with_cleanup(config)
    except KeyError as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise

def restart_llbot_with_cleanup(config):
    """清理相关进程后重启llbot"""
    # 终止flet.exe进程
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止flet.exe进程...")
    terminate_process_by_name("flet.exe")
    
    # 终止QQ相关进程
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止QQ相关进程...")
    qq_processes = ["QQ", "QQProtect", "QQPCRTP"]
    terminate_processes_by_powershell(qq_processes)
    
    # 使用taskkill额外清理
    for name in ["QQ.exe", "QQProtect.exe", "QQPCRTP.exe"]:
        try:
            subprocess.run(["taskkill", "/f", "/im", name, "/t"], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    
    # 额外等待确保进程完全终止
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 等待进程完全终止...")
    time.sleep(3)
    
    # 重新启动llbot
    restart_llbot(config)

def restart_llbot(config):
    """重启llbot"""
    try:
        if not config['llbot']['path']:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot路径未配置")
            return
            
        process_name = os.path.basename(config['llbot']['path'])
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动 {process_name}...")
        
        if os.path.exists(config['llbot']['path']):
            if not config['llbot']['directory']:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot目录未配置")
                return
                
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到 {process_name}，正在目录中启动: {config['llbot']['directory']}")
            os.chdir(config['llbot']['directory'])
            subprocess.Popen([config['llbot']['path']])
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 启动成功")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 未找到，请验证路径: {config['llbot']['path']}")
    except KeyError as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise

def check_and_manage_yunzai(config):
    """检查并管理Yunzai进程"""
    try:
        # 检查Redis是否运行
        if not config['redis']['path']:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Redis路径未配置")
            return
            
        redis_running = False
        redis_process_name = os.path.basename(config['redis']['path'])
        for proc in psutil.process_iter(['name']):
            if proc.info['name'].lower() == redis_process_name.lower():
                redis_running = True
                break
        
        if not redis_running:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 未运行，正在启动Redis服务器...")
            try:
                redis_dir = os.path.dirname(config['redis']['path'])
                os.chdir(redis_dir)
                # 使用管理员权限启动Redis
                subprocess.Popen([
                    "powershell", 
                    "-Command", 
                    f"Start-Process '{config['redis']['path']}' -WorkingDirectory '{redis_dir}' -Verb RunAs"
                ])
                time.sleep(3)  # 等待Redis启动
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Redis服务器时出错: {str(e)}")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redis_process_name} 已在运行...")
        
        # 检查Yunzai是否运行
        # 使用默认的process_name
        process_name = 'git-bash.exe'
        
        yunzai_running = False
        for proc in psutil.process_iter(['name']):
            if proc.info['name'].lower() == process_name.lower():
                yunzai_running = True
                break
        
        if not yunzai_running:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程...")
            try:
                if not config['yunzai']['git_bash_path']:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Git Bash路径未配置")
                    return
                if not config['yunzai']['bash_directory']:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Yunzai目录未配置")
                    return
                    
                # 使用git-bash启动Yunzai，使用固定命令"node app"
                subprocess.Popen([
                    config['yunzai']['git_bash_path'],
                    "-c",
                    f"cd '{config['yunzai']['bash_directory']}' && node app"
                ])
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已启动")
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时出错: {str(e)}")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已在运行...")
    except KeyError as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise

def main():
    """主函数"""
    # 加载配置
    config = load_config()

    # 检查管理员权限，如果未以管理员权限运行则请求权限
    if not is_admin():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 脚本需要管理员权限才能正常工作")
        if not run_as_admin():
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 无法获取管理员权限，脚本退出")
            return
        # 如果当前进程不是管理员权限，则退出，让新启动的管理员进程继续
        if not is_admin():
            return
    
    print("=" * 60)
    print("llbot和Yunzai进程监控脚本")
    print("=" * 60)
    
    # 检查管理员权限
    check_admin()
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始监控llbot和Yunzai进程...")
    print("按 Ctrl+C 退出监控")
    
    try:
        while True:
            # 检查并管理llbot进程
            check_and_manage_llbot(config)
            
            # 检查并管理Yunzai进程
            check_and_manage_yunzai(config)
            
            # 等待指定时间后再次检查
            time.sleep(config['llbot']['wait_seconds'])
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控已停止")

if __name__ == "__main__":
    main()
