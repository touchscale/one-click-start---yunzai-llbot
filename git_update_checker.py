# -*- coding: utf-8 -*-
"""
Git仓库更新检测模块 - 自动检测仓库更新并拉取
"""
import os
import subprocess
import threading
import time
import sys
from datetime import datetime
from logger import get_logger
from constants import EventType

logger = get_logger()

# =====================================================================
# 常量
# =====================================================================

GIT_COMMAND_TIMEOUT = 30
DEFAULT_CHECK_INTERVAL = 900
ERROR_RETRY_DELAY = 60
RESTART_WAIT_SECONDS = 2
PID_FILE_RELATIVE = 'pids/restarting_monitor.pid'

# 防止 Git 在非交互环境下卡死在凭证输入的环境变量
_GIT_NON_INTERACTIVE_ENV = {
    'GIT_TERMINAL_PROMPT': '0',
    'GCM_INTERACTIVE': 'never',
}


# =====================================================================
# 内部工具函数
# =====================================================================

def _build_non_interactive_env():
    """构建禁止凭证提示的执行环境"""
    env = os.environ.copy()
    env.update(_GIT_NON_INTERACTIVE_ENV)
    return env


def _run_git_via_git_bash(repo_path, command, git_bash_path, env):
    """通过 Git Bash 执行 Git 命令"""
    cmd = f'cd "{repo_path}" && {command}'
    return subprocess.run(
        [git_bash_path, '-c', cmd],
        capture_output=True,
        text=True,
        timeout=GIT_COMMAND_TIMEOUT,
        encoding='utf-8',
        errors='replace',
        env=env,
    )


def _run_git_via_shell(repo_path, command, env):
    """通过系统 shell 直接执行 Git 命令"""
    return subprocess.run(
        command,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=GIT_COMMAND_TIMEOUT,
        shell=True,
        encoding='utf-8',
        errors='replace',
        env=env,
    )


def _format_log_extra(**kwargs):
    """统一组装日志 extra 字段"""
    return {'event_type': kwargs.pop('event_type', EventType.INFO), **kwargs}


# =====================================================================
# 公共 Git 操作函数
# =====================================================================

def run_git_command(repo_path, command, use_git_bash=False, git_bash_path=None):
    """执行Git命令（非交互式，禁止凭证提示）"""
    try:
        env = _build_non_interactive_env()

        if use_git_bash and git_bash_path:
            result = _run_git_via_git_bash(repo_path, command, git_bash_path, env)
        else:
            result = _run_git_via_shell(repo_path, command, env)

        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(
            f"Git命令执行超时: {command}",
            extra=_format_log_extra(
                event_type=EventType.ERROR,
                repo_path=repo_path,
                command=command,
                error='timeout',
            ),
        )
        return False, "", "命令执行超时"
    except Exception as e:
        logger.error(
            f"Git命令执行失败: {command}, 错误: {str(e)}",
            extra=_format_log_extra(
                event_type=EventType.ERROR,
                repo_path=repo_path,
                command=command,
                error=str(e),
            ),
        )
        return False, "", str(e)


def check_repo_update(repo_path, use_git_bash=False, git_bash_path=None):
    """检查仓库是否有更新"""
    try:
        # 先获取远程最新信息
        success, _, stderr = run_git_command(repo_path, 'git fetch', use_git_bash, git_bash_path)
        if not success:
            logger.warning(
                f"获取远程更新失败: {stderr}",
                extra=_format_log_extra(
                    event_type=EventType.WARNING,
                    repo_path=repo_path,
                    error=stderr,
                ),
            )
            return False, None

        # 检查本地是否落后远程
        success, stdout, stderr = run_git_command(repo_path, 'git status -uno', use_git_bash, git_bash_path)
        if not success:
            logger.warning(
                f"检查仓库状态失败: {stderr}",
                extra=_format_log_extra(
                    event_type=EventType.WARNING,
                    repo_path=repo_path,
                    error=stderr,
                ),
            )
            return False, None

        # 检查输出中是否包含"Your branch is behind"或"您的分支落后"
        has_update = 'behind' in stdout.lower() or '落后' in stdout

        if has_update:
            logger.info(
                f"仓库有更新: {repo_path}",
                extra=_format_log_extra(
                    event_type=EventType.INFO,
                    repo_path=repo_path,
                    has_update=True,
                ),
            )
            return True, stdout

        logger.debug(
            f"仓库已是最新: {repo_path}",
            extra=_format_log_extra(
                event_type=EventType.DEBUG,
                repo_path=repo_path,
                has_update=False,
            ),
        )
        return False, None
    except Exception as e:
        logger.error(
            f"检查仓库更新时出错: {str(e)}",
            extra=_format_log_extra(
                event_type=EventType.ERROR,
                repo_path=repo_path,
                error=str(e),
            ),
        )
        return False, None


