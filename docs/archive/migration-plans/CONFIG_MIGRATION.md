# 配置管理统一化迁移指南

## 概述

根据架构优化报告，系统存在6种不同的配置方式导致管理混乱。现在统一使用单一的ConfigService进行配置管理。

## 新的配置架构

### 配置优先级（从高到低）
1. **环境变量** - 生产环境敏感信息
2. **config.yaml** - 主配置文件
3. **默认值** - 系统内置默认值

### 统一配置文件结构

```yaml
# config/config.yaml
system:
  log_level: INFO
  database_url: sqlite:///smart-ai-router.db
  
providers:
  openai:
    enabled: true
    channels:
      - name: main
        models: ["gpt-4o", "gpt-4o-mini"]
        priority: 10
  
  anthropic:
    enabled: true
    channels:
      - name: main
        models: ["claude-3-haiku", "claude-3-sonnet"]
        priority: 20

routing_strategies:
  default: balanced
  available: [cost_first, free_first, local_first, speed_optimized, quality_optimized, balanced]
```

## 迁移步骤

### 1. 移除旧的配置方式

**需要移除或重构的文件：**
- ❌ `core/config_loader.py` - JSON配置加载器
- ❌ `core/yaml_config.py` - 多套YAML配置
- ❌ 各种硬编码配置
- ✅ `core/services/config_service.py` - 新的统一配置

### 2. 环境变量标准化

```bash
# .env 文件只保留敏感信息
DATABASE_URL=sqlite:///smart-ai-router.db
LOG_LEVEL=INFO
JWT_SECRET=your-secret-key
```

### 3. 代码迁移示例

**之前的多种配置方式：**
```python
# ❌ 旧代码 - 多种配置源
from core.yaml_config import get_yaml_config_loader
from core.config_loader import load_json_config
import os

config_loader = get_yaml_config_loader()
yaml_config = config_loader.load_config()
json_config = load_json_config()
db_url = os.getenv('DATABASE_URL', 'sqlite:///default.db')
```

**新的统一配置方式：**
```python
# ✅ 新代码 - 统一配置服务
from core.services import get_config_service

config = get_config_service()
providers = config.get_providers()
db_url = config.get_database_url()  # 自动处理环境变量优先级
log_level = config.get_log_level()
```

### 4. 典型使用场景

**获取提供商配置：**
```python
config = get_config_service()

# 获取所有启用的提供商
enabled_providers = [
    name for name, cfg in config.get_providers().items()
    if cfg.get('enabled', False)
]

# 获取特定提供商的渠道
openai_channels = config.get_channels('openai')

# 检查提供商是否启用
is_enabled = config.is_provider_enabled('anthropic')
```

**配置验证：**
```python
config = get_config_service()

# 验证配置
errors = config.validate_config()
if errors:
    logger.error(f"配置错误: {errors}")

# 获取配置摘要
summary = config.get_config_summary()
logger.info(f"配置摘要: {summary}")
```

## 迁移清单

### ✅ 已完成
- [x] 创建统一的ConfigService
- [x] 定义配置优先级
- [x] 实现配置验证
- [x] 支持环境变量覆盖

### 📋 待迁移
- [ ] 更新现有代码使用新的ConfigService
- [ ] 移除旧的配置加载器
- [ ] 更新配置文件格式
- [ ] 编写配置迁移脚本

## 收益预期

- **配置源减少**: 6种 → 1种主要方式（+ 环境变量）
- **优先级明确**: 环境变量 > 配置文件 > 默认值
- **验证机制**: 启动时自动验证配置正确性
- **维护简化**: 单一配置文件，易于管理

## 注意事项

1. **向后兼容**: 保持现有API接口不变，内部使用新服务
2. **渐进迁移**: 可以逐步迁移，新旧系统并存
3. **测试覆盖**: 重点测试配置加载和验证逻辑
4. **文档更新**: 更新部署和配置文档

## 故障排查

**常见问题：**

1. **配置文件未找到**
   ```bash
   # 检查配置文件路径
   ls -la config/config.yaml
   ```

2. **配置验证失败**
   ```python
   from core.services import get_config_service
   config = get_config_service()
   errors = config.validate_config()
   print(errors)
   ```

3. **环境变量未生效**
   ```bash
   # 检查环境变量
   echo $DATABASE_URL
   echo $LOG_LEVEL
   ```