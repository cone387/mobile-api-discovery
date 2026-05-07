"""数据模型序列化/反序列化单元测试和属性测试（round-trip）

**Validates: Requirements 1.4**

使用 Hypothesis 属性测试验证所有数据模型的 round-trip 序列化：
- Property 1: CapturedRequest round-trip (to_json/from_json, to_dict/from_dict)
- Property 7: CrawlData round-trip (CrawlTask, CrawlConfig, CrawlStats)
- 嵌套模型: OperationSequence, APIAnalysisResult, CrawlTask
"""

import json
from datetime import datetime, timezone

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.models import (
    CapturedRequest,
    OperationStep,
    OperationSequence,
    ParameterInfo,
    APIAnalysisResult,
    GeneratedCode,
    CrawlConfig,
    CrawlStats,
    CrawlTask,
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

# Strategy for JSON-serializable dict values (no bytes, no datetime)
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

# Datetime strategy - use timezone-aware datetimes that survive isoformat round-trip
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
        operation_step_id=draw(safe_text),
        method=draw(st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])),
        url=draw(safe_text),
        headers=draw(st.dictionaries(safe_text, safe_text, max_size=5)),
        body=draw(st.none() | st.binary(max_size=200)),
        response_status=draw(st.integers(min_value=100, max_value=599)),
        response_headers=draw(st.dictionaries(safe_text, safe_text, max_size=5)),
        response_body=draw(st.none() | st.binary(max_size=200)),
        is_decrypted=draw(st.booleans()),
    )


# Strategy for OperationStep
@st.composite
def operation_step_strategy(draw):
    return OperationStep(
        id=draw(safe_text.filter(lambda x: len(x) > 0)),
        sequence_id=draw(safe_text),
        action_type=draw(st.sampled_from(["click", "swipe", "input", "navigate", "wait"])),
        target=draw(st.none() | safe_text),
        parameters=draw(json_dict),
        status=draw(st.sampled_from(["pending", "success", "failed", "skipped"])),
        error_message=draw(st.none() | safe_text),
    )


# Strategy for OperationSequence (nested with OperationStep list)
@st.composite
def operation_sequence_strategy(draw):
    return OperationSequence(
        id=draw(safe_text.filter(lambda x: len(x) > 0)),
        app_package=draw(safe_text),
        intent_description=draw(safe_text),
        steps=draw(st.lists(operation_step_strategy(), min_size=0, max_size=5)),
        created_at=draw(safe_datetimes),
    )


# Strategy for ParameterInfo
@st.composite
def parameter_info_strategy(draw):
    return ParameterInfo(
        name=draw(safe_text),
        value_sample=draw(safe_text),
        category=draw(st.sampled_from(["static", "session", "dynamic", "unknown"])),
        source=draw(st.sampled_from(["query", "header", "body", "cookie"])),
        reasoning=draw(safe_text),
    )


# Strategy for APIAnalysisResult (nested with ParameterInfo list)
@st.composite
def api_analysis_result_strategy(draw):
    return APIAnalysisResult(
        request_id=draw(safe_text.filter(lambda x: len(x) > 0)),
        endpoint=draw(safe_text),
        purpose=draw(safe_text),
        parameters=draw(st.lists(parameter_info_strategy(), min_size=0, max_size=5)),
        reproducibility=draw(st.sampled_from(["reproducible", "complex", "unknown"])),
        reproducibility_reason=draw(safe_text),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0)),
    )


# Strategy for GeneratedCode
@st.composite
def generated_code_strategy(draw):
    return GeneratedCode(
        api_id=draw(safe_text.filter(lambda x: len(x) > 0)),
        code=draw(safe_text),
        session_params=draw(st.lists(safe_text, max_size=5)),
        verification_status=draw(st.sampled_from(["pending", "passed", "failed"])),
        failure_reason=draw(st.none() | safe_text),
    )


# Strategy for CrawlConfig
@st.composite
def crawl_config_strategy(draw):
    return CrawlConfig(
        concurrency=draw(st.integers(min_value=1, max_value=100)),
        interval_ms=draw(st.integers(min_value=0, max_value=60000)),
        max_rounds=draw(st.integers(min_value=1, max_value=10000)),
        failure_threshold=draw(st.integers(min_value=1, max_value=1000)),
        round_interval_ms=draw(st.integers(min_value=0, max_value=300000)),
    )