def pull_repo_update(repo_path, use_git_bash=False, git_bash_path=None):
    """拉取仓库更新"""
    try:
        success, stdout, stderr = run_git_command(repo_path, 'git pull', use_git_bash, git_bash_path)
        if success:
            logger.info(
                f"仓库更新拉取成功: {repo_path}",
                extra=_format_log_extra(
                    event_type=EventType.INFO,
                    repo_path=repo_path,
                    output=stdout,
                ),
            )
            return True, stdout

        logger.error(
            f"仓库更新拉取失败: {stderr}",
            extra=_format_log_extra(
                event_type=EventType.ERROR,
                repo_path=repo_path,
                error=stderr,
            ),
        )
        return False, stderr
    except Exception as e:
        logger.error(
            f"拉取仓库更新时出错: {str(e)}",
            extra=_format_log_extra(
                event_type=EventType.ERROR,
                repo_path=repo_path,
                error=str(e),
            ),
        )
        return False, str(e)


def _query_commit_info(repo_path, git_subcommand, log_label,
                       use_git_bash=False, git_bash_path=None):
    """统一封装提交信息查询逻辑"""
    try:
        success, stdout, stderr = run_git_command(
            repo_path, git_subcommand, use_git_bash, git_bash_path
        )
        if success:
            return stdout.strip()
        return None
    except Exception as e:
        logger.error(
            f"{log_label}时出错: {str(e)}",
            extra=_format_log_extra(
                event_type=EventType.ERROR,
                repo_path=repo_path,
                error=str(e),
            ),
        )
        return None


def get_current_branch(repo_path, use_git_bash=False, git_bash_path=None):
    """获取当前分支"""
    branch = _query_commit_info(
        repo_path,
        'git rev-parse --abbrev-ref HEAD',
        '获取当前分支',
        use_git_bash,
        git_bash_path,
    )
    if branch:
        logger.debug(
            f"当前分支: {branch}",
            extra=_format_log_extra(
                event_type=EventType.DEBUG,
                repo_path=repo_path,
                branch=branch,
            ),
        )
    else:
        logger.warning(
            "获取当前分支失败",
            extra=_format_log_extra(
                event_type=EventType.WARNING,
                repo_path=repo_path,
            ),
        )
    return branch


def get_local_commit(repo_path, use_git_bash=False, git_bash_path=None):
    """获取本地提交哈希"""
    return _query_commit_info(
        repo_path, 'git rev-parse HEAD', '获取本地提交哈希',
        use_git_bash, git_bash_path,
    )


def get_remote_commit(repo_path, use_git_bash=False, git_bash_path=None):
    """获取远程提交哈希"""
    return _query_commit_info(
        repo_path, 'git rev-parse @{u}', '获取远程提交哈希',
        use_git_bash, git_bash_path,
    )


def get_latest_commit_message(repo_path, use_git_bash=False, git_bash_path=None):
    """获取最新一条提交信息"""
    return _query_commit_info(
        repo_path, 'git log -1 --oneline', '获取最新提交信息',
        use_git_bash, git_bash_path,
    )


def is_git_repo(repo_path):
    """检查路径是否是Git仓库"""
    git_dir = os.path.join(repo_path, '.git')
    return os.path.isdir(git_dir)


# =====================================================================
# 监控线程：模块级状态 + 轻量包装函数
# =====================================================================

_git_update_running = False
_git_update_thread = None
# 采用 RLock 以允许同一线程内部对状态进行"嵌套式"更新（例如启动流程中
# 多次读写 _git_update_running ），同时对外保持线程安全。
_git_state_lock = threading.RLock()


class _GitUpdateMonitorConfig:
    """监控线程使用的配置快照，避免与外部 dict 反复耦合"""

    __slots__ = ('check_interval', 'auto_pull', 'auto_restart')

    def __init__(self, config):
        git_cfg = config.get('git_update', {}) if config else {}
        self.check_interval = int(git_cfg.get('check_interval', DEFAULT_CHECK_INTERVAL))
        self.auto_pull = bool(git_cfg.get('auto_pull', False))
        self.auto_restart = bool(git_cfg.get('auto_restart', False))


def _is_monitor_enabled(config):
    return bool(config.get('git_update', {}).get('enabled', False)) if config else False


