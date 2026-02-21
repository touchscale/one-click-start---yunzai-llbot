# -*- coding: utf-8 -*-
"""
Git仓库更新检测模块 - 自动检测仓库更新并拉取
"""
import os
import subprocess
import threading
import time
from datetime import datetime
from logger import get_logger
from constants import EventType

logger = get_logger()

# 全局变量，用于控制更新检测线程
git_update_running = False
git_update_thread = None

def run_git_command(repo_path, command, use_git_bash=False, git_bash_path=None):
    """执行Git命令"""
    try:
        if use_git_bash and git_bash_path:
            # 使用Git Bash执行命令
            cmd = f'cd "{repo_path}" && {command}'
            result = subprocess.run(
                [git_bash_path, '-c', cmd],
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
        else:
            # 使用系统Git执行命令
            result = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                shell=True,
                encoding='utf-8',
                errors='replace'
            )
        
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Git命令执行超时: {command}", extra={
            'event_type': EventType.ERROR,
            'repo_path': repo_path,
            'command': command,
            'error': 'timeout'
        })
        return False, "", "命令执行超时"
    except Exception as e:
        logger.error(f"Git命令执行失败: {command}, 错误: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'repo_path': repo_path,
            'command': command,
            'error': str(e)
        })
        return False, "", str(e)

def check_repo_update(repo_path, use_git_bash=False, git_bash_path=None):
    """检查仓库是否有更新"""
    try:
        # 先获取远程最新信息
        success, stdout, stderr = run_git_command(repo_path, 'git fetch', use_git_bash, git_bash_path)
        if not success:
            logger.warning(f"获取远程更新失败: {stderr}", extra={
                'event_type': EventType.WARNING,
                'repo_path': repo_path,
                'error': stderr
            })
            return False, None
        
        # 检查本地是否落后远程
        success, stdout, stderr = run_git_command(repo_path, 'git status -uno', use_git_bash, git_bash_path)
        if not success:
            logger.warning(f"检查仓库状态失败: {stderr}", extra={
                'event_type': EventType.WARNING,
                'repo_path': repo_path,
                'error': stderr
            })
            return False, None
        
        # 检查输出中是否包含"Your branch is behind"或"您的分支落后"
        has_update = ('behind' in stdout.lower() or '落后' in stdout)
        
        if has_update:
            logger.info(f"仓库有更新: {repo_path}", extra={
                'event_type': EventType.INFO,
                'repo_path': repo_path,
                'has_update': True
            })
            return True, stdout
        else:
            logger.debug(f"仓库已是最新: {repo_path}", extra={
                'event_type': EventType.DEBUG,
                'repo_path': repo_path,
                'has_update': False
            })
            return False, None
    except Exception as e:
        logger.error(f"检查仓库更新时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'repo_path': repo_path,
            'error': str(e)
        })
        return False, None

def pull_repo_update(repo_path, use_git_bash=False, git_bash_path=None):
    """拉取仓库更新"""
    try:
        success, stdout, stderr = run_git_command(repo_path, 'git pull', use_git_bash, git_bash_path)
        if success:
            logger.info(f"仓库更新拉取成功: {repo_path}", extra={
                'event_type': EventType.INFO,
                'repo_path': repo_path,
                'output': stdout
            })
            return True, stdout
        else:
            logger.error(f"仓库更新拉取失败: {stderr}", extra={
                'event_type': EventType.ERROR,
                'repo_path': repo_path,
                'error': stderr
            })
            return False, stderr
    except Exception as e:
        logger.error(f"拉取仓库更新时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'repo_path': repo_path,
            'error': str(e)
        })
        return False, str(e)

def get_current_branch(repo_path, use_git_bash=False, git_bash_path=None):
    """获取当前分支"""
    try:
        success, stdout, stderr = run_git_command(repo_path, 'git rev-parse --abbrev-ref HEAD', use_git_bash, git_bash_path)
        if success:
            branch = stdout.strip()
            logger.debug(f"当前分支: {branch}", extra={
                'event_type': EventType.DEBUG,
                'repo_path': repo_path,
                'branch': branch
            })
            return branch
        else:
            logger.warning(f"获取当前分支失败: {stderr}", extra={
                'event_type': EventType.WARNING,
                'repo_path': repo_path,
                'error': stderr
            })
            return None
    except Exception as e:
        logger.error(f"获取当前分支时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'repo_path': repo_path,
            'error': str(e)
        })
        return None

