"""报告生成模块测试

包含：
- 单元测试：验证报告生成、Markdown 渲染、cURL 命令生成、样本保存
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.models import (
    AnalysisReport,
    APIAnalysisResult,
    APIType,
    CapturedRequest,
    CaptureTarget,
    DataLink,
    ParameterInfo,
)
from src.report_generator import ReportGenerator


# ============================================================
# 测试辅助
# ============================================================


def _make_target() -> CaptureTarget:
    """创建测试用 CaptureTarget"""
    return CaptureTarget(
        app_name="TestApp",
        target_data="小说章节列表和内容",
        operation_pages="首页、书架、阅读页",
    )


def _make_request(
    request_id: str = "req-001",
    method: str = "GET",
    url: str = "https://api.example.com/v1/books?page=1",
    headers: dict = None,
    body: str = None,
    response_status: int = 200,
    response_body: str = None,
) -> CapturedRequest:
    """创建测试用 CapturedRequest"""
    if headers is None:
        headers = {
            "User-Agent": "TestApp/1.0",
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
            "Host": "api.example.com",
        }
    if response_body is None:
        response_body = json.dumps({"code": 0, "data": [{"id": 1, "title": "Book 1"}]})
    return CapturedRequest(
        id=request_id,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        method=method,
        url=url,
        headers=headers,
        body=body,
        response_status=response_status,
        response_headers={"Content-Type": "application/json"},
        response_body=response_body,
        is_decrypted=True,
    )


def _make_result(
    request_id: str = "req-001",
    endpoint: str = "/v1/books",
    api_type: APIType = APIType.LIST,
    matches_target: bool = True,
    has_signature: bool = False,
    signature_fields: list = None,
    call_count: int = 1,
) -> APIAnalysisResult:
    """创建测试用 APIAnalysisResult"""
    return APIAnalysisResult(
        request_id=request_id,
        endpoint=endpoint,
        api_type=api_type,
        parameters=[
            ParameterInfo(
                name="page",
                value_sample="1",
                category="dynamic",
                source="query",
            ),
            ParameterInfo(
                name="token",
                value_sample="Bearer token123",
                category="session",
                source="header",
            ),
        ],
        has_signature=has_signature,
        signature_fields=signature_fields or [],
        matches_target=matches_target,
        call_count=call_count,
    )


def _make_report(
    results: list = None,
    data_links: list = None,
) -> AnalysisReport:
    """创建测试用 AnalysisReport"""
    if results is None:
        results = [_make_result()]
    if data_links is None:
        data_links = []
    return AnalysisReport(
        target=_make_target(),
        results=results,
        data_links=data_links,
        total_captured=50,
        total_analyzed=len(results),
        target_matched=sum(1 for r in results if r.matches_target),
        generated_at=datetime(2024, 1, 15, 12, 0, 0),
    )


# ============================================================
# 单元测试：generate_curl
# ============================================================


class TestGenerateCurl:
    """测试 generate_curl 方法"""

    def test_get_request(self):
        """GET 请求不包含 -X 标志"""
        generator = ReportGenerator()
        request = _make_request(method="GET")
        curl = generator.generate_curl(request)

        assert "curl" in curl
        assert "-X GET" not in curl
        assert request.url in curl

    def test_post_request(self):
        """POST 请求包含 -X POST"""
        generator = ReportGenerator()
        request = _make_request(method="POST", body='{"key": "value"}')
        curl = generator.generate_curl(request)

        assert "-X POST" in curl
        assert "-d " in curl

    def test_includes_non_trivial_headers(self):
        """包含非平凡请求头"""
        generator = ReportGenerator()
        request = _make_request()
        curl = generator.generate_curl(request)

        assert "User-Agent: TestApp/1.0" in curl
        assert "Authorization: Bearer token123" in curl
        assert "Content-Type: application/json" in curl

    def test_excludes_trivial_headers(self):
        """排除平凡请求头（Host, Content-Length 等）"""
        generator = ReportGenerator()
        request = _make_request(
            headers={
                "Host": "api.example.com",
                "Content-Length": "100",
                "Connection": "keep-alive",
                "Accept-Encoding": "gzip",
                "X-Custom": "value",
            }
        )
        curl = generator.generate_curl(request)

        assert "Host:" not in curl
        assert "Content-Length:" not in curl
        assert "Connection:" not in curl
        assert "Accept-Encoding:" not in curl
        assert "X-Custom: value" in curl

    def test_includes_complete_url(self):
        """包含完整 URL（含查询参数）"""
        generator = ReportGenerator()
        url = "https://api.example.com/v1/books?page=1&size=20"
        request = _make_request(url=url)
        curl = generator.generate_curl(request)

        assert url in curl

    def test_put_method(self):
        """PUT 方法"""
        generator = ReportGenerator()
        request = _make_request(method="PUT", body='{"title": "new"}')
        curl = generator.generate_curl(request)

        assert "-X PUT" in curl

    def test_body_with_single_quotes(self):
        """请求体中包含单引号时正确转义"""
        generator = ReportGenerator()
        request = _make_request(method="POST", body="{'key': 'value'}")
        curl = generator.generate_curl(request)

        # Should contain the body (escaped)
        assert "-d " in curl


# ============================================================
# 单元测试：save_samples
# ============================================================


class TestSaveSamples:
    """测试 save_samples 方法"""

    def test_saves_sample_files(self):
        """保存样本文件到指定目录"""
        generator = ReportGenerator()
        requests = [_make_request()]
        results = [_make_result()]

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = os.path.join(tmpdir, "samples")
            paths = generator.save_samples(requests, results, samples_dir)

            assert len(paths) == 1
            assert paths[0] == "samples/req-001.json"

            # 验证文件存在
            filepath = os.path.join(samples_dir, "req-001.json")
            assert os.path.exists(filepath)

            # 验证文件内容
            content = json.loads(Path(filepath).read_text(encoding="utf-8"))
            assert content["request"]["method"] == "GET"
            assert content["request"]["url"] == "https://api.example.com/v1/books?page=1"
            assert content["response"]["status"] == 200
            assert content["analysis"]["endpoint"] == "/v1/books"
            assert content["analysis"]["api_type"] == "list"

    def test_creates_directory(self):
        """自动创建 samples 目录"""
        generator = ReportGenerator()
        requests = [_make_request()]
        results = [_make_result()]

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = os.path.join(tmpdir, "nested", "samples")
            paths = generator.save_samples(requests, results, samples_dir)

            assert len(paths) == 1
            assert os.path.exists(samples_dir)

    def test_multiple_samples(self):
        """保存多个样本文件"""
        generator = ReportGenerator()
        requests = [
            _make_request(request_id="req-001"),
            _make_request(request_id="req-002", url="https://api.example.com/v1/detail?id=1"),
        ]
        results = [
            _make_result(request_id="req-001"),
            _make_result(request_id="req-002", endpoint="/v1/detail", api_type=APIType.DETAIL),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = os.path.join(tmpdir, "samples")
            paths = generator.save_samples(requests, results, samples_dir)

            assert len(paths) == 2
            assert "samples/req-001.json" in paths
            assert "samples/req-002.json" in paths

    def test_missing_request_skipped(self):
        """当 result 对应的 request 不存在时跳过"""
        generator = ReportGenerator()
        requests = [_make_request(request_id="req-001")]
        results = [
            _make_result(request_id="req-001"),
            _make_result(request_id="req-999"),  # 不存在的 request
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            samples_dir = os.path.join(tmpdir, "samples")
            paths = generator.save_samples(requests, results, samples_dir)

            assert len(paths) == 1
            assert paths[0] == "samples/req-001.json"


# ============================================================
# 单元测试：render_markdown
# ============================================================


class TestRenderMarkdown:
    """测试 render_markdown 方法"""

    def test_contains_title(self):
        """报告包含标题"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "# 接口分析报告" in markdown

    def test_contains_target_summary(self):
        """报告包含抓取目标摘要"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "## 抓取目标摘要" in markdown
        assert "TestApp" in markdown
        assert "小说章节列表和内容" in markdown
        assert "首页、书架、阅读页" in markdown

    def test_contains_statistics(self):
        """报告包含统计数据"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "总捕获请求数: 50" in markdown
        assert "分析接口数: 1" in markdown
        assert "匹配目标接口数: 1" in markdown

    def test_contains_data_links(self):
        """报告包含数据链路图"""
        generator = ReportGenerator()
        data_links = [
            DataLink(
                source_endpoint="/v1/books",
                target_endpoint="/v1/book/detail",
                link_field="book_id",
                link_type="list_to_detail",
            )
        ]
        report = _make_report(data_links=data_links)
        markdown = generator.render_markdown(report)

        assert "## 数据链路图" in markdown
        assert "/v1/books" in markdown
        assert "/v1/book/detail" in markdown
        assert "book_id" in markdown
        assert "list_to_detail" in markdown

    def test_no_data_links(self):
        """无数据链路时显示提示"""
        generator = ReportGenerator()
        report = _make_report(data_links=[])
        markdown = generator.render_markdown(report)

        assert "未检测到接口间数据链路关系" in markdown

    def test_contains_overview_table(self):
        """报告包含接口概览表"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "## 接口概览表" in markdown
        assert "| 接口路径 | 类型 | 调用次数 | 匹配目标 |" in markdown
        assert "/v1/books" in markdown
        assert "list" in markdown

    def test_contains_api_details(self):
        """报告包含接口详情"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "## 接口详情" in markdown
        assert "### /v1/books" in markdown
        assert "#### 请求参数" in markdown
        assert "| page | dynamic | query |" in markdown

    def test_contains_signature_section(self):
        """报告包含签名机制说明"""
        generator = ReportGenerator()
        results = [
            _make_result(has_signature=True, signature_fields=["sign", "nonce", "timestamp"])
        ]
        report = _make_report(results=results)
        markdown = generator.render_markdown(report)

        assert "## 签名机制说明" in markdown
        assert "sign" in markdown
        assert "nonce" in markdown
        assert "timestamp" in markdown

    def test_no_signature(self):
        """无签名接口时显示提示"""
        generator = ReportGenerator()
        results = [_make_result(has_signature=False)]
        report = _make_report(results=results)
        markdown = generator.render_markdown(report)

        assert "未检测到包含动态签名的接口" in markdown

    def test_contains_strategy_suggestions(self):
        """报告包含采集策略建议"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "## 采集策略建议" in markdown

    def test_contains_sample_file_reference(self):
        """报告包含样本文件引用"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "samples/req-001.json" in markdown

    def test_empty_results(self):
        """无接口结果时显示提示"""
        generator = ReportGenerator()
        report = _make_report(results=[])
        markdown = generator.render_markdown(report)

        assert "未发现业务接口" in markdown

    def test_generated_at_timestamp(self):
        """报告包含生成时间"""
        generator = ReportGenerator()
        report = _make_report()
        markdown = generator.render_markdown(report)

        assert "2024-01-15 12:00:00" in markdown


# ============================================================
# 单元测试：generate
# ============================================================


class TestGenerate:
    """测试 generate 方法"""

    def test_generates_report_file(self):
        """生成报告文件"""
        generator = ReportGenerator()
        report = _make_report()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "analysis")
            report_path = generator.generate(report, output_dir)

            assert os.path.exists(report_path)
            assert report_path.endswith("report.md")

            content = Path(report_path).read_text(encoding="utf-8")
            assert "# 接口分析报告" in content

    def test_creates_output_directory(self):
        """自动创建输出目录"""
        generator = ReportGenerator()
        report = _make_report()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "nested", "analysis")
            report_path = generator.generate(report, output_dir)

            assert os.path.exists(output_dir)
            assert os.path.exists(report_path)

    def test_returns_report_path(self):
        """返回报告文件路径"""
        generator = ReportGenerator()
        report = _make_report()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "analysis")
            report_path = generator.generate(report, output_dir)

            expected_path = os.path.join(output_dir, "report.md")
            assert report_path == expected_path
