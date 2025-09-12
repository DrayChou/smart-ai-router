# Smart AI Router - 测试套件

## 📋 测试目录结构

这个目录包含 Smart AI Router 项目的所有测试文件，包括功能测试、性能测试、API测试和调试工具。

## 🧪 测试文件分类

### 功能测试 (Feature Tests)
- `test_tag_routing_*.py` - 标签路由功能测试
- `test_anthropic_*.py` - Anthropic API集成测试
- `test_endpoint_*.py` - 端点直接测试
- `test_model_*.py` - 模型功能测试
- `test_new_features.py` - 新功能综合测试

### 性能测试 (Performance Tests)
- `test_tag_performance.py` - 标签路由性能测试
- `test_interval_control.py` - 间隔控制性能测试
- `test_cache.py` - 缓存系统测试

### API测试 (API Tests)
- `test_api_simulation.py` - API模拟测试
- `test_exact_format.py` - API格式验证测试
- `test_simple_endpoint.py` - 简单端点测试

### 调试工具 (Debug Tools)
- `debug_*.py` - 各种调试和问题排查工具
- `debug_anthropic.py` - Anthropic相关调试
- `debug_context_*.py` - 上下文处理调试
- `debug_config.py` - 配置系统调试

### 测试数据 (Test Data)
- `*test_results.json` - 测试结果数据
- `test_vision.json` - 视觉模型测试数据

## 🚀 运行测试

### 单个测试文件
```bash
# 运行特定测试
python tests/test_tag_routing_enhancement.py

# 运行调试脚本
python tests/debug_config.py
```

### 测试套件
```bash
# 如果安装了pytest
pytest tests/

# 运行特定类型测试
pytest tests/test_*.py
```

## 📊 测试覆盖范围

- ✅ 标签路由系统
- ✅ API端点功能
- ✅ 模型发现机制
- ✅ 缓存系统
- ✅ 性能监控
- ✅ 错误处理
- ✅ 配置系统

## 🔧 调试指南

1. **配置问题**: 使用 `debug_config.py`
2. **上下文问题**: 使用 `debug_context_*.py`
3. **标签问题**: 使用 `debug_tags.py`
4. **模型问题**: 使用 `debug_gemma_models.py`

## 💡 添加新测试

在添加新测试时，请遵循以下命名约定：
- 功能测试: `test_{feature_name}.py`
- 调试工具: `debug_{issue_name}.py`
- 测试数据: `{test_name}_results.json`

确保测试文件包含适当的文档和错误处理。