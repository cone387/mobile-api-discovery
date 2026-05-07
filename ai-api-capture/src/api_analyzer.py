"""接口分析模块 - 分析接口特征并判定可复现性

实现功能：
- 参数提取：从 URL query、headers、body、cookies 中提取参数
- 参数分类：基于规则和模式匹配将参数分为 static/session/dynamic/unknown
- 可复现性判定：根据参数分类结果判定接口类型
- 接口用途语义分析：基于 URL 模式和启发式规则分析接口用途
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from src.models import APIAnalysisResult, CapturedRequest, ParameterInfo


@dataclass
class RequestContext:
    """请求上下文，用于辅助参数分类"""

    url: str
    method: str
    content_type: Optional[str] = None


class LLMClient(ABC):
    """LLM 客户端抽象接口"""

    @abstractmethod
    async def analyze(self, prompt: str) -> str:
        """调用 LLM 分析并返回结果"""
        ...


class DefaultLLMClient(LLMClient):
    """默认 LLM 客户端 - 基于启发式规则的分析（无实际 LLM 调用）"""

    # URL 路径到用途的映射
    PURPOSE_PATTERNS: dict = {
        "feed": "feed",
        "timeline": "feed",
        "stream": "feed",
        "user": "user",
        "profile": "user",
        "account": "user",
        "comment": "comment",
        "reply": "comment",
        "search": "search",
        "query": "search",
        "login": "auth",
        "auth": "auth",
        "token": "auth",
        "upload": "upload",
        "media": "media",
        "image": "media",
        "video": "media",
        "notification": "notification",
        "message": "message",
        "chat": "message",
        "order": "order",
        "payment": "payment",
        "pay": "payment",
        "config": "config",
        "setting": "config",
        "ad": "advertisement",
        "recommend": "recommendation",
    }

    async def analyze(self, prompt: str) -> str:
        """基于启发式规则返回分析结果"""
        return "heuristic-based analysis"

    def detect_purpose(self, url: str) -> str:
        """从 URL 路径中检测接口用途"""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()

        for pattern, purpose in self.PURPOSE_PATTERNS.items():
            if pattern in path_lower:
                return purpose

        return "unknown"


# 标准 HTTP 头部列表（提取参数时过滤掉这些）
STANDARD_HEADERS = frozenset([
    "host",
    "connection",
    "content-length",
    "content-type",
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "pragma",
    "upgrade-insecure-requests",
    "user-agent",
    "referer",
    "origin",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "if-none-match",
    "if-modified-since",
    "transfer-encoding",
    "te",
    "keep-alive",
    "date",
    "vary",
])

# 静态参数名称模式
STATIC_PARAM_NAMES = frozenset([
    "app_version",
    "appversion",
    "app_ver",
    "platform",
    "os_version",
    "os_ver",
    "osversion",
    "device_model",
    "device_type",
    "devicemodel",
    "channel",
    "language",
    "lang",
    "locale",
    "version",
    "ver",
    "build",
    "build_number",
    "sdk_version",
    "api_version",
    "client_type",
    "device_id",
    "device_brand",
    "screen_width",
    "screen_height",
    "resolution",
    "network_type",
    "carrier",
])

# 会话参数名称模式（正则）
SESSION_PARAM_PATTERNS = [
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*auth.*", re.IGNORECASE),
    re.compile(r".*session.*", re.IGNORECASE),
    re.compile(r".*cookie.*", re.IGNORECASE),
    re.compile(r"^authorization$", re.IGNORECASE),
    re.compile(r"^x-access-token$", re.IGNORECASE),
    re.compile(r"^x-auth-token$", re.IGNORECASE),
    re.compile(r"^bearer$", re.IGNORECASE),
    re.compile(r"^api[_-]?key$", re.IGNORECASE),
    re.compile(r"^access[_-]?key$", re.IGNORECASE),
    re.compile(r"^uid$", re.IGNORECASE),
    re.compile(r"^user[_-]?id$", re.IGNORECASE),
]

# 动态参数名称模式（正则）
DYNAMIC_PARAM_PATTERNS = [
    re.compile(r".*sign.*", re.IGNORECASE),
    re.compile(r".*nonce.*", re.IGNORECASE),
    re.compile(r".*timestamp.*", re.IGNORECASE),
    re.compile(r"^ts$", re.IGNORECASE),
    re.compile(r"^t$", re.IGNORECASE),
    re.compile(r".*encrypt.*", re.IGNORECASE),
    re.compile(r".*hash.*", re.IGNORECASE),
    re.compile(r".*checksum.*", re.IGNORECASE),
    re.compile(r"^_t$", re.IGNORECASE),
    re.compile(r"^_ts$", re.IGNORECASE),
    re.compile(r"^salt$", re.IGNORECASE),
    re.compile(r"^random$", re.IGNORECASE),
]

# 动态值模式（hex/base64 哈希值）
DYNAMIC_VALUE_PATTERNS = [
    re.compile(r"^[0-9a-fA-F]{32}$"),  # MD5
    re.compile(r"^[0-9a-fA-F]{40}$"),  # SHA1
    re.compile(r"^[0-9a-fA-F]{64}$"),  # SHA256
    re.compile(r"^[A-Za-z0-9+/]{20,}={0,2}$"),  # Base64 (20+ chars)
]


class APIAnalyzer:
    """接口分析器 - 分析接口特征并判定可复现性"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """初始化分析器

        Args:
            llm_client: LLM 客户端实例，默认使用 DefaultLLMClient
        """
        self.llm_client = llm_client or DefaultLLMClient()

    def extract_parameters(self, request: CapturedRequest) -> List[Tuple[str, str, str]]:
        """从请求中提取所有参数

        提取来源：URL query、headers、body（JSON/form）、cookies

        Args:
            request: 捕获的请求对象

        Returns:
            参数列表，每项为 (name, value, source) 元组
        """
        params: List[Tuple[str, str, str]] = []

        # 1. 从 URL query string 提取
        params.extend(self._extract_query_params(request.url))

        # 2. 从 headers 提取（过滤标准头部）
        params.extend(self._extract_header_params(request.headers))

        # 3. 从 body 提取（JSON 或 form data）
        params.extend(self._extract_body_params(request.body, request.headers))

        # 4. 从 cookies 提取
        params.extend(self._extract_cookie_params(request.headers))

        return params

    def _extract_query_params(self, url: str) -> List[Tuple[str, str, str]]:
        """从 URL query string 中提取参数"""
        params = []
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        for name, values in query_params.items():
            # parse_qs 返回列表，取第一个值
            value = values[0] if values else ""
            params.append((name, value, "query"))

        return params

    def _extract_header_params(self, headers: dict) -> List[Tuple[str, str, str]]:
        """从 headers 中提取非标准头部作为参数"""
        params = []

        for name, value in headers.items():
            if name.lower() not in STANDARD_HEADERS and name.lower() != "cookie":
                params.append((name, str(value), "header"))

        return params

    def _extract_body_params(
        self, body: Optional[bytes], headers: dict
    ) -> List[Tuple[str, str, str]]:
        """从请求体中提取参数（支持 JSON 和 form data）"""
        if body is None:
            return []

        params = []
        content_type = ""
        for key, value in headers.items():
            if key.lower() == "content-type":
                content_type = value.lower()
                break

        # 尝试 JSON 解析
        if "json" in content_type or not content_type:
            try:
                body_str = body.decode("utf-8")
                data = json.loads(body_str)
                if isinstance(data, dict):
                    for name, value in data.items():
                        params.append((name, str(value), "body"))
                    return params
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # 尝试 form data 解析
        if "form" in content_type or (not params and not content_type):
            try:
                body_str = body.decode("utf-8")
                form_params = parse_qs(body_str, keep_blank_values=True)
                for name, values in form_params.items():
                    value = values[0] if values else ""
                    params.append((name, value, "body"))
            except UnicodeDecodeError:
                pass

        return params

    def _extract_cookie_params(self, headers: dict) -> List[Tuple[str, str, str]]:
        """从 Cookie 头部中提取 cookie 参数"""
        params = []

        cookie_value = None
        for key, value in headers.items():
            if key.lower() == "cookie":
                cookie_value = value
                break

        if cookie_value:
            # 解析 Cookie 头部: "name1=value1; name2=value2"
            cookies = cookie_value.split(";")
            for cookie in cookies:
                cookie = cookie.strip()
                if "=" in cookie:
                    name, value = cookie.split("=", 1)
                    params.append((name.strip(), value.strip(), "cookie"))

        return params

    def classify_parameter(
        self, name: str, value: str, context: RequestContext
    ) -> ParameterInfo:
        """对单个参数进行分类

        分类规则优先级：
        1. 名称匹配静态参数列表 -> static
        2. 名称匹配会话参数模式 -> session
        3. 名称匹配动态参数模式 -> dynamic
        4. 值匹配动态值模式（hex/base64 哈希） -> dynamic
        5. 来源为 cookie -> session
        6. 无法确定 -> unknown

        Args:
            name: 参数名
            value: 参数值
            context: 请求上下文

        Returns:
            ParameterInfo 对象
        """
        # 检查静态参数
        if name.lower() in STATIC_PARAM_NAMES:
            return ParameterInfo(
                name=name,
                value_sample=value,
                category="static",
                source="",  # source will be set by caller
                reasoning=f"参数名 '{name}' 匹配静态参数列表",
            )

        # 检查会话参数模式
        for pattern in SESSION_PARAM_PATTERNS:
            if pattern.match(name):
                return ParameterInfo(
                    name=name,
                    value_sample=value,
                    category="session",
                    source="",
                    reasoning=f"参数名 '{name}' 匹配会话参数模式",
                )

        # 检查 Bearer token 值
        if value.startswith("Bearer "):
            return ParameterInfo(
                name=name,
                value_sample=value,
                category="session",
                source="",
                reasoning=f"参数值包含 Bearer token",
            )

        # 检查动态参数名称模式
        for pattern in DYNAMIC_PARAM_PATTERNS:
            if pattern.match(name):
                return ParameterInfo(
                    name=name,
                    value_sample=value,
                    category="dynamic",
                    source="",
                    reasoning=f"参数名 '{name}' 匹配动态参数模式",
                )

        # 检查动态值模式
        for pattern in DYNAMIC_VALUE_PATTERNS:
            if pattern.match(value):
                return ParameterInfo(
                    name=name,
                    value_sample=value,
                    category="dynamic",
                    source="",
                    reasoning=f"参数值匹配动态值模式（hash/签名）",
                )

        # 无法确定
        return ParameterInfo(
            name=name,
            value_sample=value,
            category="unknown",
            source="",
            reasoning=f"无法确定参数 '{name}' 的分类",
        )

    def determine_reproducibility(
        self, params: List[ParameterInfo]
    ) -> Tuple[str, str]:
        """根据参数分类结果判定接口可复现性

        判定逻辑：
        - 无动态参数且无未知参数 -> reproducible
        - 有动态参数 -> complex
        - 仅有未知参数 -> unknown

        Args:
            params: 参数信息列表

        Returns:
            (reproducibility, reason) 元组
        """
        dynamic_params = [p for p in params if p.category == "dynamic"]
        unknown_params = [p for p in params if p.category == "unknown"]

        if not dynamic_params and not unknown_params:
            return ("reproducible", "所有参数均为静态或会话类型，可直接复现")
        elif dynamic_params:
            return ("complex", f"包含动态参数: {[p.name for p in dynamic_params]}")
        else:
            return ("unknown", f"包含未确定参数: {[p.name for p in unknown_params]}")

    def _detect_purpose(self, url: str) -> str:
        """从 URL 路径中检测接口用途"""
        if isinstance(self.llm_client, DefaultLLMClient):
            return self.llm_client.detect_purpose(url)

        # 对于非默认客户端，使用基本的路径匹配
        parsed = urlparse(url)
        path_lower = parsed.path.lower()

        for pattern, purpose in DefaultLLMClient.PURPOSE_PATTERNS.items():
            if pattern in path_lower:
                return purpose

        return "unknown"

    async def analyze_single(self, request: CapturedRequest) -> APIAnalysisResult:
        """分析单个请求

        流程：
        1. 提取参数
        2. 分类每个参数
        3. 判定可复现性
        4. 检测接口用途
        5. 返回分析结果

        Args:
            request: 捕获的请求对象

        Returns:
            APIAnalysisResult 分析结果
        """
        # 1. 提取参数
        raw_params = self.extract_parameters(request)

        # 2. 分类每个参数
        context = RequestContext(
            url=request.url,
            method=request.method,
            content_type=request.headers.get("Content-Type", ""),
        )

        classified_params: List[ParameterInfo] = []
        for name, value, source in raw_params:
            param_info = self.classify_parameter(name, value, context)
            # 设置来源
            param_info.source = source
            classified_params.append(param_info)

        # 对 cookie 来源的未知参数，默认归类为 session
        for param in classified_params:
            if param.source == "cookie" and param.category == "unknown":
                param.category = "session"
                param.reasoning = "Cookie 来源参数默认归类为会话参数"

        # 3. 判定可复现性
        reproducibility, reason = self.determine_reproducibility(classified_params)

        # 4. 检测接口用途
        purpose = self._detect_purpose(request.url)

        # 5. 提取 endpoint
        parsed_url = urlparse(request.url)
        endpoint = parsed_url.path

        # 计算置信度
        confidence = self._calculate_confidence(classified_params, purpose)

        return APIAnalysisResult(
            request_id=request.id,
            endpoint=endpoint,
            purpose=purpose,
            parameters=classified_params,
            reproducibility=reproducibility,
            reproducibility_reason=reason,
            confidence=confidence,
        )

    async def analyze_batch(
        self, requests: List[CapturedRequest]
    ) -> List[APIAnalysisResult]:
        """批量分析请求

        Args:
            requests: 捕获的请求列表

        Returns:
            分析结果列表
        """
        results = []
        for request in requests:
            result = await self.analyze_single(request)
            results.append(result)
        return results

    def _calculate_confidence(
        self, params: List[ParameterInfo], purpose: str
    ) -> float:
        """计算分析置信度

        基于：
        - 参数分类确定性（unknown 越少置信度越高）
        - 用途是否识别成功

        Returns:
            0.0 到 1.0 之间的置信度
        """
        if not params:
            # 无参数时，如果用途已知则高置信度
            return 0.8 if purpose != "unknown" else 0.5

        unknown_count = sum(1 for p in params if p.category == "unknown")
        unknown_ratio = unknown_count / len(params)

        # 基础置信度
        base_confidence = 1.0 - (unknown_ratio * 0.5)

        # 用途识别加分
        if purpose != "unknown":
            base_confidence = min(1.0, base_confidence + 0.1)
        else:
            base_confidence = max(0.0, base_confidence - 0.1)

        return round(base_confidence, 2)
