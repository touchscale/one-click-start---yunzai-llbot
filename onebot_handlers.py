# -*- coding: utf-8 -*-
"""
OneBot 指令处理器模块 - 定义各种指令的处理逻辑
"""
from typing import Dict, List
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


def handle_status(message: Dict, args: List[str]) -> str:
    """
    处理状态查询指令
    
    Args:
        message: 消息数据
        args: 参数列表
        
    Returns:
        状态信息文本
    """
    try:
        status_lines = ["📊 监控系统状态\n"]
        status_lines.append("=" * 30)
        
        # llbot 状态
        llbot_status = current_status.get('llbot', {})
        llbot_emoji = "✅" if llbot_status.get('running') else "❌"
        llbot_pid = llbot_status.get('pid')
        llbot_info = f"{llbot_emoji} llbot: {'运行中' if llbot_status.get('running') else '已停止'}"
        if llbot_pid:
            llbot_info += f" (PID: {llbot_pid})"
        status_lines.append(llbot_info)
        
        # Yunzai 状态
        yunzai_status = current_status.get('yunzai', {})
        yunzai_emoji = "✅" if yunzai_status.get('running') else "❌"
        yunzai_pid = yunzai_status.get('pid')
        yunzai_info = f"{yunzai_emoji} Yunzai: {'运行中' if yunzai_status.get('running') else '已停止'}"
        if yunzai_pid:
            yunzai_info += f" (PID: {yunzai_pid})"
        status_lines.append(yunzai_info)
        
        # Redis 状态
        redis_status = current_status.get('redis', {})
        redis_emoji = "✅" if redis_status.get('running') else "❌"
        redis_pid = redis_status.get('pid')
        redis_info = f"{redis_emoji} Redis: {'运行中' if redis_status.get('running') else '已停止'}"
        if redis_pid:
            redis_info += f" (PID: {redis_pid})"
        status_lines.append(redis_info)
        
        # HTTP 检查状态
        http_status = current_status.get('http_check', {})
        http_emoji = "✅" if http_status.get('accessible') else "❌"
        http_info = f"{http_emoji} HTTP服务: {'可访问' if http_status.get('accessible') else '不可访问'}"
        if http_status.get('configured'):
            http_url = current_config.get('http_check', {}).get('url', '')
            if http_url:
                http_info += f"\n   URL: {http_url}"
        status_lines.append(http_info)
        
        # 自动重启状态
        auto_restart_config = current_config.get('auto_restart', {})
        restart_emoji = "✅" if auto_restart_config.get('enabled') else "❌"
        restart_info = f"{restart_emoji} 自动重启: {'已启用' if auto_restart_config.get('enabled') else '已禁用'}"
        status_lines.append(restart_info)
        
        status_lines.append("=" * 30)
        
        return "\n".join(status_lines)
    except Exception as e:
        logger.error(f"查询状态失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'status',
            'error': str(e)
        })
        return f"❌ 查询状态失败: {str(e)}"


def handle_start(message: Dict, args: List[str]) -> str:
    """
    处理启动指令
    
    Args:
        message: 消息数据
        args: 参数列表（服务名称）
        
    Returns:
        执行结果文本
    """
    if not args:
        return "❌ 请指定要启动的服务\n用法: /start <服务名>\n可用服务: llbot, yunzai, redis, all"
    
    service = args[0].lower()
    
    try:
        if service == 'llbot':
            result = start_llbot(current_config)
            if result['success']:
                return "✅ llbot 启动成功"
            else:
                return f"❌ llbot 启动失败: {result.get('message', '未知错误')}"
        
        elif service == 'yunzai':
            result = start_yunzai(current_config)
            if result['success']:
                return "✅ Yunzai 启动成功"
            else:
                return f"❌ Yunzai 启动失败: {result.get('message', '未知错误')}"
        
        elif service == 'redis':
            result = start_redis(current_config)
            if result['success']:
                return "✅ Redis 启动成功"
            else:
                return f"❌ Redis 启动失败: {result.get('message', '未知错误')}"
        
        elif service == 'all':
            results = []
            # 启动 Redis
            redis_result = start_redis(current_config)
            if redis_result['success']:
                results.append("✅ Redis 启动成功")
            else:
                results.append(f"❌ Redis 启动失败: {redis_result.get('message', '未知错误')}")
            
            # 启动 llbot
            llbot_result = start_llbot(current_config)
            if llbot_result['success']:
                results.append("✅ llbot 启动成功")
            else:
                results.append(f"❌ llbot 启动失败: {llbot_result.get('message', '未知错误')}")
            
            # 启动 Yunzai
            yunzai_result = start_yunzai(current_config)
            if yunzai_result['success']:
                results.append("✅ Yunzai 启动成功")
            else:
                results.append(f"❌ Yunzai 启动失败: {yunzai_result.get('message', '未知错误')}")
            
            return "\n".join(results)
        
        else:
            return f"❌ 未知服务: {service}\n可用服务: llbot, yunzai, redis, all"
    
    except Exception as e:
        logger.error(f"启动服务失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'start',
            'service': service,
            'error': str(e)
        })
        return f"❌ 启动失败: {str(e)}"


