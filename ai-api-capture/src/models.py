"""数据模型定义

定义系统中所有核心数据结构，包括：
- CaptureTarget: 抓取目标
- FilterRules: 过滤规则
- CapturedRequest: 捕获的 HTTP 请求
- ParameterInfo: 参数信息
- APIType: 接口类型枚举
- APIAnalysisResult: 接口分析结果
- DataLink: 数据链路
- AnalysisReport: 分析报告
- RequirementStatus, ConnectionResult, CertResult, ProxyResult, ProcessResult: 结果类型
"""

import json
import base64
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List


# ============================================================
# 枚举类型
# ============================================================


class APIType(Enum):
    """接口类型枚举"""

    LIST = "list"
    PAGINATION = "pagination"
    DETAIL = "detail"
    MEDIA = "media"
    CONFIG = "config"
    AUX = "aux"


# ============================================================
# 核心数据模型
# ============================================================


@dataclass
class CaptureTarget:
    """抓取目标"""

    app_name: str = ""  # 目标 App 名称
    target_data: str = ""  # 期望获取的数据描述
    operation_pages: str = ""  # 需要操作的页面说明
    filter_domains: Optional[List[str]] = None  # 用户指定的域名白名单


@dataclass
class FilterRules:
    """过滤规则"""

    content_type_blacklist: List[str] = field(default_factory=lambda: [
        "image/", "font/", "video/", "audio/", "text/css", "application/javascript",
    ])
    domain_blacklist: List[str] = field(default_factory=list)
    path_blacklist: List[str] = field(default_factory=list)
    content_type_whitelist: List[str] = field(default_factory=lambda: ["json"])
    api_path_patterns: List[str] = field(default_factory=lambda: [
        "/api/", "/v1/", "/v2/", "/v3/", "/portal/", "/gateway/",
    ])
    user_domain_whitelist: Optional[List[str]] = None
    user_domain_blacklist: Optional[List[str]] = None


@dataclass
class CapturedRequest:
    """捕获的 HTTP 请求-响应对"""

    id: str
    timestamp: datetime
    method: str
    url: str
    headers: dict
    body: Optional[str]
    response_status: int
    response_headers: dict
    response_body: Optional[str]
    is_decrypted: bool

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
            "body": self.body,
            "response_status": self.response_status,
            "response_headers": self.response_headers,
            "response_body": self.response_body,
            "is_decrypted": self.is_decrypted,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CapturedRequest":
        """从字典反序列化"""
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            method=data["method"],
            url=data["url"],
            headers=data["headers"],
            body=data.get("body"),
            response_status=data["response_status"],
            response_headers=data["response_headers"],
            response_body=data.get("response_body"),
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
class ParameterInfo:
    """参数信息"""

    name: str
    value_sample: str
    category: str  # static, session, dynamic
    source: str  # query, header, body, cookie

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "name": self.name,
            "value_sample": self.value_sample,
            "category": self.category,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParameterInfo":
        """从字典反序列化"""
        return cls(
            name=data["name"],
            value_sample=data["value_sample"],
            category=data["category"],
            source=data["source"],
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
        )


@dataclass
class APIAnalysisResult:
    """接口分析结果"""

    request_id: str
    endpoint: str
    api_type: APIType
    parameters: List[ParameterInfo]
    has_signature: bool
    signature_fields: List[str]
    matches_target: bool
    call_count: int

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "api_type": self.api_type.value,
            "parameters": [p.to_dict() for p in self.parameters],
            "has_signature": self.has_signature,
            "signature_fields": self.signature_fields,
            "matches_target": self.matches_target,
            "call_count": self.call_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "APIAnalysisResult":
        """从字典反序列化"""
        return cls(
            request_id=data["request_id"],
            endpoint=data["endpoint"],
            api_type=APIType(data["api_type"]),
            parameters=[ParameterInfo.from_dict(p) for p in data["parameters"]],
            has_signature=data["has_signature"],
            signature_fields=data["signature_fields"],
            matches_target=data["matches_target"],
            call_count=data["call_count"],
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
            and self.api_type == other.api_type
            and self.parameters == other.parameters
            and self.has_signature == other.has_signature
            and self.signature_fields == other.signature_fields
            and self.matches_target == other.matches_target
            and self.call_count == other.call_count
        )


