# -*- coding: utf-8 -*-
"""
更新检查模块 - 自动检查并下载 Bootstrap 等前端库的更新
"""
import os
import hashlib
import requests
from logger import get_logger
from constants import EventType

logger = get_logger()

# CDN 提供商优先级列表（从高到低）
CDN_PROVIDERS = [
    'zstatic',    # Zstatic CDN (最快，国内友好)
    'staticfile', # Staticfile CDN
    'bootcdn',    # BootCDN
    'jsdelivr'    # jsDelivr (国外，作为最后备选)
]

# Bootstrap CDN 资源配置（多 CDN 备选）
BOOTSTRAP_RESOURCES = {
    'bootstrap.bundle.min.js': {
        'urls': {
            'zstatic': 'https://s4.zstatic.net/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js',
            'staticfile': 'https://cdn.staticfile.net/bootstrap/5.3.0/js/bootstrap.bundle.min.js',
            'bootcdn': 'https://cdn.bootcdn.net/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js',
            'jsdelivr': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'
        },
        'local_path': 'webui/static/vendor/bootstrap.bundle.min.js',
        'description': 'Bootstrap Bundle JS (包含 Popper)'
    },
    'bootstrap.min.css': {
        'urls': {
            'zstatic': 'https://s4.zstatic.net/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css',
            'staticfile': 'https://cdn.staticfile.net/bootstrap/5.3.0/css/bootstrap.min.css',
            'bootcdn': 'https://cdn.bootcdn.net/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css',
            'jsdelivr': 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css'
        },
        'local_path': 'webui/static/vendor/bootstrap.min.css',
        'description': 'Bootstrap CSS'
    }
}

# 下载超时配置（秒）
DOWNLOAD_TIMEOUT = 15  # 每个 CDN 尝试的超时时间
HASH_CHECK_TIMEOUT = 15  # 哈希检查的超时时间

def calculate_file_hash(file_path):
    """计算文件的 SHA256 哈希值"""
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"计算文件哈希失败: {file_path}, 错误: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'file': file_path,
            'error': str(e)
        })
        return None

