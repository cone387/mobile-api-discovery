"""Traffic Interceptor 模块测试

测试 TrafficInterceptor 类的核心功能：
- ProxyConfig 数据类
- 字典到 CapturedRequest 的转换
- 过滤规则设置
- 步骤 ID 管理
- 回调注册
- 启动/停止状态管理
"""

import asyncio
import base64
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "addons"))

from src.traffic_interceptor import ProxyConfig, TrafficInterceptor
from src.models import CapturedRequest
from capture_addon import FilterRules


class TestProxyConfig:
    """ProxyConfig 数据类测试"""

    def test_default_values(self):
        """默认配置值应正确"""
        config = ProxyConfig()
        assert config.listen_host == "0.0.0.0"
        assert config.listen_port == 8080
        assert config.storage_path == "./output/captures"

    def test_custom_values(self):
        """自定义配置值应正确"""
        config = ProxyConfig(
            listen_host="127.0.0.1",
            listen_port=9090,
            storage_path="/tmp/captures",
        )
        assert config.listen_host == "127.0.0.1"
        assert config.listen_port == 9090
        assert config.storage_path == "/tmp/captures"


class TestDictToCapturedRequest:
    """测试字典到 CapturedRequest 的转换"""

    def test_basic_conversion(self):
        """基本字典应正确转换为 CapturedRequest"""
        data = {
            "id": "test-id-001",
            "timestamp": "2024-01-15T10:30:00",
            "operation_step_id": "step-001",
            "method": "GET",
            "url": "https://api.example.com/users",
            "headers": {"Authorization": "Bearer token123"},
            "body": None,
            "response_status": 200,
            "response_headers": {"Content-Type": "application/json"},
            "response_body": base64.b64encode(b'{"users": []}').decode("ascii"),
            "is_decrypted": True,
        }

        result = TrafficInterceptor._dict_to_captured_request(data)

        assert isinstance(result, CapturedRequest)
        assert result.id == "test-id-001"
        assert result.timestamp == datetime(2024, 1, 15, 10, 30, 0)
        assert result.operation_step_id == "step-001"
        assert result.method == "GET"
        assert result.url == "https://api.example.com/users"
        assert result.headers == {"Authorization": "Bearer token123"}
        assert result.body is None
        assert result.response_status == 200
        assert result.response_body == b'{"users": []}'
        assert result.is_decrypted is True

    def test_conversion_with_body(self):
        """带请求体的字典应正确转换"""
        body_content = b'{"name": "test"}'
        data = {
            "id": "test-id-002",
            "timestamp": "2024-01-15T10:30:00",
            "operation_step_id": "step-002",
            "method": "POST",
            "url": "https://api.example.com/users",
            "headers": {"Content-Type": "application/json"},
            "body": base64.b64encode(body_content).decode("ascii"),
            "response_status": 201,
            "response_headers": {},
            "response_body": None,
            "is_decrypted": True,
        }

        result = TrafficInterceptor._dict_to_captured_request(data)

        assert result.body == body_content
        assert result.response_body is None

    def test_conversion_tls_failure(self):
        """TLS 失败记录应正确转换"""
        data = {
            "id": "tls-fail-001",
            "timestamp": "2024-01-15T10:30:00",
            "operation_step_id": "",
            "method": "CONNECT",
            "url": "https://unknown-host.com/",
            "headers": {},
            "body": None,
            "response_status": 0,
            "response_headers": {},
            "response_body": None,
            "is_decrypted": False,
        }

        result = TrafficInterceptor._dict_to_captured_request(data)

        assert result.is_decrypted is False
        assert result.method == "CONNECT"
        assert result.response_status == 0

    def test_conversion_missing_optional_fields(self):
        """缺少可选字段时应使用默认值"""
        data = {
            "id": "test-id-003",
            "timestamp": "2024-01-15T10:30:00",
            "method": "GET",
            "url": "https://api.example.com/test",
        }

        result = TrafficInterceptor._dict_to_captured_request(data)

        assert result.operation_step_id == ""
        assert result.headers == {}
        assert result.body is None
        assert result.response_status == 0
        assert result.response_headers == {}
        assert result.response_body is None
        assert result.is_decrypted is True


class TestTrafficInterceptorState:
    """测试 TrafficInterceptor 状态管理"""

    def test_initial_state(self):
        """初始状态应为未运行"""
        interceptor = TrafficInterceptor()
        assert interceptor.is_running is False
        assert interceptor.addon is None

    def test_set_step_id_when_not_running(self):
        """未运行时设置步骤 ID 不应报错（addon 为 None 时静默忽略）"""
        interceptor = TrafficInterceptor()
        # 不应抛出异常
        interceptor.set_step_id("step-001")

    def test_on_request_captured_registers_callback(self):
        """回调注册应正确保存"""
        interceptor = TrafficInterceptor()
        callback = MagicMock()
        interceptor.on_request_captured(callback)
        assert callback in interceptor._callbacks

    def test_multiple_callbacks(self):
        """应支持注册多个回调"""
        interceptor = TrafficInterceptor()
        cb1 = MagicMock()
        cb2 = MagicMock()
        interceptor.on_request_captured(cb1)
        interceptor.on_request_captured(cb2)
        assert len(interceptor._callbacks) == 2