# Strategy for CrawlStats
@st.composite
def crawl_stats_strategy(draw):
    total = draw(st.integers(min_value=0, max_value=100000))
    success = draw(st.integers(min_value=0, max_value=total))
    failure = total - success
    return CrawlStats(
        total_requests=total,
        success_count=success,
        failure_count=failure,
        consecutive_failures=draw(st.integers(min_value=0, max_value=failure if failure > 0 else 0)),
        data_collected=draw(st.integers(min_value=0, max_value=success if success > 0 else 0)),
    )


# Strategy for CrawlTask (nested with CrawlConfig and CrawlStats)
@st.composite
def crawl_task_strategy(draw):
    return CrawlTask(
        id=draw(safe_text.filter(lambda x: len(x) > 0)),
        api_id=draw(safe_text),
        mode=draw(st.sampled_from(["batch", "replay"])),
        config=draw(crawl_config_strategy()),
        status=draw(st.sampled_from(["running", "paused", "completed", "failed"])),
        stats=draw(crawl_stats_strategy()),
    )


# ============================================================
# Property 1: CapturedRequest Round-Trip
# **Validates: Requirements 1.4**
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
# OperationStep Round-Trip
# ============================================================


class TestOperationStepRoundTrip:
    """OperationStep 序列化 round-trip 属性测试"""

    @given(step=operation_step_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, step: OperationStep):
        """model → to_json() → from_json() → should equal original"""
        serialized = step.to_json()
        deserialized = OperationStep.from_json(serialized)
        assert deserialized == step

    @given(step=operation_step_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, step: OperationStep):
        """model → to_dict() → from_dict() → should equal original"""
        d = step.to_dict()
        restored = OperationStep.from_dict(d)
        assert restored == step


# ============================================================
# OperationSequence Round-Trip (nested model)
# ============================================================


class TestOperationSequenceRoundTrip:
    """OperationSequence 序列化 round-trip 属性测试（嵌套 OperationStep 列表）"""

    @given(seq=operation_sequence_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, seq: OperationSequence):
        """model → to_json() → from_json() → should equal original"""
        serialized = seq.to_json()
        deserialized = OperationSequence.from_json(serialized)
        assert deserialized == seq

    @given(seq=operation_sequence_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, seq: OperationSequence):
        """model → to_dict() → from_dict() → should equal original"""
        d = seq.to_dict()
        restored = OperationSequence.from_dict(d)
        assert restored == seq

    @given(seq=operation_sequence_strategy())
    @settings(max_examples=50)
    def test_nested_steps_preserved(self, seq: OperationSequence):
        """嵌套的 steps 列表在 round-trip 后保持一致"""
        d = seq.to_dict()
        restored = OperationSequence.from_dict(d)
        assert len(restored.steps) == len(seq.steps)
        for original_step, restored_step in zip(seq.steps, restored.steps):
            assert original_step == restored_step


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
# APIAnalysisResult Round-Trip (nested model)
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
# GeneratedCode Round-Trip
# ============================================================


class TestGeneratedCodeRoundTrip:
    """GeneratedCode 序列化 round-trip 属性测试"""

    @given(code=generated_code_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, code: GeneratedCode):
        """model → to_json() → from_json() → should equal original"""
        serialized = code.to_json()
        deserialized = GeneratedCode.from_json(serialized)
        assert deserialized == code

    @given(code=generated_code_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, code: GeneratedCode):
        """model → to_dict() → from_dict() → should equal original"""
        d = code.to_dict()
        restored = GeneratedCode.from_dict(d)
        assert restored == code


# ============================================================
# Property 7: CrawlData Round-Trip (CrawlConfig, CrawlStats, CrawlTask)
# **Validates: Requirements 1.4**
# ============================================================


class TestCrawlConfigRoundTrip:
    """CrawlConfig 序列化 round-trip 属性测试"""

    @given(config=crawl_config_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, config: CrawlConfig):
        """model → to_json() → from_json() → should equal original"""
        serialized = config.to_json()
        deserialized = CrawlConfig.from_json(serialized)
        assert deserialized == config

    @given(config=crawl_config_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, config: CrawlConfig):
        """model → to_dict() → from_dict() → should equal original"""
        d = config.to_dict()
        restored = CrawlConfig.from_dict(d)
        assert restored == config


