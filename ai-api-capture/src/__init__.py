"""AI 辅助的通用移动端接口抓取与分析系统

模块组成：
- CaptureSystem: 主协调器，协调四阶段工作流
- RequirementCollector: 需求收集与引导
- EnvironmentManager: 环境管理（adb + mitmdump）
- TrafficInterceptor: 流量拦截与过滤
- APIAnalyzer: 接口分析（通用模式识别）
- ReportGenerator: 报告生成（Markdown + samples）
"""

from src.capture_system import CaptureSystem
from src.requirement_collector import RequirementCollector
from src.environment_manager import EnvironmentManager
from src.traffic_interceptor import TrafficInterceptor
from src.api_analyzer import APIAnalyzer
from src.report_generator import ReportGenerator

__all__ = [
    "CaptureSystem",
    "RequirementCollector",
    "EnvironmentManager",
    "TrafficInterceptor",
    "APIAnalyzer",
    "ReportGenerator",
]
