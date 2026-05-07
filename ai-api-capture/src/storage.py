"""数据存储层 - JSON 文件读写、SQLite 索引管理

提供统一的 Storage 接口，结合：
- JSON 文件存储：保存完整数据（CapturedRequest, APIAnalysisResult, GeneratedCode, CrawlTask）
- SQLite 索引：维护索引数据库用于快速查询
"""

import json
from pathlib import Path
from typing import Optional, List

import aiosqlite

from .models import (
    CapturedRequest,
    APIAnalysisResult,
    GeneratedCode,
    CrawlTask,
)


class Storage:
    """统一数据存储接口，结合 JSON 文件存储和 SQLite 索引管理"""

    def __init__(self, base_dir: str = "output"):
        self.base_dir = Path(base_dir)
        self.captures_dir = self.base_dir / "captures"
        self.analysis_dir = self.base_dir / "analysis"
        self.generated_dir = self.base_dir / "generated"
        self.data_dir = self.base_dir / "data"
        self.db_path = self.base_dir / "index.db"
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """初始化存储：创建目录和数据库表"""
        self._ensure_directories()
        await self._init_database()

    def _ensure_directories(self) -> None:
        """确保所有输出目录存在"""
        for directory in [
            self.captures_dir,
            self.analysis_dir,
            self.generated_dir,
            self.data_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    async def _init_database(self) -> None:
        """初始化 SQLite 数据库，创建索引表"""
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                method TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                step_id TEXT,
                reproducibility TEXT
            );

            CREATE TABLE IF NOT EXISTS analyses (
                request_id TEXT PRIMARY KEY,
                endpoint TEXT NOT NULL,
                purpose TEXT NOT NULL,
                reproducibility TEXT NOT NULL,
                confidence REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS crawl_tasks (
                id TEXT PRIMARY KEY,
                api_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        await self._db.commit()

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None

    # ========== JSON 文件存储：CapturedRequest ==========

    async def save_request(self, request: CapturedRequest) -> None:
        """保存单个 CapturedRequest 到 JSON 文件并更新索引"""
        file_path = self.captures_dir / f"{request.id}.json"
        file_path.write_text(
            json.dumps(request.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await self._index_request(request)

    async def save_requests(self, requests: List[CapturedRequest]) -> None:
        """批量保存 CapturedRequest"""
        for request in requests:
            await self.save_request(request)

    async def load_request(self, request_id: str) -> Optional[CapturedRequest]:
        """从 JSON 文件加载单个 CapturedRequest"""
        file_path = self.captures_dir / f"{request_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return CapturedRequest.from_dict(data)

    async def load_all_requests(self) -> List[CapturedRequest]:
        """加载所有 CapturedRequest"""
        results = []
        for file_path in self.captures_dir.glob("*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            results.append(CapturedRequest.from_dict(data))
        return results

    async def _index_request(self, request: CapturedRequest) -> None:
        """将请求信息写入 SQLite 索引"""
        if not self._db:
            return
        await self._db.execute(
            """
            INSERT OR REPLACE INTO requests (id, url, method, timestamp, step_id, reproducibility)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.id,
                request.url,
                request.method,
                request.timestamp.isoformat(),
                request.operation_step_id,
                None,  # reproducibility 在分析后更新
            ),
        )
        await self._db.commit()

    # ========== JSON 文件存储：APIAnalysisResult ==========

    async def save_analysis(self, analysis: APIAnalysisResult) -> None:
        """保存单个 APIAnalysisResult 到 JSON 文件并更新索引"""
        file_path = self.analysis_dir / f"{analysis.request_id}.json"
        file_path.write_text(
            json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await self._index_analysis(analysis)

    async def save_analyses(self, analyses: List[APIAnalysisResult]) -> None:
        """批量保存 APIAnalysisResult"""
        for analysis in analyses:
            await self.save_analysis(analysis)

    async def load_analysis(self, request_id: str) -> Optional[APIAnalysisResult]:
        """从 JSON 文件加载单个 APIAnalysisResult"""
        file_path = self.analysis_dir / f"{request_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return APIAnalysisResult.from_dict(data)

    async def load_all_analyses(self) -> List[APIAnalysisResult]:
        """加载所有 APIAnalysisResult"""
        results = []
        for file_path in self.analysis_dir.glob("*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            results.append(APIAnalysisResult.from_dict(data))
        return results

    async def _index_analysis(self, analysis: APIAnalysisResult) -> None:
        """将分析结果写入 SQLite 索引，并更新 requests 表的 reproducibility"""
        if not self._db:
            return
        await self._db.execute(
            """
            INSERT OR REPLACE INTO analyses (request_id, endpoint, purpose, reproducibility, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                analysis.request_id,
                analysis.endpoint,
                analysis.purpose,
                analysis.reproducibility,
                analysis.confidence,
            ),
        )
        # 同步更新 requests 表中的 reproducibility 字段
        await self._db.execute(
            "UPDATE requests SET reproducibility = ? WHERE id = ?",
            (analysis.reproducibility, analysis.request_id),
        )
        await self._db.commit()

    # ========== JSON 文件存储：GeneratedCode ==========

    async def save_generated_code(self, generated: GeneratedCode) -> None:
        """保存单个 GeneratedCode 到 JSON 文件"""
        file_path = self.generated_dir / f"{generated.api_id}.json"
        file_path.write_text(
            json.dumps(generated.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def save_generated_codes(self, codes: List[GeneratedCode]) -> None:
        """批量保存 GeneratedCode"""
        for code in codes:
            await self.save_generated_code(code)

    async def load_generated_code(self, api_id: str) -> Optional[GeneratedCode]:
        """从 JSON 文件加载单个 GeneratedCode"""
        file_path = self.generated_dir / f"{api_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return GeneratedCode.from_dict(data)

    async def load_all_generated_codes(self) -> List[GeneratedCode]:
        """加载所有 GeneratedCode"""
        results = []
        for file_path in self.generated_dir.glob("*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            results.append(GeneratedCode.from_dict(data))
        return results

    # ========== JSON 文件存储：CrawlTask ==========

    async def save_crawl_task(self, task: CrawlTask) -> None:
        """保存单个 CrawlTask 到 JSON 文件并更新索引"""
        file_path = self.data_dir / f"task_{task.id}.json"
        file_path.write_text(
            json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await self._index_crawl_task(task)

    async def save_crawl_tasks(self, tasks: List[CrawlTask]) -> None:
        """批量保存 CrawlTask"""
        for task in tasks:
            await self.save_crawl_task(task)

    async def load_crawl_task(self, task_id: str) -> Optional[CrawlTask]:
        """从 JSON 文件加载单个 CrawlTask"""
        file_path = self.data_dir / f"task_{task_id}.json"
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return CrawlTask.from_dict(data)

    async def load_all_crawl_tasks(self) -> List[CrawlTask]:
        """加载所有 CrawlTask"""
        results = []
        for file_path in self.data_dir.glob("task_*.json"):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            results.append(CrawlTask.from_dict(data))
        return results

    async def _index_crawl_task(self, task: CrawlTask) -> None:
        """将采集任务信息写入 SQLite 索引"""
        if not self._db:
            return
        await self._db.execute(
            """
            INSERT OR REPLACE INTO crawl_tasks (id, api_id, mode, status)
            VALUES (?, ?, ?, ?)
            """,
            (task.id, task.api_id, task.mode, task.status),
        )
        await self._db.commit()

    # ========== JSON 文件存储：采集数据 ==========

    async def save_crawl_data(self, task_id: str, data: dict) -> None:
        """保存采集到的数据到 JSON 文件"""
        task_data_dir = self.data_dir / task_id
        task_data_dir.mkdir(parents=True, exist_ok=True)
        # 使用递增编号命名
        existing = list(task_data_dir.glob("*.json"))
        index = len(existing)
        file_path = task_data_dir / f"{index:06d}.json"
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def save_crawl_data_batch(self, task_id: str, data_list: List[dict]) -> None:
        """批量保存采集数据"""
        for data in data_list:
            await self.save_crawl_data(task_id, data)

    async def load_crawl_data(self, task_id: str) -> List[dict]:
        """加载指定任务的所有采集数据"""
        task_data_dir = self.data_dir / task_id
        if not task_data_dir.exists():
            return []
        results = []
        for file_path in sorted(task_data_dir.glob("*.json")):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            results.append(data)
        return results

    # ========== SQLite 查询方法 ==========

    async def get_request_by_id(self, request_id: str) -> Optional[CapturedRequest]:
        """通过 ID 查询请求（从 JSON 文件加载完整数据）"""
        return await self.load_request(request_id)

    async def get_requests_by_reproducibility(
        self, reproducibility: str
    ) -> List[CapturedRequest]:
        """按可复现性查询请求"""
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT id FROM requests WHERE reproducibility = ?",
            (reproducibility,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            request = await self.load_request(row[0])
            if request:
                results.append(request)
        return results

    async def get_requests_by_step_id(
        self, step_id: str
    ) -> List[CapturedRequest]:
        """按操作步骤 ID 查询请求"""
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT id FROM requests WHERE step_id = ?",
            (step_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            request = await self.load_request(row[0])
            if request:
                results.append(request)
        return results

    async def get_analyses_by_reproducibility(
        self, reproducibility: str
    ) -> List[APIAnalysisResult]:
        """按可复现性查询分析结果"""
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT request_id FROM analyses WHERE reproducibility = ?",
            (reproducibility,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            analysis = await self.load_analysis(row[0])
            if analysis:
                results.append(analysis)
        return results

    async def get_analyses_by_purpose(
        self, purpose: str
    ) -> List[APIAnalysisResult]:
        """按接口用途查询分析结果"""
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT request_id FROM analyses WHERE purpose = ?",
            (purpose,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            analysis = await self.load_analysis(row[0])
            if analysis:
                results.append(analysis)
        return results

    async def get_crawl_tasks_by_status(
        self, status: str
    ) -> List[CrawlTask]:
        """按状态查询采集任务"""
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT id FROM crawl_tasks WHERE status = ?",
            (status,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            task = await self.load_crawl_task(row[0])
            if task:
                results.append(task)
        return results

    async def get_crawl_tasks_by_api_id(
        self, api_id: str
    ) -> List[CrawlTask]:
        """按接口 ID 查询采集任务"""
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT id FROM crawl_tasks WHERE api_id = ?",
            (api_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            task = await self.load_crawl_task(row[0])
            if task:
                results.append(task)
        return results