class TestCrawlStatsRoundTrip:
    """CrawlStats 序列化 round-trip 属性测试"""

    @given(stats=crawl_stats_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, stats: CrawlStats):
        """model → to_json() → from_json() → should equal original"""
        serialized = stats.to_json()
        deserialized = CrawlStats.from_json(serialized)
        assert deserialized == stats

    @given(stats=crawl_stats_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, stats: CrawlStats):
        """model → to_dict() → from_dict() → should equal original"""
        d = stats.to_dict()
        restored = CrawlStats.from_dict(d)
        assert restored == stats


class TestCrawlTaskRoundTrip:
    """CrawlTask 序列化 round-trip 属性测试（嵌套 CrawlConfig 和 CrawlStats）"""

    @given(task=crawl_task_strategy())
    @settings(max_examples=100)
    def test_to_json_from_json_roundtrip(self, task: CrawlTask):
        """model → to_json() → from_json() → should equal original"""
        serialized = task.to_json()
        deserialized = CrawlTask.from_json(serialized)
        assert deserialized == task

    @given(task=crawl_task_strategy())
    @settings(max_examples=100)
    def test_to_dict_from_dict_roundtrip(self, task: CrawlTask):
        """model → to_dict() → from_dict() → should equal original"""
        d = task.to_dict()
        restored = CrawlTask.from_dict(d)
        assert restored == task

    @given(task=crawl_task_strategy())
    @settings(max_examples=50)
    def test_nested_config_and_stats_preserved(self, task: CrawlTask):
        """嵌套的 config 和 stats 在 round-trip 后保持一致"""
        d = task.to_dict()
        restored = CrawlTask.from_dict(d)
        assert restored.config == task.config
        assert restored.stats == task.stats

    @given(task=crawl_task_strategy())
    @settings(max_examples=50)
    def test_json_dumps_loads_roundtrip(self, task: CrawlTask):
        """model → to_dict() → json.dumps → json.loads → from_dict() → should equal original"""
        d = task.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        restored_dict = json.loads(json_str)
        restored = CrawlTask.from_dict(restored_dict)
        assert restored == task


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """边界情况测试：空字符串、None 值、空列表、大字节数组、Unicode 字符"""

    def test_captured_request_empty_body(self):
        """CapturedRequest with None body round-trips correctly"""
        req = CapturedRequest(
            id="test-1",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            operation_step_id="step-1",
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

    def test_captured_request_empty_bytes_body(self):
        """CapturedRequest with empty bytes body round-trips correctly"""
        req = CapturedRequest(
            id="test-2",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            operation_step_id="step-1",
            method="POST",
            url="https://example.com/api",
            headers={"Content-Type": "application/json"},
            body=b"",
            response_status=200,
            response_headers={},
            response_body=b"",
            is_decrypted=True,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req
        assert restored.body == b""
        assert restored.response_body == b""

    def test_captured_request_large_binary_body(self):
        """CapturedRequest with large binary body round-trips correctly"""
        large_body = bytes(range(256)) * 100  # 25600 bytes
        req = CapturedRequest(
            id="test-3",
            timestamp=datetime(2024, 6, 15, 8, 30, 0),
            operation_step_id="step-large",
            method="POST",
            url="https://example.com/upload",
            headers={},
            body=large_body,
            response_status=201,
            response_headers={},
            response_body=large_body,
            is_decrypted=True,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req
        assert restored.body == large_body

    def test_captured_request_unicode_headers(self):
        """CapturedRequest with unicode characters in headers round-trips correctly"""
        req = CapturedRequest(
            id="test-unicode",
            timestamp=datetime(2024, 1, 1, 0, 0, 0),
            operation_step_id="步骤-1",
            method="GET",
            url="https://例え.jp/パス",
            headers={"X-Custom": "中文值", "Accept": "テスト"},
            body=None,
            response_status=200,
            response_headers={"X-Response": "日本語"},
            response_body=None,
            is_decrypted=True,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req

    def test_captured_request_empty_strings(self):
        """CapturedRequest with empty strings round-trips correctly"""
        req = CapturedRequest(
            id="",
            timestamp=datetime(2024, 1, 1, 0, 0, 0),
            operation_step_id="",
            method="",
            url="",
            headers={"": ""},
            body=None,
            response_status=0,
            response_headers={},
            response_body=None,
            is_decrypted=False,
        )
        restored = CapturedRequest.from_json(req.to_json())
        assert restored == req

    def test_operation_sequence_empty_steps(self):
        """OperationSequence with empty steps list round-trips correctly"""
        seq = OperationSequence(
            id="seq-empty",
            app_package="com.example.app",
            intent_description="空操作序列",
            steps=[],
            created_at=datetime(2024, 1, 1, 0, 0, 0),
        )
        restored = OperationSequence.from_json(seq.to_json())
        assert restored == seq
        assert restored.steps == []

    def test_operation_step_none_target_and_error(self):
        """OperationStep with None target and error_message round-trips correctly"""
        step = OperationStep(
            id="step-none",
            sequence_id="seq-1",
            action_type="wait",
            target=None,
            parameters={},
            status="pending",
            error_message=None,
        )
        restored = OperationStep.from_json(step.to_json())
        assert restored == step
        assert restored.target is None
        assert restored.error_message is None

    def test_api_analysis_result_empty_parameters(self):
        """APIAnalysisResult with empty parameters list round-trips correctly"""
        result = APIAnalysisResult(
            request_id="req-1",
            endpoint="/api/v1/empty",
            purpose="测试空参数",
            parameters=[],
            reproducibility="reproducible",
            reproducibility_reason="无参数",
            confidence=1.0,
        )
        restored = APIAnalysisResult.from_json(result.to_json())
        assert restored == result
        assert restored.parameters == []

    def test_api_analysis_result_confidence_boundaries(self):
        """APIAnalysisResult with confidence at boundaries (0.0 and 1.0)"""
        for conf in [0.0, 1.0, 0.5]:
            result = APIAnalysisResult(
                request_id="req-conf",
                endpoint="/api/test",
                purpose="confidence test",
                parameters=[],
                reproducibility="unknown",
                reproducibility_reason="test",
                confidence=conf,
            )
            restored = APIAnalysisResult.from_json(result.to_json())
            assert restored.confidence == conf

    def test_generated_code_none_failure_reason(self):
        """GeneratedCode with None failure_reason round-trips correctly"""
        code = GeneratedCode(
            api_id="api-1",
            code="import requests\n\ndef fetch():\n    pass\n",
            session_params=["TOKEN", "SESSION_ID"],
            verification_status="passed",
            failure_reason=None,
        )
        restored = GeneratedCode.from_json(code.to_json())
        assert restored == code
        assert restored.failure_reason is None

    def test_generated_code_empty_session_params(self):
        """GeneratedCode with empty session_params list round-trips correctly"""
        code = GeneratedCode(
            api_id="api-2",
            code="print('hello')",
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        restored = GeneratedCode.from_json(code.to_json())
        assert restored == code
        assert restored.session_params == []

    def test_crawl_task_nested_roundtrip(self):
        """CrawlTask with nested CrawlConfig and CrawlStats round-trips correctly"""
        task = CrawlTask(
            id="task-1",
            api_id="api-1",
            mode="batch",
            config=CrawlConfig(
                concurrency=5,
                interval_ms=1000,
                max_rounds=10,
                failure_threshold=3,
                round_interval_ms=5000,
            ),
            status="running",
            stats=CrawlStats(
                total_requests=100,
                success_count=95,
                failure_count=5,
                consecutive_failures=0,
                data_collected=95,
            ),
        )
        restored = CrawlTask.from_json(task.to_json())
        assert restored == task
        assert restored.config == task.config
        assert restored.stats == task.stats

    def test_crawl_stats_zero_values(self):
        """CrawlStats with all zero values round-trips correctly"""
        stats = CrawlStats(
            total_requests=0,
            success_count=0,
            failure_count=0,
            consecutive_failures=0,
            data_collected=0,
        )
        restored = CrawlStats.from_json(stats.to_json())
        assert restored == stats