@dataclass
class DataLink:
    """数据链路"""

    source_endpoint: str  # 源接口路径
    target_endpoint: str  # 目标接口路径
    link_field: str  # 关联字段名（如 id）
    link_type: str  # 链路类型: list_to_detail, list_to_media, detail_to_media

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "source_endpoint": self.source_endpoint,
            "target_endpoint": self.target_endpoint,
            "link_field": self.link_field,
            "link_type": self.link_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DataLink":
        """从字典反序列化"""
        return cls(
            source_endpoint=data["source_endpoint"],
            target_endpoint=data["target_endpoint"],
            link_field=data["link_field"],
            link_type=data["link_type"],
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "DataLink":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DataLink):
            return NotImplemented
        return (
            self.source_endpoint == other.source_endpoint
            and self.target_endpoint == other.target_endpoint
            and self.link_field == other.link_field
            and self.link_type == other.link_type
        )


@dataclass
class AnalysisReport:
    """分析报告"""

    target: CaptureTarget
    results: List[APIAnalysisResult]
    data_links: List[DataLink]
    total_captured: int  # 总捕获请求数（过滤前）
    total_analyzed: int  # 分析的接口数（过滤后）
    target_matched: int  # 匹配用户目标的接口数
    generated_at: datetime  # 报告生成时间

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "target": {
                "app_name": self.target.app_name,
                "target_data": self.target.target_data,
                "operation_pages": self.target.operation_pages,
                "filter_domains": self.target.filter_domains,
            },
            "results": [r.to_dict() for r in self.results],
            "data_links": [dl.to_dict() for dl in self.data_links],
            "total_captured": self.total_captured,
            "total_analyzed": self.total_analyzed,
            "target_matched": self.target_matched,
            "generated_at": self.generated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisReport":
        """从字典反序列化"""
        target_data = data["target"]
        return cls(
            target=CaptureTarget(
                app_name=target_data["app_name"],
                target_data=target_data["target_data"],
                operation_pages=target_data["operation_pages"],
                filter_domains=target_data.get("filter_domains"),
            ),
            results=[APIAnalysisResult.from_dict(r) for r in data["results"]],
            data_links=[DataLink.from_dict(dl) for dl in data["data_links"]],
            total_captured=data["total_captured"],
            total_analyzed=data["total_analyzed"],
            target_matched=data["target_matched"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
        )

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "AnalysisReport":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AnalysisReport):
            return NotImplemented
        return (
            self.target.app_name == other.target.app_name
            and self.target.target_data == other.target.target_data
            and self.target.operation_pages == other.target.operation_pages
            and self.target.filter_domains == other.target.filter_domains
            and self.results == other.results
            and self.data_links == other.data_links
            and self.total_captured == other.total_captured
            and self.total_analyzed == other.total_analyzed
            and self.target_matched == other.target_matched
            and self.generated_at == other.generated_at
        )


# ============================================================
# 结果类型
# ============================================================


@dataclass
class RequirementStatus:
    """需求收集状态"""

    is_complete: bool
    missing_fields: List[str] = field(default_factory=list)
    message: str = ""


@dataclass
class ConnectionResult:
    """设备连接结果"""

    success: bool
    device_id: str = ""
    error: str = ""
    suggestion: str = ""


@dataclass
class CertResult:
    """证书安装结果"""

    success: bool
    error: str = ""
    suggestion: str = ""


@dataclass
class ProxyResult:
    """代理设置结果"""

    success: bool
    host: str = ""
    port: int = 0
    error: str = ""
    suggestion: str = ""


@dataclass
class ProcessResult:
    """进程启动结果"""

    success: bool
    pid: int = 0
    error: str = ""
    suggestion: str = ""
