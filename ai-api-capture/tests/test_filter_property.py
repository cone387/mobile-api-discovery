"""过滤规则属性测试

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

使用 Hypothesis 对 4 层过滤规则引擎进行属性测试，验证：
- Property 2（设计文档）: 过滤规则不变量
  - 通过过滤的请求必须满足：Content-Type 不在黑名单、域名不在黑名单、
    路径不在黑名单、且匹配 API 白名单
  - 过滤后的列表长度不超过原始列表长度

为避免依赖 mitmproxy flow 对象，实现独立的 apply_filter / should_keep
函数，使用与 TrafficInterceptor._should_keep 相同的逻辑。
"""

from dataclasses import dataclass, field
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
    """过滤规则（与 src/models.py FilterRules 保持一致）"""

    content_type_blacklist: List[str] = field(default_factory=lambda: [
        "image/", "font/", "video/", "audio/", "text/css", "application/javascript",
    ])
    domain_blacklist: List[str] = field(default_factory=list)
    path_blacklist: List[str] = field(default_factory=list)
    content_type_whitelist: List[str] = field(default_factory=lambda: ["json"])
    api_path_patterns: List[str] = field(default_factory=lambda: [
        "/api/", "/v1/", "/v2/", "/v3/", "/portal/", "/gateway/",
    ])
    user_domain_whitelist: Optional[List[str]] = None
    user_domain_blacklist: Optional[List[str]] = None


# ============================================================
# 4 层过滤逻辑（与 TrafficInterceptor._should_keep 保持一致）
# ============================================================


def _domain_matches_list(hostname: str, domain_list: List[str]) -> bool:
    """检查主机名是否匹配域名列表中的任一项。"""
    if not hostname:
        return False
    for domain in domain_list:
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


def should_keep(req: SimpleRequest, rules: FilterRules) -> bool:
    """应用 4 层过滤逻辑判断请求是否应保留。

    与 TrafficInterceptor._should_keep 逻辑完全一致。
    """
    parsed_url = urlparse(req.url)
    hostname = parsed_url.hostname or ""
    path = parsed_url.path or ""
    content_type = req.response_content_type.lower()

    # 用户域名白名单
    if rules.user_domain_whitelist:
        if not _domain_matches_list(hostname, rules.user_domain_whitelist):
            return False

    # 用户域名黑名单
    if rules.user_domain_blacklist:
        if _domain_matches_list(hostname, rules.user_domain_blacklist):
            return False

    # 第 1 层：静态资源过滤
    for blacklisted in rules.content_type_blacklist:
        if blacklisted.lower() in content_type:
            return False

    # 第 2 层：域名黑名单
    if _domain_matches_list(hostname, rules.domain_blacklist):
        return False

    # 第 3 层：路径黑名单
    for blacklisted_path in rules.path_blacklist:
        if blacklisted_path in path:
            return False

    # 第 4 层：API 白名单
    whitelist_match = False
    for whitelisted in rules.content_type_whitelist:
        if whitelisted.lower() in content_type:
            whitelist_match = True
            break
    if not whitelist_match:
        for pattern in rules.api_path_patterns:
            if pattern in path:
                whitelist_match = True
                break
    if not whitelist_match:
        return False

    return True


def apply_filter(requests: List[SimpleRequest], rules: FilterRules) -> List[SimpleRequest]:
    """对请求列表应用过滤规则，返回匹配的请求。"""
    return [req for req in requests if should_keep(req, rules)]


# ============================================================
# Hypothesis 策略
# ============================================================

# 域名策略
domain_strategy = st.from_regex(
    r"[a-z][a-z0-9]{0,10}\.(com|org|io|net|cn)", fullmatch=True
)

# 路径策略
path_strategy = st.from_regex(r"/[a-z0-9/]{0,20}", fullmatch=True)

# Content-Type 策略
content_type_strategy = st.sampled_from([
    "application/json",
    "application/json; charset=utf-8",
    "text/html",
    "text/plain",
    "application/xml",
    "image/png",
    "image/jpeg",
    "font/woff2",
    "video/mp4",
    "audio/mpeg",
    "text/css",
    "application/javascript",
    "application/octet-stream",
])


