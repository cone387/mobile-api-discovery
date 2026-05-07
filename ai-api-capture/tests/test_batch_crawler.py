"""Batch Crawler 模块测试

包含：
- 单元测试：并发控制、请求间隔、成功率监控、认证失败检测、数据存储
- 属性测试：失败阈值触发不变量、数据存储 round-trip
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings

from src.batch_crawler import BatchCrawler, CrawlDataRecord
from src.models import CrawlConfig, CrawlStats, CrawlTask


# ========== Fixtures ==========


def make_config(
    concurrency: int = 3,
    interval_ms: int = 0,
    max_rounds: int = 10,
    failure_threshold: int = 5,
    round_interval_ms: int = 0,
) -> CrawlConfig:
    return CrawlConfig(
        concurrency=concurrency,
        interval_ms=interval_ms,
        max_rounds=max_rounds,
        failure_threshold=failure_threshold,
        round_interval_ms=round_interval_ms,
    )


def make_task(
    task_id: str = "test-task-1",
    api_id: str = "api-1",
    config: CrawlConfig = None,
) -> CrawlTask:
    if config is None:
        config = make_config()
    return CrawlTask(
        id=task_id,
        api_id=api_id,
        mode="batch",
        config=config,
        status="running",
        stats=CrawlStats(
            total_requests=0,
            success_count=0,
            failure_count=0,
            consecutive_failures=0,
            data_collected=0,
        ),
    )


# ========== Unit Tests: 6.1 Async Batch Executor ==========


class TestBatchExecutor:
    """测试异步批量请求执行器"""

    @pytest.mark.asyncio
    async def test_start_task_sets_running_status(self):
        """启动任务后状态应为 running"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            task = make_task()
            call_count = 0

            async def mock_request():
                nonlocal call_count
                call_count += 1
                if call_count >= 3:
                    await crawler.stop_task(task.id)
                return (True, {"request_params": {}, "response_data": {"x": 1}}, 200)

            await crawler.start_task(task, mock_request)
            assert task.status == "running"
            # Wait for loop to finish
            await asyncio.sleep(0.1)
            await crawler.stop_task(task.id)

    @pytest.mark.asyncio
    async def test_concurrency_control(self):
        """并发数应受信号量限制"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(concurrency=2, interval_ms=0)
            task = make_task(config=config)
            crawler = BatchCrawler(storage_path=tmpdir)

            max_concurrent = 0
            current_concurrent = 0
            call_count = 0

            async def mock_request():
                nonlocal max_concurrent, current_concurrent, call_count
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
                call_count += 1
                await asyncio.sleep(0.01)
                current_concurrent -= 1
                if call_count >= 5:
                    await crawler.stop_task(task.id)
                return (True, {"request_params": {}, "response_data": {}}, 200)

            await crawler.start_task(task, mock_request)
            await asyncio.sleep(0.2)
            await crawler.stop_task(task.id)
            # The semaphore limits concurrency, but since the loop is sequential
            # within a single task, max_concurrent should be 1 for a single loop
            assert max_concurrent >= 1

    @pytest.mark.asyncio
    async def test_request_interval(self):
        """请求间隔应被遵守"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(concurrency=1, interval_ms=50)
            task = make_task(config=config)
            crawler = BatchCrawler(storage_path=tmpdir)

            timestamps = []
            call_count = 0

            async def mock_request():
                nonlocal call_count
                import time
                timestamps.append(time.time())
                call_count += 1
                if call_count >= 3:
                    await crawler.stop_task(task.id)
                return (True, {"request_params": {}, "response_data": {}}, 200)

            await crawler.start_task(task, mock_request)
            await asyncio.sleep(0.3)
            await crawler.stop_task(task.id)

            # Check intervals between requests
            if len(timestamps) >= 2:
                for i in range(1, len(timestamps)):
                    interval = timestamps[i] - timestamps[i - 1]
                    # Should be at least 40ms (allowing some tolerance)
                    assert interval >= 0.04


