"""设备操控模块 - 通过 MCP 协议操控移动设备

提供设备发现、连接管理和操作执行功能。
通过抽象的 MCPClient 接口与 mobile-mcp 服务器通信，
支持不同的 MCP 实现后端。
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import OperationSequence, OperationStep

logger = logging.getLogger(__name__)


# ============================================================
# 数据类型定义
# ============================================================


@dataclass
class ConnectionResult:
    """设备连接结果"""

    success: bool
    device_id: str
    error_message: Optional[str] = None


@dataclass
class StepResult:
    """单步操作执行结果"""

    step_id: str
    success: bool
    error_message: Optional[str] = None


@dataclass
class SequenceResult:
    """操作序列执行结果"""

    sequence_id: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    step_results: List[StepResult] = field(default_factory=list)


@dataclass
class ScreenElement:
    """屏幕元素信息"""

    text: str
    x: int
    y: int
    element_type: Optional[str] = None


@dataclass
class DeviceInfo:
    """设备信息"""

    device_id: str
    name: str
    platform: str  # android, ios
    status: str  # available, connected, offline


# ============================================================
# MCP 客户端抽象层
# ============================================================


class MCPClient(ABC):
    """MCP 客户端抽象基类

    定义与 mobile-mcp 服务器通信的接口。
    具体实现可以使用 subprocess、HTTP 或其他传输方式。
    """

    @abstractmethod
    async def connect(self) -> bool:
        """建立与 MCP 服务器的连接"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开与 MCP 服务器的连接"""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """检查连接状态"""
        ...

    @abstractmethod
    async def list_devices(self) -> List[DeviceInfo]:
        """列出所有可用设备"""
        ...

    @abstractmethod
    async def select_device(self, device_id: str) -> bool:
        """选择目标设备"""
        ...

    @abstractmethod
    async def launch_app(self, package_name: str) -> bool:
        """启动指定 App"""
        ...

    @abstractmethod
    async def click(self, x: int, y: int) -> bool:
        """点击屏幕坐标"""
        ...

    @abstractmethod
    async def swipe(self, direction: str, x: Optional[int] = None,
                    y: Optional[int] = None, distance: Optional[int] = None) -> bool:
        """滑动屏幕"""
        ...

    @abstractmethod
    async def type_text(self, text: str, submit: bool = False) -> bool:
        """输入文本"""
        ...

    @abstractmethod
    async def list_elements(self) -> List[Dict[str, Any]]:
        """获取当前屏幕元素列表"""
        ...

    @abstractmethod
    async def press_button(self, button: str) -> bool:
        """按下设备按钮"""
        ...


