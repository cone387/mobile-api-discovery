"""API Analyzer 模块测试

测试覆盖：
- 参数提取（URL query、headers、body、cookies）
- 参数分类规则
- 可复现性判定
- 接口用途检测
- 完整分析流程
"""

import pytest
from datetime import datetime

from src.api_analyzer import (
    APIAnalyzer,
    DefaultLLMClient,
    RequestContext,
    STANDARD_HEADERS,
)
from src.models import CapturedRequest, ParameterInfo


# === Fixtures ===


@pytest.fixture
def analyzer():
    """创建默认 APIAnalyzer 实例"""
    return APIAnalyzer()


@pytest.fixture
def basic_request():
    """创建基本的 CapturedRequest"""
    return CapturedRequest(
        id="req-001",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        operation_step_id="step-001",
        method="GET",
        url="https://api.example.com/v1/feed?page=1&app_version=2.0&token=abc123",
        headers={
            "Host": "api.example.com",
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9",
            "X-Custom-Header": "custom_value",
            "User-Agent": "MyApp/2.0",
        },
        body=None,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=b'{"data": []}',
        is_decrypted=True,
    )


@pytest.fixture
def post_request_json():
    """创建带 JSON body 的 POST 请求"""
    import json

    body = json.dumps({"user_id": "12345", "content": "hello", "sign": "abc123def456"})
    return CapturedRequest(
        id="req-002",
        timestamp=datetime(2024, 1, 1, 12, 1, 0),
        operation_step_id="step-002",
        method="POST",
        url="https://api.example.com/v1/comment/create",
        headers={
            "Host": "api.example.com",
            "Content-Type": "application/json",
            "Authorization": "Bearer token123",
        },
        body=body.encode("utf-8"),
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=b'{"success": true}',
        is_decrypted=True,
    )


@pytest.fixture
def request_with_cookies():
    """创建带 Cookie 的请求"""
    return CapturedRequest(
        id="req-003",
        timestamp=datetime(2024, 1, 1, 12, 2, 0),
        operation_step_id="step-003",
        method="GET",
        url="https://api.example.com/v1/user/profile",
        headers={
            "Host": "api.example.com",
            "Cookie": "session_id=sess123; user_pref=dark; tracking_id=xyz789",
        },
        body=None,
        response_status=200,
        response_headers={},
        response_body=b'{"name": "test"}',
        is_decrypted=True,
    )


