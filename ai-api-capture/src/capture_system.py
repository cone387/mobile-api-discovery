"""主协调器 - 协调四阶段流程

CaptureSystem 是系统的顶层协调器，负责：
- 阶段 1: RequirementCollector - 需求收集与引导
- 阶段 2: EnvironmentManager - 环境准备（adb + mitmdump）
- 阶段 3: TrafficInterceptor - 流量录制控制
- 阶段 4: APIAnalyzer + ReportGenerator - 分析与报告生成

状态流转：
  IDLE -> COLLECTING -> ENVIRONMENT_READY -> RECORDING -> ANALYZING -> COMPLETED
"""

import logging
import os
from enum import Enum
from typing import Optional

from src.api_analyzer import APIAnalyzer
from src.environment_manager import EnvironmentManager
from src.models import (
    AnalysisReport,
    CaptureTarget,
    FilterRules,
)
from src.report_generator import ReportGenerator
from src.requirement_collector import RequirementCollector
from src.traffic_interceptor import TrafficInterceptor

logger = logging.getLogger(__name__)


class CapturePhase(Enum):
    """系统阶段枚举"""

    IDLE = "idle"
    COLLECTING = "collecting"
    ENVIRONMENT_READY = "environment_ready"
    RECORDING = "recording"
    ANALYZING = "analyzing"
    COMPLETED = "completed"