class SubprocessMCPClient(MCPClient):
    """基于子进程的 MCP 客户端实现

    通过 subprocess 与 mobile-mcp 服务器进程通信。
    使用 JSON-RPC 风格的消息协议。
    """

    def __init__(self, server_command: Optional[str] = None):
        """初始化子进程 MCP 客户端

        Args:
            server_command: MCP 服务器启动命令。
                           如果为 None，则假设服务器已在外部启动。
        """
        self._server_command = server_command
        self._process: Optional[asyncio.subprocess.Process] = None
        self._connected = False
        self._selected_device: Optional[str] = None

    async def connect(self) -> bool:
        """建立与 MCP 服务器的连接

        如果提供了 server_command，则启动服务器进程。
        """
        if self._connected:
            return True

        try:
            if self._server_command:
                self._process = await asyncio.create_subprocess_shell(
                    self._server_command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                # 等待服务器就绪
                await asyncio.sleep(1.0)

                if self._process.returncode is not None:
                    logger.error("MCP 服务器进程启动失败")
                    return False

            self._connected = True
            logger.info("MCP 客户端连接成功")
            return True
        except Exception as e:
            logger.error(f"MCP 客户端连接失败: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接并终止服务器进程"""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None

        self._connected = False
        self._selected_device = None
        logger.info("MCP 客户端已断开连接")

    async def is_connected(self) -> bool:
        """检查连接状态"""
        if self._process and self._process.returncode is not None:
            self._connected = False
        return self._connected

    async def list_devices(self) -> List[DeviceInfo]:
        """列出所有可用设备

        通过 MCP 协议调用 mobile_list_available_devices。
        """
        if not self._connected:
            return []

        result = await self._call_tool("mobile_list_available_devices", {})
        if result is None:
            return []

        devices = []
        for item in result if isinstance(result, list) else []:
            devices.append(DeviceInfo(
                device_id=item.get("id", ""),
                name=item.get("name", ""),
                platform=item.get("platform", "unknown"),
                status=item.get("status", "unknown"),
            ))
        return devices

    async def select_device(self, device_id: str) -> bool:
        """选择目标设备"""
        self._selected_device = device_id
        return True

    async def launch_app(self, package_name: str) -> bool:
        """启动指定 App"""
        if not self._connected or not self._selected_device:
            return False

        result = await self._call_tool("mobile_launch_app", {
            "device": self._selected_device,
            "packageName": package_name,
        })
        return result is not None

    async def click(self, x: int, y: int) -> bool:
        """点击屏幕坐标"""
        if not self._connected or not self._selected_device:
            return False

        result = await self._call_tool("mobile_click_on_screen_at_coordinates", {
            "device": self._selected_device,
            "x": x,
            "y": y,
        })
        return result is not None

    async def swipe(self, direction: str, x: Optional[int] = None,
                    y: Optional[int] = None, distance: Optional[int] = None) -> bool:
        """滑动屏幕"""
        if not self._connected or not self._selected_device:
            return False

        params: Dict[str, Any] = {
            "device": self._selected_device,
            "direction": direction,
        }
        if x is not None:
            params["x"] = x
        if y is not None:
            params["y"] = y
        if distance is not None:
            params["distance"] = distance

        result = await self._call_tool("mobile_swipe_on_screen", params)
        return result is not None

    async def type_text(self, text: str, submit: bool = False) -> bool:
        """输入文本"""
        if not self._connected or not self._selected_device:
            return False

        result = await self._call_tool("mobile_type_keys", {
            "device": self._selected_device,
            "text": text,
            "submit": submit,
        })
        return result is not None

    async def list_elements(self) -> List[Dict[str, Any]]:
        """获取当前屏幕元素列表"""
        if not self._connected or not self._selected_device:
            return []

        result = await self._call_tool("mobile_list_elements_on_screen", {
            "device": self._selected_device,
        })
        if result is None:
            return []
        return result if isinstance(result, list) else []

    async def press_button(self, button: str) -> bool:
        """按下设备按钮"""
        if not self._connected or not self._selected_device:
            return False

        result = await self._call_tool("mobile_press_button", {
            "device": self._selected_device,
            "button": button,
        })
        return result is not None

    async def _call_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """调用 MCP 工具

        通过 stdin/stdout 与 MCP 服务器进程通信。
        发送 JSON-RPC 格式的请求，解析响应。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            工具返回结果，失败时返回 None
        """
        if not self._process or not self._process.stdin or not self._process.stdout:
            logger.warning(f"无法调用工具 {tool_name}: 进程未就绪")
            return None

        request = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params,
            },
            "id": 1,
        })

        try:
            self._process.stdin.write((request + "\n").encode())
            await self._process.stdin.drain()

            response_line = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=30.0,
            )

            if not response_line:
                return None

            response = json.loads(response_line.decode())
            if "error" in response:
                logger.error(f"MCP 工具调用失败 [{tool_name}]: {response['error']}")
                return None

            return response.get("result")
        except asyncio.TimeoutError:
            logger.error(f"MCP 工具调用超时 [{tool_name}]")
            return None
        except Exception as e:
            logger.error(f"MCP 工具调用异常 [{tool_name}]: {e}")
            return None


# ============================================================
# DeviceController 主类
# ============================================================


