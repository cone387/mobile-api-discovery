"""过滤规则引擎单元测试

测试 FilterRules 和 CaptureAddon._matches_filter 的过滤逻辑：
- 空规则（允许所有）
- 域名过滤（精确匹配、子域名匹配、不匹配）
- 多域名过滤
- 路径前缀过滤（匹配、不匹配、部分匹配）
- Content-Type 过滤（精确匹配、部分匹配）
- 组合过滤（所有维度必须通过）
- 边界情况：空 URL、无响应 Content-Type
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

    def test_default_empty_rules(self):
        """默认规则应为空列表"""
        rules = FilterRules()
        assert rules.domains == []
        assert rules.paths == []
        assert rules.content_types == []

    def test_to_dict(self):
        """to_dict 应正确序列化"""
        rules = FilterRules(
            domains=["example.com"],
            paths=["/api/"],
            content_types=["application/json"],
        )
        result = rules.to_dict()
        assert result == {
            "domains": ["example.com"],
            "paths": ["/api/"],
            "content_types": ["application/json"],
        }

    def test_from_dict(self):
        """from_dict 应正确反序列化"""
        data = {
            "domains": ["example.com", "test.com"],
            "paths": ["/api/v1"],
            "content_types": ["json"],
        }
        rules = FilterRules.from_dict(data)
        assert rules.domains == ["example.com", "test.com"]
        assert rules.paths == ["/api/v1"]
        assert rules.content_types == ["json"]

    def test_from_dict_missing_keys(self):
        """from_dict 缺少键时应使用空列表"""
        rules = FilterRules.from_dict({})
        assert rules.domains == []
        assert rules.paths == []
        assert rules.content_types == []


class TestEmptyRules:
    """空规则测试 - 空列表表示允许所有"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(),
        )

    def test_empty_rules_allow_all(self):
        """空规则应允许所有请求"""
        flow = _make_flow("https://any-domain.com/any/path", "text/html")
        assert self.addon._matches_filter(flow) is True

    def test_empty_rules_allow_any_domain(self):
        """空规则应允许任何域名"""
        flow = _make_flow("https://random.example.org/test", "application/json")
        assert self.addon._matches_filter(flow) is True

    def test_empty_rules_allow_any_path(self):
        """空规则应允许任何路径"""
        flow = _make_flow("https://example.com/deeply/nested/path", "text/plain")
        assert self.addon._matches_filter(flow) is True

    def test_empty_rules_allow_any_content_type(self):
        """空规则应允许任何 Content-Type"""
        flow = _make_flow("https://example.com/data", "image/png")
        assert self.addon._matches_filter(flow) is True


class TestDomainFilter:
    """域名过滤测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_exact_domain_match(self):
        """精确域名匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow("https://example.com/api/users", "application/json")
        assert addon._matches_filter(flow) is True

    def test_subdomain_match(self):
        """子域名匹配 - api.example.com 应匹配 example.com"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow("https://api.example.com/data", "application/json")
        assert addon._matches_filter(flow) is True

    def test_deep_subdomain_match(self):
        """深层子域名匹配 - v2.api.example.com 应匹配 example.com"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow("https://v2.api.example.com/data", "application/json")
        assert addon._matches_filter(flow) is True

    def test_domain_non_match(self):
        """域名不匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow("https://other-site.org/api/users", "application/json")
        assert addon._matches_filter(flow) is False

    def test_domain_partial_name_no_match(self):
        """域名部分名称不应匹配 - notexample.com 不应匹配 example.com"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow("https://notexample.com/api", "application/json")
        assert addon._matches_filter(flow) is False

    def test_multiple_domains_first_match(self):
        """多域名过滤 - 匹配第一个域名"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com", "test.io"]),
        )
        flow = _make_flow("https://example.com/api", "application/json")
        assert addon._matches_filter(flow) is True

    def test_multiple_domains_second_match(self):
        """多域名过滤 - 匹配第二个域名"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com", "test.io"]),
        )
        flow = _make_flow("https://api.test.io/data", "application/json")
        assert addon._matches_filter(flow) is True

    def test_multiple_domains_none_match(self):
        """多域名过滤 - 都不匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com", "test.io"]),
        )
        flow = _make_flow("https://other.org/api", "application/json")
        assert addon._matches_filter(flow) is False


class TestPathFilter:
    """路径前缀过滤测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_path_prefix_match(self):
        """路径前缀匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/api/"]),
        )
        flow = _make_flow("https://example.com/api/users", "application/json")
        assert addon._matches_filter(flow) is True

    def test_path_prefix_exact_match(self):
        """路径前缀精确匹配（路径等于前缀）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/api/v1"]),
        )
        flow = _make_flow("https://example.com/api/v1", "application/json")
        assert addon._matches_filter(flow) is True

    def test_path_prefix_non_match(self):
        """路径前缀不匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/api/"]),
        )
        flow = _make_flow("https://example.com/web/page", "text/html")
        assert addon._matches_filter(flow) is False

    def test_path_prefix_partial_segment_match(self):
        """路径前缀部分段匹配 - /api 应匹配 /api/users 和 /api-v2"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/api"]),
        )
        # /api-v2 starts with /api so it matches (prefix-based, not segment-based)
        flow = _make_flow("https://example.com/api-v2/data", "application/json")
        assert addon._matches_filter(flow) is True

    def test_multiple_path_prefixes(self):
        """多路径前缀 - 匹配任一即可"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/api/", "/v2/"]),
        )
        flow = _make_flow("https://example.com/v2/users", "application/json")
        assert addon._matches_filter(flow) is True

    def test_root_path_prefix(self):
        """根路径前缀 / 应匹配所有路径"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/"]),
        )
        flow = _make_flow("https://example.com/anything/here", "text/html")
        assert addon._matches_filter(flow) is True


