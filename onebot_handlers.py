# -*- coding: utf-8 -*-
"""
OneBot 指令处理器模块 - 定义各种指令的处理逻辑
"""
from typing import Dict
from logger import get_logger
from constants import EventType
from event_manager import get_event_manager
from process_manager import (
    start_llbot, stop_llbot, restart_llbot,
    start_yunzai, stop_yunzai, restart_yunzai,
    start_redis, stop_redis, restart_redis
)
from web_server import current_status, current_config
from update_checker import check_and_update_resources
from git_update_checker import check_repo_update, pull_repo_update

logger = get_logger()
event_manager = get_event_manager()


def handle_status(message: Dict, args) -> str:
    """
    处理状态查询指令，返回状态图片
    
    Args:
        message: 消息数据
        args: 参数列表
        
    Returns:
        状态图片的 base64 编码（CQ 码格式）
    """
    # 使用图片生成服务
    try:
        from image_client import get_image_client, check_dependencies
        
        # 获取图片服务配置
        image_service_config = current_config.get('image_service', {})
        service_url = image_service_config.get('url', 'http://localhost:3001')
        
        # 检查依赖
        dep_check = check_dependencies(service_url)
        if dep_check['ready']:
            client = get_image_client(service_url)
            img_base64 = client.generate_status_image(current_status)
            return f"[CQ:image,file=base64://{img_base64}]"
        else:
            logger.warning(f"图片服务不可用，使用文本格式: {dep_check['message']}", extra={
                'event_type': EventType.WARNING,
                'feature': 'onebot_handler',
                'command': 'status',
                'fallback': 'text'
            })
            return _generate_text_status()
    except ImportError:
        logger.warning("image_client 模块未找到，使用文本格式", extra={
            'event_type': EventType.WARNING,
            'feature': 'onebot_handler',
            'command': 'status',
            'fallback': 'text'
        })
        return _generate_text_status()
    except Exception as e:
        logger.error(f"使用图片服务生成状态图片失败，使用文本格式: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'status',
            'error': str(e),
            'fallback': 'text'
        })
        return _generate_text_status()


def _generate_text_status():
    """生成文本格式的状态信息（备用方案）"""
    try:
        status_lines = ["监控系统状态\n"]
        status_lines.append("=" * 30)
        
        llbot_status = current_status.get('llbot', {})
        llbot_emoji = "✓" if llbot_status.get('running') else "✗"
        llbot_info = f"{llbot_emoji} llbot: {'运行中' if llbot_status.get('running') else '已停止'}"
        status_lines.append(llbot_info)
        
        yunzai_status = current_status.get('yunzai', {})
        yunzai_emoji = "✓" if yunzai_status.get('running') else "✗"
        yunzai_info = f"{yunzai_emoji} Yunzai: {'运行中' if yunzai_status.get('running') else '已停止'}"
        status_lines.append(yunzai_info)
        
        redis_status = current_status.get('redis', {})
        redis_emoji = "✓" if redis_status.get('running') else "✗"
        redis_info = f"{redis_emoji} Redis: {'运行中' if redis_status.get('running') else '已停止'}"
        status_lines.append(redis_info)
        
        # 添加图片服务状态
        from image_service_manager import get_image_service_manager
        image_manager = get_image_service_manager()
        image_running = image_manager.is_running()
        image_emoji = "✓" if image_running else "✗"
        image_info = f"{image_emoji} 图片服务: {'运行中' if image_running else '已停止'}"
        status_lines.append(image_info)
        
        return "\n".join(status_lines)
    except:
        return "生成状态失败"
def handle_start(message: Dict, args) -> str:
    """启动服务 /s [服务]"""
    service = args[0].lower() if args else 'all'
    services = {
        'llbot': start_llbot,
        'yunzai': start_yunzai,
        'redis': start_redis
    }
    
    try:
        if service == 'all':
            results = []
            for name, func in services.items():
                result = func(current_config)
                results.append(f"{'✅' if result['success'] else '❌'} {name}: {result['success'] and '启动成功' or result.get('message', '失败')}")
            return "\n".join(results)
        
        if service not in services:
            return f"❌ 未知服务: {service}\n可用: llbot, yunzai, redis, all"
        
        result = services[service](current_config)
        return f"{'✅' if result['success'] else '❌'} {service}: {result['success'] and '启动成功' or result.get('message', '失败')}"
    
    except Exception as e:
        logger.error(f"启动失败: {str(e)}", extra={'event_type': EventType.ERROR, 'feature': 'onebot_handler', 'command': 'start', 'service': service, 'error': str(e)})
        return f"❌ 启动失败: {str(e)}"


