"""批量采集模块 - 执行批量数据采集

实现功能：
- 异步批量请求执行器：并发控制（信号量）、请求间隔
- 采集数据 JSON 存储：写入格式包含请求参数、响应数据、时间戳
- 成功率监控和自动暂停逻辑：连续失败计数、阈值触发
- 认证失败检测和任务暂停通知
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Awaitable, Dict, List

from .models import CrawlConfig, CrawlStats, CrawlTask


@dataclass
class CrawlDataRecord:
    """单条采集数据记录"""

    request_params: dict
    response_data: dict
    timestamp: str
    status_code: int
    success: bool

    def to_dict(self) -> dict:
        return {
            "request_params": self.request_params,
            "response_data": self.response_data,
            "timestamp": self.timestamp,
            "status_code": self.status_code,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlDataRecord":
        return cls(
            request_params=data["request_params"],
            response_data=data["response_data"],
            timestamp=data["timestamp"],
            status_code=data["status_code"],
            success=data["success"],
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CrawlDataRecord):
            return NotImplemented
        return (
            self.request_params == other.request_params
            and self.response_data == other.response_data
            and self.timestamp == other.timestamp
            and self.status_code == other.status_code
            and self.success == other.success
        )


# Type alias for the request function signature
# Returns: (success: bool, data: dict, status_code: int)
RequestFn = Callable[[], Awaitable[tuple]]


class BatchCrawler:
    """批量采集执行器

    使用 asyncio + 信号量实现并发控制，支持：
    - 并发数限制
    - 请求间隔控制
    - 连续失败阈值自动暂停
    - 认证失败检测（401/403）
    - 采集数据 JSON 持久化
    """

    def __init__(self, storage_path: str = "./output/data"):
        self.storage_path = Path(storage_path)
        self._tasks: Dict[str, CrawlTask] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._running_loops: Dict[str, asyncio.Task] = {}
        self._pause_events: Dict[str, asyncio.Event] = {}

        # Callbacks
        self._on_pause_callback: Optional[Callable[[str, str], None]] = None
        self._on_auth_failure_callback: Optional[Callable[[str, str], None]] = None

    def set_on_pause_callback(self, callback: Callable[[str, str], None]) -> None:
        """设置任务暂停时的回调函数

        Args:
            callback: 接收 (task_id, reason) 参数的回调函数
        """
        self._on_pause_callback = callback

    def set_on_auth_failure_callback(self, callback: Callable[[str, str], None]) -> None:
        """设置认证失败时的回调函数

        Args:
            callback: 接收 (task_id, message) 参数的回调函数
        """
        self._on_auth_failure_callback = callback

    async def start_task(self, task: CrawlTask, request_fn: RequestFn) -> None:
        """启动采集任务

        Args:
            task: 采集任务配置
            request_fn: 异步请求函数，返回 (success, data, status_code)
        """
        task.status = "running"
        self._tasks[task.id] = task
        self._semaphores[task.id] = asyncio.Semaphore(task.config.concurrency)
        self._pause_events[task.id] = asyncio.Event()
        self._pause_events[task.id].set()  # Initially not paused

        # Ensure storage directory exists
        task_dir = self.storage_path / task.id
        task_dir.mkdir(parents=True, exist_ok=True)

        # Start the crawl loop
        loop_task = asyncio.create_task(
            self._crawl_loop(task.id, request_fn)
        )
        self._running_loops[task.id] = loop_task

    async def pause_task(self, task_id: str) -> None:
        """暂停采集任务"""
        if task_id in self._tasks:
            self._tasks[task_id].status = "paused"
            if task_id in self._pause_events:
                self._pause_events[task_id].clear()

    async def resume_task(self, task_id: str) -> None:
        """恢复采集任务"""
        if task_id in self._tasks:
            task = self._tasks[task_id]
            task.status = "running"
            task.stats.consecutive_failures = 0
            if task_id in self._pause_events:
                self._pause_events[task_id].set()

    def get_task_stats(self, task_id: str) -> Optional[CrawlStats]:
        """获取任务统计信息"""
        if task_id in self._tasks:
            return self._tasks[task_id].stats
        return None

    def get_task(self, task_id: str) -> Optional[CrawlTask]:
        """获取任务对象"""
        return self._tasks.get(task_id)

    def record_result(self, task_id: str, success: bool, status_code: int = 200) -> None:
        """记录单次请求结果，更新统计信息并检查阈值

        Args:
            task_id: 任务 ID
            success: 请求是否成功
            status_code: HTTP 响应状态码
        """
        if task_id not in self._tasks:
            return

        task = self._tasks[task_id]
        stats = task.stats
        stats.total_requests += 1

        if success:
            stats.success_count += 1
            stats.consecutive_failures = 0
            stats.data_collected += 1
        else:
            stats.failure_count += 1
            stats.consecutive_failures += 1

        # Check for auth failure (401/403)
        if status_code in (401, 403):
            self._handle_auth_failure(task_id, status_code)
            return

        # Check failure threshold
        if stats.consecutive_failures >= task.config.failure_threshold:
            self._handle_threshold_exceeded(task_id)

    def _handle_threshold_exceeded(self, task_id: str) -> None:
        """处理连续失败超过阈值"""
        task = self._tasks[task_id]
        task.status = "paused"
        if task_id in self._pause_events:
            self._pause_events[task_id].clear()

        reason = (
            f"连续失败次数 ({task.stats.consecutive_failures}) "
            f"已达到阈值 ({task.config.failure_threshold})，任务已自动暂停"
        )
        if self._on_pause_callback:
            self._on_pause_callback(task_id, reason)

    def _handle_auth_failure(self, task_id: str, status_code: int) -> None:
        """处理认证失败"""
        task = self._tasks[task_id]
        task.status = "paused"
        if task_id in self._pause_events:
            self._pause_events[task_id].clear()

        message = (
            f"检测到认证失败 (HTTP {status_code})，"
            f"任务已暂停，请更新会话参数后恢复任务"
        )
        if self._on_auth_failure_callback:
            self._on_auth_failure_callback(task_id, message)
        if self._on_pause_callback:
            self._on_pause_callback(task_id, message)

    async def _crawl_loop(self, task_id: str, request_fn: RequestFn) -> None:
        """主采集循环"""
        task = self._tasks[task_id]
        config = task.config

        while task.status == "running":
            # Wait if paused
            if task_id in self._pause_events:
                await self._pause_events[task_id].wait()

            # Check if still running after potential pause
            if task.status != "running":
                break

            # Acquire semaphore for concurrency control
            async with self._semaphores[task_id]:
                try:
                    result = await request_fn()
                    success, data, status_code = result

                    # Record the result
                    self.record_result(task_id, success, status_code)

                    # Store data if successful
                    if success and data:
                        record = CrawlDataRecord(
                            request_params=data.get("request_params", {}),
                            response_data=data.get("response_data", {}),
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            status_code=status_code,
                            success=True,
                        )
                        await self._save_record(task_id, record)

                except Exception:
                    # Record failure on exception
                    self.record_result(task_id, False, 500)

            # Request interval
            if config.interval_ms > 0 and task.status == "running":
                await asyncio.sleep(config.interval_ms / 1000.0)

    async def _save_record(self, task_id: str, record: CrawlDataRecord) -> None:
        """保存单条采集记录到 JSON 文件"""
        task_dir = self.storage_path / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        # Use incrementing index for filenames
        existing = list(task_dir.glob("*.json"))
        index = len(existing)
        file_path = task_dir / f"{index:06d}.json"

        file_path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def stop_task(self, task_id: str) -> None:
        """停止采集任务"""
        if task_id in self._tasks:
            self._tasks[task_id].status = "completed"
        if task_id in self._pause_events:
            self._pause_events[task_id].set()  # Unblock if paused
        if task_id in self._running_loops:
            loop_task = self._running_loops[task_id]
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
            del self._running_loops[task_id]

    def load_task_data(self, task_id: str) -> List[CrawlDataRecord]:
        """加载指定任务的所有采集数据（同步方法）"""
        task_dir = self.storage_path / task_id
        if not task_dir.exists():
            return []

        records = []
        for file_path in sorted(task_dir.glob("*.json")):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            records.append(CrawlDataRecord.from_dict(data))
        return records

    def save_record_sync(self, task_id: str, record: CrawlDataRecord) -> None:
        """同步保存单条采集记录（用于测试）"""
        task_dir = self.storage_path / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        existing = list(task_dir.glob("*.json"))
        index = len(existing)
        file_path = task_dir / f"{index:06d}.json"

        file_path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