def handle_stop(message: Dict, args: List[str]) -> str:
    """
    处理停止指令
    
    Args:
        message: 消息数据
        args: 参数列表（服务名称）
        
    Returns:
        执行结果文本
    """
    if not args:
        return "❌ 请指定要停止的服务\n用法: /stop <服务名>\n可用服务: llbot, yunzai, redis, all"
    
    service = args[0].lower()
    
    try:
        if service == 'llbot':
            result = stop_llbot()
            if result['success']:
                return "✅ llbot 已停止"
            else:
                return f"❌ llbot 停止失败: {result.get('message', '未知错误')}"
        
        elif service == 'yunzai':
            result = stop_yunzai()
            if result['success']:
                return "✅ Yunzai 已停止"
            else:
                return f"❌ Yunzai 停止失败: {result.get('message', '未知错误')}"
        
        elif service == 'redis':
            result = stop_redis()
            if result['success']:
                return "✅ Redis 已停止"
            else:
                return f"❌ Redis 停止失败: {result.get('message', '未知错误')}"
        
        elif service == 'all':
            results = []
            # 停止所有服务
            llbot_result = stop_llbot()
            if llbot_result['success']:
                results.append("✅ llbot 已停止")
            else:
                results.append(f"❌ llbot 停止失败: {llbot_result.get('message', '未知错误')}")
            
            yunzai_result = stop_yunzai()
            if yunzai_result['success']:
                results.append("✅ Yunzai 已停止")
            else:
                results.append(f"❌ Yunzai 停止失败: {yunzai_result.get('message', '未知错误')}")
            
            redis_result = stop_redis()
            if redis_result['success']:
                results.append("✅ Redis 已停止")
            else:
                results.append(f"❌ Redis 停止失败: {redis_result.get('message', '未知错误')}")
            
            return "\n".join(results)
        
        else:
            return f"❌ 未知服务: {service}\n可用服务: llbot, yunzai, redis, all"
    
    except Exception as e:
        logger.error(f"停止服务失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'stop',
            'service': service,
            'error': str(e)
        })
        return f"❌ 停止失败: {str(e)}"


def handle_restart(message: Dict, args: List[str]) -> str:
    """
    处理重启指令
    
    Args:
        message: 消息数据
        args: 参数列表（服务名称）
        
    Returns:
        执行结果文本
    """
    if not args:
        return "❌ 请指定要重启的服务\n用法: /restart <服务名>\n可用服务: llbot, yunzai, redis, all"
    
    service = args[0].lower()
    
    try:
        if service == 'llbot':
            result = restart_llbot(current_config)
            if result['success']:
                return "✅ llbot 重启成功"
            else:
                return f"❌ llbot 重启失败: {result.get('message', '未知错误')}"
        
        elif service == 'yunzai':
            result = restart_yunzai(current_config)
            if result['success']:
                return "✅ Yunzai 重启成功"
            else:
                return f"❌ Yunzai 重启失败: {result.get('message', '未知错误')}"
        
        elif service == 'redis':
            result = restart_redis(current_config)
            if result['success']:
                return "✅ Redis 重启成功"
            else:
                return f"❌ Redis 重启失败: {result.get('message', '未知错误')}"
        
        elif service == 'all':
            results = []
            # 重启所有服务
            redis_result = restart_redis(current_config)
            if redis_result['success']:
                results.append("✅ Redis 重启成功")
            else:
                results.append(f"❌ Redis 重启失败: {redis_result.get('message', '未知错误')}")
            
            llbot_result = restart_llbot(current_config)
            if llbot_result['success']:
                results.append("✅ llbot 重启成功")
            else:
                results.append(f"❌ llbot 重启失败: {llbot_result.get('message', '未知错误')}")
            
            yunzai_result = restart_yunzai(current_config)
            if yunzai_result['success']:
                results.append("✅ Yunzai 重启成功")
            else:
                results.append(f"❌ Yunzai 重启失败: {yunzai_result.get('message', '未知错误')}")
            
            return "\n".join(results)
        
        else:
            return f"❌ 未知服务: {service}\n可用服务: llbot, yunzai, redis, all"
    
    except Exception as e:
        logger.error(f"重启服务失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'restart',
            'service': service,
            'error': str(e)
        })
        return f"❌ 重启失败: {str(e)}"


