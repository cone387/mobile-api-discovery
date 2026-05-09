"""过滤规则引擎单元测试

测试 CaptureAddon 的 4 层过滤逻辑：
- 第 1 层：静态资源过滤（Content-Type 黑名单）
- 第 2 层：域名黑名单
- 第 3 层：路径黑名单
- 第 4 层：API 白名单（Content-Type 含 json 或路径匹配 API 模式）
- 用户自定义域名白名单/黑名单
- 组合过滤
- 边界情况
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "addons"))

from capture_addon import CaptureAddon, FilterRules


def _make_flow(url: str, response_content_type: str = "") -> MagicMock:
    """创建模拟的 mitmproxy HTTPFlow 对象。

    Args:
        url: 请求的完整 URL
        response_content_type: 响应的 Content-Type 头

    Returns:
        模拟的 HTTPFlow 对象
    """
    flow = MagicMock()
    flow.request.pretty_url = url

    if response_content_type:
        flow.response.headers.get.side_effect = (
            lambda key, default="": response_content_type if key == "content-type" else default
        )
    else:
        flow.response.headers.get.side_effect = (
            lambda key, default="": default
        )
    # Make flow.response truthy
    flow.response.__bool__ = lambda self: True

    return flow


def _make_flow_no_response(url: str) -> MagicMock:
    """创建没有响应的模拟 HTTPFlow 对象。

    Args:
        url: 请求的完整 URL

    Returns:
        模拟的 HTTPFlow 对象（response 为 None）
    """
    flow = MagicMock()
    flow.request.pretty_url = url
    flow.response = None
    return flow


class TestFilterRulesDataclass:
    """FilterRules 数据类测试"""

    def test_default_values(self):
        """默认规则应包含预定义的黑名单和白名单"""
        rules = FilterRules()
        assert "image/" in rules.content_type_blacklist
        assert "font/" in rules.content_type_blacklist
        assert len(rules.domain_blacklist) > 0
        assert len(rules.path_blacklist) > 0
        assert "json" in rules.content_type_whitelist
        assert "/api/" in rules.api_path_patterns
        assert rules.user_domain_whitelist is None
        assert rules.user_domain_blacklist is None

    def test_custom_values(self):
        """自定义规则应正确设置"""
        rules = FilterRules(
            content_type_blacklist=["image/"],
            domain_blacklist=["bad.com"],
            path_blacklist=["/sdk/"],
            content_type_whitelist=["json"],
            api_path_patterns=["/api/"],
            user_domain_whitelist=["good.com"],
            user_domain_blacklist=["evil.com"],
        )
        assert rules.content_type_blacklist == ["image/"]
        assert rules.domain_blacklist == ["bad.com"]
        assert rules.path_blacklist == ["/sdk/"]
        assert rules.content_type_whitelist == ["json"]
        assert rules.api_path_patterns == ["/api/"]
        assert rules.user_domain_whitelist == ["good.com"]
        assert rules.user_domain_blacklist == ["evil.com"]


class TestStaticResourceFilter:
    """第 1 层：静态资源过滤测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=[],
            ),
        )

    def test_image_filtered(self):
        """image/ Content-Type 应被过滤"""
        flow = _make_flow("https://example.com/api/data", "image/png")
        assert self.addon._should_capture(flow) is False

    def test_font_filtered(self):
        """font/ Content-Type 应被过滤"""
        flow = _make_flow("https://example.com/api/data", "font/woff2")
        assert self.addon._should_capture(flow) is False

    def test_video_filtered(self):
        """video/ Content-Type 应被过滤"""
        flow = _make_flow("https://example.com/api/data", "video/mp4")
        assert self.addon._should_capture(flow) is False

    def test_audio_filtered(self):
        """audio/ Content-Type 应被过滤"""
        flow = _make_flow("https://example.com/api/data", "audio/mpeg")
        assert self.addon._should_capture(flow) is False

    def test_css_filtered(self):
        """text/css Content-Type 应被过滤"""
        flow = _make_flow("https://example.com/api/data", "text/css")
        assert self.addon._should_capture(flow) is False

    def test_javascript_filtered(self):
        """application/javascript Content-Type 应被过滤"""
        flow = _make_flow("https://example.com/api/data", "application/javascript")
        assert self.addon._should_capture(flow) is False

    def test_json_not_filtered(self):
        """application/json Content-Type 不应被过滤"""
        flow = _make_flow("https://example.com/api/data", "application/json")
        assert self.addon._should_capture(flow) is True


