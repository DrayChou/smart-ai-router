# 💰 成本监控系统使用指南

Smart AI Router 的成本监控系统提供全面的使用跟踪、成本记录和渠道监控功能，帮助你优化AI API的使用成本。

## 📋 功能概览

### 1. 使用记录收集
- ✅ **自动记录**: 每次API调用自动记录到JSONL文件
- ✅ **详细信息**: 包含模型、渠道、tokens、成本、响应时间等
- ✅ **标签系统**: 自动提取和记录请求标签
- ✅ **错误跟踪**: 记录失败请求和错误信息

### 2. 渠道监控告警  
- 🚨 **配额用完提醒**: 自动检测并通知渠道配额耗尽
- 🚨 **余额不足告警**: 监控余额并发送低余额提醒
- 🚨 **API密钥失效**: 检测无效密钥并发送告警
- 🚨 **错误频率监控**: 监控渠道错误率并告警

### 3. 统计分析API
- 📊 **多维度统计**: 按日、周、月查看使用统计
- 📊 **成本分析**: 按模型、渠道、提供商的成本分解
- 📊 **热门排行**: 使用最多的模型和渠道排行
- 📊 **趋势分析**: 使用趋势和成本变化分析

## 🚀 快速开始

### 自动记录使用情况

成本监控系统已集成到Smart AI Router中，每次API调用都会自动记录：

```bash
# 启动系统
python main.py

# 使用任何API接口，系统会自动记录
curl -X POST http://localhost:7601/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tag:free",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### 查看使用统计

```bash
# 查看今日统计
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/daily

# 查看本周统计  
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/weekly

# 查看本月统计
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/monthly

# 查看使用汇总
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/summary
```

### 查看渠道告警

```bash
# 查看最近24小时的告警
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/alerts

# 查看渠道状态
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/channel-status

# 清除特定渠道的告警状态
curl -X POST -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  http://localhost:7601/v1/stats/clear-alerts/ch_openai_001
```

## 📁 数据存储

### 使用记录文件 (JSONL格式)

位置: `logs/usage_YYYYMMDD.jsonl`

每行记录包含：
```json
{
  "timestamp": "2025-08-24T12:30:45Z",
  "request_id": "req_abc123", 
  "model": "gpt-4o-mini",
  "channel_id": "ch_openai_001",
  "channel_name": "OpenAI Official",
  "provider": "openai",
  "input_tokens": 150,
  "output_tokens": 300,
  "total_tokens": 450,
  "input_cost": 0.000075,
  "output_cost": 0.0003,
  "total_cost": 0.000375,
  "cost_currency": "USD",
  "request_type": "chat",
  "status": "success",
  "response_time_ms": 1250,
  "tags": ["gpt", "4o", "mini", "chat"]
}
```

### 渠道告警文件 (JSONL格式)

位置: `logs/channel_alerts.jsonl`

```json
{
  "channel_id": "ch_openai_001",
  "channel_name": "OpenAI Official", 
  "alert_type": "quota_exhausted",
  "message": "渠道 OpenAI Official 配额已用完",
  "timestamp": "2025-08-24T12:30:45Z",
  "details": {"remaining_requests": 0, "reset_time": "2025-08-25T00:00:00Z"}
}
```

## 🔧 管理命令

### 日志归档

```bash
# 归档30天前的日志 (默认)
python scripts/archive_usage_logs.py --archive

# 归档7天前的日志
python scripts/archive_usage_logs.py --archive --days-to-keep 7

# 生成统计报告
python scripts/archive_usage_logs.py --report

# 生成指定日期的报告
python scripts/archive_usage_logs.py --report --date 2025-08-20
```

### 查看实时统计

```bash
# 运行示例脚本查看功能演示
python examples/cost_tracking_example.py
```

## 📊 API接口详细说明

### 统计查询接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/v1/stats/daily` | GET | 获取每日使用统计 |
| `/v1/stats/weekly` | GET | 获取本周使用统计 |
| `/v1/stats/monthly` | GET | 获取月度使用统计 |
| `/v1/stats/summary` | GET | 获取使用情况汇总 |
| `/v1/stats/top-models` | GET | 获取热门模型排行 |
| `/v1/stats/top-channels` | GET | 获取热门渠道排行 |
| `/v1/stats/cost-breakdown` | GET | 获取成本分解分析 |

### 告警管理接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/v1/stats/alerts` | GET | 获取渠道告警信息 |
| `/v1/stats/channel-status` | GET | 获取渠道状态概览 |
| `/v1/stats/clear-alerts/{channel_id}` | POST | 清除指定渠道告警 |
| `/v1/stats/clear-all-alerts` | POST | 清除所有渠道告警 |

### 查询参数

大部分接口支持以下查询参数：
- `target_date`: 目标日期 (YYYY-MM-DD格式)
- `period`: 统计周期 (daily/weekly/monthly)
- `limit`: 返回数量限制
- `hours`: 查询时间范围 (小时数)

## 🎯 使用场景

### 1. 成本优化

```bash
# 查看最昂贵的模型
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "http://localhost:7601/v1/stats/cost-breakdown?breakdown_by=model&period=monthly"

# 查看最昂贵的渠道
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "http://localhost:7601/v1/stats/cost-breakdown?breakdown_by=channel&period=monthly"
```

### 2. 异常监控

```bash
# 检查最近的告警
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "http://localhost:7601/v1/stats/alerts?hours=24"

# 查看失败率较高的渠道
# (通过每日统计的成功/失败比率判断)
```

### 3. 趋势分析

```bash
# 对比不同时间段的使用情况
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "http://localhost:7601/v1/stats/daily?target_date=2025-08-20"
  
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "http://localhost:7601/v1/stats/daily?target_date=2025-08-24"
```

## ⚠️ 注意事项

1. **存储空间**: JSONL文件会随时间增长，定期运行归档命令
2. **权限认证**: 统计API需要admin token认证
3. **数据保留**: 默认保留30天的详细日志，可通过归档脚本调整
4. **性能影响**: 使用记录是异步写入，对API响应时间影响微乎其微

## 🔮 扩展功能

你可以通过修改以下文件来扩展功能：

- `core/utils/usage_tracker.py`: 使用记录逻辑
- `core/utils/channel_monitor.py`: 渠道监控逻辑  
- `api/usage_stats.py`: 统计API接口
- `scripts/archive_usage_logs.py`: 归档和报告脚本

### 自定义告警方式

修改 `ChannelMonitor._send_alert()` 方法可以添加：
- 邮件通知
- Webhook推送
- 消息队列
- 第三方监控系统集成

### 自定义统计维度

修改 `UsageTracker` 类可以添加：
- 用户级别统计
- 地理位置统计
- 自定义标签统计
- 更复杂的聚合分析

这个成本监控系统为你的Smart AI Router提供了全面的使用透明度和成本控制能力! 🎉