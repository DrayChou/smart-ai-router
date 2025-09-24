#!/usr/bin/env python3
"""
后台任务调度器 - 管理定时任务
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器"""

    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}
        self.running = False
        self._loop_task = None

    def add_task(
        self,
        name: str,
        func: Callable,
        interval_seconds: int,
        run_immediately: bool = False,
        **kwargs: Any,
    ) -> None:
        """添加定时任务

        Args:
            name: 任务名称
            func: 任务函数 (可以是async或sync)
            interval_seconds: 执行间隔(秒)
            run_immediately: 是否立即执行一次
            **kwargs: 传递给任务函数的参数
        """
        self.tasks[name] = {
            "func": func,
            "interval": interval_seconds,
            "last_run": None,
            "next_run": (
                datetime.now()
                if run_immediately
                else datetime.now() + timedelta(seconds=interval_seconds)
            ),
            "kwargs": kwargs,
            "run_count": 0,
            "success_count": 0,
            "error_count": 0,
            "last_error": None,
            "last_duration": None,
            "enabled": True,
        }

        logger.info(
            f"已添加任务 '{name}', 间隔 {interval_seconds}s, 立即执行: {run_immediately}"
        )

    def remove_task(self, name: str) -> None:
        """移除任务"""
        if name in self.tasks:
            del self.tasks[name]
            logger.info(f"已移除任务 '{name}'")

    def enable_task(self, name: str) -> None:
        """启用任务"""
        if name in self.tasks:
            self.tasks[name]["enabled"] = True
            logger.info(f"已启用任务 '{name}'")

    def disable_task(self, name: str) -> None:
        """禁用任务"""
        if name in self.tasks:
            self.tasks[name]["enabled"] = False
            logger.info(f"已禁用任务 '{name}'")

    async def _run_task(self, name: str, task_info: dict[str, Any]) -> Any:
        """执行单个任务"""
        func = task_info["func"]
        kwargs = task_info["kwargs"]

        start_time = time.time()

        try:
            logger.debug(f"开始执行任务 '{name}'")

            # 检查是否是异步函数
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)

            duration = time.time() - start_time

            # 更新任务统计
            task_info["last_run"] = datetime.now()
            task_info["next_run"] = datetime.now() + timedelta(
                seconds=task_info["interval"]
            )
            task_info["run_count"] += 1
            task_info["success_count"] += 1
            task_info["last_duration"] = duration
            task_info["last_error"] = None

            logger.info(f"任务 '{name}' 执行成功，耗时 {duration:.2f}s")

            return result

        except Exception as e:
            duration = time.time() - start_time

            # 更新错误统计
            task_info["last_run"] = datetime.now()
            task_info["next_run"] = datetime.now() + timedelta(
                seconds=task_info["interval"]
            )
            task_info["run_count"] += 1
            task_info["error_count"] += 1
            task_info["last_duration"] = duration
            task_info["last_error"] = str(e)

            logger.error(f"任务 '{name}' 执行失败: {e}, 耗时 {duration:.2f}s")

            raise

    async def _scheduler_loop(self) -> None:
        """调度器主循环"""
        logger.info("任务调度器启动")

        while self.running:
            try:
                now = datetime.now()
                tasks_to_run = []

                # 检查需要执行的任务
                for name, task_info in self.tasks.items():
                    if not task_info["enabled"]:
                        continue

                    if now >= task_info["next_run"]:
                        tasks_to_run.append((name, task_info))

                # 并发执行所有到期的任务
                if tasks_to_run:
                    logger.debug(f"准备执行 {len(tasks_to_run)} 个任务")

                    # 创建任务协程
                    coroutines = []
                    for name, task_info in tasks_to_run:
                        coro = self._run_task(name, task_info)
                        coroutines.append(coro)

                    # 并发执行，但不等待全部完成（防止阻塞）
                    if coroutines:
                        await asyncio.gather(*coroutines, return_exceptions=True)

                # 休眠1秒再检查
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"调度器循环异常: {e}")
                await asyncio.sleep(5)  # 异常时等待5秒

    async def start(self) -> None:
        """启动调度器"""
        if self.running:
            logger.warning("调度器已在运行")
            return

        self.running = True
        self._loop_task = asyncio.create_task(self._scheduler_loop())
        logger.info("任务调度器已启动")

    async def stop(self) -> None:
        """停止调度器"""
        if not self.running:
            return

        self.running = False

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        logger.info("任务调度器已停止")

    def get_task_status(self) -> dict[str, Any]:
        """获取任务状态"""
        status = {
            "scheduler_running": self.running,
            "total_tasks": len(self.tasks),
            "enabled_tasks": len([t for t in self.tasks.values() if t["enabled"]]),
            "tasks": {},
        }

        for name, task_info in self.tasks.items():
            status["tasks"][name] = {
                "enabled": task_info["enabled"],
                "interval": task_info["interval"],
                "last_run": (
                    task_info["last_run"].isoformat() if task_info["last_run"] else None
                ),
                "next_run": (
                    task_info["next_run"].isoformat() if task_info["next_run"] else None
                ),
                "run_count": task_info["run_count"],
                "success_count": task_info["success_count"],
                "error_count": task_info["error_count"],
                "success_rate": task_info["success_count"]
                / max(task_info["run_count"], 1),
                "last_error": task_info["last_error"],
                "last_duration": task_info["last_duration"],
            }

        return status


# 全局调度器实例
_scheduler = None


def get_scheduler() -> TaskScheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler


# 便捷函数
def add_task(
    name: str,
    func: Callable,
    interval_seconds: int,
    run_immediately: bool = False,
    **kwargs: Any,
) -> None:
    """添加任务的便捷函数"""
    scheduler = get_scheduler()
    scheduler.add_task(name, func, interval_seconds, run_immediately, **kwargs)


async def start_scheduler() -> None:
    """启动调度器的便捷函数"""
    scheduler = get_scheduler()
    await scheduler.start()


async def stop_scheduler() -> None:
    """停止调度器的便捷函数"""
    scheduler = get_scheduler()
    await scheduler.stop()


def get_task_status() -> dict[str, Any]:
    """获取任务状态的便捷函数"""
    scheduler = get_scheduler()
    return scheduler.get_task_status()