def _sleep_interruptible(total_seconds):
    """可被外部 stop 打断的分段等待"""
    for _ in range(total_seconds):
        if not _git_update_running:
            break
        time.sleep(1)


def _handle_update_found(repo_path, cfg, restart_callback):
    """发现更新后的处理逻辑：可选拉取 + 可选重启"""
    logger.info(
        "当前脚本仓库有更新可用",
        extra=_format_log_extra(
            event_type=EventType.INFO,
            repo_path=repo_path,
            has_update=True,
        ),
    )

    if not cfg.auto_pull:
        logger.info(
            "当前脚本有更新但未启用自动拉取",
            extra=_format_log_extra(
                event_type=EventType.INFO,
                repo_path=repo_path,
                auto_pull=False,
            ),
        )
        return

    logger.info(
        "开始自动拉取当前脚本更新...",
        extra=_format_log_extra(
            event_type=EventType.INFO,
            repo_path=repo_path,
            action='auto_pull',
        ),
    )

    pull_success, pull_output = pull_repo_update(repo_path, False, None)
    if not pull_success:
        logger.error(
            "当前脚本更新拉取失败",
            extra=_format_log_extra(
                event_type=EventType.ERROR,
                repo_path=repo_path,
                status='pull_failed',
                error=pull_output,
            ),
        )
        return

    logger.info(
        "当前脚本更新拉取成功",
        extra=_format_log_extra(
            event_type=EventType.INFO,
            repo_path=repo_path,
            status='pulled',
        ),
    )

    if cfg.auto_restart:
        _try_auto_restart()
    else:
        logger.info(
            "当前脚本已更新，请手动重启程序以应用最新版本",
            extra=_format_log_extra(
                event_type=EventType.INFO,
                action='manual_restart_required',
            ),
        )
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            "监控脚本已更新，请手动重启程序以应用最新版本"
        )

    if restart_callback:
        _try_invoke_restart_callback(restart_callback)


def _try_auto_restart():
    try:
        logger.info(
            "开始自动重启监控脚本...",
            extra=_format_log_extra(event_type=EventType.INFO, action='auto_restart'),
        )
        time.sleep(RESTART_WAIT_SECONDS)
        restart_monitor_script()
        _set_running(False)
    except Exception as e:
        logger.error(
            f"自动重启监控脚本失败: {str(e)}",
            extra=_format_log_extra(event_type=EventType.ERROR, error=str(e)),
        )


def _try_invoke_restart_callback(restart_callback):
    try:
        logger.info(
            "触发监控脚本重启...",
            extra=_format_log_extra(event_type=EventType.INFO, action='restart'),
        )
        restart_callback('monitor')
    except Exception as e:
        logger.error(
            f"重启监控脚本失败: {str(e)}",
            extra=_format_log_extra(event_type=EventType.ERROR, error=str(e)),
        )


def _set_running(value):
    global _git_update_running
    with _git_state_lock:
        _git_update_running = value


def git_update_monitor(config, restart_callback=None):
    """Git更新检测监控线程"""
    if not _is_monitor_enabled(config):
        logger.info(
            "Git更新检测未启用",
            extra=_format_log_extra(event_type=EventType.INFO, enabled=False),
        )
        return

    cfg = _GitUpdateMonitorConfig(config)
    current_dir = os.path.dirname(os.path.abspath(__file__))

    if not is_git_repo(current_dir):
        logger.warning(
            f"当前目录不是Git仓库，停止更新检测: {current_dir}",
            extra=_format_log_extra(
                event_type=EventType.WARNING,
                reason='not_a_git_repo',
                directory=current_dir,
            ),
        )
        return

    logger.info(
        f"开始Git更新检测，监控当前脚本仓库: {current_dir}",
        extra=_format_log_extra(
            event_type=EventType.INFO,
            repo_path=current_dir,
            check_interval=cfg.check_interval,
            auto_pull=cfg.auto_pull,
            auto_restart=cfg.auto_restart,
        ),
    )

    while _git_update_running:
        try:
            logger.info(
                "检查当前脚本仓库更新...",
                extra=_format_log_extra(event_type=EventType.INFO, repo_path=current_dir),
            )

            has_update, _ = check_repo_update(current_dir, False, None)
            if has_update:
                _handle_update_found(current_dir, cfg, restart_callback)

            if _git_update_running:
                _sleep_interruptible(cfg.check_interval)

        except Exception as e:
            logger.error(
                f"Git更新检测线程错误: {str(e)}",
                extra=_format_log_extra(event_type=EventType.ERROR, error=str(e)),
            )
            if _git_update_running:
                time.sleep(ERROR_RETRY_DELAY)