class TestContentTypeFilter:
    """Content-Type 过滤测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_content_type_exact_match(self):
        """Content-Type 精确匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["application/json"]),
        )
        flow = _make_flow("https://example.com/api", "application/json")
        assert addon._matches_filter(flow) is True

    def test_content_type_partial_match(self):
        """Content-Type 部分匹配 - 'json' in 'application/json'"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["json"]),
        )
        flow = _make_flow("https://example.com/api", "application/json")
        assert addon._matches_filter(flow) is True

    def test_content_type_with_charset(self):
        """Content-Type 带 charset 参数时也应匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["application/json"]),
        )
        flow = _make_flow("https://example.com/api", "application/json; charset=utf-8")
        assert addon._matches_filter(flow) is True

    def test_content_type_non_match(self):
        """Content-Type 不匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["application/json"]),
        )
        flow = _make_flow("https://example.com/image", "image/png")
        assert addon._matches_filter(flow) is False

    def test_multiple_content_types(self):
        """多 Content-Type 过滤 - 匹配任一即可"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["json", "xml"]),
        )
        flow = _make_flow("https://example.com/api", "application/xml")
        assert addon._matches_filter(flow) is True

    def test_content_type_no_response(self):
        """无响应时 Content-Type 过滤应不通过"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["application/json"]),
        )
        flow = _make_flow_no_response("https://example.com/api")
        assert addon._matches_filter(flow) is False

    def test_content_type_empty_response_header(self):
        """响应无 Content-Type 头时过滤应不通过"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["application/json"]),
        )
        flow = _make_flow("https://example.com/api", "")
        assert addon._matches_filter(flow) is False


class TestCombinedFilters:
    """组合过滤测试 - 所有维度必须通过（AND 逻辑）"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_all_dimensions_pass(self):
        """所有维度都通过时应允许"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domains=["example.com"],
                paths=["/api/"],
                content_types=["json"],
            ),
        )
        flow = _make_flow("https://api.example.com/api/users", "application/json")
        assert addon._matches_filter(flow) is True

    def test_domain_fails_others_pass(self):
        """域名不通过时应拒绝（即使路径和 Content-Type 通过）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domains=["example.com"],
                paths=["/api/"],
                content_types=["json"],
            ),
        )
        flow = _make_flow("https://other.org/api/users", "application/json")
        assert addon._matches_filter(flow) is False

    def test_path_fails_others_pass(self):
        """路径不通过时应拒绝（即使域名和 Content-Type 通过）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domains=["example.com"],
                paths=["/api/"],
                content_types=["json"],
            ),
        )
        flow = _make_flow("https://example.com/web/page", "application/json")
        assert addon._matches_filter(flow) is False

    def test_content_type_fails_others_pass(self):
        """Content-Type 不通过时应拒绝（即使域名和路径通过）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domains=["example.com"],
                paths=["/api/"],
                content_types=["json"],
            ),
        )
        flow = _make_flow("https://example.com/api/image", "image/png")
        assert addon._matches_filter(flow) is False

    def test_domain_and_path_only(self):
        """仅域名和路径过滤（Content-Type 为空列表允许所有）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(
                domains=["example.com"],
                paths=["/api/"],
            ),
        )
        flow = _make_flow("https://example.com/api/data", "image/png")
        assert addon._matches_filter(flow) is True

    def test_content_type_only(self):
        """仅 Content-Type 过滤（域名和路径为空列表允许所有）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(content_types=["json"]),
        )
        flow = _make_flow("https://any-domain.com/any/path", "application/json")
        assert addon._matches_filter(flow) is True


class TestEdgeCases:
    """边界情况测试"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_empty_url_with_domain_filter(self):
        """空 URL 主机名时域名过滤应不通过"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        # URL without hostname
        flow = _make_flow("http:///path/only", "application/json")
        assert addon._matches_filter(flow) is False

    def test_url_with_port(self):
        """带端口的 URL 域名匹配"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow("https://example.com:8443/api", "application/json")
        assert addon._matches_filter(flow) is True

    def test_http_url(self):
        """HTTP URL 也应正常过滤"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow("http://example.com/api", "application/json")
        assert addon._matches_filter(flow) is True

    def test_url_with_query_params(self):
        """带查询参数的 URL 路径过滤应只看路径部分"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/api/"]),
        )
        flow = _make_flow("https://example.com/api/users?page=1&size=10", "application/json")
        assert addon._matches_filter(flow) is True

    def test_empty_path(self):
        """空路径（根路径）"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(paths=["/api/"]),
        )
        flow = _make_flow("https://example.com", "application/json")
        assert addon._matches_filter(flow) is False

    def test_no_response_with_empty_content_type_filter(self):
        """无响应但 Content-Type 过滤为空时应允许"""
        addon = CaptureAddon(
            storage_path=self.tmpdir,
            filter_rules=FilterRules(domains=["example.com"]),
        )
        flow = _make_flow_no_response("https://example.com/api")
        assert addon._matches_filter(flow) is True
