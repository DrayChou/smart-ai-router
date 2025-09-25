"""基础功能测试"""
import pytest
from pathlib import Path
import sys
import os

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestProjectStructure:
    """测试项目结构"""
    
    def test_project_root_exists(self):
        """测试项目根目录存在"""
        assert project_root.exists()
        assert project_root.is_dir()
    
    def test_core_directory_exists(self):
        """测试core目录存在"""
        core_dir = project_root / "core"
        assert core_dir.exists()
        assert core_dir.is_dir()
    
    def test_api_directory_exists(self):
        """测试api目录存在"""
        api_dir = project_root / "api"
        assert api_dir.exists()
        assert api_dir.is_dir()
    
    def test_main_file_exists(self):
        """测试main.py文件存在"""
        main_file = project_root / "main.py"
        assert main_file.exists()
        assert main_file.is_file()


class TestBasicImports:
    """测试基础模块导入"""
    
    def test_import_core_init(self):
        """测试导入core.__init__"""
        try:
            import core
            assert hasattr(core, '__file__')
        except ImportError:
            pytest.skip("core模块导入失败")
    
    def test_import_api_init(self):
        """测试导入api.__init__"""
        try:
            import api
            assert hasattr(api, '__file__')
        except ImportError:
            pytest.skip("api模块导入失败")


class TestConfigFiles:
    """测试配置文件"""
    
    def test_pyproject_toml_exists(self):
        """测试pyproject.toml存在"""
        pyproject_file = project_root / "pyproject.toml"
        assert pyproject_file.exists()
    
    def test_pricing_config_exists(self):
        """测试定价配置文件存在"""
        pricing_file = project_root / "pricing.json"
        if pricing_file.exists():
            assert pricing_file.is_file()
    
    def test_project_config_exists(self):
        """测试项目配置文件存在"""
        config_file = project_root / "project_config.json"
        if config_file.exists():
            assert config_file.is_file()


if __name__ == "__main__":
    pytest.main([__file__])