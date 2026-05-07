"""回放控制模块 - 对复杂接口通过设备操作重复触发采集

本模块实现 ReplayController 类，负责：
- 从完整操作序列中提取触发目标接口的最小操作子集（序列精简）
- 按轮次执行精简后的操作序列（回放执行引擎）
- 验证每轮执行后是否成功捕获目标接口请求
- 实现重试和失败标记逻辑
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from .device_controller import DeviceController
from .models import (
    APIAnalysisResult,
    CapturedRequest,
    CrawlTask,
    OperationSequence,
    OperationStep,
)
from .traffic_interceptor import TrafficInterceptor

logger = logging.getLogger(__name__)


@dataclass
class ReplayResult:
    """回放执行结果

    Attributes:
        task_id: 任务 ID
        total_rounds: 总轮次数
        successful_rounds: 成功轮次数（成功捕获目标接口）
        failed_rounds: 失败轮次数
        captured_data: 每轮成功捕获的请求数据列表
        status: 最终状态 - completed, failed, partial
    """

    task_id: str
    total_rounds: int
    successful_rounds: int
    failed_rounds: int
    captured_data: List[dict] = field(default_factory=list)
    status: str = "completed"  # completed, failed, partial


class ReplayController:
    """回放控制器

    对复杂接口（含动态签名/加密参数）通过设备操作重复触发采集。
    依赖 DeviceController 执行操作序列，依赖 TrafficInterceptor 捕获流量。

    使用示例:
        controller = ReplayController(
            device_controller=device_ctrl,
            traffic_interceptor=interceptor,
        )
        sequence = await controller.generate_replay_sequence(api, original_seq)
        result = await controller.execute_replay(task)
    """

    def __init__(
        self,
        device_controller: DeviceController,
        traffic_interceptor: TrafficInterceptor,
    ) -> None:
        """初始化 ReplayController。

        Args:
            device_controller: 设备操控器实例
            traffic_interceptor: 流量拦截器实例
        """
        self._device_controller = device_controller
        self._traffic_interceptor = traffic_interceptor
        # 存储 API 分析结果，用于回放时匹配目标接口
        self._api_registry: dict[str, APIAnalysisResult] = {}
        # 存储精简后的操作序列
        self._replay_sequences: dict[str, OperationSequence] = {}

    def register_api(self, api: APIAnalysisResult) -> None:
        """注册 API 分析结果，用于后续回放匹配。

        Args:
            api: 接口分析结果
        """
        self._api_registry[api.request_id] = api

    # ================================================================
    # 7.1 - 操作序列精简逻辑
    # ================================================================

    async def generate_replay_sequence(
        self,
        api: APIAnalysisResult,
        original_sequence: OperationSequence,
        start_step_id: Optional[str] = None,
    ) -> OperationSequence:
        """从完整操作序列中提取触发目标接口的最小子集。

        策略：找到触发目标 API 的步骤（通过 request_id 关联的
        operation_step_id），然后包含该步骤及其所有前置步骤
        （因为前置步骤可能是导航前提条件）。

        可选地通过 start_step_id 从序列开头进行裁剪。

        Args:
            api: 目标接口的分析结果
            original_sequence: 原始完整操作序列
            start_step_id: 可选的起始步骤 ID，用于从开头裁剪

        Returns:
            精简后的操作序列
        """
        steps = original_sequence.steps

        if not steps:
            # 空序列直接返回
            return self._create_trimmed_sequence(original_sequence, [])

        # 找到触发目标 API 的步骤索引
        trigger_step_index = self._find_trigger_step_index(api, steps)

        # 如果找不到触发步骤，保留所有步骤（保守策略）
        if trigger_step_index is None:
            trigger_step_index = len(steps) - 1

        # 确定起始索引
        start_index = 0
        if start_step_id is not None:
            for i, step in enumerate(steps):
                if step.id == start_step_id:
                    start_index = i
                    break

        # 提取从 start_index 到 trigger_step_index（含）的步骤
        trimmed_steps = steps[start_index : trigger_step_index + 1]

        # 创建精简后的序列
        replay_sequence = self._create_trimmed_sequence(
            original_sequence, trimmed_steps
        )

        # 注册 API 和序列
        self._api_registry[api.request_id] = api
        self._replay_sequences[api.request_id] = replay_sequence

        logger.info(
            f"生成回放序列: 原始 {len(steps)} 步 -> 精简 {len(trimmed_steps)} 步 "
            f"(API: {api.endpoint})"
        )

        return replay_sequence

    def _find_trigger_step_index(
        self, api: APIAnalysisResult, steps: List[OperationStep]
    ) -> Optional[int]:
        """查找触发目标 API 的步骤索引。

        通过 API 的 request_id 匹配步骤 ID（operation_step_id 关联）。

        Args:
            api: 目标接口分析结果
            steps: 操作步骤列表

        Returns:
            触发步骤的索引，未找到返回 None
        """
        # request_id 格式通常包含 step_id 信息
        # 尝试直接匹配步骤 ID
        for i, step in enumerate(steps):
            if step.id == api.request_id:
                return i

        # 如果没有直接匹配，返回 None（调用方会使用保守策略）
        return None

    def _create_trimmed_sequence(
        self,
        original: OperationSequence,
        trimmed_steps: List[OperationStep],
    ) -> OperationSequence:
        """创建精简后的操作序列。

        Args:
            original: 原始操作序列
            trimmed_steps: 精简后的步骤列表

        Returns:
            新的操作序列
        """
        return OperationSequence(
            id=f"replay-{original.id}-{uuid.uuid4().hex[:8]}",
            app_package=original.app_package,
            intent_description=f"[回放] {original.intent_description}",
            steps=trimmed_steps,
            created_at=datetime.now(),
        )

    # ================================================================
    # 7.2 - 回放执行引擎
    # ================================================================

    async def execute_replay(self, task: CrawlTask) -> ReplayResult:
        """执行回放采集任务。

        按配置的轮次数重复执行操作序列，每轮之间等待配置的间隔时间。
        使用 DeviceController 执行操作，TrafficInterceptor 捕获流量。

        Args:
            task: 采集任务（mode 应为 "replay"）

        Returns:
            ReplayResult 包含执行结果
        """
        max_rounds = task.config.max_rounds
        round_interval_ms = task.config.round_interval_ms

        # 获取目标 API 和回放序列
        api = self._api_registry.get(task.api_id)
        replay_sequence = self._replay_sequences.get(task.api_id)

        if api is None or replay_sequence is None:
            logger.error(f"未找到 API {task.api_id} 的注册信息或回放序列")
            return ReplayResult(
                task_id=task.id,
                total_rounds=0,
                successful_rounds=0,
                failed_rounds=0,
                captured_data=[],
                status="failed",
            )

        result = ReplayResult(
            task_id=task.id,
            total_rounds=max_rounds,
            successful_rounds=0,
            failed_rounds=0,
            captured_data=[],
            status="completed",
        )

        for round_num in range(max_rounds):
            logger.info(
                f"回放轮次 {round_num + 1}/{max_rounds} (API: {api.endpoint})"
            )

            # 执行单轮回放并验证捕获
            round_success, captured = await self._execute_single_round(
                api, replay_sequence
            )

            if round_success and captured:
                result.successful_rounds += 1
                result.captured_data.extend(captured)
            else:
                # 7.4 - 重试逻辑：失败后重试一次
                logger.info(
                    f"轮次 {round_num + 1} 未捕获目标接口，执行重试..."
                )
                retry_success, retry_captured = await self._execute_single_round(
                    api, replay_sequence
                )

                if retry_success and retry_captured:
                    result.successful_rounds += 1
                    result.captured_data.extend(retry_captured)
                else:
                    result.failed_rounds += 1
                    logger.warning(
                        f"轮次 {round_num + 1} 重试后仍未捕获目标接口"
                    )

            # 轮次间等待（最后一轮不需要等待）
            if round_num < max_rounds - 1 and round_interval_ms > 0:
                await asyncio.sleep(round_interval_ms / 1000.0)

        # 7.4 - 确定最终状态
        result.status = self._determine_final_status(result)

        logger.info(
            f"回放完成: {result.successful_rounds}/{result.total_rounds} 轮成功, "
            f"状态: {result.status}"
        )

        return result

    async def _execute_single_round(
        self,
        api: APIAnalysisResult,
        sequence: OperationSequence,
    ) -> tuple[bool, List[dict]]:
        """执行单轮回放并验证是否捕获目标接口。

        Args:
            api: 目标接口分析结果
            sequence: 回放操作序列

        Returns:
            (是否成功捕获, 捕获的数据列表)
        """
        # 清空之前的捕获记录
        try:
            await self._traffic_interceptor.clear()
        except RuntimeError:
            # 拦截器可能未运行，忽略
            pass

        # 执行操作序列
        seq_result = await self._device_controller.execute_sequence(sequence)

        logger.debug(
            f"操作序列执行完成: {seq_result.completed_steps}/{seq_result.total_steps} 步成功"
        )

        # 等待一小段时间让网络请求完成
        await asyncio.sleep(0.5)

        # 7.3 - 验证是否捕获到目标接口
        captured = await self._verify_target_capture(api)

        return len(captured) > 0, captured

    # ================================================================
    # 7.3 - 目标接口捕获验证
    # ================================================================

    async def _verify_target_capture(
        self, api: APIAnalysisResult
    ) -> List[dict]:
        """验证是否成功捕获目标接口请求。

        通过 URL 路径模式匹配来确认捕获的请求是否为目标接口。

        Args:
            api: 目标接口分析结果

        Returns:
            匹配的捕获数据列表（字典格式）
        """
        try:
            captured_requests = (
                await self._traffic_interceptor.get_captured_requests()
            )
        except RuntimeError:
            logger.warning("无法获取捕获的请求（拦截器可能未运行）")
            return []

        matched = []
        for request in captured_requests:
            if self._matches_target_api(request, api):
                matched.append(request.to_dict())

        if matched:
            logger.info(
                f"成功捕获目标接口 {api.endpoint}: {len(matched)} 条请求"
            )
        else:
            logger.debug(
                f"未捕获到目标接口 {api.endpoint} "
                f"(共 {len(captured_requests)} 条请求)"
            )

        return matched

    def _matches_target_api(
        self, request: CapturedRequest, api: APIAnalysisResult
    ) -> bool:
        """判断捕获的请求是否匹配目标接口。

        通过 URL 路径模式匹配：检查请求 URL 的路径部分是否包含
        目标接口的 endpoint。

        Args:
            request: 捕获的请求
            api: 目标接口分析结果

        Returns:
            是否匹配
        """
        try:
            parsed_url = urlparse(request.url)
            request_path = parsed_url.path

            # 目标 endpoint 可能是完整路径或部分路径
            target_endpoint = api.endpoint

            # 精确路径匹配或包含匹配
            if target_endpoint == request_path:
                return True
            if target_endpoint in request_path:
                return True

            # 去除前导斜杠后比较
            stripped_target = target_endpoint.lstrip("/")
            stripped_path = request_path.lstrip("/")
            if stripped_target and stripped_target in stripped_path:
                return True

        except Exception:
            pass

        return False

    # ================================================================
    # 7.4 - 重试和失败标记逻辑
    # ================================================================

    def _determine_final_status(self, result: ReplayResult) -> str:
        """根据执行结果确定最终状态。

        规则：
        - 所有轮次都成功 -> completed
        - 所有轮次都失败 -> failed
        - 部分成功部分失败 -> partial

        Args:
            result: 回放结果

        Returns:
            状态字符串
        """
        if result.total_rounds == 0:
            return "failed"
        if result.failed_rounds == 0:
            return "completed"
        if result.successful_rounds == 0:
            return "failed"
        return "partial"
