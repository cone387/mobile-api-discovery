"""DeviceController 单元测试

测试设备发现、连接管理和断开逻辑。
测试与 TrafficInterceptor 的步骤 ID 协调。
使用 Mock MCP 客户端避免依赖真实设备。
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from src.device_controller import (
    ConnectionResult,
    DeviceController,
    DeviceInfo,
    MCPClient,
    ScreenElement,
    SequenceResult,
    StepResult,
)
from src.models import OperationSequence, OperationStep


# ============================================================
# Mock MCP 客户端
# ============================================================


class MockMCPClient(MCPClient):
    """用于测试的 Mock MCP 客户端"""

    def __init__(
        self,
        connect_success: bool = True,
        devices: Optional[List[DeviceInfo]] = None,
    ):
        self._connect_success = connect_success
        self._devices = devices or []
        self._connected = False
        self._selected_device: Optional[str] = None
        self.connect_called = False
        self.disconnect_called = False
        self.select_device_calls: List[str] = []

    async def connect(self) -> bool:
        self.connect_called = True
        if self._connect_success:
            self._connected = True
        return self._connect_success

    async def disconnect(self) -> None:
        self.disconnect_called = True
        self._connected = False
        self._selected_device = None

    async def is_connected(self) -> bool:
        return self._connected

    async def list_devices(self) -> List[DeviceInfo]:
        return self._devices

    async def select_device(self, device_id: str) -> bool:
        self.select_device_calls.append(device_id)
        self._selected_device = device_id
        return True

    async def launch_app(self, package_name: str) -> bool:
        return self._connected and self._selected_device is not None

    async def click(self, x: int, y: int) -> bool:
        return True

    async def swipe(self, direction: str, x: Optional[int] = None,
                    y: Optional[int] = None, distance: Optional[int] = None) -> bool:
        return True

    async def type_text(self, text: str, submit: bool = False) -> bool:
        return True

    async def list_elements(self) -> List[Dict[str, Any]]:
        return [
            {"text": "Button1", "x": 100, "y": 200, "type": "button"},
            {"text": "Input", "x": 150, "y": 300, "type": "input"},
        ]

    async def press_button(self, button: str) -> bool:
        return True


# ============================================================
# 设备发现测试
# ============================================================


class TestDeviceDiscovery:
    """设备发现功能测试"""

    @pytest.mark.asyncio
    async def test_discover_devices_returns_available_devices(self):
        """发现设备应返回可用设备列表"""
        devices = [
            DeviceInfo(device_id="emulator-5554", name="Pixel 6", platform="android", status="available"),
            DeviceInfo(device_id="iphone-12", name="iPhone 12", platform="ios", status="available"),
        ]
        mock_client = MockMCPClient(devices=devices)
        controller = DeviceController(mcp_client=mock_client)

        result = await controller.discover_devices()

        assert len(result) == 2
        assert result[0].device_id == "emulator-5554"
        assert result[1].device_id == "iphone-12"

    @pytest.mark.asyncio
    async def test_discover_devices_empty_when_none_available(self):
        """没有可用设备时应返回空列表"""
        mock_client = MockMCPClient(devices=[])
        controller = DeviceController(mcp_client=mock_client)

        result = await controller.discover_devices()

        assert result == []

    @pytest.mark.asyncio
    async def test_discover_devices_connects_mcp_if_not_connected(self):
        """设备发现时如果 MCP 未连接应自动连接"""
        mock_client = MockMCPClient(devices=[
            DeviceInfo(device_id="dev1", name="Dev1", platform="android", status="available"),
        ])
        controller = DeviceController(mcp_client=mock_client)

        await controller.discover_devices()

        assert mock_client.connect_called

    @pytest.mark.asyncio
    async def test_discover_devices_fails_when_mcp_connection_fails(self):
        """MCP 连接失败时设备发现应返回空列表"""
        mock_client = MockMCPClient(connect_success=False)
        controller = DeviceController(mcp_client=mock_client)

        result = await controller.discover_devices()

        assert result == []


# ============================================================
# 连接管理测试
# ============================================================


class TestConnectionManagement:
    """设备连接管理测试"""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """成功连接到设备"""
        mock_client = MockMCPClient()
        controller = DeviceController(mcp_client=mock_client)

        result = await controller.connect("emulator-5554")

        assert result.success is True
        assert result.device_id == "emulator-5554"
        assert result.error_message is None
        assert controller.is_connected is True
        assert controller.connected_device == "emulator-5554"

    @pytest.mark.asyncio
    async def test_connect_fails_when_mcp_unavailable(self):
        """MCP 服务器不可用时连接应失败"""
        mock_client = MockMCPClient(connect_success=False)
        controller = DeviceController(mcp_client=mock_client)

        result = await controller.connect("emulator-5554")

        assert result.success is False
        assert result.device_id == "emulator-5554"
        assert result.error_message is not None
        assert controller.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_same_device_returns_success(self):
        """重复连接同一设备应直接返回成功"""
        mock_client = MockMCPClient()
        controller = DeviceController(mcp_client=mock_client)

        await controller.connect("emulator-5554")
        result = await controller.connect("emulator-5554")

        assert result.success is True
        # select_device 只应被调用一次
        assert len(mock_client.select_device_calls) == 1

    @pytest.mark.asyncio
    async def test_connect_different_device_disconnects_first(self):
        """连接不同设备时应先断开当前连接"""
        mock_client = MockMCPClient()
        controller = DeviceController(mcp_client=mock_client)

        await controller.connect("device-1")
        assert controller.connected_device == "device-1"

        await controller.connect("device-2")
        assert controller.connected_device == "device-2"
        assert mock_client.disconnect_called


# ============================================================
# 断开连接测试
# ============================================================


class TestDisconnection:
    """设备断开连接测试"""

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        """断开连接应清理所有状态"""
        mock_client = MockMCPClient()
        controller = DeviceController(mcp_client=mock_client)

        await controller.connect("emulator-5554")
        assert controller.is_connected is True

        await controller.disconnect()

        assert controller.is_connected is False
        assert controller.connected_device is None
        assert mock_client.disconnect_called

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected_is_noop(self):
        """未连接时断开应为空操作"""
        mock_client = MockMCPClient()
        controller = DeviceController(mcp_client=mock_client)

        await controller.disconnect()

        assert mock_client.disconnect_called is False

    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(self):
        """断开后应能重新连接"""
        mock_client = MockMCPClient()
        controller = DeviceController(mcp_client=mock_client)

        await controller.connect("device-1")
        await controller.disconnect()

        result = await controller.connect("device-2")

        assert result.success is True
        assert controller.connected_device == "device-2"


# ============================================================
# ConnectionResult 数据类型测试
# ============================================================


class TestConnectionResult:
    """ConnectionResult 数据类型测试"""

    def test_success_result(self):
        """成功结果应正确构造"""
        result = ConnectionResult(success=True, device_id="dev-1")
        assert result.success is True
        assert result.device_id == "dev-1"
        assert result.error_message is None

    def test_failure_result(self):
        """失败结果应包含错误信息"""
        result = ConnectionResult(
            success=False,
            device_id="dev-1",
            error_message="Connection refused",
        )
        assert result.success is False
        assert result.error_message == "Connection refused"


# ============================================================
# 步骤 ID 回调协调测试
# ============================================================


class TestStepIdCallback:
    """测试 DeviceController 与 TrafficInterceptor 的步骤 ID 协调"""

    @pytest.mark.asyncio
    async def test_execute_step_calls_callback_with_step_id(self):
        """执行步骤前应调用回调传入当前步骤 ID"""
        callback_calls: List[Optional[str]] = []
        mock_client = MockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=lambda sid: callback_calls.append(sid),
        )

        await controller.connect("device-1")

        step = OperationStep(
            id="step-001",
            sequence_id="seq-1",
            action_type="click",
            target=None,
            parameters={"x": 100, "y": 200},
            status="pending",
            error_message=None,
        )

        await controller.execute_step(step)

        assert callback_calls == ["step-001"]

    @pytest.mark.asyncio
    async def test_execute_sequence_calls_callback_for_each_step(self):
        """执行序列时应为每个步骤调用回调"""
        callback_calls: List[Optional[str]] = []
        mock_client = MockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=lambda sid: callback_calls.append(sid),
        )

        await controller.connect("device-1")

        sequence = OperationSequence(
            id="seq-1",
            app_package="com.example.app",
            intent_description="测试操作",
            steps=[
                OperationStep(
                    id="step-001",
                    sequence_id="seq-1",
                    action_type="click",
                    target=None,
                    parameters={"x": 100, "y": 200},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-002",
                    sequence_id="seq-1",
                    action_type="swipe",
                    target=None,
                    parameters={"direction": "up"},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-003",
                    sequence_id="seq-1",
                    action_type="wait",
                    target=None,
                    parameters={"duration_ms": 100},
                    status="pending",
                    error_message=None,
                ),
            ],
            created_at=datetime(2024, 1, 1),
        )

        await controller.execute_sequence(sequence)

        # 应该为每个步骤调用一次，最后重置为 None
        assert callback_calls == ["step-001", "step-002", "step-003", None]

    @pytest.mark.asyncio
    async def test_execute_sequence_resets_step_id_after_completion(self):
        """序列执行完毕后应重置步骤 ID 为 None"""
        callback_calls: List[Optional[str]] = []
        mock_client = MockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=lambda sid: callback_calls.append(sid),
        )

        await controller.connect("device-1")

        sequence = OperationSequence(
            id="seq-1",
            app_package="com.example.app",
            intent_description="测试",
            steps=[
                OperationStep(
                    id="step-001",
                    sequence_id="seq-1",
                    action_type="click",
                    target=None,
                    parameters={"x": 50, "y": 50},
                    status="pending",
                    error_message=None,
                ),
            ],
            created_at=datetime(2024, 1, 1),
        )

        await controller.execute_sequence(sequence)

        # 最后一个调用应该是 None（重置）
        assert callback_calls[-1] is None

    @pytest.mark.asyncio
    async def test_no_callback_does_not_raise(self):
        """没有设置回调时执行步骤不应报错"""
        mock_client = MockMCPClient()
        controller = DeviceController(mcp_client=mock_client)

        await controller.connect("device-1")

        step = OperationStep(
            id="step-001",
            sequence_id="seq-1",
            action_type="click",
            target=None,
            parameters={"x": 100, "y": 200},
            status="pending",
            error_message=None,
        )

        # 不应抛出异常
        result = await controller.execute_step(step)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_callback_not_called_when_not_connected(self):
        """未连接设备时不应调用回调"""
        callback_calls: List[Optional[str]] = []
        mock_client = MockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=lambda sid: callback_calls.append(sid),
        )

        step = OperationStep(
            id="step-001",
            sequence_id="seq-1",
            action_type="click",
            target=None,
            parameters={"x": 100, "y": 200},
            status="pending",
            error_message=None,
        )

        result = await controller.execute_step(step)

        assert result.success is False
        assert callback_calls == []

    @pytest.mark.asyncio
    async def test_callback_with_traffic_interceptor_set_step_id(self):
        """验证回调可以直接使用 TrafficInterceptor.set_step_id 方法"""
        # 模拟 TrafficInterceptor 的 set_step_id 行为
        step_ids_received: List[Optional[str]] = []

        def mock_set_step_id(step_id: Optional[str]) -> None:
            step_ids_received.append(step_id)

        mock_client = MockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=mock_set_step_id,
        )

        await controller.connect("device-1")

        sequence = OperationSequence(
            id="seq-1",
            app_package="com.example.app",
            intent_description="模拟与 TrafficInterceptor 协调",
            steps=[
                OperationStep(
                    id="step-A",
                    sequence_id="seq-1",
                    action_type="click",
                    target=None,
                    parameters={"x": 10, "y": 20},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-B",
                    sequence_id="seq-1",
                    action_type="input",
                    target=None,
                    parameters={"text": "hello", "submit": True},
                    status="pending",
                    error_message=None,
                ),
            ],
            created_at=datetime(2024, 6, 15),
        )

        await controller.execute_sequence(sequence)

        assert step_ids_received == ["step-A", "step-B", None]