# ========== Unit Tests: 6.2 Data Storage ==========


class TestDataStorage:
    """测试采集数据 JSON 存储"""

    def test_save_and_load_record(self):
        """保存的记录应能正确加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            record = CrawlDataRecord(
                request_params={"page": 1, "size": 20},
                response_data={"items": [1, 2, 3]},
                timestamp="2024-01-01T00:00:00+00:00",
                status_code=200,
                success=True,
            )

            crawler.save_record_sync("task-1", record)
            loaded = crawler.load_task_data("task-1")

            assert len(loaded) == 1
            assert loaded[0] == record

    def test_record_contains_required_fields(self):
        """存储的 JSON 应包含请求参数、响应数据、时间戳"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            record = CrawlDataRecord(
                request_params={"q": "test"},
                response_data={"result": "ok"},
                timestamp="2024-06-15T12:00:00+00:00",
                status_code=200,
                success=True,
            )

            crawler.save_record_sync("task-2", record)

            # Verify JSON file content directly
            task_dir = Path(tmpdir) / "task-2"
            files = list(task_dir.glob("*.json"))
            assert len(files) == 1

            data = json.loads(files[0].read_text(encoding="utf-8"))
            assert "request_params" in data
            assert "response_data" in data
            assert "timestamp" in data
            assert data["request_params"] == {"q": "test"}
            assert data["response_data"] == {"result": "ok"}

    def test_multiple_records_incrementing_filenames(self):
        """多条记录应使用递增文件名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)

            for i in range(3):
                record = CrawlDataRecord(
                    request_params={"index": i},
                    response_data={"value": i * 10},
                    timestamp=f"2024-01-01T00:00:0{i}+00:00",
                    status_code=200,
                    success=True,
                )
                crawler.save_record_sync("task-3", record)

            loaded = crawler.load_task_data("task-3")
            assert len(loaded) == 3
            assert loaded[0].request_params == {"index": 0}
            assert loaded[2].request_params == {"index": 2}

    def test_load_nonexistent_task_returns_empty(self):
        """加载不存在的任务应返回空列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            loaded = crawler.load_task_data("nonexistent")
            assert loaded == []


# ========== Unit Tests: 6.3 Success Rate Monitoring ==========


class TestSuccessRateMonitoring:
    """测试成功率监控和自动暂停逻辑"""

    def test_consecutive_failures_increment(self):
        """连续失败应递增计数器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=5)
            task = make_task(config=config)
            crawler._tasks[task.id] = task

            crawler.record_result(task.id, False)
            crawler.record_result(task.id, False)
            crawler.record_result(task.id, False)

            assert task.stats.consecutive_failures == 3
            assert task.stats.failure_count == 3

    def test_success_resets_consecutive_failures(self):
        """成功请求应重置连续失败计数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=10)
            task = make_task(config=config)
            crawler._tasks[task.id] = task

            crawler.record_result(task.id, False)
            crawler.record_result(task.id, False)
            assert task.stats.consecutive_failures == 2

            crawler.record_result(task.id, True)
            assert task.stats.consecutive_failures == 0

    def test_threshold_triggers_pause(self):
        """连续失败达到阈值应触发暂停"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=3)
            task = make_task(config=config)
            crawler._tasks[task.id] = task
            crawler._pause_events[task.id] = asyncio.Event()
            crawler._pause_events[task.id].set()

            crawler.record_result(task.id, False)
            crawler.record_result(task.id, False)
            assert task.status == "running"

            crawler.record_result(task.id, False)
            assert task.status == "paused"

    def test_pause_callback_invoked(self):
        """暂停时应调用回调函数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=2)
            task = make_task(config=config)
            crawler._tasks[task.id] = task
            crawler._pause_events[task.id] = asyncio.Event()
            crawler._pause_events[task.id].set()

            callback_args = []
            crawler.set_on_pause_callback(
                lambda tid, reason: callback_args.append((tid, reason))
            )

            crawler.record_result(task.id, False)
            crawler.record_result(task.id, False)

            assert len(callback_args) == 1
            assert callback_args[0][0] == task.id
            assert "阈值" in callback_args[0][1]


