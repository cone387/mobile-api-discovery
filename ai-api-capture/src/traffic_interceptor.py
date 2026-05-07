"""流量拦截模块 - 通过 mitmproxy 捕获和存储网络流量

本模块实现 TrafficInterceptor 类，负责：
- 启动/停止 mitmproxy 代理服务器（使用 DumpMaster）
- 在后台线程中运行 mitmproxy 事件循环
- 管理 CaptureAddon 生命周期
- 提供异步接口供系统其他模块调用
- 支持动态更新过滤规则和步骤 ID
- 将捕获的请求字典转换为 CapturedRequest 模型对象
- 支持回调注册用于实时捕获通知
"""

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster

import sys
import os

# 将 addons 目录加入 Python 路径以便导入 CaptureAddon
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "addons"))

from capture_addon import CaptureAddon, FilterRules
from src.models import CapturedRequest


@dataclass
class ProxyConfig:
    """代理服务器配置

    Attributes:
        listen_host: 监听地址，默认 0.0.0.0（所有网络接口）
        listen_port: 监听端口，默认 8080
        storage_path: 捕获数据存储路径
    """

    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    storage_path: str = "./output/captures"


class TrafficInterceptor:
    """流量拦截器，封装 mitmproxy 代理服务器和 CaptureAddon。

    通过 mitmproxy 的 Python API（DumpMaster）在后台线程中运行代理服务器，
    提供异步接口供系统其他模块调用。

    使用示例:
        interceptor = TrafficInterceptor()
        await interceptor.start(ProxyConfig(listen_port=8080))
        interceptor.set_step_id("step-001")
        # ... 设备操作触发流量 ...
        requests = await interceptor.get_captured_requests()
        await interceptor.stop()
    """

    def __init__(self) -> None:
        """初始化 TrafficInterceptor。"""
        self._master: Optional[DumpMaster] = None
        self._addon: Optional[CaptureAddon] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._config: Optional[ProxyConfig] = None
        self._callbacks: List[Callable] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def is_running(self) -> bool:
        """代理服务器是否正在运行。"""
        return self._running

    @property
    def addon(self) -> Optional[CaptureAddon]:
        """获取当前的 CaptureAddon 实例。"""
        return self._addon

    async def start(self, config: ProxyConfig) -> None:
        """启动 mitmproxy 代理服务器。

        在后台线程中启动 DumpMaster，配置监听地址和端口，
        并附加 CaptureAddon 用于捕获流量。

        Args:
            config: 代理服务器配置

        Raises:
            RuntimeError: 如果代理服务器已在运行
        """
        if self._running:
            raise RuntimeError("TrafficInterceptor is already running")

        self._config = config
        self._loop = asyncio.get_event_loop()

        # 创建 CaptureAddon 实例
        self._addon = CaptureAddon(
            storage_path=config.storage_path,
            filter_rules=FilterRules(),
        )

        # 使用 threading.Event 等待 mitmproxy 启动完成
        started_event = threading.Event()
        error_holder: List[Optional[Exception]] = [None]

        def _run_master() -> None:
            """在后台线程中运行 mitmproxy DumpMaster。"""
            try:
                # 创建新的事件循环用于 mitmproxy
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                opts = options.Options(
                    listen_host=config.listen_host,
                    listen_port=config.listen_port,
                )

                self._master = DumpMaster(opts)
                self._master.addons.add(self._addon)

                # 通知主线程启动完成
                started_event.set()

                # 运行 mitmproxy 事件循环（阻塞）
                self._master.run()
            except Exception as e:
                error_holder[0] = e
                started_event.set()
            finally:
                self._running = False

        # 在后台线程中启动 mitmproxy
        self._thread = threading.Thread(
            target=_run_master,
            name="mitmproxy-thread",
            daemon=True,
        )
        self._thread.start()

        # 等待 mitmproxy 启动完成（最多 10 秒）
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: started_event.wait(timeout=10.0)
        )

        if error_holder[0] is not None:
            raise RuntimeError(
                f"Failed to start mitmproxy: {error_holder[0]}"
            ) from error_holder[0]

        self._running = True

    async def stop(self) -> None:
        """停止 mitmproxy 代理服务器。

        关闭 DumpMaster 并等待后台线程结束。

        Raises:
            RuntimeError: 如果代理服务器未在运行
        """
        if not self._running:
            raise RuntimeError("TrafficInterceptor is not running")

        if self._master is not None:
            # 在 mitmproxy 的线程中调度关闭
            self._master.shutdown()

        # 等待后台线程结束
        if self._thread is not None:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._thread.join(timeout=5.0)
            )

        self._running = False
        self._master = None
        self._addon = None
        self._thread = None

    async def set_filter(self, rules: FilterRules) -> None:
        """动态更新过滤规则。

        Args:
            rules: 新的过滤规则配置

        Raises:
            RuntimeError: 如果代理服务器未在运行
        """
        if not self._running or self._addon is None:
            raise RuntimeError("TrafficInterceptor is not running")

        self._addon.filter_rules = rules

    def set_step_id(self, step_id: Optional[str]) -> None:
        """设置当前操作步骤 ID。

        委托给 CaptureAddon，后续捕获的请求将关联到此步骤 ID。

        Args:
            step_id: 操作步骤 ID，None 表示无关联步骤
        """
        if self._addon is not None:
            self._addon.set_step_id(step_id)

    async def get_captured_requests(self) -> List[CapturedRequest]:
        """获取所有已捕获的请求，转换为 CapturedRequest 模型对象。

        从 CaptureAddon 获取原始字典列表，并转换为类型化的
        CapturedRequest 数据类实例。

        Returns:
            CapturedRequest 对象列表

        Raises:
            RuntimeError: 如果代理服务器未在运行
        """
        if self._addon is None:
            raise RuntimeError("TrafficInterceptor is not running")

        raw_requests = self._addon.get_captured_requests()
        return [self._dict_to_captured_request(r) for r in raw_requests]

    async def clear(self) -> None:
        """清空所有已捕获的请求记录。

        Raises:
            RuntimeError: 如果代理服务器未在运行
        """
        if not self._running or self._addon is None:
            raise RuntimeError("TrafficInterceptor is not running")

        self._addon.clear()

    def on_request_captured(self, callback: Callable) -> None:
        """注册请求捕获回调函数。

        当有新请求被捕获时，回调函数将被调用，参数为 CapturedRequest 对象。

        Args:
            callback: 回调函数，签名为 (CapturedRequest) -> None
        """
        self._callbacks.append(callback)

    def _notify_callbacks(self, request: CapturedRequest) -> None:
        """通知所有已注册的回调函数。

        Args:
            request: 新捕获的请求对象
        """
        for callback in self._callbacks:
            try:
                callback(request)
            except Exception:
                # 回调异常不应影响主流程
                pass

    @staticmethod
    def _dict_to_captured_request(data: dict) -> CapturedRequest:
        """将捕获的请求字典转换为 CapturedRequest 模型对象。

        处理 base64 编码的 body 字段和时间戳解析。

        Args:
            data: CaptureAddon 产生的请求字典

        Returns:
            CapturedRequest 模型对象
        """
        import base64

        # 解析 body 字段（base64 编码的 bytes 或 None）
        body = None
        if data.get("body") is not None:
            body = base64.b64decode(data["body"])

        response_body = None
        if data.get("response_body") is not None:
            response_body = base64.b64decode(data["response_body"])

        # 解析时间戳
        timestamp = datetime.fromisoformat(data["timestamp"])

        return CapturedRequest(
            id=data["id"],
            timestamp=timestamp,
            operation_step_id=data.get("operation_step_id", ""),
            method=data["method"],
            url=data["url"],
            headers=data.get("headers", {}),
            body=body,
            response_status=data.get("response_status", 0),
            response_headers=data.get("response_headers", {}),
            response_body=response_body,
            is_decrypted=data.get("is_decrypted", True),
        )
