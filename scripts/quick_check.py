#!/usr/bin/env python3
"""
快速健康检查脚本
用于快速验证Smart AI Router的基本状态
"""

import sys
import json
import requests
import subprocess
from pathlib import Path

def check_config_file():
    """检查配置文件"""
    config_file = Path("config/router_config.yaml")
    if not config_file.exists():
        print("ERROR: 配置文件不存在: config/router_config.yaml")
        print("   解决方案: cp config/router_config.yaml.template config/router_config.yaml")
        return False
    
    print("OK: 配置文件存在")
    return True

def check_service_running():
    """检查服务是否运行"""
    try:
        response = requests.get("http://localhost:7601/health", timeout=5)
        if response.status_code == 200:
            print("OK: 服务正在运行")
            health_data = response.json()
            print(f"   状态: {health_data.get('status', 'unknown')}")
            return True
        else:
            print(f"ERROR: 服务响应错误: HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("ERROR: 服务未运行或端口7601不可达")
        print("   解决方案: python main.py")
        return False
    except Exception as e:
        print(f"ERROR: 服务检查失败: {e}")
        return False

def check_models_available():
    """检查模型是否可用"""
    try:
        response = requests.get("http://localhost:7601/v1/models", timeout=10)
        if response.status_code == 200:
            models_data = response.json()
            models = models_data.get('data', [])
            print(f"OK: 发现 {len(models)} 个可用模型")
            if models:
                print(f"   示例模型: {', '.join([m['id'] for m in models[:3]])}")
            return True
        else:
            print(f"ERROR: 模型列表获取失败: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"ERROR: 模型检查失败: {e}")
        return False

def check_dependencies():
    """检查关键依赖"""
    dependencies = ["fastapi", "httpx", "yaml", "pydantic"]
    all_ok = True
    
    for dep in dependencies:
        try:
            result = subprocess.run(
                [sys.executable, "-c", f"import {dep}"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"OK: {dep} 已安装")
            else:
                print(f"ERROR: {dep} 未安装")
                all_ok = False
        except Exception:
            print(f"ERROR: {dep} 检查失败")
            all_ok = False
    
    if not all_ok:
        print("   解决方案: uv sync")
    
    return all_ok

def test_simple_request():
    """测试简单请求"""
    try:
        response = requests.post(
            "http://localhost:7601/v1/chat/completions",
            json={
                "model": "tag:free",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 5
            },
            timeout=30
        )
        
        if response.status_code == 200:
            print("OK: 基本请求测试通过")
            return True
        else:
            print(f"ERROR: 请求测试失败: HTTP {response.status_code}")
            try:
                error_info = response.json()
                print(f"   错误: {error_info.get('detail', 'Unknown error')}")
            except:
                print(f"   响应: {response.text[:100]}")
            return False
    except requests.exceptions.Timeout:
        print("ERROR: 请求超时")
        print("   可能原因: 所有渠道不可用或网络问题")
        return False
    except Exception as e:
        print(f"ERROR: 请求测试失败: {e}")
        return False

def main():
    """主检查流程"""
    print("Smart AI Router Quick Health Check")
    print("=" * 40)
    
    checks = [
        ("配置文件", check_config_file),
        ("关键依赖", check_dependencies),
        ("服务状态", check_service_running),
        ("模型列表", check_models_available),
        ("基本请求", test_simple_request),
    ]
    
    passed = 0
    total = len(checks)
    
    for check_name, check_func in checks:
        print(f"\n>> 检查 {check_name}...")
        if check_func():
            passed += 1
        else:
            print("   提示: 查看 docs/TROUBLESHOOTING.md 获取详细解决方案")
    
    print("\n" + "=" * 40)
    print(f"检查结果: {passed}/{total} 项通过")
    
    if passed == total:
        print("SUCCESS: 系统状态良好！")
        return True
    elif passed >= total - 1:
        print("WARNING: 系统基本正常，有少量问题")
        return True
    else:
        print("ERROR: 发现多个问题，需要检修")
        print("提示: 运行 'python scripts/diagnostic_tool.py' 进行详细诊断")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)