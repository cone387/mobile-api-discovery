"""报告生成模块 - 统计数据、Markdown 格式输出

实现功能：
- 汇总报告生成：统计接口总数、各分类数量
- Markdown 格式渲染：生成可读的 Markdown 报告
- 报告文件保存：输出到指定路径
- 接口详情查询：展示分析报告、生成代码和采集状态
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.models import APIAnalysisResult, GeneratedCode


@dataclass
class APISummary:
    """单个接口的摘要信息"""

    request_id: str
    endpoint: str
    purpose: str
    reproducibility: str
    confidence: float


@dataclass
class SummaryReport:
    """汇总报告数据结构"""

    total_count: int
    reproducible_count: int
    complex_count: int
    unknown_count: int
    api_summaries: List[APISummary]


class ReportGenerator:
    """报告生成器

    核心功能：
    1. generate_summary(): 从分析结果列表生成汇总报告
    2. render_markdown(): 将报告渲染为 Markdown 格式字符串
    3. save_report(): 保存报告到文件
    4. get_api_detail(): 获取单个接口的详细 Markdown 视图
    """

    def generate_summary(self, analyses: List[APIAnalysisResult]) -> SummaryReport:
        """从分析结果列表生成汇总报告

        统计各分类的接口数量，并为每个接口生成摘要。

        Args:
            analyses: 接口分析结果列表

        Returns:
            SummaryReport 汇总报告对象
        """
        reproducible_count = 0
        complex_count = 0
        unknown_count = 0
        api_summaries: List[APISummary] = []

        for analysis in analyses:
            if analysis.reproducibility == "reproducible":
                reproducible_count += 1
            elif analysis.reproducibility == "complex":
                complex_count += 1
            else:
                unknown_count += 1

            api_summaries.append(
                APISummary(
                    request_id=analysis.request_id,
                    endpoint=analysis.endpoint,
                    purpose=analysis.purpose,
                    reproducibility=analysis.reproducibility,
                    confidence=analysis.confidence,
                )
            )

        total_count = len(analyses)

        return SummaryReport(
            total_count=total_count,
            reproducible_count=reproducible_count,
            complex_count=complex_count,
            unknown_count=unknown_count,
            api_summaries=api_summaries,
        )

    def render_markdown(self, report: SummaryReport) -> str:
        """将汇总报告渲染为 Markdown 格式字符串

        Args:
            report: 汇总报告对象

        Returns:
            Markdown 格式的报告字符串
        """
        lines: List[str] = []

        # 标题
        lines.append("# 接口抓取分析报告")
        lines.append("")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 统计概览
        lines.append("## 统计概览")
        lines.append("")
        lines.append(f"| 指标 | 数量 |")
        lines.append(f"|------|------|")
        lines.append(f"| 总接口数 | {report.total_count} |")
        lines.append(f"| 可复现接口 | {report.reproducible_count} |")
        lines.append(f"| 复杂接口 | {report.complex_count} |")
        lines.append(f"| 未知接口 | {report.unknown_count} |")
        lines.append("")

        # 接口列表
        lines.append("## 接口列表")
        lines.append("")

        if report.api_summaries:
            lines.append("| 接口路径 | 用途 | 分类 | 置信度 |")
            lines.append("|----------|------|------|--------|")

            for summary in report.api_summaries:
                reproducibility_label = self._get_reproducibility_label(
                    summary.reproducibility
                )
                lines.append(
                    f"| {summary.endpoint} | {summary.purpose} "
                    f"| {reproducibility_label} | {summary.confidence:.0%} |"
                )
            lines.append("")
        else:
            lines.append("暂无接口数据。")
            lines.append("")

        return "\n".join(lines)

    def save_report(self, report: SummaryReport, output_path: str) -> None:
        """将报告保存到指定路径

        Args:
            report: 汇总报告对象
            output_path: 输出文件路径
        """
        markdown_content = self.render_markdown(report)

        # 确保目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        Path(output_path).write_text(markdown_content, encoding="utf-8")

    def get_api_detail(
        self,
        request_id: str,
        analysis: APIAnalysisResult,
        generated_code: Optional[GeneratedCode],
        crawl_status: Optional[str],
    ) -> str:
        """获取单个接口的详细 Markdown 视图

        展示分析报告、生成代码（如有）和采集状态。

        Args:
            request_id: 请求 ID
            analysis: 接口分析结果
            generated_code: 生成的代码（可选）
            crawl_status: 采集状态（可选）

        Returns:
            Markdown 格式的详情字符串
        """
        lines: List[str] = []

        # 标题
        lines.append(f"# 接口详情: {analysis.endpoint}")
        lines.append("")

        # 基本信息
        lines.append("## 基本信息")
        lines.append("")
        lines.append(f"- **请求 ID**: {request_id}")
        lines.append(f"- **接口路径**: {analysis.endpoint}")
        lines.append(f"- **接口用途**: {analysis.purpose}")
        lines.append(
            f"- **可复现性**: {self._get_reproducibility_label(analysis.reproducibility)}"
        )
        lines.append(f"- **判定依据**: {analysis.reproducibility_reason}")
        lines.append(f"- **置信度**: {analysis.confidence:.0%}")
        lines.append("")

        # 参数分析
        lines.append("## 参数分析")
        lines.append("")

        if analysis.parameters:
            lines.append("| 参数名 | 分类 | 来源 | 样本值 |")
            lines.append("|--------|------|------|--------|")

            for param in analysis.parameters:
                category_label = self._get_category_label(param.category)
                # 截断过长的样本值
                value_display = param.value_sample
                if len(value_display) > 30:
                    value_display = value_display[:27] + "..."
                lines.append(
                    f"| {param.name} | {category_label} "
                    f"| {param.source} | `{value_display}` |"
                )
            lines.append("")
        else:
            lines.append("无参数。")
            lines.append("")

        # 生成代码
        lines.append("## 生成代码")
        lines.append("")

        if generated_code is not None:
            lines.append(f"- **验证状态**: {generated_code.verification_status}")
            if generated_code.failure_reason:
                lines.append(f"- **失败原因**: {generated_code.failure_reason}")
            if generated_code.session_params:
                lines.append(
                    f"- **会话参数**: {', '.join(generated_code.session_params)}"
                )
            lines.append("")
            lines.append("```python")
            lines.append(generated_code.code)
            lines.append("```")
            lines.append("")
        else:
            lines.append("未生成代码。")
            lines.append("")

        # 采集状态
        lines.append("## 采集状态")
        lines.append("")

        if crawl_status is not None:
            lines.append(f"当前状态: **{crawl_status}**")
        else:
            lines.append("未启动采集。")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _get_reproducibility_label(reproducibility: str) -> str:
        """获取可复现性的中文标签"""
        labels = {
            "reproducible": "✅ 可复现",
            "complex": "⚠️ 复杂接口",
            "unknown": "❓ 未知",
        }
        return labels.get(reproducibility, reproducibility)

    @staticmethod
    def _get_category_label(category: str) -> str:
        """获取参数分类的中文标签"""
        labels = {
            "static": "静态",
            "session": "会话",
            "dynamic": "动态",
            "unknown": "未知",
        }
        return labels.get(category, category)