def handle_stop(message: Dict, args) -> str:
    """停止服务 /t [服务]"""
    service = args[0].lower() if args else 'all'
    services = {
        'llbot': stop_llbot,
        'yunzai': stop_yunzai,
        'redis': stop_redis
    }
    
    try:
        if service == 'all':
            results = []
            for name, func in services.items():
                result = func()
                results.append(f"{'✅' if result['success'] else '❌'} {name}: {result['success'] and '已停止' or result.get('message', '失败')}")
            return "\n".join(results)
        
        if service not in services:
            return f"❌ 未知服务: {service}\n可用: llbot, yunzai, redis, all"
        
        result = services[service]()
        return f"{'✅' if result['success'] else '❌'} {service}: {result['success'] and '已停止' or result.get('message', '失败')}"
    
    except Exception as e:
        logger.error(f"停止失败: {str(e)}", extra={'event_type': EventType.ERROR, 'feature': 'onebot_handler', 'command': 'stop', 'service': service, 'error': str(e)})
        return f"❌ 停止失败: {str(e)}"


def handle_restart(message: Dict, args) -> str:
    """重启服务 /r [服务]"""
    service = args[0].lower() if args else 'all'
    services = {
        'llbot': restart_llbot,
        'yunzai': restart_yunzai,
        'redis': restart_redis
    }
    
    try:
        if service == 'all':
            results = []
            for name, func in services.items():
                result = func(current_config)
                results.append(f"{'✅' if result['success'] else '❌'} {name}: {result['success'] and '重启成功' or result.get('message', '失败')}")
            return "\n".join(results)
        
        if service not in services:
            return f"❌ 未知服务: {service}\n可用: llbot, yunzai, redis, all"
        
        result = services[service](current_config)
        return f"{'✅' if result['success'] else '❌'} {service}: {result['success'] and '重启成功' or result.get('message', '失败')}"
    
    except Exception as e:
        logger.error(f"重启失败: {str(e)}", extra={'event_type': EventType.ERROR, 'feature': 'onebot_handler', 'command': 'restart', 'service': service, 'error': str(e)})
        return f"❌ 重启失败: {str(e)}"


def handle_check_update(message: Dict, args) -> str:
    """检查更新"""
    try:
        update_type = args[0].lower() if args else 'all'
        results = []
        
        if update_type in ['all', 'frontend']:
            frontend_result = check_and_update_resources()
            if frontend_result['updated'] > 0:
                results.append(f"✅ 前端资源已更新 {frontend_result['updated']} 个文件")
            elif frontend_result['failed'] > 0:
                results.append(f"❌ 前端资源更新失败 {frontend_result['failed']} 个文件")
            else:
                results.append("✅ 前端资源已是最新")
        
        if update_type in ['all', 'git']:
            from git_update_checker import get_local_commit, get_remote_commit
            import os
            repo_path = os.path.dirname(os.path.abspath(__file__))
            has_update, _ = check_repo_update(repo_path)
            if has_update:
                local_commit = get_local_commit(repo_path)
                remote_commit = get_remote_commit(repo_path)
                results.append(f"📦 Git 有新版本\n本地: {local_commit[:8] if local_commit else 'N/A'}\n远程: {remote_commit[:8] if remote_commit else 'N/A'}")
            else:
                results.append("✅ Git 已是最新")
        
        return "\n".join(results) if results else "❌ 未知类型: frontend, git, all"
    
    except Exception as e:
        logger.error(f"检查更新失败: {str(e)}", extra={'event_type': EventType.ERROR, 'feature': 'onebot_handler', 'command': 'check_update', 'error': str(e)})
        return f"❌ 检查失败: {str(e)}"


