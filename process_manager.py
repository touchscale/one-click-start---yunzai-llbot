# -*- coding: utf-8 -*-
"""
进程管理模块 - 处理进程的启动、停止、重启等操作
"""
import os
import subprocess
import psutil
import time
from datetime import datetime
from logger import get_logger
from event_manager import get_event_manager
from constants import EventType

logger = get_logger()
event_manager = get_event_manager()

# 全局手动停止状态跟踪 - 记录通过Web界面手动停止的进程
global_manual_stop_status = {
    'llbot': False,
    'yunzai': False,
    'redis': False
}

# 存储yunzai的git-bash进程PID，用于精确终止
yunzai_git_bash_pid = None

def update_global_manual_stop_status(process, value):
    """安全更新全局手动停止状态"""
    global global_manual_stop_status
    global_manual_stop_status[process] = value

def get_global_manual_stop_status(process):
    """安全获取全局手动停止状态"""
    global global_manual_stop_status
    return global_manual_stop_status.get(process, False)

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
        logger.info("已以管理员权限运行", extra={'event_type': 'process_check', 'status': 'already_admin'})
        return True
    
    logger.info("正在请求管理员权限", extra={'event_type': 'admin_request'})
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在请求管理员权限...")
    try:
        # 重新运行脚本并请求管理员权限
        import sys
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([script] + sys.argv[1:])
        subprocess.run([
            "powershell", 
            "-Command", 
            f"Start-Process python -ArgumentList '{params}' -Verb RunAs"
        ])
        logger.info("管理员权限请求已发送", extra={'event_type': 'admin_request_sent'})
        return True
    except Exception as e:
        logger.error(f"请求管理员权限失败: {str(e)}", extra={'event_type': 'error', 'error': str(e)})
        return False

