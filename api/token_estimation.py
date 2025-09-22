#!/usr/bin/env python3
"""
Token预估和模型优化API接口
"""

from typing import List, Dict, Any, Optional
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.utils.token_estimator import (
    get_token_estimator, 
    get_model_optimizer, 
    TokenEstimate, 
    ModelRecommendation,
    TaskComplexity
)
from core.yaml_config import get_yaml_config_loader

logger = logging.getLogger(__name__)

# --- Request/Response Models ---

class ChatMessage(BaseModel):
    role: str
    content: str

class TokenEstimationRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    messages: List[ChatMessage]
    model_family: str = "gpt"
    optimization_strategy: str = "balanced"  # cost_first, quality_first, speed_first, balanced
    max_recommendations: int = 10

class TokenEstimationResponse(BaseModel):
    input_tokens: int
    estimated_output_tokens: int
    total_tokens: int
    confidence: float
    task_complexity: str
    recommendations: List[Dict[str, Any]]
    optimization_strategy: str

class ModelPricingRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_name: str
    provider: str
    input_tokens: int
    output_tokens: int

class ModelPricingResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_name: str
    provider: str
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    currency: str = "USD"

def create_token_estimation_router(config_loader) -> APIRouter:
    """创建Token预估路由"""
    router = APIRouter(prefix="/v1/token", tags=["token-estimation"])

    @router.post("/estimate", response_model=TokenEstimationResponse)
    async def estimate_tokens(request: TokenEstimationRequest):
        """Token预估和模型推荐"""
        try:
            # 获取预估器和优化器
            token_estimator = get_token_estimator()
            model_optimizer = get_model_optimizer()

            # 转换消息格式
            messages = [{'role': msg.role, 'content': msg.content} for msg in request.messages]

            # 执行Token预估
            token_estimate = token_estimator.estimate_tokens(messages, request.model_family)

            # 获取可用渠道
            all_channels = config_loader.get_enabled_channels()
            if not all_channels:
                raise HTTPException(status_code=503, detail="No available channels")

            # 准备渠道信息
            available_channels = []
            for channel in all_channels[:50]:  # 限制处理数量避免性能问题
                available_channels.append({
                    'id': channel.id,
                    'model_name': channel.model_name,
                    'provider': channel.provider,
                    'input_price': getattr(channel, 'input_price', 0.0),
                    'output_price': getattr(channel, 'output_price', 0.0)
                })

            # 生成推荐
            recommendations = model_optimizer.recommend_models(
                token_estimate, 
                available_channels, 
                request.optimization_strategy
            )

            # 构造响应
            rec_data = []
            for rec in recommendations[:request.max_recommendations]:
                rec_data.append({
                    'model_name': rec.model_name,
                    'channel_id': rec.channel_id,
                    'estimated_cost': rec.estimated_cost,
                    'estimated_time_seconds': rec.estimated_time,
                    'quality_score': rec.quality_score,
                    'reason': rec.reason,
                    'formatted_cost': f"${rec.estimated_cost:.6f}" if rec.estimated_cost > 0 else "Free"
                })

            return TokenEstimationResponse(
                input_tokens=token_estimate.input_tokens,
                estimated_output_tokens=token_estimate.estimated_output_tokens,
                total_tokens=token_estimate.total_tokens,
                confidence=token_estimate.confidence,
                task_complexity=token_estimate.task_complexity.value,
                recommendations=rec_data,
                optimization_strategy=request.optimization_strategy
            )

        except Exception as e:
            logger.error(f"Token预估失败: {e}")
            raise HTTPException(status_code=500, detail=f"Token预估失败: {str(e)}")

    @router.post("/pricing", response_model=ModelPricingResponse)
    async def calculate_model_pricing(request: ModelPricingRequest):
        """计算特定模型的精确定价"""
        try:
            model_optimizer = get_model_optimizer()

            # 查找匹配的渠道
            all_channels = config_loader.get_enabled_channels()
            matching_channel = None

            for channel in all_channels:
                if (channel.model_name.lower() == request.model_name.lower() and 
                    channel.provider.lower() == request.provider.lower()):
                    matching_channel = channel
                    break

            if not matching_channel:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Model {request.model_name} from {request.provider} not found"
                )

            # 获取定价信息
            input_price = getattr(matching_channel, 'input_price', 0.0)
            output_price = getattr(matching_channel, 'output_price', 0.0)

            # 计算成本（价格通常是每百万token）
            input_cost = (request.input_tokens / 1000000) * input_price
            output_cost = (request.output_tokens / 1000000) * output_price
            total_cost = input_cost + output_cost

            return ModelPricingResponse(
                model_name=request.model_name,
                provider=request.provider,
                input_tokens=request.input_tokens,
                output_tokens=request.output_tokens,
                input_cost=input_cost,
                output_cost=output_cost,
                total_cost=total_cost
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"定价计算失败: {e}")
            raise HTTPException(status_code=500, detail=f"定价计算失败: {str(e)}")

    @router.get("/complexity/{text}")
    async def detect_task_complexity(text: str):
        """检测文本的任务复杂度"""
        try:
            token_estimator = get_token_estimator()
            
            # 模拟消息格式
            messages = [{'role': 'user', 'content': text}]
            complexity = token_estimator.detect_task_complexity(messages)
            
            return {
                'text': text[:100] + ('...' if len(text) > 100 else ''),
                'complexity': complexity.value,
                'description': {
                    'simple': '简单对话、翻译等基础任务',
                    'moderate': '文档总结、问答等中等任务', 
                    'complex': '代码生成、分析等复杂任务',
                    'expert': '专业研究、复杂推理等专家级任务'
                }.get(complexity.value, '未知复杂度')
            }

        except Exception as e:
            logger.error(f"复杂度检测失败: {e}")
            raise HTTPException(status_code=500, detail=f"复杂度检测失败: {str(e)}")

    @router.get("/models/quality")
    async def get_model_quality_scores():
        """获取所有模型的质量评分"""
        try:
            model_optimizer = get_model_optimizer()
            
            # 获取所有可用模型
            all_channels = config_loader.get_enabled_channels()
            model_scores = {}
            
            for channel in all_channels:
                model_name = channel.model_name
                if model_name not in model_scores:
                    quality_score = model_optimizer.get_model_quality_score(model_name)
                    speed_score = model_optimizer.get_model_speed_score(model_name, channel.provider)
                    
                    model_scores[model_name] = {
                        'quality_score': quality_score,
                        'speed_score': speed_score,
                        'providers': []
                    }
                
                model_scores[model_name]['providers'].append({
                    'provider': channel.provider,
                    'channel_id': channel.id,
                    'input_price': getattr(channel, 'input_price', 0.0),
                    'output_price': getattr(channel, 'output_price', 0.0)
                })
            
            # 按质量评分排序
            sorted_models = dict(sorted(model_scores.items(), key=lambda x: x[1]['quality_score'], reverse=True))
            
            return {
                'total_models': len(sorted_models),
                'models': sorted_models
            }

        except Exception as e:
            logger.error(f"获取模型质量评分失败: {e}")
            raise HTTPException(status_code=500, detail=f"获取模型质量评分失败: {str(e)}")

    @router.get("/strategies")
    async def get_optimization_strategies():
        """获取所有可用的优化策略"""
        return {
            'strategies': {
                'cost_first': {
                    'name': '成本优先',
                    'description': '优先选择最便宜的模型，免费 > 低成本 > 性价比',
                    'suitable_for': ['个人开发者', '成本敏感应用', '大量请求场景']
                },
                'quality_first': {
                    'name': '质量优先', 
                    'description': '优先选择高质量模型，质量 > 速度 > 成本',
                    'suitable_for': ['专业应用', '重要任务', '质量要求高的场景']
                },
                'speed_first': {
                    'name': '速度优先',
                    'description': '优先选择响应最快的模型，速度 > 质量 > 成本', 
                    'suitable_for': ['实时应用', '交互式应用', '延迟敏感场景']
                },
                'balanced': {
                    'name': '平衡策略',
                    'description': '综合考虑成本、质量和速度，适用于大多数场景',
                    'suitable_for': ['通用应用', '平衡需求', '默认选择']
                }
            },
            'default': 'balanced'
        }

    return router