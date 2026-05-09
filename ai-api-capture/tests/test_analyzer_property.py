"""接口分析器属性测试

**Validates: Requirements 5.2, 5.3**

使用 Hypothesis 对接口分析器进行属性测试，验证：
- Property 3: 参数分类一致性
  - 对任意 ParameterInfo，category 必须为 static/session/dynamic 之一
  - 分类是确定性的：相同输入总是产生相同输出
- Property 6: 接口类型识别一致性
  - 被分类为 LIST 的请求，响应体必须含结构化对象数组
  - 被分类为 PAGINATION 的请求，必须含分页参数
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.api_analyzer import APIAnalyzer
from src.models import CapturedRequest, ParameterInfo, APIType, CaptureTarget

from datetime import datetime


# ============================================================
# Hypothesis 策略
# ============================================================

VALID_CATEGORIES = ["static", "session", "dynamic"]
VALID_SOURCES = ["query", "header", "body", "cookie"]

# 参数名策略
param_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True)

# 参数值策略
param_value_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=0,
    max_size=50,
)


# ============================================================
# Property 3: 参数分类一致性
# **Validates: Requirements 5.3**
# ============================================================


class TestParameterClassificationConsistency:
    """参数分类一致性属性测试

    验证：
    - 所有参数的 category 必须为 static/session/dynamic 之一
    - 分类是确定性的
    """

    def setup_method(self):
        self.analyzer = APIAnalyzer()

    @given(
        name=param_name_strategy,
        value=param_value_strategy,
    )
    @settings(max_examples=200)
    def test_classification_produces_valid_category(self, name, value):
        """分类结果必须为 static/session/dynamic 之一"""
        category = self.analyzer._classify_single_param(name, value)
        assert category in VALID_CATEGORIES, (
            f"Invalid category '{category}' for param '{name}' with value '{value}'"
        )

    @given(
        name=param_name_strategy,
        value=param_value_strategy,
    )
    @settings(max_examples=200)
    def test_classification_is_deterministic(self, name, value):
        """相同输入总是产生相同的分类结果"""
        result1 = self.analyzer._classify_single_param(name, value)
        result2 = self.analyzer._classify_single_param(name, value)
        assert result1 == result2

    def test_known_static_params(self):
        """已知的静态参数名应分类为 static"""
        static_names = ["version", "platform", "os", "brand", "model", "channel"]
        for name in static_names:
            category = self.analyzer._classify_single_param(name, "some_value")
            assert category == "static", f"'{name}' should be static, got '{category}'"

    def test_known_session_params(self):
        """已知的会话参数名应分类为 session"""
        session_names = ["token", "authorization", "session_id"]
        for name in session_names:
            category = self.analyzer._classify_single_param(name, "some_value")
            assert category == "session", f"'{name}' should be session, got '{category}'"

    def test_known_dynamic_params(self):
        """已知的动态参数名应分类为 dynamic"""
        dynamic_names = ["sign", "nonce", "timestamp", "signature"]
        for name in dynamic_names:
            category = self.analyzer._classify_single_param(name, "some_value")
            assert category == "dynamic", f"'{name}' should be dynamic, got '{category}'"

    def test_md5_value_classified_as_dynamic(self):
        """MD5 格式的值应分类为 dynamic"""
        category = self.analyzer._classify_single_param(
            "unknown_param", "a" * 32
        )
        assert category == "dynamic"

    def test_sha1_value_classified_as_dynamic(self):
        """SHA1 格式的值应分类为 dynamic"""
        category = self.analyzer._classify_single_param(
            "unknown_param", "b" * 40
        )
        assert category == "dynamic"


# ============================================================
# Property 6: 接口类型识别一致性
# **Validates: Requirements 5.2**
# ============================================================


def _make_request(
    url: str = "https://api.example.com/v1/data",
    method: str = "GET",
    response_body: str = "{}",
    body: str = None,
) -> CapturedRequest:
    """创建测试用 CapturedRequest"""
    return CapturedRequest(
        id="test-001",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        method=method,
        url=url,
        headers={},
        body=body,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=response_body,
        is_decrypted=True,
    )


class TestAPITypeIdentificationConsistency:
    """接口类型识别一致性属性测试

    验证：
    - LIST 类型的响应必须含结构化对象数组
    - PAGINATION 类型的请求必须含分页参数
    """

    def setup_method(self):
        self.analyzer = APIAnalyzer()

    def test_list_type_has_array_in_response(self):
        """被分类为 LIST 的请求，响应体必须含结构化对象数组"""
        # 构造一个 LIST 类型的响应
        response = json.dumps({
            "data": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"},
            ]
        })
        req = _make_request(response_body=response)
        api_type = self.analyzer.classify_api_type(req)
        assert api_type == APIType.LIST

        # 验证不变量：响应确实含数组
        parsed = json.loads(response)
        assert isinstance(parsed.get("data"), list)
        assert len(parsed["data"]) > 0
        assert isinstance(parsed["data"][0], dict)

    def test_pagination_type_has_pagination_params(self):
        """被分类为 PAGINATION 的请求，必须含分页参数"""
        response = json.dumps({
            "data": [{"id": 1, "name": "Item"}],
            "hasMore": True,
            "total": 100,
        })
        req = _make_request(
            url="https://api.example.com/v1/list?page=1&pageSize=20",
            response_body=response,
        )
        api_type = self.analyzer.classify_api_type(req)
        assert api_type == APIType.PAGINATION

    def test_non_list_response_not_classified_as_list(self):
        """不含数组的响应不应被分类为 LIST"""
        response = json.dumps({"status": "ok", "message": "success"})
        req = _make_request(response_body=response)
        api_type = self.analyzer.classify_api_type(req)
        assert api_type != APIType.LIST

    def test_array_without_id_not_classified_as_list(self):
        """数组元素不含 id 字段的不应被分类为 LIST"""
        response = json.dumps({
            "data": [
                {"value": 1, "label": "Option 1"},
                {"value": 2, "label": "Option 2"},
            ]
        })
        req = _make_request(response_body=response)
        api_type = self.analyzer.classify_api_type(req)
        assert api_type != APIType.LIST

    @given(
        page_param=st.sampled_from(["page", "offset", "cursor", "pageFlag"]),
        page_value=st.sampled_from(["1", "0", "abc123", "10"]),
    )
    @settings(max_examples=50)
    def test_pagination_requires_response_indicator(self, page_param, page_value):
        """有分页参数但无分页响应标识的不应被分类为 PAGINATION"""
        # 响应不含分页标识
        response = json.dumps({
            "data": [{"id": 1, "name": "Item"}],
        })
        req = _make_request(
            url=f"https://api.example.com/v1/list?{page_param}={page_value}",
            response_body=response,
        )
        api_type = self.analyzer.classify_api_type(req)
        # 没有分页响应标识，不应该是 PAGINATION（可能是 LIST）
        assert api_type != APIType.PAGINATION

    def test_classification_is_deterministic(self):
        """相同请求总是产生相同的类型分类"""
        response = json.dumps({
            "data": [{"id": 1, "name": "Test", "title": "Hello"}]
        })
        req = _make_request(response_body=response)

        results = [self.analyzer.classify_api_type(req) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_media_type_contains_media_url(self):
        """被分类为 MEDIA 的响应必须含媒体 URL 模式"""
        response = json.dumps({
            "videoUrl": "https://cdn.example.com/video/123.mp4",
            "title": "Test Video",
        })
        req = _make_request(response_body=response)
        api_type = self.analyzer.classify_api_type(req)
        assert api_type == APIType.MEDIA
