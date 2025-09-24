"""配置系统测试"""

import pytest
import json
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestConfigFiles:
    """配置文件测试"""
    
    def test_pricing_config_files(self):
        """测试定价配置文件"""
        config_dir = project_root / "config" / "pricing"
        assert config_dir.exists()
        
        # 检查定价配置文件
        pricing_files = [
            "base_pricing_unified.json",
            "doubao_unified.json", 
            "openrouter_unified.json",
            "siliconflow_unified.json"
        ]
        
        for file_name in pricing_files:
            file_path = config_dir / file_name
            assert file_path.exists(), f"Missing pricing file: {file_name}"
            
            # 验证 JSON 格式
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in {file_name}: {e}")
    
    def test_test_config_files(self):
        """测试测试配置文件"""
        tests_dir = project_root / "tests"
        
        # 检查测试配置文件
        test_configs = [
            "test_negative_local_only.json",
            "test_negative_tags.json",
            "test_vision.json"
        ]
        
        for file_name in test_configs:
            file_path = tests_dir / file_name
            assert file_path.exists(), f"Missing test config: {file_name}"
            
            # 验证 JSON 格式
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON in {file_name}: {e}")


class TestProjectConfig:
    """项目配置测试"""
    
    def test_pyproject_toml(self):
        """测试 pyproject.toml 配置"""
        pyproject_path = project_root / "pyproject.toml"
        assert pyproject_path.exists()
        
        # 读取并基本验证
        content = pyproject_path.read_text(encoding='utf-8')
        assert '[project]' in content
        assert 'name = "smart-ai-router"' in content
        assert '[tool.pytest.ini_options]' in content
    
    def test_requirements_txt(self):
        """测试 requirements.txt"""
        req_path = project_root / "requirements.txt"
        assert req_path.exists()
        
        content = req_path.read_text(encoding='utf-8')
        assert len(content.strip()) > 0
    
    def test_docker_files(self):
        """测试 Docker 配置文件"""
        dockerfile = project_root / "Dockerfile"
        docker_compose = project_root / "docker-compose.yml"
        
        assert dockerfile.exists()
        assert docker_compose.exists()


if __name__ == "__main__":
    pytest.main([__file__])