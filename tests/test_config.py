"""配置系统测试"""
import json
import sys
from pathlib import Path

import pytest

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestConfigSystem:
    """测试配置系统"""
    
    def test_pyproject_toml_content(self):
        """测试pyproject.toml内容"""
        pyproject_file = project_root / "pyproject.toml"
        if pyproject_file.exists():
            content = pyproject_file.read_text(encoding='utf-8')
            assert '[tool.pytest.ini_options]' in content or 'pytest' in content
    
    def test_pricing_json_format(self):
        """测试pricing.json格式"""
        pricing_file = project_root / "pricing.json"
        if pricing_file.exists():
            try:
                with open(pricing_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                assert isinstance(data, dict)
            except json.JSONDecodeError:
                pytest.fail("pricing.json格式错误")
    
    def test_project_config_json_format(self):
        """测试project_config.json格式"""
        config_file = project_root / "project_config.json"
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                assert isinstance(data, dict)
            except json.JSONDecodeError:
                pytest.fail("project_config.json格式错误")


class TestEnvironment:
    """测试环境配置"""
    
    def test_python_version(self):
        """测试Python版本"""
        import sys
        assert sys.version_info >= (3, 8)
    
    def test_pytest_available(self):
        """测试pytest可用"""
        try:
            import pytest
            assert hasattr(pytest, 'main')
        except ImportError:
            pytest.fail("pytest不可用")
    
    def test_project_in_path(self):
        """测试项目路径配置"""
        assert str(project_root) in sys.path or str(project_root.absolute()) in sys.path


if __name__ == "__main__":
    pytest.main([__file__])