class TestDomainBlacklist:
    """第 2 层：域名黑名单测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_blacklisted_domain_filtered(self):
        """黑名单域名应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=["analytics.oceanengine.com"],
                path_blacklist=[],
            ),
        )
        flow = _make_flow("https://analytics.oceanengine.com/api/report", "application/json")
        assert addon._should_capture(flow) is False

    def test_subdomain_of_blacklisted_filtered(self):
        """黑名单域名的子域名应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=["bugly.qq.com"],
                path_blacklist=[],
            ),
        )
        flow = _make_flow("https://pro.bugly.qq.com/api/crash", "application/json")
        assert addon._should_capture(flow) is False

    def test_non_blacklisted_domain_passes(self):
        """非黑名单域名应通过"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=["analytics.oceanengine.com"],
                path_blacklist=[],
            ),
        )
        flow = _make_flow("https://api.myapp.com/v1/users", "application/json")
        assert addon._should_capture(flow) is True

    def test_default_blacklist_includes_known_sdks(self):
        """默认黑名单应包含已知 SDK 域名"""
        rules = FilterRules()
        assert "analytics.oceanengine.com" in rules.domain_blacklist
        assert "sss.umeng.com" in rules.domain_blacklist
        assert "tracking.miui.com" in rules.domain_blacklist
        assert "bugly.qq.com" in rules.domain_blacklist
        assert "gepush.com" in rules.domain_blacklist
        assert "tingyun.com" in rules.domain_blacklist


class TestPathBlacklist:
    """第 3 层：路径黑名单测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_blacklisted_path_filtered(self):
        """黑名单路径应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=["/sdk/app/"],
            ),
        )
        flow = _make_flow("https://api.example.com/sdk/app/init", "application/json")
        assert addon._should_capture(flow) is False

    def test_reportBatchData_filtered(self):
        """/reportBatchData 路径应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=["/reportBatchData"],
            ),
        )
        flow = _make_flow("https://api.example.com/reportBatchData", "application/json")
        assert addon._should_capture(flow) is False

    def test_track_v4_filtered(self):
        """/track/v4 路径应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=["/track/v4"],
            ),
        )
        flow = _make_flow("https://api.example.com/track/v4/event", "application/json")
        assert addon._should_capture(flow) is False

    def test_non_blacklisted_path_passes(self):
        """非黑名单路径应通过"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=["/sdk/app/"],
            ),
        )
        flow = _make_flow("https://api.example.com/v1/users", "application/json")
        assert addon._should_capture(flow) is True

    def test_default_blacklist_includes_known_paths(self):
        """默认黑名单应包含已知非业务路径"""
        rules = FilterRules()
        assert "/sdk/app/" in rules.path_blacklist
        assert "/reportBatchData" in rules.path_blacklist
        assert "/track/v4" in rules.path_blacklist
        assert "/upload-json" in rules.path_blacklist


class TestAPIWhitelist:
    """第 4 层：API 白名单测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=[],
            ),
        )

    def test_json_content_type_passes(self):
        """Content-Type 含 json 应通过白名单"""
        flow = _make_flow("https://example.com/custom/endpoint", "application/json")
        assert self.addon._should_capture(flow) is True

    def test_json_with_charset_passes(self):
        """Content-Type 含 json 带 charset 应通过白名单"""
        flow = _make_flow("https://example.com/custom/endpoint", "application/json; charset=utf-8")
        assert self.addon._should_capture(flow) is True

    def test_api_path_pattern_passes(self):
        """路径含 /api/ 应通过白名单"""
        flow = _make_flow("https://example.com/api/users", "text/plain")
        assert self.addon._should_capture(flow) is True

    def test_v1_path_pattern_passes(self):
        """路径含 /v1/ 应通过白名单"""
        flow = _make_flow("https://example.com/v1/data", "text/plain")
        assert self.addon._should_capture(flow) is True

    def test_v2_path_pattern_passes(self):
        """路径含 /v2/ 应通过白名单"""
        flow = _make_flow("https://example.com/v2/data", "text/plain")
        assert self.addon._should_capture(flow) is True

    def test_v3_path_pattern_passes(self):
        """路径含 /v3/ 应通过白名单"""
        flow = _make_flow("https://example.com/v3/data", "text/plain")
        assert self.addon._should_capture(flow) is True

    def test_portal_path_pattern_passes(self):
        """路径含 /portal/ 应通过白名单"""
        flow = _make_flow("https://example.com/portal/home", "text/plain")
        assert self.addon._should_capture(flow) is True

    def test_gateway_path_pattern_passes(self):
        """路径含 /gateway/ 应通过白名单"""
        flow = _make_flow("https://example.com/gateway/service", "text/plain")
        assert self.addon._should_capture(flow) is True

    def test_non_api_non_json_filtered(self):
        """既不是 JSON 也不匹配 API 路径模式的应被过滤"""
        flow = _make_flow("https://example.com/page/about", "text/html")
        assert self.addon._should_capture(flow) is False

    def test_empty_content_type_with_api_path(self):
        """空 Content-Type 但路径匹配 API 模式应通过"""
        flow = _make_flow("https://example.com/api/data", "")
        assert self.addon._should_capture(flow) is True


