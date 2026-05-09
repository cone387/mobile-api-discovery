"""Traffic Interceptor 模块测试

测试 TrafficInterceptor 类的核心功能：
- start_recording / stop_recording 状态管理
- get_captured_requests() 从 JSON 文件读取并过滤
- get_stats() 统计信息
- 4 层过滤逻辑
- 用户自定义域名白名单/黑名单
- 时间范围过滤
"""

import json
import os
import tempfile
from datetime import datetime, timedelta

import pytest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from src.traffic_interceptor import TrafficInterceptor
from src.models import CapturedRequest, FilterRules


def _write_request_json(storage_path: str, request_data: dict) -> str:
    """写入一个请求 JSON 文件到存储目录。

    Args:
        storage_path: 存储目录路径
        request_data: 请求数据字典

    Returns:
        写入的文件路径
    """
    filepath = os.path.join(storage_path, f"{request_data['id']}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(request_data, f, ensure_ascii=False, indent=2)
    return filepath


def _make_request_data(
    request_id: str = "test-001",
    url: str = "https://api.example.com/v1/users",
    method: str = "GET",
    response_content_type: str = "application/json",
    response_body: str = '{"users": []}',
    timestamp: str = None,
    is_decrypted: bool = True,
) -> dict:
    """创建请求数据字典。"""
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    return {
        "id": request_id,
        "timestamp": timestamp,
        "method": method,
        "url": url,
        "headers": {"User-Agent": "TestApp/1.0"},
        "body": None,
        "response_status": 200,
        "response_headers": {"Content-Type": response_content_type},
        "response_body": response_body,
        "is_decrypted": is_decrypted,
    }


class TestTrafficInterceptorState:
    """测试 TrafficInterceptor 状态管理"""

    def test_initial_state(self):
        """初始状态应为未录制"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        assert interceptor.is_recording is False

    def test_start_recording(self):
        """start_recording 应将状态设为录制中"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        interceptor.start_recording()
        assert interceptor.is_recording is True

    def test_stop_recording(self):
        """stop_recording 应将状态设为未录制"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        interceptor.start_recording()
        interceptor.stop_recording()
        assert interceptor.is_recording is False

    def test_start_recording_already_recording(self):
        """已在录制时再次 start_recording 应抛出 RuntimeError"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        interceptor.start_recording()
        with pytest.raises(RuntimeError, match="Already recording"):
            interceptor.start_recording()

    def test_stop_recording_not_recording(self):
        """未在录制时 stop_recording 应抛出 RuntimeError"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        with pytest.raises(RuntimeError, match="Not recording"):
            interceptor.stop_recording()

    def test_filter_rules_property(self):
        """filter_rules 属性应可读写"""
        tmpdir = tempfile.mkdtemp()
        rules = FilterRules(domain_blacklist=["bad.com"])
        interceptor = TrafficInterceptor(storage_path=tmpdir, filter_rules=rules)
        assert interceptor.filter_rules.domain_blacklist == ["bad.com"]

        new_rules = FilterRules(domain_blacklist=["worse.com"])
        interceptor.filter_rules = new_rules
        assert interceptor.filter_rules.domain_blacklist == ["worse.com"]


class TestGetCapturedRequests:
    """测试 get_captured_requests() 方法"""

    def test_empty_directory(self):
        """空目录应返回空列表"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert result == []

    def test_nonexistent_directory(self):
        """不存在的目录应返回空列表"""
        interceptor = TrafficInterceptor(storage_path="/nonexistent/path")
        result = interceptor.get_captured_requests()
        assert result == []

    def test_reads_json_files(self):
        """应正确读取 JSON 文件并转换为 CapturedRequest"""
        tmpdir = tempfile.mkdtemp()
        data = _make_request_data(
            request_id="req-001",
            url="https://api.example.com/v1/users",
            response_content_type="application/json",
        )
        _write_request_json(tmpdir, data)

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()

        assert len(result) == 1
        assert isinstance(result[0], CapturedRequest)
        assert result[0].id == "req-001"
        assert result[0].method == "GET"
        assert result[0].url == "https://api.example.com/v1/users"

    def test_skips_invalid_json(self):
        """无效 JSON 文件应被跳过"""
        tmpdir = tempfile.mkdtemp()
        # 写入有效文件
        data = _make_request_data(request_id="valid-001")
        _write_request_json(tmpdir, data)
        # 写入无效文件
        with open(os.path.join(tmpdir, "invalid.json"), "w") as f:
            f.write("not valid json{{{")

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "valid-001"

    def test_skips_non_json_files(self):
        """非 .json 文件应被跳过"""
        tmpdir = tempfile.mkdtemp()
        data = _make_request_data(request_id="req-001")
        _write_request_json(tmpdir, data)
        # 写入非 JSON 文件
        with open(os.path.join(tmpdir, "readme.txt"), "w") as f:
            f.write("not a json file")

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 1

    def test_sorted_by_timestamp(self):
        """结果应按时间戳排序"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="req-002",
            timestamp="2024-01-15T10:30:00",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="req-001",
            timestamp="2024-01-15T10:00:00",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="req-003",
            timestamp="2024-01-15T11:00:00",
        ))

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert [r.id for r in result] == ["req-001", "req-002", "req-003"]


class TestFourLayerFiltering:
    """测试 4 层过滤逻辑"""

    def test_static_resource_filtered(self):
        """静态资源（image/、font/ 等）应被过滤"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="img-001",
            url="https://cdn.example.com/api/image.png",
            response_content_type="image/png",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="api-001",
            url="https://api.example.com/v1/users",
            response_content_type="application/json",
        ))

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "api-001"

    def test_css_and_js_filtered(self):
        """text/css 和 application/javascript 应被过滤"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="css-001",
            url="https://cdn.example.com/api/style.css",
            response_content_type="text/css",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="js-001",
            url="https://cdn.example.com/api/app.js",
            response_content_type="application/javascript",
        ))

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 0

    def test_domain_blacklist_filtered(self):
        """域名黑名单中的请求应被过滤"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="sdk-001",
            url="https://analytics.oceanengine.com/api/report",
            response_content_type="application/json",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="api-001",
            url="https://api.myapp.com/v1/data",
            response_content_type="application/json",
        ))

        rules = FilterRules(
            domain_blacklist=["analytics.oceanengine.com"],
        )
        interceptor = TrafficInterceptor(storage_path=tmpdir, filter_rules=rules)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "api-001"

    def test_path_blacklist_filtered(self):
        """路径黑名单中的请求应被过滤"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="sdk-001",
            url="https://api.example.com/sdk/app/init",
            response_content_type="application/json",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="api-001",
            url="https://api.example.com/v1/users",
            response_content_type="application/json",
        ))

        rules = FilterRules(
            path_blacklist=["/sdk/app/"],
        )
        interceptor = TrafficInterceptor(storage_path=tmpdir, filter_rules=rules)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "api-001"

    def test_api_whitelist_json_content_type(self):
        """Content-Type 含 json 的请求应通过 API 白名单"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="json-001",
            url="https://api.example.com/custom/endpoint",
            response_content_type="application/json",
        ))

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "json-001"

    def test_api_whitelist_path_pattern(self):
        """路径匹配 API 模式的请求应通过 API 白名单"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="api-001",
            url="https://api.example.com/api/users",
            response_content_type="text/plain",
        ))

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "api-001"

    def test_non_api_non_json_filtered(self):
        """既不是 JSON 也不匹配 API 路径模式的请求应被过滤"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="html-001",
            url="https://www.example.com/page/about",
            response_content_type="text/html",
        ))

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 0