def get_local_commit(repo_path, use_git_bash=False, git_bash_path=None):
    """获取本地提交哈希"""
    try:
        success, stdout, stderr = run_git_command(repo_path, 'git rev-parse HEAD', use_git_bash, git_bash_path)
        if success:
            commit = stdout.strip()
            return commit
        return None
    except Exception as e:
        logger.error(f"获取本地提交哈希时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'repo_path': repo_path,
            'error': str(e)
        })
        return None

def get_remote_commit(repo_path, use_git_bash=False, git_bash_path=None):
    """获取远程提交哈希"""
    try:
        success, stdout, stderr = run_git_command(repo_path, 'git rev-parse @{u}', use_git_bash, git_bash_path)
        if success:
            commit = stdout.strip()
            return commit
        return None
    except Exception as e:
        logger.error(f"获取远程提交哈希时出错: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'repo_path': repo_path,
            'error': str(e)
        })
        return None

def is_git_repo(repo_path):
    """检查路径是否是Git仓库"""
    git_dir = os.path.join(repo_path, '.git')
    return os.path.isdir(git_dir)

def git_update_monitor(config, restart_callback=None):
    """Git更新检测监控线程"""
    global git_update_running
    
    if not config.get('git_update', {}).get('enabled', False):
        logger.info("Git更新检测未启用", extra={'event_type': EventType.INFO, 'enabled': False})
        return
    
    check_interval = config.get('git_update', {}).get('check_interval', 900)
    auto_pull = config.get('git_update', {}).get('auto_pull', False)
    auto_restart = config.get('git_update', {}).get('auto_restart', False)
    
    # 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 检查当前目录是否是Git仓库
    if not is_git_repo(current_dir):
        logger.warning(f"当前目录不是Git仓库，停止更新检测: {current_dir}", extra={
            'event_type': EventType.WARNING,
            'reason': 'not_a_git_repo',
            'directory': current_dir
        })
        return
    
    logger.info(f"开始Git更新检测，监控当前脚本仓库: {current_dir}", extra={
        'event_type': EventType.INFO,
        'repo_path': current_dir,
        'check_interval': check_interval,
        'auto_pull': auto_pull,
        'auto_restart': auto_restart
    })
    
    while git_update_running:
        try:
            logger.info("检查当前脚本仓库更新...", extra={
                'event_type': EventType.INFO,
                'repo_path': current_dir
            })
            
            has_update, status_output = check_repo_update(current_dir, False, None)
            
            if has_update:
                logger.info("当前脚本仓库有更新可用", extra={
                    'event_type': EventType.INFO,
                    'repo_path': current_dir,
                    'has_update': True
                })
                
                if auto_pull:
                    logger.info("开始自动拉取当前脚本更新...", extra={
                        'event_type': EventType.INFO,
                        'repo_path': current_dir,
                        'action': 'auto_pull'
                    })
                    
                    pull_success, pull_output = pull_repo_update(current_dir, False, None)
                    
                    if pull_success:
                        logger.info("当前脚本更新拉取成功", extra={
                            'event_type': EventType.INFO,
                            'repo_path': current_dir,
                            'status': 'pulled'
                        })
                        
                        # 根据配置决定是否自动重启
                        if auto_restart:
                            try:
                                logger.info("开始自动重启监控脚本...", extra={
                                    'event_type': EventType.INFO,
                                    'action': 'auto_restart'
                                })
                                # 等待一小段时间确保文件系统同步
                                time.sleep(2)
                                # 调用重启函数
                                restart_monitor_script()
                                # 停止监控循环，让当前进程退出
                                git_update_running = False
                            except Exception as e:
                                logger.error(f"自动重启监控脚本失败: {str(e)}", extra={
                                    'event_type': EventType.ERROR,
                                    'error': str(e)
                                })
                        else:
                            # 提示用户手动重启
                            logger.info("当前脚本已更新，请手动重启程序以应用最新版本", extra={
                                'event_type': EventType.INFO,
                                'action': 'manual_restart_required'
                            })
                            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 监控脚本已更新，请手动重启程序以应用最新版本")
                        
                        # 如果提供了重启回调，则调用它（兼容旧逻辑）
                        if restart_callback:
                            try:
                                logger.info("触发监控脚本重启...", extra={
                                    'event_type': EventType.INFO,
                                    'action': 'restart'
                                })
                                restart_callback('monitor')
                            except Exception as e:
                                logger.error(f"重启监控脚本失败: {str(e)}", extra={
                                    'event_type': EventType.ERROR,
                                    'error': str(e)
                                })
                    else:
                        logger.error("当前脚本更新拉取失败", extra={
                            'event_type': EventType.ERROR,
                            'repo_path': current_dir,
                            'status': 'pull_failed',
                            'error': pull_output
                        })
                else:
                    logger.info("当前脚本有更新但未启用自动拉取", extra={
                        'event_type': EventType.INFO,
                        'repo_path': current_dir,
                        'auto_pull': False
                    })
            
            # 等待下一次检查
            if git_update_running:
                for _ in range(check_interval):
                    if not git_update_running:
                        break
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Git更新检测线程错误: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'error': str(e)
            })
            if git_update_running:
                time.sleep(60)  # 出错后等待1分钟再重试