class CaptureSystem:
    """主协调器 - 协调四阶段工作流

    四阶段流程：
    1. 需求收集：通过 RequirementCollector 引导用户明确抓取目标
    2. 环境准备：通过 EnvironmentManager 配置 adb + mitmdump
    3. 流量录制：通过 TrafficInterceptor 管理录制状态
    4. 分析报告：通过 APIAnalyzer + ReportGenerator 生成报告

    使用示例:
        system = CaptureSystem(storage_path="./output/captures")

        # 阶段 1: 需求收集
        status = system.collect_requirements("抓取盒马的商品列表，操作首页")
        if status.is_complete:
            # 阶段 2: 环境准备（由 AI 代理调用 EnvironmentManager）
            system.mark_environment_ready()

            # 阶段 3: 用户操作 App
            system.start_recording()
            # ... 用户操作 ...
            system.stop_recording()  # 自动触发阶段 4

            # 获取报告
            print(system.report_summary)
            print(system.report_path)
    """

    def __init__(
        self,
        storage_path: str = "./output/captures",
        output_dir: str = "./output/analysis",
        filter_rules: Optional[FilterRules] = None,
    ) -> None:
        """初始化 CaptureSystem

        Args:
            storage_path: 流量 JSON 文件存储目录
            output_dir: 分析报告输出目录
            filter_rules: 过滤规则，为 None 时使用默认规则
        """
        self._storage_path = storage_path
        self._output_dir = output_dir

        # 初始化各模块
        self._requirement_collector = RequirementCollector()
        self._environment_manager = EnvironmentManager()
        self._traffic_interceptor = TrafficInterceptor(
            storage_path=storage_path,
            filter_rules=filter_rules,
        )
        self._api_analyzer = APIAnalyzer()
        self._report_generator = ReportGenerator()

        # 状态
        self._phase = CapturePhase.IDLE
        self._target: Optional[CaptureTarget] = None
        self._report: Optional[AnalysisReport] = None
        self._report_path: Optional[str] = None

    @property
    def phase(self) -> CapturePhase:
        """当前阶段"""
        return self._phase

    @property
    def target(self) -> Optional[CaptureTarget]:
        """当前抓取目标"""
        return self._target

    @property
    def requirement_collector(self) -> RequirementCollector:
        """需求收集器实例"""
        return self._requirement_collector

    @property
    def environment_manager(self) -> EnvironmentManager:
        """环境管理器实例"""
        return self._environment_manager

    @property
    def traffic_interceptor(self) -> TrafficInterceptor:
        """流量拦截器实例"""
        return self._traffic_interceptor

    @property
    def api_analyzer(self) -> APIAnalyzer:
        """接口分析器实例"""
        return self._api_analyzer

    @property
    def report_generator(self) -> ReportGenerator:
        """报告生成器实例"""
        return self._report_generator

    @property
    def report(self) -> Optional[AnalysisReport]:
        """分析报告（分析完成后可用）"""
        return self._report

    @property
    def report_path(self) -> Optional[str]:
        """报告文件路径（分析完成后可用）"""
        return self._report_path

    @property
    def report_summary(self) -> Optional[str]:
        """报告摘要文本（分析完成后可用）"""
        if self._report is None:
            return None
        return (
            f"分析完成！\n"
            f"- 总捕获请求数: {self._report.total_captured}\n"
            f"- 分析接口数: {self._report.total_analyzed}\n"
            f"- 匹配目标接口数: {self._report.target_matched}\n"
            f"- 报告路径: {self._report_path}"
        )

    def collect_requirements(self, user_message: str) -> "RequirementStatus":
        """阶段 1: 收集用户需求

        解析用户输入，提取抓取目标信息。
        当信息完整时自动进入 COLLECTING 完成状态。

        Args:
            user_message: 用户的自然语言输入

        Returns:
            RequirementStatus: 包含是否完整、缺失字段和提示消息
        """
        from src.models import RequirementStatus

        self._phase = CapturePhase.COLLECTING
        status = self._requirement_collector.analyze_input(user_message)

        if status.is_complete:
            # 从用户输入中提取目标（重新提取以获取完整对象）
            self._target = self._requirement_collector._extract_target(user_message)

        return status

    def set_target(self, target: CaptureTarget) -> None:
        """直接设置抓取目标（跳过自然语言解析）

        Args:
            target: 完整的抓取目标

        Raises:
            ValueError: 如果目标信息不完整
        """
        if not self._requirement_collector.is_complete(target):
            missing = self._requirement_collector.get_missing_fields(target)
            raise ValueError(f"目标信息不完整，缺少: {', '.join(missing)}")

        self._target = target
        self._phase = CapturePhase.COLLECTING

    def mark_environment_ready(self) -> None:
        """标记环境准备完成，进入等待录制状态

        由 AI 代理在完成 EnvironmentManager 的所有步骤后调用。

        Raises:
            RuntimeError: 如果目标未设置
        """
        if self._target is None:
            raise RuntimeError("请先完成需求收集（设置抓取目标）")

        self._phase = CapturePhase.ENVIRONMENT_READY
        logger.info("环境准备完成，等待用户开始操作 App")

    def start_recording(self) -> None:
        """阶段 3: 开始流量录制

        标记录制开始，TrafficInterceptor 将记录此后的请求。

        Raises:
            RuntimeError: 如果环境未就绪
        """
        if self._phase not in (CapturePhase.ENVIRONMENT_READY, CapturePhase.COLLECTING):
            if self._phase == CapturePhase.RECORDING:
                raise RuntimeError("已在录制中")
            if self._target is None:
                raise RuntimeError("请先完成需求收集和环境准备")

        self._traffic_interceptor.start_recording()
        self._phase = CapturePhase.RECORDING
        logger.info("流量录制已开始，请在手机上操作 App")

    def stop_recording(self) -> str:
        """停止录制并自动触发分析流程

        停止 TrafficInterceptor 的录制，读取捕获的请求，
        调用 APIAnalyzer 进行分析，调用 ReportGenerator 生成报告。

        Returns:
            报告摘要文本

        Raises:
            RuntimeError: 如果未在录制中
        """
        if self._phase != CapturePhase.RECORDING:
            raise RuntimeError("未在录制中，无法停止")

        # 停止录制
        self._traffic_interceptor.stop_recording()
        self._phase = CapturePhase.ANALYZING
        logger.info("流量录制已停止，开始分析...")

        # 获取捕获的请求
        captured_requests = self._traffic_interceptor.get_captured_requests()
        logger.info(f"共捕获 {len(captured_requests)} 个有效请求")

        # 分析
        target = self._target or CaptureTarget()
        self._report = self._api_analyzer.analyze_all(captured_requests, target)

        # 生成报告
        os.makedirs(self._output_dir, exist_ok=True)
        self._report_path = self._report_generator.generate(
            self._report, self._output_dir
        )

        # 保存样本文件
        samples_dir = os.path.join(self._output_dir, "samples")
        self._report_generator.save_samples(
            captured_requests, self._report.results, samples_dir
        )

        self._phase = CapturePhase.COMPLETED
        logger.info(f"分析完成，报告已保存到: {self._report_path}")

        return self.report_summary or ""
