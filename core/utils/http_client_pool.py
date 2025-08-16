#!/usr/bin/env python3
"""
HTTP客户端连接池管理器
提供连接复用，减少连接建立时间
"""

import httpx
import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class HTTPStreamContext:
    """HTTP流式请求的异步上下文管理器"""
    
    def __init__(self, stream_coroutine):
        self.stream_coroutine = stream_coroutine
        self.stream_manager = None
    
    async def __aenter__(self):
        # 获取实际的流式上下文管理器
        self.stream_manager = await self.stream_coroutine
        # 进入流式上下文
        return await self.stream_manager.__aenter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 退出流式上下文
        if self.stream_manager:
            return await self.stream_manager.__aexit__(exc_type, exc_val, exc_tb)

class HTTPClientPool:
    """HTTP客户端连接池"""
    
    def __init__(self):
        self.clients: Dict[str, httpx.AsyncClient] = {}
        self.lock = asyncio.Lock()
        
        # 连接池配置
        self.limits = httpx.Limits(
            max_keepalive_connections=20,  # 每个客户端最多保持20个keepalive连接
            max_connections=100,           # 每个客户端最多100个连接
            keepalive_expiry=30.0         # keepalive连接30秒过期
        )
        
        # 超时配置
        self.timeout = httpx.Timeout(
            connect=10.0,   # 连接超时
            read=300.0,     # 读取超时（适应慢模型）
            write=30.0,     # 写入超时
            pool=10.0       # 连接池超时
        )
    
    def _get_base_url_key(self, url: str) -> str:
        """从完整URL提取base URL作为key"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    async def get_client(self, url: str) -> httpx.AsyncClient:
        """获取或创建HTTP客户端"""
        base_url_key = self._get_base_url_key(url)
        
        async with self.lock:
            if base_url_key not in self.clients:
                # 创建新的客户端
                client = httpx.AsyncClient(
                    base_url=base_url_key,
                    timeout=self.timeout,
                    limits=self.limits,
                    follow_redirects=True,
                    http2=True  # 启用HTTP/2支持
                )
                self.clients[base_url_key] = client
                logger.info(f"创建新的HTTP客户端连接池: {base_url_key}")
            
            return self.clients[base_url_key]
    
    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """使用连接池发送HTTP请求"""
        client = await self.get_client(url)
        return await client.request(method, url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """POST请求"""
        return await self.request("POST", url, **kwargs)
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET请求"""
        return await self.request("GET", url, **kwargs)
    
    def stream(self, method: str, url: str, **kwargs):
        """流式请求 - 返回异步上下文管理器"""
        # 注意：这里不能用async def，因为需要返回一个可以用于async with的对象
        async def _stream_context():
            client = await self.get_client(url)
            return client.stream(method, url, **kwargs)
        
        # 返回一个自定义的异步上下文管理器
        return HTTPStreamContext(_stream_context())
    
    async def close_all(self):
        """关闭所有客户端连接"""
        async with self.lock:
            for base_url, client in self.clients.items():
                try:
                    await client.aclose()
                    logger.info(f"关闭HTTP客户端连接池: {base_url}")
                except Exception as e:
                    logger.warning(f"关闭客户端连接池失败 {base_url}: {e}")
            self.clients.clear()
    
    async def cleanup_idle_clients(self, max_idle_time: float = 300.0):
        """清理空闲的客户端连接（可选的后台任务）"""
        # 这个功能对个人开发者来说可能不是必需的
        # 因为连接数量通常不会很大
        pass
    
    def get_stats(self) -> Dict[str, int]:
        """获取连接池统计信息"""
        return {
            'active_clients': len(self.clients),
            'base_urls': list(self.clients.keys())
        }

# 全局连接池实例
_global_pool: Optional[HTTPClientPool] = None

def get_http_pool() -> HTTPClientPool:
    """获取全局HTTP连接池实例"""
    global _global_pool
    if _global_pool is None:
        _global_pool = HTTPClientPool()
        logger.info("初始化全局HTTP连接池")
    return _global_pool

async def close_global_pool():
    """关闭全局连接池"""
    global _global_pool
    if _global_pool is not None:
        await _global_pool.close_all()
        _global_pool = None
        logger.info("全局HTTP连接池已关闭")