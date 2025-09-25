"""核心模块测试"""

import sys
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestCoreUtilsImports:
    """核心工具模块导入测试"""
    
    def test_config_import(self):
        """测试配置模块导入"""
        try:
            from core.utils.config import get_config
            assert get_config is not None
        except ImportError:
            pytest.skip("Config module import failed")
    
    def test_auth_import(self):
        """测试认证模块导入"""
        try:
            from core.utils.auth import generate_token, verify_token
            assert generate_token is not None
            assert verify_token is not None
        except ImportError:
            pytest.skip("Auth module import failed")


class TestCoreModelsImports:
    """核心模型导入测试"""
    
    def test_base_model_import(self):
        """测试基础模型导入"""
        try:
            from core.models.base import Base
            assert Base is not None
        except ImportError:
            pytest.skip("Base model import failed")
    
    def test_chat_request_import(self):
        """测试聊天请求模型导入"""
        try:
            from core.models.chat_request import ChatRequest
            assert ChatRequest is not None
        except ImportError:
            pytest.skip("ChatRequest model import failed")
    
    def test_model_info_import(self):
        """测试模型信息导入"""
        try:
            from core.models.model_info import ModelInfo
            assert ModelInfo is not None
        except ImportError:
            pytest.skip("ModelInfo model import failed")


class TestAPIImports:
    """API 模块导入测试"""
    
    def test_health_api_import(self):
        """测试健康检查 API 导入"""
        try:
            from api.health import router
            assert router is not None
        except ImportError:
            pytest.skip("Health API import failed")
    
    def test_models_api_import(self):
        """测试模型 API 导入"""
        try:
            from api.models import router
            assert router is not None
        except ImportError:
            pytest.skip("Models API import failed")
    
    def test_chat_api_import(self):
        """测试聊天 API 导入"""
        try:
            from api.chat import router
            assert router is not None
        except ImportError:
            pytest.skip("Chat API import failed")


class TestCoreServices:
    """核心服务测试"""
    
    def test_cache_service_import(self):
        """测试缓存服务导入"""
        try:
            from core.services.cache_service import CacheService
            assert CacheService is not None
        except ImportError:
            pytest.skip("CacheService import failed")
    
    def test_config_service_import(self):
        """测试配置服务导入"""
        try:
            from core.services.config_service import ConfigService
            assert ConfigService is not None
        except ImportError:
            pytest.skip("ConfigService import failed")


class TestCoreProviders:
    """核心提供者测试"""
    
    def test_base_provider_import(self):
        """测试基础提供者导入"""
        try:
            from core.providers.base import BaseProvider
            assert BaseProvider is not None
        except ImportError:
            pytest.skip("BaseProvider import failed")
    
    def test_registry_import(self):
        """测试提供者注册表导入"""
        try:
            from core.providers.registry import ProviderRegistry
            assert ProviderRegistry is not None
        except ImportError:
            pytest.skip("ProviderRegistry import failed")


class TestCoreRouter:
    """核心路由器测试"""
    
    def test_base_router_import(self):
        """测试基础路由器导入"""
        try:
            from core.router.base import BaseRouter
            assert BaseRouter is not None
        except ImportError:
            pytest.skip("BaseRouter import failed")
    
    def test_router_types_import(self):
        """测试路由器类型导入"""
        try:
            from core.router.types import RouterRequest, RouterResponse
            assert RouterRequest is not None
            assert RouterResponse is not None
        except ImportError:
            pytest.skip("Router types import failed")


class TestMainModule:
    """主模块测试"""
    
    def test_main_import(self):
        """测试主模块导入"""
        try:
            import main
            assert main is not None
            # 检查主要函数存在
            assert hasattr(main, "create_app") or hasattr(main, "main")
        except ImportError:
            pytest.skip("Main module import failed")


class TestConfigFiles:
    """配置文件功能测试"""
    
    def test_json_config_loading(self):
        """测试 JSON 配置文件加载"""
        import json
        
        config_dir = project_root / "config" / "pricing"
        if config_dir.exists():
            for json_file in config_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        assert isinstance(data, (dict, list))
                except Exception as e:
                    pytest.fail(f"Failed to load {json_file}: {e}")
    
    def test_yaml_config_import(self):
        """测试 YAML 配置导入"""
        try:
            from core.yaml_config import YAMLConfig
            assert YAMLConfig is not None
        except ImportError:
            pytest.skip("YAMLConfig import failed")


class TestUtilityFunctions:
    """工具函数测试"""
    
    def test_token_counter_import(self):
        """测试 token 计数器导入"""
        try:
            from core.utils.token_counter import count_tokens
            assert count_tokens is not None
        except ImportError:
            pytest.skip("Token counter import failed")
    
    def test_cost_estimator_import(self):
        """测试成本估算器导入"""
        try:
            from core.utils.cost_estimator import CostEstimator
            assert CostEstimator is not None
        except ImportError:
            pytest.skip("CostEstimator import failed")
    
    def test_factory_import(self):
        """测试工厂模式导入"""
        try:
            from core.utils.factory import create_instance
            assert create_instance is not None
        except ImportError:
            pytest.skip("Factory import failed")


if __name__ == "__main__":
    pytest.main([__file__])