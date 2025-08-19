# Smart AI Router 故障排除检查清单

## 🚀 快速启动检查清单

遇到问题时，请按顺序执行以下检查：

### ⚡ 一分钟快速检查

```bash
# 1. 运行快速健康检查
python scripts/quick_check.py

# 2. 检查服务状态
curl http://localhost:7601/health

# 3. 查看最近错误
tail -20 logs/smart-ai-router.log | grep -i error
```

### 📋 详细诊断

如果快速检查发现问题，运行详细诊断：

```bash
# 运行完整诊断工具
python scripts/diagnostic_tool.py

# 查看特定类别的问题
python scripts/diagnostic_tool.py --category configuration
```

---

## 🔧 按问题类型排查

### 启动问题

| 症状 | 检查项目 | 解决方案 |
|------|----------|----------|
| 服务无法启动 | ☐ 配置文件是否存在 | `cp config/router_config.yaml.template config/router_config.yaml` |
| | ☐ 端口是否被占用 | `netstat -tulpn \| grep :7601` |
| | ☐ Python依赖是否完整 | `uv sync` |
| | ☐ 环境变量是否配置 | `cp .env.example .env` |

### 认证问题

| 症状 | 检查项目 | 解决方案 |
|------|----------|----------|
| 401/403错误 | ☐ API密钥是否有效 | 更新配置文件中的API密钥 |
| | ☐ 密钥格式是否正确 | 检查前缀：sk-, sk-ant- 等 |
| | ☐ 密钥权限是否足够 | 在Provider官网检查密钥权限 |

### 路由问题

| 症状 | 检查项目 | 解决方案 |
|------|----------|----------|
| No channels found | ☐ 渠道是否启用 | 检查 `enabled: true` |
| | ☐ 模型名称是否正确 | 运行 `curl localhost:7601/v1/models` |
| | ☐ 标签是否匹配 | 使用 `python scripts/debug_tag_matching.py` |
| All channels failed | ☐ 网络连接是否正常 | `ping api.openai.com` |
| | ☐ API密钥是否全部失效 | 逐个测试密钥 |

### 性能问题

| 症状 | 检查项目 | 解决方案 |
|------|----------|----------|
| 响应慢 | ☐ 网络延迟 | `ping api.openai.com` |
| | ☐ 系统资源 | `top`, `free -h` |
| | ☐ 日志中的慢请求 | `grep "LATENCY" logs/*.log` |
| 内存占用高 | ☐ 缓存大小 | 清理 `cache/` 目录 |
| | ☐ 日志文件大小 | 轮转或清理日志 |

---

## 🔍 常用调试命令

### 系统状态检查

```bash
# 服务健康检查
curl -s http://localhost:7601/health | jq

# 模型列表
curl -s http://localhost:7601/v1/models | jq '.data[].id'

# 可用标签
curl -s "http://localhost:7601/v1/models?format=tags" | jq

# 路由策略
curl -s http://localhost:7601/admin/routing/strategy
```

### 配置验证

```bash
# YAML语法检查
python -c "import yaml; yaml.safe_load(open('config/router_config.yaml'))"

# 配置加载测试
python -c "from core.yaml_config import get_yaml_config_loader; config = get_yaml_config_loader(); print(f'Loaded {len(config.config.channels)} channels')"

# 渠道状态统计
python -c "
from core.yaml_config import get_yaml_config_loader
config = get_yaml_config_loader()
enabled = [ch for ch in config.config.channels if ch.enabled]
print(f'Total: {len(config.config.channels)}, Enabled: {len(enabled)}')
"
```

### 网络诊断

```bash
# API端点连通性
curl -I https://api.openai.com/v1/models
curl -I https://api.anthropic.com/v1/messages
curl -I https://api.siliconflow.cn/v1/models

# DNS解析
nslookup api.openai.com
dig api.openai.com

# 网络延迟测试
ping -c 4 api.openai.com
traceroute api.openai.com
```

### 日志分析

```bash
# 查看实时日志
tail -f logs/smart-ai-router.log

# 错误统计
grep -i error logs/smart-ai-router.log | wc -l

# 最近10分钟的错误
grep -i error logs/smart-ai-router.log | grep "$(date -d '10 minutes ago' '+%H:%M')"

# 按错误类型统计
grep -i "exception\|error" logs/smart-ai-router.log | awk '{print $4}' | sort | uniq -c | sort -nr

# 性能分析
grep "LATENCY" logs/smart-ai-router.log | awk '{sum+=$NF; count++} END {print "Avg:", sum/count, "ms"}'
```

