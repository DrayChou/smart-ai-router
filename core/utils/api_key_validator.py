#!/usr/bin/env python3
"""
API密钥验证和自动失效检测模块
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class APIKeyValidationResult:
    """API密钥验证结果"""

    channel_id: str
    provider: str
    api_key: str
    is_valid: bool
    error_type: Optional[
        str
    ]  # "invalid_key", "quota_exceeded", "rate_limit", "network_error", "unknown"
    error_message: Optional[str]
    status_code: Optional[int]
    latency_ms: Optional[float]
    timestamp: datetime
    models_discovered: Optional[list[dict]] = None
    model_count: int = 0


@dataclass
class APIKeyStatus:
    """API密钥状态"""

    channel_id: str
    provider: str
    api_key: str
    is_valid: bool
    last_validated: datetime
    consecutive_failures: int
    next_validation: datetime
    health_score: float  # 0.0 - 1.0
    usage_stats: dict[str, Any]


class APIKeyValidator:
    """API密钥验证器"""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

        # 缓存文件路径
        self.validation_cache_file = self.cache_dir / "api_key_validation.json"
        self.key_status_file = self.cache_dir / "api_key_status.json"

        # 验证结果和状态
        self.validation_results: dict[str, APIKeyValidationResult] = {}
        self.key_status: dict[str, APIKeyStatus] = {}

        # 验证配置
        self.validation_timeout = httpx.Timeout(15.0, connect=5.0)
        self.max_consecutive_failures = 3
        self.validation_interval = timedelta(hours=6)  # 每6小时验证一次
        self.backoff_multiplier = 2.0
        self.max_backoff = timedelta(days=1)

        # 加载现有数据
        self._load_cache()

    def _load_cache(self):
        """加载缓存的验证数据"""
        try:
            if self.validation_cache_file.exists():
                with open(self.validation_cache_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.validation_results = {
                        k: APIKeyValidationResult(**v)
                        for k, v in data.get("validation_results", {}).items()
                    }
                logger.info(
                    f"已加载API密钥验证缓存: {len(self.validation_results)} 个密钥"
                )

            if self.key_status_file.exists():
                with open(self.key_status_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.key_status = {
                        k: APIKeyStatus(**v)
                        for k, v in data.get("key_status", {}).items()
                    }
                logger.info(f"已加载API密钥状态: {len(self.key_status)} 个密钥")
        except Exception as e:
            logger.warning(f"加载API密钥验证缓存失败: {e}")

    def _save_cache(self):
        """保存验证数据到缓存"""
        try:
            cache_data = {
                "validation_results": {
                    k: asdict(v) for k, v in self.validation_results.items()
                },
                "key_status": {k: asdict(v) for k, v in self.key_status.items()},
                "last_update": datetime.now().isoformat(),
            }

            with open(self.validation_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)

            logger.info("API密钥验证数据已保存到缓存")
        except Exception as e:
            logger.error(f"保存API密钥验证缓存失败: {e}")

    def _classify_error(self, status_code: int, error_message: str) -> str:
        """分类错误类型"""
        if status_code == 401:
            return "invalid_key"
        elif status_code == 403:
            if "quota" in error_message.lower() or "limit" in error_message.lower():
                return "quota_exceeded"
            else:
                return "invalid_key"
        elif status_code == 429:
            return "rate_limit"
        elif status_code >= 500:
            return "server_error"
        elif status_code == 0 or "connection" in error_message.lower():
            return "network_error"
        else:
            return "unknown"

    def _calculate_backoff(self, consecutive_failures: int) -> timedelta:
        """计算退避时间"""
        base_interval = self.validation_interval
        backoff_factor = min(
            self.backoff_multiplier**consecutive_failures, 24
        )  # 最大24倍
        return min(base_interval * backoff_factor, self.max_backoff)

    async def _validate_openai_key(
        self, channel: dict[str, Any]
    ) -> APIKeyValidationResult:
        """验证OpenAI格式的API密钥"""
        channel_id = channel.get("id", "unknown")
        provider = channel.get("provider", "unknown")
        api_key = channel.get("api_key", "")
        base_url = channel.get("base_url", "https://api.openai.com")

        start_time = time.time()

        try:
            # 尝试获取模型列表
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=self.validation_timeout) as client:
                # 构建模型列表URL
                if base_url.endswith("/"):
                    models_url = f"{base_url}v1/models"
                else:
                    models_url = f"{base_url}/v1/models"

                response = await client.get(models_url, headers=headers)
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000

                if response.status_code == 200:
                    # 解析模型列表
                    try:
                        response_data = response.json()
                        models = response_data.get("data", [])
                        model_count = len(models)

                        return APIKeyValidationResult(
                            channel_id=channel_id,
                            provider=provider,
                            api_key=api_key,
                            is_valid=True,
                            error_type=None,
                            error_message=None,
                            status_code=response.status_code,
                            latency_ms=latency_ms,
                            timestamp=datetime.now(),
                            models_discovered=models,
                            model_count=model_count,
                        )
                    except json.JSONDecodeError:
                        return APIKeyValidationResult(
                            channel_id=channel_id,
                            provider=provider,
                            api_key=api_key,
                            is_valid=False,
                            error_type="invalid_response",
                            error_message="Invalid JSON response",
                            status_code=response.status_code,
                            latency_ms=latency_ms,
                            timestamp=datetime.now(),
                        )
                else:
                    error_type = self._classify_error(
                        response.status_code, response.text
                    )
                    return APIKeyValidationResult(
                        channel_id=channel_id,
                        provider=provider,
                        api_key=api_key,
                        is_valid=False,
                        error_type=error_type,
                        error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        timestamp=datetime.now(),
                    )

        except Exception as e:
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            error_type = (
                "network_error" if "connection" in str(e).lower() else "unknown"
            )

            return APIKeyValidationResult(
                channel_id=channel_id,
                provider=provider,
                api_key=api_key,
                is_valid=False,
                error_type=error_type,
                error_message=f"Connection error: {str(e)}",
                status_code=0,
                latency_ms=latency_ms,
                timestamp=datetime.now(),
            )

    async def _validate_anthropic_key(
        self, channel: dict[str, Any]
    ) -> APIKeyValidationResult:
        """验证Anthropic格式的API密钥"""
        channel_id = channel.get("id", "unknown")
        provider = channel.get("provider", "unknown")
        api_key = channel.get("api_key", "")
        base_url = channel.get("base_url", "https://api.anthropic.com")

        start_time = time.time()

        try:
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=self.validation_timeout) as client:
                # 构建消息URL
                if base_url.endswith("/"):
                    messages_url = f"{base_url}v1/messages"
                else:
                    messages_url = f"{base_url}/v1/messages"

                # 发送一个最小的测试消息
                test_payload = {
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "test"}],
                }

                response = await client.post(
                    messages_url, json=test_payload, headers=headers
                )
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000

                if response.status_code == 200:
                    return APIKeyValidationResult(
                        channel_id=channel_id,
                        provider=provider,
                        api_key=api_key,
                        is_valid=True,
                        error_type=None,
                        error_message=None,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        timestamp=datetime.now(),
                    )
                else:
                    error_type = self._classify_error(
                        response.status_code, response.text
                    )
                    return APIKeyValidationResult(
                        channel_id=channel_id,
                        provider=provider,
                        api_key=api_key,
                        is_valid=False,
                        error_type=error_type,
                        error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        timestamp=datetime.now(),
                    )

        except Exception as e:
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            error_type = (
                "network_error" if "connection" in str(e).lower() else "unknown"
            )

            return APIKeyValidationResult(
                channel_id=channel_id,
                provider=provider,
                api_key=api_key,
                is_valid=False,
                error_type=error_type,
                error_message=f"Connection error: {str(e)}",
                status_code=0,
                latency_ms=latency_ms,
                timestamp=datetime.now(),
            )

    async def validate_api_key(self, channel: dict[str, Any]) -> APIKeyValidationResult:
        """验证单个API密钥"""
        channel_id = channel.get("id", "unknown")
        provider = channel.get("provider", "unknown")
        api_key = channel.get("api_key", "")

        # 检查是否需要跳过验证
        if not api_key or len(api_key.strip()) < 10:
            return APIKeyValidationResult(
                channel_id=channel_id,
                provider=provider,
                api_key=api_key,
                is_valid=False,
                error_type="invalid_key",
                error_message="API key is empty or too short",
                status_code=0,
                latency_ms=0,
                timestamp=datetime.now(),
            )

        # 根据provider类型选择验证方法
        if provider.lower() in ["anthropic"]:
            return await self._validate_anthropic_key(channel)
        else:
            # 默认使用OpenAI格式验证
            return await self._validate_openai_key(channel)

    async def validate_all_keys(
        self, channels: list[dict[str, Any]]
    ) -> dict[str, APIKeyValidationResult]:
        """验证所有API密钥"""
        if not channels:
            logger.warning("没有可验证的API密钥")
            return {}

        logger.info(f"开始验证 {len(channels)} 个API密钥")

        # 并发验证所有密钥
        tasks = []
        for channel in channels:
            task = self.validate_api_key(channel)
            tasks.append(task)

        # 执行并发验证，限制并发数
        semaphore = asyncio.Semaphore(5)  # 最多5个并发请求

        async def limited_validation(task):
            async with semaphore:
                return await task

        results = await asyncio.gather(
            *[limited_validation(task) for task in tasks], return_exceptions=True
        )

        # 处理结果
        validation_results = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"API密钥验证出错: {result}")
                continue
            if isinstance(result, APIKeyValidationResult):
                validation_results[result.channel_id] = result

                # 更新密钥状态
                self._update_key_status(result)

        self.validation_results.update(validation_results)

        # 保存缓存
        self._save_cache()

        # 打印统计信息
        self._log_validation_summary()

        return validation_results

    def _update_key_status(self, result: APIKeyValidationResult):
        """更新API密钥状态"""
        channel_id = result.channel_id

        # 获取现有状态或创建新状态
        current_status = self.key_status.get(channel_id)
        if current_status is None:
            current_status = APIKeyStatus(
                channel_id=channel_id,
                provider=result.provider,
                api_key=result.api_key,
                is_valid=result.is_valid,
                last_validated=result.timestamp,
                consecutive_failures=0,
                next_validation=result.timestamp + self.validation_interval,
                health_score=1.0 if result.is_valid else 0.0,
                usage_stats={},
            )

        # 更新状态
        current_status.last_validated = result.timestamp

        if result.is_valid:
            current_status.is_valid = True
            current_status.consecutive_failures = 0
            current_status.health_score = min(1.0, current_status.health_score + 0.1)
            current_status.next_validation = result.timestamp + self.validation_interval
        else:
            current_status.is_valid = False
            current_status.consecutive_failures += 1

            # 根据错误类型调整健康分数
            if result.error_type == "quota_exceeded":
                current_status.health_score *= 0.8  # 配额问题，适度降低
            elif result.error_type == "rate_limit":
                current_status.health_score *= 0.9  # 限流问题，轻微降低
            elif result.error_type == "invalid_key":
                current_status.health_score = 0.0  # 无效密钥，直接降为0
            else:
                current_status.health_score *= 0.7  # 其他错误，显著降低

            # 计算下次验证时间（退避策略）
            backoff_time = self._calculate_backoff(current_status.consecutive_failures)
            current_status.next_validation = result.timestamp + backoff_time

        # 更新使用统计
        if result.models_discovered:
            current_status.usage_stats["model_count"] = result.model_count
            current_status.usage_stats["last_model_discovery"] = (
                result.timestamp.isoformat()
            )

        self.key_status[channel_id] = current_status

    def _log_validation_summary(self):
        """打印验证摘要"""
        total_keys = len(self.validation_results)
        valid_keys = sum(1 for r in self.validation_results.values() if r.is_valid)

        logger.info("=== API密钥验证完成 ===")
        logger.info(f"总密钥数: {total_keys}")
        logger.info(f"有效密钥: {valid_keys}")
        logger.info(f"无效密钥: {total_keys - valid_keys}")
        logger.info(f"有效率: {valid_keys/total_keys*100:.1f}%")

        # 按错误类型统计
        error_types = {}
        for result in self.validation_results.values():
            if not result.is_valid and result.error_type:
                error_types[result.error_type] = (
                    error_types.get(result.error_type, 0) + 1
                )

        for error_type, count in error_types.items():
            logger.info(f"{error_type}: {count} 个")

    def get_valid_channels(self) -> list[str]:
        """获取有效的渠道ID列表"""
        return [
            channel_id
            for channel_id, status in self.key_status.items()
            if status.is_valid and status.health_score > 0.5
        ]

    def get_invalid_channels(self) -> list[str]:
        """获取无效的渠道ID列表"""
        return [
            channel_id
            for channel_id, status in self.key_status.items()
            if not status.is_valid or status.health_score <= 0.5
        ]

    def get_channel_validation_result(
        self, channel_id: str
    ) -> Optional[APIKeyValidationResult]:
        """获取指定渠道的验证结果"""
        return self.validation_results.get(channel_id)

    def get_channel_status(self, channel_id: str) -> Optional[APIKeyStatus]:
        """获取指定渠道的状态"""
        return self.key_status.get(channel_id)

    def should_validate_channel(self, channel_id: str) -> bool:
        """检查是否应该验证指定渠道"""
        status = self.key_status.get(channel_id)
        if status is None:
            return True

        return datetime.now() >= status.next_validation

    def get_validation_stats(self) -> dict[str, Any]:
        """获取验证统计信息"""
        total = len(self.key_status)
        valid = len([s for s in self.key_status.values() if s.is_valid])

        # 按provider统计
        provider_stats = {}
        for status in self.key_status.values():
            provider = status.provider
            if provider not in provider_stats:
                provider_stats[provider] = {"total": 0, "valid": 0, "avg_health": 0.0}

            provider_stats[provider]["total"] += 1
            if status.is_valid:
                provider_stats[provider]["valid"] += 1
            provider_stats[provider]["avg_health"] += status.health_score

        # 计算平均健康分数
        for _provider, stats in provider_stats.items():
            stats["avg_health"] = stats["avg_health"] / stats["total"]
            stats["success_rate"] = stats["valid"] / stats["total"]

        return {
            "total_keys": total,
            "valid_keys": valid,
            "success_rate": valid / total if total > 0 else 0,
            "provider_stats": provider_stats,
            "last_validation": (
                max(
                    (
                        status.last_validated.isoformat()
                        if isinstance(status.last_validated, datetime)
                        else status.last_validated
                    )
                    for status in self.key_status.values()
                )
                if self.key_status
                else None
            ),
        }


# 主要的任务执行函数
async def run_api_key_validation_task(channels: list[dict[str, Any]]) -> dict[str, Any]:
    """运行API密钥验证任务"""
    validator = APIKeyValidator()
    results = await validator.validate_all_keys(channels)
    stats = validator.get_validation_stats()

    return {
        "results": {k: asdict(v) for k, v in results.items()},
        "stats": stats,
        "valid_channels": validator.get_valid_channels(),
        "invalid_channels": validator.get_invalid_channels(),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    # 测试代码
    async def test_api_key_validation():
        # 示例渠道配置
        test_channels = [
            {
                "id": "test_channel_1",
                "provider": "openai",
                "api_key": "sk-test-key",
                "base_url": "https://api.openai.com",
            },
            {
                "id": "test_channel_2",
                "provider": "anthropic",
                "api_key": "sk-ant-test-key",
                "base_url": "https://api.anthropic.com",
            },
        ]

        result = await run_api_key_validation_task(test_channels)
        print("API密钥验证结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    asyncio.run(test_api_key_validation())
