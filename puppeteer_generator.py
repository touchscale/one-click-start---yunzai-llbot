# -*- coding: utf-8 -*-
"""
Puppeteer 图片生成器模块
调用 Node.js 脚本生成状态图片和帮助图片
"""
import json
import subprocess
import os
from logger import get_logger
from constants import EventType

logger = get_logger()

# 获取脚本所在目录的绝对路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_GENERATOR_DIR = os.path.join(SCRIPT_DIR, 'image_generator')
NODE_SCRIPT = os.path.join(IMAGE_GENERATOR_DIR, 'index.js')


def generate_status_image(status_data) -> str:
    """
    生成状态图片
    
    Args:
        status_data: 状态数据字典，包含 llbot, yunzai, redis, http, autoRestart 等信息
        
    Returns:
        Base64 编码的图片数据
    """
    try:
        # 准备数据
        data = {
            'llbot': status_data.get('llbot', {}),
            'yunzai': status_data.get('yunzai', {}),
            'redis': status_data.get('redis', {}),
            'http': status_data.get('http_check', {}),
            'autoRestart': status_data.get('auto_restart', {})
        }
        
        # 调用 Node.js 脚本
        result = _call_puppeteer('status', data)
        
        logger.info("状态图片生成成功", extra={
            'event_type': EventType.INFO,
            'feature': 'puppeteer_generator',
            'type': 'status'
        })
        
        return result
        
    except Exception as e:
        logger.error(f"生成状态图片失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'puppeteer_generator',
            'type': 'status',
            'error': str(e)
        })
        raise


def generate_help_image() -> str:
    """
    生成帮助图片
    
    Returns:
        Base64 编码的图片数据
    """
    try:
        # 调用 Node.js 脚本
        result = _call_puppeteer('help', {})
        
        logger.info("帮助图片生成成功", extra={
            'event_type': EventType.INFO,
            'feature': 'puppeteer_generator',
            'type': 'help'
        })
        
        return result
        
    except Exception as e:
        logger.error(f"生成帮助图片失败: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'feature': 'puppeteer_generator',
            'type': 'help',
            'error': str(e)
        })
        raise


def _call_puppeteer(type_, data) -> str:
    """
    调用 Puppeteer 脚本生成图片
    
    Args:
        type_: 图片类型 (status|help)
        data: 传递给脚本的数据
        
    Returns:
        Base64 编码的图片数据
        
    Raises:
        RuntimeError: 当脚本执行失败时
    """
    # 检查 Node.js 脚本是否存在
    if not os.path.exists(NODE_SCRIPT):
        raise RuntimeError(f"Puppeteer 脚本不存在: {NODE_SCRIPT}")
    
    # 检查 node_modules 是否存在
    node_modules = os.path.join(IMAGE_GENERATOR_DIR, 'node_modules')
    if not os.path.exists(node_modules):
        raise RuntimeError(
            f"Node.js 依赖未安装。请在 {IMAGE_GENERATOR_DIR} 目录下运行: npm install"
        )
    
    # 构建命令
    cmd = ['node', NODE_SCRIPT, type_, json.dumps(data, ensure_ascii=False)]
    
    try:
        # 执行命令
        result = subprocess.run(
            cmd,
            cwd=IMAGE_GENERATOR_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8'
        )
        
        # 检查返回码
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Puppeteer 脚本执行失败 (返回码 {result.returncode}): {error_msg}")
        
        # 获取输出
        base64_data = result.stdout.strip()
        
        if not base64_data:
            raise RuntimeError("Puppeteer 脚本未返回任何数据")
        
        return base64_data
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("Puppeteer 脚本执行超时（30秒）")
    except FileNotFoundError:
        raise RuntimeError("未找到 Node.js，请确保已安装 Node.js 并添加到 PATH")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"数据序列化失败: {str(e)}")


def check_dependencies():
    """
    检查 Puppeteer 生成器依赖是否满足
    
    Returns:
        检查结果字典，包含 ready 和 message 字段
    """
    errors = []
    
    # 检查 Node.js 是否可用
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            errors.append("Node.js 未正确安装")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        errors.append("未找到 Node.js，请安装 Node.js 并添加到 PATH")
    
    # 检查脚本是否存在
    if not os.path.exists(NODE_SCRIPT):
        errors.append(f"Puppeteer 脚本不存在: {NODE_SCRIPT}")
    
    # 检查依赖是否已安装
    node_modules = os.path.join(IMAGE_GENERATOR_DIR, 'node_modules')
    if not os.path.exists(node_modules):
        errors.append(f"Node.js 依赖未安装，请在 {IMAGE_GENERATOR_DIR} 目录运行: npm install")
    
    # 检查 Microsoft Edge 是否存在
    edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    if not os.path.exists(edge_path):
        # 尝试其他常见路径
        alternative_paths = [
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe')
        ]
        edge_found = any(os.path.exists(p) for p in alternative_paths)
        if not edge_found:
            errors.append("未找到 Microsoft Edge，请安装 Microsoft Edge")
    
    return {
        'ready': len(errors) == 0,
        'message': '依赖检查通过' if len(errors) == 0 else '依赖缺失: ' + '; '.join(errors),
        'errors': errors
    }