class TestUserDomainFilters:
    """测试用户自定义域名白名单/黑名单"""

    def test_user_domain_whitelist(self):
        """设置用户域名白名单后，只保留白名单中的域名"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="allowed-001",
            url="https://api.myapp.com/v1/data",
            response_content_type="application/json",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="blocked-001",
            url="https://api.other.com/v1/data",
            response_content_type="application/json",
        ))

        rules = FilterRules(user_domain_whitelist=["api.myapp.com"])
        interceptor = TrafficInterceptor(storage_path=tmpdir, filter_rules=rules)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "allowed-001"

    def test_user_domain_blacklist(self):
        """设置用户域名黑名单后，排除黑名单中的域名"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="allowed-001",
            url="https://api.myapp.com/v1/data",
            response_content_type="application/json",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="blocked-001",
            url="https://api.blocked.com/v1/data",
            response_content_type="application/json",
        ))

        rules = FilterRules(user_domain_blacklist=["api.blocked.com"])
        interceptor = TrafficInterceptor(storage_path=tmpdir, filter_rules=rules)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "allowed-001"

    def test_user_domain_whitelist_subdomain(self):
        """用户域名白名单应支持子域名匹配"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="sub-001",
            url="https://sub.myapp.com/v1/data",
            response_content_type="application/json",
        ))

        rules = FilterRules(user_domain_whitelist=["myapp.com"])
        interceptor = TrafficInterceptor(storage_path=tmpdir, filter_rules=rules)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].id == "sub-001"


class TestGetStats:
    """测试 get_stats() 方法"""

    def test_empty_stats(self):
        """空目录的统计信息"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        stats = interceptor.get_stats()
        assert stats["total_files"] == 0
        assert stats["total_filtered"] == 0
        assert stats["is_recording"] is False
        assert stats["start_time"] is None
        assert stats["stop_time"] is None

    def test_stats_with_data(self):
        """有数据时的统计信息"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="api-001",
            url="https://api.example.com/v1/users",
            response_content_type="application/json",
        ))
        _write_request_json(tmpdir, _make_request_data(
            request_id="img-001",
            url="https://cdn.example.com/image.png",
            response_content_type="image/png",
        ))

        interceptor = TrafficInterceptor(storage_path=tmpdir)
        stats = interceptor.get_stats()
        assert stats["total_files"] == 2
        assert stats["total_filtered"] == 1

    def test_stats_recording_state(self):
        """录制状态应反映在统计信息中"""
        tmpdir = tempfile.mkdtemp()
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        interceptor.start_recording()
        stats = interceptor.get_stats()
        assert stats["is_recording"] is True
        assert stats["start_time"] is not None


class TestHTTPSDecryptionFailure:
    """测试 HTTPS 解密失败标记"""

    def test_undecrypted_request_preserved(self):
        """is_decrypted=False 的请求应被保留（通过 API 白名单路径匹配）"""
        tmpdir = tempfile.mkdtemp()
        _write_request_json(tmpdir, _make_request_data(
            request_id="tls-fail-001",
            url="https://secure.example.com/api/data",
            method="CONNECT",
            response_content_type="",
            response_body=None,
            is_decrypted=False,
        ))

        # 使用空过滤规则（允许所有通过白名单的）
        # 注意：CONNECT 请求的 URL 含 /api/ 所以会通过路径白名单
        interceptor = TrafficInterceptor(storage_path=tmpdir)
        result = interceptor.get_captured_requests()
        assert len(result) == 1
        assert result[0].is_decrypted is False