def handle_check_update(message: Dict, args: List[str]) -> str:
    """
    处理检查更新指令
    
    Args:
        message: 消息数据
        args: 参数列表
        
    Returns:
        检查结果文本
    """
    try:
        update_type = args[0].lower() if args else 'all'
        
        results = []
        
        if update_type in ['all', 'frontend']:
            # 检查前端资源更新
            frontend_result = check_and_update_resources()
            if frontend_result['updated'] > 0:
                results.append(f"✅ 前端资源已更新 {frontend_result['updated']} 个文件")
            elif frontend_result['failed'] > 0:
                results.append(f"❌ 前端资源更新失败 {frontend_result['failed']} 个文件")
            else:
                results.append("✅ 前端资源已是最新版本")
        
        if update_type in ['all', 'git']:
            # 检查 Git 仓库更新
            from git_update_checker import get_local_commit, get_remote_commit
            import os
            repo_path = os.path.dirname(os.path.abspath(__file__))
            has_update, _ = check_repo_update(repo_path)
            if has_update:
                local_commit = get_local_commit(repo_path)
                remote_commit = get_remote_commit(repo_path)
                results.append(f"📦 Git 仓库有新版本可用")
                results.append(f"   本地: {local_commit[:8] if local_commit else 'N/A'}")
                results.append(f"   远程: {remote_commit[:8] if remote_commit else 'N/A'}")
                results.append(f"   使用 /update git 拉取更新")
            else:
                results.append("✅ Git 仓库已是最新版本")
        
        if not results:
            return "❌ 未知更新类型\n用法: /check_update <类型>\n可用类型: frontend, git, all"
        
        return "\n".join(results)
    
    except Exception as e:
        logger.error(f"检查更新失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'check_update',
            'error': str(e)
        })
        return f"❌ 检查更新失败: {str(e)}"


def handle_update(message: Dict, args: List[str]) -> str:
    """
    处理更新指令
    
    Args:
        message: 消息数据
        args: 参数列表
        
    Returns:
        更新结果文本
    """
    if not args:
        return "❌ 请指定更新类型\n用法: /update <类型>\n可用类型: frontend, git"
    
    update_type = args[0].lower()
    
    try:
        if update_type == 'frontend':
            # 强制更新前端资源
            from update_checker import FORCE_UPDATE_URLS
            result = check_and_update_resources(force=True)
            if result['updated'] > 0:
                return f"✅ 前端资源已强制更新 {result['updated']} 个文件"
            else:
                return "✅ 前端资源已是最新版本"
        
        elif update_type == 'git':
            # 拉取 Git 更新
            import os
            repo_path = os.path.dirname(os.path.abspath(__file__))
            success, output = pull_repo_update(repo_path)
            if success:
                return f"✅ Git 仓库已更新到最新版本\n{output}"
            else:
                return f"❌ Git 更新失败: {output}"
        
        else:
            return f"❌ 未知更新类型: {update_type}\n可用类型: frontend, git"
    
    except Exception as e:
        logger.error(f"更新失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'update',
            'update_type': update_type,
            'error': str(e)
        })
        return f"❌ 更新失败: {str(e)}"


def handle_help(message: Dict, args: List[str]) -> str:
    """
    处理帮助指令
    
    Args:
        message: 消息数据
        args: 参数列表
        
    Returns:
        帮助信息文本
    """
    help_text = """📖 监控系统指令帮助

📊 状态查询
  /status           查看所有服务状态

🔧 服务控制
  /start <服务>     启动服务
  /stop <服务>      停止服务
  /restart <服务>   重启服务
  
  可用服务: llbot, yunzai, redis, all

🔄 更新管理
  /check_update     检查更新
  /update <类型>    执行更新
  
  更新类型: frontend, git

💡 提示
  所有指令以 / 开头
  使用 all 可以操作所有服务
"""
    return help_text


def register_all_handlers(client):
    """
    注册所有指令处理器到 OneBot 客户端
    
    Args:
        client: OneBotClient 实例
    """
    client.register_handler('status', handle_status)
    client.register_handler('start', handle_start)
    client.register_handler('stop', handle_stop)
    client.register_handler('restart', handle_restart)
    client.register_handler('check_update', handle_check_update)
    client.register_handler('update', handle_update)
    client.register_handler('help', handle_help)
    
    logger.info("所有 OneBot 指令处理器已注册", extra={
        'event_type': EventType.INFO,
        'feature': 'onebot_handler'
    })