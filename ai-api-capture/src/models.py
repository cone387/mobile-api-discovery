"""数据模型定义

定义系统中所有核心数据结构，包括：
- CapturedRequest: 捕获的 HTTP 请求
- OperationStep: 操作步骤
- OperationSequence: 操作序列
- ParameterInfo: 参数信息
- APIAnalysisResult: 接口分析结果
- GeneratedCode: 生成的代码
- CrawlConfig: 采集配置
- CrawlStats: 采集统计
- CrawlTask: 采集任务
"""

import json
import base64
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class CapturedRequest:
    """捕获的 HTTP 请求-响应对"""

    id: str
    timestamp: datetime
    operation_step_id: str
    method: str
    url: str
    headers: dict
    body: Optional[bytes]
    response_status: int
    response_headers: dict
    response_body: Optional[bytes]
    is_decrypted: bool

    def to_dict(self) -> dict:
        """序列化为字典，bytes 字段使用 base64 编码"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "operation_step_id": self.operation_step_id,
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
            "body": base64.b64encode(self.body).decode("ascii") if self.body is not None else None,
            "response_status": self.response_status,
            "response_headers": self.response_headers,
            "response_body": base64.b64encode(self.response_body).decode("ascii") if self.response_body is not None else None,
            "is_decrypted": self.is_decrypted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CapturedRequest":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            operation_step_id=data["operation_step_id"],
            method=data["method"],
            url=data["url"],
            headers=data["headers"],
            body=base64.b64decode(data["body"]) if data.get("body") is not None else None,
            response_status=data["response_status"],
            response_headers=data["response_headers"],
            response_body=base64.b64decode(data["response_body"]) if data.get("response_body") is not None else None,
            is_decrypted=data["is_decrypted"],
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "CapturedRequest":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CapturedRequest):
            return NotImplemented
        return (
            self.id == other.id
            and self.timestamp == other.timestamp
            and self.operation_step_id == other.operation_step_id
            and self.method == other.method
            and self.url == other.url
            and self.headers == other.headers
            and self.body == other.body
            and self.response_status == other.response_status
            and self.response_headers == other.response_headers
            and self.response_body == other.response_body
            and self.is_decrypted == other.is_decrypted
        )


@dataclass
class OperationStep:
    """操作步骤"""

    id: str
    sequence_id: str
    action_type: str  # click, swipe, input, navigate, wait
    target: Optional[str]
    parameters: dict
    status: str  # pending, success, failed, skipped
    error_message: Optional[str]

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "sequence_id": self.sequence_id,
            "action_type": self.action_type,
            "target": self.target,
            "parameters": self.parameters,
            "status": self.status,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OperationStep":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            sequence_id=data["sequence_id"],
            action_type=data["action_type"],
            target=data.get("target"),
            parameters=data["parameters"],
            status=data["status"],
            error_message=data.get("error_message"),
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "OperationStep":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OperationStep):
            return NotImplemented
        return (
            self.id == other.id
            and self.sequence_id == other.sequence_id
            and self.action_type == other.action_type
            and self.target == other.target
            and self.parameters == other.parameters
            and self.status == other.status
            and self.error_message == other.error_message
        )


@dataclass
class OperationSequence:
    """操作序列"""

    id: str
    app_package: str
    intent_description: str
    steps: List[OperationStep]
    created_at: datetime

    def to_dict(self) -> dict:
        """序列化为字典，递归序列化嵌套的 OperationStep"""
        return {
            "id": self.id,
            "app_package": self.app_package,
            "intent_description": self.intent_description,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OperationSequence":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            app_package=data["app_package"],
            intent_description=data["intent_description"],
            steps=[OperationStep.from_dict(s) for s in data["steps"]],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "OperationSequence":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OperationSequence):
            return NotImplemented
        return (
            self.id == other.id
            and self.app_package == other.app_package
            and self.intent_description == other.intent_description
            and self.steps == other.steps
            and self.created_at == other.created_at
        )


@dataclass
class ParameterInfo:
    """参数信息"""

    name: str
    value_sample: str
    category: str  # static, session, dynamic, unknown
    source: str  # query, header, body, cookie
    reasoning: str

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "name": self.name,
            "value_sample": self.value_sample,
            "category": self.category,
            "source": self.source,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParameterInfo":
        """从字典反序列化"""
        return cls(
            name=data["name"],
            value_sample=data["value_sample"],
            category=data["category"],
            source=data["source"],
            reasoning=data["reasoning"],
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "ParameterInfo":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ParameterInfo):
            return NotImplemented
        return (
            self.name == other.name
            and self.value_sample == other.value_sample
            and self.category == other.category
            and self.source == other.source
            and self.reasoning == other.reasoning
        )


@dataclass
class APIAnalysisResult:
    """接口分析结果"""

    request_id: str
    endpoint: str
    purpose: str
    parameters: List[ParameterInfo]
    reproducibility: str  # reproducible, complex, unknown
    reproducibility_reason: str
    confidence: float  # 0-1

    def to_dict(self) -> dict:
        """序列化为字典，递归序列化嵌套的 ParameterInfo"""
        return {
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "purpose": self.purpose,
            "parameters": [p.to_dict() for p in self.parameters],
            "reproducibility": self.reproducibility,
            "reproducibility_reason": self.reproducibility_reason,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "APIAnalysisResult":
        """从字典反序列化"""
        return cls(
            request_id=data["request_id"],
            endpoint=data["endpoint"],
            purpose=data["purpose"],
            parameters=[ParameterInfo.from_dict(p) for p in data["parameters"]],
            reproducibility=data["reproducibility"],
            reproducibility_reason=data["reproducibility_reason"],
            confidence=data["confidence"],
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "APIAnalysisResult":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, APIAnalysisResult):
            return NotImplemented
        return (
            self.request_id == other.request_id
            and self.endpoint == other.endpoint
            and self.purpose == other.purpose
            and self.parameters == other.parameters
            and self.reproducibility == other.reproducibility
            and self.reproducibility_reason == other.reproducibility_reason
            and self.confidence == other.confidence
        )


@dataclass
class GeneratedCode:
    """生成的 Python 代码"""

    api_id: str
    code: str
    session_params: List[str]
    verification_status: str  # pending, passed, failed
    failure_reason: Optional[str]

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "api_id": self.api_id,
            "code": self.code,
            "session_params": self.session_params,
            "verification_status": self.verification_status,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GeneratedCode":
        """从字典反序列化"""
        return cls(
            api_id=data["api_id"],
            code=data["code"],
            session_params=data["session_params"],
            verification_status=data["verification_status"],
            failure_reason=data.get("failure_reason"),
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "GeneratedCode":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GeneratedCode):
            return NotImplemented
        return (
            self.api_id == other.api_id
            and self.code == other.code
            and self.session_params == other.session_params
            and self.verification_status == other.verification_status
            and self.failure_reason == other.failure_reason
        )


@dataclass
class CrawlConfig:
    """采集配置"""

    concurrency: int
    interval_ms: int
    max_rounds: int
    failure_threshold: int
    round_interval_ms: int

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "concurrency": self.concurrency,
            "interval_ms": self.interval_ms,
            "max_rounds": self.max_rounds,
            "failure_threshold": self.failure_threshold,
            "round_interval_ms": self.round_interval_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlConfig":
        """从字典反序列化"""
        return cls(
            concurrency=data["concurrency"],
            interval_ms=data["interval_ms"],
            max_rounds=data["max_rounds"],
            failure_threshold=data["failure_threshold"],
            round_interval_ms=data["round_interval_ms"],
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "CrawlConfig":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CrawlConfig):
            return NotImplemented
        return (
            self.concurrency == other.concurrency
            and self.interval_ms == other.interval_ms
            and self.max_rounds == other.max_rounds
            and self.failure_threshold == other.failure_threshold
            and self.round_interval_ms == other.round_interval_ms
        )


@dataclass
class CrawlStats:
    """采集统计"""

    total_requests: int
    success_count: int
    failure_count: int
    consecutive_failures: int
    data_collected: int

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "total_requests": self.total_requests,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "data_collected": self.data_collected,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlStats":
        """从字典反序列化"""
        return cls(
            total_requests=data["total_requests"],
            success_count=data["success_count"],
            failure_count=data["failure_count"],
            consecutive_failures=data["consecutive_failures"],
            data_collected=data["data_collected"],
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "CrawlStats":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CrawlStats):
            return NotImplemented
        return (
            self.total_requests == other.total_requests
            and self.success_count == other.success_count
            and self.failure_count == other.failure_count
            and self.consecutive_failures == other.consecutive_failures
            and self.data_collected == other.data_collected
        )


@dataclass
class CrawlTask:
    """采集任务"""

    id: str
    api_id: str
    mode: str  # batch, replay
    config: CrawlConfig
    status: str  # running, paused, completed, failed
    stats: CrawlStats

    def to_dict(self) -> dict:
        """序列化为字典，递归序列化嵌套的 CrawlConfig 和 CrawlStats"""
        return {
            "id": self.id,
            "api_id": self.api_id,
            "mode": self.mode,
            "config": self.config.to_dict(),
            "status": self.status,
            "stats": self.stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlTask":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            api_id=data["api_id"],
            mode=data["mode"],
            config=CrawlConfig.from_dict(data["config"]),
            status=data["status"],
            stats=CrawlStats.from_dict(data["stats"]),
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "CrawlTask":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CrawlTask):
            return NotImplemented
        return (
            self.id == other.id
            and self.api_id == other.api_id
            and self.mode == other.mode
            and self.config == other.config
            and self.status == other.status
            and self.stats == other.stats
        )
