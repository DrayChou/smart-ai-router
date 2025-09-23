# -*- coding: utf-8 -*-
"""
简单的管理员认证模块
"""

import os
from typing import Optional

from fastapi import HTTPException, Query, status


def verify_admin_token(admin_token: Optional[str] = Query(None)) -> str:
    """
    验证管理员token

    Args:
        admin_token: 管理员token (来自查询参数)

    Returns:
        str: 验证通过的token

    Raises:
        HTTPException: 认证失败
    """
    # 从环境变量获取预期的管理员token
    expected_token = os.getenv("ADMIN_TOKEN", "admin-secret-2025")

    if not admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token required"
        )

    if admin_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin token"
        )

    return admin_token
