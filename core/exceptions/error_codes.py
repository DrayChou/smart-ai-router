"""
统一错误码体系
定义所有系统错误的标准化错误码
"""

from enum import Enum


class ErrorCode(Enum):
    """系统错误码枚举"""

    # 通用错误 (1000-1099)
    UNKNOWN_ERROR = "E1000"
    INVALID_REQUEST = "E1001"
    INVALID_PARAMETER = "E1002"
    RESOURCE_NOT_FOUND = "E1003"
    PERMISSION_DENIED = "E1004"
    RATE_LIMIT_EXCEEDED = "E1005"

    # 配置错误 (1100-1199)
    CONFIG_LOAD_FAILED = "E1100"
    CONFIG_INVALID = "E1101"
    CONFIG_MISSING_REQUIRED = "E1102"
    CONFIG_PARSE_ERROR = "E1103"

    # 路由错误 (1200-1299)
    MODEL_NOT_FOUND = "E1200"
    TAG_NOT_FOUND = "E1201"
    NO_AVAILABLE_CHANNELS = "E1202"
    ROUTING_FAILED = "E1203"
    PARAMETER_COMPARISON_FAILED = "E1204"
    CHANNEL_DISABLED = "E1205"
    CHANNEL_UNHEALTHY = "E1206"

    # 渠道错误 (1300-1399)
    CHANNEL_NOT_FOUND = "E1300"
    CHANNEL_CONFIG_INVALID = "E1301"
    API_KEY_INVALID = "E1302"
    API_KEY_EXPIRED = "E1303"
    CHANNEL_QUOTA_EXCEEDED = "E1304"
    CHANNEL_TIMEOUT = "E1305"

    # 模型错误 (1400-1499)
    MODEL_LOAD_FAILED = "E1400"
    MODEL_INCOMPATIBLE = "E1401"
    MODEL_CACHE_ERROR = "E1402"
    MODEL_DISCOVERY_FAILED = "E1403"

    # 网络错误 (1500-1599)
    NETWORK_ERROR = "E1500"
    CONNECTION_TIMEOUT = "E1501"
    CONNECTION_REFUSED = "E1502"
    DNS_RESOLUTION_FAILED = "E1503"
    SSL_ERROR = "E1504"

    # 认证错误 (1600-1699)
    AUTH_FAILED = "E1600"
    TOKEN_INVALID = "E1601"
    TOKEN_EXPIRED = "E1602"
    INSUFFICIENT_PERMISSIONS = "E1603"

    # 缓存错误 (1700-1799)
    CACHE_ERROR = "E1700"
    CACHE_MISS = "E1701"
    CACHE_EXPIRED = "E1702"
    CACHE_CORRUPTED = "E1703"

    # 数据库错误 (1800-1899)
    DATABASE_ERROR = "E1800"
    DATABASE_CONNECTION_FAILED = "E1801"
    DATABASE_QUERY_FAILED = "E1802"
    DATABASE_CONSTRAINT_VIOLATION = "E1803"


# 错误码到消息的映射
ERROR_MESSAGES = {
    ErrorCode.UNKNOWN_ERROR: "未知错误",
    ErrorCode.INVALID_REQUEST: "无效的请求",
    ErrorCode.INVALID_PARAMETER: "无效的参数",
    ErrorCode.RESOURCE_NOT_FOUND: "资源未找到",
    ErrorCode.PERMISSION_DENIED: "权限被拒绝",
    ErrorCode.RATE_LIMIT_EXCEEDED: "请求频率超限",
    ErrorCode.CONFIG_LOAD_FAILED: "配置加载失败",
    ErrorCode.CONFIG_INVALID: "配置无效",
    ErrorCode.CONFIG_MISSING_REQUIRED: "缺少必需的配置项",
    ErrorCode.CONFIG_PARSE_ERROR: "配置解析错误",
    ErrorCode.MODEL_NOT_FOUND: "模型未找到",
    ErrorCode.TAG_NOT_FOUND: "标签未找到",
    ErrorCode.NO_AVAILABLE_CHANNELS: "没有可用的渠道",
    ErrorCode.ROUTING_FAILED: "路由失败",
    ErrorCode.PARAMETER_COMPARISON_FAILED: "参数量比较失败",
    ErrorCode.CHANNEL_DISABLED: "渠道已禁用",
    ErrorCode.CHANNEL_UNHEALTHY: "渠道不健康",
    ErrorCode.CHANNEL_NOT_FOUND: "渠道未找到",
    ErrorCode.CHANNEL_CONFIG_INVALID: "渠道配置无效",
    ErrorCode.API_KEY_INVALID: "API密钥无效",
    ErrorCode.API_KEY_EXPIRED: "API密钥已过期",
    ErrorCode.CHANNEL_QUOTA_EXCEEDED: "渠道配额已超限",
    ErrorCode.CHANNEL_TIMEOUT: "渠道超时",
    ErrorCode.MODEL_LOAD_FAILED: "模型加载失败",
    ErrorCode.MODEL_INCOMPATIBLE: "模型不兼容",
    ErrorCode.MODEL_CACHE_ERROR: "模型缓存错误",
    ErrorCode.MODEL_DISCOVERY_FAILED: "模型发现失败",
    ErrorCode.NETWORK_ERROR: "网络错误",
    ErrorCode.CONNECTION_TIMEOUT: "连接超时",
    ErrorCode.CONNECTION_REFUSED: "连接被拒绝",
    ErrorCode.DNS_RESOLUTION_FAILED: "DNS解析失败",
    ErrorCode.SSL_ERROR: "SSL错误",
    ErrorCode.AUTH_FAILED: "认证失败",
    ErrorCode.TOKEN_INVALID: "令牌无效",
    ErrorCode.TOKEN_EXPIRED: "令牌已过期",
    ErrorCode.INSUFFICIENT_PERMISSIONS: "权限不足",
    ErrorCode.CACHE_ERROR: "缓存错误",
    ErrorCode.CACHE_MISS: "缓存未命中",
    ErrorCode.CACHE_EXPIRED: "缓存已过期",
    ErrorCode.CACHE_CORRUPTED: "缓存已损坏",
    ErrorCode.DATABASE_ERROR: "数据库错误",
    ErrorCode.DATABASE_CONNECTION_FAILED: "数据库连接失败",
    ErrorCode.DATABASE_QUERY_FAILED: "数据库查询失败",
    ErrorCode.DATABASE_CONSTRAINT_VIOLATION: "数据库约束违反",
}


def get_error_message(error_code: ErrorCode, default: str = "未知错误") -> str:
    """获取错误码对应的消息"""
    return ERROR_MESSAGES.get(error_code, default)
