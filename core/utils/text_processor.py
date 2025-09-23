#!/usr/bin/env python3
"""
文本处理工具模块
提供推理模型输出清理、敏感信息过滤等文本处理功能
"""

import re
from typing import Optional


def remove_thinking_chains(text: str) -> str:
    """
    移除推理模型的思维链标签，支持o1、Claude等推理模型的输出清理

    支持的思维链格式:
    - <think>...</think>           # 标准格式
    - <thinking>...</thinking>     # Claude格式
    - <analysis>...</analysis>     # 分析格式
    - <reasoning>...</reasoning>   # 推理格式
    - <internal>...</internal>     # 内部思考格式

    Args:
        text (str): 包含思维链的原始文本

    Returns:
        str: 清理后的文本，移除所有思维链标签和内容

    Examples:
        >>> remove_thinking_chains("Hello <think>Let me think about this</think> World")
        'Hello  World'

        >>> remove_thinking_chains("Answer: <thinking>This is complex</thinking>42")
        'Answer: 42'
    """
    if not text or not isinstance(text, str):
        return text

    # 支持多种思维链格式的正则表达式模式
    thinking_patterns = [
        r"<think>.*?</think>",  # 标准格式
        r"<thinking>.*?</thinking>",  # Claude格式
        r"<analysis>.*?</analysis>",  # 分析格式
        r"<reasoning>.*?</reasoning>",  # 推理格式
        r"<internal>.*?</internal>",  # 内部思考格式
        r"<scratch>.*?</scratch>",  # 草稿格式
        r"<draft>.*?</draft>",  # 草稿格式
    ]

    # 逐个应用所有模式，使用DOTALL标志支持跨行匹配
    cleaned_text = text
    for pattern in thinking_patterns:
        cleaned_text = re.sub(
            pattern, "", cleaned_text, flags=re.DOTALL | re.IGNORECASE
        )

    # 清理多余的空白字符（但保留基本格式）
    # 将多个连续空行替换为单个空行
    cleaned_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_text)

    # 清理多个连续空格，但保留单个空格和缩进
    cleaned_text = re.sub(r"  +", " ", cleaned_text)

    # 清理行首行尾多余空格，但保留缩进
    lines = cleaned_text.split("\n")
    cleaned_lines = []
    for line in lines:
        # 只清理完全空白的行，保留有意义的缩进
        if line.strip():
            cleaned_lines.append(line.rstrip())  # 只清理行尾空格
        else:
            cleaned_lines.append("")  # 保留空行

    return "\n".join(cleaned_lines).strip()


def clean_sensitive_content(text: str) -> str:
    """
    清理文本中的敏感信息

    Args:
        text (str): 原始文本

    Returns:
        str: 清理敏感信息后的文本
    """
    if not text or not isinstance(text, str):
        return text

    # 敏感信息替换模式
    sensitive_patterns = [
        (r"sk-[A-Za-z0-9]{20,}", "sk-***"),  # OpenAI API keys
        (r"Bearer [A-Za-z0-9+/]{20,}", "Bearer ***"),  # Bearer tokens
        (
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "***@***.com",
        ),  # Email addresses
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "***.***.***"),  # IP addresses
    ]

    cleaned_text = text
    for pattern, replacement in sensitive_patterns:
        cleaned_text = re.sub(pattern, replacement, cleaned_text)

    return cleaned_text


def truncate_large_content(text: str, max_length: int = 1000) -> str:
    """
    截断过长的内容，保留开头和结尾

    Args:
        text (str): 原始文本
        max_length (int): 最大长度

    Returns:
        str: 截断后的文本
    """
    if not text or len(text) <= max_length:
        return text

    if max_length < 50:  # 太短的话直接截断
        return text[:max_length] + "..."

    # 保留开头70%和结尾30%的内容
    head_length = int(max_length * 0.7) - 10  # 减去省略号长度
    tail_length = int(max_length * 0.3) - 10

    head = text[:head_length]
    tail = text[-tail_length:] if tail_length > 0 else ""

    return f"{head}... [TRUNCATED] ...{tail}"


def clean_model_response(
    text: str,
    remove_thinking: bool = True,
    clean_sensitive: bool = False,
    max_length: Optional[int] = None,
) -> str:
    """
    综合清理模型响应内容

    Args:
        text (str): 模型原始响应
        remove_thinking (bool): 是否移除思维链
        clean_sensitive (bool): 是否清理敏感信息
        max_length (Optional[int]): 最大长度限制

    Returns:
        str: 清理后的响应内容
    """
    if not text:
        return text

    cleaned_text = text

    # 1. 移除思维链
    if remove_thinking:
        cleaned_text = remove_thinking_chains(cleaned_text)

    # 2. 清理敏感信息
    if clean_sensitive:
        cleaned_text = clean_sensitive_content(cleaned_text)

    # 3. 截断过长内容
    if max_length is not None:
        cleaned_text = truncate_large_content(cleaned_text, max_length)

    return cleaned_text


# 便捷函数别名
def clean_thinking(text: str) -> str:
    """remove_thinking_chains的便捷别名"""
    return remove_thinking_chains(text)


def clean_response(text: str) -> str:
    """clean_model_response的便捷别名，使用默认参数"""
    return clean_model_response(text)
