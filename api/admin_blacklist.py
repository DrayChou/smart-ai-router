"""
黑名单管理和监控API端点
提供模型黑名单的查看、管理和监控功能
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.utils.auth import verify_admin_token
from core.utils.blacklist_recovery import get_blacklist_recovery_manager
from core.utils.model_channel_blacklist import ErrorType, get_model_blacklist_manager

router = APIRouter(prefix="/admin/blacklist", tags=["Admin - Blacklist Management"])


# --- Response Models ---


class BlacklistEntryResponse(BaseModel):
    """黑名单条目响应模型"""

    model_config = {"protected_namespaces": ()}

    channel_id: str
    model_name: str
    error_type: str
    error_code: int
    error_message: str
    blacklisted_at: datetime
    expires_at: Optional[datetime]
    failure_count: int
    is_permanent: bool
    remaining_time: int  # 剩余时间（秒）


class BlacklistStatsResponse(BaseModel):
    """黑名单统计响应模型"""

    total_blacklisted: int
    permanent_blacklisted: int
    temporary_blacklisted: int
    by_channel: dict[str, list[dict[str, Any]]]
    by_error_type: dict[str, int]
    channel_failure_counts: dict[str, int]


class RecoveryStatsResponse(BaseModel):
    """恢复统计响应模型"""

    total_attempts_24h: int
    successful_recoveries_24h: int
    failed_recoveries_24h: int
    success_rate: float
    avg_response_time: float
    is_running: bool
    recovery_interval: int


class BlacklistManagementRequest(BaseModel):
    """黑名单管理请求模型"""

    model_config = {"protected_namespaces": ()}

    channel_id: str
    model_name: str
    action: str  # "remove", "extend", "permanent"
    duration: Optional[int] = None  # 延长时间（秒）


class HealthReportResponse(BaseModel):
    """健康报告响应模型"""

    model_config = {"protected_namespaces": ()}

    timestamp: datetime
    total_channels: int
    healthy_channels: int
    total_models: int
    available_models: int
    blacklisted_models: int
    channels: dict[str, dict[str, Any]]
    model_blacklists: dict[str, Any]


# --- API Endpoints ---


@router.get("/stats", response_model=BlacklistStatsResponse)
async def get_blacklist_stats(
    admin_token: str = Depends(verify_admin_token),
) -> BlacklistStatsResponse:
    """获取黑名单统计信息"""
    blacklist_manager = get_model_blacklist_manager()
    stats = blacklist_manager.get_blacklist_stats()

    return BlacklistStatsResponse(**stats)


@router.get("/entries", response_model=list[BlacklistEntryResponse])
async def get_blacklist_entries(
    channel_id: Optional[str] = None,
    model_name: Optional[str] = None,
    error_type: Optional[str] = None,
    admin_token: str = Depends(verify_admin_token),
) -> list[BlacklistEntryResponse]:
    """获取黑名单条目列表，支持过滤"""
    blacklist_manager = get_model_blacklist_manager()

    entries = []
    for entry in blacklist_manager._blacklist.values():
        # 应用过滤条件
        if channel_id and entry.channel_id != channel_id:
            continue
        if model_name and entry.model_name.lower() != model_name.lower():
            continue
        if error_type and entry.error_type.value != error_type:
            continue

        entries.append(
            BlacklistEntryResponse(
                channel_id=entry.channel_id,
                model_name=entry.model_name,
                error_type=entry.error_type.value,
                error_code=entry.error_code,
                error_message=entry.error_message,
                blacklisted_at=entry.blacklisted_at,
                expires_at=entry.expires_at,
                failure_count=entry.failure_count,
                is_permanent=entry.is_permanent,
                remaining_time=entry.get_remaining_time(),
            )
        )

    # 按剩余时间排序
    entries.sort(key=lambda x: x.remaining_time if x.remaining_time >= 0 else 999999)

    return entries


@router.post("/manage")
async def manage_blacklist_entry(
    request: BlacklistManagementRequest, admin_token: str = Depends(verify_admin_token)
) -> dict[str, str]:
    """管理黑名单条目（移除、延长、设为永久）"""
    blacklist_manager = get_model_blacklist_manager()

    if request.action == "remove":
        # 移除黑名单条目
        success = await blacklist_manager.remove_blacklist_entry(
            request.channel_id, request.model_name
        )
        if success:
            return {
                "message": f"Successfully removed {request.model_name}@{request.channel_id} from blacklist"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Blacklist entry for {request.model_name}@{request.channel_id} not found",
            )

    elif request.action == "extend":
        # 延长黑名单时间
        if not request.duration:
            raise HTTPException(
                status_code=400, detail="Duration required for extend action"
            )

        key = blacklist_manager._generate_key(request.channel_id, request.model_name)
        if key in blacklist_manager._blacklist:
            entry = blacklist_manager._blacklist[key]
            if not entry.is_permanent:
                from datetime import timedelta

                entry.expires_at = datetime.now() + timedelta(seconds=request.duration)
                entry.backoff_duration = request.duration
                return {
                    "message": f"Extended blacklist for {request.model_name}@{request.channel_id} by {request.duration} seconds"
                }
            else:
                raise HTTPException(
                    status_code=400, detail="Cannot extend permanent blacklist"
                )
        else:
            raise HTTPException(status_code=404, detail="Blacklist entry not found")

    elif request.action == "permanent":
        # 设为永久黑名单
        key = blacklist_manager._generate_key(request.channel_id, request.model_name)
        if key in blacklist_manager._blacklist:
            entry = blacklist_manager._blacklist[key]
            entry.is_permanent = True
            entry.expires_at = None
            return {
                "message": f"Set {request.model_name}@{request.channel_id} as permanently blacklisted"
            }
        else:
            raise HTTPException(status_code=404, detail="Blacklist entry not found")

    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")


@router.post("/cleanup")
async def cleanup_expired_entries(
    admin_token: str = Depends(verify_admin_token),
) -> dict[str, Any]:
    """清理过期的黑名单条目"""
    blacklist_manager = get_model_blacklist_manager()
    cleaned_count = blacklist_manager.cleanup_expired_entries()

    return {
        "message": f"Cleaned up {cleaned_count} expired blacklist entries",
        "cleaned_count": cleaned_count,
    }


@router.get("/recovery/stats", response_model=RecoveryStatsResponse)
async def get_recovery_stats(
    admin_token: str = Depends(verify_admin_token),
) -> RecoveryStatsResponse:
    """获取恢复服务统计信息"""
    recovery_manager = get_blacklist_recovery_manager()
    stats = recovery_manager.get_recovery_stats()

    return RecoveryStatsResponse(**stats)


@router.post("/recovery/trigger")
async def trigger_recovery_check(
    admin_token: str = Depends(verify_admin_token),
) -> dict[str, str]:
    """手动触发一次恢复检查"""
    recovery_manager = get_blacklist_recovery_manager()

    try:
        await recovery_manager._perform_recovery_check()
        return {"message": "Recovery check completed successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Recovery check failed: {str(e)}"
        ) from e


@router.post("/recovery/service/{action}")
async def manage_recovery_service(
    action: str, admin_token: str = Depends(verify_admin_token)
) -> dict[str, str]:
    """管理恢复服务（启动/停止）"""
    recovery_manager = get_blacklist_recovery_manager()

    if action == "start":
        await recovery_manager.start_recovery_service()
        return {"message": "Recovery service started"}
    elif action == "stop":
        await recovery_manager.stop_recovery_service()
        return {"message": "Recovery service stopped"}
    else:
        raise HTTPException(
            status_code=400, detail=f"Invalid action: {action}. Use 'start' or 'stop'"
        )


@router.get("/health-report", response_model=HealthReportResponse)
async def get_health_report(
    admin_token: str = Depends(verify_admin_token),
) -> HealthReportResponse:
    """获取详细的健康报告"""
    from core.yaml_config import get_yaml_config_loader

    config_loader = get_yaml_config_loader()
    blacklist_manager = get_model_blacklist_manager()

    # 获取所有渠道
    all_channels = config_loader.get_enabled_channels()

    # 统计信息
    total_channels = len(all_channels)
    healthy_channels = sum(1 for ch in all_channels if ch.enabled and ch.api_key)

    # 构建渠道健康信息
    channels = {}
    total_models = 0
    available_models = 0
    blacklisted_models = 0

    for channel in all_channels:
        if not channel.enabled or not channel.api_key:
            continue

        # 获取该渠道的黑名单信息
        blacklisted_model_names = blacklist_manager.get_blacklisted_models_for_channel(
            channel.id
        )

        # 假设每个渠道有多个模型（实际需要根据模型发现结果）
        # 这里简化处理，假设每个渠道至少有1个模型
        channel_model_count = max(1, len(blacklisted_model_names) + 1)
        total_models += channel_model_count
        available_models += channel_model_count - len(blacklisted_model_names)
        blacklisted_models += len(blacklisted_model_names)

        channels[channel.id] = {
            "name": channel.name,
            "provider": channel.provider,
            "status": "healthy" if channel.enabled and channel.api_key else "disabled",
            "available_models": channel_model_count - len(blacklisted_model_names),
            "blacklisted_models": [
                {
                    "model": model_name,
                    "blacklisted_until": None,  # 需要从黑名单管理器获取
                    "failure_count": 0,  # 需要从黑名单管理器获取
                }
                for model_name in blacklisted_model_names
            ],
        }

    # 黑名单统计
    blacklist_stats = blacklist_manager.get_blacklist_stats()
    model_blacklists = {
        "active_count": blacklist_stats["total_blacklisted"],
        "by_channel": blacklist_stats["by_channel"],
        "by_error_code": blacklist_stats["by_error_type"],
        "recovery_queue": [],  # 可以添加待恢复的条目
    }

    return HealthReportResponse(
        timestamp=datetime.now(),
        total_channels=total_channels,
        healthy_channels=healthy_channels,
        total_models=total_models,
        available_models=available_models,
        blacklisted_models=blacklisted_models,
        channels=channels,
        model_blacklists=model_blacklists,
    )


@router.get("/error-types")
async def get_error_types(
    admin_token: str = Depends(verify_admin_token),
) -> dict[str, Any]:
    """获取支持的错误类型列表"""
    error_types = [error_type.value for error_type in ErrorType]

    return {
        "error_types": error_types,
        "descriptions": {
            ErrorType.RATE_LIMIT.value: "Speed rate limiting (HTTP 429)",
            ErrorType.AUTH_ERROR.value: "Authentication/authorization errors (HTTP 401, 403)",
            ErrorType.MODEL_UNAVAILABLE.value: "Model not found or unavailable (HTTP 404)",
            ErrorType.QUOTA_EXCEEDED.value: "Quota or balance exhausted",
            ErrorType.SERVER_ERROR.value: "Server-side errors (HTTP 500+)",
            ErrorType.TIMEOUT.value: "Request timeout",
            ErrorType.CONNECTION_ERROR.value: "Connection failure",
            ErrorType.UNKNOWN.value: "Unknown or unclassified errors",
        },
    }


@router.get("/channels/{channel_id}/models")
async def get_channel_model_status(
    channel_id: str, admin_token: str = Depends(verify_admin_token)
) -> dict[str, Any]:
    """获取特定渠道的所有模型状态"""
    blacklist_manager = get_model_blacklist_manager()

    # 获取该渠道的黑名单模型
    blacklisted_models = blacklist_manager.get_blacklisted_models_for_channel(
        channel_id
    )

    # 构建响应
    model_status = []
    for model_name in blacklisted_models:
        is_blacklisted, entry = blacklist_manager.is_model_blacklisted(
            channel_id, model_name
        )

        if is_blacklisted and entry:
            model_status.append(
                {
                    "model_name": model_name,
                    "status": "blacklisted",
                    "error_type": entry.error_type.value,
                    "failure_count": entry.failure_count,
                    "remaining_time": entry.get_remaining_time(),
                    "blacklisted_at": entry.blacklisted_at,
                    "expires_at": entry.expires_at,
                }
            )

    return {
        "channel_id": channel_id,
        "total_models": len(model_status),
        "blacklisted_count": len(blacklisted_models),
        "models": model_status,
    }