def start_git_update_monitor(config, restart_callback=None):
    """启动Git更新检测线程"""
    global _git_update_thread

    if not _is_monitor_enabled(config):
        logger.info(
            "Git更新检测未启用，不启动监控线程",
            extra=_format_log_extra(event_type=EventType.INFO, enabled=False),
        )
        return False

    with _git_state_lock:
        if _git_update_running:
            logger.warning(
                "Git更新检测线程已在运行",
                extra=_format_log_extra(event_type=EventType.WARNING, status='already_running'),
            )
            return False

        _set_running(True)
        _git_update_thread = threading.Thread(
            target=git_update_monitor,
            args=(config, restart_callback),
            daemon=True,
            name='GitUpdateMonitor',
        )

    _git_update_thread.start()

    logger.info(
        "Git更新检测线程已启动",
        extra=_format_log_extra(event_type=EventType.INFO, thread_name='GitUpdateMonitor'),
    )
    return True


def stop_git_update_monitor():
    """停止Git更新检测线程"""
    global _git_update_thread

    _set_running(False)

    if _git_update_thread and _git_update_thread.is_alive():
        _git_update_thread.join(timeout=5)

    logger.info(
        "Git更新检测线程已停止",
        extra=_format_log_extra(event_type=EventType.INFO, action='stopped'),
    )


def is_git_update_monitor_running():
    """检查Git更新检测线程是否正在运行"""
    return _git_update_running


# =====================================================================
# 重启脚本
# =====================================================================

def _write_restart_pid_file(script_path):
    """将当前 PID 写入临时文件，供新进程检查"""
    pid_dir = os.path.join(os.path.dirname(script_path), 'pids')
    pid_file = os.path.join(pid_dir, PID_FILE_RELATIVE.rsplit('/', 1)[-1])
    os.makedirs(pid_dir, exist_ok=True)
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
    return pid_file


def _launch_new_process(script_path):
    """启动新的监控脚本进程（Windows 不创建新窗口）"""
    startupinfo = subprocess.STARTUPINFO() if os.name == 'nt' else None
    if startupinfo:
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    subprocess.Popen(
        [sys.executable, script_path] + sys.argv[1:],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        startupinfo=startupinfo,
    )


def restart_monitor_script():
    """重启监控脚本（先关闭当前窗口，再开启新的）"""
    try:
        script_path = os.path.abspath(sys.argv[0])
        current_pid = os.getpid()
        temp_pid_file = _write_restart_pid_file(script_path)

        logger.info(
            f"准备重启监控脚本: {script_path}",
            extra=_format_log_extra(
                event_type=EventType.INFO,
                action='restart_script',
                script_path=script_path,
                old_pid=current_pid,
            ),
        )

        _launch_new_process(script_path)

        logger.info(
            "新监控脚本已启动，正在关闭当前进程...",
            extra=_format_log_extra(
                event_type=EventType.INFO,
                action='restart_script_sent',
                new_pid='unknown',
            ),
        )

        stop_git_update_monitor()
        time.sleep(RESTART_WAIT_SECONDS)

        try:
            if os.path.exists(temp_pid_file):
                os.remove(temp_pid_file)
        except OSError:
            pass

        sys.exit(0)
    except Exception as e:
        logger.error(
            f"重启监控脚本失败: {str(e)}",
            extra=_format_log_extra(event_type=EventType.ERROR, error=str(e)),
        )
        return False


# =====================================================================
# 命令行测试入口
# =====================================================================

def _run_cli_test():
    test_config = {
        'git_update': {
            'enabled': True,
            'check_interval': 60,
            'auto_pull': False,
        },
        'yunzai': {
            'git_bash_path': '',
        },
    }

    print("=" * 60)
    print("Git仓库更新检测工具")
    print("=" * 60)

    current_dir = os.getcwd()
    print(f"测试仓库: {current_dir}")

    if is_git_repo(current_dir):
        print("检测到Git仓库")

        branch = get_current_branch(current_dir)
        print(f"当前分支: {branch}")

        has_update, status = check_repo_update(current_dir)
        if has_update:
            print(f"仓库有更新: {status}")
        else:
            print("仓库已是最新")

        local_commit = get_local_commit(current_dir)
        remote_commit = get_remote_commit(current_dir)
        print(f"本地提交: {local_commit}")
        print(f"远程提交: {remote_commit}")
    else:
        print("当前目录不是Git仓库")

    print("=" * 60)


if __name__ == "__main__":
    _run_cli_test()