def start_git_update_monitor(config, restart_callback=None):
    """启动Git更新检测线程"""
    global git_update_running, git_update_thread
    
    if not config.get('git_update', {}).get('enabled', False):
        logger.info("Git更新检测未启用，不启动监控线程", extra={
            'event_type': EventType.INFO,
            'enabled': False
        })
        return False
    
    if git_update_running:
        logger.warning("Git更新检测线程已在运行", extra={
            'event_type': EventType.WARNING,
            'status': 'already_running'
        })
        return False
    
    git_update_running = True
    git_update_thread = threading.Thread(
        target=git_update_monitor,
        args=(config, restart_callback),
        daemon=True,
        name='GitUpdateMonitor'
    )
    git_update_thread.start()
    
    logger.info("Git更新检测线程已启动", extra={
        'event_type': EventType.INFO,
        'thread_name': 'GitUpdateMonitor'
    })
    return True

def stop_git_update_monitor():
    """停止Git更新检测线程"""
    global git_update_running, git_update_thread
    
    git_update_running = False
    
    if git_update_thread and git_update_thread.is_alive():
        git_update_thread.join(timeout=5)
    
    logger.info("Git更新检测线程已停止", extra={
        'event_type': EventType.INFO,
        'action': 'stopped'
    })

def is_git_update_monitor_running():
    """检查Git更新检测线程是否正在运行"""
    return git_update_running

def restart_monitor_script():
    """重启监控脚本"""
    try:
        import sys
        import os
        
        # 获取当前脚本路径
        script_path = os.path.abspath(sys.argv[0])
        
        logger.info(f"准备重启监控脚本: {script_path}", extra={
            'event_type': EventType.INFO,
            'action': 'restart_script',
            'script_path': script_path
        })
        
        # 使用Python重新启动脚本
        subprocess.Popen(
            [sys.executable, script_path] + sys.argv[1:],
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )
        
        logger.info("监控脚本重启命令已发送", extra={
            'event_type': EventType.INFO,
            'action': 'restart_script_sent'
        })
        
        return True
    except Exception as e:
        logger.error(f"重启监控脚本失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'error': str(e)
        })
        return False

if __name__ == "__main__":
    import time
    
    # 测试代码
    test_config = {
        'git_update': {
            'enabled': True,
            'check_interval': 60,
            'auto_pull': False
        },
        'yunzai': {
            'git_bash_path': ''
        }
    }
    
    print("=" * 60)
    print("Git仓库更新检测工具")
    print("=" * 60)
    
    # 获取当前目录作为测试仓库
    current_dir = os.getcwd()
    print(f"测试仓库: {current_dir}")
    
    if is_git_repo(current_dir):
        print("检测到Git仓库")
        
        # 获取当前分支
        branch = get_current_branch(current_dir)
        print(f"当前分支: {branch}")
        
        # 检查更新
        has_update, status = check_repo_update(current_dir)
        if has_update:
            print(f"仓库有更新: {status}")
        else:
            print("仓库已是最新")
        
        # 获取提交哈希
        local_commit = get_local_commit(current_dir)
        remote_commit = get_remote_commit(current_dir)
        print(f"本地提交: {local_commit}")
        print(f"远程提交: {remote_commit}")
    else:
        print("当前目录不是Git仓库")
    
    print("=" * 60)