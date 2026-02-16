# -*- coding: utf-8 -*-
"""
测试图片服务管理器功能
"""
import sys
import time

# 添加项目根目录到路径
sys.path.insert(0, __file__.rsplit('\\', 1)[0])

from image_service_manager import get_image_service_manager
from logger import get_logger

logger = get_logger()

def test_image_service():
    """测试图片服务的启动和停止功能"""
    
    print("=" * 50)
    print("开始测试图片服务管理器")
    print("=" * 50)
    
    manager = get_image_service_manager()
    
    # 测试1: 检查初始状态
    print("\n[测试1] 检查初始状态")
    is_running = manager.is_running()
    print(f"服务运行状态: {'运行中' if is_running else '已停止'}")
    
    # 测试2: 启动服务
    print("\n[测试2] 启动图片服务")
    success = manager.start(wait_ready=True, timeout=60)
    print(f"启动结果: {'成功' if success else '失败'}")
    
    if success:
        # 测试3: 检查启动后的状态
        print("\n[测试3] 检查启动后的状态")
        is_running = manager.is_running()
        print(f"服务运行状态: {'运行中' if is_running else '已停止'}")
        
        pid = manager.get_pid()
        print(f"进程PID: {pid}")
        
        # 测试4: 健康检查
        print("\n[测试4] 执行健康检查")
        health = manager.health_check()
        print(f"健康状态: {health}")
        
        # 等待几秒
        print("\n等待5秒...")
        time.sleep(5)
        
        # 测试5: 停止服务
        print("\n[测试5] 停止图片服务")
        success = manager.stop()
        print(f"停止结果: {'成功' if success else '失败'}")
        
        # 测试6: 检查停止后的状态
        print("\n[测试6] 检查停止后的状态")
        is_running = manager.is_running()
        print(f"服务运行状态: {'运行中' if is_running else '已停止'}")
        
        # 测试7: 重复启动（应该跳过）
        print("\n[测试7] 重复启动（应该跳过）")
        success = manager.start(wait_ready=True, timeout=60)
        print(f"启动结果: {'成功' if success else '失败'}")
        
        # 测试8: 再次停止
        print("\n[测试8] 再次停止")
        success = manager.stop()
        print(f"停止结果: {'成功' if success else '失败'}")
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)

if __name__ == "__main__":
    try:
        test_image_service()
    except Exception as e:
        print(f"\n测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()