@pytest.fixture
def form_data_request():
    """创建带 form data body 的请求"""
    return CapturedRequest(
        id="req-004",
        timestamp=datetime(2024, 1, 1, 12, 3, 0),
        operation_step_id="step-004",
        method="POST",
        url="https://api.example.com/v1/search",
        headers={
            "Host": "api.example.com",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=b"keyword=python&page=1&timestamp=1704067200",
        response_status=200,
        response_headers={},
        response_body=b'{"results": []}',
        is_decrypted=True,
    )


# === 4.1 参数提取测试 ===


class TestParameterExtraction:
    """测试参数提取逻辑"""

    def test_extract_query_params(self, analyzer, basic_request):
        """从 URL query string 提取参数"""
        params = analyzer.extract_parameters(basic_request)
        query_params = [(n, v, s) for n, v, s in params if s == "query"]

        assert ("page", "1", "query") in query_params
        assert ("app_version", "2.0", "query") in query_params
        assert ("token", "abc123", "query") in query_params

    def test_extract_header_params(self, analyzer, basic_request):
        """从 headers 提取非标准头部"""
        params = analyzer.extract_parameters(basic_request)
        header_params = [(n, v, s) for n, v, s in params if s == "header"]

        # Authorization 和 X-Custom-Header 应被提取
        header_names = [n for n, v, s in header_params]
        assert "Authorization" in header_names
        assert "X-Custom-Header" in header_names

        # 标准头部不应被提取
        assert "Host" not in header_names
        assert "User-Agent" not in header_names

    def test_extract_json_body_params(self, analyzer, post_request_json):
        """从 JSON body 提取参数"""
        params = analyzer.extract_parameters(post_request_json)
        body_params = [(n, v, s) for n, v, s in params if s == "body"]

        body_names = [n for n, v, s in body_params]
        assert "user_id" in body_names
        assert "content" in body_names
        assert "sign" in body_names

    def test_extract_form_body_params(self, analyzer, form_data_request):
        """从 form data body 提取参数"""
        params = analyzer.extract_parameters(form_data_request)
        body_params = [(n, v, s) for n, v, s in params if s == "body"]

        assert ("keyword", "python", "body") in body_params
        assert ("page", "1", "body") in body_params
        assert ("timestamp", "1704067200", "body") in body_params

    def test_extract_cookie_params(self, analyzer, request_with_cookies):
        """从 Cookie 头部提取参数"""
        params = analyzer.extract_parameters(request_with_cookies)
        cookie_params = [(n, v, s) for n, v, s in params if s == "cookie"]

        assert ("session_id", "sess123", "cookie") in cookie_params
        assert ("user_pref", "dark", "cookie") in cookie_params
        assert ("tracking_id", "xyz789", "cookie") in cookie_params

    def test_extract_no_body(self, analyzer, basic_request):
        """body 为 None 时不提取 body 参数"""
        params = analyzer.extract_parameters(basic_request)
        body_params = [(n, v, s) for n, v, s in params if s == "body"]
        assert body_params == []

    def test_extract_empty_query(self, analyzer):
        """URL 无 query string 时返回空"""
        request = CapturedRequest(
            id="req-empty",
            timestamp=datetime(2024, 1, 1),
            operation_step_id="step-001",
            method="GET",
            url="https://api.example.com/v1/feed",
            headers={},
            body=None,
            response_status=200,
            response_headers={},
            response_body=None,
            is_decrypted=True,
        )
        params = analyzer.extract_parameters(request)
        assert params == []


# === 4.2 参数分类测试 ===


class TestParameterClassification:
    """测试参数分类规则"""

    @pytest.fixture
    def context(self):
        return RequestContext(
            url="https://api.example.com/v1/feed",
            method="GET",
        )

    def test_classify_static_params(self, analyzer, context):
        """静态参数分类"""
        static_names = [
            "app_version",
            "platform",
            "os_version",
            "device_model",
            "channel",
            "language",
            "locale",
        ]
        for name in static_names:
            result = analyzer.classify_parameter(name, "some_value", context)
            assert result.category == "static", f"Expected '{name}' to be static"

    def test_classify_session_params_by_name(self, analyzer, context):
        """会话参数 - 名称匹配"""
        session_names = [
            "Authorization",
            "access_token",
            "session_id",
            "auth_key",
            "user_token",
            "cookie_value",
        ]
        for name in session_names:
            result = analyzer.classify_parameter(name, "some_value", context)
            assert result.category == "session", f"Expected '{name}' to be session"

    def test_classify_session_params_by_bearer_value(self, analyzer, context):
        """会话参数 - Bearer token 值"""
        result = analyzer.classify_parameter(
            "X-Custom", "Bearer eyJhbGciOiJIUzI1NiJ9", context
        )
        assert result.category == "session"

    def test_classify_dynamic_params_by_name(self, analyzer, context):
        """动态参数 - 名称匹配"""
        dynamic_names = [
            "sign",
            "signature",
            "nonce",
            "timestamp",
            "ts",
            "encrypted_data",
            "hash_value",
            "checksum",
        ]
        for name in dynamic_names:
            result = analyzer.classify_parameter(name, "some_value", context)
            assert result.category == "dynamic", f"Expected '{name}' to be dynamic"

    def test_classify_dynamic_params_by_value_md5(self, analyzer, context):
        """动态参数 - MD5 哈希值"""
        result = analyzer.classify_parameter(
            "data", "d41d8cd98f00b204e9800998ecf8427e", context
        )
        assert result.category == "dynamic"

    def test_classify_dynamic_params_by_value_sha256(self, analyzer, context):
        """动态参数 - SHA256 哈希值"""
        result = analyzer.classify_parameter(
            "data",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            context,
        )
        assert result.category == "dynamic"

    def test_classify_unknown_params(self, analyzer, context):
        """未知参数分类"""
        result = analyzer.classify_parameter("custom_field", "hello world", context)
        assert result.category == "unknown"

    def test_classification_priority_static_over_session(self, analyzer, context):
        """分类优先级：静态 > 会话（device_id 虽含 id 但在静态列表中）"""
        # device_id is in STATIC_PARAM_NAMES
        result = analyzer.classify_parameter("device_id", "abc123", context)
        assert result.category == "static"


# === 4.3 可复现性判定测试 ===


class TestReproducibilityDetermination:
    """测试可复现性判定逻辑"""

    def test_reproducible_all_static(self, analyzer):
        """全部静态参数 -> reproducible"""
        params = [
            ParameterInfo(
                name="app_version",
                value_sample="2.0",
                category="static",
                source="query",
                reasoning="",
            ),
            ParameterInfo(
                name="platform",
                value_sample="android",
                category="static",
                source="query",
                reasoning="",
            ),
        ]
        result, reason = analyzer.determine_reproducibility(params)
        assert result == "reproducible"
        assert "静态" in reason or "复现" in reason

    def test_reproducible_static_and_session(self, analyzer):
        """静态 + 会话参数 -> reproducible"""
        params = [
            ParameterInfo(
                name="app_version",
                value_sample="2.0",
                category="static",
                source="query",
                reasoning="",
            ),
            ParameterInfo(
                name="token",
                value_sample="abc",
                category="session",
                source="header",
                reasoning="",
            ),
        ]
        result, reason = analyzer.determine_reproducibility(params)
        assert result == "reproducible"

    def test_complex_with_dynamic(self, analyzer):
        """包含动态参数 -> complex"""
        params = [
            ParameterInfo(
                name="app_version",
                value_sample="2.0",
                category="static",
                source="query",
                reasoning="",
            ),
            ParameterInfo(
                name="sign",
                value_sample="abc123",
                category="dynamic",
                source="query",
                reasoning="",
            ),
        ]
        result, reason = analyzer.determine_reproducibility(params)
        assert result == "complex"
        assert "sign" in reason

    def test_unknown_with_only_unknown(self, analyzer):
        """仅有未知参数 -> unknown"""
        params = [
            ParameterInfo(
                name="app_version",
                value_sample="2.0",
                category="static",
                source="query",
                reasoning="",
            ),
            ParameterInfo(
                name="custom_field",
                value_sample="value",
                category="unknown",
                source="query",
                reasoning="",
            ),
        ]
        result, reason = analyzer.determine_reproducibility(params)
        assert result == "unknown"
        assert "custom_field" in reason

    def test_reproducible_empty_params(self, analyzer):
        """空参数列表 -> reproducible"""
        result, reason = analyzer.determine_reproducibility([])
        assert result == "reproducible"

    def test_complex_takes_priority_over_unknown(self, analyzer):
        """动态参数优先于未知参数"""
        params = [
            ParameterInfo(
                name="sign",
                value_sample="abc",
                category="dynamic",
                source="query",
                reasoning="",
            ),
            ParameterInfo(
                name="custom",
                value_sample="val",
                category="unknown",
                source="query",
                reasoning="",
            ),
        ]
        result, reason = analyzer.determine_reproducibility(params)
        assert result == "complex"


# === 4.4 接口用途语义分析测试 ===


class TestPurposeDetection:
    """测试接口用途检测"""

    def test_detect_feed_purpose(self, analyzer):
        """检测 feed 类接口"""
        purpose = analyzer._detect_purpose("https://api.example.com/v1/feed/list")
        assert purpose == "feed"

    def test_detect_user_purpose(self, analyzer):
        """检测 user 类接口"""
        purpose = analyzer._detect_purpose("https://api.example.com/v1/user/profile")
        assert purpose == "user"

    def test_detect_comment_purpose(self, analyzer):
        """检测 comment 类接口"""
        purpose = analyzer._detect_purpose(
            "https://api.example.com/v1/comment/create"
        )
        assert purpose == "comment"

    def test_detect_search_purpose(self, analyzer):
        """检测 search 类接口"""
        purpose = analyzer._detect_purpose("https://api.example.com/v1/search")
        assert purpose == "search"

    def test_detect_auth_purpose(self, analyzer):
        """检测 auth 类接口"""
        purpose = analyzer._detect_purpose("https://api.example.com/v1/login")
        assert purpose == "auth"

    def test_detect_unknown_purpose(self, analyzer):
        """无法识别的接口用途"""
        purpose = analyzer._detect_purpose("https://api.example.com/v1/xyz/abc")
        assert purpose == "unknown"

    def test_detect_payment_purpose(self, analyzer):
        """检测 payment 类接口"""
        purpose = analyzer._detect_purpose("https://api.example.com/v1/payment/create")
        assert purpose == "payment"


# === 完整分析流程测试 ===


class TestAnalyzeSingle:
    """测试完整的单请求分析流程"""

    @pytest.mark.asyncio
    async def test_analyze_simple_get(self, analyzer):
        """分析简单 GET 请求（仅静态参数）"""
        request = CapturedRequest(
            id="req-simple",
            timestamp=datetime(2024, 1, 1),
            operation_step_id="step-001",
            method="GET",
            url="https://api.example.com/v1/feed?app_version=2.0&platform=android",
            headers={"Host": "api.example.com"},
            body=None,
            response_status=200,
            response_headers={},
            response_body=b'{"data": []}',
            is_decrypted=True,
        )

        result = await analyzer.analyze_single(request)

        assert result.request_id == "req-simple"
        assert result.endpoint == "/v1/feed"
        assert result.purpose == "feed"
        assert result.reproducibility == "reproducible"
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_analyze_complex_request(self, analyzer):
        """分析包含动态参数的复杂请求"""
        request = CapturedRequest(
            id="req-complex",
            timestamp=datetime(2024, 1, 1),
            operation_step_id="step-001",
            method="GET",
            url="https://api.example.com/v1/feed?sign=abc123&nonce=xyz&app_version=2.0",
            headers={"Host": "api.example.com"},
            body=None,
            response_status=200,
            response_headers={},
            response_body=b'{"data": []}',
            is_decrypted=True,
        )

        result = await analyzer.analyze_single(request)

        assert result.reproducibility == "complex"
        dynamic_names = [p.name for p in result.parameters if p.category == "dynamic"]
        assert "sign" in dynamic_names
        assert "nonce" in dynamic_names

    @pytest.mark.asyncio
    async def test_analyze_cookie_params_classified_as_session(self, analyzer):
        """Cookie 来源的未知参数应归类为 session"""
        request = CapturedRequest(
            id="req-cookie",
            timestamp=datetime(2024, 1, 1),
            operation_step_id="step-001",
            method="GET",
            url="https://api.example.com/v1/user/profile",
            headers={
                "Host": "api.example.com",
                "Cookie": "my_custom_cookie=value123",
            },
            body=None,
            response_status=200,
            response_headers={},
            response_body=b'{}',
            is_decrypted=True,
        )

        result = await analyzer.analyze_single(request)

        cookie_params = [p for p in result.parameters if p.source == "cookie"]
        assert len(cookie_params) > 0
        # Cookie 来源的未知参数应被归类为 session
        for p in cookie_params:
            assert p.category == "session"

    @pytest.mark.asyncio
    async def test_analyze_batch(self, analyzer):
        """批量分析多个请求"""
        requests = [
            CapturedRequest(
                id=f"req-{i}",
                timestamp=datetime(2024, 1, 1),
                operation_step_id="step-001",
                method="GET",
                url=f"https://api.example.com/v1/feed?page={i}",
                headers={"Host": "api.example.com"},
                body=None,
                response_status=200,
                response_headers={},
                response_body=b'{}',
                is_decrypted=True,
            )
            for i in range(3)
        ]

        results = await analyzer.analyze_batch(requests)

        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.request_id == f"req-{i}"


# === DefaultLLMClient 测试 ===


class TestDefaultLLMClient:
    """测试默认 LLM 客户端"""

    def test_detect_purpose_patterns(self):
        """测试各种 URL 模式的用途检测"""
        client = DefaultLLMClient()

        assert client.detect_purpose("https://api.com/feed") == "feed"
        assert client.detect_purpose("https://api.com/timeline") == "feed"
        assert client.detect_purpose("https://api.com/user/info") == "user"
        assert client.detect_purpose("https://api.com/profile") == "user"
        assert client.detect_purpose("https://api.com/search/query") == "search"
        assert client.detect_purpose("https://api.com/comment/list") == "comment"
        assert client.detect_purpose("https://api.com/unknown/path") == "unknown"

    @pytest.mark.asyncio
    async def test_analyze_returns_string(self):
        """analyze 方法返回字符串"""
        client = DefaultLLMClient()
        result = await client.analyze("test prompt")
        assert isinstance(result, str)
