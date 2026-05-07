"""报告生成模块测试

包含：
- 单元测试：验证报告生成、Markdown 渲染、文件保存、接口详情查询
- 属性测试：验证报告数据一致性（总数 = 各分类之和）
"""

import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import APIAnalysisResult, GeneratedCode, ParameterInfo
from src.report_generator import APISummary, ReportGenerator, SummaryReport


# ============================================================
# Hypothesis 策略
# ============================================================


def parameter_info_strategy():
    """生成 ParameterInfo 的策略"""
    return st.builds(
        ParameterInfo,
        name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-")),
        value_sample=st.text(min_size=0, max_size=50),
        category=st.sampled_from(["static", "session", "dynamic", "unknown"]),
        source=st.sampled_from(["query", "header", "body", "cookie"]),
        reasoning=st.text(min_size=1, max_size=100),
    )


def api_analysis_result_strategy():
    """生成 APIAnalysisResult 的策略"""
    return st.builds(
        APIAnalysisResult,
        request_id=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-")),
        endpoint=st.from_regex(r"/[a-z]{1,10}(/[a-z]{1,10}){0,3}", fullmatch=True),
        purpose=st.sampled_from(["feed", "user", "comment", "search", "auth", "unknown"]),
        parameters=st.lists(parameter_info_strategy(), min_size=0, max_size=5),
        reproducibility=st.sampled_from(["reproducible", "complex", "unknown"]),
        reproducibility_reason=st.text(min_size=1, max_size=100),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )


# ============================================================
# 属性测试
# ============================================================