def handle_update(message: Dict, args) -> str:
    """执行更新"""
    if not args:
        return "❌ 请指定类型: frontend, git"
    
    update_type = args[0].lower()
    
    try:
        if update_type == 'frontend':
            result = check_and_update_resources(force=True)
            return f"✅ 前端资源已更新 {result['updated']} 个文件" if result['updated'] > 0 else "✅ 前端资源已是最新"
        
        if update_type == 'git':
            import os
            repo_path = os.path.dirname(os.path.abspath(__file__))
            success, output = pull_repo_update(repo_path)
            return f"✅ Git 已更新\n{output}" if success else f"❌ Git 更新失败: {output}"
        
        return f"❌ 未知类型: {update_type}\n可用: frontend, git"
    
    except Exception as e:
        logger.error(f"更新失败: {str(e)}", extra={'event_type': EventType.ERROR, 'feature': 'onebot_handler', 'command': 'update', 'update_type': update_type, 'error': str(e)})
        return f"❌ 更新失败: {str(e)}"


def handle_help(message: Dict, args) -> str:
    """显示帮助（优先返回图片格式）"""
    # 首先尝试使用图片生成服务
    try:
        from image_client import get_image_client, check_dependencies
        
        # 获取图片服务配置
        image_service_config = current_config.get('image_service', {})
        service_url = image_service_config.get('url', 'http://localhost:3001')
        
        # 检查依赖
        dep_check = check_dependencies(service_url)
        if dep_check['ready']:
            client = get_image_client(service_url)
            img_base64 = client.generate_help_image()
            return f"[CQ:image,file=base64://{img_base64}]"
        else:
            logger.warning(f"图片服务不可用，使用文本格式: {dep_check['message']}", extra={
                'event_type': EventType.WARNING,
                'feature': 'onebot_handler',
                'command': 'help',
                'fallback': 'text'
            })
            return _generate_text_help()
    except ImportError:
        logger.warning("image_client 模块未找到，使用文本格式", extra={
            'event_type': EventType.WARNING,
            'feature': 'onebot_handler',
            'command': 'help',
            'fallback': 'text'
        })
        return _generate_text_help()
    except Exception as e:
        logger.error(f"使用图片服务生成帮助图片失败，使用文本格式: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'help',
            'error': str(e),
            'fallback': 'text'
        })
        return _generate_text_help()


def handle_start_image_service(message: Dict, args) -> str:
    """启动图片服务"""
    try:
        from image_service_manager import get_image_service_manager

        logger.info("收到启动图片服务指令", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_handler',
            'command': 'start_image_service',
            'user_id': message.get('user_id', 'unknown')
        })

        manager = get_image_service_manager()

        # 检查是否已在运行
        logger.info("检查图片服务运行状态...", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_handler',
            'command': 'start_image_service'
        })

        if manager.is_running():
            pid = manager.get_pid()
            logger.info(f"图片服务已在运行中 (PID: {pid})", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_handler',
                'command': 'start_image_service',
                'pid': pid
            })
            return f"✅ 图片服务已在运行中\n📋 进程 ID: {pid}\n🌐 服务地址: http://localhost:3001"

        # 启动服务
        logger.info("开始启动图片服务...", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_handler',
            'command': 'start_image_service'
        })

        success = manager.start(wait_ready=True, timeout=60)

        if success:
            pid = manager.get_pid()
            logger.info(f"图片服务启动成功 (PID: {pid})", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_handler',
                'command': 'start_image_service',
                'pid': pid
            })

            # 检查健康状态
            logger.info("执行健康检查...", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_handler',
                'command': 'start_image_service'
            })

            health = manager.health_check()
            if health.get('ready'):
                health_msg = health.get('message', '正常')
                logger.info(f"健康检查通过: {health_msg}", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_handler',
                    'command': 'start_image_service'
                })
                return f"✅ 图片服务启动成功\n📋 进程 ID: {pid}\n🌐 服务地址: http://localhost:3001\n💚 健康状态: {health_msg}"
            else:
                health_msg = health.get('message', '未知')
                logger.warning(f"健康检查失败: {health_msg}", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'onebot_handler',
                    'command': 'start_image_service',
                    'health_check': health_msg
                })
                return f"⚠️ 图片服务启动成功但健康检查异常\n📋 进程 ID: {pid}\n🌐 服务地址: http://localhost:3001\n❗ 健康状态: {health_msg}"
        else:
            logger.error("图片服务启动失败", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_handler',
                'command': 'start_image_service'
            })
            return "❌ 图片服务启动失败\n💡 请检查以下内容：\n   • Node.js 是否已安装\n   • image-generator 目录是否存在\n   • Node.js 依赖是否已安装\n   • 查看日志获取详细错误信息"

    except Exception as e:
        logger.error(f"启动图片服务失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'start_image_service',
            'error': str(e),
            'error_type': type(e).__name__
        })
        return f"❌ 启动图片服务失败\n📝 错误信息: {str(e)}\n💡 请查看日志获取详细信息"