class DeviceController:
    """设备操控器

    通过 MCPClient 与移动设备交互，提供设备发现、连接管理、
    App 启动和操作序列执行等功能。
    """

    def __init__(
        self,
        mcp_client: Optional[MCPClient] = None,
        step_id_callback: Optional[Callable[[Optional[str]], None]] = None,
    ):
        """初始化设备操控器

        Args:
            mcp_client: MCP 客户端实例。如果为 None，
                       则创建默认的 SubprocessMCPClient。
            step_id_callback: 步骤 ID 回调函数。执行每个步骤前调用，
                            传入当前步骤 ID；序列执行完毕后传入 None。
                            用于与 TrafficInterceptor 协调，将捕获的请求
                            关联到正确的操作步骤。
        """
        self._mcp_client = mcp_client or SubprocessMCPClient()
        self._step_id_callback = step_id_callback
        self._connected_device: Optional[str] = None
        self._is_connected = False

    @property
    def connected_device(self) -> Optional[str]:
        """当前连接的设备 ID"""
        return self._connected_device

    @property
    def is_connected(self) -> bool:
        """是否已连接到设备"""
        return self._is_connected

    async def discover_devices(self) -> List[DeviceInfo]:
        """发现可用设备

        连接 MCP 服务器并列出所有可用的移动设备。

        Returns:
            可用设备列表
        """
        # 确保 MCP 客户端已连接
        if not await self._mcp_client.is_connected():
            connected = await self._mcp_client.connect()
            if not connected:
                logger.error("无法连接到 MCP 服务器，设备发现失败")
                return []

        devices = await self._mcp_client.list_devices()
        logger.info(f"发现 {len(devices)} 个设备")
        return devices

    async def connect(self, device_id: str) -> ConnectionResult:
        """连接到指定设备

        建立与 MCP 服务器的连接，并选择目标设备。

        Args:
            device_id: 目标设备标识符

        Returns:
            ConnectionResult 包含连接结果
        """
        # 如果已连接到其他设备，先断开
        if self._is_connected and self._connected_device != device_id:
            await self.disconnect()

        # 如果已连接到同一设备，直接返回成功
        if self._is_connected and self._connected_device == device_id:
            return ConnectionResult(success=True, device_id=device_id)

        # 建立 MCP 连接
        if not await self._mcp_client.is_connected():
            connected = await self._mcp_client.connect()
            if not connected:
                return ConnectionResult(
                    success=False,
                    device_id=device_id,
                    error_message="无法连接到 MCP 服务器",
                )

        # 选择目标设备
        device_selected = await self._mcp_client.select_device(device_id)
        if not device_selected:
            return ConnectionResult(
                success=False,
                device_id=device_id,
                error_message=f"无法选择设备: {device_id}",
            )

        self._connected_device = device_id
        self._is_connected = True
        logger.info(f"已连接到设备: {device_id}")

        return ConnectionResult(success=True, device_id=device_id)

    async def disconnect(self) -> None:
        """断开与当前设备的连接

        清理连接状态并断开 MCP 客户端。
        """
        if not self._is_connected:
            return

        device_id = self._connected_device
        await self._mcp_client.disconnect()
        self._connected_device = None
        self._is_connected = False
        logger.info(f"已断开设备连接: {device_id}")

    async def launch_app(self, package_name: str) -> bool:
        """启动指定 App

        Args:
            package_name: App 包名

        Returns:
            是否启动成功
        """
        if not self._is_connected:
            logger.error("未连接到设备，无法启动 App")
            return False

        result = await self._mcp_client.launch_app(package_name)
        if result:
            logger.info(f"App 启动成功: {package_name}")
        else:
            logger.error(f"App 启动失败: {package_name}")
        return result

    async def execute_step(self, step: OperationStep) -> StepResult:
        """执行单个操作步骤

        根据步骤的 action_type 调用对应的 MCP 工具。
        执行前通过 step_id_callback 通知当前步骤 ID，
        以便 TrafficInterceptor 将捕获的请求关联到此步骤。

        Args:
            step: 操作步骤

        Returns:
            StepResult 包含执行结果
        """
        if not self._is_connected:
            return StepResult(
                step_id=step.id,
                success=False,
                error_message="未连接到设备",
            )

        # 通知 TrafficInterceptor 当前步骤 ID
        if self._step_id_callback:
            self._step_id_callback(step.id)

        try:
            success = await self._dispatch_action(step)
            return StepResult(step_id=step.id, success=success)
        except Exception as e:
            error_msg = f"步骤执行异常: {e}"
            logger.error(f"[{step.id}] {error_msg}")
            return StepResult(
                step_id=step.id,
                success=False,
                error_message=error_msg,
            )

    async def execute_sequence(self, sequence: OperationSequence) -> SequenceResult:
        """执行操作序列

        顺序执行序列中的所有步骤，采用容错模式：
        步骤失败时记录错误并继续执行后续步骤。
        执行完毕后重置步骤 ID 回调为 None。

        Args:
            sequence: 操作序列

        Returns:
            SequenceResult 包含整体执行结果
        """
        result = SequenceResult(
            sequence_id=sequence.id,
            total_steps=len(sequence.steps),
            completed_steps=0,
            failed_steps=0,
        )

        for step in sequence.steps:
            step_result = await self.execute_step(step)
            result.step_results.append(step_result)

            if step_result.success:
                result.completed_steps += 1
            else:
                result.failed_steps += 1
                logger.warning(
                    f"步骤 {step.id} 执行失败: {step_result.error_message}，继续执行后续步骤"
                )

        # 序列执行完毕，重置步骤 ID
        if self._step_id_callback:
            self._step_id_callback(None)

        return result

    async def get_screen_elements(self) -> List[ScreenElement]:
        """获取当前屏幕上的元素列表

        Returns:
            屏幕元素列表
        """
        if not self._is_connected:
            return []

        raw_elements = await self._mcp_client.list_elements()
        elements = []
        for item in raw_elements:
            elements.append(ScreenElement(
                text=item.get("text", ""),
                x=item.get("x", 0),
                y=item.get("y", 0),
                element_type=item.get("type"),
            ))
        return elements

    async def _dispatch_action(self, step: OperationStep) -> bool:
        """根据操作类型分发执行

        Args:
            step: 操作步骤

        Returns:
            是否执行成功
        """
        action_type = step.action_type
        params = step.parameters

        if action_type == "click":
            x = params.get("x", 0)
            y = params.get("y", 0)
            return await self._mcp_client.click(x, y)

        elif action_type == "swipe":
            direction = params.get("direction", "up")
            x = params.get("x")
            y = params.get("y")
            distance = params.get("distance")
            return await self._mcp_client.swipe(direction, x, y, distance)

        elif action_type == "input":
            text = params.get("text", "")
            submit = params.get("submit", False)
            return await self._mcp_client.type_text(text, submit)

        elif action_type == "navigate":
            button = params.get("button", "BACK")
            return await self._mcp_client.press_button(button)

        elif action_type == "wait":
            duration_ms = params.get("duration_ms", 1000)
            await asyncio.sleep(duration_ms / 1000.0)
            return True

        else:
            logger.warning(f"未知操作类型: {action_type}")
            return False