class TestTrafficInterceptorWithMockAddon:
    """使用 mock addon 测试 TrafficInterceptor 的方法"""

    def setup_method(self):
        """为每个测试创建带 mock addon 的 interceptor"""
        self.interceptor = TrafficInterceptor()
        self.interceptor._addon = MagicMock()
        self.interceptor._running = True

    @pytest.mark.asyncio
    async def test_set_filter(self):
        """set_filter 应更新 addon 的过滤规则"""
        rules = FilterRules(domains=["api.example.com"])
        await self.interceptor.set_filter(rules)
        assert self.interceptor._addon.filter_rules == rules

    @pytest.mark.asyncio
    async def test_set_filter_not_running(self):
        """未运行时 set_filter 应抛出 RuntimeError"""
        interceptor = TrafficInterceptor()
        rules = FilterRules(domains=["api.example.com"])
        with pytest.raises(RuntimeError, match="not running"):
            await interceptor.set_filter(rules)

    def test_set_step_id_delegates_to_addon(self):
        """set_step_id 应委托给 addon"""
        self.interceptor.set_step_id("step-123")
        self.interceptor._addon.set_step_id.assert_called_once_with("step-123")

    def test_set_step_id_none(self):
        """set_step_id(None) 应委托给 addon"""
        self.interceptor.set_step_id(None)
        self.interceptor._addon.set_step_id.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_get_captured_requests(self):
        """get_captured_requests 应转换 addon 返回的字典列表"""
        self.interceptor._addon.get_captured_requests.return_value = [
            {
                "id": "req-001",
                "timestamp": "2024-01-15T10:30:00",
                "operation_step_id": "step-001",
                "method": "GET",
                "url": "https://api.example.com/data",
                "headers": {},
                "body": None,
                "response_status": 200,
                "response_headers": {},
                "response_body": None,
                "is_decrypted": True,
            }
        ]

        results = await self.interceptor.get_captured_requests()

        assert len(results) == 1
        assert isinstance(results[0], CapturedRequest)
        assert results[0].id == "req-001"
        assert results[0].method == "GET"

    @pytest.mark.asyncio
    async def test_get_captured_requests_empty(self):
        """无捕获请求时应返回空列表"""
        self.interceptor._addon.get_captured_requests.return_value = []
        results = await self.interceptor.get_captured_requests()
        assert results == []

    @pytest.mark.asyncio
    async def test_get_captured_requests_not_running(self):
        """未运行时 get_captured_requests 应抛出 RuntimeError"""
        interceptor = TrafficInterceptor()
        with pytest.raises(RuntimeError, match="not running"):
            await interceptor.get_captured_requests()

    @pytest.mark.asyncio
    async def test_clear(self):
        """clear 应调用 addon 的 clear 方法"""
        await self.interceptor.clear()
        self.interceptor._addon.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_not_running(self):
        """未运行时 clear 应抛出 RuntimeError"""
        interceptor = TrafficInterceptor()
        with pytest.raises(RuntimeError, match="not running"):
            await interceptor.clear()

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """已运行时再次 start 应抛出 RuntimeError"""
        config = ProxyConfig()
        with pytest.raises(RuntimeError, match="already running"):
            await self.interceptor.start(config)

    @pytest.mark.asyncio
    async def test_stop_not_running(self):
        """未运行时 stop 应抛出 RuntimeError"""
        interceptor = TrafficInterceptor()
        with pytest.raises(RuntimeError, match="not running"):
            await interceptor.stop()


class TestCallbackNotification:
    """测试回调通知机制"""

    def test_notify_callbacks(self):
        """_notify_callbacks 应调用所有注册的回调"""
        interceptor = TrafficInterceptor()
        cb1 = MagicMock()
        cb2 = MagicMock()
        interceptor.on_request_captured(cb1)
        interceptor.on_request_captured(cb2)

        request = CapturedRequest(
            id="test-001",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            operation_step_id="step-001",
            method="GET",
            url="https://api.example.com/test",
            headers={},
            body=None,
            response_status=200,
            response_headers={},
            response_body=None,
            is_decrypted=True,
        )

        interceptor._notify_callbacks(request)

        cb1.assert_called_once_with(request)
        cb2.assert_called_once_with(request)

    def test_callback_exception_does_not_propagate(self):
        """回调异常不应影响其他回调"""
        interceptor = TrafficInterceptor()
        cb1 = MagicMock(side_effect=ValueError("callback error"))
        cb2 = MagicMock()
        interceptor.on_request_captured(cb1)
        interceptor.on_request_captured(cb2)

        request = CapturedRequest(
            id="test-001",
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            operation_step_id="step-001",
            method="GET",
            url="https://api.example.com/test",
            headers={},
            body=None,
            response_status=200,
            response_headers={},
            response_body=None,
            is_decrypted=True,
        )

        # 不应抛出异常
        interceptor._notify_callbacks(request)

        # cb2 仍应被调用
        cb2.assert_called_once_with(request)
