# -*- coding: utf-8 -*-
"""
Chat请求模型 - 用于适配器系统的统一请求格式
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """聊天消息"""

    role: str = Field(..., description="消息角色")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """Chat完成请求模型"""

    model: str = Field(..., description="模型名称")
    messages: List[Union[Dict[str, Any], ChatMessage]] = Field(
        ..., description="消息列表"
    )
    temperature: Optional[float] = Field(None, description="温度参数", ge=0, le=2)
    max_tokens: Optional[int] = Field(None, description="最大token数", ge=1)
    top_p: Optional[float] = Field(None, description="top_p参数", ge=0, le=1)
    frequency_penalty: Optional[float] = Field(
        None, description="频率惩罚", ge=-2, le=2
    )
    presence_penalty: Optional[float] = Field(None, description="存在惩罚", ge=-2, le=2)
    stop: Optional[Union[str, List[str]]] = Field(None, description="停止词")
    stream: bool = Field(False, description="是否流式返回")

    # Function calling支持
    functions: Optional[List[Dict[str, Any]]] = Field(None, description="可用函数列表")
    function_call: Optional[Union[str, Dict[str, Any]]] = Field(
        None, description="函数调用设置"
    )
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="工具列表")
    tool_choice: Optional[Union[str, Dict[str, Any]]] = Field(
        None, description="工具选择设置"
    )

    # 系统消息支持
    system: Optional[str] = Field(None, description="系统消息")

    # 路由相关参数
    routing_strategy: Optional[str] = Field("balanced", description="路由策略")
    required_capabilities: Optional[List[str]] = Field(None, description="必需能力")

    # 扩展参数
    extra_params: Optional[Dict[str, Any]] = Field(None, description="额外参数")

    class Config:
        extra = "allow"  # 允许额外字段

    def dict(self, **kwargs):
        """重写dict方法，确保兼容性"""
        result = super().dict(**kwargs)

        # 处理消息格式
        if self.messages:
            processed_messages = []
            for msg in self.messages:
                if isinstance(msg, ChatMessage):
                    processed_messages.append(msg.dict())
                else:
                    processed_messages.append(msg)
            result["messages"] = processed_messages

        return result
