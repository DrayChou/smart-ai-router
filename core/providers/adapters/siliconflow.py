# -*- coding: utf-8 -*-
"""
SiliconFlow Provider Adapter - 简化版本，仅从JSON配置文件加载数据

这个适配器专注于从预解析的JSON配置文件中加载模型信息，
不再包含复杂的网页抓取和HTML解析逻辑。
"""
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path

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
    capabilities: Optional[List[str]] = None


class SiliconFlowAdapter(BaseAdapter):
    """SiliconFlow适配器 - 从HTML解析的JSON配置文件加载数据"""

    def __init__(self, provider_name: str = "siliconflow", config: dict = None):
        if config is None:
            config = {
                "base_url": "https://api.siliconflow.cn",
                "auth_type": "bearer",
                "timeout": 30,
            }
        super().__init__(provider_name, config)
        self.base_url = "https://api.siliconflow.cn"
        self._cached_pricing: Optional[Dict[str, SiliconFlowModelPricing]] = None
        self.pricing_json_path = Path("config/pricing/siliconflow_pricing_from_html.json")

    async def discover_models(self, api_key: str, timeout: int = 30) -> List[str]:
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

        # 回退到JSON配置文件中的模型列表
        try:
            pricing_data = await self._load_pricing_from_json()
            json_models = list(pricing_data.keys())
            logger.info(f"SiliconFlow: 从JSON配置文件获取 {len(json_models)} 个模型")
            return json_models
        except Exception as e:
            logger.error(f"从JSON加载模型列表失败: {e}")
            return []

    async def _load_pricing_from_json(self) -> Dict[str, SiliconFlowModelPricing]:
        """从JSON文件加载定价数据"""
        if self._cached_pricing:
            return self._cached_pricing

        try:
            if not self.pricing_json_path.exists():
                logger.error(f"定价JSON文件不存在: {self.pricing_json_path}")
                raise FileNotFoundError(f"定价JSON文件不存在: {self.pricing_json_path}")
            
            with open(self.pricing_json_path, 'r', encoding='utf-8') as f:
                pricing_json = json.load(f)
            
            models_data = pricing_json.get('models', {})
            exchange_rate = pricing_json.get('exchange_rate_to_usd', 0.14)
            data_source = pricing_json.get('data_source', 'Unknown')
            
            logger.info(f"加载定价数据，来源: {data_source}")
            
            pricing_data = {}
            for model_name, model_info in models_data.items():
                # 从JSON中获取价格信息 (元/M tokens)
                input_price_per_m = model_info.get('input_price_per_m', 0.0)
                output_price_per_m = model_info.get('output_price_per_m', 0.0)
                
                # 获取模型元数据
                description = model_info.get('description', 'Standard model')
                context_length = model_info.get('context_length', 8192)
                capabilities = model_info.get('capabilities', [])
                display_name = model_info.get('display_name', model_name)
                category = model_info.get('category', 'standard')
                
                # 价格转换: 元/M tokens -> USD/token
                input_price_per_token = (input_price_per_m * exchange_rate) / 1_000_000
                output_price_per_token = (output_price_per_m * exchange_rate) / 1_000_000
                
                # 构建更详细的显示名称
                model_display_name = display_name
                if display_name == model_name:
                    model_display_name = (
                        f"{model_name.split('/')[-1]} ({description})"
                        if "/" in model_name
                        else f"{model_name} ({description})"
                    )
                
                # 构建描述信息
                desc_parts = [f"SiliconFlow {description}"]
                if input_price_per_m == 0 and output_price_per_m == 0:
                    desc_parts.append("(免费)")
                else:
                    desc_parts.append(f"(输入: {input_price_per_m}元/M, 输出: {output_price_per_m}元/M)")
                
                if context_length > 8192:
                    desc_parts.append(f"上下文: {context_length:,} tokens")
                
                if capabilities:
                    capability_desc = ", ".join(capabilities[:3])  # 只显示前3个能力
                    if len(capabilities) > 3:
                        capability_desc += f" 等{len(capabilities)}项能力"
                    desc_parts.append(f"支持: {capability_desc}")
                
                pricing_data[model_name] = SiliconFlowModelPricing(
                    model_name=model_name,
                    display_name=model_display_name,
                    input_price=input_price_per_token,
                    output_price=output_price_per_token,
                    context_length=context_length,
                    description=" | ".join(desc_parts),
                    capabilities=capabilities
                )
            
            self._cached_pricing = pricing_data
            logger.info(f"成功从JSON加载 {len(pricing_data)} 个模型的定价信息")
            return pricing_data
            
        except Exception as e:
            logger.error(f"加载JSON定价文件失败: {e}")
            raise

    async def get_model_pricing(self, model_name: str) -> Optional[Dict[str, Any]]:
        """获取特定模型的定价信息"""
        try:
            pricing_data = await self._load_pricing_from_json()
            
            if model_name in pricing_data:
                pricing = pricing_data[model_name]
                return {
                    "prompt": str(pricing.input_price),
                    "completion": str(pricing.output_price),
                    "request": "0",
                    "image": "0",
                    "audio": "0",
                    "web_search": "0",
                    "internal_reasoning": "0",
                }
            else:
                logger.warning(f"模型 {model_name} 不在定价数据中")
                return None
                
        except Exception as e:
            logger.error(f"获取模型定价失败: {e}")
            return None

    async def enhance_model_data(
        self, model_name: str, base_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """增强模型数据 - 添加定价和元数据信息"""
        try:
            pricing_data = await self._load_pricing_from_json()
            
            if model_name in pricing_data:
                model_pricing = pricing_data[model_name]
                
                # 添加定价信息
                pricing = await self.get_model_pricing(model_name)
                if pricing:
                    if "raw_data" not in base_data:
                        base_data["raw_data"] = {}
                    base_data["raw_data"]["pricing"] = pricing
                
                # 添加显示名称和描述
                base_data["raw_data"]["name"] = model_pricing.display_name
                if model_pricing.description:
                    base_data["raw_data"]["description"] = model_pricing.description
                
                # 添加上下文长度
                if model_pricing.context_length:
                    base_data["raw_data"]["context_length"] = model_pricing.context_length
                
                # 添加能力信息
                if model_pricing.capabilities:
                    base_data["raw_data"]["capabilities"] = model_pricing.capabilities
                    
                logger.debug(f"已增强模型 {model_name} 的数据")
            else:
                logger.warning(f"未找到模型 {model_name} 的定价数据，使用默认数据")
                
        except Exception as e:
            logger.error(f"增强模型数据失败 {model_name}: {e}")
        
        return base_data

    def clear_pricing_cache(self):
        """清除定价缓存 - 用于强制重新加载JSON文件"""
        self._cached_pricing = None
        logger.info("SiliconFlow定价缓存已清除")
    
    def get_pricing_json_path(self) -> Path:
        """获取定价JSON文件路径"""
        return self.pricing_json_path
    
    def set_pricing_json_path(self, path: Path):
        """设置定价JSON文件路径"""
        self.pricing_json_path = path
        self.clear_pricing_cache()  # 清除缓存以便使用新路径
        logger.info(f"SiliconFlow定价JSON路径已更新: {path}")

    async def get_model_capabilities(self, model_name: str) -> List[str]:
        """获取模型能力列表"""
        try:
            pricing_data = await self._load_pricing_from_json()
            if model_name in pricing_data:
                return pricing_data[model_name].capabilities or []
            else:
                return []
        except Exception as e:
            logger.error(f"获取模型能力失败 {model_name}: {e}")
            return []

    async def get_model_context_length(self, model_name: str) -> int:
        """获取模型上下文长度"""
        try:
            pricing_data = await self._load_pricing_from_json()
            if model_name in pricing_data:
                return pricing_data[model_name].context_length or 8192
            else:
                return 8192
        except Exception as e:
            logger.error(f"获取模型上下文长度失败 {model_name}: {e}")
            return 8192

    async def get_all_models_summary(self) -> Dict[str, Any]:
        """获取所有模型的汇总信息"""
        try:
            pricing_data = await self._load_pricing_from_json()
            
            summary = {
                "total_models": len(pricing_data),
                "free_models": 0,
                "paid_models": 0,
                "categories": {},
                "capabilities": set(),
                "max_context_length": 0,
                "sample_models": []
            }
            
            for model_name, model_info in pricing_data.items():
                # 统计免费和付费模型
                if model_info.input_price == 0 and model_info.output_price == 0:
                    summary["free_models"] += 1
                else:
                    summary["paid_models"] += 1
                
                # 收集能力
                if model_info.capabilities:
                    summary["capabilities"].update(model_info.capabilities)
                
                # 记录最大上下文长度
                if model_info.context_length:
                    summary["max_context_length"] = max(
                        summary["max_context_length"], 
                        model_info.context_length
                    )
                
                # 采样模型信息
                if len(summary["sample_models"]) < 5:
                    summary["sample_models"].append({
                        "name": model_name,
                        "display_name": model_info.display_name,
                        "context_length": model_info.context_length,
                        "capabilities": model_info.capabilities or []
                    })
            
            summary["capabilities"] = list(summary["capabilities"])
            logger.info(f"生成模型汇总: {summary['total_models']} 个模型")
            return summary
            
        except Exception as e:
            logger.error(f"生成模型汇总失败: {e}")
            return {
                "total_models": 0,
                "error": str(e)
            }

    # 实现基础适配器的抽象方法
    async def chat_completions(
        self, request: ChatRequest, api_key: str, **kwargs
    ) -> ChatResponse:
        """执行聊天补全请求"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": request.model,
            "messages": request.messages,
            "stream": False,
        }
        
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
            
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            choice = data["choices"][0]
            
            return ChatResponse(
                content=choice["message"]["content"],
                finish_reason=choice["finish_reason"],
                usage=data["usage"],
                model=data["model"],
                provider_response=data,
                tools_called=choice["message"].get("tool_calls")
            )

    async def chat_completions_stream(
        self, request: ChatRequest, api_key: str, **kwargs
    ):
        """执行流式聊天补全请求"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": request.model,
            "messages": request.messages,
            "stream": True,
        }
        
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
            
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue

    async def list_models(self, api_key: str) -> List[ModelInfo]:
        """获取可用模型列表"""
        try:
            models_list = await self.discover_models(api_key)
            pricing_data = await self._load_pricing_from_json()
            
            model_infos = []
            for model_name in models_list:
                if model_name in pricing_data:
                    pricing_info = pricing_data[model_name]
                    
                    # 价格转换为每1K tokens的成本 (从每token转换)
                    input_cost_1k = pricing_info.input_price * 1000
                    output_cost_1k = pricing_info.output_price * 1000
                    
                    model_infos.append(ModelInfo(
                        id=model_name,
                        name=pricing_info.display_name,
                        provider="siliconflow",
                        capabilities=pricing_info.capabilities or ["chat"],
                        context_length=pricing_info.context_length or 8192,
                        input_cost_per_1k=input_cost_1k,
                        output_cost_per_1k=output_cost_1k,
                        speed_score=1.0
                    ))
                else:
                    model_infos.append(ModelInfo(
                        id=model_name,
                        name=model_name,
                        provider="siliconflow",
                        capabilities=["chat"],
                        context_length=8192,
                        input_cost_per_1k=0.0,
                        output_cost_per_1k=0.0,
                        speed_score=1.0
                    ))
            
            return model_infos
            
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return []