def check_admin():
    """检查管理员权限"""
    if is_admin():
        logger.info("已以管理员权限运行", extra={'event_type': 'process_check', 'status': 'already_admin'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已以管理员权限运行")
        return True
    else:
        logger.warning("未以管理员权限运行", extra={'event_type': 'process_check', 'status': 'not_admin'})
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 未以管理员权限运行，某些功能可能受限")
        return False

def terminate_process_by_name(process_name):
    """通过进程名称终止进程"""
    try:
        terminated = False
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if process_name.lower() in proc.info['name'].lower():
                    # 对于git-bash.exe使用kill强制终止，其他进程使用terminate优雅终止
                    if process_name.lower() in ['git-bash.exe', 'git-bash']:
                        proc.kill()
                    else:
                        proc.terminate()
                    terminated = True
                    logger.info(f"已终止进程: {proc.info['name']} (PID: {proc.info['pid']})", extra={
                        'event_type': EventType.PROCESS_STOP,
                        'process_name': proc.info['name'],
                        'pid': proc.info['pid']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if terminated:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止进程: {process_name}")
        return terminated
    except Exception as e:
        logger.error(f"终止进程 {process_name} 时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'process_name': process_name
        })
        return False

def terminate_yunzai_git_bash_process():
    """终止yunzai的git-bash进程及其子进程，确保git窗口被完全关闭"""
    global yunzai_git_bash_pid
    try:
        if yunzai_git_bash_pid is None:
            logger.warning("未找到yunzai的git-bash进程PID，跳过终止", extra={
                'event_type': 'warning',
                'action': 'skip_terminate_git_bash',
                'reason': 'pid_not_found'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 未找到yunzai的git-bash进程PID，跳过终止")
            return False
        
        try:
            proc = psutil.Process(yunzai_git_bash_pid)
            # 验证进程是否确实是git-bash.exe
            if 'git-bash' not in proc.name().lower():
                logger.warning(f"PID {yunzai_git_bash_pid} 不是git-bash进程，跳过终止", extra={
                    'event_type': 'warning',
                    'action': 'skip_terminate_git_bash',
                    'reason': 'not_git_bash_process',
                    'pid': yunzai_git_bash_pid,
                    'process_name': proc.name()
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: PID {yunzai_git_bash_pid} 不是git-bash进程，跳过终止")
                return False
            
            # 使用taskkill /t参数终止进程树，确保所有子进程都被终止
            # 这样可以确保git窗口及其所有子进程（如node.exe）都被关闭
            try:
                subprocess.run([
                    "taskkill", "/f", "/t", "/pid", str(yunzai_git_bash_pid)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                logger.info(f"已使用taskkill终止yunzai的git-bash进程树 (PID: {yunzai_git_bash_pid})", extra={
                    'event_type': EventType.PROCESS_STOP,
                    'process_name': 'git-bash.exe',
                    'pid': yunzai_git_bash_pid,
                    'source': 'yunzai',
                    'method': 'taskkill_tree'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止yunzai的git-bash进程及其子进程 (PID: {yunzai_git_bash_pid})")
            except subprocess.TimeoutExpired:
                # 如果taskkill超时，使用psutil的kill方法
                logger.warning(f"taskkill超时，使用psutil终止进程", extra={
                    'event_type': 'warning',
                    'action': 'fallback_to_psutil_kill',
                    'pid': yunzai_git_bash_pid
                })
                # 先终止所有子进程
                for child in proc.children(recursive=True):
                    try:
                        child.kill()
                        logger.info(f"已终止子进程: {child.name()} (PID: {child.pid})", extra={
                            'event_type': EventType.PROCESS_STOP,
                            'process_name': child.name(),
                            'pid': child.pid,
                            'parent_pid': yunzai_git_bash_pid
                        })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                # 再终止父进程
                proc.kill()
                logger.info(f"已使用psutil终止yunzai的git-bash进程 (PID: {yunzai_git_bash_pid})", extra={
                    'event_type': EventType.PROCESS_STOP,
                    'process_name': 'git-bash.exe',
                    'pid': yunzai_git_bash_pid,
                    'source': 'yunzai',
                    'method': 'psutil_kill'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止yunzai的git-bash进程 (PID: {yunzai_git_bash_pid})")
            
            # 清除记录的PID
            yunzai_git_bash_pid = None
            return True
        except psutil.NoSuchProcess:
            logger.warning(f"yunzai的git-bash进程 (PID: {yunzai_git_bash_pid}) 已不存在", extra={
                'event_type': 'warning',
                'action': 'skip_terminate_git_bash',
                'reason': 'process_not_exists',
                'pid': yunzai_git_bash_pid
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: yunzai的git-bash进程 (PID: {yunzai_git_bash_pid}) 已不存在")
            yunzai_git_bash_pid = None
            return False
        except psutil.AccessDenied:
            logger.error(f"无权限终止yunzai的git-bash进程 (PID: {yunzai_git_bash_pid})", extra={
                'event_type': EventType.ERROR,
                'error': 'access_denied',
                'pid': yunzai_git_bash_pid
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: 无权限终止yunzai的git-bash进程 (PID: {yunzai_git_bash_pid})")
            return False
    except Exception as e:
        logger.error(f"终止yunzai的git-bash进程时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: 终止yunzai的git-bash进程时出错: {str(e)}")
        return False

def terminate_processes_by_powershell(process_names):
    """使用PowerShell终止多个进程"""
    try:
        for name in process_names:
            try:
                result = subprocess.run([
                    "powershell", "-Command",
                    f"Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Stop-Process -Force"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    logger.info(f"已通过PowerShell终止进程: {name}", extra={
                        'event_type': EventType.PROCESS_STOP,
                        'process_name': name
                    })
            except Exception as e:
                logger.warning(f"终止进程 {name} 失败: {str(e)}", extra={
                    'event_type': 'warning',
                    'error': str(e),
                    'process_name': name
                })
    except Exception as e:
        logger.error(f"使用PowerShell终止进程时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })

def terminate_llbot_process_tree(llbot_path=None):
    """精确终止llbot进程及其所有子进程，不影响其他node.exe进程"""
    try:
        terminated = False
        
        # 确定llbot进程名
        if llbot_path:
            llbot_process_name = os.path.basename(llbot_path).lower()
        else:
            llbot_process_name = 'lucky-lillia-desktop.exe'
        
        # 查找llbot主进程
        llbot_pid = None
        for proc in psutil.process_iter(['name', 'pid', 'cmdline']):
            try:
                proc_name = proc.info['name'].lower()
                if proc_name == llbot_process_name or proc_name == 'llbot.exe':
                    llbot_pid = proc.info['pid']
                    logger.info(f"找到llbot进程: {proc.info['name']} (PID: {llbot_pid})", extra={
                        'event_type': EventType.PROCESS_STOP,
                        'process_name': proc.info['name'],
                        'pid': llbot_pid
                    })
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if llbot_pid:
            try:
                parent_proc = psutil.Process(llbot_pid)
                
                # 终止所有子进程（包括node.exe）
                children = parent_proc.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                        logger.info(f"已终止llbot子进程: {child.name()} (PID: {child.pid})", extra={
                            'event_type': EventType.PROCESS_STOP,
                            'process_name': child.name(),
                            'pid': child.pid,
                            'parent_pid': llbot_pid
                        })
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止llbot子进程: {child.name()} (PID: {child.pid})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                # 终止主进程
                parent_proc.kill()
                logger.info(f"已终止llbot主进程: {parent_proc.name()} (PID: {llbot_pid})", extra={
                    'event_type': EventType.PROCESS_STOP,
                    'process_name': parent_proc.name(),
                    'pid': llbot_pid,
                    'method': 'process_tree_termination'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止llbot主进程: {parent_proc.name()} (PID: {llbot_pid})")
                terminated = True
            except psutil.NoSuchProcess:
                logger.warning(f"llbot进程 (PID: {llbot_pid}) 已不存在", extra={
                    'event_type': 'warning',
                    'action': 'skip_terminate_llbot',
                    'reason': 'process_not_exists',
                    'pid': llbot_pid
                })
            except psutil.AccessDenied:
                logger.error(f"无权限终止llbot进程 (PID: {llbot_pid})", extra={
                    'event_type': EventType.ERROR,
                    'error': 'access_denied',
                    'pid': llbot_pid
                })
        else:
            logger.warning("未找到llbot进程", extra={
                'event_type': 'warning',
                'action': 'skip_terminate_llbot',
                'reason': 'process_not_found'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 警告: 未找到llbot进程")
        
        # 也尝试终止pmhq-win-x64.exe和flet.exe（llbot依赖进程）
        for dep_process in ["pmhq-win-x64.exe", "flet.exe"]:
            try:
                for proc in psutil.process_iter(['name', 'pid']):
                    try:
                        if dep_process.lower() in proc.info['name'].lower():
                            proc.kill()
                            logger.info(f"已终止llbot依赖进程: {proc.info['name']} (PID: {proc.info['pid']})", extra={
                                'event_type': EventType.PROCESS_STOP,
                                'process_name': proc.info['name'],
                                'pid': proc.info['pid'],
                                'dependency': 'llbot'
                            })
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止llbot依赖进程: {proc.info['name']} (PID: {proc.info['pid']})")
                            terminated = True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception as e:
                logger.warning(f"终止{dep_process}失败: {str(e)}", extra={
                    'event_type': 'warning',
                    'error': str(e),
                    'process_name': dep_process
                })
        
        # 终止QQ相关进程及其子进程
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止QQ相关进程及其子进程...")
        qq_processes = ["QQ", "QQProtect", "QQPCRTP"]
        for qq_process in qq_processes:
            try:
                for proc in psutil.process_iter(['name', 'pid']):
                    try:
                        if qq_process.lower() in proc.info['name'].lower():
                            # 先终止所有子进程(包括crashpad_handler.exe)
                            children = proc.children(recursive=True)
                            for child in children:
                                try:
                                    child.kill()
                                    logger.info(f"已终止QQ子进程: {child.name()} (PID: {child.pid})", extra={
                                        'event_type': EventType.PROCESS_STOP,
                                        'process_name': child.name(),
                                        'pid': child.pid,
                                        'parent_pid': proc.info['pid']
                                    })
                                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止QQ子进程: {child.name()} (PID: {child.pid})")
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                            # 再终止主进程
                            proc.kill()
                            logger.info(f"已终止QQ进程: {proc.info['name']} (PID: {proc.info['pid']})", extra={
                                'event_type': EventType.PROCESS_STOP,
                                'process_name': proc.info['name'],
                                'pid': proc.info['pid']
                            })
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 已终止QQ进程: {proc.info['name']} (PID: {proc.info['pid']})")
                            terminated = True
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception as e:
                logger.warning(f"终止{qq_process}失败: {str(e)}", extra={
                    'event_type': 'warning',
                    'error': str(e),
                    'process_name': qq_process
                })
        
        return terminated
    except Exception as e:
        logger.error(f"终止llbot进程树时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return False

def restart_llbot_with_cleanup(config):
    """清理相关进程后重启llbot"""
    # 精确终止llbot进程及其子进程
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 尝试终止llbot进程及其子进程...")
    terminate_llbot_process_tree(config.get('llbot', {}).get('path'))
    
    # 额外等待确保进程完全终止
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 等待进程完全终止...")
    time.sleep(3)
    
    # 重新启动llbot
    restart_llbot(config)

def restart_llbot(config):
    """重启llbot"""
    try:
        logger.info("开始执行restart_llbot函数", extra={
            'event_type': EventType.PROCESS_START,
            'action': 'restart_llbot_start',
            'config_path': config.get('llbot', {}).get('path', '未配置')
        })
        
        if not config.get('llbot', {}).get('path'):
            logger.error("llbot路径未配置，无法重启", extra={
                'event_type': EventType.ERROR,
                'error': 'llbot_path_not_configured'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot路径未配置")
            return
            
        process_name = os.path.basename(config['llbot']['path'])
        logger.info(f"准备启动llbot进程: {process_name}", extra={
            'event_type': EventType.PROCESS_START,
            'process_name': process_name,
            'full_path': config['llbot']['path']
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动 {process_name}...")
        
        if os.path.exists(config['llbot']['path']):
            if not config.get('llbot', {}).get('directory'):
                logger.error("llbot目录未配置，无法重启", extra={
                    'event_type': EventType.ERROR,
                    'error': 'llbot_directory_not_configured'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: llbot目录未配置")
                return
                
            logger.info(f"切换到工作目录: {config['llbot']['directory']}", extra={
                'event_type': EventType.PROCESS_START,
                'working_directory': config['llbot']['directory']
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到 {process_name}，正在目录中启动: {config['llbot']['directory']}")
            os.chdir(config['llbot']['directory'])
            
            # 启动进程
            process = subprocess.Popen([config['llbot']['path']])
            logger.info(f"llbot进程已启动，PID: {process.pid}", extra={
                'event_type': EventType.PROCESS_START,
                'process_name': process_name,
                'pid': process.pid,
                'command': config['llbot']['path']
            })
            
            # 清除手动停止状态
            try:
                update_global_manual_stop_status('llbot', False)
                logger.info("已清除llbot手动停止状态", extra={
                    'event_type': EventType.PROCESS_START,
                    'action': 'clear_manual_stop_status'
                })
            except Exception as e:
                logger.warning(f"清除手动停止状态失败: {str(e)}", extra={
                    'event_type': 'warning',
                    'error': str(e)
                })
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 启动成功 (PID: {process.pid})")
        else:
            logger.error(f"llbot可执行文件未找到: {config['llbot']['path']}", extra={
                'event_type': EventType.ERROR,
                'error': 'llbot_executable_not_found',
                'path': config['llbot']['path']
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 未找到，请验证路径: {config['llbot']['path']}")
    except KeyError as e:
        logger.error(f"配置错误 - 缺少必需的配置项: {e}", extra={
            'event_type': EventType.ERROR,
            'error': 'config_key_missing',
            'missing_key': str(e)
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配置错误: 缺少必需的配置项 {e}")
        raise
    except Exception as e:
        logger.error(f"重启llbot时发生未知错误: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 重启llbot时发生错误: {str(e)}")

def start_yunzai(config):
    """启动Yunzai进程"""
    try:
        process_name = os.path.basename(config['yunzai']['git_bash_path'])
        logger.info(f"准备启动Yunzai进程: {process_name}", extra={
            'event_type': EventType.PROCESS_START,
            'process_name': process_name,
            'full_path': config['yunzai']['git_bash_path']
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动 {process_name}...")
        
        if os.path.exists(config['yunzai']['git_bash_path']):
            if not config.get('yunzai', {}).get('bash_directory'):
                logger.error("Yunzai目录未配置，无法启动", extra={
                    'event_type': EventType.ERROR,
                    'error': 'yunzai_directory_not_configured'
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 错误: Yunzai目录未配置")
                return None
                
            logger.info(f"切换到工作目录: {config['yunzai']['bash_directory']}", extra={
                'event_type': EventType.PROCESS_START,
                'working_directory': config['yunzai']['bash_directory']
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 找到 {process_name}，正在目录中启动: {config['yunzai']['bash_directory']}")
            
            # 使用git-bash启动Yunzai，使用固定命令"node app"
            start_command = [
                config['yunzai']['git_bash_path'],
                "-c",
                f"cd '{config['yunzai']['bash_directory']}' && node app"
            ]
            result = subprocess.Popen(start_command)
            logger.info(f"Yunzai启动命令已执行，PID: {result.pid}", extra={
                'event_type': EventType.PROCESS_START,
                'process_name': process_name,
                'pid': result.pid,
                'start_time': datetime.now().isoformat(),
                'command': start_command
            })
            
            # 记录git-bash进程的PID，用于精确终止
            global yunzai_git_bash_pid
            yunzai_git_bash_pid = result.pid
            logger.info(f"已记录yunzai的git-bash进程PID: {yunzai_git_bash_pid}", extra={
                'event_type': EventType.PROCESS_START,
                'git_bash_pid': yunzai_git_bash_pid
            })
            
            # 清除手动停止状态
            try:
                update_global_manual_stop_status('yunzai', False)
            except:
                pass  # 如果全局变量不存在，跳过
            
            logger.info("Yunzai进程已启动", extra={
                'event_type': EventType.PROCESS_START, 
                'process_name': process_name,
                'status': 'success',
                'pid': result.pid
            })
            event_manager.publish(EventType.PROCESS_START, {
                'process_name': process_name,
                'status': 'success',
                'pid': result.pid,
                'command_used': start_command
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Yunzai进程已启动")
            return result
        else:
            logger.error(f"Git Bash可执行文件未找到: {config['yunzai']['git_bash_path']}", extra={
                'event_type': EventType.ERROR, 
                'process_name': process_name, 
                'error': 'file_not_found',
                'config_git_bash': config['yunzai']['git_bash_path'],
                'suggestion': '请检查Git Bash路径配置是否正确'
            })
            event_manager.publish(EventType.ERROR, {
                'message': f'Git Bash可执行文件未找到: {config["yunzai"]["git_bash_path"]}',
                'process_name': process_name,
                'error': 'file_not_found',
                'config_git_bash': config['yunzai']['git_bash_path'],
                'suggestion': '请检查Git Bash路径配置是否正确'
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Git Bash可执行文件未找到: {config['yunzai']['git_bash_path']}")
            return None
    except FileNotFoundError as e:
        logger.error(f"Git Bash可执行文件或Yunzai目录未找到: {str(e)}", extra={
            'event_type': EventType.ERROR, 
            'error': str(e), 
            'error_type': 'file_not_found',
            'config_git_bash': config.get('yunzai', {}).get('git_bash_path', ''),
            'config_bash_directory': config.get('yunzai', {}).get('bash_directory', ''),
            'suggestion': '请检查Git Bash路径和Yunzai目录配置是否正确'
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'Git Bash可执行文件或Yunzai目录未找到: {str(e)}',
            'error': str(e),
            'error_type': 'file_not_found',
            'config_git_bash': config.get('yunzai', {}).get('git_bash_path', ''),
            'config_bash_directory': config.get('yunzai', {}).get('bash_directory', ''),
            'suggestion': '请检查Git Bash路径和Yunzai目录配置是否正确'
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Git Bash可执行文件或Yunzai目录未找到: {str(e)}")
        return None
    except subprocess.SubprocessError as e:
        logger.error(f"启动Yunzai进程时出错: {str(e)}", extra={
            'event_type': EventType.ERROR, 
            'error': str(e), 
            'error_type': 'subprocess_error',
            'error_class': type(e).__name__,
            'working_directory': config.get('yunzai', {}).get('bash_directory', '')
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'启动Yunzai进程时出错: {str(e)}',
            'error': str(e),
            'error_type': 'subprocess_error',
            'error_class': type(e).__name__,
            'working_directory': config.get('yunzai', {}).get('bash_directory', '')
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时出错: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"启动Yunzai进程时发生未知错误: {str(e)}", extra={
            'event_type': EventType.ERROR, 
            'error': str(e), 
            'error_type': 'unknown_error',
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc(),
            'config_keys': list(config.get('yunzai', {}).keys()) if 'config' in locals() else []
        })
        event_manager.publish(EventType.ERROR, {
            'message': f'启动Yunzai进程时发生未知错误: {str(e)}',
            'error': str(e),
            'error_type': 'unknown_error',
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Yunzai进程时发生未知错误: {str(e)}")
        return None

def start_redis(config):
    """启动Redis进程"""
    try:
        process_name = os.path.basename(config['redis']['path'])
        logger.info(f"准备启动Redis进程: {process_name}", extra={
            'event_type': EventType.PROCESS_START,
            'process_name': process_name,
            'full_path': config['redis']['path']
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动 {process_name}...")
        
        if os.path.exists(config['redis']['path']):
            # 获取Redis目录
            redis_dir = os.path.dirname(config['redis']['path'])
            
            # 切换到Redis目录
            if redis_dir:
                logger.info(f"切换到Redis目录: {redis_dir}", extra={
                    'event_type': EventType.PROCESS_START,
                    'working_directory': redis_dir
                })
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 切换到Redis目录: {redis_dir}")
                os.chdir(redis_dir)
            
            # 记录启动Redis的命令
            start_command = [
                "powershell", 
                "-Command", 
                f"Start-Process '{config['redis']['path']}' -WorkingDirectory '{redis_dir}' -Verb RunAs"
            ]
            
            # 使用管理员权限启动Redis
            process = subprocess.Popen(start_command)
            logger.info(f"Redis进程已启动，PID: {process.pid}", extra={
                'event_type': EventType.PROCESS_START,
                'process_name': process_name,
                'pid': process.pid,
                'command': config['redis']['path']
            })
            
            # 清除手动停止状态
            try:
                update_global_manual_stop_status('redis', False)
                logger.info("已清除redis手动停止状态", extra={
                    'event_type': EventType.PROCESS_START,
                    'action': 'clear_manual_stop_status'
                })
            except Exception as e:
                logger.warning(f"清除手动停止状态失败: {str(e)}", extra={
                    'event_type': 'warning',
                    'error': str(e)
                })
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 启动成功 (PID: {process.pid})")
            return process
        else:
            logger.error(f"Redis可执行文件未找到: {config['redis']['path']}", extra={
                'event_type': EventType.ERROR,
                'error': 'redis_executable_not_found',
                'path': config['redis']['path']
            })
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {process_name} 未找到，请验证路径: {config['redis']['path']}")
            return None
    except Exception as e:
        logger.error(f"启动Redis时发生错误: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e),
            'error_class': type(e).__name__,
            'traceback': __import__('traceback').format_exc()
        })
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动Redis时发生错误: {str(e)}")
        return None