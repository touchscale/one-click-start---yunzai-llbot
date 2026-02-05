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
    处理状态查询指令，返回状态图片（使用 Pillow 绘制）
    
    Args:
        message: 消息数据
        args: 参数列表
        
    Returns:
        状态图片的 base64 编码（CQ 码格式）
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        import base64
        from datetime import datetime
        
        # 构建状态信息
        llbot_status = current_status.get('llbot', {})
        llbot_running = llbot_status.get('running')
        llbot_pid = llbot_status.get('pid')
        
        yunzai_status = current_status.get('yunzai', {})
        yunzai_running = yunzai_status.get('running')
        yunzai_pid = yunzai_status.get('pid')
        
        redis_status = current_status.get('redis', {})
        redis_running = redis_status.get('running')
        redis_pid = redis_status.get('pid')
        
        http_status = current_status.get('http_check', {})
        http_accessible = http_status.get('accessible')
        
        auto_restart_config = current_config.get('auto_restart', {})
        auto_restart_enabled = auto_restart_config.get('enabled')
        
        # 创建图片
        width, height = 650, 480
        image = Image.new('RGB', (width, height), color='#1a1a2e')
        draw = ImageDraw.Draw(image)
        
        # 尝试加载字体
        try:
            font_title = ImageFont.truetype("C:\\Windows\\Fonts\\msyhbd.ttc", 28)
            font_large = ImageFont.truetype("C:\\Windows\\Fonts\\msyh.ttc", 20)
            font_medium = ImageFont.truetype("C:\\Windows\\Fonts\\msyh.ttc", 16)
            font_small = ImageFont.truetype("C:\\Windows\\Fonts\\msyh.ttc", 13)
        except:
            font_title = ImageFont.load_default()
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # 标题
        title = "监控系统状态"
        title_bbox = draw.textbbox((0, 0), title, font=font_title)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((width - title_width) // 2, 25), title, fill='#e94560', font=font_title)
        
        # 装饰线
        draw.line([(20, 75), (width - 20, 75)], fill='#0f3460', width=3)
        
        # 状态列表
        y_pos = 100
        
        def draw_status_card(label, is_running, pid=None):
            nonlocal y_pos
            
            card_height = 50
            card_y = y_pos
            
            # 卡片背景
            draw.rectangle([20, card_y, width - 20, card_y + card_height], 
                          fill='#16213e', outline='#0f3460', width=2)
            
            # 状态指示器
            circle_radius = 10
            circle_x = 45
            circle_y = card_y + card_height // 2
            
            if is_running:
                # 绿色圆圈
                draw.ellipse([circle_x - circle_radius, circle_y - circle_radius, 
                            circle_x + circle_radius, circle_y + circle_radius], 
                          fill='#00b894', outline='#00cec9', width=2)
                # 勾号
                draw.line([circle_x - 4, circle_y, circle_x - 1, circle_y + 3], fill='#ffffff', width=2)
                draw.line([circle_x - 1, circle_y + 3, circle_x + 5, circle_y - 4], fill='#ffffff', width=2)
                status_color = "#00b894"
                status_text = "运行中"
            else:
                # 红色圆圈
                draw.ellipse([circle_x - circle_radius, circle_y - circle_radius, 
                            circle_x + circle_radius, circle_y + circle_radius], 
                          fill='#d63031', outline='#e17055', width=2)
                # 叉号
                draw.line([circle_x - 4, circle_y - 4, circle_x + 4, circle_y + 4], fill='#ffffff', width=2)
                draw.line([circle_x - 4, circle_y + 4, circle_x + 4, circle_y - 4], fill='#ffffff', width=2)
                status_color = "#d63031"
                status_text = "已停止"
            
            # 服务名称
            draw.text((70, card_y + 12), label, fill='#dfe6e9', font=font_large)
            
            # 状态文本
            draw.text((200, card_y + 12), status_text, fill=status_color, font=font_large)
            
            # PID
            if pid:
                draw.text((400, card_y + 12), f"PID: {pid}", fill='#636e72', font=font_medium)
            
            y_pos += card_height + 10
        
        # 绘制各个状态
        draw_status_card("llbot", llbot_running, llbot_pid)
        draw_status_card("Yunzai", yunzai_running, yunzai_pid)
        draw_status_card("Redis", redis_running, redis_pid)
        draw_status_card("HTTP服务", http_accessible, None)
        draw_status_card("自动重启", auto_restart_enabled, None)
        
        # 底部装饰线
        draw.line([(20, y_pos), (width - 20, y_pos)], fill='#0f3460', width=2)
        
        # 时间戳
        y_pos += 15
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        timestamp_bbox = draw.textbbox((0, 0), timestamp, font=font_small)
        timestamp_width = timestamp_bbox[2] - timestamp_bbox[0]
        draw.text(((width - timestamp_width) // 2, y_pos), f"更新时间: {timestamp}", fill='#636e72', font=font_small)
        
        # 转换为 base64
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        
        return f"[CQ:image,file=base64://{img_base64}]"
        
    except Exception as e:
        logger.error(f"生成状态图片失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'onebot_handler',
            'command': 'status',
            'error': str(e)
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
        
        return "\n".join(status_lines)
    except:
        return "生成状态失败"
def handle_start(message: Dict, args: List[str]) -> str:
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


def handle_stop(message: Dict, args: List[str]) -> str:
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


def handle_restart(message: Dict, args: List[str]) -> str:
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


def handle_check_update(message: Dict, args: List[str]) -> str:
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


def handle_update(message: Dict, args: List[str]) -> str:
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


def handle_help(message: Dict, args: List[str]) -> str:
    """显示帮助"""
    return """📖 指令帮助

📊 /st /status      查看状态

🔧 /s /start [服务] 启动服务
🔧 /t /stop [服务]  停止服务
🔧 /r /restart [服务] 重启服务
   服务: llbot, yunzai, redis, all (默认all)

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