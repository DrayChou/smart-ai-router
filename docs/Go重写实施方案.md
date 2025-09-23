# Go 语言重写实施方案

## 📋 方案概览

基于 Go 语言的高并发特性和优秀的 HTTP 生态系统，本方案提供完整的 Smart AI Router 重写计划。Go 方案在保持合理开发复杂度的同时，能够实现显著的性能提升，特别是在冷启动时间和并发处理能力方面。

### 核心优势

- **真正的并行处理**：无 GIL 限制，goroutines 实现真正的并行评分
- **极快的冷启动**：编译后二进制，启动时间 10-50ms
- **内存效率**：相比 Python 减少 60-80% 内存使用
- **成熟的 Web 生态**：丰富的 HTTP、JSON、配置管理库

### 技术栈选择

- **Web 框架**: Gin (高性能 HTTP 框架)
- **配置管理**: Viper + YAML
- **并发模型**: Goroutines + Channels
- **缓存**: Groupcache + Redis (可选)
- **日志**: Zap (结构化高性能日志)
- **监控**: Prometheus + Grafana

## 🎯 性能改进目标

| 指标             | Python 当前  | Go 目标       | 改进幅度   |
| ---------------- | ------------ | ------------- | ---------- |
| **冷启动时间**   | 10-15 秒     | 10-50ms       | **99%+**   |
| **首次请求延迟** | 8-12 秒      | 10-50ms       | **99%+**   |
| **并发处理能力** | ~1,000 req/s | ~20,000 req/s | **20x**    |
| **内存使用**     | 40-60MB      | 5-15MB        | **70-80%** |
| **评分计算**     | 0.1ms/渠道   | 0.01ms/渠道   | **10x**    |

## 🏗️ 系统架构设计