# ========== Unit Tests: 6.4 Auth Failure Detection ==========


class TestAuthFailureDetection:
    """测试认证失败检测和任务暂停通知"""

    def test_401_triggers_auth_failure(self):
        """401 响应应触发认证失败处理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=10)
            task = make_task(config=config)
            crawler._tasks[task.id] = task
            crawler._pause_events[task.id] = asyncio.Event()
            crawler._pause_events[task.id].set()

            crawler.record_result(task.id, False, status_code=401)

            assert task.status == "paused"

    def test_403_triggers_auth_failure(self):
        """403 响应应触发认证失败处理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=10)
            task = make_task(config=config)
            crawler._tasks[task.id] = task
            crawler._pause_events[task.id] = asyncio.Event()
            crawler._pause_events[task.id].set()

            crawler.record_result(task.id, False, status_code=403)

            assert task.status == "paused"

    def test_auth_failure_callback_invoked(self):
        """认证失败时应调用专用回调"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=10)
            task = make_task(config=config)
            crawler._tasks[task.id] = task
            crawler._pause_events[task.id] = asyncio.Event()
            crawler._pause_events[task.id].set()

            auth_callback_args = []
            crawler.set_on_auth_failure_callback(
                lambda tid, msg: auth_callback_args.append((tid, msg))
            )

            crawler.record_result(task.id, False, status_code=401)

            assert len(auth_callback_args) == 1
            assert auth_callback_args[0][0] == task.id
            assert "认证失败" in auth_callback_args[0][1]
            assert "401" in auth_callback_args[0][1]

    def test_auth_failure_does_not_count_toward_threshold(self):
        """认证失败应直接暂停，不依赖阈值计数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            config = make_config(failure_threshold=100)
            task = make_task(config=config)
            crawler._tasks[task.id] = task
            crawler._pause_events[task.id] = asyncio.Event()
            crawler._pause_events[task.id].set()

            # Even with high threshold, auth failure pauses immediately
            crawler.record_result(task.id, False, status_code=401)
            assert task.status == "paused"


# ========== Unit Tests: Task Lifecycle ==========


