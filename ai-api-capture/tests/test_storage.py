"""数据存储层测试"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.storage import Storage
from src.models import (
    CapturedRequest,
    APIAnalysisResult,
    GeneratedCode,
    CrawlTask,
    CrawlConfig,
    CrawlStats,
    ParameterInfo,
)


@pytest.fixture
async def storage(tmp_path):
    """创建临时目录中的 Storage 实例"""
    s = Storage(base_dir=str(tmp_path / "output"))
    await s.initialize()
    yield s
    await s.close()


def make_captured_request(
    request_id: str = "req-001",
    step_id: str = "step-001",
) -> CapturedRequest:
    """创建测试用 CapturedRequest"""
    return CapturedRequest(
        id=request_id,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        operation_step_id=step_id,
        method="GET",
        url="https://api.example.com/feed",
        headers={"Authorization": "Bearer token123"},
        body=None,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=b'{"items": []}',
        is_decrypted=True,
    )


def make_analysis_result(
    request_id: str = "req-001",
    reproducibility: str = "reproducible",
    purpose: str = "feed",
) -> APIAnalysisResult:
    """创建测试用 APIAnalysisResult"""
    return APIAnalysisResult(
        request_id=request_id,
        endpoint="/api/feed",
        purpose=purpose,
        parameters=[
            ParameterInfo(
                name="page",
                value_sample="1",
                category="static",
                source="query",
                reasoning="固定分页参数",
            )
        ],
        reproducibility=reproducibility,
        reproducibility_reason="所有参数均为静态或会话类型",
        confidence=0.95,
    )


def make_generated_code(api_id: str = "req-001") -> GeneratedCode:
    """创建测试用 GeneratedCode"""
    return GeneratedCode(
        api_id=api_id,
        code='import requests\n\ndef fetch_feed():\n    pass\n',
        session_params=["token"],
        verification_status="pending",
        failure_reason=None,
    )


def make_crawl_task(
    task_id: str = "task-001",
    api_id: str = "req-001",
    status: str = "running",
) -> CrawlTask:
    """创建测试用 CrawlTask"""
    return CrawlTask(
        id=task_id,
        api_id=api_id,
        mode="batch",
        config=CrawlConfig(
            concurrency=5,
            interval_ms=1000,
            max_rounds=10,
            failure_threshold=3,
            round_interval_ms=5000,
        ),
        status=status,
        stats=CrawlStats(
            total_requests=0,
            success_count=0,
            failure_count=0,
            consecutive_failures=0,
            data_collected=0,
        ),
    )


# ========== 初始化测试 ==========


class TestStorageInitialization:
    async def test_creates_directories(self, storage, tmp_path):
        """初始化时应创建所有输出目录"""
        output_dir = tmp_path / "output"
        assert (output_dir / "captures").exists()
        assert (output_dir / "analysis").exists()
        assert (output_dir / "generated").exists()
        assert (output_dir / "data").exists()

    async def test_creates_database(self, storage, tmp_path):
        """初始化时应创建 SQLite 数据库"""
        assert (tmp_path / "output" / "index.db").exists()


# ========== CapturedRequest 存储测试 ==========


class TestCapturedRequestStorage:
    async def test_save_and_load_request(self, storage):
        """保存后应能正确加载 CapturedRequest"""
        request = make_captured_request()
        await storage.save_request(request)
        loaded = await storage.load_request("req-001")
        assert loaded == request

    async def test_load_nonexistent_request(self, storage):
        """加载不存在的请求应返回 None"""
        loaded = await storage.load_request("nonexistent")
        assert loaded is None

    async def test_save_requests_batch(self, storage):
        """批量保存应正确存储所有请求"""
        requests = [
            make_captured_request(request_id=f"req-{i:03d}")
            for i in range(3)
        ]
        await storage.save_requests(requests)
        all_loaded = await storage.load_all_requests()
        assert len(all_loaded) == 3

    async def test_load_all_requests(self, storage):
        """load_all_requests 应返回所有已保存的请求"""
        for i in range(5):
            await storage.save_request(
                make_captured_request(request_id=f"req-{i:03d}")
            )
        all_requests = await storage.load_all_requests()
        assert len(all_requests) == 5

    async def test_request_json_file_content(self, storage, tmp_path):
        """JSON 文件内容应为有效的序列化数据"""
        request = make_captured_request()
        await storage.save_request(request)
        file_path = tmp_path / "output" / "captures" / "req-001.json"
        assert file_path.exists()
        data = json.loads(file_path.read_text(encoding="utf-8"))
        assert data["id"] == "req-001"
        assert data["method"] == "GET"


# ========== APIAnalysisResult 存储测试 ==========


class TestAnalysisStorage:
    async def test_save_and_load_analysis(self, storage):
        """保存后应能正确加载 APIAnalysisResult"""
        analysis = make_analysis_result()
        await storage.save_analysis(analysis)
        loaded = await storage.load_analysis("req-001")
        assert loaded == analysis

    async def test_load_nonexistent_analysis(self, storage):
        """加载不存在的分析结果应返回 None"""
        loaded = await storage.load_analysis("nonexistent")
        assert loaded is None

    async def test_save_analyses_batch(self, storage):
        """批量保存分析结果"""
        analyses = [
            make_analysis_result(request_id=f"req-{i:03d}")
            for i in range(3)
        ]
        await storage.save_analyses(analyses)
        all_loaded = await storage.load_all_analyses()
        assert len(all_loaded) == 3

    async def test_analysis_updates_request_reproducibility(self, storage):
        """保存分析结果时应更新 requests 表的 reproducibility"""
        request = make_captured_request()
        await storage.save_request(request)
        analysis = make_analysis_result(reproducibility="reproducible")
        await storage.save_analysis(analysis)
        # 通过 reproducibility 查询应能找到该请求
        results = await storage.get_requests_by_reproducibility("reproducible")
        assert len(results) == 1
        assert results[0].id == "req-001"


# ========== GeneratedCode 存储测试 ==========


class TestGeneratedCodeStorage:
    async def test_save_and_load_generated_code(self, storage):
        """保存后应能正确加载 GeneratedCode"""
        code = make_generated_code()
        await storage.save_generated_code(code)
        loaded = await storage.load_generated_code("req-001")
        assert loaded == code

    async def test_load_nonexistent_generated_code(self, storage):
        """加载不存在的生成代码应返回 None"""
        loaded = await storage.load_generated_code("nonexistent")
        assert loaded is None

    async def test_save_generated_codes_batch(self, storage):
        """批量保存生成代码"""
        codes = [make_generated_code(api_id=f"api-{i:03d}") for i in range(3)]
        await storage.save_generated_codes(codes)
        all_loaded = await storage.load_all_generated_codes()
        assert len(all_loaded) == 3


# ========== CrawlTask 存储测试 ==========


class TestCrawlTaskStorage:
    async def test_save_and_load_crawl_task(self, storage):
        """保存后应能正确加载 CrawlTask"""
        task = make_crawl_task()
        await storage.save_crawl_task(task)
        loaded = await storage.load_crawl_task("task-001")
        assert loaded == task

    async def test_load_nonexistent_crawl_task(self, storage):
        """加载不存在的采集任务应返回 None"""
        loaded = await storage.load_crawl_task("nonexistent")
        assert loaded is None

    async def test_save_crawl_tasks_batch(self, storage):
        """批量保存采集任务"""
        tasks = [
            make_crawl_task(task_id=f"task-{i:03d}") for i in range(3)
        ]
        await storage.save_crawl_tasks(tasks)
        all_loaded = await storage.load_all_crawl_tasks()
        assert len(all_loaded) == 3


# ========== 采集数据存储测试 ==========


class TestCrawlDataStorage:
    async def test_save_and_load_crawl_data(self, storage):
        """保存后应能正确加载采集数据"""
        data = {"response": {"items": [1, 2, 3]}, "timestamp": "2024-01-15T10:30:00"}
        await storage.save_crawl_data("task-001", data)
        loaded = await storage.load_crawl_data("task-001")
        assert len(loaded) == 1
        assert loaded[0] == data

    async def test_save_crawl_data_batch(self, storage):
        """批量保存采集数据"""
        data_list = [
            {"index": i, "value": f"data-{i}"} for i in range(5)
        ]
        await storage.save_crawl_data_batch("task-001", data_list)
        loaded = await storage.load_crawl_data("task-001")
        assert len(loaded) == 5

    async def test_load_crawl_data_empty(self, storage):
        """加载不存在的任务数据应返回空列表"""
        loaded = await storage.load_crawl_data("nonexistent")
        assert loaded == []

    async def test_crawl_data_ordering(self, storage):
        """采集数据应按保存顺序加载"""
        for i in range(3):
            await storage.save_crawl_data("task-001", {"index": i})
        loaded = await storage.load_crawl_data("task-001")
        assert [d["index"] for d in loaded] == [0, 1, 2]


# ========== SQLite 查询测试 ==========


class TestSQLiteQueries:
    async def test_get_requests_by_reproducibility(self, storage):
        """按可复现性查询请求"""
        # 保存请求和分析结果
        for i in range(3):
            req = make_captured_request(request_id=f"req-{i:03d}")
            await storage.save_request(req)
        await storage.save_analysis(
            make_analysis_result(request_id="req-000", reproducibility="reproducible")
        )
        await storage.save_analysis(
            make_analysis_result(request_id="req-001", reproducibility="complex")
        )
        await storage.save_analysis(
            make_analysis_result(request_id="req-002", reproducibility="reproducible")
        )

        reproducible = await storage.get_requests_by_reproducibility("reproducible")
        assert len(reproducible) == 2

        complex_reqs = await storage.get_requests_by_reproducibility("complex")
        assert len(complex_reqs) == 1

    async def test_get_requests_by_step_id(self, storage):
        """按操作步骤 ID 查询请求"""
        await storage.save_request(
            make_captured_request(request_id="req-001", step_id="step-A")
        )
        await storage.save_request(
            make_captured_request(request_id="req-002", step_id="step-A")
        )
        await storage.save_request(
            make_captured_request(request_id="req-003", step_id="step-B")
        )

        step_a_requests = await storage.get_requests_by_step_id("step-A")
        assert len(step_a_requests) == 2

        step_b_requests = await storage.get_requests_by_step_id("step-B")
        assert len(step_b_requests) == 1

    async def test_get_analyses_by_reproducibility(self, storage):
        """按可复现性查询分析结果"""
        await storage.save_analysis(
            make_analysis_result(request_id="req-001", reproducibility="reproducible")
        )
        await storage.save_analysis(
            make_analysis_result(request_id="req-002", reproducibility="complex")
        )

        reproducible = await storage.get_analyses_by_reproducibility("reproducible")
        assert len(reproducible) == 1
        assert reproducible[0].request_id == "req-001"

    async def test_get_analyses_by_purpose(self, storage):
        """按接口用途查询分析结果"""
        await storage.save_analysis(
            make_analysis_result(request_id="req-001", purpose="feed")
        )
        await storage.save_analysis(
            make_analysis_result(request_id="req-002", purpose="user")
        )
        await storage.save_analysis(
            make_analysis_result(request_id="req-003", purpose="feed")
        )

        feed_analyses = await storage.get_analyses_by_purpose("feed")
        assert len(feed_analyses) == 2

        user_analyses = await storage.get_analyses_by_purpose("user")
        assert len(user_analyses) == 1

    async def test_get_crawl_tasks_by_status(self, storage):
        """按状态查询采集任务"""
        await storage.save_crawl_task(
            make_crawl_task(task_id="task-001", status="running")
        )
        await storage.save_crawl_task(
            make_crawl_task(task_id="task-002", status="completed")
        )
        await storage.save_crawl_task(
            make_crawl_task(task_id="task-003", status="running")
        )

        running = await storage.get_crawl_tasks_by_status("running")
        assert len(running) == 2

        completed = await storage.get_crawl_tasks_by_status("completed")
        assert len(completed) == 1

    async def test_get_crawl_tasks_by_api_id(self, storage):
        """按接口 ID 查询采集任务"""
        await storage.save_crawl_task(
            make_crawl_task(task_id="task-001", api_id="api-A")
        )
        await storage.save_crawl_task(
            make_crawl_task(task_id="task-002", api_id="api-A")
        )
        await storage.save_crawl_task(
            make_crawl_task(task_id="task-003", api_id="api-B")
        )

        api_a_tasks = await storage.get_crawl_tasks_by_api_id("api-A")
        assert len(api_a_tasks) == 2

        api_b_tasks = await storage.get_crawl_tasks_by_api_id("api-B")
        assert len(api_b_tasks) == 1