def download_file(url, local_path, cdn_provider=None):
    """下载文件到本地路径"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        # 下载文件
        logger.info(f"开始下载: {url}", extra={'event_type': EventType.INFO, 'url': url, 'cdn_provider': cdn_provider})
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
        
        # 写入文件
        with open(local_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"下载完成: {local_path}", extra={
            'event_type': EventType.INFO,
            'file': local_path,
            'size': len(response.content),
            'cdn_provider': cdn_provider
        })
        return True
    except Exception as e:
        logger.error(f"下载文件失败: {url}, 错误: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'url': url,
            'error': str(e),
            'cdn_provider': cdn_provider
        })
        return False

def download_file_with_fallback(urls_dict, local_path, resource_name):
    """使用多 CDN 备选机制下载文件
    
    Args:
        urls_dict: CDN 提供商到 URL 的映射字典
        local_path: 本地文件路径
        resource_name: 资源名称（用于日志）
    
    Returns:
        tuple: (成功状态, 使用的 CDN 提供商)
    """
    # 确保目录存在
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    
    for cdn_provider in CDN_PROVIDERS:
        if cdn_provider not in urls_dict:
            continue
        
        url = urls_dict[cdn_provider]
        logger.info(f"尝试使用 {cdn_provider} CDN 下载 {resource_name}", extra={
            'event_type': EventType.INFO,
            'resource': resource_name,
            'cdn_provider': cdn_provider
        })
        
        try:
            response = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            
            # 写入文件
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"下载成功: {local_path} (使用 {cdn_provider} CDN)", extra={
                'event_type': EventType.INFO,
                'file': local_path,
                'size': len(response.content),
                'cdn_provider': cdn_provider
            })
            return True, cdn_provider
            
        except Exception as e:
            logger.warning(f"{cdn_provider} CDN 下载失败: {str(e)}", extra={
                'event_type': EventType.WARNING,
                'resource': resource_name,
                'cdn_provider': cdn_provider,
                'error': str(e)
            })
            # 继续尝试下一个 CDN
    
    # 所有 CDN 都失败了
    logger.error(f"所有 CDN 下载失败: {resource_name}", extra={
        'event_type': EventType.ERROR,
        'resource': resource_name
    })
    return False, None

def get_remote_file_hash(url, cdn_provider=None):
    """获取远程文件的哈希值"""
    try:
        response = requests.get(url, timeout=HASH_CHECK_TIMEOUT)
        response.raise_for_status()
        sha256_hash = hashlib.sha256()
        sha256_hash.update(response.content)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"获取远程文件哈希失败: {url}, 错误: {str(e)}", extra={
            'event_type': EventType.ERROR,
            'url': url,
            'error': str(e),
            'cdn_provider': cdn_provider
        })
        return None

def get_remote_file_hash_with_fallback(urls_dict, resource_name):
    """使用多 CDN 备选机制获取远程文件的哈希值
    
    Args:
        urls_dict: CDN 提供商到 URL 的映射字典
        resource_name: 资源名称（用于日志）
    
    Returns:
        tuple: (哈希值, 使用的 CDN 提供商)
    """
    for cdn_provider in CDN_PROVIDERS:
        if cdn_provider not in urls_dict:
            continue
        
        url = urls_dict[cdn_provider]
        logger.info(f"尝试使用 {cdn_provider} CDN 获取 {resource_name} 哈希", extra={
            'event_type': EventType.INFO,
            'resource': resource_name,
            'cdn_provider': cdn_provider
        })
        
        try:
            response = requests.get(url, timeout=HASH_CHECK_TIMEOUT)
            response.raise_for_status()
            sha256_hash = hashlib.sha256()
            sha256_hash.update(response.content)
            
            logger.info(f"成功获取哈希: {resource_name} (使用 {cdn_provider} CDN)", extra={
                'event_type': EventType.INFO,
                'resource': resource_name,
                'cdn_provider': cdn_provider
            })
            return sha256_hash.hexdigest(), cdn_provider
            
        except Exception as e:
            logger.warning(f"{cdn_provider} CDN 获取哈希失败: {str(e)}", extra={
                'event_type': EventType.WARNING,
                'resource': resource_name,
                'cdn_provider': cdn_provider,
                'error': str(e)
            })
            # 继续尝试下一个 CDN
    
    # 所有 CDN 都失败了
    logger.error(f"所有 CDN 获取哈希失败: {resource_name}", extra={
        'event_type': EventType.ERROR,
        'resource': resource_name
    })
    return None, None

def check_and_update_resources():
    """检查并更新所有前端资源"""
    logger.info("开始检查前端资源更新", extra={'event_type': EventType.INFO, 'action': 'check_updates'})
    
    updated_count = 0
    skipped_count = 0
    failed_count = 0
    
    for name, resource in BOOTSTRAP_RESOURCES.items():
        urls_dict = resource['urls']
        local_path = resource['local_path']
        description = resource['description']
        
        logger.info(f"检查 {description} ({name})", extra={
            'event_type': EventType.INFO,
            'resource': name,
            'description': description
        })
        
        # 获取本地文件哈希
        local_hash = None
        if os.path.exists(local_path):
            local_hash = calculate_file_hash(local_path)
            if local_hash:
                logger.info(f"本地文件哈希: {local_hash[:16]}...", extra={
                    'event_type': EventType.INFO,
                    'resource': name,
                    'hash': local_hash[:16]
                })
        
        # 获取远程文件哈希（使用多 CDN 备选）
        remote_hash, hash_cdn = get_remote_file_hash_with_fallback(urls_dict, name)
        if not remote_hash:
            logger.warning(f"无法获取远程文件哈希，跳过: {name}", extra={
                'event_type': EventType.WARNING,
                'resource': name
            })
            failed_count += 1
            continue
        
        logger.info(f"远程文件哈希: {remote_hash[:16]}... (来源: {hash_cdn})", extra={
            'event_type': EventType.INFO,
            'resource': name,
            'hash': remote_hash[:16],
            'cdn_provider': hash_cdn
        })
        
        # 比较哈希值
        if local_hash == remote_hash:
            logger.info(f"{description} 已是最新版本，无需更新", extra={
                'event_type': EventType.INFO,
                'resource': name,
                'status': 'up_to_date'
            })
            skipped_count += 1
        else:
            logger.info(f"{description} 有更新，开始下载", extra={
                'event_type': EventType.INFO,
                'resource': name,
                'status': 'update_available'
            })
            
            # 下载更新（使用多 CDN 备选）
            success, download_cdn = download_file_with_fallback(urls_dict, local_path, name)
            if success:
                updated_count += 1
                logger.info(f"{description} 更新成功 (来源: {download_cdn})", extra={
                    'event_type': EventType.INFO,
                    'resource': name,
                    'status': 'updated',
                    'cdn_provider': download_cdn
                })
            else:
                failed_count += 1
                logger.error(f"{description} 更新失败", extra={
                    'event_type': EventType.ERROR,
                    'resource': name,
                    'status': 'update_failed'
                })
    
    # 输出汇总信息
    summary = f"更新检查完成: 更新 {updated_count} 个, 跳过 {skipped_count} 个, 失败 {failed_count} 个"
    logger.info(summary, extra={
        'event_type': EventType.INFO,
        'action': 'update_check_complete',
        'updated': updated_count,
        'skipped': skipped_count,
        'failed': failed_count
    })
    
    return {
        'updated': updated_count,
        'skipped': skipped_count,
        'failed': failed_count
    }

def force_update_resources():
    """强制更新所有前端资源（不检查哈希）"""
    logger.info("开始强制更新所有前端资源", extra={'event_type': EventType.INFO, 'action': 'force_update'})
    
    updated_count = 0
    failed_count = 0
    
    for name, resource in BOOTSTRAP_RESOURCES.items():
        urls_dict = resource['urls']
        local_path = resource['local_path']
        description = resource['description']
        
        logger.info(f"强制更新 {description} ({name})", extra={
            'event_type': EventType.INFO,
            'resource': name,
            'description': description
        })
        
        success, cdn_provider = download_file_with_fallback(urls_dict, local_path, name)
        if success:
            updated_count += 1
            logger.info(f"{description} 强制更新成功 (来源: {cdn_provider})", extra={
                'event_type': EventType.INFO,
                'resource': name,
                'status': 'force_updated',
                'cdn_provider': cdn_provider
            })
        else:
            failed_count += 1
            logger.error(f"{description} 强制更新失败", extra={
                'event_type': EventType.ERROR,
                'resource': name,
                'status': 'force_update_failed'
            })
    
    summary = f"强制更新完成: 成功 {updated_count} 个, 失败 {failed_count} 个"
    logger.info(summary, extra={
        'event_type': EventType.INFO,
        'action': 'force_update_complete',
        'updated': updated_count,
        'failed': failed_count
    })
    
    return {
        'updated': updated_count,
        'failed': failed_count
    }

if __name__ == "__main__":
    from datetime import datetime
    print("=" * 60)
    print("前端资源更新检查工具")
    print("=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始检查更新...")
    
    result = check_and_update_resources()
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 更新检查完成")
    print(f"  - 更新: {result['updated']} 个")
    print(f"  - 跳过: {result['skipped']} 个")
    print(f"  - 失败: {result['failed']} 个")
    print("=" * 60)