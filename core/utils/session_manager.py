"""
会话管理器 - 基于用户标识的会话统计和管理
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    """用户会话信息"""

    session_id: str
    user_identifier: str
    created_at: float
    last_active_at: float
    total_requests: int = 0
    total_cost: float = 0.0
    models_used: dict[str, int] = field(default_factory=dict)
    channels_used: dict[str, int] = field(default_factory=dict)

    def add_request(self, cost: float, model: str, channel: str):
        """添加请求记录"""
        self.total_requests += 1
        self.total_cost += cost
        self.last_active_at = time.time()

        # 更新模型使用统计
        self.models_used[model] = self.models_used.get(model, 0) + 1

        # 更新渠道使用统计
        self.channels_used[channel] = self.channels_used.get(channel, 0) + 1

    def is_expired(self, session_timeout: int = 3600) -> bool:
        """检查会话是否已过期（默认1小时）"""
        return (time.time() - self.last_active_at) > session_timeout

    def get_formatted_cost(self) -> str:
        """获取格式化的总成本"""
        return f"${self.total_cost:.6f}"


class SessionManager:
    """会话管理器"""

    def __init__(self, session_timeout: int = 3600, cleanup_interval: int = 300):
        self.sessions: dict[str, UserSession] = {}
        self.session_timeout = session_timeout  # 1小时
        self.cleanup_interval = cleanup_interval  # 5分钟
        self._last_cleanup = time.time()

    def create_user_identifier(
        self,
        api_key: Optional[str],
        user_agent: Optional[str],
        client_ip: Optional[str] = None,
    ) -> str:
        """
        创建用户标识符
        基于: API Key + User-Agent + IP（可选）
        """
        # 构建标识符组件
        components = []

        if api_key:
            # 使用API Key的前8位和后4位，避免完整泄露
            if len(api_key) > 12:
                masked_key = f"{api_key[:8]}***{api_key[-4:]}"
            else:
                masked_key = "***" + api_key[-4:] if len(api_key) >= 4 else "anonymous"
            components.append(masked_key)
        else:
            components.append("anonymous")

        if user_agent:
            # 提取主要的客户端信息
            components.append(user_agent[:100])  # 限制长度
        else:
            components.append("unknown-client")

        if client_ip:
            components.append(client_ip)

        # 生成唯一标识符
        identifier_str = "|".join(components)
        hash_object = hashlib.sha256(identifier_str.encode("utf-8"))
        return f"user_{hash_object.hexdigest()[:16]}"

    def get_or_create_session(self, user_identifier: str) -> UserSession:
        """获取或创建用户会话"""
        self._maybe_cleanup()

        if user_identifier in self.sessions:
            session = self.sessions[user_identifier]
            if not session.is_expired(self.session_timeout):
                return session
            else:
                # 会话已过期，删除并创建新的
                del self.sessions[user_identifier]
                logger.info(
                    f"🧹 SESSION EXPIRED: {user_identifier} (requests: {session.total_requests}, cost: {session.get_formatted_cost()})"
                )

        # 创建新会话
        session_id = f"sess_{int(time.time())}_{user_identifier}"
        session = UserSession(
            session_id=session_id,
            user_identifier=user_identifier,
            created_at=time.time(),
            last_active_at=time.time(),
        )

        self.sessions[user_identifier] = session
        logger.info(f"🆕 NEW SESSION: {user_identifier} -> {session_id}")

        return session

    def add_request(
        self, user_identifier: str, cost: float, model: str, channel: str
    ) -> UserSession:
        """添加请求到会话"""
        session = self.get_or_create_session(user_identifier)
        session.add_request(cost, model, channel)

        logger.debug(
            f"📊 SESSION UPDATE: {user_identifier} - requests: {session.total_requests}, cost: {session.get_formatted_cost()}"
        )

        return session

    def get_session_stats(self, user_identifier: str) -> dict[str, Any]:
        """获取会话统计信息"""
        if user_identifier not in self.sessions:
            return {
                "total_cost": 0.0,
                "formatted_total_cost": "$0.000000",
                "total_requests": 0,
                "session_duration": 0,
                "models_used": {},
                "channels_used": {},
            }

        session = self.sessions[user_identifier]
        duration = time.time() - session.created_at

        return {
            "total_cost": session.total_cost,
            "formatted_total_cost": session.get_formatted_cost(),
            "total_requests": session.total_requests,
            "session_duration": int(duration),
            "models_used": dict(session.models_used),
            "channels_used": dict(session.channels_used),
            "average_cost": session.total_cost / max(session.total_requests, 1),
        }

    def _maybe_cleanup(self):
        """按需清理过期会话"""
        now = time.time()
        if (now - self._last_cleanup) > self.cleanup_interval:
            expired_sessions = []

            for user_id, session in self.sessions.items():
                if session.is_expired(self.session_timeout):
                    expired_sessions.append(user_id)

            for user_id in expired_sessions:
                session = self.sessions[user_id]
                logger.info(
                    f"🧹 CLEANUP SESSION: {user_id} (requests: {session.total_requests}, cost: {session.get_formatted_cost()})"
                )
                del self.sessions[user_id]

            if expired_sessions:
                logger.info(
                    f"🧹 CLEANUP COMPLETE: Removed {len(expired_sessions)} expired sessions"
                )

            self._last_cleanup = now

    def get_global_stats(self) -> dict[str, Any]:
        """获取全局统计信息"""
        total_sessions = len(self.sessions)
        total_requests = sum(
            session.total_requests for session in self.sessions.values()
        )
        total_cost = sum(session.total_cost for session in self.sessions.values())

        return {
            "active_sessions": total_sessions,
            "total_requests": total_requests,
            "total_cost": total_cost,
            "formatted_total_cost": f"${total_cost:.6f}",
            "average_requests_per_session": total_requests / max(total_sessions, 1),
        }


# 全局会话管理器实例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器实例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
