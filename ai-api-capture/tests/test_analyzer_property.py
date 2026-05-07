"""参数分类与可复现性判定属性测试

**Validates: Requirements 3.3**

使用 Hypothesis 对参数分类和可复现性判定逻辑进行属性测试，验证：
- 属性 3（设计文档）: 参数分类与可复现性判定一致性
  - 如果接口被标记为"可复现"，则其参数列表中不包含 category 为 "dynamic" 的参数
  - 如果接口被标记为"可复现"，则其参数列表中不包含 category 为 "unknown" 的参数
  - 如果接口被标记为"complex"，则其参数列表中至少有一个 category 为 "dynamic" 的参数

额外属性：
1. 分类是确定性的：相同输入总是产生相同输出
2. 可复现性判定是确定性的：相同参数列表总是产生相同结果
3. 向可复现参数集添加动态参数使其变为 complex
4. 从任何参数集中移除所有 dynamic/unknown 参数使其变为 reproducible
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.api_analyzer import APIAnalyzer, RequestContext
from src.models import ParameterInfo


# ============================================================
# Hypothesis 策略
# ============================================================

# 参数分类策略
VALID_CATEGORIES = ["static", "session", "dynamic", "unknown"]

# 参数来源策略
VALID_SOURCES = ["query", "header", "body", "cookie"]

# 参数名策略
param_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True)

# 参数值策略
param_value_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=0,
    max_size=50,
)


def parameter_info_strategy() -> st.SearchStrategy[ParameterInfo]:
    """生成 ParameterInfo 的策略

    生成带有合法 category 和 source 的参数信息对象。
    """
    return st.builds(
        ParameterInfo,
        name=param_name_strategy,
        value_sample=param_value_strategy,
        category=st.sampled_from(VALID_CATEGORIES),
        source=st.sampled_from(VALID_SOURCES),
        reasoning=st.just("test reasoning"),
    )


def reproducible_param_strategy() -> st.SearchStrategy[ParameterInfo]:
    """生成不会导致 complex/unknown 判定的参数（static 或 session）"""
    return st.builds(
        ParameterInfo,
        name=param_name_strategy,
        value_sample=param_value_strategy,
        category=st.sampled_from(["static", "session"]),
        source=st.sampled_from(VALID_SOURCES),
        reasoning=st.just("test reasoning"),
    )


def dynamic_param_strategy() -> st.SearchStrategy[ParameterInfo]:
    """生成 dynamic 类别的参数"""
    return st.builds(
        ParameterInfo,
        name=param_name_strategy,
        value_sample=param_value_strategy,
        category=st.just("dynamic"),
        source=st.sampled_from(VALID_SOURCES),
        reasoning=st.just("test reasoning"),
    )


def request_context_strategy() -> st.SearchStrategy[RequestContext]:
    """生成 RequestContext 的策略"""
    return st.builds(
        RequestContext,
        url=st.sampled_from([
            "https://api.example.com/v1/feed",
            "https://app.test.io/api/users",
            "https://service.net/data/items",
        ]),
        method=st.sampled_from(["GET", "POST", "PUT", "DELETE"]),
        content_type=st.sampled_from([
            "application/json",
            "application/x-www-form-urlencoded",
            None,
        ]),
    )


# ============================================================
# 属性测试
# ============================================================


class TestReproducibilityConsistency:
    """参数分类与可复现性判定一致性属性测试

    **Validates: Requirements 3.3**

    验证设计文档中的属性 3：
    - reproducible 结果不包含 dynamic 或 unknown 参数
    - complex 结果至少包含一个 dynamic 参数
    """

    def setup_method(self):
        self.analyzer = APIAnalyzer()

    @given(params=st.lists(parameter_info_strategy(), min_size=0, max_size=20))
    @settings(max_examples=200)
    def test_reproducible_has_no_dynamic_or_unknown(self, params):
        """如果判定为 reproducible，则参数列表中不包含 dynamic 或 unknown 参数"""
        result, reason = self.analyzer.determine_reproducibility(params)
        if result == "reproducible":
            assert all(p.category != "dynamic" for p in params)
            assert all(p.category != "unknown" for p in params)

    @given(params=st.lists(parameter_info_strategy(), min_size=0, max_size=20))
    @settings(max_examples=200)
    def test_complex_has_at_least_one_dynamic(self, params):
        """如果判定为 complex，则参数列表中至少有一个 dynamic 参数"""
        result, reason = self.analyzer.determine_reproducibility(params)
        if result == "complex":
            assert any(p.category == "dynamic" for p in params)

    @given(params=st.lists(parameter_info_strategy(), min_size=0, max_size=20))
    @settings(max_examples=200)
    def test_unknown_result_has_unknown_params_no_dynamic(self, params):
        """如果判定为 unknown，则参数列表中有 unknown 参数但无 dynamic 参数"""
        result, reason = self.analyzer.determine_reproducibility(params)
        if result == "unknown":
            assert any(p.category == "unknown" for p in params)
            assert all(p.category != "dynamic" for p in params)


class TestClassificationDeterminism:
    """分类确定性属性测试

    **Validates: Requirements 3.3**

    验证分类和可复现性判定是确定性的：相同输入总是产生相同输出。
    """

    def setup_method(self):
        self.analyzer = APIAnalyzer()

    @given(
        name=param_name_strategy,
        value=param_value_strategy,
        context=request_context_strategy(),
    )
    @settings(max_examples=200)
    def test_classification_is_deterministic(self, name, value, context):
        """相同输入参数总是产生相同的分类结果"""
        result1 = self.analyzer.classify_parameter(name, value, context)
        result2 = self.analyzer.classify_parameter(name, value, context)
        assert result1.category == result2.category
        assert result1.reasoning == result2.reasoning

    @given(params=st.lists(parameter_info_strategy(), min_size=0, max_size=20))
    @settings(max_examples=200)
    def test_reproducibility_is_deterministic(self, params):
        """相同参数列表总是产生相同的可复现性判定结果"""
        result1, reason1 = self.analyzer.determine_reproducibility(params)
        result2, reason2 = self.analyzer.determine_reproducibility(params)
        assert result1 == result2
        assert reason1 == reason2


class TestReproducibilityTransitions:
    """可复现性状态转换属性测试

    **Validates: Requirements 3.3**

    验证参数集合变化时可复现性判定的正确转换：
    - 向可复现参数集添加动态参数使其变为 complex
    - 从任何参数集中移除所有 dynamic/unknown 参数使其变为 reproducible
    """

    def setup_method(self):
        self.analyzer = APIAnalyzer()

    @given(
        reproducible_params=st.lists(reproducible_param_strategy(), min_size=0, max_size=10),
        dynamic_param=dynamic_param_strategy(),
    )
    @settings(max_examples=200)
    def test_adding_dynamic_makes_complex(self, reproducible_params, dynamic_param):
        """向可复现参数集添加一个 dynamic 参数使其变为 complex"""
        # 先验证原始参数集是 reproducible
        result_before, _ = self.analyzer.determine_reproducibility(reproducible_params)
        assert result_before == "reproducible"

        # 添加 dynamic 参数后应变为 complex
        params_with_dynamic = reproducible_params + [dynamic_param]
        result_after, _ = self.analyzer.determine_reproducibility(params_with_dynamic)
        assert result_after == "complex"

    @given(params=st.lists(parameter_info_strategy(), min_size=0, max_size=20))
    @settings(max_examples=200)
    def test_removing_dynamic_unknown_makes_reproducible(self, params):
        """从任何参数集中移除所有 dynamic/unknown 参数使其变为 reproducible"""
        # 过滤掉 dynamic 和 unknown 参数
        filtered_params = [
            p for p in params if p.category not in ("dynamic", "unknown")
        ]
        result, _ = self.analyzer.determine_reproducibility(filtered_params)
        assert result == "reproducible"
