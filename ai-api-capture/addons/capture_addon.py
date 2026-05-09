"""mitmproxy addon 脚本 - 4 层过滤 + JSON 文件存储

本模块实现 mitmproxy 的 addon 接口，用于：
- 捕获 HTTP 请求/响应对
- 实现 4 层过滤逻辑：静态资源过滤、域名黑名单、路径黑名单、API 白名单
- 将每个通过过滤的请求保存为独立 JSON 文件
- 记录 HTTPS 解密失败的请求
- 响应体以文本形式存储（JSON 响应）

作为 mitmdump addon 独立运行（不导入 src/models.py），
通过环境变量或命令行参数配置。

使用方式：
    mitmdump -s capture_addon.py

环境变量配置：
    CAPTURE_STORAGE_PATH: 存储路径（默认: ./output/captures）
    CAPTURE_USER_DOMAIN_WHITELIST: 逗号分隔的用户域名白名单
    CAPTURE_USER_DOMAIN_BLACKLIST: 逗号分隔的用户域名黑名单
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from mitmproxy import http, tls


# ============================================================
# 过滤规则（独立定义，不依赖 src/models.py）
# ============================================================

# 第 1 层：静态资源 Content-Type 黑名单
DEFAULT_CONTENT_TYPE_BLACKLIST = [
    "image/", "font/", "video/", "audio/", "text/css", "application/javascript",
]

# 第 2 层：域名黑名单（第三方 SDK：数据上报、崩溃上报、广告、推送、性能监控等）
DEFAULT_DOMAIN_BLACKLIST = [
    "analytics.oceanengine.com",
    "sss.umeng.com",
    "tracking.miui.com",
    "pro.bugly.qq.com",
    "bugly.qq.com",
    "pbaccess.video.qq.com",
    "amdcopen.m.taobao.com",
    "gepush.com",
    "sdk-open-phone.getui.com",
    "tingyun.com",
    "wkdcm1.tingyun.com",
    "203.107.1.1",
    "cbsipv4.shuzilm.cn",
    "mssdk",
    "polaris",
    "gecko.zijieapi.com",
    "report.mumu.nie.netease.com",
    "api.mumu.nie.netease.com",
]

# 第 3 层：路径黑名单（已知非业务路径）
DEFAULT_PATH_BLACKLIST = [
    "/sdk/app/",
    "/reportBatchData",
    "/upload-json",
    "/api/v2/al",
    "/api/v1/attribute",
    "/api/collection",
    "/getMobileRedirectHost",
    "/initMobileApp",
    "/track/v4",
]

# 第 4 层：API 白名单
DEFAULT_CONTENT_TYPE_WHITELIST = ["json"]
DEFAULT_API_PATH_PATTERNS = ["/api/", "/v1/", "/v2/", "/v3/", "/portal/", "/gateway/"]


@dataclass
class FilterRules:
    """过滤规则配置（独立于 src/models.py，用于 mitmdump addon 进程）

    Attributes:
        content_type_blacklist: 静态资源 Content-Type 黑名单
        domain_blacklist: 域名黑名单
        path_blacklist: 路径黑名单
        content_type_whitelist: API Content-Type 白名单
        api_path_patterns: API 路径模式白名单
        user_domain_whitelist: 用户指定的域名白名单
        user_domain_blacklist: 用户指定的域名黑名单
    """

    content_type_blacklist: List[str] = field(
        default_factory=lambda: list(DEFAULT_CONTENT_TYPE_BLACKLIST)
    )
    domain_blacklist: List[str] = field(
        default_factory=lambda: list(DEFAULT_DOMAIN_BLACKLIST)
    )
    path_blacklist: List[str] = field(
        default_factory=lambda: list(DEFAULT_PATH_BLACKLIST)
    )
    content_type_whitelist: List[str] = field(
        default_factory=lambda: list(DEFAULT_CONTENT_TYPE_WHITELIST)
    )
    api_path_patterns: List[str] = field(
        default_factory=lambda: list(DEFAULT_API_PATH_PATTERNS)
    )
    user_domain_whitelist: Optional[List[str]] = None
    user_domain_blacklist: Optional[List[str]] = None


class CaptureAddon:
    """mitmproxy addon，实现 4 层过滤并将请求保存为独立 JSON 文件。

    过滤逻辑：
    1. 静态资源过滤：Content-Type 为 image/、font/、video/、audio/、text/css、application/javascript
    2. 域名黑名单：第三方 SDK 域名（数据上报、崩溃上报、广告、推送、性能监控等）
    3. 路径黑名单：已知非业务路径（/sdk/app/、/reportBatchData、/track/v4 等）
    4. API 白名单：Content-Type 含 json，或路径含 /api/、/v1/、/v2/、/v3/、/portal/、/gateway/

    Attributes:
        storage_path: JSON 文件存储目录路径
        filter_rules: 过滤规则配置
    """

    def __init__(self, storage_path: str, filter_rules: Optional[FilterRules] = None):
        """初始化 CaptureAddon。

        Args:
            storage_path: 捕获数据的存储目录路径
            filter_rules: 过滤规则，为 None 时使用默认规则
        """
        self.storage_path = storage_path
        self.filter_rules = filter_rules or FilterRules()
        self._captured_requests: List[dict] = []
        self._tls_failures: List[dict] = []

        # 确保存储目录存在
        os.makedirs(self.storage_path, exist_ok=True)

    def get_captured_requests(self) -> List[dict]:
        """获取所有已捕获的请求列表（内存中的）。

        Returns:
            捕获的请求字典列表
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

    def response(self, flow: http.HTTPFlow) -> None:
        """mitmproxy 响应钩子 - 应用 4 层过滤并保存匹配的请求。

        Args:
            flow: mitmproxy HTTP 流对象（包含请求和响应）
        """
        if self._should_capture(flow):
            self._save_flow(flow)

    def tls_failed_client_hello(self, client_hello: tls.ClientHelloData) -> None:
        """mitmproxy TLS 失败钩子 - 记录 HTTPS 解密失败。

        Args:
            client_hello: TLS ClientHello 数据
        """
        sni = "unknown"
        if client_hello.context and client_hello.context.client:
            sni = client_hello.context.client.sni or "unknown"

        failure_record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "method": "CONNECT",
            "url": f"https://{sni}/",
            "headers": {},
            "body": None,
            "response_status": 0,
            "response_headers": {},
            "response_body": None,
            "is_decrypted": False,
        }
        self._tls_failures.append(failure_record)
        self._captured_requests.append(failure_record)
        self._write_json_file(failure_record["id"], failure_record)

    def _should_capture(self, flow: http.HTTPFlow) -> bool:
        """应用 4 层过滤逻辑判断是否应捕获该请求。

        过滤顺序：
        1. 静态资源过滤
        2. 域名黑名单
        3. 路径黑名单
        4. API 白名单

        Args:
            flow: mitmproxy HTTP 流对象

        Returns:
            True 表示应捕获该请求
        """
        parsed_url = urlparse(flow.request.pretty_url)
        hostname = parsed_url.hostname or ""
        path = parsed_url.path or ""

        # 获取响应 Content-Type
        response_content_type = ""
        if flow.response and flow.response.headers:
            response_content_type = flow.response.headers.get("content-type", "").lower()

        # === 用户域名白名单（如果设置了，只保留白名单中的域名）===
        if self.filter_rules.user_domain_whitelist:
            if not self._domain_matches_list(hostname, self.filter_rules.user_domain_whitelist):
                return False

        # === 用户域名黑名单 ===
        if self.filter_rules.user_domain_blacklist:
            if self._domain_matches_list(hostname, self.filter_rules.user_domain_blacklist):
                return False

        # === 第 1 层：静态资源过滤 ===
        if self._is_static_resource(response_content_type):
            return False

        # === 第 2 层：域名黑名单 ===
        if self._is_blacklisted_domain(hostname):
            return False

        # === 第 3 层：路径黑名单 ===
        if self._is_blacklisted_path(path):
            return False

        # === 第 4 层：API 白名单 ===
        if not self._matches_api_whitelist(response_content_type, path):
            return False

        return True

    def _is_static_resource(self, content_type: str) -> bool:
        """检查 Content-Type 是否为静态资源。"""
        for blacklisted in self.filter_rules.content_type_blacklist:
            if blacklisted.lower() in content_type:
                return True
        return False

    def _is_blacklisted_domain(self, hostname: str) -> bool:
        """检查域名是否在黑名单中。"""
        return self._domain_matches_list(hostname, self.filter_rules.domain_blacklist)

    def _is_blacklisted_path(self, path: str) -> bool:
        """检查路径是否在黑名单中（包含匹配）。"""
        for blacklisted_path in self.filter_rules.path_blacklist:
            if blacklisted_path in path:
                return True
        return False

    def _matches_api_whitelist(self, content_type: str, path: str) -> bool:
        """检查是否匹配 API 白名单（Content-Type 含 json 或路径匹配 API 模式）。"""
        # 检查 Content-Type 白名单
        for whitelisted in self.filter_rules.content_type_whitelist:
            if whitelisted.lower() in content_type:
                return True

        # 检查 API 路径模式
        for pattern in self.filter_rules.api_path_patterns:
            if pattern in path:
                return True

        return False

    @staticmethod
    def _domain_matches_list(hostname: str, domain_list: List[str]) -> bool:
        """检查主机名是否匹配域名列表中的任一项（精确匹配或子域名匹配）。"""
        if not hostname:
            return False
        for domain in domain_list:
            if hostname == domain or hostname.endswith("." + domain):
                return True
        return False

    def _save_flow(self, flow: http.HTTPFlow) -> None:
        """将 HTTP 流保存为 JSON 文件。

        响应体以文本形式存储（JSON 响应直接存文本）。

        Args:
            flow: mitmproxy HTTP 流对象
        """
        request_id = str(uuid.uuid4())

        # 获取请求体（文本形式）
        request_body = None
        if flow.request.content:
            try:
                request_body = flow.request.content.decode("utf-8", errors="replace")
            except Exception:
                request_body = None

        # 获取响应体（文本形式）
        response_body = None
        if flow.response and flow.response.content:
            try:
                response_body = flow.response.content.decode("utf-8", errors="replace")
            except Exception:
                response_body = None

        captured = {
            "id": request_id,
            "timestamp": datetime.now().isoformat(),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "headers": dict(flow.request.headers),
            "body": request_body,
            "response_status": flow.response.status_code if flow.response else 0,
            "response_headers": dict(flow.response.headers) if flow.response else {},
            "response_body": response_body,
            "is_decrypted": True,
        }

        self._captured_requests.append(captured)
        self._write_json_file(request_id, captured)

    def _write_json_file(self, request_id: str, data: dict) -> None:
        """将数据写入 JSON 文件。

        Args:
            request_id: 请求唯一 ID，用作文件名
            data: 要写入的字典数据
        """
        filepath = os.path.join(self.storage_path, f"{request_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            # 写入失败时静默跳过（不中断录制）
            pass


# === mitmdump 独立运行支持 ===
# 当作为 mitmdump addon 使用时（mitmdump -s capture_addon.py），
# 通过环境变量配置参数


def _create_addon_from_env() -> CaptureAddon:
    """从环境变量创建 CaptureAddon 实例。

    环境变量：
        CAPTURE_STORAGE_PATH: 存储路径（默认: ./output/captures）
        CAPTURE_USER_DOMAIN_WHITELIST: 逗号分隔的用户域名白名单
        CAPTURE_USER_DOMAIN_BLACKLIST: 逗号分隔的用户域名黑名单
    """
    storage_path = os.environ.get("CAPTURE_STORAGE_PATH", "./output/captures")

    # 用户自定义域名白名单/黑名单
    user_whitelist_str = os.environ.get("CAPTURE_USER_DOMAIN_WHITELIST", "")
    user_blacklist_str = os.environ.get("CAPTURE_USER_DOMAIN_BLACKLIST", "")

    user_domain_whitelist = (
        [d.strip() for d in user_whitelist_str.split(",") if d.strip()]
        if user_whitelist_str else None
    )
    user_domain_blacklist = (
        [d.strip() for d in user_blacklist_str.split(",") if d.strip()]
        if user_blacklist_str else None
    )

    filter_rules = FilterRules(
        user_domain_whitelist=user_domain_whitelist,
        user_domain_blacklist=user_domain_blacklist,
    )

    return CaptureAddon(storage_path=storage_path, filter_rules=filter_rules)


# mitmdump 加载入口点
addons = [_create_addon_from_env()]
