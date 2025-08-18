# -*- coding: utf-8 -*-
"""
Authentication module for Smart AI Router
"""

from .middleware import AuthenticationMiddleware
from .token_generator import generate_random_token

__all__ = ["AuthenticationMiddleware", "generate_random_token"]