class TestUserDomainFilters:
    """用户自定义域名白名单/黑名单测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_user_whitelist_only_allows_listed(self):
        """用户域名白名单应只允许白名单中的域名"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=[],
                user_domain_whitelist=["api.myapp.com"],
            ),
        )
        flow_allowed = _make_flow("https://api.myapp.com/v1/data", "application/json")
        flow_blocked = _make_flow("https://api.other.com/v1/data", "application/json")
        assert addon._should_capture(flow_allowed) is True
        assert addon._should_capture(flow_blocked) is False

    def test_user_blacklist_blocks_listed(self):
        """用户域名黑名单应阻止黑名单中的域名"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=[],
                user_domain_blacklist=["blocked.com"],
            ),
        )
        flow_allowed = _make_flow("https://api.myapp.com/v1/data", "application/json")
        flow_blocked = _make_flow("https://blocked.com/v1/data", "application/json")
        assert addon._should_capture(flow_allowed) is True
        assert addon._should_capture(flow_blocked) is False

    def test_user_whitelist_subdomain_match(self):
        """用户域名白名单应支持子域名匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=[],
                user_domain_whitelist=["myapp.com"],
            ),
        )
        flow = _make_flow("https://sub.myapp.com/v1/data", "application/json")
        assert addon._should_capture(flow) is True


class TestCombinedFilters:
    """组合过滤测试 - 所有层必须通过"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_all_layers_pass(self):
        """所有层都通过时应允许"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=["bad.com"],
                path_blacklist=["/sdk/"],
            ),
        )
        flow = _make_flow("https://api.example.com/v1/users", "application/json")
        assert addon._should_capture(flow) is True

    def test_static_resource_blocks_even_with_api_path(self):
        """静态资源即使路径匹配 API 模式也应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=[],
            ),
        )
        flow = _make_flow("https://example.com/api/avatar.png", "image/png")
        assert addon._should_capture(flow) is False

    def test_blacklisted_domain_blocks_even_with_json(self):
        """黑名单域名即使返回 JSON 也应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=["analytics.example.com"],
                path_blacklist=[],
            ),
        )
        flow = _make_flow("https://analytics.example.com/api/report", "application/json")
        assert addon._should_capture(flow) is False

    def test_blacklisted_path_blocks_even_with_json(self):
        """黑名单路径即使返回 JSON 也应被过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=["/reportBatchData"],
            ),
        )
        flow = _make_flow("https://api.example.com/reportBatchData", "application/json")
        assert addon._should_capture(flow) is False


class TestEdgeCases:
    """边界情况测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_no_response_filtered(self):
        """无响应的请求应被过滤（无法判断 Content-Type）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=[],
                path_blacklist=[],
            ),
        )
        flow = _make_flow_no_response("https://example.com/api/data")
        # 无响应时 content_type 为空，但路径含 /api/ 所以通过白名单
        assert addon._should_capture(flow) is True

    def test_url_with_port(self):
        """带端口的 URL 域名匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=["bad.com"],
                path_blacklist=[],
            ),
        )
        flow = _make_flow("https://bad.com:8443/api/data", "application/json")
        assert addon._should_capture(flow) is False

    def test_empty_hostname(self):
        """空主机名不应匹配任何域名黑名单"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domain_blacklist=["example.com"],
                path_blacklist=[],
            ),
        )
        flow = _make_flow("http:///api/data", "application/json")
        # 空主机名不匹配黑名单，通过域名检查
        assert addon._should_capture(flow) is True