def handle_stop_image_service(message: Dict, args) -> str:
    """停止图片服务"""
    try:
        from image_service_manager import get_image_service_manager

        logger.info("收到停止图片服务指令", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_handler',
            'command': 'stop_image_service',
            'user_id': message.get('user_id', 'unknown')
        })

        manager = get_image_service_manager()

        # 检查是否在运行
        logger.info("检查图片服务运行状态...", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_handler',
            'command': 'stop_image_service'
        })

        if not manager.is_running():
            logger.info("图片服务未运行", extra={
                'event_type': EventType.INFO,
                'feature': 'onebot_handler',
                'command': 'stop_image_service'
            })
            return "✅ 图片服务已停止（未发现运行中的进程）"

        pid = manager.get_pid()
        logger.info(f"发现运行中的图片服务 (PID: {pid})，准备停止...", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_handler',
            'command': 'stop_image_service',
            'pid': pid
        })

        # 停止服务
        logger.info("开始停止图片服务...", extra={
            'event_type': EventType.INFO,
            'feature': 'onebot_handler',
            'command': 'stop_image_service'
        })

        success = manager.stop()

        if success:
            # 等待一下，确保进程完全终止
            import time
            time.sleep(1)

            # 再次检查状态
            is_still_running = manager.is_running()
            if is_still_running:
                logger.warning("图片服务可能仍在运行", extra={
                    'event_type': EventType.WARNING,
                    'feature': 'onebot_handler',
                    'command': 'stop_image_service'
                })
                return "⚠️ 图片服务停止命令已执行，但检测到进程可能仍在运行\n💡 可能需要强制终止，请稍后再试或查看日志"
            else:
                logger.info("图片服务已成功停止", extra={
                    'event_type': EventType.INFO,
                    'feature': 'onebot_handler',
                    'command': 'stop_image_service'
                })
                return "✅ 图片服务已成功停止\n📋 所有相关进程已终止\n🔒 端口 3001 已释放"
        else:
            logger.error("图片服务停止失败", extra={
                'event_type': EventType.ERROR,
                'feature': 'onebot_handler',
                'command': 'stop_image_service'
            })
            return "❌ 图片服务停止失败\n💡 请查看日志获取详细错误信息\n💡 可能需要手动终止进程"

    except Exception as e:
        logger.error(f"停止图片服务失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'stop_image_service',
            'error': str(e),
            'error_type': type(e).__name__
        })
        return f"❌ 停止图片服务失败\n📝 错误信息: {str(e)}\n💡 请查看日志获取详细信息"


def _generate_text_help():
    """生成文本格式的帮助信息（备用方案）"""
    return """📖 指令帮助

📊 /st /status      查看状态

🔧 /s /start [服务] 启动服务
🔧 /t /stop [服务]  停止服务
🔧 /r /restart [服务] 重启服务
   服务: llbot, yunzai, redis, all (默认all)

🖼️ /si /start_image 启动图片服务
🖼️ /ti /stop_image  停止图片服务

🔄 /cu /check_update 检查更新
🔄 /up /update [类型] 执行更新
   类型: frontend, git, all (默认all)

💡 /h /help         帮助
"""


def register_all_handlers(client):
    """
    注册所有指令处理器到 OneBot 客户端
    
    Args:
        client: OneBotClient 实例
    """
    client.register_handler('status', handle_status)
    client.register_handler('st', handle_status)
    client.register_handler('start', handle_start)
    client.register_handler('s', handle_start)
    client.register_handler('stop', handle_stop)
    client.register_handler('t', handle_stop)
    client.register_handler('restart', handle_restart)
    client.register_handler('r', handle_restart)
    client.register_handler('start_image', handle_start_image_service)
    client.register_handler('si', handle_start_image_service)
    client.register_handler('stop_image', handle_stop_image_service)
    client.register_handler('ti', handle_stop_image_service)
    client.register_handler('check_update', handle_check_update)
    client.register_handler('cu', handle_check_update)
    client.register_handler('update', handle_update)
    client.register_handler('up', handle_update)
    client.register_handler('help', handle_help)
    client.register_handler('h', handle_help)
    
    logger.info("所有 OneBot 指令处理器已注册", extra={
        'event_type': EventType.INFO,
        'feature': 'onebot_handler'
    })