"""ReplayController 单元测试

测试操作序列精简、回放执行引擎、目标接口捕获验证和重试逻辑。
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))

from src.device_controller import DeviceController, SequenceResult, StepResult
from src.models import (
    APIAnalysisResult,
    CapturedRequest,
    CrawlConfig,
    CrawlStats,
    CrawlTask,
    OperationSequence,
    OperationStep,
    ParameterInfo,
)
from src.replay_controller import ReplayController, ReplayResult
from src.traffic_interceptor import TrafficInterceptor


# ============================================================
# Fixtures
# ============================================================


def make_step(step_id: str, seq_id: str = "seq-1", action_type: str = "click") -> OperationStep:
    """创建测试用操作步骤"""
    return OperationStep(
        id=step_id,
        sequence_id=seq_id,
        action_type=action_type,
        target=None,
        parameters={"x": 100, "y": 200},
        status="pending",
        error_message=None,
    )


def make_sequence(steps: list[OperationStep], seq_id: str = "seq-1") -> OperationSequence:
    """创建测试用操作序列"""
    return OperationSequence(
        id=seq_id,
        app_package="com.example.app",
        intent_description="测试操作",
        steps=steps,
        created_at=datetime(2024, 1, 1),
    )


def make_api(request_id: str = "step-3", endpoint: str = "/api/v1/feed") -> APIAnalysisResult:
    """创建测试用 API 分析结果"""
    return APIAnalysisResult(
        request_id=request_id,
        endpoint=endpoint,
        purpose="获取信息流",
        parameters=[],
        reproducibility="complex",
        reproducibility_reason="包含动态签名",
        confidence=0.8,
    )


def make_captured_request(url: str = "https://api.example.com/api/v1/feed?page=1") -> CapturedRequest:
    """创建测试用捕获请求"""
    return CapturedRequest(
        id="req-001",
        timestamp=datetime.now(),
        operation_step_id="step-3",
        method="GET",
        url=url,
        headers={"Authorization": "Bearer token"},
        body=None,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=b'{"data": []}',
        is_decrypted=True,
    )


def make_crawl_task(api_id: str = "step-3", max_rounds: int = 3) -> CrawlTask:
    """创建测试用采集任务"""
    return CrawlTask(
        id="task-001",
        api_id=api_id,
        mode="replay",
        config=CrawlConfig(
            concurrency=1,
            interval_ms=100,
            max_rounds=max_rounds,
            failure_threshold=3,
            round_interval_ms=100,
        ),
        status="running",
        stats=CrawlStats(
            total_requests=0,
            success_count=0,
            failure_count=0,
            consecutive_failures=0,
            data_collected=0,
        ),
    )


def create_mock_controller() -> tuple[ReplayController, AsyncMock, AsyncMock]:
    """创建带 mock 依赖的 ReplayController"""
    device_ctrl = MagicMock(spec=DeviceController)
    interceptor = MagicMock(spec=TrafficInterceptor)

    # 设置异步方法
    device_ctrl.execute_sequence = AsyncMock()
    interceptor.get_captured_requests = AsyncMock(return_value=[])
    interceptor.clear = AsyncMock()

    controller = ReplayController(
        device_controller=device_ctrl,
        traffic_interceptor=interceptor,
    )
    return controller, device_ctrl, interceptor


# ============================================================
# 7.1 - 操作序列精简逻辑测试
# ============================================================


class TestGenerateReplaySequence:
    """测试操作序列精简逻辑"""

    @pytest.mark.asyncio
    async def test_trim_to_trigger_step(self):
        """应裁剪到触发目标 API 的步骤（含前置步骤）"""
        controller, _, _ = create_mock_controller()

        steps = [make_step(f"step-{i}") for i in range(1, 6)]
        sequence = make_sequence(steps)
        api = make_api(request_id="step-3")

        result = await controller.generate_replay_sequence(api, sequence)

        # 应包含 step-1, step-2, step-3（触发步骤及其前置）
        assert len(result.steps) == 3
        assert result.steps[0].id == "step-1"
        assert result.steps[1].id == "step-2"
        assert result.steps[2].id == "step-3"

    @pytest.mark.asyncio
    async def test_trim_with_start_step_id(self):
        """指定 start_step_id 时应从该步骤开始裁剪"""
        controller, _, _ = create_mock_controller()

        steps = [make_step(f"step-{i}") for i in range(1, 6)]
        sequence = make_sequence(steps)
        api = make_api(request_id="step-4")

        result = await controller.generate_replay_sequence(
            api, sequence, start_step_id="step-2"
        )

        # 应包含 step-2, step-3, step-4
        assert len(result.steps) == 3
        assert result.steps[0].id == "step-2"
        assert result.steps[1].id == "step-3"
        assert result.steps[2].id == "step-4"

    @pytest.mark.asyncio
    async def test_trigger_step_not_found_keeps_all(self):
        """找不到触发步骤时保留所有步骤（保守策略）"""
        controller, _, _ = create_mock_controller()

        steps = [make_step(f"step-{i}") for i in range(1, 4)]
        sequence = make_sequence(steps)
        api = make_api(request_id="nonexistent-step")

        result = await controller.generate_replay_sequence(api, sequence)

        # 保守策略：保留所有步骤
        assert len(result.steps) == 3

    @pytest.mark.asyncio
    async def test_empty_sequence(self):
        """空序列应返回空结果"""
        controller, _, _ = create_mock_controller()

        sequence = make_sequence([])
        api = make_api()

        result = await controller.generate_replay_sequence(api, sequence)

        assert len(result.steps) == 0

    @pytest.mark.asyncio
    async def test_replay_sequence_metadata(self):
        """精简后的序列应保留原始元数据并添加回放标记"""
        controller, _, _ = create_mock_controller()

        steps = [make_step("step-1")]
        sequence = make_sequence(steps)
        api = make_api(request_id="step-1")

        result = await controller.generate_replay_sequence(api, sequence)

        assert result.app_package == "com.example.app"
        assert "[回放]" in result.intent_description
        assert result.id.startswith("replay-")


# ============================================================
# 7.2 - 回放执行引擎测试
# ============================================================


class TestExecuteReplay:
    """测试回放执行引擎"""

    @pytest.mark.asyncio
    async def test_execute_all_rounds_success(self):
        """所有轮次成功时返回 completed 状态"""
        controller, device_ctrl, interceptor = create_mock_controller()

        api = make_api()
        steps = [make_step("step-3")]
        sequence = make_sequence(steps)
        await controller.generate_replay_sequence(api, sequence)

        # 模拟每轮都成功捕获
        captured_req = make_captured_request()
        interceptor.get_captured_requests = AsyncMock(return_value=[captured_req])
        device_ctrl.execute_sequence = AsyncMock(
            return_value=SequenceResult(
                sequence_id="seq-1", total_steps=1, completed_steps=1, failed_steps=0
            )
        )

        task = make_crawl_task(api_id="step-3", max_rounds=2)
        result = await controller.execute_replay(task)

        assert result.status == "completed"
        assert result.successful_rounds == 2
        assert result.failed_rounds == 0
        assert len(result.captured_data) == 2

    @pytest.mark.asyncio
    async def test_execute_with_failures(self):
        """部分轮次失败时返回 partial 状态"""
        controller, device_ctrl, interceptor = create_mock_controller()

        api = make_api()
        steps = [make_step("step-3")]
        sequence = make_sequence(steps)
        await controller.generate_replay_sequence(api, sequence)

        # 第一轮成功（第1次调用返回结果），
        # 第二轮失败（第2次调用返回空）+ 重试也失败（第3次调用返回空）
        captured_req = make_captured_request()
        call_count = [0]

        async def mock_get_requests():
            call_count[0] += 1
            # 只有第1次调用返回结果（第一轮首次尝试成功）
            if call_count[0] == 1:
                return [captured_req]
            return []

        interceptor.get_captured_requests = AsyncMock(side_effect=mock_get_requests)
        device_ctrl.execute_sequence = AsyncMock(
            return_value=SequenceResult(
                sequence_id="seq-1", total_steps=1, completed_steps=1, failed_steps=0
            )
        )

        task = make_crawl_task(api_id="step-3", max_rounds=2)
        result = await controller.execute_replay(task)

        assert result.status == "partial"
        assert result.successful_rounds == 1
        assert result.failed_rounds == 1

    @pytest.mark.asyncio
    async def test_execute_all_rounds_fail(self):
        """所有轮次失败时返回 failed 状态"""
        controller, device_ctrl, interceptor = create_mock_controller()

        api = make_api()
        steps = [make_step("step-3")]
        sequence = make_sequence(steps)
        await controller.generate_replay_sequence(api, sequence)

        # 所有轮次都不捕获目标接口
        interceptor.get_captured_requests = AsyncMock(return_value=[])
        device_ctrl.execute_sequence = AsyncMock(
            return_value=SequenceResult(
                sequence_id="seq-1", total_steps=1, completed_steps=1, failed_steps=0
            )
        )

        task = make_crawl_task(api_id="step-3", max_rounds=2)
        result = await controller.execute_replay(task)

        assert result.status == "failed"
        assert result.successful_rounds == 0
        assert result.failed_rounds == 2

    @pytest.mark.asyncio
    async def test_unregistered_api_returns_failed(self):
        """未注册的 API 应返回 failed"""
        controller, _, _ = create_mock_controller()

        task = make_crawl_task(api_id="unknown-api", max_rounds=1)
        result = await controller.execute_replay(task)

        assert result.status == "failed"
        assert result.total_rounds == 0


# ============================================================
# 7.3 - 目标接口捕获验证测试
# ============================================================


class TestTargetCaptureVerification:
    """测试目标接口捕获验证"""

    def test_matches_exact_path(self):
        """精确路径匹配"""
        controller, _, _ = create_mock_controller()
        api = make_api(endpoint="/api/v1/feed")
        request = make_captured_request(url="https://api.example.com/api/v1/feed")

        assert controller._matches_target_api(request, api) is True

    def test_matches_path_with_query(self):
        """带查询参数的路径匹配"""
        controller, _, _ = create_mock_controller()
        api = make_api(endpoint="/api/v1/feed")
        request = make_captured_request(
            url="https://api.example.com/api/v1/feed?page=1&size=20"
        )

        assert controller._matches_target_api(request, api) is True

    def test_no_match_different_path(self):
        """不同路径不匹配"""
        controller, _, _ = create_mock_controller()
        api = make_api(endpoint="/api/v1/feed")
        request = make_captured_request(
            url="https://api.example.com/api/v1/user/profile"
        )

        assert controller._matches_target_api(request, api) is False

    def test_matches_partial_path(self):
        """部分路径包含匹配"""
        controller, _, _ = create_mock_controller()
        api = make_api(endpoint="/v1/feed")
        request = make_captured_request(
            url="https://api.example.com/api/v1/feed/list"
        )

        assert controller._matches_target_api(request, api) is True

    def test_matches_without_leading_slash(self):
        """去除前导斜杠后匹配"""
        controller, _, _ = create_mock_controller()
        api = make_api(endpoint="api/v1/feed")
        request = make_captured_request(
            url="https://api.example.com/api/v1/feed"
        )

        assert controller._matches_target_api(request, api) is True


# ============================================================
# 7.4 - 重试和失败标记逻辑测试
# ============================================================


class TestRetryAndFailureMarking:
    """测试重试和失败标记逻辑"""

    def test_determine_status_all_success(self):
        """全部成功 -> completed"""
        controller, _, _ = create_mock_controller()
        result = ReplayResult(
            task_id="t1",
            total_rounds=3,
            successful_rounds=3,
            failed_rounds=0,
        )
        assert controller._determine_final_status(result) == "completed"

    def test_determine_status_all_failed(self):
        """全部失败 -> failed"""
        controller, _, _ = create_mock_controller()
        result = ReplayResult(
            task_id="t1",
            total_rounds=3,
            successful_rounds=0,
            failed_rounds=3,
        )
        assert controller._determine_final_status(result) == "failed"

    def test_determine_status_partial(self):
        """部分成功 -> partial"""
        controller, _, _ = create_mock_controller()
        result = ReplayResult(
            task_id="t1",
            total_rounds=3,
            successful_rounds=2,
            failed_rounds=1,
        )
        assert controller._determine_final_status(result) == "partial"

    def test_determine_status_zero_rounds(self):
        """零轮次 -> failed"""
        controller, _, _ = create_mock_controller()
        result = ReplayResult(
            task_id="t1",
            total_rounds=0,
            successful_rounds=0,
            failed_rounds=0,
        )
        assert controller._determine_final_status(result) == "failed"

    @pytest.mark.asyncio
    async def test_retry_on_first_failure(self):
        """首次失败后应重试一次"""
        controller, device_ctrl, interceptor = create_mock_controller()

        api = make_api()
        steps = [make_step("step-3")]
        sequence = make_sequence(steps)
        await controller.generate_replay_sequence(api, sequence)

        # 第一次调用返回空（失败），第二次返回结果（重试成功）
        captured_req = make_captured_request()
        call_count = [0]

        async def mock_get_requests():
            call_count[0] += 1
            if call_count[0] % 2 == 0:  # 偶数次调用返回结果（重试成功）
                return [captured_req]
            return []

        interceptor.get_captured_requests = AsyncMock(side_effect=mock_get_requests)
        device_ctrl.execute_sequence = AsyncMock(
            return_value=SequenceResult(
                sequence_id="seq-1", total_steps=1, completed_steps=1, failed_steps=0
            )
        )

        task = make_crawl_task(api_id="step-3", max_rounds=1)
        result = await controller.execute_replay(task)

        # 重试成功
        assert result.successful_rounds == 1
        assert result.failed_rounds == 0
        assert result.status == "completed"