### 核心架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Go Smart AI Router                      │
├─────────────────────────────────────────────────────────────┤
│  HTTP Layer (Gin Framework)                               │
│  ├── /v1/chat/completions                                  │
│  ├── /v1/models                                           │
│  ├── /health                                              │
│  └── /admin/*                                             │
├─────────────────────────────────────────────────────────────┤
│  Router Core                                               │
│  ├── Channel Manager (sync.Map)                           │
│  ├── Scoring Engine (Goroutine Pool)                      │
│  ├── Tag Index (Concurrent Trie)                          │
│  └── Request Cache (GroupCache)                           │
├─────────────────────────────────────────────────────────────┤
│  Provider Adapters                                         │
│  ├── OpenAI Adapter                                       │
│  ├── Anthropic Adapter                                    │
│  ├── SiliconFlow Adapter                                  │
│  └── ... (17 adapters)                                    │
├─────────────────────────────────────────────────────────────┤
│  Background Services                                        │
│  ├── Model Discovery (Worker Pool)                        │
│  ├── Health Checker (Ticker)                              │
│  ├── Price Updater (Scheduler)                            │
│  └── Metrics Collector                                    │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 详细实施计划

### Phase 1: 核心路由引擎 (Week 1-4)

#### 1.1 项目结构设计

```
smart-ai-router-go/
├── cmd/
│   └── server/
│       └── main.go                 # 应用入口
├── internal/
│   ├── config/                     # 配置管理
│   │   ├── config.go
│   │   └── yaml_loader.go
│   ├── router/                     # 路由核心
│   │   ├── router.go
│   │   ├── scoring.go
│   │   ├── channel_manager.go
│   │   └── tag_index.go
│   ├── providers/                  # Provider 适配器
│   │   ├── adapter.go              # 通用接口
│   │   ├── openai/
│   │   ├── anthropic/
│   │   └── siliconflow/
│   ├── cache/                      # 缓存系统
│   │   ├── memory_cache.go
│   │   ├── request_cache.go
│   │   └── redis_cache.go
│   ├── api/                        # HTTP API
│   │   ├── handlers/
│   │   ├── middleware/
│   │   └── routes.go
│   └── services/                   # 后台服务
│       ├── discovery.go
│       ├── health_check.go
│       └── metrics.go
├── pkg/                            # 公共包
│   ├── logger/
│   ├── utils/
│   └── types/
├── configs/                        # 配置文件
├── scripts/                        # 构建脚本
└── go.mod
```

#### 1.2 核心路由器实现

```go
// internal/router/router.go
package router

import (
    "context"
    "sync"
    "time"
)

type Router struct {
    channels        sync.Map                    // 并发安全的频道映射
    tagIndex        *ConcurrentTagIndex         // 并发标签索引
    scoreCalculator *ParallelScoringEngine      // 并行评分引擎
    requestCache    *GroupCacheManager          // 请求级缓存
    config          *config.RouterConfig        // 路由配置

    // 性能监控
    metrics         *RouterMetrics
    logger          *zap.Logger
}

type RoutingRequest struct {
    Model                string                 `json:"model"`
    Messages            []Message              `json:"messages"`
    Strategy            string                 `json:"strategy,omitempty"`
    RequiredCapabilities []string              `json:"required_capabilities,omitempty"`
    MaxCostPer1K        *float64               `json:"max_cost_per_1k,omitempty"`
    PreferLocal         bool                   `json:"prefer_local,omitempty"`
    ExcludeProviders    []string               `json:"exclude_providers,omitempty"`
}

type RoutingResult struct {
    PrimaryChannel   *Channel               `json:"primary_channel"`
    BackupChannels   []*Channel             `json:"backup_channels"`
    TotalScore      float64                `json:"total_score"`
    CostEstimate    float64                `json:"cost_estimate"`
    ProcessingTime  time.Duration          `json:"processing_time"`
}

func NewRouter(cfg *config.RouterConfig) *Router {
    return &Router{
        channels:        sync.Map{},
        tagIndex:        NewConcurrentTagIndex(),
        scoreCalculator: NewParallelScoringEngine(cfg.ScoringWorkers),
        requestCache:    NewGroupCacheManager(cfg.CacheSize),
        config:          cfg,
        metrics:        NewRouterMetrics(),
        logger:         logger.NewLogger("router"),
    }
}

func (r *Router) RouteRequest(ctx context.Context, req *RoutingRequest) (*RoutingResult, error) {
    // 生成缓存键
    cacheKey := r.generateCacheKey(req)

    // 检查缓存
    if cached, found := r.requestCache.Get(cacheKey); found {
        r.metrics.CacheHits.Inc()
        return cached.(*RoutingResult), nil
    }

    r.metrics.CacheMisses.Inc()

    // 获取候选频道
    candidates, err := r.getCandidateChannels(ctx, req)
    if err != nil {
        return nil, err
    }

    // 并行评分
    scores, err := r.scoreCalculator.ScoreChannels(ctx, candidates, req)
    if err != nil {
        return nil, err
    }

    // 选择最佳频道
    result := r.selectBestChannels(scores)

    // 缓存结果
    r.requestCache.Set(cacheKey, result, time.Minute)

    return result, nil
}
```

#### 1.3 并行评分引擎

```go
// internal/router/scoring.go
package router

import (
    "context"
    "runtime"
    "sync"
)

type ParallelScoringEngine struct {
    workerPool    chan struct{}              // 工作池，限制并发数
    scoringFuncs  map[string]ScoringFunc     // 评分函数映射
    weights       map[string]float64         // 权重配置
    logger        *zap.Logger
}

type ScoringFunc func(context.Context, *Channel, *RoutingRequest) (float64, error)

type ChannelScore struct {
    Channel       *Channel                   `json:"channel"`
    TotalScore    float64                    `json:"total_score"`
    CostScore     float64                    `json:"cost_score"`
    SpeedScore    float64                    `json:"speed_score"`
    QualityScore  float64                    `json:"quality_score"`
    ReliabilityScore float64                `json:"reliability_score"`
}

func NewParallelScoringEngine(maxWorkers int) *ParallelScoringEngine {
    if maxWorkers <= 0 {
        maxWorkers = runtime.NumCPU() * 2
    }

    return &ParallelScoringEngine{
        workerPool: make(chan struct{}, maxWorkers),
        scoringFuncs: map[string]ScoringFunc{
            "cost":        calculateCostScore,
            "speed":       calculateSpeedScore,
            "quality":     calculateQualityScore,
            "reliability": calculateReliabilityScore,
        },
        weights: map[string]float64{
            "cost": 0.4, "speed": 0.3, "quality": 0.2, "reliability": 0.1,
        },
        logger: logger.NewLogger("scoring"),
    }
}

func (e *ParallelScoringEngine) ScoreChannels(ctx context.Context, channels []*Channel, req *RoutingRequest) ([]*ChannelScore, error) {
    scores := make([]*ChannelScore, len(channels))
    var wg sync.WaitGroup
    var mu sync.Mutex

    // 并行评分每个频道
    for i, channel := range channels {
        wg.Add(1)
        go func(idx int, ch *Channel) {
            defer wg.Done()

            // 获取工作池许可证
            e.workerPool <- struct{}{}
            defer func() { <-e.workerPool }()

            score, err := e.scoreChannel(ctx, ch, req)
            if err != nil {
                e.logger.Warn("Failed to score channel",
                    zap.String("channel", ch.ID),
                    zap.Error(err))
                return
            }

            mu.Lock()
            scores[idx] = score
            mu.Unlock()
        }(i, channel)
    }

    wg.Wait()

    // 过滤 nil 结果并排序
    validScores := make([]*ChannelScore, 0, len(scores))
    for _, score := range scores {
        if score != nil {
            validScores = append(validScores, score)
        }
    }

    // 按总分排序
    sort.Slice(validScores, func(i, j int) bool {
        return validScores[i].TotalScore > validScores[j].TotalScore
    })

    return validScores, nil
}

func (e *ParallelScoringEngine) scoreChannel(ctx context.Context, channel *Channel, req *RoutingRequest) (*ChannelScore, error) {
    score := &ChannelScore{Channel: channel}

    // 并行计算各项评分
    var wg sync.WaitGroup
    var mu sync.Mutex

    for scoreType, scoringFunc := range e.scoringFuncs {
        wg.Add(1)
        go func(sType string, sFunc ScoringFunc) {
            defer wg.Done()

            value, err := sFunc(ctx, channel, req)
            if err != nil {
                e.logger.Debug("Scoring function failed",
                    zap.String("type", sType),
                    zap.Error(err))
                return
            }

            mu.Lock()
            switch sType {
            case "cost":
                score.CostScore = value
            case "speed":
                score.SpeedScore = value
            case "quality":
                score.QualityScore = value
            case "reliability":
                score.ReliabilityScore = value
            }
            mu.Unlock()
        }(scoreType, scoringFunc)
    }

    wg.Wait()

    // 计算加权总分
    score.TotalScore =
        score.CostScore*e.weights["cost"] +
        score.SpeedScore*e.weights["speed"] +
        score.QualityScore*e.weights["quality"] +
        score.ReliabilityScore*e.weights["reliability"]

    return score, nil
}
```

#### 1.4 并发标签索引

```go
// internal/router/tag_index.go
package router

import (
    "strings"
    "sync"
)

type ConcurrentTagIndex struct {
    tagToModels   sync.Map    // map[string][]string - 标签到模型映射
    modelToTags   sync.Map    // map[string][]string - 模型到标签映射
    tagFrequency  sync.Map    // map[string]int - 标签频率统计
    rwMutex       sync.RWMutex
}

func NewConcurrentTagIndex() *ConcurrentTagIndex {
    return &ConcurrentTagIndex{}
}

func (idx *ConcurrentTagIndex) AddModel(modelName string, providerID string) {
    // 提取标签
    tags := idx.extractTags(modelName)

    // 存储模型到标签映射
    modelKey := fmt.Sprintf("%s:%s", providerID, modelName)
    idx.modelToTags.Store(modelKey, tags)

    // 更新标签到模型映射
    for _, tag := range tags {
        modelsInterface, _ := idx.tagToModels.LoadOrStore(tag, &sync.Map{})
        models := modelsInterface.(*sync.Map)
        models.Store(modelKey, true)

        // 更新频率统计
        freqInterface, _ := idx.tagFrequency.LoadOrStore(tag, int64(0))
        freq := freqInterface.(int64)
        idx.tagFrequency.Store(tag, freq+1)
    }
}

func (idx *ConcurrentTagIndex) FindModelsByTags(tags []string) []string {
    if len(tags) == 0 {
        return []string{}
    }

    // 从最不频繁的标签开始（更高选择性）
    sortedTags := idx.sortTagsBySelectivity(tags)

    if len(sortedTags) == 0 {
        return []string{}
    }

    // 获取第一个标签的模型集合
    modelsInterface, exists := idx.tagToModels.Load(sortedTags[0])
    if !exists {
        return []string{}
    }

    firstTagModels := modelsInterface.(*sync.Map)
    candidateModels := make(map[string]bool)

    firstTagModels.Range(func(key, value interface{}) bool {
        candidateModels[key.(string)] = true
        return true
    })

    // 与其他标签的模型集合求交集
    for _, tag := range sortedTags[1:] {
        modelsInterface, exists := idx.tagToModels.Load(tag)
        if !exists {
            return []string{} // 没有模型匹配这个标签
        }

        tagModels := modelsInterface.(*sync.Map)
        newCandidates := make(map[string]bool)

        tagModels.Range(func(key, value interface{}) bool {
            modelKey := key.(string)
            if candidateModels[modelKey] {
                newCandidates[modelKey] = true
            }
            return true
        })

        candidateModels = newCandidates

        if len(candidateModels) == 0 {
            return []string{} // 早期终止
        }
    }

    // 转换为切片
    result := make([]string, 0, len(candidateModels))
    for model := range candidateModels {
        result = append(result, model)
    }

    return result
}

func (idx *ConcurrentTagIndex) extractTags(modelName string) []string {
    // 标签提取逻辑 - 使用编译后的正则表达式
    separators := regexp.MustCompile(`[/:@\-_,]`)
    parts := separators.Split(strings.ToLower(modelName), -1)

    var tags []string
    for _, part := range parts {
        part = strings.TrimSpace(part)
        if len(part) > 0 && len(part) < 50 { // 过滤过长的部分
            tags = append(tags, part)
        }
    }

    return tags
}

func (idx *ConcurrentTagIndex) sortTagsBySelectivity(tags []string) []string {
    type tagFreq struct {
        tag  string
        freq int64
    }

    var tagFreqs []tagFreq
    for _, tag := range tags {
        freqInterface, exists := idx.tagFrequency.Load(tag)
        if exists {
            freq := freqInterface.(int64)
            tagFreqs = append(tagFreqs, tagFreq{tag: tag, freq: freq})
        }
    }

    // 按频率排序（频率低的优先，选择性高）
    sort.Slice(tagFreqs, func(i, j int) bool {
        return tagFreqs[i].freq < tagFreqs[j].freq
    })

    result := make([]string, len(tagFreqs))
    for i, tf := range tagFreqs {
        result[i] = tf.tag
    }

    return result
}
```

### Phase 2: Provider 适配器系统 (Week 5-8)

#### 2.1 通用适配器接口

```go
// internal/providers/adapter.go
package providers

import (
    "context"
    "time"
)

type Adapter interface {
    // 基础信息
    GetProviderID() string
    GetProviderName() string

    // 模型发现
    DiscoverModels(ctx context.Context, apiKey string) ([]*ModelInfo, error)

    // API 密钥验证
    ValidateAPIKey(ctx context.Context, apiKey string) (*APIKeyInfo, error)

    // 定价信息
    GetPricing(ctx context.Context) (*PricingInfo, error)

    // 健康检查
    HealthCheck(ctx context.Context, apiKey string) error

    // 请求处理
    ProcessRequest(ctx context.Context, req *ChatCompletionRequest) (*ChatCompletionResponse, error)
}

type ModelInfo struct {
    ID                  string                `json:"id"`
    Name               string                `json:"name"`
    Description        string                `json:"description,omitempty"`
    ContextLength      int                   `json:"context_length"`
    MaxTokens          int                   `json:"max_tokens,omitempty"`
    Capabilities       []string              `json:"capabilities"`
    InputCost          float64               `json:"input_cost"`
    OutputCost         float64               `json:"output_cost"`
    Tags               []string              `json:"tags"`

    // 性能指标
    AverageLatency     time.Duration         `json:"average_latency,omitempty"`
    SuccessRate        float64               `json:"success_rate,omitempty"`
}

type APIKeyInfo struct {
    Valid              bool                  `json:"valid"`
    UserTier           string                `json:"user_tier,omitempty"`
    RateLimits         *RateLimitInfo        `json:"rate_limits,omitempty"`
    QuotaInfo          *QuotaInfo            `json:"quota_info,omitempty"`
    ExpiresAt          *time.Time            `json:"expires_at,omitempty"`
}

type RateLimitInfo struct {
    RequestsPerMinute  int                   `json:"requests_per_minute"`
    TokensPerMinute    int                   `json:"tokens_per_minute"`
    RequestsPerDay     int                   `json:"requests_per_day"`
}
```

#### 2.2 OpenAI 适配器实现

```go
// internal/providers/openai/adapter.go
package openai

import (
    "context"
    "encoding/json"
    "fmt"
    "net/http"
    "time"
)

type OpenAIAdapter struct {
    httpClient    *http.Client
    baseURL       string
    timeout       time.Duration
    rateLimiter   *rate.Limiter
    logger        *zap.Logger
}

func NewOpenAIAdapter(config *OpenAIConfig) *OpenAIAdapter {
    return &OpenAIAdapter{
        httpClient: &http.Client{
            Timeout: config.Timeout,
            Transport: &http.Transport{
                MaxIdleConns:       100,
                IdleConnTimeout:    90 * time.Second,
                DisableCompression: false,
            },
        },
        baseURL:     config.BaseURL,
        timeout:     config.Timeout,
        rateLimiter: rate.NewLimiter(rate.Limit(config.RateLimit), config.BurstLimit),
        logger:      logger.NewLogger("openai-adapter"),
    }
}

func (a *OpenAIAdapter) DiscoverModels(ctx context.Context, apiKey string) ([]*providers.ModelInfo, error) {
    // 等待速率限制
    if err := a.rateLimiter.Wait(ctx); err != nil {
        return nil, fmt.Errorf("rate limit: %w", err)
    }

    req, err := http.NewRequestWithContext(ctx, "GET", a.baseURL+"/v1/models", nil)
    if err != nil {
        return nil, err
    }

    req.Header.Set("Authorization", "Bearer "+apiKey)
    req.Header.Set("Content-Type", "application/json")

    resp, err := a.httpClient.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("API request failed: %d", resp.StatusCode)
    }

    var modelsResp struct {
        Data []struct {
            ID      string `json:"id"`
            Object  string `json:"object"`
            Created int64  `json:"created"`
            OwnedBy string `json:"owned_by"`
        } `json:"data"`
    }

    if err := json.NewDecoder(resp.Body).Decode(&modelsResp); err != nil {
        return nil, err
    }

    models := make([]*providers.ModelInfo, 0, len(modelsResp.Data))
    for _, model := range modelsResp.Data {
        if model.Object == "model" {
            modelInfo := a.convertToModelInfo(model)
            models = append(models, modelInfo)
        }
    }

    return models, nil
}

func (a *OpenAIAdapter) ProcessRequest(ctx context.Context, req *providers.ChatCompletionRequest) (*providers.ChatCompletionResponse, error) {
    // 等待速率限制
    if err := a.rateLimiter.Wait(ctx); err != nil {
        return nil, fmt.Errorf("rate limit: %w", err)
    }

    // 转换请求格式
    openaiReq := a.convertRequest(req)

    // 发送请求
    reqBody, err := json.Marshal(openaiReq)
    if err != nil {
        return nil, err
    }

    httpReq, err := http.NewRequestWithContext(ctx, "POST",
        a.baseURL+"/v1/chat/completions",
        bytes.NewBuffer(reqBody))
    if err != nil {
        return nil, err
    }

    httpReq.Header.Set("Authorization", "Bearer "+req.APIKey)
    httpReq.Header.Set("Content-Type", "application/json")

    start := time.Now()
    resp, err := a.httpClient.Do(httpReq)
    latency := time.Since(start)

    if err != nil {
        a.logger.Error("Request failed",
            zap.String("model", req.Model),
            zap.Duration("latency", latency),
            zap.Error(err))
        return nil, err
    }
    defer resp.Body.Close()

    // 处理响应
    if resp.StatusCode != http.StatusOK {
        return a.handleErrorResponse(resp)
    }

    var openaiResp OpenAIResponse
    if err := json.NewDecoder(resp.Body).Decode(&openaiResp); err != nil {
        return nil, err
    }

    // 转换响应格式
    result := a.convertResponse(&openaiResp)
    result.ProcessingTime = latency

    a.logger.Info("Request completed",
        zap.String("model", req.Model),
        zap.Duration("latency", latency),
        zap.Int("input_tokens", result.Usage.PromptTokens),
        zap.Int("output_tokens", result.Usage.CompletionTokens))

    return result, nil
}
```

### Phase 3: 高性能缓存系统 (Week 9-10)

#### 3.1 分层缓存实现

```go
// internal/cache/memory_cache.go
package cache

import (
    "context"
    "sync"
    "time"

    "github.com/allegro/bigcache/v3"
    "github.com/patrickmn/go-cache"
)

type MultiLevelCache struct {
    // L1: 热点数据缓存 (最快访问)
    l1Cache    *cache.Cache

    // L2: 常用数据缓存 (内存缓存)
    l2Cache    *bigcache.BigCache

    // L3: 大容量缓存 (可选 Redis)
    l3Cache    RedisCache

    // 缓存统计
    metrics    *CacheMetrics
    logger     *zap.Logger
}

type CacheItem struct {
    Value      interface{}   `json:"value"`
    CreatedAt  time.Time     `json:"created_at"`
    ExpiresAt  time.Time     `json:"expires_at"`
    AccessCount int64        `json:"access_count"`
    LastAccess time.Time     `json:"last_access"`
}

func NewMultiLevelCache(config *CacheConfig) *MultiLevelCache {
    // L1: 小容量高速缓存
    l1 := cache.New(config.L1TTL, config.L1CleanupInterval)

    // L2: 大容量内存缓存
    l2Config := bigcache.DefaultConfig(config.L2TTL)
    l2Config.Shards = 1024
    l2Config.MaxEntrySize = config.L2MaxEntrySize
    l2Config.MaxEntriesInWindow = config.L2MaxEntries
    l2, _ := bigcache.NewBigCache(l2Config)

    return &MultiLevelCache{
        l1Cache: l1,
        l2Cache: l2,
        l3Cache: NewRedisCache(config.RedisConfig),
        metrics: NewCacheMetrics(),
        logger:  logger.NewLogger("cache"),
    }
}

func (c *MultiLevelCache) Get(key string) (interface{}, bool) {
    start := time.Now()
    defer func() {
        c.metrics.GetLatency.Observe(time.Since(start).Seconds())
    }()

    // L1 缓存查找
    if value, found := c.l1Cache.Get(key); found {
        c.metrics.L1Hits.Inc()
        c.updateAccessStats(key, value)
        return value, true
    }
    c.metrics.L1Misses.Inc()

    // L2 缓存查找
    if data, err := c.l2Cache.Get(key); err == nil {
        c.metrics.L2Hits.Inc()

        var item CacheItem
        if err := json.Unmarshal(data, &item); err == nil && time.Now().Before(item.ExpiresAt) {
            // 提升到 L1
            c.l1Cache.Set(key, item.Value, time.Until(item.ExpiresAt))
            return item.Value, true
        }
    }
    c.metrics.L2Misses.Inc()

    // L3 缓存查找 (Redis)
    if c.l3Cache != nil {
        if value, found := c.l3Cache.Get(key); found {
            c.metrics.L3Hits.Inc()

            // 反向填充到上层缓存
            c.setMultiLevel(key, value, time.Hour) // 默认 TTL
            return value, true
        }
    }
    c.metrics.L3Misses.Inc()

    return nil, false
}

func (c *MultiLevelCache) Set(key string, value interface{}, ttl time.Duration) {
    c.setMultiLevel(key, value, ttl)
}

func (c *MultiLevelCache) setMultiLevel(key string, value interface{}, ttl time.Duration) {
    item := CacheItem{
        Value:       value,
        CreatedAt:   time.Now(),
        ExpiresAt:   time.Now().Add(ttl),
        AccessCount: 1,
        LastAccess:  time.Now(),
    }

    // 设置到所有层级
    c.l1Cache.Set(key, value, ttl)

    if data, err := json.Marshal(item); err == nil {
        c.l2Cache.Set(key, data)
    }

    if c.l3Cache != nil {
        c.l3Cache.Set(key, value, ttl)
    }
}
```

#### 3.2 请求级缓存

```go
// internal/cache/request_cache.go
package cache

import (
    "crypto/md5"
    "fmt"
    "strings"
    "time"
)

type RequestCache struct {
    cache      *MultiLevelCache
    keyBuilder *CacheKeyBuilder
    ttlConfig  map[string]time.Duration
    logger     *zap.Logger
}

type CacheKeyBuilder struct {
    includeTimestamp bool
    timestampWindow  time.Duration
}

func NewRequestCache(cacheConfig *CacheConfig) *RequestCache {
    return &RequestCache{
        cache:      NewMultiLevelCache(cacheConfig),
        keyBuilder: &CacheKeyBuilder{
            includeTimestamp: true,
            timestampWindow:  time.Minute, // 1分钟时间窗口
        },
        ttlConfig: map[string]time.Duration{
            "routing":        time.Minute,
            "model_discovery": time.Hour * 6,
            "pricing":        time.Hour,
            "health_check":   time.Minute * 5,
        },
        logger: logger.NewLogger("request-cache"),
    }
}

func (rc *RequestCache) GetRoutingResult(req *RoutingRequest) (*RoutingResult, bool) {
    key := rc.keyBuilder.BuildRoutingKey(req)

    if value, found := rc.cache.Get(key); found {
        if result, ok := value.(*RoutingResult); ok {
            rc.logger.Debug("Cache hit for routing request",
                zap.String("key", key[:16]+"..."))
            return result, true
        }
    }

    return nil, false
}

func (rc *RequestCache) SetRoutingResult(req *RoutingRequest, result *RoutingResult) {
    key := rc.keyBuilder.BuildRoutingKey(req)
    ttl := rc.ttlConfig["routing"]

    rc.cache.Set(key, result, ttl)
    rc.logger.Debug("Cached routing result",
        zap.String("key", key[:16]+"..."),
        zap.Duration("ttl", ttl))
}

func (kb *CacheKeyBuilder) BuildRoutingKey(req *RoutingRequest) string {
    var keyParts []string

    keyParts = append(keyParts, req.Model)
    keyParts = append(keyParts, req.Strategy)

    if req.MaxCostPer1K != nil {
        keyParts = append(keyParts, fmt.Sprintf("cost:%.4f", *req.MaxCostPer1K))
    }

    if req.PreferLocal {
        keyParts = append(keyParts, "local:true")
    }

    if len(req.ExcludeProviders) > 0 {
        keyParts = append(keyParts, "exclude:"+strings.Join(req.ExcludeProviders, ","))
    }

    // 时间窗口 (减少缓存分片)
    if kb.includeTimestamp {
        window := time.Now().Truncate(kb.timestampWindow).Unix()
        keyParts = append(keyParts, fmt.Sprintf("t:%d", window))
    }

    keyString := strings.Join(keyParts, "|")

    // MD5 哈希生成固定长度键
    hash := md5.Sum([]byte(keyString))
    return fmt.Sprintf("route:%x", hash)
}
```

### Phase 4: 后台服务和监控 (Week 11-12)

#### 4.1 模型发现服务

```go
// internal/services/discovery.go
package services

import (
    "context"
    "sync"
    "time"
)

type ModelDiscoveryService struct {
    adapters       map[string]providers.Adapter
    discoveryPool  *WorkerPool
    cache          *cache.RequestCache
    tagIndex       *router.ConcurrentTagIndex

    // 配置
    discoveryInterval time.Duration
    maxWorkers       int

    // 状态
    isRunning        bool
    lastDiscovery    map[string]time.Time
    discoveryErrors  map[string]error
    mu               sync.RWMutex

    logger           *zap.Logger
}

func NewModelDiscoveryService(adapters map[string]providers.Adapter, config *DiscoveryConfig) *ModelDiscoveryService {
    return &ModelDiscoveryService{
        adapters:          adapters,
        discoveryPool:     NewWorkerPool(config.MaxWorkers),
        discoveryInterval: config.Interval,
        maxWorkers:        config.MaxWorkers,
        lastDiscovery:     make(map[string]time.Time),
        discoveryErrors:   make(map[string]error),
        logger:           logger.NewLogger("discovery"),
    }
}

func (s *ModelDiscoveryService) Start(ctx context.Context) error {
    s.mu.Lock()
    if s.isRunning {
        s.mu.Unlock()
        return fmt.Errorf("discovery service already running")
    }
    s.isRunning = true
    s.mu.Unlock()

    // 启动工作池
    s.discoveryPool.Start(ctx)

    // 立即执行一次发现
    go s.discoverAllProviders(ctx)

    // 启动定时发现
    ticker := time.NewTicker(s.discoveryInterval)
    defer ticker.Stop()

    for {
        select {
        case <-ctx.Done():
            s.logger.Info("Discovery service stopping")
            s.stop()
            return ctx.Err()

        case <-ticker.C:
            go s.discoverAllProviders(ctx)
        }
    }
}

func (s *ModelDiscoveryService) discoverAllProviders(ctx context.Context) {
    s.logger.Info("Starting model discovery for all providers")
    start := time.Now()

    var wg sync.WaitGroup

    for providerID, adapter := range s.adapters {
        wg.Add(1)

        // 提交到工作池
        s.discoveryPool.Submit(func() {
            defer wg.Done()
            s.discoverProviderModels(ctx, providerID, adapter)
        })
    }

    wg.Wait()

    elapsed := time.Since(start)
    s.logger.Info("Model discovery completed",
        zap.Duration("elapsed", elapsed),
        zap.Int("providers", len(s.adapters)))
}

func (s *ModelDiscoveryService) discoverProviderModels(ctx context.Context, providerID string, adapter providers.Adapter) {
    s.logger.Debug("Discovering models", zap.String("provider", providerID))
    start := time.Now()

    // 获取该 Provider 的 API Keys
    apiKeys := s.getProviderAPIKeys(providerID)
    if len(apiKeys) == 0 {
        s.logger.Warn("No API keys found for provider", zap.String("provider", providerID))
        return
    }

    // 使用第一个有效的 API Key 进行发现
    var models []*providers.ModelInfo
    var discoveryErr error

    for _, apiKey := range apiKeys {
        discoveryCtx, cancel := context.WithTimeout(ctx, time.Minute*2)
        models, discoveryErr = adapter.DiscoverModels(discoveryCtx, apiKey)
        cancel()

        if discoveryErr == nil && len(models) > 0 {
            break
        }

        s.logger.Debug("API key failed for discovery",
            zap.String("provider", providerID),
            zap.Error(discoveryErr))
    }

    s.mu.Lock()
    s.lastDiscovery[providerID] = time.Now()
    s.discoveryErrors[providerID] = discoveryErr
    s.mu.Unlock()

    if discoveryErr != nil {
        s.logger.Error("Model discovery failed",
            zap.String("provider", providerID),
            zap.Error(discoveryErr))
        return
    }

    // 更新缓存和索引
    s.updateModelCache(providerID, models)
    s.updateTagIndex(providerID, models)

    elapsed := time.Since(start)
    s.logger.Info("Provider model discovery completed",
        zap.String("provider", providerID),
        zap.Int("models", len(models)),
        zap.Duration("elapsed", elapsed))
}

func (s *ModelDiscoveryService) updateTagIndex(providerID string, models []*providers.ModelInfo) {
    for _, model := range models {
        s.tagIndex.AddModel(model.ID, providerID)
    }
}
```

## 📊 性能测试和基准

### 基准测试设计

```go
// benchmarks/router_benchmark_test.go
package benchmarks

import (
    "context"
    "testing"
    "time"
)

func BenchmarkRouterPerformance(b *testing.B) {
    router := setupTestRouter()
    ctx := context.Background()

    testCases := []struct {
        name    string
        request *RoutingRequest
    }{
        {
            name: "SimpleTagRouting",
            request: &RoutingRequest{
                Model: "tag:gpt",
                Strategy: "cost_first",
            },
        },
        {
            name: "ComplexTagRouting",
            request: &RoutingRequest{
                Model: "tag:gpt,4o,vision",
                Strategy: "balanced",
                RequiredCapabilities: []string{"function_calling", "vision"},
            },
        },
    }

    for _, tc := range testCases {
        b.Run(tc.name, func(b *testing.B) {
            b.ResetTimer()
            for i := 0; i < b.N; i++ {
                _, err := router.RouteRequest(ctx, tc.request)
                if err != nil {
                    b.Fatal(err)
                }
            }
        })
    }
}

func BenchmarkConcurrentRouting(b *testing.B) {
    router := setupTestRouter()
    ctx := context.Background()

    request := &RoutingRequest{
        Model: "tag:free",
        Strategy: "cost_first",
    }

    b.RunParallel(func(pb *testing.PB) {
        for pb.Next() {
            _, err := router.RouteRequest(ctx, request)
            if err != nil {
                b.Fatal(err)
            }
        }
    })
}
```

## 📅 实施时间线

### 总体时间表 (12-16 周)

**Week 1-4: 核心路由引擎**

- Week 1: 项目搭建和基础架构
- Week 2: 并发路由器和评分引擎
- Week 3: 标签索引和缓存系统
- Week 4: 测试和优化

**Week 5-8: Provider 适配器**

- Week 5-6: 核心适配器 (OpenAI, Anthropic, SiliconFlow)
- Week 7: 其余适配器实现
- Week 8: 适配器测试和优化

**Week 9-10: 缓存和性能优化**

- Week 9: 多层缓存系统
- Week 10: 性能优化和基准测试

**Week 11-12: 后台服务**

- Week 11: 模型发现和健康检查
- Week 12: 监控系统和部署准备

**Week 13-16: 集成和部署**

- Week 13-14: 完整集成测试
- Week 15: 性能对比和调优
- Week 16: 生产部署和文档

## 🛡️ 风险评估和缓解

### 主要技术风险

1. **开发复杂度**: Go 的 interface 和 goroutine 学习曲线

   - **缓解**: 分阶段实施，先实现核心功能

2. **AI 生态缺失**: 缺少 tiktoken 等 Python 库

   - **缓解**: 调用 Python 微服务或自实现 token 计算

3. **业务逻辑迁移**: 复杂路由逻辑的正确性

   - **缓解**: 详细的单元测试和对比测试

4. **性能调优**: Go 的内存管理和 GC 优化
   - **缓解**: 使用 pprof 进行性能分析和优化

### 项目风险

1. **时间超期**: 12-16 周的开发周期较长

   - **缓解**: MVP 优先，分阶段交付

2. **功能回退**: 某些 Python 特性难以实现
   - **缓解**: 保持 Python 版本作为备份

## 💰 成本效益分析

### 开发成本

- **人力成本**: 12-16 周 × 1 开发者
- **学习成本**: Go 语言和生态系统学习
- **测试成本**: 全面的功能和性能测试
- **部署成本**: 新的部署和监控体系

### 预期收益

- **性能提升**: 99% 的启动时间和首次请求改进
- **并发能力**: 20x 的并发处理能力提升
- **资源节约**: 70-80% 的内存使用减少
- **运维简化**: 单二进制部署，无依赖管理

### ROI 分析

- **短期 (3-6 个月)**: 开发成本较高，收益有限
- **中期 (6-12 个月)**: 性能优势显现，运维成本降低
- **长期 (1-2 年)**: 显著的性能和维护优势

---

**总结**: Go 重写方案能够实现显著的性能提升，特别适合对性能有极高要求的场景。虽然开发周期较长，但长期收益明显，特别是在高并发和低延迟要求的生产环境中。