---

## 🆘 紧急恢复程序

### 服务完全无法启动

1. **检查基础环境**
   ```bash
   python --version  # 应该是 3.8+
   which python
   ls -la config/router_config.yaml
   ```

2. **重置配置**
   ```bash
   cp config/router_config.yaml.template config/router_config.yaml
   cp .env.example .env
   ```

3. **重新安装依赖**
   ```bash
   rm -rf .venv/
   uv sync
   ```

4. **清理缓存**
   ```bash
   rm -rf cache/*
   rm -rf logs/*
   ```

5. **最小配置启动**
   ```bash
   # 使用最简配置文件
   python -c "
   import yaml
   config = {
       'system': {'name': 'smart-ai-router', 'version': '1.0.0'},
       'server': {'host': '0.0.0.0', 'port': 7601, 'debug': True},
       'providers': {},
       'channels': [],
       'routing': {'default_strategy': 'balanced'},
       'tasks': {'model_discovery': {'enabled': False}}
   }
   with open('config/router_config.yaml', 'w') as f:
       yaml.dump(config, f)
   "
   python main.py
   ```

### 所有API请求失败

1. **检查API密钥**
   ```bash
   # 测试OpenAI密钥
   curl -H "Authorization: Bearer YOUR_KEY" https://api.openai.com/v1/models
   
   # 测试Anthropic密钥  
   curl -H "x-api-key: YOUR_KEY" https://api.anthropic.com/v1/messages
   ```

2. **检查网络连接**
   ```bash
   curl -I https://www.google.com
   ping 8.8.8.8
   ```

3. **使用测试模式**
   ```bash
   # 启用调试模式
   export LOG_LEVEL=DEBUG
   python main.py
   ```

4. **单渠道测试**
   ```bash
   # 禁用所有渠道，只启用一个进行测试
   python scripts/debug_routing.py --channel openai_main
   ```

### Docker部署问题

1. **重建容器**
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

2. **检查容器日志**
   ```bash
   docker-compose logs smart-ai-router
   ```

3. **进入容器调试**
   ```bash
   docker exec -it smart-ai-router bash
   cd /app
   python scripts/quick_check.py
   ```

4. **检查挂载和权限**
   ```bash
   docker exec smart-ai-router ls -la /app/config/
   docker exec smart-ai-router cat /app/config/router_config.yaml
   ```

---

## 📞 获取更多帮助

### 自助诊断工具

| 工具 | 用途 | 命令 |
|------|------|------|
| 快速检查 | 基本状态验证 | `python scripts/quick_check.py` |
| 详细诊断 | 完整系统诊断 | `python scripts/diagnostic_tool.py` |
| 路由调试 | 路由逻辑测试 | `python scripts/debug_routing.py` |
| 标签调试 | 标签匹配测试 | `python scripts/debug_tag_matching.py` |

### 信息收集

在寻求帮助时，请提供以下信息：

```bash
# 系统信息
python --version
uv --version
docker --version

# 诊断报告  
python scripts/diagnostic_tool.py --output diagnostic_report.json

# 最近日志
tail -50 logs/smart-ai-router.log

# 配置摘要（隐藏敏感信息）
grep -v "api_key\|secret" config/router_config.yaml
```

### 问题报告模板

```markdown
## 问题描述
[简要描述遇到的问题]

## 环境信息
- OS: [Windows/Linux/macOS]
- Python版本: [python --version]
- 部署方式: [直接运行/Docker]

## 重现步骤
1. [第一步]
2. [第二步]
3. [第三步]

## 期望结果
[描述期望的正常行为]

## 实际结果
[描述实际发生的情况]

## 诊断信息
```bash
# 快速检查结果
python scripts/quick_check.py

# 错误日志
tail -20 logs/smart-ai-router.log | grep -i error
```

## 其他尝试
[列出已经尝试的解决方案]
```

---

## 🎯 预防措施

### 定期维护

- ☐ 每周检查API密钥有效性
- ☐ 每月清理日志文件
- ☐ 每月更新依赖包
- ☐ 定期备份配置文件

### 监控建议

- ☐ 设置健康检查监控 (`/health`)
- ☐ 监控错误率和响应时间
- ☐ 设置磁盘空间告警
- ☐ 监控API密钥配额使用

### 最佳实践

- ☐ 使用版本控制管理配置变更
- ☐ 定期测试故障转移
- ☐ 保持多个Provider的API密钥
- ☐ 使用负载均衡分散风险

---

*此检查清单会根据常见问题持续更新。如有问题或建议，请提交Issue。*