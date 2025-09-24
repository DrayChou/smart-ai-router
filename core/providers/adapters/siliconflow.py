"""
SiliconFlow Provider Adapter - 统一格式版本

专注于从统一格式定价文件中加载模型信息，提供一致的数据访问接口。
"""

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from ..base import BaseAdapter, ChatRequest, ChatResponse, ModelInfo

logger = logging.getLogger(__name__)


@dataclass
class SiliconFlowModelPricing:
    """SiliconFlow模型定价信息"""

    model_name: str
    display_name: str
    input_price: float  # USD per token
    output_price: float  # USD per token
    context_length: Optional[int] = None
    description: Optional[str] = None
    capabilities: Optional[list[str]] = None


class SiliconFlowAdapter(BaseAdapter):
    """SiliconFlow适配器 - 统一格式版本"""

    def __init__(self, provider_name: str = "siliconflow", config: dict = None):
        if config is None:
            config = {
                "base_url": "https://api.siliconflow.cn",
                "auth_type": "bearer",
                "timeout": 30,
            }
        super().__init__(provider_name, config)
        self.base_url = "https://api.siliconflow.cn"
        self._cached_pricing: Optional[dict[str, SiliconFlowModelPricing]] = None

        # 只使用统一格式文件
        self.unified_pricing_path = Path("config/pricing/siliconflow_unified.json")

    async def discover_models(self, api_key: str, timeout: int = 30) -> list[str]:
        """发现SiliconFlow可用模型"""
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            # 尝试从API获取模型列表
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{self.base_url}/v1/models", headers=headers
                )
                response.raise_for_status()

                models_data = response.json()
                if "data" in models_data:
                    models = [model["id"] for model in models_data["data"]]
                    logger.info(f"SiliconFlow: 从API发现 {len(models)} 个模型")
                    return models
                else:
                    logger.warning("SiliconFlow: 无效的模型列表响应格式")

        except Exception as e:
            logger.error(f"SiliconFlow模型发现失败: {e}")

        # 回退到统一格式配置文件中的模型列表
        try:
            pricing_data = await self._load_unified_pricing()
            json_models = list(pricing_data.keys())
            logger.info(
                f"SiliconFlow: 从统一格式配置文件获取 {len(json_models)} 个模型"
            )
            return json_models
        except Exception as e:
            logger.error(f"从统一格式配置文件加载模型列表失败: {e}")
            return []

    async def _load_unified_pricing(self) -> dict[str, SiliconFlowModelPricing]:
        """加载统一格式定价数据"""
        if self._cached_pricing:
            return self._cached_pricing

        try:
            if not self.unified_pricing_path.exists():
                logger.error(f"统一格式定价文件不存在: {self.unified_pricing_path}")
                raise FileNotFoundError(
                    f"统一格式定价文件不存在: {self.unified_pricing_path}"
                )

            # 导入统一格式加载器
            project_root = Path(__file__).parent.parent.parent.parent
            sys.path.insert(0, str(project_root))
            from core.pricing.unified_format import UnifiedPricingFile

            unified_data = UnifiedPricingFile.load_from_file(self.unified_pricing_path)
            logger.info(f"加载统一格式定价数据: {unified_data.description}")

            pricing_data = {}
            for model_id, model_data in unified_data.models.items():
                # 提取价格信息 (已经是USD per token)
                input_price = model_data.pricing.prompt if model_data.pricing else 0.0
                output_price = (
                    model_data.pricing.completion if model_data.pricing else 0.0
                )

                # 构建显示名称
                display_name = model_data.name or model_id
                if display_name == model_id and "/" in model_id:
                    display_name = model_id.split("/")[-1]

                # 构建描述
                description = model_data.description or "SiliconFlow模型"
                if input_price == 0 and output_price == 0:
                    description += " (免费)"

                # 添加能力和上下文信息
                if model_data.capabilities:
                    capability_desc = ", ".join(model_data.capabilities[:3])
                    if len(model_data.capabilities) > 3:
                        capability_desc += f" 等{len(model_data.capabilities)}项能力"
                    description += f" - 支持: {capability_desc}"

                if model_data.context_length and model_data.context_length > 8192:
                    description += f" - 上下文: {model_data.context_length:,} tokens"

                pricing_data[model_id] = SiliconFlowModelPricing(
                    model_name=model_id,
                    display_name=display_name,
                    input_price=input_price,
                    output_price=output_price,
                    context_length=model_data.context_length,
                    description=description,
                    capabilities=model_data.capabilities,
                )

            self._cached_pricing = pricing_data
            logger.info(f"统一格式加载完成: {len(pricing_data)} 个模型")
            return pricing_data

        except Exception as e:
            logger.error(f"加载统一格式定价数据失败: {e}")
            raise

    async def get_model_pricing(self, model_name: str) -> Optional[dict[str, Any]]:
        """获取特定模型的定价信息"""
        try:
            pricing_data = await self._load_unified_pricing()

            model_pricing = pricing_data.get(model_name)
            if not model_pricing:
                return None

            return {
                "model_name": model_pricing.model_name,
                "display_name": model_pricing.display_name,
                "input_price": model_pricing.input_price,
                "output_price": model_pricing.output_price,
                "context_length": model_pricing.context_length,
                "description": model_pricing.description,
                "capabilities": model_pricing.capabilities or [],
                "is_free": (
                    model_pricing.input_price == 0 and model_pricing.output_price == 0
                ),
            }

        except Exception as e:
            logger.error(f"获取模型定价失败 ({model_name}): {e}")
            return None

    async def list_models(self, api_key: str, timeout: int = 30) -> list[ModelInfo]:
        """列出所有可用模型"""
        try:
            models = await self.discover_models(api_key, timeout)
            pricing_data = await self._load_unified_pricing()

            model_infos = []
            for model_id in models:
                model_pricing = pricing_data.get(model_id)
                if model_pricing:
                    model_infos.append(
                        ModelInfo(
                            id=model_id,
                            name=model_pricing.display_name,
                            description=model_pricing.description,
                            context_length=model_pricing.context_length,
                            input_price=model_pricing.input_price,
                            output_price=model_pricing.output_price,
                        )
                    )
                else:
                    # 基本信息，无定价数据
                    model_infos.append(
                        ModelInfo(
                            id=model_id,
                            name=(
                                model_id.split("/")[-1] if "/" in model_id else model_id
                            ),
                            description=f"SiliconFlow模型 {model_id}",
                            context_length=8192,
                            input_price=0.0,
                            output_price=0.0,
                        )
                    )

            return model_infos

        except Exception as e:
            logger.error(f"列出模型失败: {e}")
            return []

    async def chat_completions(
        self, request: ChatRequest, api_key: str
    ) -> ChatResponse:
        """聊天补全 - 通过SiliconFlow API"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # 构建请求数据
        request_data = {
            "model": request.model,
            "messages": [
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                for msg in request.messages
            ],
            "stream": False,
        }

        # 添加可选参数
        if request.temperature is not None:
            request_data["temperature"] = request.temperature
        if request.max_tokens is not None:
            request_data["max_tokens"] = request.max_tokens
        # Add top_p from extra_params if available
        if request.extra_params and "top_p" in request.extra_params:
            request_data["top_p"] = request.extra_params["top_p"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=request_data,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()

            return ChatResponse(
                id=result.get("id", ""),
                model=result.get("model", request.model),
                choices=[
                    {
                        "message": {
                            "role": choice["message"]["role"],
                            "content": choice["message"]["content"],
                        },
                        "finish_reason": choice.get("finish_reason"),
                    }
                    for choice in result.get("choices", [])
                ],
                usage=result.get("usage", {}),
            )

    async def chat_completions_stream(self, request: ChatRequest, api_key: str):
        """流式聊天补全 - 通过SiliconFlow API"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # 构建请求数据
        request_data = {
            "model": request.model,
            "messages": [
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                for msg in request.messages
            ],
            "stream": True,
        }

        # 添加可选参数
        if request.temperature is not None:
            request_data["temperature"] = request.temperature
        if request.max_tokens is not None:
            request_data["max_tokens"] = request.max_tokens
        # Add top_p from extra_params if available
        if request.extra_params and "top_p" in request.extra_params:
            request_data["top_p"] = request.extra_params["top_p"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=request_data,
                headers=headers,
            ) as response:
                response.raise_for_status()

                async for chunk in response.aiter_text():
                    if chunk.strip():
                        # 处理Server-Sent Events格式
                        if chunk.startswith("data: "):
                            chunk_data = chunk[6:].strip()
                            if chunk_data == "[DONE]":
                                break
                            try:
                                yield json.loads(chunk_data)
                            except json.JSONDecodeError:
                                continue