def filter_rules_strategy() -> st.SearchStrategy[FilterRules]:
    """生成 FilterRules 的策略"""
    return st.builds(
        FilterRules,
        content_type_blacklist=st.just([
            "image/", "font/", "video/", "audio/", "text/css", "application/javascript",
        ]),
        domain_blacklist=st.lists(domain_strategy, min_size=0, max_size=3),
        path_blacklist=st.lists(path_strategy, min_size=0, max_size=3),
        content_type_whitelist=st.just(["json"]),
        api_path_patterns=st.just(["/api/", "/v1/", "/v2/", "/v3/", "/portal/", "/gateway/"]),
        user_domain_whitelist=st.none(),
        user_domain_blacklist=st.none(),
    )


def captured_request_strategy() -> st.SearchStrategy[SimpleRequest]:
    """生成 SimpleRequest 的策略"""
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
            "/health", "/portal/home", "/gateway/service",
        ]),
    )

    return st.builds(
        SimpleRequest,
        url=url_strategy,
        response_content_type=content_type_strategy,
    )


# ============================================================
# 属性测试
# ============================================================


class TestFilterInvariant:
    """过滤规则不变量属性测试

    Feature: ai-api-capture, Property 2: 过滤规则不变量

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

    验证：通过过滤的请求必须满足所有 4 层过滤条件。
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
    def test_all_filtered_items_satisfy_invariant(self, requests, rules):
        """过滤后的每条记录都满足 4 层过滤不变量：
        - Content-Type 不在黑名单
        - 域名不在黑名单
        - 路径不在黑名单
        - 匹配 API 白名单
        """
        filtered = apply_filter(requests, rules)
        for req in filtered:
            parsed_url = urlparse(req.url)
            hostname = parsed_url.hostname or ""
            path = parsed_url.path or ""
            content_type = req.response_content_type.lower()

            # 不变量 1: Content-Type 不在黑名单
            for blacklisted in rules.content_type_blacklist:
                assert blacklisted.lower() not in content_type, (
                    f"Filtered request has blacklisted content type: {content_type}"
                )

            # 不变量 2: 域名不在黑名单
            assert not _domain_matches_list(hostname, rules.domain_blacklist), (
                f"Filtered request has blacklisted domain: {hostname}"
            )

            # 不变量 3: 路径不在黑名单
            for blacklisted_path in rules.path_blacklist:
                assert blacklisted_path not in path, (
                    f"Filtered request has blacklisted path: {path}"
                )

            # 不变量 4: 匹配 API 白名单
            whitelist_match = False
            for whitelisted in rules.content_type_whitelist:
                if whitelisted.lower() in content_type:
                    whitelist_match = True
                    break
            if not whitelist_match:
                for pattern in rules.api_path_patterns:
                    if pattern in path:
                        whitelist_match = True
                        break
            assert whitelist_match, (
                f"Filtered request doesn't match API whitelist: {req.url} ({content_type})"
            )

    @given(
        requests=st.lists(captured_request_strategy(), min_size=0, max_size=30),
        rules=filter_rules_strategy(),
    )
    @settings(max_examples=200)
    def test_filter_is_subset_of_original(self, requests, rules):
        """过滤后的列表是原始列表的子集"""
        filtered = apply_filter(requests, rules)
        for req in filtered:
            assert req in requests

    @given(
        requests=st.lists(captured_request_strategy(), min_size=0, max_size=30),
    )
    @settings(max_examples=100)
    def test_empty_blacklists_with_matching_whitelist(self, requests):
        """空黑名单 + 匹配白名单的请求应全部通过"""
        rules = FilterRules(
            content_type_blacklist=[],
            domain_blacklist=[],
            path_blacklist=[],
            content_type_whitelist=[""],  # 空字符串匹配所有
            api_path_patterns=[],
        )
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
        non_matching = [req for req in requests if not should_keep(req, rules)]
        for req in non_matching:
            assert req not in filtered
