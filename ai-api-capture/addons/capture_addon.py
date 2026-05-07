"""mitmproxy addon 脚本 - 请求/响应捕获、字段记录、步骤 ID 关联

本模块实现 mitmproxy 的 addon 接口，用于：
- 捕获 HTTP 请求/响应对
- 记录所有必要字段（method, URL, headers, body, response status 等）
- 将每个请求与当前操作步骤 ID 关联
- 将捕获数据保存为 JSON 文件
- 支持过滤规则（域名、路径、Content-Type）
- 处理 HTTPS 解密失败

可作为 mitmdump addon 独立使用，也可通过 TrafficInterceptor 编程调用。
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from mitmproxy import http, tls


@dataclass
class FilterRules:
    """过滤规则配置

    Attributes:
        domains: 允许的域名列表（空列表表示允许所有域名）
        paths: 允许的路径前缀列表（空列表表示允许所有路径）
        content_types: 允许的 Content-Type 列表（空列表表示允许所有类型）
    """

    domains: List[str] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)
    content_types: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "domains": self.domains,
            "paths": self.paths,
            "content_types": self.content_types,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FilterRules":
        """从字典反序列化"""
        return cls(
            domains=data.get("domains", []),
            paths=data.get("paths", []),
            content_types=data.get("content_types", []),
        )


class CaptureAddon:
    """mitmproxy addon，用于捕获 HTTP 请求/响应并保存为 JSON 文件。

    该 addon 拦截经过代理的所有 HTTP 流量，根据过滤规则筛选后，
    将请求-响应对序列化为 JSON 文件存储到指定路径。

    Attributes:
        storage_path: JSON 文件存储目录路径
        filter_rules: 过滤规则配置
        current_step_id: 当前操作步骤 ID（由 DeviceController 更新）
    """

    def __init__(self, storage_path: str, filter_rules: Optional[FilterRules] = None):
        """初始化 CaptureAddon。

        Args:
            storage_path: 捕获数据的存储目录路径
            filter_rules: 过滤规则，为 None 时使用默认规则（允许所有）
        """
        self.storage_path = storage_path
        self.filter_rules = filter_rules or FilterRules()
        self.current_step_id: Optional[str] = None
        self._captured_requests: List[dict] = []
        self._tls_failures: List[dict] = []

        # 确保存储目录存在
        os.makedirs(self.storage_path, exist_ok=True)

    def set_step_id(self, step_id: Optional[str]) -> None:
        """更新当前操作步骤 ID。

        由 DeviceController 在执行操作步骤时调用，
        后续捕获的请求将关联到此步骤 ID。

        Args:
            step_id: 操作步骤 ID，None 表示无关联步骤
        """
        self.current_step_id = step_id

    def get_captured_requests(self) -> List[dict]:
        """获取所有已捕获的请求列表。

        Returns:
            捕获的请求字典列表，每个字典包含 CapturedRequest 的所有字段
        """
        return list(self._captured_requests)

    def get_tls_failures(self) -> List[dict]:
        """获取所有 TLS 解密失败记录。

        Returns:
            TLS 失败记录列表
        """
        return list(self._tls_failures)

    def clear(self) -> None:
        """清空内存中的捕获记录。"""
        self._captured_requests.clear()
        self._tls_failures.clear()

    def request(self, flow: http.HTTPFlow) -> None:
        """mitmproxy 请求钩子 - 记录请求开始时间和步骤 ID。

        在请求发出时记录元数据，供后续 response 钩子使用。

        Args:
            flow: mitmproxy HTTP 流对象
        """
        flow.metadata["capture_time"] = datetime.now().isoformat()
        flow.metadata["step_id"] = self.current_step_id

    def response(self, flow: http.HTTPFlow) -> None:
        """mitmproxy 响应钩子 - 捕获并保存匹配过滤规则的请求/响应对。

        Args:
            flow: mitmproxy HTTP 流对象（包含请求和响应）
        """
        if self._matches_filter(flow):
            self._save_flow(flow)

    def tls_failed_client_hello(self, client_hello: tls.ClientHelloData) -> None:
        """mitmproxy TLS 失败钩子 - 记录 HTTPS 解密失败。

        当客户端 TLS 握手失败时调用，标记该连接的请求为未解密。

        Args:
            client_hello: TLS ClientHello 数据
        """
        failure_record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "operation_step_id": self.current_step_id or "",
            "client_sni": client_hello.context.client.sni if client_hello.context.client.sni else "unknown",
            "is_decrypted": False,
        }
        self._tls_failures.append(failure_record)
        self._save_tls_failure(failure_record)

    def _matches_filter(self, flow: http.HTTPFlow) -> bool:
        """检查请求是否匹配过滤规则。

        过滤逻辑：
        - 如果某个过滤列表为空，表示该维度不过滤（允许所有）
        - 如果某个过滤列表非空，请求必须匹配列表中的至少一项

        Args:
            flow: mitmproxy HTTP 流对象

        Returns:
            True 表示请求匹配过滤规则，应该被保存
        """
        parsed_url = urlparse(flow.request.pretty_url)

        # 域名过滤
        if self.filter_rules.domains:
            hostname = parsed_url.hostname or ""
            if not any(hostname == domain or hostname.endswith("." + domain)
                       for domain in self.filter_rules.domains):
                return False

        # 路径前缀过滤
        if self.filter_rules.paths:
            path = parsed_url.path
            if not any(path.startswith(prefix) for prefix in self.filter_rules.paths):
                return False

        # Content-Type 过滤（检查响应的 Content-Type）
        if self.filter_rules.content_types:
            response_content_type = flow.response.headers.get("content-type", "") if flow.response else ""
            if not any(ct in response_content_type for ct in self.filter_rules.content_types):
                return False

        return True

    def _save_flow(self, flow: http.HTTPFlow) -> None:
        """将 HTTP 流保存为 JSON 文件。

        生成唯一 ID，构建 CapturedRequest 格式的字典，
        同时保存到内存列表和磁盘文件。

        Args:
            flow: mitmproxy HTTP 流对象
        """
        import base64

        request_id = str(uuid.uuid4())

        # 获取请求体
        request_body = flow.request.content
        # 获取响应体
        response_body = flow.response.content if flow.response else None

        captured = {
            "id": request_id,
            "timestamp": flow.metadata.get("capture_time", datetime.now().isoformat()),
            "operation_step_id": flow.metadata.get("step_id", "") or "",
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "headers": dict(flow.request.headers),
            "body": base64.b64encode(request_body).decode("ascii") if request_body else None,
            "response_status": flow.response.status_code if flow.response else 0,
            "response_headers": dict(flow.response.headers) if flow.response else {},
            "response_body": base64.b64encode(response_body).decode("ascii") if response_body else None,
            "is_decrypted": True,
        }

        self._captured_requests.append(captured)
        self._write_json_file(request_id, captured)

    def _save_tls_failure(self, failure_record: dict) -> None:
        """将 TLS 失败记录保存为 JSON 文件。

        Args:
            failure_record: TLS 失败记录字典
        """
        # 为 TLS 失败创建一个最小化的 CapturedRequest 格式记录
        captured = {
            "id": failure_record["id"],
            "timestamp": failure_record["timestamp"],
            "operation_step_id": failure_record["operation_step_id"],
            "method": "CONNECT",
            "url": f"https://{failure_record['client_sni']}/",
            "headers": {},
            "body": None,
            "response_status": 0,
            "response_headers": {},
            "response_body": None,
            "is_decrypted": False,
        }

        self._captured_requests.append(captured)
        self._write_json_file(failure_record["id"], captured)

    def _write_json_file(self, request_id: str, data: dict) -> None:
        """将数据写入 JSON 文件。

        Args:
            request_id: 请求唯一 ID，用作文件名
            data: 要写入的字典数据
        """
        filepath = os.path.join(self.storage_path, f"{request_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# === mitmdump 独立运行支持 ===
# 当作为 mitmdump addon 使用时（mitmdump -s capture_addon.py），
# 通过环境变量配置参数

def _create_addon_from_env() -> CaptureAddon:
    """从环境变量创建 CaptureAddon 实例。

    环境变量：
        CAPTURE_STORAGE_PATH: 存储路径（默认: ./output/captures）
        CAPTURE_FILTER_DOMAINS: 逗号分隔的域名列表
        CAPTURE_FILTER_PATHS: 逗号分隔的路径前缀列表
        CAPTURE_FILTER_CONTENT_TYPES: 逗号分隔的 Content-Type 列表
        CAPTURE_STEP_ID: 初始步骤 ID
    """
    storage_path = os.environ.get("CAPTURE_STORAGE_PATH", "./output/captures")

    domains_str = os.environ.get("CAPTURE_FILTER_DOMAINS", "")
    paths_str = os.environ.get("CAPTURE_FILTER_PATHS", "")
    content_types_str = os.environ.get("CAPTURE_FILTER_CONTENT_TYPES", "")

    filter_rules = FilterRules(
        domains=[d.strip() for d in domains_str.split(",") if d.strip()],
        paths=[p.strip() for p in paths_str.split(",") if p.strip()],
        content_types=[ct.strip() for ct in content_types_str.split(",") if ct.strip()],
    )

    addon = CaptureAddon(storage_path=storage_path, filter_rules=filter_rules)

    step_id = os.environ.get("CAPTURE_STEP_ID")
    if step_id:
        addon.set_step_id(step_id)

    return addon


# mitmdump 加载入口点
addons = [_create_addon_from_env()]
