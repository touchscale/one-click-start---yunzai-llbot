# -*- coding: utf-8 -*-
"""
OneBot 11 客户端模块 - 支持通过 QQ 机器人远程管理监控脚本
使用 WebSocket 反向连接，无需配置内网穿透
"""
import json
import threading
import time
import asyncio
from typing import Dict, Optional, Callable
from logger import get_logger
from constants import EventType
from event_manager import get_event_manager

logger = get_logger()
event_manager = get_event_manager()

# 尝试导入 websockets 库
try:
    import websockets
    websockets_available = True
except ImportError:
    websockets_available = False
    logger.warning("websockets 库未安装，OneBot 功能不可用", extra={
        'event_type': EventType.WARNING,
        'feature': 'onebot_client',
        'error': 'websockets_not_installed'
    })


class OneBotClient:
    """OneBot 11 WebSocket 反向连接客户端"""
    
    def __init__(self, config: Dict):
        """
        初始化 OneBot 客户端
        
        Args:
            config: OneBot 配置字典
        """
        self.config = config
        self.enabled = config.get('enabled', False)
        self.ws_url = config.get('ws_url', '')
        self.access_token = config.get('access_token', '')
        self.reconnect_interval = config.get('reconnect_interval', 5)
        self.authorized_users = config.get('authorized_users', [])
        
        self.websocket = None
        self.running = False
        self.connect_thread = None
        self.loop = None
        
        # 回调函数字典
        self.message_handlers = {}
        
        # 状态回调
        self.status_callback = None
        
        if not websockets_available:
            self.enabled = False
            logger.warning("OneBot 功能已禁用：websockets 库未安装")
    
    def set_status_callback(self, callback: Callable):
        """设置状态回调函数"""
        self.status_callback = callback
    
    def register_handler(self, command: str, handler: Callable):
        """
        注册指令处理器
        
        Args:
            command: 指令名称
            handler: 处理函数，接收 message_dict 参数，返回回复文本
        """
        self.message_handlers[command] = handler
        logger.info(f"注册 OneBot 指令处理器: {command}", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client',
            'command': command
        })
    
    async def _connect(self):
        """WebSocket 连接协程"""
        while self.running:
            try:
                logger.info(f"尝试连接到 OneBot WebSocket: {self.ws_url}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'connect_attempt'
                })
                
                # 设置连接超时
                import websockets.client
                self.websocket = await asyncio.wait_for(
                    websockets.client.connect(
                        self.ws_url,
                        extra_headers={
                            'Authorization': f'Bearer {self.access_token}'
                        } if self.access_token else {}
                    ),
                    timeout=10
                )
                
                logger.info("OneBot WebSocket 连接成功", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'connect_success'
                })
                
                # 连接成功后发送启动消息
                if self.status_callback:
                    await self.status_callback('connected')
                
                # 开始接收消息
                await self._receive_messages()
                
            except asyncio.TimeoutError:
                logger.warning(f"OneBot WebSocket 连接超时: {self.ws_url}", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'onebot_client',
                    'error': 'connection_timeout'
                })
            except Exception as e:
                logger.error(f"OneBot WebSocket 连接失败: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'onebot_client',
                    'error': str(e)
                })
                
                if self.status_callback:
                    await self.status_callback('disconnected')
            
            # 断线后等待重连
            if self.running:
                logger.info(f"{self.reconnect_interval} 秒后尝试重连...", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'reconnect_wait'
                })
                await asyncio.sleep(self.reconnect_interval)
    
    async def _receive_messages(self):
        """接收消息的协程"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"解析 OneBot 消息失败: {str(e)}", extra={
                        'event_type': EventType.ERROR,
                        'feature': 'onebot_client',
                        'error': str(e)
                    })
                except Exception as e:
                    logger.error(f"处理 OneBot 消息失败: {str(e)}", extra={
                        'event_type': EventType.ERROR,
                        'feature': 'onebot_client',
                        'error': str(e)
                    })
        except Exception as e:
            logger.error(f"OneBot WebSocket 接收消息出错: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
            raise
    
    async def _handle_message(self, data: Dict):
        """
        处理接收到的消息
        
        Args:
            data: 消息数据字典
        """
        # 只处理消息事件
        if data.get('post_type') != 'message':
            return
        
        message_type = data.get('message_type')
        user_id = data.get('user_id')
        message = data.get('message', '')
        
        # 检查用户权限
        if self.authorized_users and str(user_id) not in self.authorized_users:
            logger.warning(f"未授权用户尝试使用 OneBot 指令: {user_id}", extra={
                'event_type': EventType.WARNING,
                'feature': 'onebot_client',
                'user_id': user_id
            })
            return
        
        # 解析消息内容
        if isinstance(message, list):
            # 处理 CQ 码格式的消息
            text_parts = [seg.get('data', {}).get('text', '') for seg in message if seg.get('type') == 'text']
            text = ''.join(text_parts).strip()
        else:
            text = str(message).strip()
        
        if not text.startswith('/'):
            return  # 不是指令
        
        # 解析指令
        parts = text[1:].split()
        command = parts[0] if parts else ''
        args = parts[1:] if len(parts) > 1 else []
        
        logger.info(f"收到 OneBot 指令: {command} {args}", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client',
            'command': command,
            'args': args,
            'user_id': user_id
        })
        
        # 查找对应的处理器
        handler = self.message_handlers.get(command)
        if handler:
            try:
                reply = await self._run_handler(handler, data, args)
                if reply:
                    await self._send_reply(data, reply)
            except Exception as e:
                logger.error(f"执行 OneBot 指令处理器失败: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'onebot_client',
                    'command': command,
                    'error': str(e)
                })
                await self._send_reply(data, f"指令执行失败: {str(e)}")
        else:
            await self._send_reply(data, f"未知指令: {command}")
    
    async def _run_handler(self, handler: Callable, message: Dict, args: list):
        """
        运行指令处理器
        
        Args:
            handler: 处理函数
            message: 消息数据
            args: 参数列表
            
        Returns:
            回复文本
        """
        # 如果是协程函数，使用 await
        if asyncio.iscoroutinefunction(handler):
            return await handler(message, args)
        else:
            # 如果是普通函数，在线程池中执行
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, handler, message, args)
    
    async def _send_reply(self, original_message: Dict, reply: str):
        """
        发送回复消息
        
        Args:
            original_message: 原始消息数据
            reply: 回复内容
        """
        try:
            # 构造回复消息
            reply_data = {
                'action': 'send_msg',
                'params': {
                    'message_type': original_message.get('message_type'),
                    'user_id': original_message.get('user_id'),
                    'group_id': original_message.get('group_id'),
                    'message': reply
                }
            }
            
            await self.websocket.send(json.dumps(reply_data))
            logger.debug(f"发送 OneBot 回复: {reply[:50]}", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_client',
                'action': 'send_reply'
            })
        except Exception as e:
            logger.error(f"发送 OneBot 回复失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
    
    async def send_private_message(self, user_id: int, message: str):
        """
        发送私聊消息
        
        Args:
            user_id: 用户 ID
            message: 消息内容
        """
        if not self.websocket:
            logger.warning("WebSocket 未连接，无法发送消息", extra={
                'event_type': EventType.WARNING,
                'feature': 'onebot_client'
            })
            return
        
        try:
            reply_data = {
                'action': 'send_private_msg',
                'params': {
                    'user_id': user_id,
                    'message': message
                }
            }
            
            await self.websocket.send(json.dumps(reply_data))
            logger.info(f"发送私聊消息到 {user_id}: {message[:50]}", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_client',
                'action': 'send_private_message',
                'user_id': user_id
            })
        except Exception as e:
            logger.error(f"发送私聊消息失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
    
    def _run_loop(self):
        """运行事件循环的线程函数"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connect())
        except Exception as e:
            logger.error(f"OneBot 事件循环出错: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
        finally:
            self.loop.close()
    
    def start(self):
        """启动 OneBot 客户端"""
        if not self.enabled:
            logger.info("OneBot 客户端未启用", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_client'
            })
            return
        
        if not websockets_available:
            logger.error("无法启动 OneBot 客户端：websockets 库未安装", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': 'websockets_not_installed'
            })
            return
        
        self.running = True
        self.connect_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.connect_thread.start()
        
        logger.info("OneBot 客户端已启动", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client',
            'ws_url': self.ws_url
        })
    
    def stop(self):
        """停止 OneBot 客户端"""
        self.running = False
        
        if self.websocket:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.websocket.close(),
                    self.loop
                )
            except:
                pass
        
        if self.connect_thread:
            self.connect_thread.join(timeout=5)
        
        logger.info("OneBot 客户端已停止", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client'
        })


# 全局 OneBot 客户端实例
_onebot_client: Optional[OneBotClient] = None
_client_lock = threading.Lock()


def init_onebot_client(config: Dict) -> Optional[OneBotClient]:
    """
    初始化 OneBot 客户端
    
    Args:
        config: OneBot 配置字典
        
    Returns:
        OneBotClient 实例，如果未启用则返回 None
    """
    global _onebot_client
    
    with _client_lock:
        if _onebot_client is not None:
            return _onebot_client
        
        client = OneBotClient(config)
        _onebot_client = client
        return client


def get_onebot_client() -> Optional[OneBotClient]:
    """
    获取全局 OneBot 客户端实例
    
    Returns:
        OneBotClient 实例，如果未初始化则返回 None
    """
    return _onebot_client