# -*- coding: utf-8 -*-
"""
Token generation utilities
"""

import secrets
import string

def generate_random_token(length: int = 32) -> str:
    """
    生成安全的随机Token
    
    Args:
        length: Token长度，默认32位
        
    Returns:
        随机生成的Token字符串
    """
    # 使用字母、数字和一些安全的符号
    alphabet = string.ascii_letters + string.digits + "-_"
    token = ''.join(secrets.choice(alphabet) for _ in range(length))
    return f"sar-{token}"  # sar = Smart AI Router

def is_valid_token_format(token: str) -> bool:
    """
    检查Token格式是否有效
    
    Args:
        token: 要检查的Token
        
    Returns:
        True如果格式有效，False否则
    """
    if not token:
        return False
        
    # 检查是否以sar-开头
    if not token.startswith("sar-"):
        return False
        
    # 检查长度 (sar- + 32字符)
    if len(token) < 36:
        return False
        
    # 检查字符是否合法
    token_part = token[4:]  # 去掉sar-前缀
    allowed_chars = set(string.ascii_letters + string.digits + "-_")
    return all(c in allowed_chars for c in token_part)