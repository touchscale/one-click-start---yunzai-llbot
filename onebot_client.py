# -*- coding: utf-8 -*-
"""
OneBot 11 反向 WebSocket 服务器模块 - 支持通过 QQ 机器人远程管理监控脚本

此模块实现反向 WebSocket 服务器模式：
- 脚本作为 WebSocket 服务器运行，监听指定端口
- OneBot 作为客户端，主动连接到此服务器
- 适用于无需内网穿透的场景

配置说明：
- ws_url: WebSocket 服务器监听地址（如 ws://localhost:8080）
- access_token: 访问令牌，用于验证 OneBot 连接
- 在 OneBot 配置中，需要配置反向 WebSocket 目标地址为脚本监听的地址
"""
import json
import threading
import asyncio
from typing import Dict, Callable
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
    """OneBot 11 反向 WebSocket 服务器
    
    作为 WebSocket 服务器运行，等待 OneBot 主动连接
    """
    
    def __init__(self, config: Dict):
        """
        初始化 OneBot 反向 WebSocket 服务器
        
        Args:
            config: OneBot 配置字典
        """
        self.config = config
        self.enabled = config.get('enabled', False)
        self.ws_url = config.get('ws_url', '')  # WebSocket 服务器监听地址
        self.access_token = config.get('access_token', '')  # 访问令牌
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
        """反向 WebSocket 服务器 - 等待 OneBot 主动连接"""
        # 解析监听地址和端口
        # ws_url 格式: ws://host:port 或 ws://host
        import re
        import websockets.server
        
        # 提取 host 和 port
        match = re.match(r'ws://([^:]+)(?::(\d+))?', self.ws_url)
        if not match:
            logger.error(f"无效的 WebSocket URL 格式: {self.ws_url}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': 'invalid_url_format'
            })
            return
        
        host = match.group(1)
        port = int(match.group(2)) if match.group(2) else 8080
        
        logger.info(f"反向 WebSocket 服务器启动，监听 {host}:{port}", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client',
            'action': 'server_start',
            'host': host,
            'port': port
        })
        
        async def handle_connection(websocket, path):
            """处理 OneBot 的连接"""
            logger.info(f"OneBot 已连接到反向 WebSocket 服务器", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_client',
                'action': 'client_connected',
                'remote_address': websocket.remote_address
            })
            
            # 验证 access_token
            if self.access_token:
                auth_header = websocket.request_headers.get('Authorization', '')
                expected_auth = f'Bearer {self.access_token}'
                if auth_header != expected_auth:
                    logger.warning(f"OneBot 连接认证失败: 期望 {expected_auth}，实际 {auth_header}", extra={
                        'event_type': EventType.WARNING,
                        'feature': 'onebot_client',
                        'error': 'authentication_failed'
                    })
                    await websocket.close(code=1008, reason='Unauthorized')
                    return
            
            self.websocket = websocket
            
            # 连接成功后发送启动消息
            if self.status_callback:
                await self.status_callback('connected')
            
            try:
                # 开始接收消息
                await self._receive_messages()
            finally:
                logger.info(f"OneBot 连接已断开", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'client_disconnected'
                })
                if self.status_callback:
                    await self.status_callback('disconnected')
                self.websocket = None
        
        # 启动 WebSocket 服务器
        try:
            async with websockets.server.serve(
                handle_connection,
                host,
                port,
                ping_interval=None,
                ping_timeout=None
            ):
                logger.info(f"反向 WebSocket 服务器正在运行，等待 OneBot 连接...", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'server_running'
                })
                
                # 保持服务器运行
                while self.running:
                    await asyncio.sleep(1)
                    
        except OSError as e:
            logger.error(f"反向 WebSocket 服务器启动失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
            if self.status_callback:
                await self.status_callback('disconnected')
    
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
        # 记录收到的原始消息（用于调试）
        post_type = data.get('post_type', 'unknown')
        message_type = data.get('message_type', 'unknown')
        sub_type = data.get('sub_type', 'unknown')
        user_id = data.get('user_id', 'unknown')
        group_id = data.get('group_id', 'unknown')
        message = data.get('message', '')
        raw_message = data.get('raw_message', '')
        sender = data.get('sender', {})
        sender_nickname = sender.get('nickname', 'unknown') if sender else 'unknown'
        sender_card = sender.get('card', '') if sender else ''

        # 格式化消息内容用于日志显示
        if isinstance(message, list):
            # CQ 码格式，提取文本
            text_parts = [seg.get('data', {}).get('text', '') for seg in message if seg.get('type') == 'text']
            message_text = ''.join(text_parts).strip()
            message_display = f"[CQ码] {message_text[:100]}{'...' if len(message_text) > 100 else ''}"
        else:
            message_text = str(message).strip()
            message_display = message_text[:100] + ('...' if len(message_text) > 100 else '')

        # 根据消息类型显示不同的日志
        if message_type == 'private':
            logger.info(f"收到私聊消息 - 用户: {sender_nickname}({user_id}) | 内容: {message_display}", extra={
                        'event_type': EventType.INFO,
                        'feature': 'onebot_client',
                        'message_type': message_type,
                        'user_id': user_id,
                        'sender_nickname': sender_nickname,
                        'message_content': message_display,
                        'raw_data': data
                    })
        elif message_type == 'group':
            # 在 OneBot 11 中，群名通常在 data 的 group_name 字段中
            # 或者从 sender 的 card 或 group_name 中获取
            group_name = data.get('group_name') or (sender.get('group_name', 'unknown') if sender else 'unknown')
            display_name = sender_card if sender_card else sender_nickname
            logger.info(f"收到群消息 - 群: {group_name}({group_id}) | 发送者: {display_name}({user_id}) | 内容: {message_display}", extra={
                        'event_type': EventType.INFO,
                        'feature': 'onebot_client',
                        'message_type': message_type,
                        'group_id': group_id,
                        'group_name': group_name,
                        'user_id': user_id,
                        'sender_name': display_name,
                        'sender_nickname': sender_nickname,
                        'message_content': message_display,
                        'raw_data': data
                    })
        else:
            logger.info(f"收到{message_type}消息 - 类型: {sub_type} | 内容: {message_display}", extra={
                        'event_type': EventType.INFO,
                        'feature': 'onebot_client',
                        'message_type': message_type,
                        'sub_type': sub_type,
                        'user_id': user_id,
                        'message_content': message_display,
                        'raw_data': data
                    })
        # 只处理消息事件
        if post_type != 'message':
            logger.debug(f"跳过非消息事件: {post_type}", extra={
                'event_type': EventType.DEBUG,
                'feature': 'onebot_client',
                'post_type': post_type
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
            logger.debug(f"收到普通消息（非指令）: {text[:50]}...", extra={
                'event_type': EventType.DEBUG,
                'feature': 'onebot_client',
                'user_id': user_id,
                'message_type': message_type
            })
            return  # 不是指令

        # 解析指令
        parts = text[1:].split()
        command = parts[0] if parts else ''
        args = parts[1:] if len(parts) > 1 else []

        logger.info(f"解析到 OneBot 指令: /{command} 参数: {args}", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client',
            'command': command,
            'command_args': args,
            'user_id': user_id
        })

        # 检查用户权限
        if self.authorized_users and str(user_id) not in self.authorized_users:
            logger.warning(f"用户 {user_id}({sender_nickname}) 无权限执行指令: /{command}", extra={
                'event_type': EventType.WARNING,
                'feature': 'onebot_client',
                'user_id': user_id,
                'sender_nickname': sender_nickname,
                'command': command,
                'authorized_users': self.authorized_users
            })
            return
        
        # 查找对应的处理器
        handler = self.message_handlers.get(command)
        if handler:
            try:
                logger.info(f"开始执行指令: /{command} 参数: {args}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'command': command,
                    'command_args': args,
                    'user_id': user_id
                })
                reply = await self._run_handler(handler, data, args)
                if reply:
                    logger.info(f"指令执行成功: /{command} | 回复: {reply[:100]}{'...' if len(reply) > 100 else ''}", extra={
                        'event_type': EventType.INFO,
                        'feature': 'onebot_client',
                        'command': command,
                        'reply': reply[:200],  # 限制日志长度
                        'user_id': user_id
                    })
                    await self._send_reply(data, reply)
                else:
                    logger.info(f"指令执行成功（无回复）: /{command}", extra={
                        'event_type': EventType.INFO,
                        'feature': 'onebot_client',
                        'command': command,
                        'user_id': user_id
                    })
            except Exception as e:
                logger.error(f"执行 OneBot 指令失败: /{command} | 错误: {str(e)}", extra={
                    'event_type': EventType.ERROR,
                    'feature': 'onebot_client',
                    'command': command,
                    'error': str(e),
                    'user_id': user_id
                })
                await self._send_reply(data, f"指令执行失败: {str(e)}")
        else:
            logger.warning(f"未知指令: /{command} | 已注册指令: {list(self.message_handlers.keys())}", extra={
                'event_type': EventType.WARNING,
                'feature': 'onebot_client',
                'command': command,
                'user_id': user_id,
                'available_commands': list(self.message_handlers.keys())
            })
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
        message_type = original_message.get('message_type', 'unknown')
        user_id = original_message.get('user_id', 'unknown')
        group_id = original_message.get('group_id', 'unknown')

        try:
            # 构造回复消息
            reply_data = {
                'action': 'send_msg',
                'params': {
                    'message_type': message_type,
                    'user_id': user_id,
                    'group_id': group_id,
                    'message': reply
                }
            }

            await self.websocket.send(json.dumps(reply_data))

            # 根据消息类型显示不同的日志
            if message_type == 'private':
                logger.info(f"发送私聊回复 -> 用户 {user_id} | 内容: {reply[:100]}{'...' if len(reply) > 100 else ''}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'send_reply',
                    'message_type': message_type,
                    'user_id': user_id,
                    'message_content': reply[:200]
                })
            elif message_type == 'group':
                logger.info(f"发送群回复 -> 群 {group_id} | 内容: {reply[:100]}{'...' if len(reply) > 100 else ''}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'send_reply',
                    'message_type': message_type,
                    'group_id': group_id,
                    'message_content': reply[:200]
                })
            else:
                logger.info(f"发送回复 -> {message_type} | 内容: {reply[:100]}{'...' if len(reply) > 100 else ''}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_client',
                    'action': 'send_reply',
                    'message_type': message_type,
                    'message_content': reply[:200]
                })
        except Exception as e:
            logger.error(f"发送 OneBot 回复失败: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e),
                'message_type': message_type,
                'user_id': user_id
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
        """运行反向 WebSocket 服务器的事件循环"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._connect())
        except Exception as e:
            logger.error(f"OneBot 反向 WebSocket 服务器事件循环出错: {str(e)}", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': str(e)
            })
        finally:
            self.loop.close()
    
    def start(self):
        """启动 OneBot 反向 WebSocket 服务器"""
        if not self.enabled:
            logger.info("OneBot 反向 WebSocket 服务器未启用", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_client'
            })
            return
        
        if not websockets_available:
            logger.error("无法启动 OneBot 反向 WebSocket 服务器：websockets 库未安装", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_client',
                'error': 'websockets_not_installed'
            })
            return
        
        self.running = True
        self.connect_thread = threading.Thread(target=self._run_loop, daemon=True)
        self.connect_thread.start()
        
        logger.info("OneBot 反向 WebSocket 服务器已启动", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client',
            'ws_url': self.ws_url
        })
    
    def stop(self):
        """停止 OneBot 反向 WebSocket 服务器"""
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
        
        logger.info("OneBot 反向 WebSocket 服务器已停止", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_client'
        })


# 全局 OneBot 客户端实例
_onebot_client = None
_client_lock = threading.Lock()


def init_onebot_client(config: Dict):
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


def get_onebot_client():
    """
    获取全局 OneBot 客户端实例
    
    Returns:
        OneBotClient 实例，如果未初始化则返回 None
    """
    return _onebot_client