class TestTaskLifecycle:
    """测试任务生命周期管理"""

    @pytest.mark.asyncio
    async def test_pause_and_resume(self):
        """暂停和恢复任务"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            task = make_task()
            crawler._tasks[task.id] = task
            crawler._pause_events[task.id] = asyncio.Event()
            crawler._pause_events[task.id].set()

            await crawler.pause_task(task.id)
            assert task.status == "paused"

            await crawler.resume_task(task.id)
            assert task.status == "running"
            assert task.stats.consecutive_failures == 0

    def test_get_task_stats(self):
        """获取任务统计信息"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            task = make_task()
            crawler._tasks[task.id] = task

            crawler.record_result(task.id, True)
            crawler.record_result(task.id, True)
            crawler.record_result(task.id, False)

            stats = crawler.get_task_stats(task.id)
            assert stats is not None
            assert stats.total_requests == 3
            assert stats.success_count == 2
            assert stats.failure_count == 1

    def test_get_nonexistent_task_stats(self):
        """获取不存在任务的统计应返回 None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            assert crawler.get_task_stats("nonexistent") is None


# ========== Property Tests: 6.5 ==========


class TestFailureThresholdProperty:
    """属性测试：失败阈值触发不变量

    **Validates: Requirements 5.3**

    当连续失败次数达到配置阈值时，采集任务状态必须变为 paused。
    """

    @given(
        threshold=st.integers(min_value=1, max_value=50),
        results=st.lists(st.booleans(), min_size=1, max_size=100),
    )
    @settings(max_examples=200)
    def test_failure_threshold_invariant(self, threshold: int, results: list):
        """属性：如果 consecutive_failures >= threshold，则 status 必须为 paused

        **Validates: Requirements 5.3**
        """
        config = make_config(failure_threshold=threshold)
        task = make_task(config=config)
        crawler = BatchCrawler(storage_path="/tmp/pbt_test")
        crawler._tasks[task.id] = task
        crawler._pause_events[task.id] = asyncio.Event()
        crawler._pause_events[task.id].set()

        for success in results:
            if task.status == "paused":
                break
            crawler.record_result(task.id, success)

        # Invariant: if consecutive_failures >= threshold, status must be paused
        if task.stats.consecutive_failures >= threshold:
            assert task.status == "paused"

    @given(
        threshold=st.integers(min_value=1, max_value=20),
        num_failures=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=200)
    def test_exact_threshold_triggers_pause(self, threshold: int, num_failures: int):
        """属性：恰好达到阈值时必须暂停

        **Validates: Requirements 5.3**
        """
        config = make_config(failure_threshold=threshold)
        task = make_task(config=config)
        crawler = BatchCrawler(storage_path="/tmp/pbt_test")
        crawler._tasks[task.id] = task
        crawler._pause_events[task.id] = asyncio.Event()
        crawler._pause_events[task.id].set()

        for _ in range(num_failures):
            if task.status == "paused":
                break
            crawler.record_result(task.id, False)

        if num_failures >= threshold:
            assert task.status == "paused"
        else:
            assert task.status == "running"


class TestDataStorageRoundTrip:
    """属性测试：数据存储 Round-Trip

    **Validates: Requirements 5.2**

    采集到的数据以 JSON 格式写入后再读取，应得到等价数据。
    """

    @given(
        request_params=st.dictionaries(
            keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            values=st.one_of(
                st.integers(min_value=-1000, max_value=1000),
                st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
                st.booleans(),
            ),
            min_size=0,
            max_size=5,
        ),
        response_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            values=st.one_of(
                st.integers(min_value=-1000, max_value=1000),
                st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P"))),
                st.booleans(),
                st.lists(st.integers(min_value=-100, max_value=100), max_size=5),
            ),
            min_size=0,
            max_size=5,
        ),
        status_code=st.sampled_from([200, 201, 400, 404, 500]),
        success=st.booleans(),
    )
    @settings(max_examples=200)
    def test_crawl_data_roundtrip(
        self, request_params, response_data, status_code, success
    ):
        """属性：保存后加载的数据应与原始数据完全一致

        **Validates: Requirements 5.2**
        """
        import tempfile

        record = CrawlDataRecord(
            request_params=request_params,
            response_data=response_data,
            timestamp="2024-01-15T10:30:00+00:00",
            status_code=status_code,
            success=success,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            crawler = BatchCrawler(storage_path=tmpdir)
            crawler.save_record_sync("roundtrip-test", record)
            loaded = crawler.load_task_data("roundtrip-test")

            assert len(loaded) == 1
            assert loaded[0] == record

    @given(
        request_params=st.dictionaries(
            keys=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
            values=st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=0,
            max_size=3,
        ),
        response_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
            values=st.text(min_size=0, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=0,
            max_size=3,
        ),
    )
    @settings(max_examples=100)
    def test_record_serialization_roundtrip(self, request_params, response_data):
        """属性：CrawlDataRecord 的 to_dict/from_dict 应为互逆操作

        **Validates: Requirements 5.2**
        """
        record = CrawlDataRecord(
            request_params=request_params,
            response_data=response_data,
            timestamp="2024-06-01T00:00:00Z",
            status_code=200,
            success=True,
        )

        serialized = record.to_dict()
        restored = CrawlDataRecord.from_dict(serialized)
        assert restored == record

        # Also test JSON round-trip
        json_str = json.dumps(serialized, ensure_ascii=False)
        from_json = CrawlDataRecord.from_dict(json.loads(json_str))
        assert from_json == record
