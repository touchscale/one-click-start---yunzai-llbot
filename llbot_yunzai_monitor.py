# -*- coding: utf-8 -*-
import os
import sys
import time
import subprocess
import threading
import requests
import psutil
from datetime import datetime

# 配置参数
LLBOT_PATH = r"D:\idm\qqnt\LLBot-Desktop-win-x64\llbot.exe"
LLBOT_DIR = r"D:\idm\qqnt\LLBot-Desktop-win-x64"
LLBOT_PROCESS_NAME = "llbot.exe"
LLBOT_WAIT_SECONDS = 5

GIT_BASH_PATH = r"D:\Git\git-bash.exe"
BASH_DIR = r"D:\idm\Yunzai"
NODE_COMMAND = "node app"
YUNZAI_WAIT_SECONDS = 5
YUNZAI_PROCESS_NAME = "git-bash.exe"

REDIS_DIR = r"D:\idm\Redis-7.2.5-Windows-x64-msys2\Redis-7.2.5-Windows-x64-msys2"
REDIS_PROCESS_NAME = "redis-server.exe"

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

def check_and_manage_llbot():
    """检查并管理llbot进程"""
    try:
        # 检查http://localhost:3080是否可访问
        response = requests.get("http://localhost:3080", timeout=10)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] http://localhost:3080 可访问...")
            
            # 检查llbot.exe是否仍在运行
            llbot_running = False
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == LLBOT_PROCESS_NAME.lower():
                    llbot_running = True
                    break
            
            if llbot_running:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {LLBOT_PROCESS_NAME} 进程正在运行...")
            else:
                # llbot.exe未运行但网站应该可访问，清理相关进程后重新启动它
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {LLBOT_PROCESS_NAME} 进程未运行但网站应该可访问，正在清理相关进程并重启...")
                restart_llbot_with_cleanup()
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] http://localhost:3080 不可访问，正在终止相关进程并重启llbot...")
            restart_llbot_with_cleanup()
    except requests.RequestException:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] http://localhost:3080 不可访问，正在终止相关进程并重启llbot...")
        restart_llbot_with_cleanup()

def restart_llbot_with_cleanup():
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
    restart_llbot()

def restart_llbot():
    """重启llbot"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动 {LLBOT_PROCESS_NAME}...")
    
    if os.path.exists(LLBOT_PATH):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到 {LLBOT_PROCESS_NAME}，正在目录中启动: {LLBOT_DIR}")
        os.chdir(LLBOT_DIR)
        subprocess.Popen([LLBOT_PATH])
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {LLBOT_PROCESS_NAME} 启动成功")
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {LLBOT_PROCESS_NAME} 未找到，请验证路径: {LLBOT_PATH}")

def check_and_manage_yunzai():
    """检查并管理Yunzai进程"""
    # 检查Redis是否运行
    redis_running = False
    for proc in psutil.process_iter(['name']):
        if proc.info['name'].lower() == REDIS_PROCESS_NAME.lower():
            redis_running = True
            break
    
    if not redis_running:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {REDIS_PROCESS_NAME} 未运行，正在启动Redis服务器...")
        try:
            os.chdir(REDIS_DIR)
            # 使用管理员权限启动Redis
            subprocess.Popen([
                "powershell", 
                "-Command", 
                f"Start-Process '{REDIS_PROCESS_NAME}' -Verb RunAs"
            ])
            time.sleep(3)  # 等待Redis启动
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Redis服务器时出错: {str(e)}")
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {REDIS_PROCESS_NAME} 已在运行...")
    
    # 检查Yunzai是否运行
    yunzai_running = False
    for proc in psutil.process_iter(['name']):
        if proc.info['name'].lower() == YUNZAI_PROCESS_NAME.lower():
            yunzai_running = True
            break
    
    if not yunzai_running:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程...")
        try:
            # 使用git-bash启动Yunzai
            subprocess.Popen([
                GIT_BASH_PATH,
                "-c",
                f"cd '{BASH_DIR}' && {NODE_COMMAND}"
            ])
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已启动")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时出错: {str(e)}")
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已在运行...")

def main():
    """主函数"""
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
            check_and_manage_llbot()
            
            # 检查并管理Yunzai进程
            check_and_manage_yunzai()
            
            # 等待指定时间后再次检查
            time.sleep(LLBOT_WAIT_SECONDS)
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控已停止")

if __name__ == "__main__":
    main()
