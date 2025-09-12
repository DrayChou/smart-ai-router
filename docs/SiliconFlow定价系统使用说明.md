# SiliconFlow 定价系统使用说明

## 概述

已成功将 SiliconFlow 的定价信息从硬编码迁移到外部 JSON 配置文件，实现了数据与代码的分离，便于批量更新和维护。

## 文件结构

### 配置文件

- `config/pricing/siliconflow_pricing_from_html.json` - 从 HTML 解析的 SiliconFlow 真实模型数据
- `cache/siliconflow/model.html` - SiliconFlow 网页缓存数据（解析源）

### 脚本文件

- `scripts/parse_siliconflow_fixed.py` - HTML 解析脚本，从 SiliconFlow 网页数据提取真实模型信息
- `scripts/test_html_parsed_data.py` - 测试 HTML 解析数据的验证脚本

## 定价配置格式

### JSON 文件结构

```json
{
  "provider": "SiliconFlow",
  "currency": "CNY",
  "currency_symbol": "￥",
  "unit": "1M tokens",
  "exchange_rate_to_usd": 0.14,
  "last_updated": "2025-01-21",
  "pricing_source": "https://siliconflow.cn/pricing",
  "models": {
    "模型名称": {
      "input_price_per_m": 价格,
      "output_price_per_m": 价格,
      "context_length": 上下文长度,
      "capabilities": ["能力列表"],
      "category": "模型类别",
      "description": "模型描述"
    }
  },
  "categories": {
    "类别配置": {
      "name": "显示名称",
      "description": "类别描述"
    }
  }
}
```

### 模型类别

- `free` - 免费模型
- `pro` - Pro 版本
- `standard` - 标准收费
- `large` - 大模型
- `xlarge` - 超大模型
- `xxlarge` - 超超大模型
- `vision` - 视觉模型
- `premium` - 高端模型

### 模型能力

- `chat` - 对话
- `instruct` - 指令
- `code` - 代码
- `vision` - 视觉
- `reasoning` - 推理
- `thinking` - 思维
- `long_context` - 长上下文

## 使用方法

### 1. HTML 数据解析

从 SiliconFlow 网页缓存中提取真实模型数据：

```bash
python scripts/parse_siliconflow_fixed.py
```

功能：

- 从 HTML 缓存文件中提取真实模型元数据
- 包含准确的上下文长度、函数调用支持、视觉能力等
- 自动分类 127 个模型（vs 旧方法的 67 个）
- 生成详细统计报告

### 2. 数据验证测试

验证 HTML 解析数据的准确性：

```bash
python scripts/test_html_parsed_data.py
```

输出示例：

```
测试SiliconFlow定价数据加载...
成功从JSON加载 67 个模型定价
免费模型: 11 个
示例免费模型:
  1. THUDM/GLM-4.1V-9B-Thinking (免费)
  2. deepseek-ai/DeepSeek-R1-0528-Qwen3-8B (免费)
  3. THUDM/GLM-Z1-9B-0414 (免费)

Pro模型: 12 个
示例Pro模型:
  1. Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B - 输入:0.35 输出:0.35
  2. Pro/Qwen/Qwen2.5-Coder-7B-Instruct - 输入:0.35 输出:0.35
  3. Pro/Qwen/Qwen2.5-VL-7B-Instruct - 输入:0.35 输出:0.35

模型分类统计:
  free: 11 个
  large: 23 个
  premium: 7 个
  pro: 12 个
  standard: 2 个
  vision: 1 个
  xlarge: 6 个
  xxlarge: 5 个

JSON文件加载测试通过!
```

## 代码集成

### SiliconFlowAdapter 增强

适配器已更新支持外部 JSON 数据：

```python
from core.providers.adapters.siliconflow import SiliconFlowAdapter

# 初始化适配器
adapter = SiliconFlowAdapter()

# 获取特定模型定价
pricing = await adapter.get_model_pricing("Qwen/Qwen2.5-7B-Instruct")
print(pricing)
# 输出: {'prompt': '0.0', 'completion': '0.0', 'request': '0', ...}

# 清除定价缓存（强制重新加载）
adapter.clear_pricing_cache()

# 设置自定义JSON文件路径
from pathlib import Path
adapter.set_pricing_json_path(Path("custom/pricing/path.json"))
```

### 数据加载优先级

适配器使用以下优先级加载定价数据：

1. **API 模型发现** - 尝试从 SiliconFlow API 获取当前可用模型列表
2. **JSON 文件** - 从本地 HTML 解析的 JSON 配置文件获取模型详细信息
3. **回退处理** - 如果所有方法失败，返回空模型列表并记录错误日志

## 维护建议

### 定期更新

建议定期更新定价数据：

```bash
# 当SiliconFlow官网模型有更新时，重新获取HTML缓存数据
python scripts/parse_siliconflow_fixed.py
```

### 备份策略

- HTML 解析脚本会自动生成带时间戳的配置文件
- 配置文件路径：`config/pricing/siliconflow_pricing_from_html.json`
- 可手动备份重要的配置版本

### 数据验证

- 使用测试脚本验证数据完整性
- 检查免费模型列表是否正确
- 验证价格转换是否合理（人民币到美元）

## 故障排除

### 常见问题

1. **编码错误**

   ```
   UnicodeEncodeError: 'gbk' codec can't encode character
   ```

   解决方案：确保终端支持 UTF-8 编码或使用简化版本的输出。

2. **JSON 文件不存在**

   ```
   定价JSON文件不存在: config/pricing/siliconflow_pricing_from_html.json
   ```

   解决方案：运行 HTML 解析脚本生成 JSON 文件。

3. **HTML 解析失败**
   ```
   未能从HTML中提取JSON数据
   ```
   解决方案：检查 HTML 缓存文件是否存在，格式是否正确。

### 日志输出

所有脚本都提供详细的日志输出，便于问题诊断：

```
开始从HTML缓存中解析SiliconFlow模型数据...
成功提取JSON数据，长度: 1234567 字符
递归搜索找到模型数据数组，包含 127 个模型
成功解析 127 个模型的完整元数据
配置文件已保存到: config/pricing/siliconflow_pricing_from_html.json
```

## 扩展性

### 添加新模型

当 SiliconFlow 官网有新模型时，重新获取 HTML 缓存数据并运行解析脚本即可自动识别和添加。

### 自定义分类

可以在 JSON 文件中的`categories`部分添加新的模型分类。

### 支持其他 Provider

该架构可以轻松扩展支持其他 AI 提供商的定价管理。

## 总结

新的 SiliconFlow 定价系统提供了：

- ✅ **数据与代码分离** - 定价数据独立于代码维护
- ✅ **自动化更新** - 脚本化更新流程，减少人工错误
- ✅ **智能推断** - 自动推断模型属性和分类
- ✅ **向后兼容** - 完全兼容现有 API 接口
- ✅ **测试验证** - 完整的测试工具验证系统
- ✅ **备份保护** - 自动备份，防止数据丢失
- ✅ **扩展友好** - 易于添加新模型和功能

通过这个系统，SiliconFlow 的定价信息维护变得更加高效和可靠。
