"""
使用统计API - 提供成本和使用情况查询接口
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from core.auth import get_admin_auth_dependency
from core.utils.channel_monitor import get_channel_monitor
from core.utils.usage_tracker import get_usage_tracker
from core.yaml_config import YAMLConfigLoader


def create_usage_stats_router(config_loader: YAMLConfigLoader) -> APIRouter:
    """创建使用统计相关的API路由"""

    router = APIRouter(prefix="/v1/stats", tags=["usage-stats"])
    tracker = get_usage_tracker()
    monitor = get_channel_monitor()

    @router.get("/daily")
    async def get_daily_stats(
        target_date: Optional[str] = Query(
            None, description="目标日期 (YYYY-MM-DD格式)，默认为今天"
        ),
        auth: bool = Depends(get_admin_auth_dependency),
    ):
        """获取每日使用统计"""
        try:
            if target_date:
                target = datetime.strptime(target_date, "%Y-%m-%d").date()
            else:
                target = date.today()

            stats = tracker.get_daily_stats(target)
            return JSONResponse(content={"success": True, "data": stats})

        except ValueError:
            raise HTTPException(
                status_code=400, detail="日期格式错误，请使用YYYY-MM-DD格式"
            ) from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取每日统计失败: {str(e)}") from e

    @router.get("/weekly")
    async def get_weekly_stats(
        target_date: Optional[str] = Query(
            None, description="目标日期 (YYYY-MM-DD格式)，默认为今天所在周"
        ),
        auth: bool = Depends(get_admin_auth_dependency),
    ):
        """获取本周使用统计"""
        try:
            if target_date:
                target = datetime.strptime(target_date, "%Y-%m-%d").date()
            else:
                target = date.today()

            stats = tracker.get_weekly_stats(target)
            return JSONResponse(content={"success": True, "data": stats})

        except ValueError:
            raise HTTPException(
                status_code=400, detail="日期格式错误，请使用YYYY-MM-DD格式"
            ) from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取周统计失败: {str(e)}") from e

    @router.get("/monthly")
    async def get_monthly_stats(
        year: Optional[int] = Query(None, description="年份，默认为当前年"),
        month: Optional[int] = Query(None, description="月份 (1-12)，默认为当前月"),
        auth: bool = Depends(get_admin_auth_dependency),
    ):
        """获取月度使用统计"""
        try:
            stats = tracker.get_monthly_stats(year, month)
            return JSONResponse(content={"success": True, "data": stats})

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取月度统计失败: {str(e)}") from e

    @router.get("/summary")
    async def get_usage_summary(auth: bool = Depends(get_admin_auth_dependency)):
        """获取使用情况汇总"""
        try:
            today = date.today()

            # 获取各维度统计
            daily_stats = tracker.get_daily_stats(today)
            weekly_stats = tracker.get_weekly_stats(today)
            monthly_stats = tracker.get_monthly_stats(today.year, today.month)

            summary = {
                "today": daily_stats,
                "this_week": weekly_stats,
                "this_month": monthly_stats,
                "comparison": {
                    "daily_vs_weekly_avg": 0.0,
                    "weekly_vs_monthly_avg": 0.0,
                },
            }

            # 计算对比数据
            if weekly_stats["total_requests"] > 0:
                weekly_avg = weekly_stats["total_cost"] / max(
                    1, (today.weekday() + 1)
                )  # 按已过天数计算
                if weekly_avg > 0:
                    summary["comparison"]["daily_vs_weekly_avg"] = (
                        daily_stats["total_cost"] - weekly_avg
                    ) / weekly_avg

            if monthly_stats["total_requests"] > 0:
                monthly_avg = monthly_stats["total_cost"] / max(
                    1, today.day
                )  # 按已过天数计算
                weekly_avg_monthly = weekly_stats["total_cost"] / 7 * 7  # 本周总消费
                if monthly_avg > 0:
                    summary["comparison"]["weekly_vs_monthly_avg"] = (
                        weekly_avg_monthly - monthly_avg * 7
                    ) / (monthly_avg * 7)

            return JSONResponse(content={"success": True, "data": summary})

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取汇总统计失败: {str(e)}") from e

    @router.get("/top-models")
    async def get_top_models(
        period: str = Query(
            "daily", regex="^(daily|weekly|monthly)$", description="统计周期"
        ),
        limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
        target_date: Optional[str] = Query(
            None, description="目标日期 (YYYY-MM-DD格式)"
        ),
        auth: bool = Depends(get_admin_auth_dependency),
    ):
        """获取使用最多的模型排行"""
        try:
            if target_date:
                target = datetime.strptime(target_date, "%Y-%m-%d").date()
            else:
                target = date.today()

            if period == "daily":
                stats = tracker.get_daily_stats(target)
            elif period == "weekly":
                stats = tracker.get_weekly_stats(target)
            else:  # monthly
                stats = tracker.get_monthly_stats(target.year, target.month)

            # 按使用次数排序模型
            models = stats["models"]
            sorted_models = sorted(
                [(model, info) for model, info in models.items()],
                key=lambda x: x[1]["requests"],
                reverse=True,
            )[:limit]

            result = []
            for model, info in sorted_models:
                result.append(
                    {
                        "model": model,
                        "requests": info["requests"],
                        "cost": info["cost"],
                        "tokens": info["tokens"],
                        "avg_cost_per_request": info["cost"] / max(1, info["requests"]),
                        "avg_tokens_per_request": info["tokens"]
                        / max(1, info["requests"]),
                    }
                )

            return JSONResponse(
                content={
                    "success": True,
                    "data": {
                        "period": period,
                        "target_date": target.isoformat(),
                        "models": result,
                    },
                }
            )

        except ValueError:
            raise HTTPException(
                status_code=400, detail="日期格式错误，请使用YYYY-MM-DD格式"
            ) from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取模型排行失败: {str(e)}") from e

    @router.get("/top-channels")
    async def get_top_channels(
        period: str = Query(
            "daily", regex="^(daily|weekly|monthly)$", description="统计周期"
        ),
        limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
        target_date: Optional[str] = Query(
            None, description="目标日期 (YYYY-MM-DD格式)"
        ),
        auth: bool = Depends(get_admin_auth_dependency),
    ):
        """获取使用最多的渠道排行"""
        try:
            if target_date:
                target = datetime.strptime(target_date, "%Y-%m-%d").date()
            else:
                target = date.today()

            if period == "daily":
                stats = tracker.get_daily_stats(target)
            elif period == "weekly":
                stats = tracker.get_weekly_stats(target)
            else:  # monthly
                stats = tracker.get_monthly_stats(target.year, target.month)

            # 按成本排序渠道
            channels = stats["channels"]
            sorted_channels = sorted(
                [(channel, info) for channel, info in channels.items()],
                key=lambda x: x[1]["cost"],
                reverse=True,
            )[:limit]

            result = []
            for channel, info in sorted_channels:
                result.append(
                    {
                        "channel": channel,
                        "requests": info["requests"],
                        "cost": info["cost"],
                        "tokens": info["tokens"],
                        "avg_cost_per_request": info["cost"] / max(1, info["requests"]),
                        "avg_tokens_per_request": info["tokens"]
                        / max(1, info["requests"]),
                    }
                )

            return JSONResponse(
                content={
                    "success": True,
                    "data": {
                        "period": period,
                        "target_date": target.isoformat(),
                        "channels": result,
                    },
                }
            )

        except ValueError:
            raise HTTPException(
                status_code=400, detail="日期格式错误，请使用YYYY-MM-DD格式"
            ) from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取渠道排行失败: {str(e)}") from e

    @router.get("/cost-breakdown")
    async def get_cost_breakdown(
        period: str = Query(
            "daily", regex="^(daily|weekly|monthly)$", description="统计周期"
        ),
        breakdown_by: str = Query(
            "provider", regex="^(provider|channel|model)$", description="分解维度"
        ),
        target_date: Optional[str] = Query(
            None, description="目标日期 (YYYY-MM-DD格式)"
        ),
        auth: bool = Depends(get_admin_auth_dependency),
    ):
        """获取成本分解分析"""
        try:
            if target_date:
                target = datetime.strptime(target_date, "%Y-%m-%d").date()
            else:
                target = date.today()

            if period == "daily":
                stats = tracker.get_daily_stats(target)
            elif period == "weekly":
                stats = tracker.get_weekly_stats(target)
            else:  # monthly
                stats = tracker.get_monthly_stats(target.year, target.month)

            # 获取分解数据
            breakdown_data = stats[f"{breakdown_by}s"]  # providers, channels, models
            total_cost = stats["total_cost"]

            result = []
            for item, info in breakdown_data.items():
                percentage = (info["cost"] / total_cost * 100) if total_cost > 0 else 0
                result.append(
                    {
                        breakdown_by: item,
                        "cost": info["cost"],
                        "percentage": round(percentage, 2),
                        "requests": info["requests"],
                        "tokens": info["tokens"],
                    }
                )

            # 按成本排序
            result.sort(key=lambda x: x["cost"], reverse=True)

            return JSONResponse(
                content={
                    "success": True,
                    "data": {
                        "period": period,
                        "breakdown_by": breakdown_by,
                        "target_date": target.isoformat(),
                        "total_cost": total_cost,
                        "breakdown": result,
                    },
                }
            )

        except ValueError:
            raise HTTPException(
                status_code=400, detail="日期格式错误，请使用YYYY-MM-DD格式"
            ) from None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取成本分解失败: {str(e)}") from e

    @router.get("/alerts")
    async def get_channel_alerts(
        hours: int = Query(24, ge=1, le=168, description="查询最近多少小时的告警"),
        auth: bool = Depends(get_admin_auth_dependency),
    ):
        """获取渠道告警信息"""
        try:
            alerts = monitor.get_recent_alerts(hours)

            # 转换为字典格式
            alert_list = []
            for alert in alerts:
                alert_list.append(
                    {
                        "channel_id": alert.channel_id,
                        "channel_name": alert.channel_name,
                        "alert_type": alert.alert_type,
                        "message": alert.message,
                        "timestamp": alert.timestamp,
                        "details": alert.details,
                    }
                )

            # 按告警类型分组统计
            alert_counts = {}
            for alert in alerts:
                alert_type = alert.alert_type
                if alert_type not in alert_counts:
                    alert_counts[alert_type] = 0
                alert_counts[alert_type] += 1

            return JSONResponse(
                content={
                    "success": True,
                    "data": {
                        "time_range_hours": hours,
                        "total_alerts": len(alerts),
                        "alert_counts": alert_counts,
                        "alerts": alert_list,
                    },
                }
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取告警信息失败: {str(e)}") from e

    @router.get("/channel-status")
    async def get_channel_status(auth: bool = Depends(get_admin_auth_dependency)):
        """获取渠道状态概览"""
        try:
            status = monitor.get_channel_status()
            return JSONResponse(content={"success": True, "data": status})

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"获取渠道状态失败: {str(e)}") from e

    @router.post("/clear-alerts/{channel_id}")
    async def clear_channel_alerts(
        channel_id: str, auth: bool = Depends(get_admin_auth_dependency)
    ):
        """清除指定渠道的告警状态"""
        try:
            monitor.clear_channel_notifications(channel_id)
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"已清除渠道 {channel_id} 的告警状态",
                }
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"清除告警状态失败: {str(e)}") from e

    @router.post("/clear-all-alerts")
    async def clear_all_alerts(auth: bool = Depends(get_admin_auth_dependency)):
        """清除所有渠道的告警状态"""
        try:
            monitor.clear_all_notifications()
            return JSONResponse(
                content={"success": True, "message": "已清除所有渠道的告警状态"}
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"清除告警状态失败: {str(e)}") from e

    return router
