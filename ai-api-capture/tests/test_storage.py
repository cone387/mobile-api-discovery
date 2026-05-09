"""数据存储层测试

测试 Storage 类的 JSON 文件读写功能：
- CapturedRequest 的增量写入和批量读取
- APIAnalysisResult 的存储和加载
- Samples 文件的保存和加载
- AnalysisReport 的存储和加载
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.storage import Storage
from src.models import (
    CapturedRequest,
    APIAnalysisResult,
    APIType,
    ParameterInfo,
    CaptureTarget,
    DataLink,
    AnalysisReport,
)


@pytest.fixture
def storage(tmp_path):
    """创建临时目录中的 Storage 实例"""
    s = Storage(base_dir=str(tmp_path / "output"))
    s.initialize()
    return s


def make_captured_request(
    request_id: str = "req-001",
) -> CapturedRequest:
    """创建测试用 CapturedRequest"""
    return CapturedRequest(
        id=request_id,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        method="GET",
        url="https://api.example.com/feed",
        headers={"Authorization": "Bearer token123"},
        body=None,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"items": []}',
        is_decrypted=True,
    )


def make_analysis_result(
    request_id: str = "req-001",
    api_type: APIType = APIType.LIST,
) -> APIAnalysisResult:
    """创建测试用 APIAnalysisResult"""
    return APIAnalysisResult(
        request_id=request_id,
        endpoint="/api/feed",
        api_type=api_type,
        parameters=[
            ParameterInfo(
                name="page",
                value_sample="1",
                category="static",
                source="query",
            )
        ],
        has_signature=False,
        signature_fields=[],
        matches_target=True,
        call_count=3,
    )


# ========== 初始化测试 ==========


class TestStorageInitialization:
    def test_creates_directories(self, storage, tmp_path):
        """初始化时应创建所有输出目录"""
        output_dir = tmp_path / "output"
        assert (output_dir / "captures").exists()
        assert (output_dir / "analysis").exists()
        assert (output_dir / "analysis" / "samples").exists()

    def test_initialize_idempotent(self, storage):
        """多次初始化不应报错"""
        storage.initialize()
        storage.initialize()


# ========== CapturedRequest 存储测试 ==========


class TestCapturedRequestStorage:
    def test_save_and_load_request(self, storage):
        """保存后应能正确加载 CapturedRequest"""
        request = make_captured_request()
        storage.save_request(request)
        loaded = storage.load_request("req-001")
        assert loaded == request

    def test_load_nonexistent_request(self, storage):
        """加载不存在的请求应返回 None"""
        loaded = storage.load_request("nonexistent")
        assert loaded is None

    def test_save_requests_batch(self, storage):
        """批量保存应正确存储所有请求"""
        requests = [
            make_captured_request(request_id=f"req-{i:03d}")
            for i in range(3)
        ]
        storage.save_requests(requests)
        all_loaded = storage.load_all_requests()
        assert len(all_loaded) == 3

    def test_load_all_requests(self, storage):
        """load_all_requests 应返回所有已保存的请求"""
        for i in range(5):
            storage.save_request(
                make_captured_request(request_id=f"req-{i:03d}")
            )
        all_requests = storage.load_all_requests()
        assert len(all_requests) == 5

    def test_request_json_file_content(self, storage, tmp_path):
        """JSON 文件内容应为有效的序列化数据"""
        request = make_captured_request()
        storage.save_request(request)
        file_path = tmp_path / "output" / "captures" / "req-001.json"
        assert file_path.exists()
        data = json.loads(file_path.read_text(encoding="utf-8"))
        assert data["id"] == "req-001"
        assert data["method"] == "GET"

    def test_incremental_write(self, storage):
        """每个请求应保存为独立 JSON 文件（增量写入）"""
        storage.save_request(make_captured_request(request_id="req-001"))
        assert storage.get_request_count() == 1

        storage.save_request(make_captured_request(request_id="req-002"))
        assert storage.get_request_count() == 2

        storage.save_request(make_captured_request(request_id="req-003"))
        assert storage.get_request_count() == 3

    def test_get_request_count_empty(self, storage):
        """空存储应返回 0"""
        assert storage.get_request_count() == 0


# ========== APIAnalysisResult 存储测试 ==========


class TestAnalysisStorage:
    def test_save_and_load_analysis(self, storage):
        """保存后应能正确加载 APIAnalysisResult"""
        analysis = make_analysis_result()
        storage.save_analysis(analysis)
        loaded = storage.load_analysis("req-001")
        assert loaded == analysis

    def test_load_nonexistent_analysis(self, storage):
        """加载不存在的分析结果应返回 None"""
        loaded = storage.load_analysis("nonexistent")
        assert loaded is None

    def test_save_analyses_batch(self, storage):
        """批量保存分析结果"""
        analyses = [
            make_analysis_result(request_id=f"req-{i:03d}")
            for i in range(3)
        ]
        storage.save_analyses(analyses)
        all_loaded = storage.load_all_analyses()
        assert len(all_loaded) == 3

    def test_analysis_preserves_api_type(self, storage):
        """保存和加载应保留 APIType 枚举值"""
        for api_type in APIType:
            analysis = make_analysis_result(
                request_id=f"req-{api_type.value}",
                api_type=api_type,
            )
            storage.save_analysis(analysis)
            loaded = storage.load_analysis(f"req-{api_type.value}")
            assert loaded.api_type == api_type


# ========== Samples 存储测试 ==========


class TestSamplesStorage:
    def test_save_and_load_sample(self, storage):
        """保存后应能正确加载样本"""
        request_data = {
            "method": "GET",
            "url": "https://api.example.com/feed",
            "headers": {"Authorization": "Bearer token"},
        }
        response_data = {
            "status": 200,
            "body": {"items": [{"id": 1, "name": "test"}]},
        }
        rel_path = storage.save_sample("req-001", request_data, response_data)
        assert rel_path == "samples/req-001.json"

        loaded = storage.load_sample("req-001")
        assert loaded is not None
        assert loaded["request"] == request_data
        assert loaded["response"] == response_data

    def test_load_nonexistent_sample(self, storage):
        """加载不存在的样本应返回 None"""
        loaded = storage.load_sample("nonexistent")
        assert loaded is None

    def test_sample_file_location(self, storage, tmp_path):
        """样本文件应保存在 output/analysis/samples/ 目录"""
        storage.save_sample("req-001", {"method": "GET"}, {"status": 200})
        file_path = tmp_path / "output" / "analysis" / "samples" / "req-001.json"
        assert file_path.exists()


# ========== AnalysisReport 存储测试 ==========


class TestReportStorage:
    def test_save_and_load_report(self, storage):
        """保存后应能正确加载分析报告"""
        report = AnalysisReport(
            target=CaptureTarget(
                app_name="TestApp",
                target_data="列表数据",
                operation_pages="首页",
            ),
            results=[make_analysis_result()],
            data_links=[
                DataLink(
                    source_endpoint="/api/list",
                    target_endpoint="/api/detail",
                    link_field="id",
                    link_type="list_to_detail",
                )
            ],
            total_captured=100,
            total_analyzed=10,
            target_matched=3,
            generated_at=datetime(2024, 1, 15, 12, 0, 0),
        )
        storage.save_report(report)
        loaded = storage.load_report()
        assert loaded == report

    def test_load_nonexistent_report(self, storage):
        """加载不存在的报告应返回 None"""
        loaded = storage.load_report()
        assert loaded is None

    def test_save_report_custom_filename(self, storage):
        """支持自定义报告文件名"""
        report = AnalysisReport(
            target=CaptureTarget(app_name="App", target_data="data", operation_pages="pages"),
            results=[],
            data_links=[],
            total_captured=0,
            total_analyzed=0,
            target_matched=0,
            generated_at=datetime(2024, 1, 1, 0, 0, 0),
        )
        storage.save_report(report, filename="custom_report.json")
        loaded = storage.load_report(filename="custom_report.json")
        assert loaded == report
