"""数据模型序列化/反序列化单元测试和属性测试（round-trip）

**Validates: Requirements 3.6**

使用 Hypothesis 属性测试验证所有数据模型的 round-trip 序列化：
- Property 1: CapturedRequest round-trip (to_json/from_json, to_dict/from_dict)
- 嵌套模型: APIAnalysisResult, AnalysisReport
"""

import json
from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import (
    CaptureTarget,
    FilterRules,
    CapturedRequest,
    ParameterInfo,
    APIType,
    APIAnalysisResult,
    DataLink,
    AnalysisReport,
    RequirementStatus,
    ConnectionResult,
    CertResult,
    ProxyResult,
    ProcessResult,
)


# ============================================================
# Hypothesis Strategies
# ============================================================

# Use text that is JSON-safe (no surrogates) for dict keys/values
safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),  # exclude surrogates
    ),
    min_size=0,
    max_size=50,
)

# Strategy for JSON-serializable dict values
json_value = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**53), max_value=2**53),
        st.floats(allow_nan=False, allow_infinity=False),
        safe_text,
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(safe_text, children, max_size=5),
    ),
    max_leaves=10,
)

json_dict = st.dictionaries(safe_text, json_value, max_size=5)

# Datetime strategy
safe_datetimes = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2030, 12, 31),
).map(lambda dt: dt.replace(microsecond=(dt.microsecond // 1000) * 1000))


# Strategy for CapturedRequest
@st.composite
def captured_request_strategy(draw):
    return CapturedRequest(
        id=draw(safe_text.filter(lambda x: len(x) > 0)),
        timestamp=draw(safe_datetimes),
        method=draw(st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])),
        url=draw(safe_text),
        headers=draw(st.dictionaries(safe_text, safe_text, max_size=5)),
        body=draw(st.none() | safe_text),
        response_status=draw(st.integers(min_value=100, max_value=599)),
        response_headers=draw(st.dictionaries(safe_text, safe_text, max_size=5)),
        response_body=draw(st.none() | safe_text),
        is_decrypted=draw(st.booleans()),
    )


# Strategy for ParameterInfo
@st.composite
def parameter_info_strategy(draw):
    return ParameterInfo(
        name=draw(safe_text),
        value_sample=draw(safe_text),
        category=draw(st.sampled_from(["static", "session", "dynamic"])),
        source=draw(st.sampled_from(["query", "header", "body", "cookie"])),
    )


# Strategy for APIAnalysisResult
@st.composite
def api_analysis_result_strategy(draw):
    return APIAnalysisResult(
        request_id=draw(safe_text.filter(lambda x: len(x) > 0)),
        endpoint=draw(safe_text),
        api_type=draw(st.sampled_from(list(APIType))),
        parameters=draw(st.lists(parameter_info_strategy(), min_size=0, max_size=5)),
        has_signature=draw(st.booleans()),
        signature_fields=draw(st.lists(safe_text, max_size=5)),
        matches_target=draw(st.booleans()),
        call_count=draw(st.integers(min_value=0, max_value=10000)),
    )


# Strategy for DataLink
@st.composite
def data_link_strategy(draw):
    return DataLink(
        source_endpoint=draw(safe_text),
        target_endpoint=draw(safe_text),
        link_field=draw(safe_text),
        link_type=draw(st.sampled_from([
            "list_to_detail", "list_to_media", "detail_to_media",
        ])),
    )


# Strategy for AnalysisReport
@st.composite
def analysis_report_strategy(draw):
    results = draw(st.lists(api_analysis_result_strategy(), min_size=0, max_size=3))
    total_analyzed = len(results)
    target_matched = sum(1 for r in results if r.matches_target)
    total_captured = draw(st.integers(min_value=total_analyzed, max_value=total_analyzed + 100))
    return AnalysisReport(
        target=CaptureTarget(
            app_name=draw(safe_text),
            target_data=draw(safe_text),
            operation_pages=draw(safe_text),
            filter_domains=draw(st.none() | st.lists(safe_text, max_size=3)),
        ),
        results=results,
        data_links=draw(st.lists(data_link_strategy(), min_size=0, max_size=3)),
        total_captured=total_captured,
        total_analyzed=total_analyzed,
        target_matched=target_matched,
        generated_at=draw(safe_datetimes),
    )


# ============================================================
# Property 1: CapturedRequest Round-Trip
# **Validates: Requirements 3.6**
# ============================================================


class TestCapturedRequestRoundTrip:
    """CapturedRequest 序列化 round-trip 属性测试"""

    @given(request=captured_request_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, request: CapturedRequest):
        """model → to_json() → from_json() → should equal original"""
        serialized = request.to_json()
        deserialized = CapturedRequest.from_json(serialized)
        assert deserialized == request

    @given(request=captured_request_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, request: CapturedRequest):
        """model → to_dict() → from_dict() → should equal original"""
        d = request.to_dict()
        restored = CapturedRequest.from_dict(d)
        assert restored == request

    @given(request=captured_request_strategy())
    @settings(max_examples=50)
    def test_json_is_valid_json(self, request: CapturedRequest):
        """to_json() produces valid JSON"""
        json_str = request.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    @given(request=captured_request_strategy())
    @settings(max_examples=50)
    def test_dict_json_dumps_loads_roundtrip(self, request: CapturedRequest):
        """model → to_dict() → json.dumps → json.loads → from_dict() → should equal original"""
        d = request.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        restored_dict = json.loads(json_str)
        restored = CapturedRequest.from_dict(restored_dict)
        assert restored == request


# ============================================================
# ParameterInfo Round-Trip
# ============================================================


class TestParameterInfoRoundTrip:
    """ParameterInfo 序列化 round-trip 属性测试"""

    @given(param=parameter_info_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, param: ParameterInfo):
        """model → to_json() → from_json() → should equal original"""
        serialized = param.to_json()
        deserialized = ParameterInfo.from_json(serialized)
        assert deserialized == param

    @given(param=parameter_info_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, param: ParameterInfo):
        """model → to_dict() → from_dict() → should equal original"""
        d = param.to_dict()
        restored = ParameterInfo.from_dict(d)
        assert restored == param


# ============================================================
# APIAnalysisResult Round-Trip
# ============================================================


class TestAPIAnalysisResultRoundTrip:
    """APIAnalysisResult 序列化 round-trip 属性测试（嵌套 ParameterInfo 列表）"""

    @given(result=api_analysis_result_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, result: APIAnalysisResult):
        """model → to_json() → from_json() → should equal original"""
        serialized = result.to_json()
        deserialized = APIAnalysisResult.from_json(serialized)
        assert deserialized == result

    @given(result=api_analysis_result_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, result: APIAnalysisResult):
        """model → to_dict() → from_dict() → should equal original"""
        d = result.to_dict()
        restored = APIAnalysisResult.from_dict(d)
        assert restored == result

    @given(result=api_analysis_result_strategy())
    @settings(max_examples=50)
    def test_nested_parameters_preserved(self, result: APIAnalysisResult):
        """嵌套的 parameters 列表在 round-trip 后保持一致"""
        d = result.to_dict()
        restored = APIAnalysisResult.from_dict(d)
        assert len(restored.parameters) == len(result.parameters)
        for orig, rest in zip(result.parameters, restored.parameters):
            assert orig == rest


# ============================================================
# DataLink Round-Trip
# ============================================================


class TestDataLinkRoundTrip:
    """DataLink 序列化 round-trip 属性测试"""

    @given(link=data_link_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, link: DataLink):
        """model → to_json() → from_json() → should equal original"""
        serialized = link.to_json()
        deserialized = DataLink.from_json(serialized)
        assert deserialized == link

    @given(link=data_link_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, link: DataLink):
        """model → to_dict() → from_dict() → should equal original"""
        d = link.to_dict()
        restored = DataLink.from_dict(d)
        assert restored == link


# ============================================================
# AnalysisReport Round-Trip
# ============================================================


class TestAnalysisReportRoundTrip:
    """AnalysisReport 序列化 round-trip 属性测试"""

    @given(report=analysis_report_strategy())
    @settings(max_examples=50)
    def test_to_json_from_json_roundtrip(self, report: AnalysisReport):
        """model → to_json() → from_json() → should equal original"""
        serialized = report.to_json()
        deserialized = AnalysisReport.from_json(serialized)
        assert deserialized == report

    @given(report=analysis_report_strategy())
    @settings(max_examples=50)
    def test_to_dict_from_dict_roundtrip(self, report: AnalysisReport):
        """model → to_dict() → from_dict() → should equal original"""
        d = report.to_dict()
        restored = AnalysisReport.from_dict(d)
        assert restored == report


# ============================================================
# APIType Enum Tests
# ============================================================


class TestAPITypeEnum:
    """APIType 枚举测试"""

    def test_all_values_exist(self):
        """所有枚举值应存在"""
        assert APIType.LIST.value == "list"
        assert APIType.PAGINATION.value == "pagination"
        assert APIType.DETAIL.value == "detail"
        assert APIType.MEDIA.value == "media"
        assert APIType.CONFIG.value == "config"
        assert APIType.AUX.value == "aux"

    def test_enum_count(self):
        """应有 6 种接口类型"""
        assert len(APIType) == 6

    def test_enum_from_value(self):
        """应能从字符串值创建枚举"""
        assert APIType("list") == APIType.LIST
        assert APIType("pagination") == APIType.PAGINATION
        assert APIType("detail") == APIType.DETAIL
        assert APIType("media") == APIType.MEDIA
        assert APIType("config") == APIType.CONFIG
        assert APIType("aux") == APIType.AUX


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """边界情况测试"""

    def test_captured_request_none_body(self):
        """CapturedRequest with None body round-trips correctly"""
        req = CapturedRequest(
            id="test-1",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            method="GET",
            url="https://example.com",
            headers={},
            body=None,
            response_status=200,
            response_headers={},
            response_body=None,
            is_decrypted=True,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req
        assert restored.body is None
        assert restored.response_body is None

    def test_captured_request_empty_string_body(self):
        """CapturedRequest with empty string body round-trips correctly"""
        req = CapturedRequest(
            id="test-2",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            method="POST",
            url="https://example.com/api",
            headers={"Content-Type": "application/json"},
            body="",
            response_status=200,
            response_headers={},
            response_body="",
            is_decrypted=True,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req
        assert restored.body == ""
        assert restored.response_body == ""

    def test_captured_request_unicode(self):
        """CapturedRequest with unicode characters round-trips correctly"""
        req = CapturedRequest(
            id="test-unicode",
            timestamp=datetime(2024, 1, 1, 0, 0, 0),
            method="GET",
            url="https://例え.jp/パス",
            headers={"X-Custom": "中文值", "Accept": "テスト"},
            body=None,
            response_status=200,
            response_headers={"X-Response": "日本語"},
            response_body='{"message": "你好世界"}',
            is_decrypted=True,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req

    def test_captured_request_large_response_body(self):
        """CapturedRequest with large response body round-trips correctly"""
        large_body = json.dumps({"items": [{"id": i, "name": f"item-{i}"} for i in range(1000)]})
        req = CapturedRequest(
            id="test-large",
            timestamp=datetime(2024, 6, 15, 8, 30, 0),
            method="GET",
            url="https://example.com/api/list",
            headers={},
            body=None,
            response_status=200,
            response_headers={"Content-Type": "application/json"},
            response_body=large_body,
            is_decrypted=True,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req
        assert restored.response_body == large_body

    def test_api_analysis_result_empty_parameters(self):
        """APIAnalysisResult with empty parameters list round-trips correctly"""
        result = APIAnalysisResult(
            request_id="req-1",
            endpoint="/api/v1/empty",
            api_type=APIType.AUX,
            parameters=[],
            has_signature=False,
            signature_fields=[],
            matches_target=False,
            call_count=1,
        )
        restored = APIAnalysisResult.from_json(result.to_json())
        assert restored == result
        assert restored.parameters == []

    def test_analysis_report_empty_results(self):
        """AnalysisReport with empty results round-trips correctly"""
        report = AnalysisReport(
            target=CaptureTarget(
                app_name="TestApp",
                target_data="列表数据",
                operation_pages="首页",
            ),
            results=[],
            data_links=[],
            total_captured=0,
            total_analyzed=0,
            target_matched=0,
            generated_at=datetime(2024, 1, 1, 0, 0, 0),
        )
        restored = AnalysisReport.from_json(report.to_json())
        assert restored == report

    def test_capture_target_defaults(self):
        """CaptureTarget with default values"""
        target = CaptureTarget()
        assert target.app_name == ""
        assert target.target_data == ""
        assert target.operation_pages == ""
        assert target.filter_domains is None

    def test_filter_rules_defaults(self):
        """FilterRules with default values"""
        rules = FilterRules()
        assert "image/" in rules.content_type_blacklist
        assert "json" in rules.content_type_whitelist
        assert "/api/" in rules.api_path_patterns
        assert rules.user_domain_whitelist is None
        assert rules.user_domain_blacklist is None

    def test_result_types_creation(self):
        """Result types can be created with default values"""
        req_status = RequirementStatus(is_complete=False, missing_fields=["app_name"])
        assert not req_status.is_complete
        assert "app_name" in req_status.missing_fields

        conn = ConnectionResult(success=True, device_id="emulator-5554")
        assert conn.success
        assert conn.device_id == "emulator-5554"

        cert = CertResult(success=False, error="Permission denied")
        assert not cert.success
        assert cert.error == "Permission denied"

        proxy = ProxyResult(success=True, host="127.0.0.1", port=8080)
        assert proxy.success
        assert proxy.port == 8080

        proc = ProcessResult(success=True, pid=12345)
        assert proc.success
        assert proc.pid == 12345
