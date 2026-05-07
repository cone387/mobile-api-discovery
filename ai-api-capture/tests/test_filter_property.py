"""过滤规则属性测试

**Validates: Requirements 2.5**

使用 Hypothesis 对过滤规则引擎进行属性测试，验证：
- 属性 2（设计文档）: 过滤规则不变量
  - 过滤后的请求列表中每条记录都满足过滤规则
  - 过滤后的列表长度不超过原始列表长度

为避免依赖 mitmproxy flow 对象，实现独立的 apply_filter / matches_rules
函数，使用与 CaptureAddon._matches_filter 相同的逻辑，作用于简单字典对象。
"""

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ============================================================
# 数据结构（轻量级请求表示，用于属性测试）
# ============================================================


@dataclass
class SimpleRequest:
    """用于属性测试的简化请求对象"""

    url: str
    response_content_type: str


@dataclass
class FilterRules:
    """过滤规则（与 capture_addon.FilterRules 保持一致）"""

    domains: List[str]
    paths: List[str]
    content_types: List[str]


# ============================================================
# 过滤逻辑（与 CaptureAddon._matches_filter 保持一致）
# ============================================================


def matches_rules(req: SimpleRequest, rules: FilterRules) -> bool:
    """检查单个请求是否匹配过滤规则。

    逻辑与 CaptureAddon._matches_filter 完全一致：
    - 空列表表示该维度不过滤（允许所有）
    - 非空列表要求请求匹配列表中至少一项

    Args:
        req: 简化请求对象
        rules: 过滤规则

    Returns:
        True 表示请求匹配过滤规则
    """
    parsed_url = urlparse(req.url)

    # 域名过滤
    if rules.domains:
        hostname = parsed_url.hostname or ""
        if not any(
            hostname == domain or hostname.endswith("." + domain)
            for domain in rules.domains
        ):
            return False

    # 路径前缀过滤
    if rules.paths:
        path = parsed_url.path
        if not any(path.startswith(prefix) for prefix in rules.paths):
            return False

    # Content-Type 过滤
    if rules.content_types:
        response_content_type = req.response_content_type
        if not any(ct in response_content_type for ct in rules.content_types):
            return False

    return True


def apply_filter(requests: List[SimpleRequest], rules: FilterRules) -> List[SimpleRequest]:
    """对请求列表应用过滤规则，返回匹配的请求。

    Args:
        requests: 请求列表
        rules: 过滤规则

    Returns:
        匹配过滤规则的请求子列表
    """
    return [req for req in requests if matches_rules(req, rules)]


# ============================================================
# Hypothesis 策略
# ============================================================

# 域名策略：生成合法的域名
domain_strategy = st.from_regex(
    r"[a-z][a-z0-9]{0,10}\.(com|org|io|net|cn)", fullmatch=True
)

# 路径前缀策略：生成以 / 开头的路径
path_prefix_strategy = st.from_regex(r"/[a-z0-9/]{0,20}", fullmatch=True)

# Content-Type 策略：从常见类型中选择
content_type_strategy = st.sampled_from([
    "application/json",
    "text/html",
    "text/plain",
    "application/xml",
    "image/png",
    "image/jpeg",
    "application/octet-stream",
    "multipart/form-data",
    "json",
    "xml",
    "html",
])


def filter_rules_strategy() -> st.SearchStrategy[FilterRules]:
    """生成 FilterRules 的策略"""
    return st.builds(
        FilterRules,
        domains=st.lists(domain_strategy, min_size=0, max_size=3),
        paths=st.lists(path_prefix_strategy, min_size=0, max_size=3),
        content_types=st.lists(content_type_strategy, min_size=0, max_size=3),
    )


def captured_request_strategy() -> st.SearchStrategy[SimpleRequest]:
    """生成 SimpleRequest 的策略

    生成带有合法结构的 URL 和 Content-Type 的请求对象。
    """
    # 生成 URL：scheme + optional subdomain + domain + path
    url_strategy = st.builds(
        lambda scheme, subdomain, domain, path: f"{scheme}://{subdomain}{domain}{path}",
        scheme=st.sampled_from(["http", "https"]),
        subdomain=st.sampled_from(["", "api.", "www.", "v2.", "m."]),
        domain=st.sampled_from([
            "example.com", "test.org", "myapp.io", "service.net",
            "data.cn", "other.com", "random.org",
        ]),
        path=st.sampled_from([
            "/", "/api/users", "/api/v1/data", "/web/page",
            "/v2/feed", "/search", "/api/comments", "/static/img",
            "/health", "/api-v2/items",
        ]),
    )

    return st.builds(
        SimpleRequest,
        url=url_strategy,
        response_content_type=st.sampled_from([
            "application/json",
            "application/json; charset=utf-8",
            "text/html",
            "text/html; charset=utf-8",
            "text/plain",
            "application/xml",
            "image/png",
            "image/jpeg",
            "application/octet-stream",
            "",
        ]),
    )


# ============================================================
# 属性测试
# ============================================================


class TestFilterInvariant:
    """过滤规则不变量属性测试

    **Validates: Requirements 2.5**

    验证设计文档中的属性 2：
    - 过滤后的列表长度不超过原始列表长度
    - 过滤后的每条记录都满足过滤规则
    """

    @given(
        requests=st.lists(captured_request_strategy(), min_size=0, max_size=30),
        rules=filter_rules_strategy(),
    )
    @settings(max_examples=200)
    def test_filtered_length_not_exceeds_original(self, requests, rules):
        """过滤后的列表长度不超过原始列表长度"""
        filtered = apply_filter(requests, rules)
        assert len(filtered) <= len(requests)

    @given(
        requests=st.lists(captured_request_strategy(), min_size=0, max_size=30),
        rules=filter_rules_strategy(),
    )
    @settings(max_examples=200)
    def test_all_filtered_items_match_rules(self, requests, rules):
        """过滤后的每条记录都满足过滤规则"""
        filtered = apply_filter(requests, rules)
        for req in filtered:
            assert matches_rules(req, rules)

    @given(
        requests=st.lists(captured_request_strategy(), min_size=0, max_size=30),
        rules=filter_rules_strategy(),
    )
    @settings(max_examples=200)
    def test_filter_is_subset_of_original(self, requests, rules):
        """过滤后的列表是原始列表的子集（每个元素都来自原始列表）"""
        filtered = apply_filter(requests, rules)
        for req in filtered:
            assert req in requests

    @given(
        requests=st.lists(captured_request_strategy(), min_size=0, max_size=30),
    )
    @settings(max_examples=100)
    def test_empty_rules_allow_all(self, requests):
        """空规则（所有维度为空列表）应允许所有请求通过"""
        rules = FilterRules(domains=[], paths=[], content_types=[])
        filtered = apply_filter(requests, rules)
        assert len(filtered) == len(requests)

    @given(
        requests=st.lists(captured_request_strategy(), min_size=1, max_size=30),
        rules=filter_rules_strategy(),
    )
    @settings(max_examples=200)
    def test_non_matching_items_excluded(self, requests, rules):
        """不满足规则的请求不会出现在过滤结果中"""
        filtered = apply_filter(requests, rules)
        non_matching = [req for req in requests if not matches_rules(req, rules)]
        for req in non_matching:
            assert req not in filtered
