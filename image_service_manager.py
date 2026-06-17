# -*- coding: utf-8 -*-
"""
图片生成服务管理模块
负责启动、停止和管理图片生成服务
"""
import os
import sys
import time
import psutil
import subprocess
import threading
import shutil
from typing import Optional, Dict, Any
from logger import get_logger, get_image_service_logger
from constants import EventType

logger = get_logger()
image_logger = get_image_service_logger()

# Windows 进程组标志
if sys.platform == 'win32':
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    DETACHED_PROCESS = 0x00000008
else:
    CREATE_NEW_PROCESS_GROUP = 0
    DETACHED_PROCESS = 0


class ImageServiceManager:
    """图片服务管理器"""

    def __init__(self):
        """初始化图片服务管理器"""
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image_generator_dir = os.path.join(self.script_dir, "image_generator")
        self.node_script = os.path.join(self.image_generator_dir, "image-service.js")
        self.pid_file = os.path.join(self.script_dir, "pids", "image_service.pid")
        self.process: Optional[subprocess.Popen] = None
        self.service_url = "http://localhost:3001"
        self._running = False
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = False

    # ==================== 工具方法 ====================

    @staticmethod
    def _force_delete_file(file_path: str, max_retries: int = 5, retry_delay: float = 0.3) -> bool:
        """强制删除文件，使用多种策略"""
        if not os.path.exists(file_path):
            return True

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(retry_delay)
                os.remove(file_path)
                return True
            except Exception:
                try:
                    temp_name = file_path + f'.delete_{int(time.time() * 1000)}_{os.getpid()}'
                    if os.path.exists(file_path):
                        os.rename(file_path, temp_name)
                        if os.path.exists(temp_name):
                            os.remove(temp_name)
                    return True
                except Exception:
                    pass

                if os.name == 'nt':
                    try:
                        subprocess.run(
                            ['cmd', '/c', 'del', '/f', '/q', file_path],
                            capture_output=True,
                            timeout=3
                        )
                        if not os.path.exists(file_path):
                            return True
                    except Exception:
                        pass

                if attempt == max_retries - 1:
                    raise
        return False

    def _read_pid_from_file(self) -> Optional[int]:
        """读取 PID 文件（不在锁内调用）"""
        if not os.path.exists(self.pid_file):
            return None
        try:
            with open(self.pid_file, 'r', encoding='utf-8') as f:
                pid_str = f.read().strip()
            if pid_str and pid_str.isdigit():
                return int(pid_str)
        except Exception:
            pass
        return None

    def _cleanup_stale_pid_file(self) -> None:
        """清理僵尸 PID 文件"""
        if not os.path.exists(self.pid_file):
            return
        try:
            with open(self.pid_file, 'r', encoding='utf-8') as f:
                pid_str = f.read().strip()
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if not psutil.pid_exists(pid):
                    image_logger.warning(f"检测到僵尸 PID 文件，进程 {pid} 不存在，正在清理", extra={
                        'event_type': EventType.WARNING,
                        'feature': 'image_service',
                        'stale_pid': pid
                    })
                    self._force_delete_file(self.pid_file, max_retries=5, retry_delay=0.2)
                    return
        except Exception as e:
            image_logger.warning(f"读取 PID 文件失败: {str(e)}", extra={
                'event_type': EventType.WARNING,
                'feature': 'image_service',
                'error': str(e)
            })

    def _write_pid_file(self, pid: int) -> None:
        """原子性写入 PID 文件"""
        pids_dir = os.path.dirname(self.pid_file)
        if pids_dir and not os.path.exists(pids_dir):
            os.makedirs(pids_dir, exist_ok=True)

        temp_pid_file = self.pid_file + '.tmp'
        try:
            with open(temp_pid_file, 'w', encoding='utf-8') as f:
                f.write(str(pid))
            if os.name == 'nt' and os.path.exists(self.pid_file):
                os.replace(temp_pid_file, self.pid_file)
            else:
                os.rename(temp_pid_file, self.pid_file)
        except Exception as e:
            image_logger.warning(f"写入 PID 文件失败: {str(e)}，尝试直接写入", extra={
                'event_type': EventType.WARNING,
                'feature': 'image_service'
            })
            try:
                with open(self.pid_file, 'w', encoding='utf-8') as f:
                    f.write(str(pid))
            except Exception:
                pass

    def _delete_pid_file(self) -> None:
        """删除 PID 文件"""
        if os.path.exists(self.pid_file):
            if self._force_delete_file(self.pid_file, max_retries=5, retry_delay=0.2):
                image_logger.info("已删除 PID 文件", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })
            else:
                image_logger.warning("未能删除 PID 文件，可能被其他进程锁定", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'image_service'
                })

    # ==================== 进程监控 ====================

    def _process_monitor(self) -> None:
        """后台线程：监控进程状态，当进程异常退出时更新状态"""
        while not self._stop_monitor:
            time.sleep(3)
            if self._stop_monitor:
                break

            with self._lock:
                if self.process is None:
                    continue

                exit_code = self.process.poll()
                if exit_code is not None:
                    # 进程已退出
                    image_logger.warning(f"检测到图片服务进程异常退出 (退出码: {exit_code})，正在清理状态", extra={
                        'event_type': EventType.WARNING,
                        'feature': 'image_service',
                        'exit_code': exit_code
                    })
                    self.process = None
                    self._running = False
                    self._delete_pid_file()

    def _ensure_monitor_running(self) -> None:
        """确保监控线程在运行"""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_monitor = False
            self._monitor_thread = threading.Thread(target=self._process_monitor, daemon=True)
            self._monitor_thread.start()
            image_logger.info("进程监控线程已启动", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })

    def _stop_monitor_thread(self) -> None:
        """停止监控线程"""
        self._stop_monitor = True

    # ==================== 环境检查 ====================

    def check_node_installed(self) -> bool:
        """检查 Node.js 是否已安装"""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                image_logger.info(f"Node.js 版本: {result.stdout.strip()}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service',
                    'node_version': result.stdout.strip()
                })
                return True
            return False
        except Exception as e:
            image_logger.warning(f"检查 Node.js 失败: {str(e)}", extra={
                'event_type': EventType.WARNING,
                'feature': 'image_service',
                'error': str(e)
            })
            return False

    def check_dependencies_installed(self) -> bool:
        """检查 node_modules 是否已安装"""
        node_modules = os.path.join(self.image_generator_dir, "node_modules")
        if os.path.exists(node_modules):
            return True
        image_logger.warning("Node.js 依赖未安装", extra={
            'event_type': EventType.WARNING,
            'feature': 'image_service'
        })
        return False

    def install_dependencies(self) -> bool:
        """安装 Node.js 依赖"""
        image_logger.info("开始安装 Node.js 依赖...", extra={
            'event_type': EventType.INFO,
            'feature': 'image_service'
        })

        try:
            process = subprocess.Popen(
                ["npm", "install"],
                cwd=self.image_generator_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                stdout, stderr = process.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                process.kill()
                image_logger.error("安装 Node.js 依赖超时（5分钟）", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service',
                    'error': 'timeout'
                })
                return False

            if stdout:
                for line in stdout.split('\n'):
                    line = line.strip()
                    if line:
                        image_logger.info(f"npm: {line}", extra={
                            'event_type': EventType.INFO,
                            'feature': 'image_service'
                        })

            if stderr:
                image_logger.warning(f"npm 警告: {stderr}", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'image_service'
                })

            if process.returncode == 0:
                image_logger.info("Node.js 依赖安装成功", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })
                return True
            else:
                image_logger.error(f"Node.js 依赖安装失败，退出码: {process.returncode}", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service',
                    'error': f'exit code: {process.returncode}'
                })
                return False
        except Exception as e:
            image_logger.error(f"安装 Node.js 依赖时出错: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service',
                'error': str(e)
            })
            return False

    # ==================== 核心接口 ====================

    def is_running(self) -> bool:
        """检查服务是否在运行"""
        with self._lock:
            if self.process is not None:
                try:
                    if self.process.poll() is None:
                        return True
                except Exception:
                    self.process = None

            # 通过 PID 文件检查（不触发锁内 sleep）
            pid = self._read_pid_from_file()
            if pid is not None and psutil.pid_exists(pid):
                # 同步内部状态
                self._running = True
                return True

            # 僵尸 PID，清理
            if pid is not None:
                self._cleanup_stale_pid_file()
            self._running = False
            return False

    def get_pid(self) -> Optional[int]:
        """获取服务进程 ID"""
        with self._lock:
            if self.process is not None:
                try:
                    if self.process.poll() is None:
                        return self.process.pid
                except Exception:
                    self.process = None

        # 锁外读取 PID 文件
        return self._read_pid_from_file()

    def start(self, wait_ready: bool = True, timeout: int = 60) -> bool:
        """
        启动图片服务

        Args:
            wait_ready: 是否等待服务就绪
            timeout: 等待就绪的超时时间（秒）

        Returns:
            是否启动成功
        """
        # 确保监控线程运行
        self._ensure_monitor_running()

        # 先检查 Node.js（不持锁）
        if not self.check_node_installed():
            image_logger.error("Node.js 未安装，无法启动图片服务", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service'
            })
            return False

        if not os.path.exists(self.node_script):
            image_logger.error(f"图片服务脚本不存在: {self.node_script}", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service'
            })
            return False

        if not self.check_dependencies_installed():
            image_logger.info("开始安装 Node.js 依赖...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })
            if not self.install_dependencies():
                image_logger.error("无法安装 Node.js 依赖", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service'
                })
                return False

        # 持锁检查状态和启动服务
        start_result = None  # 'already_running' | 'started' | 'failed'
        with self._lock:
            if self._running:
                # 双重确认：检查进程是否真正在运行
                if self.process and self.process.poll() is None:
                    image_logger.info("图片服务已在运行中", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service'
                    })
                    start_result = 'already_running'
                else:
                    self._running = False
                    self.process = None

            if start_result is None:
                pid = self._read_pid_from_file()
                if pid is not None and psutil.pid_exists(pid):
                    image_logger.info("检测到图片服务已在运行（通过 PID 文件），跳过启动", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service',
                        'pid': pid
                    })
                    self._running = True
                    start_result = 'already_running'
                else:
                    # 清理僵尸 PID
                    self._cleanup_stale_pid_file()

            if start_result is None:
                # 启动服务
                try:
                    image_logger.info("正在启动图片生成服务...", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service'
                    })

                    # 构建进程启动参数
                    # 关键：使用 start_new_session (Unix) 或 CREATE_NEW_PROCESS_GROUP (Windows)
                    # 使子进程独立于父进程组，避免父进程信号影响子进程
                    popen_kwargs: Dict[str, Any] = {
                        'cwd': self.image_generator_dir,
                    }

                    if sys.platform == 'win32':
                        popen_kwargs['creationflags'] = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
                        popen_kwargs['stdin'] = subprocess.DEVNULL
                        popen_kwargs['stdout'] = subprocess.DEVNULL
                        popen_kwargs['stderr'] = subprocess.DEVNULL
                    else:
                        # Unix: 使用 start_new_session 创建新的会话和进程组
                        popen_kwargs['start_new_session'] = True

                    self.process = subprocess.Popen(
                        ["node", self.node_script],
                        **popen_kwargs
                    )

                    self._write_pid_file(self.process.pid)
                    self._running = True

                    image_logger.info(f"图片生成服务进程已启动 (PID: {self.process.pid})", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service',
                        'pid': self.process.pid
                    })
                    start_result = 'started'

                except Exception as e:
                    image_logger.error(f"启动图片服务失败: {str(e)}", extra={
                        'event_type': EventType.ERROR,
                        'feature': 'image_service',
                        'error': str(e)
                    })
                    self._running = False
                    self.process = None
                    self._delete_pid_file()
                    start_result = 'failed'

        # 锁外处理结果
        if start_result == 'failed':
            return False

        if start_result == 'already_running':
            return True

        # 等待服务就绪
        if wait_ready:
            image_logger.info(f"等待图片服务就绪（最长等待 {timeout} 秒）...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service',
                'timeout': timeout
            })
            if not self.wait_for_ready(timeout):
                image_logger.error("图片服务启动超时，正在回滚停止...", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service'
                })
                try:
                    self.stop()
                except Exception:
                    pass
                return False
            image_logger.info("图片服务已就绪", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })

        return True

    def stop(self) -> bool:
        """停止图片服务"""
        self._stop_monitor_thread()

        with self._lock:
            image_logger.info("开始停止图片服务...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })

            stopped_pids = []

            # 直接读取 PID（不在锁内调用 get_pid()，避免重入锁问题）
            pid = self._read_pid_from_file()
            if pid and psutil.pid_exists(pid):
                try:
                    process = psutil.Process(pid)
                    image_logger.info(f"找到 PID 文件中的进程 {pid}，正在终止...", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service',
                        'pid': pid
                    })

                    process.terminate()
                    try:
                        process.wait(timeout=5)
                        stopped_pids.append(pid)
                        image_logger.info(f"已优雅终止进程 {pid}", extra={
                            'event_type': EventType.INFO,
                            'feature': 'image_service',
                            'pid': pid
                        })
                    except psutil.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                        stopped_pids.append(pid)
                        image_logger.info(f"已强制终止进程 {pid}", extra={
                            'event_type': EventType.INFO,
                            'feature': 'image_service',
                            'pid': pid
                        })
                except psutil.NoSuchProcess:
                    image_logger.info(f"进程 {pid} 已不存在", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service',
                        'pid': pid
                    })
                except Exception as e:
                    image_logger.error(f"通过 PID 停止图片服务失败: {str(e)}", extra={
                        'event_type': EventType.ERROR,
                        'feature': 'image_service',
                        'pid': pid,
                        'error': str(e)
                    })

            # 扫描所有 image-service.js 相关进程
            image_logger.info("扫描所有 image-service.js 相关进程...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })

            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and 'image-service.js' in ' '.join(cmdline):
                        proc_pid = proc.info['pid']
                        if proc_pid not in stopped_pids:
                            image_logger.info(f"发现相关进程 {proc_pid}，正在终止...", extra={
                                'event_type': EventType.INFO,
                                'feature': 'image_service',
                                'pid': proc_pid,
                                'cmdline': ' '.join(cmdline)[:100]
                            })
                            proc.terminate()
                            try:
                                proc.wait(timeout=3)
                                stopped_pids.append(proc_pid)
                            except psutil.TimeoutExpired:
                                proc.kill()
                                proc.wait(timeout=2)
                                stopped_pids.append(proc_pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                except Exception as e:
                    image_logger.warning(f"处理进程时出错: {e}", extra={
                        'event_type': EventType.WARNING,
                        'feature': 'image_service',
                        'error': str(e)
                    })

            # 清理内部进程引用
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    pass
                self.process = None

            self._running = False
            self._delete_pid_file()

            total_stopped = len(stopped_pids)
            if total_stopped > 0:
                image_logger.info(f"图片服务停止成功，共终止 {total_stopped} 个进程", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service',
                    'stopped_pids': stopped_pids
                })
            else:
                image_logger.info("未发现运行中的图片服务进程", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })

            return True

    def wait_for_ready(self, timeout: int = 30) -> bool:
        """等待服务就绪"""
        import requests

        start_time = time.time()
        health_url = f"{self.service_url}/health"

        while time.time() - start_time < timeout:
            # 同时检查进程是否还活着
            with self._lock:
                if self.process is not None and self.process.poll() is not None:
                    image_logger.error(f"图片服务进程在等待就绪期间异常退出 (退出码: {self.process.poll()})", extra={
                        'event_type': EventType.ERROR,
                        'feature': 'image_service'
                    })
                    return False

            try:
                response = requests.get(health_url, timeout=2)
                if response.status_code == 200:
                    image_logger.info("图片服务已就绪", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service'
                    })
                    return True
            except Exception:
                pass

            time.sleep(1)

        return False

    def health_check(self) -> Dict[str, Any]:
        """检查服务健康状态"""
        import requests

        try:
            response = requests.get(f"{self.service_url}/health", timeout=5)
            if response.status_code == 200:
                return {
                    'ready': True,
                    'message': '图片服务运行正常',
                    'data': response.json()
                }
            else:
                return {
                    'ready': False,
                    'message': f'图片服务返回异常状态码: {response.status_code}'
                }
        except Exception as e:
            return {
                'ready': False,
                'message': f'无法连接到图片服务: {str(e)}'
            }


# 全局管理器实例
_global_manager: Optional[ImageServiceManager] = None


def get_image_service_manager() -> ImageServiceManager:
    """获取图片服务管理器实例（单例模式）"""
    global _global_manager
    if _global_manager is None:
        _global_manager = ImageServiceManager()
    return _global_manager
