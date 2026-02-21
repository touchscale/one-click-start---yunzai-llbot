# -*- coding: utf-8 -*-
"""
图片生成客户端模块
通过 HTTP API 与 Node.js 图片生成服务通信
"""
import requests
from typing import Dict, Any
from logger import get_logger
from constants import EventType

logger = get_logger()

# 默认服务配置
DEFAULT_SERVICE_URL = "http://localhost:3001"
DEFAULT_TIMEOUT = 30


class ImageServiceClient:
    """图片生成服务客户端"""
    
    def __init__(self, service_url: str = DEFAULT_SERVICE_URL, timeout: int = DEFAULT_TIMEOUT):
        """
        初始化客户端
        
        Args:
            service_url: 图片服务地址
            timeout: 请求超时时间（秒）
        """
        self.service_url = service_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def generate_status_image(self, status_data: Dict[str, Any]) -> str:
        """
        生成状态图片
        
        Args:
            status_data: 状态数据字典
            
        Returns:
            Base64 编码的图片数据
            
        Raises:
            RuntimeError: 生成失败时抛出
        """
        try:
            # 准备数据
            data = {
                'llbot': status_data.get('llbot', {}),
                'yunzai': status_data.get('yunzai', {}),
                'redis': status_data.get('redis', {}),
                'http': status_data.get('http_check', {}),
                'autoRestart': status_data.get('auto_restart', {}),
                'imageService': status_data.get('image_service', {})
            }
            
            # 发送请求
            response = self._post('/api/generate-status', data)
            
            if not response.get('success'):
                error = response.get('error', '未知错误')
                raise RuntimeError(f"图片服务返回错误: {error}")
            
            base64_data = response.get('data', '')
            if not base64_data:
                raise RuntimeError("图片服务未返回数据")
            
            duration = response.get('duration', 0)
            logger.info(f"状态图片生成成功，耗时: {duration}ms", extra={
                'event_type': EventType.INFO,
                'feature': 'image_client',
                'type': 'status',
                'duration': duration
            })
            
            return base64_data
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"无法连接到图片服务: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"生成状态图片失败: {str(e)}")
    
    def generate_help_image(self) -> str:
        """
        生成帮助图片
        
        Returns:
            Base64 编码的图片数据
            
        Raises:
            RuntimeError: 生成失败时抛出
        """
        try:
            # 发送请求
            response = self._post('/api/generate-help', {})
            
            if not response.get('success'):
                error = response.get('error', '未知错误')
                raise RuntimeError(f"图片服务返回错误: {error}")
            
            base64_data = response.get('data', '')
            if not base64_data:
                raise RuntimeError("图片服务未返回数据")
            
            duration = response.get('duration', 0)
            logger.info(f"帮助图片生成成功，耗时: {duration}ms", extra={
                'event_type': EventType.INFO,
                'feature': 'image_client',
                'type': 'help',
                'duration': duration
            })
            
            return base64_data
            
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"无法连接到图片服务: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"生成帮助图片失败: {str(e)}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        检查图片服务健康状态
        
        Returns:
            健康状态字典
        """
        try:
            url = f"{self.service_url}/health"
            response = self.session.get(url, timeout=5)
            
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
                
        except requests.exceptions.RequestException as e:
            return {
                'ready': False,
                'message': f'无法连接到图片服务: {str(e)}'
            }
    
    def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送 POST 请求
        
        Args:
            endpoint: API 端点
            data: 请求数据
            
        Returns:
            响应数据
            
        Raises:
            requests.exceptions.RequestException: 请求失败时抛出
        """
        url = f"{self.service_url}{endpoint}"
        response = self.session.post(url, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def close(self):
        """关闭客户端会话"""
        self.session.close()


# 全局客户端实例（单例模式）
_global_client = None


def get_image_client(service_url: str = DEFAULT_SERVICE_URL, timeout: int = DEFAULT_TIMEOUT):
    """
    获取图片服务客户端实例（单例模式）
    
    Args:
        service_url: 图片服务地址
        timeout: 请求超时时间（秒）
        
    Returns:
        ImageServiceClient 实例
    """
    global _global_client
    
    if _global_client is None:
        _global_client = ImageServiceClient(service_url, timeout)
    
    return _global_client


def check_dependencies(service_url: str = DEFAULT_SERVICE_URL) -> Dict[str, Any]:
    """
    检查图片生成服务依赖是否满足
    
    Args:
        service_url: 图片服务地址
        
    Returns:
        检查结果字典，包含 ready 和 message 字段
    """
    errors = []
    
    # 检查 requests 库是否可用
    try:
        import requests
    except ImportError:
        errors.append("未安装 requests 库，请运行: pip install requests")
    
    # 检查图片服务是否可用
    client = ImageServiceClient(service_url)
    health = client.health_check()
    
    if not health.get('ready'):
        errors.append(f"图片服务不可用: {health.get('message')}")
    
    return {
        'ready': len(errors) == 0,
        'message': '依赖检查通过' if len(errors) == 0 else '依赖缺失: ' + '; '.join(errors),
        'errors': errors
    }