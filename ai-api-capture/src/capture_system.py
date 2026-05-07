"""主协调器 - 串联三阶段流程、管理模块生命周期

CaptureSystem 是系统的顶层协调器，负责：
- 阶段 1: 设备操控与流量捕获（Device_Controller + Traffic_Interceptor）
- 阶段 2: 接口分析与分类（API_Analyzer + Code_Generator）
- 阶段 3: 分路径数据采集（Batch_Crawler / Replay_Controller）
- 模块生命周期管理（启动、停止、资源清理）
- 汇总报告生成
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from src.api_analyzer import APIAnalyzer
from src.batch_crawler import BatchCrawler
from src.code_generator import CodeGenerator
from src.device_controller import DeviceController
from src.models import (
    APIAnalysisResult,
    CapturedRequest,
    CrawlConfig,
    CrawlStats,
    CrawlTask,
    GeneratedCode,
    OperationSequence,
)
from src.replay_controller import ReplayController
from src.report_generator import ReportGenerator, SummaryReport
from src.traffic_interceptor import ProxyConfig, TrafficInterceptor

logger = logging.getLogger(__name__)


@dataclass
class CaptureSystemConfig:
    """系统配置"""

    # 代理配置
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8080
    storage_path: str = "./output/captures"

    # 采集配置
    crawl_concurrency: int = 3
    crawl_interval_ms: int = 500
    crawl_failure_threshold: int = 5
    crawl_max_rounds: int = 10
    crawl_round_interval_ms: int = 3000

    # 输出配置
    output_dir: str = "./output"
    report_path: str = "./output/analysis/report.md"

    # 代码生成配置
    template_dir: Optional[str] = None
    verify_timeout: int = 30


class CaptureSystem:
    """主协调器 - 串联三阶段流程、管理模块生命周期

    使用示例:
        config = CaptureSystemConfig(proxy_port=8080)
        system = CaptureSystem(config)

        # 执行完整流程
        report = await system.run_capture(
            app_package="com.example.app",
            device_id="emulator-5554",
            operations=operation_sequence,
        )

        # 或分阶段执行
        await system.start()
        await system.run_phase1_capture(app_package, device_id, operations)
        analyses = await system.run_analysis()
        await system.run_collection(analyses)
        await system.stop()
    """

    def __init__(self, config: CaptureSystemConfig) -> None:
        """初始化 CaptureSystem

        Args:
            config: 系统配置
        """
        self._config = config

        # 初始化各模块
        self._device_controller = DeviceController()
        self._traffic_interceptor = TrafficInterceptor()
        self._api_analyzer = APIAnalyzer()
        self._code_generator = CodeGenerator(
            template_dir=config.template_dir,
            verify_timeout=config.verify_timeout,
        )
        self._batch_crawler = BatchCrawler(
            storage_path=f"{config.output_dir}/data"
        )
        self._replay_controller = ReplayController(
            device_controller=self._device_controller,
            traffic_interceptor=self._traffic_interceptor,
        )
        self._report_generator = ReportGenerator()

        # 状态
        self._started = False
        self._captured_requests: List[CapturedRequest] = []
        self._analyses: List[APIAnalysisResult] = []
        self._generated_codes: dict[str, GeneratedCode] = {}

    @property
    def is_started(self) -> bool:
        """系统是否已启动"""
        return self._started

    @property
    def device_controller(self) -> DeviceController:
        """获取设备控制器实例"""
        return self._device_controller

    @property
    def traffic_interceptor(self) -> TrafficInterceptor:
        """获取流量拦截器实例"""
        return self._traffic_interceptor

    @property
    def report_generator(self) -> ReportGenerator:
        """获取报告生成器实例"""
        return self._report_generator

    async def start(self) -> None:
        """启动系统，初始化各模块

        启动流量拦截器代理服务器。

        Raises:
            RuntimeError: 如果系统已启动
        """
        if self._started:
            raise RuntimeError("CaptureSystem is already started")

        logger.info("启动 CaptureSystem...")

        # 启动流量拦截器
        proxy_config = ProxyConfig(
            listen_host=self._config.proxy_host,
            listen_port=self._config.proxy_port,
            storage_path=self._config.storage_path,
        )
        await self._traffic_interceptor.start(proxy_config)

        self._started = True
        logger.info("CaptureSystem 启动完成")

    async def stop(self) -> None:
        """停止系统，清理资源

        停止流量拦截器并断开设备连接。

        Raises:
            RuntimeError: 如果系统未启动
        """
        if not self._started:
            raise RuntimeError("CaptureSystem is not started")

        logger.info("停止 CaptureSystem...")

        # 停止流量拦截器
        try:
            await self._traffic_interceptor.stop()
        except RuntimeError:
            pass  # 可能已经停止

        # 断开设备连接
        try:
            await self._device_controller.disconnect()
        except Exception:
            pass  # 可能未连接

        self._started = False
        logger.info("CaptureSystem 已停止")

    async def run_capture(
        self,
        app_package: str,
        device_id: str,
        operations: OperationSequence,
    ) -> SummaryReport:
        """执行完整的三阶段流程

        阶段 1: 设备操控与流量捕获
        阶段 2: 接口分析与分类
        阶段 3: 分路径数据采集

        Args:
            app_package: 目标 App 包名
            device_id: 设备标识
            operations: 操作序列

        Returns:
            SummaryReport 汇总报告
        """
        try:
            # 启动系统
            await self.start()

            # 阶段 1: 捕获
            await self._run_phase1_capture(app_package, device_id, operations)

            # 阶段 2: 分析
            analyses = await self.run_analysis()

            # 阶段 3: 采集
            await self.run_collection(analyses)

            # 生成报告
            report = self._report_generator.generate_summary(analyses)
            self._report_generator.save_report(report, self._config.report_path)

            logger.info(
                f"流程完成: 共 {report.total_count} 个接口, "
                f"{report.reproducible_count} 个可复现, "
                f"{report.complex_count} 个复杂接口"
            )

            return report

        finally:
            # 确保资源清理
            if self._started:
                await self.stop()

    async def _run_phase1_capture(
        self,
        app_package: str,
        device_id: str,
        operations: OperationSequence,
    ) -> None:
        """阶段 1: 设备操控与流量捕获

        连接设备、启动 App、执行操作序列、捕获流量。

        Args:
            app_package: 目标 App 包名
            device_id: 设备标识
            operations: 操作序列
        """
        logger.info(f"阶段 1: 设备操控与流量捕获 (App: {app_package})")

        # 连接设备
        connection_result = await self._device_controller.connect(device_id)
        if not connection_result.success:
            raise RuntimeError(
                f"设备连接失败: {connection_result.error_message} "
                f"(设备: {device_id})"
            )

        # 启动 App
        app_launched = await self._device_controller.launch_app(app_package)
        if not app_launched:
            raise RuntimeError(f"App 启动失败: {app_package}")

        # 执行操作序列，同步更新步骤 ID
        for step in operations.steps:
            self._traffic_interceptor.set_step_id(step.id)
            await self._device_controller.execute_step(step)

        # 清除步骤 ID
        self._traffic_interceptor.set_step_id(None)

        # 获取捕获的请求
        self._captured_requests = (
            await self._traffic_interceptor.get_captured_requests()
        )

        logger.info(f"阶段 1 完成: 捕获 {len(self._captured_requests)} 个请求")

    async def run_analysis(self) -> List[APIAnalysisResult]:
        """阶段 2: 接口分析与分类

        对捕获的请求进行分析，判定可复现性，为可复现接口生成代码。

        Returns:
            分析结果列表
        """
        logger.info("阶段 2: 接口分析与分类")

        # 批量分析
        self._analyses = await self._api_analyzer.analyze_batch(
            self._captured_requests
        )

        # 为可复现接口生成代码
        for analysis in self._analyses:
            if analysis.reproducibility == "reproducible":
                # 找到对应的原始请求
                request = self._find_request(analysis.request_id)
                if request:
                    generated = self._code_generator.generate(analysis, request)
                    self._generated_codes[analysis.request_id] = generated

        logger.info(
            f"阶段 2 完成: {len(self._analyses)} 个接口已分析, "
            f"{len(self._generated_codes)} 个代码已生成"
        )

        return self._analyses

    async def run_collection(self, analyses: List[APIAnalysisResult]) -> None:
        """阶段 3: 分路径数据采集

        根据分析结果，对可复现接口使用批量采集，对复杂接口使用回放采集。

        Args:
            analyses: 分析结果列表
        """
        logger.info("阶段 3: 分路径数据采集")

        for analysis in analyses:
            if analysis.reproducibility == "reproducible":
                # 可复现接口 -> 批量采集
                generated = self._generated_codes.get(analysis.request_id)
                if generated and generated.verification_status != "failed":
                    await self._start_batch_crawl(analysis, generated)
            elif analysis.reproducibility == "complex":
                # 复杂接口 -> 回放采集
                self._replay_controller.register_api(analysis)

        logger.info("阶段 3 完成")

    async def _start_batch_crawl(
        self, analysis: APIAnalysisResult, generated: GeneratedCode
    ) -> None:
        """为可复现接口启动批量采集任务

        Args:
            analysis: 接口分析结果
            generated: 生成的代码
        """
        config = CrawlConfig(
            concurrency=self._config.crawl_concurrency,
            interval_ms=self._config.crawl_interval_ms,
            max_rounds=self._config.crawl_max_rounds,
            failure_threshold=self._config.crawl_failure_threshold,
            round_interval_ms=self._config.crawl_round_interval_ms,
        )

        task = CrawlTask(
            id=f"crawl-{analysis.request_id}",
            api_id=analysis.request_id,
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

        # 创建请求函数（此处为占位，实际需要执行生成的代码）
        async def request_fn():
            # 实际实现中会执行 generated.code
            return (False, None, 500)

        try:
            await self._batch_crawler.start_task(task, request_fn)
        except Exception as e:
            logger.warning(f"批量采集启动失败 ({analysis.endpoint}): {e}")

    def _find_request(self, request_id: str) -> Optional[CapturedRequest]:
        """根据 request_id 查找原始请求

        Args:
            request_id: 请求 ID

        Returns:
            匹配的 CapturedRequest，未找到返回 None
        """
        for request in self._captured_requests:
            if request.id == request_id:
                return request
        return None

    def get_api_detail(self, request_id: str) -> Optional[str]:
        """获取接口详情的 Markdown 视图

        Args:
            request_id: 请求 ID

        Returns:
            Markdown 格式的详情字符串，未找到返回 None
        """
        # 查找分析结果
        analysis = None
        for a in self._analyses:
            if a.request_id == request_id:
                analysis = a
                break

        if analysis is None:
            return None

        # 获取生成的代码
        generated_code = self._generated_codes.get(request_id)

        # 获取采集状态
        crawl_task = self._batch_crawler.get_task(f"crawl-{request_id}")
        crawl_status = crawl_task.status if crawl_task else None

        return self._report_generator.get_api_detail(
            request_id=request_id,
            analysis=analysis,
            generated_code=generated_code,
            crawl_status=crawl_status,
        )
