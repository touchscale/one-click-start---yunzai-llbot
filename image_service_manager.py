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
from typing import Optional, Dict, Any
from logger import get_logger
from constants import EventType

logger = get_logger()


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
                logger.info(f"Node.js 版本: {result.stdout.strip()}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service',
                    'node_version': result.stdout.strip()
                })
                return True
            return False
        except Exception as e:
            logger.warning(f"检查 Node.js 失败: {str(e)}", extra={
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
        
        logger.warning("Node.js 依赖未安装", extra={
            'event_type': EventType.WARNING,
            'feature': 'image_service'
        })
        return False
    
    def install_dependencies(self) -> bool:
        """安装 Node.js 依赖"""
        logger.info("开始安装 Node.js 依赖...", extra={
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
                logger.error("安装 Node.js 依赖超时（5分钟）", extra={
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
                        logger.info(f"npm: {line}", extra={
                            'event_type': EventType.INFO,
                            'feature': 'image_service'
                        })
            
            if stderr:
                logger.warning(f"npm 警告: {stderr}", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'image_service'
                })
            
            if process.returncode == 0:
                logger.info("Node.js 依赖安装成功", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })
                return True
            else:
                logger.error(f"Node.js 依赖安装失败，退出码: {process.returncode}", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service',
                    'error': f'exit code: {process.returncode}'
                })
                return False
        except Exception as e:
            logger.error(f"安装 Node.js 依赖时出错: {str(e)}", extra={
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
                            # PID文件中的进程不存在，清理僵尸PID文件
                            logger.warning(f"检测到僵尸PID文件，进程 {pid} 不存在，正在清理...", extra={
                                'event_type': EventType.WARNING,
                                'feature': 'image_service',
                                'stale_pid': pid
                            })
                            try:
                                os.remove(self.pid_file)
                                logger.info("僵尸PID文件已清理", extra={
                                    'event_type': EventType.INFO,
                                    'feature': 'image_service'
                                })
                            except Exception as e:
                                logger.warning(f"常规删除PID文件失败，尝试使用PowerShell强制删除: {str(e)}", extra={
                                    'event_type': EventType.WARNING,
                                    'feature': 'image_service',
                                    'error': str(e)
                                })
                                try:
                                    import subprocess
                                    # 使用单引号包裹路径，避免PowerShell中的转义问题
                                    cmd = f'Remove-Item -Path \'{self.pid_file}\' -Force'
                                    subprocess.run(['powershell', '-Command', cmd],
                                                 check=True, capture_output=True, timeout=10, text=True)
                                    logger.info("使用PowerShell强制删除PID文件成功", extra={
                                        'event_type': EventType.INFO,
                                        'feature': 'image_service'
                                    })
                                except subprocess.CalledProcessError as force_e:
                                    logger.error(f"强制删除PID文件失败: {force_e.stderr if force_e.stderr else str(force_e)}", extra={
                                        'event_type': EventType.ERROR,
                                        'feature': 'image_service',
                                        'error': str(force_e)
                                    })
                                except Exception as force_e:
                                    logger.error(f"强制删除PID文件失败: {str(force_e)}", extra={
                                        'event_type': EventType.ERROR,
                                        'feature': 'image_service',
                                        'error': str(force_e)
                                    })
            except Exception as e:
                logger.warning(f"读取 PID 文件失败: {str(e)}", extra={
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
            
            if os.path.exists(self.pid_file):
                try:
                    with open(self.pid_file, 'r', encoding='utf-8') as f:
                        pid_str = f.read().strip()
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
        logger.info("检查 Node.js 环境...", extra={
            'event_type': EventType.INFO,
            'feature': 'image_service'
        })
        if not self.check_node_installed():
            logger.error("Node.js 未安装，无法启动图片服务", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service'
            })
            return False
        
        # 检查服务脚本（不持锁）
        if not os.path.exists(self.node_script):
            logger.error(f"图片服务脚本不存在: {self.node_script}", extra={
                'event_type': EventType.ERROR,
                'feature': 'image_service'
            })
            return False
        
        # 检查依赖（不持锁）
        logger.info("检查 Node.js 依赖...", extra={
            'event_type': EventType.INFO,
            'feature': 'image_service'
        })
        if not self.check_dependencies_installed():
            logger.info("开始安装 Node.js 依赖...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service'
            })
            if not self.install_dependencies():
                logger.error("无法安装 Node.js 依赖", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service'
                })
                return False
        
        # 持锁检查状态和启动服务
        with self._lock:
            if self._running:
                logger.warning("图片服务已在运行中", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'image_service'
                })
                return True
            
            # 检查是否已有实例在运行（使用不加锁的版本）
            if self._is_running_unlocked():
                logger.info("检测到图片服务已在运行，跳过启动", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })
                self._running = True
                return True
            
            # 创建 pids 目录
            pids_dir = os.path.dirname(self.pid_file)
            if not os.path.exists(pids_dir):
                os.makedirs(pids_dir, exist_ok=True)
            
            # 启动服务
            try:
                logger.info("正在启动图片生成服务...", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service'
                })
                
                # 使用 CREATE_NO_WINDOW 标志避免显示控制台窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                self.process = subprocess.Popen(
                    ["node", self.node_script],
                    cwd=self.image_generator_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # 保存 PID
                with open(self.pid_file, 'w', encoding='utf-8') as f:
                    f.write(str(self.process.pid))
                
                self._running = True
                
                logger.info(f"图片生成服务进程已启动 (PID: {self.process.pid})", extra={
                    'event_type': EventType.INFO,
                    'feature': 'image_service',
                    'pid': self.process.pid
                })
                
                return True
                
            except Exception as e:
                logger.error(f"启动图片服务失败: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service',
                    'error': str(e)
                })
                self._running = False
                return False
        
        # 等待服务就绪（在锁外部）
        if wait_ready:
            logger.info(f"等待图片服务就绪（最长等待 {timeout} 秒）...", extra={
                'event_type': EventType.INFO,
                'feature': 'image_service',
                'timeout': timeout
            })
            if not self.wait_for_ready(timeout):
                logger.error("图片服务启动超时", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'image_service'
                })
                self.stop()
                return False
        
        return True
    
    def stop(self) -> bool:
        """停止图片服务"""
        with self._lock:
            if not self._running:
                return True
            
            success = True
            pid = self.get_pid()
            
            if pid:
                try:
                    process = psutil.Process(pid)
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                    
                    logger.info(f"图片服务已停止 (PID: {pid})", extra={
                        'event_type': EventType.INFO,
                        'feature': 'image_service',
                        'pid': pid
                    })
                except psutil.NoSuchProcess:
                    pass  # 进程已不存在
                except Exception as e:
                    logger.error(f"停止图片服务失败: {str(e)}", extra={
                        'event_type': EventType.ERROR,
                        'feature': 'image_service',
                        'error': str(e)
                    })
                    success = False
            
            # 清理
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except:
                    pass
                self.process = None
            
            # 删除 PID 文件
            if os.path.exists(self.pid_file):
                try:
                    os.remove(self.pid_file)
                except:
                    pass
            
            self._running = False
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
                    logger.info("图片服务已就绪", extra={
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