class TestReportCountsProperty:
    """属性测试：报告数据一致性

    **Validates: Requirements 7.1**
    """

    @given(analyses=st.lists(api_analysis_result_strategy(), min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_report_counts_consistency(self, analyses):
        """总数 = 可复现数 + 复杂数 + 未知数 = 分析结果列表长度

        属性：汇总报告中的总接口数量等于可复现接口数量加复杂接口数量加未知接口数量，
        且等于输入分析结果列表的长度。
        """
        generator = ReportGenerator()
        report = generator.generate_summary(analyses)

        # 总数等于各分类之和
        assert report.total_count == (
            report.reproducible_count + report.complex_count + report.unknown_count
        )

        # 总数等于输入列表长度
        assert report.total_count == len(analyses)

    @given(analyses=st.lists(api_analysis_result_strategy(), min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_api_summaries_count_matches_total(self, analyses):
        """api_summaries 列表长度等于 total_count

        属性：报告中的摘要列表长度应与总接口数一致。
        """
        generator = ReportGenerator()
        report = generator.generate_summary(analyses)

        assert len(report.api_summaries) == report.total_count

    @given(analyses=st.lists(api_analysis_result_strategy(), min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_category_counts_match_input(self, analyses):
        """各分类计数与输入数据中的实际分类一致

        属性：报告中各分类的计数应与输入分析结果中对应分类的数量完全匹配。
        """
        generator = ReportGenerator()
        report = generator.generate_summary(analyses)

        expected_reproducible = sum(
            1 for a in analyses if a.reproducibility == "reproducible"
        )
        expected_complex = sum(
            1 for a in analyses if a.reproducibility == "complex"
        )
        expected_unknown = sum(
            1 for a in analyses if a.reproducibility == "unknown"
        )

        assert report.reproducible_count == expected_reproducible
        assert report.complex_count == expected_complex
        assert report.unknown_count == expected_unknown


# ============================================================
# 单元测试
# ============================================================


class TestGenerateSummary:
    """测试 generate_summary 方法"""

    def _make_analysis(
        self, request_id: str, endpoint: str, reproducibility: str
    ) -> APIAnalysisResult:
        """辅助方法：创建分析结果"""
        return APIAnalysisResult(
            request_id=request_id,
            endpoint=endpoint,
            purpose="feed",
            parameters=[],
            reproducibility=reproducibility,
            reproducibility_reason="test reason",
            confidence=0.9,
        )

    def test_empty_list(self):
        """空列表生成空报告"""
        generator = ReportGenerator()
        report = generator.generate_summary([])

        assert report.total_count == 0
        assert report.reproducible_count == 0
        assert report.complex_count == 0
        assert report.unknown_count == 0
        assert report.api_summaries == []

    def test_single_reproducible(self):
        """单个可复现接口"""
        generator = ReportGenerator()
        analyses = [self._make_analysis("req-1", "/api/feed", "reproducible")]
        report = generator.generate_summary(analyses)

        assert report.total_count == 1
        assert report.reproducible_count == 1
        assert report.complex_count == 0
        assert report.unknown_count == 0

    def test_mixed_types(self):
        """混合类型接口"""
        generator = ReportGenerator()
        analyses = [
            self._make_analysis("req-1", "/api/feed", "reproducible"),
            self._make_analysis("req-2", "/api/user", "reproducible"),
            self._make_analysis("req-3", "/api/sign", "complex"),
            self._make_analysis("req-4", "/api/other", "unknown"),
        ]
        report = generator.generate_summary(analyses)

        assert report.total_count == 4
        assert report.reproducible_count == 2
        assert report.complex_count == 1
        assert report.unknown_count == 1

    def test_api_summaries_content(self):
        """验证摘要内容正确"""
        generator = ReportGenerator()
        analysis = APIAnalysisResult(
            request_id="req-1",
            endpoint="/api/feed",
            purpose="feed",
            parameters=[],
            reproducibility="reproducible",
            reproducibility_reason="all static",
            confidence=0.95,
        )
        report = generator.generate_summary([analysis])

        assert len(report.api_summaries) == 1
        summary = report.api_summaries[0]
        assert summary.request_id == "req-1"
        assert summary.endpoint == "/api/feed"
        assert summary.purpose == "feed"
        assert summary.reproducibility == "reproducible"
        assert summary.confidence == 0.95


class TestRenderMarkdown:
    """测试 render_markdown 方法"""

    def test_renders_header(self):
        """渲染包含标题"""
        generator = ReportGenerator()
        report = SummaryReport(
            total_count=0,
            reproducible_count=0,
            complex_count=0,
            unknown_count=0,
            api_summaries=[],
        )
        markdown = generator.render_markdown(report)

        assert "# 接口抓取分析报告" in markdown

    def test_renders_statistics_table(self):
        """渲染包含统计表格"""
        generator = ReportGenerator()
        report = SummaryReport(
            total_count=3,
            reproducible_count=2,
            complex_count=1,
            unknown_count=0,
            api_summaries=[],
        )
        markdown = generator.render_markdown(report)

        assert "| 总接口数 | 3 |" in markdown
        assert "| 可复现接口 | 2 |" in markdown
        assert "| 复杂接口 | 1 |" in markdown
        assert "| 未知接口 | 0 |" in markdown

    def test_renders_api_list(self):
        """渲染包含接口列表"""
        generator = ReportGenerator()
        report = SummaryReport(
            total_count=1,
            reproducible_count=1,
            complex_count=0,
            unknown_count=0,
            api_summaries=[
                APISummary(
                    request_id="req-1",
                    endpoint="/api/feed",
                    purpose="feed",
                    reproducibility="reproducible",
                    confidence=0.9,
                )
            ],
        )
        markdown = generator.render_markdown(report)

        assert "/api/feed" in markdown
        assert "feed" in markdown
        assert "✅ 可复现" in markdown


class TestSaveReport:
    """测试 save_report 方法"""

    def test_saves_to_file(self):
        """报告保存到文件"""
        generator = ReportGenerator()
        report = SummaryReport(
            total_count=1,
            reproducible_count=1,
            complex_count=0,
            unknown_count=0,
            api_summaries=[
                APISummary(
                    request_id="req-1",
                    endpoint="/api/feed",
                    purpose="feed",
                    reproducibility="reproducible",
                    confidence=0.9,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "report.md")
            generator.save_report(report, output_path)

            assert os.path.exists(output_path)
            content = Path(output_path).read_text(encoding="utf-8")
            assert "# 接口抓取分析报告" in content
            assert "/api/feed" in content

    def test_creates_directories(self):
        """自动创建目录"""
        generator = ReportGenerator()
        report = SummaryReport(
            total_count=0,
            reproducible_count=0,
            complex_count=0,
            unknown_count=0,
            api_summaries=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "nested", "dir", "report.md")
            generator.save_report(report, output_path)

            assert os.path.exists(output_path)


class TestGetApiDetail:
    """测试 get_api_detail 方法"""

    def test_basic_detail(self):
        """基本详情输出"""
        generator = ReportGenerator()
        analysis = APIAnalysisResult(
            request_id="req-1",
            endpoint="/api/feed",
            purpose="feed",
            parameters=[
                ParameterInfo(
                    name="token",
                    value_sample="abc123",
                    category="session",
                    source="header",
                    reasoning="匹配会话参数模式",
                )
            ],
            reproducibility="reproducible",
            reproducibility_reason="所有参数均为静态或会话类型",
            confidence=0.95,
        )

        detail = generator.get_api_detail(
            request_id="req-1",
            analysis=analysis,
            generated_code=None,
            crawl_status=None,
        )

        assert "# 接口详情: /api/feed" in detail
        assert "req-1" in detail
        assert "feed" in detail
        assert "✅ 可复现" in detail
        assert "token" in detail
        assert "未生成代码" in detail
        assert "未启动采集" in detail

    def test_detail_with_generated_code(self):
        """包含生成代码的详情"""
        generator = ReportGenerator()
        analysis = APIAnalysisResult(
            request_id="req-1",
            endpoint="/api/feed",
            purpose="feed",
            parameters=[],
            reproducibility="reproducible",
            reproducibility_reason="all static",
            confidence=0.9,
        )
        generated = GeneratedCode(
            api_id="req-1",
            code="import requests\n\ndef fetch_feed():\n    pass",
            session_params=["token"],
            verification_status="passed",
            failure_reason=None,
        )

        detail = generator.get_api_detail(
            request_id="req-1",
            analysis=analysis,
            generated_code=generated,
            crawl_status="running",
        )

        assert "```python" in detail
        assert "import requests" in detail
        assert "passed" in detail
        assert "token" in detail
        assert "running" in detail

    def test_detail_with_crawl_status(self):
        """包含采集状态的详情"""
        generator = ReportGenerator()
        analysis = APIAnalysisResult(
            request_id="req-1",
            endpoint="/api/data",
            purpose="unknown",
            parameters=[],
            reproducibility="complex",
            reproducibility_reason="包含动态参数",
            confidence=0.7,
        )

        detail = generator.get_api_detail(
            request_id="req-1",
            analysis=analysis,
            generated_code=None,
            crawl_status="paused",
        )

        assert "⚠️ 复杂接口" in detail
        assert "paused" in detail
