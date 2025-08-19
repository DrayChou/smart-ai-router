# Smart AI Router 故障排除指南

## 目录

- [常见问题快速诊断](#常见问题快速诊断)
- [启动和配置问题](#启动和配置问题)
- [API密钥和认证问题](#api密钥和认证问题)
- [路由和渠道问题](#路由和渠道问题)
- [性能和连接问题](#性能和连接问题)
- [Docker和部署问题](#docker和部署问题)
- [日志分析指南](#日志分析指南)
- [高级调试技巧](#高级调试技巧)
- [常见错误码解释](#常见错误码解释)

---

## 常见问题快速诊断

### 🔍 问题诊断检查清单

在深入具体问题之前，请按顺序检查以下项目：

1. **服务状态检查**
   ```bash
   curl http://localhost:7601/health
   ```

2. **配置文件检查**
   ```bash
   # 确认配置文件存在
   ls -la config/router_config.yaml
   
   # 检查配置文件语法
   python -c "import yaml; yaml.safe_load(open('config/router_config.yaml'))"
   ```

3. **日志文件检查**
   ```bash
   # 查看最新日志
   tail -f logs/smart-ai-router.log
   
   # 查找错误信息
   grep -i "error\|exception\|failed" logs/smart-ai-router.log | tail -20
   ```

4. **依赖环境检查**
   ```bash
   # 检查Python环境
   python --version
   
   # 检查依赖安装
   uv sync --check
   ```

---

## 启动和配置问题

### ❌ 应用启动失败

#### 症状：
- 服务无法启动
- 端口占用错误
- 配置文件错误

#### 解决方案：

**1. 配置文件不存在**
```bash
# 错误信息示例
[ERROR] Configuration file 'config/router_config.yaml' not found.

# 解决方法
cp config/router_config.yaml.template config/router_config.yaml
# 然后编辑配置文件
```

**2. 端口已被占用**
```bash
# 错误信息示例
OSError: [Errno 98] Address already in use

# 查找占用端口的进程
netstat -tulpn | grep :7601
# 或者
lsof -i :7601

# 终止占用进程
kill -9 <PID>

# 或者修改配置文件使用其他端口
```

**3. 环境变量缺失**
```bash
# 检查必需的环境变量
echo $JWT_SECRET
echo $WEB_SECRET_KEY

# 如果缺失，复制环境变量模板
cp .env.example .env
# 然后编辑 .env 文件
```

**4. Python依赖问题**
```bash
# 重新安装依赖
uv sync --reinstall

# 如果使用Docker
docker-compose build --no-cache
```

### ⚙️ 配置文件语法错误

#### 常见YAML语法问题：

**1. 缩进错误**
```yaml
# ❌ 错误：缩进不一致
providers:
openai:
  name: "OpenAI"
    adapter_class: "OpenAIAdapter"

# ✅ 正确：使用一致的2空格缩进
providers:
  openai:
    name: "OpenAI"
    adapter_class: "OpenAIAdapter"
```

**2. 引号使用错误**
```yaml
# ❌ 错误：包含特殊字符但未加引号
api_key: sk-1234:abcd

# ✅ 正确：包含特殊字符时使用引号
api_key: "sk-1234:abcd"
```

**3. 列表格式错误**
```yaml
# ❌ 错误：列表格式不正确
channels:
- id: "openai_1"
  enabled: true
- id: "anthropic_1"
enabled: true

# ✅ 正确：保持一致的缩进
channels:
  - id: "openai_1"
    enabled: true
  - id: "anthropic_1"
    enabled: true
```

#### 配置验证工具：
```bash
# 验证YAML语法
python -c "
import yaml
try:
    with open('config/router_config.yaml') as f:
        yaml.safe_load(f)
    print('配置文件语法正确')
except yaml.YAMLError as e:
    print(f'YAML语法错误: {e}')
"

# 使用内置配置检查
python -c "
from core.yaml_config import get_yaml_config_loader
try:
    config = get_yaml_config_loader()
    print('配置加载成功')
    print(f'发现 {len(config.config.providers)} 个提供商')
    print(f'发现 {len(config.config.channels)} 个渠道')
except Exception as e:
    print(f'配置加载失败: {e}')
"
```

---

## API密钥和认证问题

### 🔑 API密钥验证失败

#### 症状：
- 401 Unauthorized 错误
- 403 Forbidden 错误
- "Authentication failed" 消息

#### 诊断步骤：

**1. 检查API密钥格式**
```bash
# OpenAI密钥格式：sk-...
# Anthropic密钥格式：sk-ant-...
# 检查密钥是否完整且无额外空格
```

**2. 测试API密钥有效性**
```bash
# 测试OpenAI密钥
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://api.openai.com/v1/models

# 测试Anthropic密钥
curl -H "x-api-key: YOUR_API_KEY" \
     https://api.anthropic.com/v1/messages

# 测试SiliconFlow密钥
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://api.siliconflow.cn/v1/models
```

**3. 检查密钥配置**
```python
# 检查密钥是否正确加载
python -c "
from core.yaml_config import get_yaml_config_loader
config = get_yaml_config_loader()
for channel in config.config.channels:
    if channel.enabled:
        print(f'渠道 {channel.id}: 密钥长度 {len(channel.api_key if channel.api_key else \"\")}')
"
```

#### 解决方案：

**1. 更新过期的API密钥**
```yaml
# 在配置文件中更新密钥
channels:
  - id: "openai_main"
    api_key: "sk-新的有效密钥"
```

**2. 检查密钥权限**
- 确保API密钥有足够的权限访问所需的模型
- 检查密钥是否有使用限制或配额限制

**3. 环境变量配置**
```bash
# 如果使用环境变量
export OPENAI_API_KEY="sk-your-key-here"
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

### 🔒 路由器认证问题

#### 症状：
- 无法访问管理接口
- Token验证失败

#### 解决方案：

**1. 检查认证配置**
```yaml
# 在router_config.yaml中检查auth配置
auth:
  enabled: true
  api_token: "your-admin-token"
```

**2. 重新生成认证令牌**
```python
# 生成新的认证令牌
from core.auth import generate_secure_token
new_token = generate_secure_token()
print(f"新的认证令牌: {new_token}")
```

**3. 使用正确的认证头**
```bash
# 正确的API调用方式
curl -H "Authorization: Bearer your-admin-token" \
     http://localhost:7601/admin/channels
```

---

## 路由和渠道问题

### 🛣️ 路由失败问题

#### 症状：
- "No channels found" 错误
- "All channels failed" 错误
- 模型不可用

#### 诊断步骤：

**1. 检查模型可用性**
```bash
# 查看系统发现的模型
curl http://localhost:7601/v1/models

# 检查特定标签的模型
curl "http://localhost:7601/v1/models?tag=free"
```

**2. 检查渠道状态**
```python
# 运行渠道健康检查
python -c "
import asyncio
from core.scheduler.tasks.service_health_check import get_health_check_task
async def check():
    task = get_health_check_task()
    await task.run()
asyncio.run(check())
"
```

**3. 检查路由配置**
```python
# 测试路由逻辑
python scripts/debug_routing.py --model "gpt-3.5-turbo"
```

#### 常见问题和解决方案：

**1. 没有可用渠道**
```bash
# 症状：NoChannelsFoundException
# 原因：
# - 所有渠道都被禁用
# - 模型名称不匹配
# - 标签匹配失败

# 解决方法：
# 1. 检查渠道启用状态
python -c "
from core.yaml_config import get_yaml_config_loader
config = get_yaml_config_loader()
enabled_channels = [ch for ch in config.config.channels if ch.enabled]
print(f'启用的渠道数量: {len(enabled_channels)}')
for ch in enabled_channels[:5]:
    print(f'- {ch.id}: {ch.model_name}')
"

# 2. 检查模型发现状态
python scripts/run_model_discovery.py
```

**2. 所有渠道都失败**
```bash
# 症状：AllChannelsFailedException
# 原因：
# - API密钥都无效
# - 网络连接问题
# - 服务器错误

# 解决方法：
# 1. 逐个测试渠道
python -c "
import asyncio
from core.utils.api_key_validator import get_api_key_validator
async def test_keys():
    validator = get_api_key_validator()
    # 测试所有启用的渠道
    # ... (详细测试代码)
asyncio.run(test_keys())
"

# 2. 检查网络连接
curl -I https://api.openai.com/v1/models
curl -I https://api.anthropic.com/v1/messages
```

**3. 标签匹配问题**
```python
# 测试标签匹配
python scripts/debug_tag_matching.py --tag "free" --verbose

# 查看所有可用标签
python -c "
from core.json_router import JSONRouter
from core.yaml_config import get_yaml_config_loader
config = get_yaml_config_loader()
router = JSONRouter(config)
tags = router.get_all_available_tags()
print('可用标签:', sorted(tags))
"
```

### 📊 路由策略问题

#### 症状：
- 选择了昂贵的渠道而不是免费的
- 路由决策不符合预期
- 性能不佳的渠道被选中

#### 解决方案：

**1. 检查路由策略配置**
```bash
# 查看当前路由策略
curl http://localhost:7601/admin/routing/strategy

# 更改路由策略
curl -X POST http://localhost:7601/admin/routing/strategy \
     -H "Content-Type: application/json" \
     -d '{"strategy": "free_first"}'
```

**2. 分析路由决策**
```python
# 详细路由分析
python scripts/analyze_routing_strategy.py \
       --model "tag:free" \
       --strategy "cost_first" \
       --verbose
```

**3. 优化路由权重**
```yaml
# 在配置文件中调整渠道权重
channels:
  - id: "free_channel"
    priority: 1      # 高优先级
    cost_score: 10   # 低成本
    speed_score: 8   # 高速度
```

---

## 性能和连接问题

### 🐌 响应速度慢

#### 症状：
- 请求超时
- 响应时间过长
- 高延迟

#### 诊断步骤：

**1. 检查网络延迟**
```bash
# 测试到主要Provider的延迟
ping api.openai.com
ping api.anthropic.com
ping api.siliconflow.cn

# 测试HTTPS连接时间
curl -w "@curl-format.txt" -o /dev/null -s https://api.openai.com/v1/models
```

创建`curl-format.txt`文件：
```
     time_namelookup:  %{time_namelookup}s\n
        time_connect:  %{time_connect}s\n
     time_appconnect:  %{time_appconnect}s\n
    time_pretransfer:  %{time_pretransfer}s\n
       time_redirect:  %{time_redirect}s\n
  time_starttransfer:  %{time_starttransfer}s\n
                     ----------\n
          time_total:  %{time_total}s\n
```

**2. 检查系统资源**
```bash
# CPU和内存使用情况
top -p $(pgrep -f "python.*main.py")

# 磁盘I/O
iostat -x 1 5

# 网络连接
netstat -tuln | grep :7601
```

**3. 分析日志性能**
```bash
# 查找慢请求
grep "LATENCY" logs/smart-ai-router.log | awk '$NF > 5000' | tail -10

# 统计平均响应时间
grep "LATENCY" logs/smart-ai-router.log | awk '{sum+=$NF; count++} END {print "平均延迟:", sum/count, "ms"}'
```

#### 性能优化方案：

**1. 启用缓存**
```python
# 检查缓存状态
python -c "
from core.utils.smart_cache import get_smart_cache
cache = get_smart_cache()
stats = cache.get_stats()
print('缓存统计:', stats)
"
```

**2. 调整连接池**
```yaml
# 在配置中增加连接池设置
providers:
  openai:
    connection_pool_size: 20
    connection_timeout: 30
```

**3. 启用压缩**
```yaml
# 启用响应压缩
server:
  enable_compression: true
  compression_level: 6
```

### 🔌 连接问题

#### 症状：
- Connection timeout
- Connection refused
- SSL/TLS 错误

#### 解决方案：

**1. DNS解析问题**
```bash
# 检查DNS解析
nslookup api.openai.com
dig api.openai.com

# 尝试使用不同的DNS
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
```

**2. 防火墙问题**
```bash
# 检查出站连接
telnet api.openai.com 443
telnet api.anthropic.com 443

# 检查防火墙规则
iptables -L OUTPUT
ufw status
```

**3. 代理配置**
```bash
# 如果使用代理
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080

# 或在配置文件中设置
```

---

## Docker和部署问题

### 🐳 Docker部署问题

#### 症状：
- 容器启动失败
- 服务不可访问
- 配置文件挂载问题

#### 解决方案：

**1. 容器日志检查**
```bash
# 查看容器日志
docker-compose logs smart-ai-router

# 实时查看日志
docker-compose logs -f smart-ai-router

# 检查容器状态
docker-compose ps
```

**2. 网络连接问题**
```bash
# 检查端口映射
docker port smart-ai-router

# 测试容器内网络
docker exec smart-ai-router curl localhost:7601/health

# 检查Docker网络
docker network ls
docker network inspect smart-ai-router_default
```

**3. 配置文件挂载**
```bash
# 检查挂载点
docker exec smart-ai-router ls -la /app/config/

# 验证配置文件
docker exec smart-ai-router cat /app/config/router_config.yaml
```

**4. 重建容器**
```bash
# 完全重建
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 查看构建日志
docker-compose build --no-cache --progress=plain
```

### 🚀 生产部署问题

#### 环境配置检查：

**1. 环境变量**
```bash
# 检查必需的环境变量
env | grep -E "(JWT_SECRET|WEB_SECRET_KEY|DATABASE_URL)"

# 生产环境配置
export DEBUG=false
export LOG_LEVEL=INFO
```

**2. 数据库配置**
```bash
# 如果使用PostgreSQL
export DATABASE_URL="postgresql://user:pass@localhost/smart_ai_router"

# 测试数据库连接
python -c "
from core.database import test_connection
test_connection()
"
```

**3. 反向代理配置**
```nginx
# Nginx配置示例
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:7601;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 日志分析指南

### 📋 日志文件位置

```bash
# 主要日志文件
logs/smart-ai-router.log          # 主应用日志
logs/scheduler.log                # 定时任务日志
logs/model-discovery.log          # 模型发现日志
logs/performance.log              # 性能日志
```

### 🔍 日志关键词搜索

**1. 错误相关**
```bash
# 查找错误信息
grep -i "error\|exception\|failed\|timeout" logs/smart-ai-router.log

# 查找特定错误类型
grep "AuthenticationException\|RateLimitException\|ChannelException" logs/smart-ai-router.log

# 查找最近的错误
grep -i "error" logs/smart-ai-router.log | tail -20
```

**2. 性能相关**
```bash
# 查找慢请求（超过5秒）
grep "LATENCY" logs/smart-ai-router.log | awk '$NF > 5000'

# 查找高频错误
grep -i "error" logs/smart-ai-router.log | awk '{print $4}' | sort | uniq -c | sort -nr

# 查看请求量统计
grep "REQUEST:" logs/smart-ai-router.log | grep $(date +%Y-%m-%d) | wc -l
```

**3. 渠道状态**
```bash
# 查看渠道健康状态
grep "HEALTH:" logs/smart-ai-router.log | tail -20

# 查看API密钥验证结果
grep "API_KEY_VALIDATION:" logs/smart-ai-router.log

# 查看模型发现结果
grep "MODEL_DISCOVERY:" logs/smart-ai-router.log
```

### 📊 日志分析脚本

创建`analyze_logs.py`：
```python
#!/usr/bin/env python3
"""日志分析工具"""

import re
import sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta

def analyze_error_patterns(log_file):
    """分析错误模式"""
    error_counts = Counter()
    channel_errors = defaultdict(list)
    
    with open(log_file, 'r') as f:
        for line in f:
            if 'ERROR' in line or 'Exception' in line:
                # 提取错误类型
                error_match = re.search(r'(\w+Exception|\w+Error)', line)
                if error_match:
                    error_type = error_match.group(1)
                    error_counts[error_type] += 1
                
                # 提取渠道ID
                channel_match = re.search(r'channel[_\s]*[\'":]([^\'",\s]+)', line, re.I)
                if channel_match:
                    channel_id = channel_match.group(1)
                    channel_errors[channel_id].append(line.strip())
    
    print("错误类型统计:")
    for error_type, count in error_counts.most_common():
        print(f"  {error_type}: {count}")
    
    print("\n渠道错误统计:")
    for channel_id, errors in channel_errors.items():
        print(f"  {channel_id}: {len(errors)} 个错误")

if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else "logs/smart-ai-router.log"
    analyze_error_patterns(log_file)
```

---

## 高级调试技巧

### 🔬 调试模式

**1. 启用详细日志**
```bash
# 临时启用DEBUG模式
export LOG_LEVEL=DEBUG
python main.py

# 或修改配置文件
```

**2. 使用调试工具**
```python
# 交互式调试会话
python -c "
import asyncio
from core.yaml_config import get_yaml_config_loader
from core.json_router import JSONRouter

async def debug_session():
    config = get_yaml_config_loader()
    router = JSONRouter(config)
    
    # 交互式调试
    import pdb; pdb.set_trace()
    
    # 测试路由
    result = await router.route_request('gpt-3.5-turbo', {})
    print(f'路由结果: {result}')

asyncio.run(debug_session())
"
```

**3. 性能分析**
```python
# 使用cProfile进行性能分析
python -m cProfile -o performance.prof main.py

# 分析结果
python -c "
import pstats
p = pstats.Stats('performance.prof')
p.sort_stats('cumulative').print_stats(20)
"
```

### 🛠️ 常用调试脚本

**1. 测试单个渠道**
```python
# test_channel.py
import asyncio
from core.providers.registry import get_provider_registry
from core.yaml_config import get_yaml_config_loader

async def test_channel(channel_id):
    config = get_yaml_config_loader()
    channel = config.get_channel_by_id(channel_id)
    if not channel:
        print(f"渠道 {channel_id} 不存在")
        return
    
    registry = get_provider_registry()
    adapter = registry.get_adapter(channel.provider_name)
    
    try:
        # 测试模型列表
        models = await adapter.list_models(channel)
        print(f"发现 {len(models)} 个模型")
        
        # 测试简单请求
        response = await adapter.chat_completion(
            channel,
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-3.5-turbo",
            max_tokens=10
        )
        print("测试请求成功")
        
    except Exception as e:
        print(f"测试失败: {e}")

# 使用方法
# python -c "import asyncio; from test_channel import test_channel; asyncio.run(test_channel('openai_main'))"
```

**2. 路由决策分析**
```python
# analyze_routing.py
import asyncio
from core.json_router import JSONRouter
from core.yaml_config import get_yaml_config_loader

async def analyze_routing_decision(model_name, strategy="balanced"):
    config = get_yaml_config_loader()
    router = JSONRouter(config)
    
    # 获取候选渠道
    candidates = await router.get_candidate_channels(model_name)
    print(f"找到 {len(candidates)} 个候选渠道")
    
    for candidate in candidates[:5]:
        print(f"  {candidate.channel_id}: "
              f"优先级={candidate.priority}, "
              f"成本评分={candidate.cost_score}, "
              f"速度评分={candidate.speed_score}")
    
    # 应用路由策略
    sorted_candidates = router.apply_routing_strategy(candidates, strategy)
    print(f"\n使用 {strategy} 策略后的排序:")
    
    for i, candidate in enumerate(sorted_candidates[:3]):
        print(f"  {i+1}. {candidate.channel_id}: 总分={candidate.total_score}")

# 使用方法
# python -c "import asyncio; from analyze_routing import analyze_routing_decision; asyncio.run(analyze_routing_decision('gpt-3.5-turbo'))"
```

---

## 常见错误码解释

### HTTP状态码

| 状态码 | 错误类型 | 可能原因 | 解决方案 |
|--------|----------|----------|----------|
| 400 | Bad Request | 请求格式错误、模型不支持 | 检查请求格式和模型名称 |
| 401 | Unauthorized | API密钥无效或过期 | 更新API密钥 |
| 403 | Forbidden | 权限不足、配额不足 | 检查API密钥权限和配额 |
| 429 | Too Many Requests | 速率限制 | 等待后重试或更换渠道 |
| 500 | Internal Server Error | 服务器内部错误 | 检查日志，重启服务 |
| 502 | Bad Gateway | 上游服务器错误 | 检查Provider服务状态 |
| 503 | Service Unavailable | 所有渠道不可用 | 检查渠道配置和网络连接 |
| 504 | Gateway Timeout | 请求超时 | 增加超时时间或优化网络 |

### 自定义错误类型

| 错误类型 | 描述 | 常见原因 | 解决方案 |
|----------|------|----------|----------|
| `NoChannelsFoundException` | 没有找到可用渠道 | 模型名称错误、所有渠道被禁用 | 检查模型名称和渠道配置 |
| `AllChannelsFailedException` | 所有渠道都失败了 | API密钥问题、网络问题 | 检查API密钥和网络连接 |
| `AuthenticationException` | 认证失败 | API密钥无效 | 更新API密钥 |
| `RateLimitException` | 速率限制 | 请求频率过高 | 降低请求频率或升级账户 |
| `ModelNotSupportedException` | 模型不支持 | 模型名称错误 | 使用正确的模型名称 |
| `ChannelUnavailableException` | 渠道不可用 | 网络问题、服务器维护 | 检查网络或等待服务恢复 |

### 错误响应头

Smart AI Router会在错误响应中添加详细的头信息：

```http
X-Router-Status: error
X-Router-Error-Type: AllChannelsFailedException
X-Router-Attempts: 3
X-Router-Model-Requested: gpt-3.5-turbo
X-Router-Time: 5.234s
```

这些头信息可以帮助快速定位问题：

- `X-Router-Status`: 路由器状态
- `X-Router-Error-Type`: 具体错误类型
- `X-Router-Attempts`: 尝试次数
- `X-Router-Model-Requested`: 请求的模型
- `X-Router-Time`: 执行时间

---

## 获取帮助

### 📞 技术支持

1. **查看文档**
   - [README.md](../README.md) - 基础使用说明
   - [CLAUDE.md](../CLAUDE.md) - 开发指南
   - [架构文档](./architecture.md) - 系统架构

2. **社区支持**
   - GitHub Issues - 报告bug和请求功能
   - 讨论区 - 技术讨论和问答

3. **调试信息收集**
   
   在报告问题时，请提供以下信息：
   
   ```bash
   # 系统信息
   python --version
   uv --version
   docker --version
   
   # 配置信息（隐藏敏感信息）
   grep -v "api_key\|secret" config/router_config.yaml
   
   # 错误日志
   tail -50 logs/smart-ai-router.log
   
   # 健康检查
   curl http://localhost:7601/health
   
   # 模型列表
   curl http://localhost:7601/v1/models
   ```

### 💡 常见问题FAQ

**Q: 为什么我的免费模型没有被优先选择？**
A: 检查路由策略设置，使用 `free_first` 策略，并确保模型正确标记了 `free` 标签。

**Q: 如何添加新的AI提供商？**
A: 1) 在配置文件中添加provider定义，2) 创建对应的adapter类，3) 添加渠道配置。

**Q: 如何监控系统性能？**
A: 检查 `/health` 端点，分析日志文件，使用内置的性能统计功能。

**Q: 配置修改后需要重启吗？**
A: 大部分配置修改需要重启，但渠道的启用/禁用可以通过管理API动态修改。

**Q: 如何实现负载均衡？**
A: 使用 `balanced` 路由策略，配置多个相同模型的渠道，系统会自动进行负载均衡。

---

*本文档会持续更新，如有问题或建议，请提交Issue或Pull Request。*