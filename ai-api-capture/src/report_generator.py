"""报告生成模块

实现功能：
- generate(): 协调完整报告生成（渲染 Markdown + 保存样本 + 写入报告文件）
- generate_curl(): 为每个接口生成可执行的 cURL 命令
- save_samples(): 保存请求/响应 JSON 到 samples/ 目录
- render_markdown(): 生成完整的 Markdown 报告，适合 AI 解析
"""

import json
import os
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from src.models import (
    AnalysisReport,
    APIAnalysisResult,
    APIType,
    CapturedRequest,
    CaptureTarget,
    DataLink,
    ParameterInfo,
)


# Headers that are trivial/standard and should be excluded from cURL
_TRIVIAL_HEADERS = {
    "host",
    "content-length",
    "connection",
    "accept-encoding",
    "transfer-encoding",
}


class ReportGenerator:
    """报告生成器

    核心功能：
    1. generate(): 协调完整报告生成流程
    2. generate_curl(): 生成可执行的 cURL 命令
    3. save_samples(): 保存请求/响应 JSON 样本文件
    4. render_markdown(): 渲染完整 Markdown 报告
    """

    def generate(self, report: AnalysisReport, output_dir: str) -> str:
        """协调完整报告生成流程

        1. 渲染 Markdown 报告
        2. 保存样本文件到 samples/ 子目录
        3. 写入报告文件

        Args:
            report: 分析报告对象
            output_dir: 输出目录路径（如 output/analysis/）

        Returns:
            报告文件的路径
        """
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 渲染 Markdown 报告
        markdown_content = self.render_markdown(report)

        # 写入报告文件
        report_path = os.path.join(output_dir, "report.md")
        Path(report_path).write_text(markdown_content, encoding="utf-8")

        return report_path

    def generate_curl(self, request: CapturedRequest) -> str:
        """为请求生成可执行的 cURL 命令

        包含正确的 HTTP 方法、完整 URL 和所有非平凡请求头。

        Args:
            request: 捕获的请求对象

        Returns:
            可执行的 cURL 命令字符串
        """
        parts = ["curl"]

        # HTTP 方法
        if request.method.upper() != "GET":
            parts.append(f"-X {request.method.upper()}")

        # URL
        parts.append(f"'{request.url}'")

        # 非平凡请求头
        for name, value in request.headers.items():
            if name.lower() not in _TRIVIAL_HEADERS:
                parts.append(f"-H '{name}: {value}'")

        # 请求体
        if request.body:
            # Escape single quotes in body
            escaped_body = request.body.replace("'", "'\\''")
            parts.append(f"-d '{escaped_body}'")

        return " \\\n  ".join(parts)

    def save_samples(
        self,
        requests: List[CapturedRequest],
        results: List[APIAnalysisResult],
        samples_dir: str,
    ) -> List[str]:
        """保存请求/响应 JSON 到 samples/ 目录

        每个接口保存一个 JSON 文件，包含请求和响应信息。

        Args:
            requests: 捕获的请求列表
            results: 分析结果列表
            samples_dir: 样本保存目录路径

        Returns:
            保存的文件相对路径列表
        """
        os.makedirs(samples_dir, exist_ok=True)

        # 建立 request_id -> request 的映射
        request_map = {req.id: req for req in requests}

        saved_paths: List[str] = []

        for result in results:
            req = request_map.get(result.request_id)
            if req is None:
                continue

            # 构建样本数据
            sample_data = {
                "request": {
                    "method": req.method,
                    "url": req.url,
                    "headers": req.headers,
                    "body": req.body,
                },
                "response": {
                    "status": req.response_status,
                    "headers": req.response_headers,
                    "body": req.response_body,
                },
                "analysis": {
                    "endpoint": result.endpoint,
                    "api_type": result.api_type.value,
                    "matches_target": result.matches_target,
                },
            }

            # 生成文件名（使用 request_id）
            filename = f"{result.request_id}.json"
            filepath = os.path.join(samples_dir, filename)

            Path(filepath).write_text(
                json.dumps(sample_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 返回相对路径
            saved_paths.append(f"samples/{filename}")

        return saved_paths

    def render_markdown(self, report: AnalysisReport) -> str:
        """生成完整的 Markdown 报告

        报告结构：
        1. 抓取目标摘要
        2. 数据链路图
        3. 接口概览表
        4. 每个接口详情
        5. 签名机制说明
        6. 采集策略建议

        Args:
            report: 分析报告对象

        Returns:
            Markdown 格式的报告字符串
        """
        lines: List[str] = []

        # 标题
        lines.append("# 接口分析报告")
        lines.append("")
        lines.append(f"生成时间: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 1. 抓取目标摘要
        lines.append("## 抓取目标摘要")
        lines.append("")
        lines.append(f"- **目标 App**: {report.target.app_name}")
        lines.append(f"- **目标数据**: {report.target.target_data}")
        lines.append(f"- **操作页面**: {report.target.operation_pages}")
        if report.target.filter_domains:
            lines.append(f"- **过滤域名**: {', '.join(report.target.filter_domains)}")
        lines.append("")
        lines.append(f"- 总捕获请求数: {report.total_captured}")
        lines.append(f"- 分析接口数: {report.total_analyzed}")
        lines.append(f"- 匹配目标接口数: {report.target_matched}")
        lines.append("")

        # 2. 数据链路图
        lines.append("## 数据链路图")
        lines.append("")
        if report.data_links:
            lines.append("```")
            for link in report.data_links:
                lines.append(
                    f"{link.source_endpoint} --[{link.link_field}]--> "
                    f"{link.target_endpoint} ({link.link_type})"
                )
            lines.append("```")
        else:
            lines.append("未检测到接口间数据链路关系。")
        lines.append("")

        # 3. 接口概览表
        lines.append("## 接口概览表")
        lines.append("")
        if report.results:
            lines.append("| 接口路径 | 类型 | 调用次数 | 匹配目标 |")
            lines.append("|----------|------|----------|----------|")
            for result in report.results:
                matches = "✅" if result.matches_target else "❌"
                lines.append(
                    f"| {result.endpoint} | {result.api_type.value} "
                    f"| {result.call_count} | {matches} |"
                )
        else:
            lines.append("未发现业务接口。")
        lines.append("")

        # 4. 每个接口详情
        lines.append("## 接口详情")
        lines.append("")
        for result in report.results:
            lines.append(f"### {result.endpoint}")
            lines.append("")
            lines.append(f"- **类型**: {result.api_type.value}")
            lines.append(f"- **调用次数**: {result.call_count}")
            lines.append(f"- **匹配目标**: {'是' if result.matches_target else '否'}")
            lines.append("")

            # 请求参数表
            if result.parameters:
                lines.append("#### 请求参数")
                lines.append("")
                lines.append("| 参数名 | 分类 | 来源 | 示例值 |")
                lines.append("|--------|------|------|--------|")
                for param in result.parameters:
                    # 截断过长的样本值
                    value_display = param.value_sample
                    if len(value_display) > 40:
                        value_display = value_display[:37] + "..."
                    lines.append(
                        f"| {param.name} | {param.category} "
                        f"| {param.source} | `{value_display}` |"
                    )
                lines.append("")

            # 签名字段
            if result.has_signature:
                lines.append(f"#### 签名字段")
                lines.append("")
                lines.append(f"包含动态签名: {', '.join(result.signature_fields)}")
                lines.append("")

            # 完整响应引用
            lines.append(f"#### 样本文件")
            lines.append("")
            lines.append(f"完整请求/响应: [samples/{result.request_id}.json](samples/{result.request_id}.json)")
            lines.append("")

        # 5. 签名机制说明
        lines.append("## 签名机制说明")
        lines.append("")
        signed_results = [r for r in report.results if r.has_signature]
        if signed_results:
            for result in signed_results:
                lines.append(f"- **{result.endpoint}**: 签名字段 = {', '.join(result.signature_fields)}")
            lines.append("")
            lines.append("这些接口包含动态签名参数，直接重放可能失败，需要逆向签名算法。")
        else:
            lines.append("未检测到包含动态签名的接口。")
        lines.append("")

        # 6. 采集策略建议
        lines.append("## 采集策略建议")
        lines.append("")
        lines.append(self._generate_strategy_suggestions(report))
        lines.append("")

        return "\n".join(lines)

    def _generate_strategy_suggestions(self, report: AnalysisReport) -> str:
        """根据分析结果生成采集策略建议"""
        suggestions: List[str] = []

        # 检查是否有分页接口
        pagination_apis = [
            r for r in report.results if r.api_type == APIType.PAGINATION
        ]
        if pagination_apis:
            suggestions.append(
                "- 检测到分页接口，建议实现翻页逻辑以获取完整数据"
            )

        # 检查是否有签名接口
        signed_apis = [r for r in report.results if r.has_signature]
        if signed_apis:
            suggestions.append(
                "- 检测到签名接口，需要逆向签名算法或使用 session 重放"
            )

        # 检查数据链路
        if report.data_links:
            suggestions.append(
                "- 检测到数据链路关系，建议按 列表→详情→媒体 的顺序采集"
            )

        # 检查匹配目标的接口
        if report.target_matched > 0:
            suggestions.append(
                f"- 已找到 {report.target_matched} 个匹配目标的接口，可直接开始采集"
            )
        else:
            suggestions.append(
                "- 未找到直接匹配目标的接口，建议扩大操作范围或调整目标描述"
            )

        if not suggestions:
            return "暂无特别建议。"

        return "\n".join(suggestions)
