"""数据存储层 - JSON 文件读写

提供简单的 JSON 文件存储接口：
- 每个 CapturedRequest 保存为独立 JSON 文件（增量写入）
- 支持批量读取所有流量数据
- 存储路径：output/captures/ 和 output/analysis/samples/
"""

import json
from pathlib import Path
from typing import Optional, List

from .models import CapturedRequest, APIAnalysisResult, AnalysisReport


class Storage:
    """JSON 文件存储接口

    简单直接的文件存储，无需数据库依赖。
    每个请求独立存储，支持增量写入。
    """

    def __init__(self, base_dir: str = "output"):
        self.base_dir = Path(base_dir)
        self.captures_dir = self.base_dir / "captures"
        self.analysis_dir = self.base_dir / "analysis"
        self.samples_dir = self.base_dir / "analysis" / "samples"

    def initialize(self) -> None:
        """初始化存储：创建目录结构"""
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保所有输出目录存在"""
        for directory in [
            self.captures_dir,
            self.analysis_dir,
            self.samples_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    # ========== CapturedRequest 存储 ==========

    def save_request(self, request: CapturedRequest) -> None:
        """保存单个 CapturedRequest 到独立 JSON 文件（增量写入）"""
        self._ensure_directories()
        file_path = self.captures_dir / f"{request.id}.json"
        file_path.write_text(
            json.dumps(request.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_requests(self, requests: List[CapturedRequest]) -> None:
        """批量保存 CapturedRequest"""
        for request in requests:
            self.save_request(request)

    def load_request(self, request_id: str) -> Optional[CapturedRequest]:
        """从 JSON 文件加载单个 CapturedRequest"""
        file_path = self.captures_dir / f"{request_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return CapturedRequest.from_dict(data)

    def load_all_requests(self) -> List[CapturedRequest]:
        """批量读取所有捕获的流量数据"""
        results = []
        if not self.captures_dir.exists():
            return results
        for file_path in sorted(self.captures_dir.glob("*.json")):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            results.append(CapturedRequest.from_dict(data))
        return results

    def get_request_count(self) -> int:
        """获取已保存的请求数量"""
        if not self.captures_dir.exists():
            return 0
        return len(list(self.captures_dir.glob("*.json")))

    # ========== APIAnalysisResult 存储 ==========

    def save_analysis(self, analysis: APIAnalysisResult) -> None:
        """保存单个 APIAnalysisResult 到 JSON 文件"""
        self._ensure_directories()
        file_path = self.analysis_dir / f"{analysis.request_id}.json"
        file_path.write_text(
            json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_analyses(self, analyses: List[APIAnalysisResult]) -> None:
        """批量保存 APIAnalysisResult"""
        for analysis in analyses:
            self.save_analysis(analysis)

    def load_analysis(self, request_id: str) -> Optional[APIAnalysisResult]:
        """从 JSON 文件加载单个 APIAnalysisResult"""
        file_path = self.analysis_dir / f"{request_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return APIAnalysisResult.from_dict(data)

    def load_all_analyses(self) -> List[APIAnalysisResult]:
        """加载所有 APIAnalysisResult"""
        results = []
        if not self.analysis_dir.exists():
            return results
        for file_path in sorted(self.analysis_dir.glob("*.json")):
            # Skip files in samples/ subdirectory
            if file_path.parent != self.analysis_dir:
                continue
            data = json.loads(file_path.read_text(encoding="utf-8"))
            results.append(APIAnalysisResult.from_dict(data))
        return results

    # ========== Samples 存储 ==========

    def save_sample(self, request_id: str, request_data: dict, response_data: dict) -> str:
        """保存请求/响应 JSON 样本到 samples/ 目录

        Returns:
            保存的文件相对路径（相对于 analysis 目录）
        """
        self._ensure_directories()
        sample = {
            "request": request_data,
            "response": response_data,
        }
        file_path = self.samples_dir / f"{request_id}.json"
        file_path.write_text(
            json.dumps(sample, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return f"samples/{request_id}.json"

    def load_sample(self, request_id: str) -> Optional[dict]:
        """加载请求/响应 JSON 样本"""
        file_path = self.samples_dir / f"{request_id}.json"
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text(encoding="utf-8"))

    # ========== AnalysisReport 存储 ==========

    def save_report(self, report: AnalysisReport, filename: str = "report.json") -> None:
        """保存分析报告到 JSON 文件"""
        self._ensure_directories()
        file_path = self.analysis_dir / filename
        file_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_report(self, filename: str = "report.json") -> Optional[AnalysisReport]:
        """加载分析报告"""
        file_path = self.analysis_dir / filename
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return AnalysisReport.from_dict(data)
