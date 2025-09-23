"""配置管理模块"""

import os
from pathlib import Path
from typing import Any, Optional, Union

import yaml
from dotenv import load_dotenv


def load_config(config_path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径，默认为 config/config.yaml

    Returns:
        配置字典
    """
    # 加载环境变量
    load_dotenv()

    # 确定配置文件路径
    if config_path is None:
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "config.yaml"

        # 如果 config.yaml 不存在，尝试 example.yaml
        if not config_path.exists():
            config_path = project_root / "config" / "example.yaml"
            print(
                f"警告: 配置文件 config/config.yaml 不存在，使用示例配置 {config_path}"
            )

    # 读取配置文件
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件未找到: {config_path}") from None
    except yaml.YAMLError as e:
        raise ValueError(f"配置文件格式错误: {e}") from e

    # 环境变量替换
    config = _replace_env_vars(config)

    return config  # type: ignore[no-any-return]


def _replace_env_vars(obj: Any) -> Any:
    """
    递归替换配置中的环境变量占位符

    Args:
        obj: 配置对象

    Returns:
        替换后的配置对象
    """
    if isinstance(obj, dict):
        return {key: _replace_env_vars(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_replace_env_vars(item) for item in obj]
    elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        # 提取环境变量名 ${VAR_NAME} -> VAR_NAME
        env_var = obj[2:-1]
        default_value = None

        # 支持默认值 ${VAR_NAME:default_value}
        if ":" in env_var:
            env_var, default_value = env_var.split(":", 1)

        value = os.getenv(env_var, default_value)
        if value is None:
            print(f"⚠️  环境变量 {env_var} 未设置，使用占位符")
            return obj
        return value
    else:
        return obj


def get_config_value(config: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    获取嵌套配置值

    Args:
        config: 配置字典
        key_path: 配置路径，如 'server.host'
        default: 默认值

    Returns:
        配置值
    """
    keys = key_path.split(".")
    value = config

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value
