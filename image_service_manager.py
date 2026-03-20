# -*- coding: utf-8 -*-
"""
图片生成服务管理模块
负责启动、停止和管理图片生成服务
"""
import os
import time
import psutil
import subprocess
import threading
import tempfile
import shutil
from typing import Optional, Dict, Any
from logger import get_logger, get_image_service_logger
from constants import EventType

logger = get_logger()
image_logger = get_image_service_logger()


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

    @staticmethod
    def _force_delete_file(file_path: str, max_retries: int = 5, retry_delay: float = 0.3) -> bool:
        """
        强制删除文件，使用多种策略

        Args:
            file_path: 要删除的文件路径
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）

        Returns:
            是否删除成功
        """
        if not os.path.exists(file_path):
            return True

        for attempt in range(max_retries):
            try:
                # 策略1: 先短暂等待
                if attempt > 0:
                    time.sleep(retry_delay)

                # 策略2: 尝试标准删除
                os.remove(file_path)
                return True

            except Exception as e:
                # 如果失败，尝试其他策略
                try:
                    # 策略3: 重命名到临时文件（绕过文件锁定）
                    temp_name = file_path + f'.delete_{int(time.time() * 1000)}_{os.getpid()}'
                    if os.path.exists(file_path):
                        os.rename(file_path, temp_name)
                        # 重命名成功后，删除临时文件
                        if os.path.exists(temp_name):
                            os.remove(temp_name)
                    return True

                except Exception as e2:
                    # 策略4: 使用shutil.rmtree（对文件无效，但值得尝试）
                    try:
                        shutil.rmtree(file_path, ignore_errors=True)
                        return True
                    except:
                        pass

                    # 策略5: 使用Windows命令行强制删除
                    if os.name == 'nt':
                        try:
                            subprocess.run(
                                ['cmd', '/c', 'del', '/f', '/q', file_path],
                                capture_output=True,
                                timeout=3
                            )
                            if not os.path.exists(file_path):
                                return True
                        except:
                            pass

                    # 最后一次尝试
                    if attempt == max_retries - 1:
                        raise

        return False
        """初始化图片服务管理器"""
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.image_generator_dir = os.path.join(self.script_dir, "image_generator")
        self.node_script = os.path.join(self.image_generator_dir, "image-service.js")
        self.pid_file = os.path.join(self.script_dir, "pids", "image_service.pid")
        self.process: Optional[subprocess.Popen] = None
        self.service_url = "http://localhost:3001"
        self._running = False
        self._lock = threading.RLock()
    
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
            # 使用非阻塞方式，避免死锁
            process = subprocess.Popen(
                ["npm", "install"],
                cwd=self.image_generator_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 等待进程完成，设置超时
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

            # 输出安装结果
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
    
    def _is_running_unlocked(self) -> bool:
        """检查服务是否在运行（不加锁的内部方法）"""
        if self.process is not None:
            # 检查进程是否还存在
            try:
                return self.process.poll() is None
            except:
                self.process = None

        # 从 PID 文件读取
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r', encoding='utf-8') as f:
                    pid_str = f.read().strip()
                    if pid_str and pid_str.isdigit():
                        pid = int(pid_str)
                        if psutil.pid_exists(pid):
                            return True
                        else:
                            # PID文件中的进程不存在，立即清理僵尸PID文件
                            image_logger.warning(f"检测到僵尸PID文件，进程 {pid} 不存在，正在清理", extra={
                                'event_type': EventType.WARNING,
                                'feature': 'image_service',
                                'stale_pid': pid
                            })
                            # 使用强制删除
                            if self._force_delete_file(self.pid_file, max_retries=5, retry_delay=0.2):
                                image_logger.info(f"已清理僵尸PID文件", extra={
                                    'event_type': EventType.INFO,
                                    'feature': 'image_service',
                                    'stale_pid': pid
                                })
                            else:
                                image_logger.warning(f"清理僵尸PID文件失败，但将继续运行", extra={
                                    'event_type': EventType.WARNING,
                                    'feature': 'image_service',
                                    'stale_pid': pid
                                })
                            return False
            except Exception as e:
                image_logger.warning(f"读取 PID 文件失败: {str(e)}", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'image_service',
                    'error': str(e)
                })

        return False
    
    def is_running(self) -> bool:
        """检查服务是否在运行"""
        with self._lock:
            return self._is_running_unlocked()
    
    def get_pid(self) -> Optional[int]:
        """获取服务进程 ID"""
        with self._lock:
            if self.process is not None:
                try:
                    if self.process.poll() is None:
                        return self.process.pid
                except:
                    pass

            # 从PID文件读取（添加小延迟，避免文件锁竞争）
            if os.path.exists(self.pid_file):
                try:
                    with open(self.pid_file, 'r', encoding='utf-8') as f:
                        pid_str = f.read().strip()
                    # with语句会自动关闭文件，但添加小延迟确保文件锁释放
                    time.sleep(0.05)
                    if pid_str and pid_str.isdigit():
                        return int(pid_str)
                except:
                    pass

            return None
    
    def start(self, wait_ready: bool = True, timeout: int = 60) -> bool:
        """
        启动图片服务

        Args:
            wait_ready: 是否等待服务就绪
            timeout: 等待就绪的超时时间（秒）

        Returns:
            是否启动成功
        """
        # 先检查 Node.js（不持锁）
        image_logger.info("检查 Node.js 环境...", extra={
            'event_type': EventType.INFO,
            'feature': 'image_service'
        })
        if not self.check_node_installed():
            image_logger.error("Node.js 未安装，无法启动图片服务", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service'
            })
            return False

        # 检查服务脚本（不持锁）
        if not os.path.exists(self.node_script):
            image_logger.error(f"图片服务脚本不存在: {self.node_script}", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service'
            })
            return False

        # 检查依赖（不持锁）
        image_logger.info("检查 Node.js 依赖...", extra={
            'event_type': EventType.INFO,
            'feature': 'image_service'
        })
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
        with self._lock:
            if self._running:
                image_logger.warning("图片服务已在运行中", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'image_service'
                })
                return True

            # 检查是否已有实例在运行（使用不加锁的版本）
            if self._is_running_unlocked():
                image_logger.info("检测到图片服务已在运行，跳过启动", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })
                self._running = True
                return True

            # 创建 pids 目录
            pids_dir = os.path.dirname(self.pid_file)
            if not os.path.exists(pids_dir):
                os.makedirs(pids_dir, exist_ok=True)

            # 清理可能存在的旧 PID 文件
            if os.path.exists(self.pid_file):
                try:
                    # 先尝试读取旧 PID，确认进程是否存在
                    with open(self.pid_file, 'r', encoding='utf-8') as f:
                        old_pid_str = f.read().strip()
                        if old_pid_str and old_pid_str.isdigit():
                            old_pid = int(old_pid_str)
                            if not psutil.pid_exists(old_pid):
                                # 旧进程不存在，使用强制删除
                                if self._force_delete_file(self.pid_file, max_retries=5, retry_delay=0.2):
                                    image_logger.info(f"清理旧的 PID 文件 (进程 {old_pid} 不存在)", extra={
                                        'event_type': EventType.INFO,
                                        'feature': 'image_service'
                                    })
                                else:
                                    # 如果删除失败，记录警告但继续启动（可能需要管理员权限或文件被锁定）
                                    image_logger.warning(f"无法删除旧的PID文件，但将尝试覆盖启动新进程", extra={
                                        'event_type': EventType.WARNING,
                                        'feature': 'image_service'
                                    })
                            else:
                                # 旧进程还存在，尝试优雅终止
                                try:
                                    old_proc = psutil.Process(old_pid)
                                    old_proc.terminate()
                                    try:
                                        old_proc.wait(timeout=3)
                                    except psutil.TimeoutExpired:
                                        old_proc.kill()
                                        old_proc.wait(timeout=2)
                                    image_logger.info(f"终止旧的图片服务进程 {old_pid}", extra={
                                        'event_type': EventType.INFO,
                                        'feature': 'image_service'
                                    })
                                    # 终止后删除PID文件
                                    self._force_delete_file(self.pid_file, max_retries=5, retry_delay=0.2)
                                except:
                                    # 无法终止旧进程，记录警告但继续
                                    image_logger.warning(f"无法终止旧进程 {old_pid}，尝试继续", extra={
                                        'event_type': EventType.WARNING,
                                        'feature': 'image_service'
                                    })
                except Exception as e:
                    # 如果清理失败，记录警告但继续
                    image_logger.warning(f"清理 PID 文件失败: {str(e)}，将尝试覆盖启动", extra={
                        'event_type': EventType.WARNING,
                        'feature': 'image_service',
                        'error': str(e)
                    })

            # 启动服务
            try:
                image_logger.info("正在启动图片生成服务...", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })

                # 不使用 CREATE_NO_WINDOW，允许日志输出到控制台
                self.process = subprocess.Popen(
                    ["node", self.node_script],
                    cwd=self.image_generator_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    universal_newlines=True
                )

                # 启动线程实时读取 stdout
                def read_stdout():
                    for line in iter(self.process.stdout.readline, ''):
                        if line:
                            line = line.rstrip()
                            # 解析日志级别
                            if '[ERROR]' in line:
                                image_logger.error(line, extra={
                                    'event_type': EventType.ERROR,
                                    'feature': 'image_service'
                                })
                            elif '[WARN]' in line:
                                image_logger.warning(line, extra={
                                    'event_type': EventType.WARNING,
                                    'feature': 'image_service'
                                })
                            else:
                                image_logger.info(line, extra={
                                    'event_type': EventType.INFO,
                                    'feature': 'image_service'
                                })
                    self.process.stdout.close()

                # 启动线程实时读取 stderr
                def read_stderr():
                    for line in iter(self.process.stderr.readline, ''):
                        if line:
                            line = line.rstrip()
                            image_logger.error(line, extra={
                                'event_type': EventType.ERROR,
                                'feature': 'image_service'
                            })
                    self.process.stderr.close()

                stdout_thread = threading.Thread(target=read_stdout, daemon=True)
                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stdout_thread.start()
                stderr_thread.start()

                # 保存 PID（使用更可靠的方法）
                temp_pid_file = self.pid_file + '.tmp'
                try:
                    with open(temp_pid_file, 'w', encoding='utf-8') as f:
                        f.write(str(self.process.pid))
                    # 原子性重命名
                    if os.name == 'nt':
                        # Windows 下可能无法直接重命名目标文件已存在的情况
                        if os.path.exists(self.pid_file):
                            os.replace(temp_pid_file, self.pid_file)
                        else:
                            os.rename(temp_pid_file, self.pid_file)
                    else:
                        os.rename(temp_pid_file, self.pid_file)
                except Exception as e:
                    # 如果重命名失败，至少确保临时文件存在
                    image_logger.warning(f"使用原子性重命名失败: {str(e)}，直接写入", extra={
                        'event_type': EventType.WARNING,
                        'feature': 'image_service'
                    })
                    with open(self.pid_file, 'w', encoding='utf-8') as f:
                        f.write(str(self.process.pid))

                self._running = True

                image_logger.info(f"图片生成服务进程已启动 (PID: {self.process.pid})", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service',
                    'pid': self.process.pid
                })

                return True

            except Exception as e:
                image_logger.error(f"启动图片服务失败: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service',
                    'error': str(e)
                })
                self._running = False
                return False

        # 等待服务就绪（在锁外部）
        if wait_ready:
            image_logger.info(f"等待图片服务就绪（最长等待 {timeout} 秒）...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service',
                'timeout': timeout
            })
            if not self.wait_for_ready(timeout):
                image_logger.error("图片服务启动超时", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service'
                })
                self.stop()
                return False

        return True
    
    def stop(self) -> bool:
        """停止图片服务"""
        with self._lock:
            image_logger.info("开始停止图片服务...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })

            success = True
            stopped_pids = []

            # 方法1: 通过 PID 文件停止
            pid = self.get_pid()
            if pid:
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
                        image_logger.warning(f"进程 {pid} 优雅终止超时，强制终止...", extra={
                            'event_type': EventType.WARNING,
                            'feature': 'image_service',
                            'pid': pid
                        })
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
                    success = False

            # 方法2: 通过进程名查找所有相关进程
            image_logger.info("扫描所有 image-service.js 相关进程...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })

            additional_stopped = []
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
                                additional_stopped.append(proc_pid)
                                image_logger.info(f"已终止额外进程 {proc_pid}", extra={
                                    'event_type': EventType.INFO,
                                    'feature': 'image_service',
                                    'pid': proc_pid
                                })
                            except psutil.TimeoutExpired:
                                proc.kill()
                                proc.wait(timeout=2)
                                additional_stopped.append(proc_pid)
                                image_logger.info(f"已强制终止额外进程 {proc_pid}", extra={
                                    'event_type': EventType.INFO,
                                    'feature': 'image_service',
                                    'pid': proc_pid
                                })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                    image_logger.debug(f"跳过进程: {e}", extra={
                        'event_type': EventType.DEBUG,
                        'feature': 'image_service'
                    })
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
                    image_logger.info("已清理内部进程引用", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service'
                    })
                except:
                    pass
                self.process = None

            # 删除 PID 文件
            if os.path.exists(self.pid_file):
                if self._force_delete_file(self.pid_file, max_retries=5, retry_delay=0.2):
                    image_logger.info("已删除 PID 文件", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service'
                    })
                else:
                    image_logger.warning("未能删除PID文件，可能被其他进程锁定", extra={
                        'event_type': EventType.WARNING,
                        'feature': 'image_service'
                    })

            # 总结
            total_stopped = len(stopped_pids) + len(additional_stopped)
            self._running = False

            if total_stopped > 0:
                image_logger.info(f"图片服务停止成功，共终止 {total_stopped} 个进程", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service',
                    'stopped_pids': stopped_pids + additional_stopped
                })
            else:
                image_logger.info("未发现运行中的图片服务进程", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })

            return success    
    def wait_for_ready(self, timeout: int = 30) -> bool:
        """
        等待服务就绪

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否就绪
        """
        import requests

        start_time = time.time()
        health_url = f"{self.service_url}/health"

        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url, timeout=2)
                if response.status_code == 200:
                    image_logger.info("图片服务已就绪", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service'
                    })
                    return True
            except:
                pass

            time.sleep(1)

        return False

    def health_check(self) -> Dict[str, Any]:
        """
        检查服务健康状态

        Returns:
            健康状态字典
        """
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