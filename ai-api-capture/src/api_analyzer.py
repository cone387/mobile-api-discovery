"""接口分析模块 - 基于通用响应结构模式识别接口类型

实现功能：
- classify_api_type: 基于响应结构模式识别接口类型 (LIST/PAGINATION/DETAIL/MEDIA/CONFIG/AUX)
- classify_parameters: 将请求参数分为 static/session/dynamic 三类
- detect_data_links: 自动识别接口间的数据链路关系
- analyze_all: 结合用户目标数据描述进行综合分析
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

from src.models import (
    AnalysisReport,
    APIAnalysisResult,
    APIType,
    CapturedRequest,
    CaptureTarget,
    DataLink,
    ParameterInfo,
)


# ============================================================
# 参数分类规则
# ============================================================

# 静态参数名称（固定值，不随请求变化）
STATIC_PARAM_NAMES: Set[str] = {
    "version", "platform", "os", "brand", "model", "channel",
    "appversion", "app_version", "pname", "channelcode", "channel_code",
    "app_ver", "os_version", "os_ver", "osversion", "device_model",
    "device_type", "devicemodel", "language", "lang", "locale",
    "ver", "build", "build_number", "sdk_version", "api_version",
    "client_type", "device_id", "device_brand", "screen_width",
    "screen_height", "resolution", "network_type", "carrier",
}

# 会话参数名称模式（用户身份标识）
SESSION_PARAM_PATTERNS: List[re.Pattern] = [
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*auth.*", re.IGNORECASE),
    re.compile(r".*session.*", re.IGNORECASE),
    re.compile(r".*cookie.*", re.IGNORECASE),
    re.compile(r"^uid$", re.IGNORECASE),
    re.compile(r"^user[_-]?id$", re.IGNORECASE),
    re.compile(r"^authorization$", re.IGNORECASE),
]

# 动态参数名称模式（每次请求值不同）
DYNAMIC_PARAM_PATTERNS: List[re.Pattern] = [
    re.compile(r".*sign.*", re.IGNORECASE),
    re.compile(r".*nonce.*", re.IGNORECASE),
    re.compile(r".*timestamp.*", re.IGNORECASE),
    re.compile(r"^ts$", re.IGNORECASE),
    re.compile(r"^t$", re.IGNORECASE),
    re.compile(r"^signature$", re.IGNORECASE),
    re.compile(r"^boxid$", re.IGNORECASE),
    re.compile(r"^box_id$", re.IGNORECASE),
]

# 分页参数名称
PAGINATION_PARAM_NAMES: Set[str] = {
    "page", "pageno", "page_no", "pagenumber", "page_number",
    "offset", "cursor", "pageflag", "page_flag",
    "pageindex", "page_index", "start", "limit",
    "pagesize", "page_size", "per_page", "perpage", "size",
}

# 分页响应标识字段
PAGINATION_RESPONSE_FIELDS: Set[str] = {
    "hasmore", "has_more", "hasnext", "has_next",
    "total", "totalcount", "total_count", "totalpage", "total_page",
    "totalpages", "total_pages", "nextpage", "next_page",
    "nextcursor", "next_cursor", "pagecount", "page_count",
}

# 名称/标题类字段名
NAME_TITLE_FIELDS: Set[str] = {
    "name", "title", "label", "text", "desc", "description",
    "nickname", "username", "displayname", "display_name",
    "heading", "subject", "caption",
}

# 配置类字段名
CONFIG_FIELDS: Set[str] = {
    "config", "settings", "setting", "version", "configuration",
    "preferences", "options", "feature_flags", "features",
}

# 媒体 URL 模式
MEDIA_URL_PATTERNS: List[re.Pattern] = [
    re.compile(r"\.mp4", re.IGNORECASE),
    re.compile(r"\.m3u8", re.IGNORECASE),
    re.compile(r"\.mp3", re.IGNORECASE),
    re.compile(r"\.flv", re.IGNORECASE),
    re.compile(r"\.m4a", re.IGNORECASE),
    re.compile(r"/video/", re.IGNORECASE),
    re.compile(r"/play/", re.IGNORECASE),
    re.compile(r"/stream/", re.IGNORECASE),
    re.compile(r"/media/", re.IGNORECASE),
]


class APIAnalyzer:
    """通用接口分析器 - 基于响应结构模式识别接口类型"""

    def __init__(self) -> None:
        """初始化分析器"""
        # 用于 DETAIL 识别时参考的列表元素平均字段数
        self._list_element_field_counts: List[int] = []

    def classify_api_type(self, request: CapturedRequest) -> APIType:
        """基于通用响应结构模式识别接口类型

        识别优先级：
        1. MEDIA: 响应含媒体 URL 模式
        2. PAGINATION: 请求含分页参数 + 响应含分页标识
        3. LIST: 响应含数组，元素为结构化对象（含 id + 名称类字段）
        4. DETAIL: 请求含 id 参数 + 响应字段数 > 列表元素字段数 * 1.5
        5. CONFIG: 响应含 config/settings/version 字段
        6. AUX: 其他

        Args:
            request: 捕获的请求对象

        Returns:
            APIType 枚举值
        """
        response_data = self._parse_response_body(request.response_body)
        request_params = self._extract_all_params(request)

        # 1. MEDIA 识别
        if self._is_media_type(response_data):
            return APIType.MEDIA

        # 2. PAGINATION 识别
        if self._is_pagination_type(request_params, response_data):
            return APIType.PAGINATION

        # 3. LIST 识别
        if self._is_list_type(response_data):
            return APIType.LIST

        # 4. DETAIL 识别
        if self._is_detail_type(request_params, response_data):
            return APIType.DETAIL

        # 5. CONFIG 识别
        if self._is_config_type(response_data):
            return APIType.CONFIG

        # 6. AUX
        return APIType.AUX

    def classify_parameters(self, request: CapturedRequest) -> List[ParameterInfo]:
        """将请求参数分为 static/session/dynamic 三类

        分类规则：
        - static: version, platform, os, brand, model, channel 等固定值
        - session: token, userId, session, uid, authorization 等用户身份标识
        - dynamic: sign, nonce, timestamp, signature, boxId 等每次请求值不同

        Args:
            request: 捕获的请求对象

        Returns:
            参数信息列表
        """
        raw_params = self._extract_raw_params(request)
        classified: List[ParameterInfo] = []

        for name, value, source in raw_params:
            category = self._classify_single_param(name, value)
            classified.append(ParameterInfo(
                name=name,
                value_sample=value,
                category=category,
                source=source,
            ))

        return classified

    def detect_data_links(self, results: List[APIAnalysisResult]) -> List[DataLink]:
        """检测接口间的数据链路关系

        逻辑：
        - 从 LIST 类型接口响应中提取 ID 字段值
        - 检查 DETAIL 或 MEDIA 类型接口请求中是否使用了该 ID
        - 建立调用链（list → detail → media）

        Args:
            results: 所有接口分析结果列表

        Returns:
            数据链路列表
        """
        links: List[DataLink] = []

        # 收集 LIST 类型接口的 ID 值
        list_results = [r for r in results if r.api_type == APIType.LIST]
        detail_results = [r for r in results if r.api_type == APIType.DETAIL]
        media_results = [r for r in results if r.api_type == APIType.MEDIA]

        # 从 LIST 结果中提取 ID 值（需要原始请求数据）
        # 由于 APIAnalysisResult 不包含原始响应，我们通过 request_id 关联
        # 这里使用 _list_id_values 缓存（在 analyze_all 中填充）
        list_ids: Dict[str, Set[str]] = getattr(self, "_list_id_values", {})

        for list_endpoint, id_values in list_ids.items():
            if not id_values:
                continue

            # 检查 DETAIL 接口
            for detail_result in detail_results:
                # 检查 detail 接口的参数中是否包含 list 中的 ID
                for param in detail_result.parameters:
                    if param.value_sample in id_values:
                        links.append(DataLink(
                            source_endpoint=list_endpoint,
                            target_endpoint=detail_result.endpoint,
                            link_field=param.name,
                            link_type="list_to_detail",
                        ))
                        break

            # 检查 MEDIA 接口
            for media_result in media_results:
                for param in media_result.parameters:
                    if param.value_sample in id_values:
                        links.append(DataLink(
                            source_endpoint=list_endpoint,
                            target_endpoint=media_result.endpoint,
                            link_field=param.name,
                            link_type="list_to_media",
                        ))
                        break

        # 检查 detail → media 链路
        detail_ids: Dict[str, Set[str]] = getattr(self, "_detail_id_values", {})
        for detail_endpoint, id_values in detail_ids.items():
            if not id_values:
                continue
            for media_result in media_results:
                for param in media_result.parameters:
                    if param.value_sample in id_values:
                        links.append(DataLink(
                            source_endpoint=detail_endpoint,
                            target_endpoint=media_result.endpoint,
                            link_field=param.name,
                            link_type="detail_to_media",
                        ))
                        break

        return links

    def analyze_all(
        self, requests: List[CapturedRequest], target: CaptureTarget
    ) -> AnalysisReport:
        """综合分析所有请求，结合用户目标数据描述

        Args:
            requests: 捕获的请求列表
            target: 用户的抓取目标

        Returns:
            完整的分析报告
        """
        # 重置缓存
        self._list_id_values: Dict[str, Set[str]] = {}
        self._detail_id_values: Dict[str, Set[str]] = {}
        self._list_element_field_counts = []

        results: List[APIAnalysisResult] = []

        # 按 endpoint 分组统计调用次数
        endpoint_counts: Dict[str, int] = {}
        for req in requests:
            parsed = urlparse(req.url)
            endpoint = parsed.path
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1

        # 去重：每个 endpoint 只分析一次（取第一个请求）
        seen_endpoints: Set[str] = set()
        unique_requests: List[CapturedRequest] = []
        for req in requests:
            parsed = urlparse(req.url)
            endpoint = parsed.path
            if endpoint not in seen_endpoints:
                seen_endpoints.add(endpoint)
                unique_requests.append(req)

        # 第一遍：分类所有接口并收集 LIST 元素字段数
        for req in unique_requests:
            api_type = self.classify_api_type(req)
            if api_type in (APIType.LIST, APIType.PAGINATION):
                response_data = self._parse_response_body(req.response_body)
                arr = self._find_main_array(response_data)
                if arr and len(arr) > 0 and isinstance(arr[0], dict):
                    self._list_element_field_counts.append(len(arr[0]))
                    # 提取 ID 值
                    parsed = urlparse(req.url)
                    endpoint = parsed.path
                    id_values = set()
                    for item in arr:
                        if isinstance(item, dict):
                            for key in ("id", "Id", "ID", "item_id", "itemId"):
                                if key in item and item[key] is not None:
                                    id_values.add(str(item[key]))
                                    break
                    self._list_id_values[endpoint] = id_values

        # 第二遍：完整分析（DETAIL 需要参考 LIST 字段数）
        for req in unique_requests:
            parsed = urlparse(req.url)
            endpoint = parsed.path
            call_count = endpoint_counts.get(endpoint, 1)

            api_type = self.classify_api_type(req)
            parameters = self.classify_parameters(req)

            # 检查是否有签名
            signature_fields = [
                p.name for p in parameters if p.category == "dynamic"
            ]
            has_signature = len(signature_fields) > 0

            # 检查是否匹配用户目标
            matches_target = self._matches_user_target(
                req, api_type, target
            )

            # 收集 DETAIL 接口的 ID 值（用于 detail→media 链路）
            if api_type == APIType.DETAIL:
                response_data = self._parse_response_body(req.response_body)
                if isinstance(response_data, dict):
                    id_values = set()
                    for key in ("id", "Id", "ID", "item_id", "itemId"):
                        if key in response_data and response_data[key] is not None:
                            id_values.add(str(response_data[key]))
                            break
                    self._detail_id_values[endpoint] = id_values

            results.append(APIAnalysisResult(
                request_id=req.id,
                endpoint=endpoint,
                api_type=api_type,
                parameters=parameters,
                has_signature=has_signature,
                signature_fields=signature_fields,
                matches_target=matches_target,
                call_count=call_count,
            ))

        # 检测数据链路
        data_links = self.detect_data_links(results)

        # 统计
        target_matched = sum(1 for r in results if r.matches_target)

        return AnalysisReport(
            target=target,
            results=results,
            data_links=data_links,
            total_captured=len(requests),
            total_analyzed=len(results),
            target_matched=target_matched,
            generated_at=datetime.now(),
        )

    # ============================================================
    # 内部方法：类型识别
    # ============================================================

    def _parse_response_body(self, response_body: Optional[str]) -> Any:
        """解析响应体 JSON"""
        if not response_body:
            return None
        try:
            return json.loads(response_body)
        except (json.JSONDecodeError, TypeError):
            return None

    def _extract_all_params(self, request: CapturedRequest) -> Dict[str, str]:
        """提取请求中的所有参数（URL query + body）为扁平字典"""
        params: Dict[str, str] = {}

        # URL query params
        parsed = urlparse(request.url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        for name, values in query_params.items():
            params[name.lower()] = values[0] if values else ""

        # Body params
        if request.body:
            try:
                body_data = json.loads(request.body)
                if isinstance(body_data, dict):
                    for key, value in body_data.items():
                        params[key.lower()] = str(value)
            except (json.JSONDecodeError, TypeError):
                # Try form data
                try:
                    form_params = parse_qs(request.body, keep_blank_values=True)
                    for name, values in form_params.items():
                        params[name.lower()] = values[0] if values else ""
                except Exception:
                    pass

        return params

    def _is_media_type(self, response_data: Any) -> bool:
        """检查响应是否包含媒体 URL 模式"""
        if response_data is None:
            return False
        text = json.dumps(response_data) if not isinstance(response_data, str) else response_data
        for pattern in MEDIA_URL_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def _is_pagination_type(
        self, request_params: Dict[str, str], response_data: Any
    ) -> bool:
        """检查是否为分页接口"""
        # 请求必须含分页参数
        has_pagination_param = any(
            name in PAGINATION_PARAM_NAMES for name in request_params.keys()
        )
        if not has_pagination_param:
            return False

        # 响应必须含分页标识
        if not isinstance(response_data, dict):
            return False

        response_fields = self._get_all_field_names(response_data)
        has_pagination_indicator = any(
            f.lower() in PAGINATION_RESPONSE_FIELDS for f in response_fields
        )
        return has_pagination_indicator

    def _is_list_type(self, response_data: Any) -> bool:
        """检查响应是否为列表类型

        条件：响应含数组，数组元素为结构化对象（含 id 字段 + 至少一个名称类字段）
        """
        arr = self._find_main_array(response_data)
        if arr is None or len(arr) == 0:
            return False

        # 检查第一个元素是否为结构化对象
        first_elem = arr[0]
        if not isinstance(first_elem, dict):
            return False

        # 检查是否含 id 字段
        elem_keys_lower = {k.lower() for k in first_elem.keys()}
        has_id = "id" in elem_keys_lower or any(
            "id" in k for k in elem_keys_lower
        )
        if not has_id:
            return False

        # 检查是否含至少一个名称/标题类字段
        has_name_field = any(
            k.lower() in NAME_TITLE_FIELDS for k in first_elem.keys()
        )
        return has_name_field

    def _is_detail_type(
        self, request_params: Dict[str, str], response_data: Any
    ) -> bool:
        """检查是否为详情接口

        条件：请求含 id 参数 + 响应字段数 > 列表元素字段数 * 1.5
        """
        # 请求必须含 id 参数
        has_id_param = any(
            "id" in name for name in request_params.keys()
        )
        if not has_id_param:
            return False

        # 响应必须是对象
        if not isinstance(response_data, dict):
            return False

        # 获取响应字段数（递归展开一层）
        response_field_count = self._count_fields(response_data)

        # 与列表元素字段数比较
        if self._list_element_field_counts:
            avg_list_fields = sum(self._list_element_field_counts) / len(
                self._list_element_field_counts
            )
            if avg_list_fields > 0 and response_field_count > avg_list_fields * 1.5:
                return True

        # 如果没有列表参考，但有 id 参数且响应字段较多（>5），也认为是 DETAIL
        if response_field_count > 5:
            return True

        return False

    def _is_config_type(self, response_data: Any) -> bool:
        """检查响应是否为配置类型"""
        if not isinstance(response_data, dict):
            return False

        all_fields = self._get_all_field_names(response_data)
        has_config_field = any(
            f.lower() in CONFIG_FIELDS for f in all_fields
        )
        return has_config_field

    # ============================================================
    # 内部方法：辅助函数
    # ============================================================

    def _find_main_array(self, data: Any) -> Optional[List]:
        """在响应数据中查找主要数组

        支持：
        - 顶层就是数组
        - 嵌套在 data/list/items/results 等字段中的数组
        """
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            # 常见的数组字段名
            array_field_names = [
                "data", "list", "items", "results", "records",
                "rows", "content", "entries", "elements",
            ]
            for field_name in array_field_names:
                for key in data.keys():
                    if key.lower() == field_name and isinstance(data[key], list):
                        return data[key]

            # 如果没找到，检查所有值中是否有数组
            for value in data.values():
                if isinstance(value, list) and len(value) > 0:
                    if isinstance(value[0], dict):
                        return value

        return None

    def _get_all_field_names(self, data: Dict) -> Set[str]:
        """获取字典中所有字段名（包括一层嵌套）"""
        fields: Set[str] = set()
        if not isinstance(data, dict):
            return fields

        for key, value in data.items():
            fields.add(key)
            if isinstance(value, dict):
                for sub_key in value.keys():
                    fields.add(sub_key)

        return fields

    def _count_fields(self, data: Any) -> int:
        """计算数据中的字段数量（顶层）"""
        if isinstance(data, dict):
            return len(data)
        return 0

    def _extract_raw_params(
        self, request: CapturedRequest
    ) -> List[Tuple[str, str, str]]:
        """从请求中提取所有原始参数

        Returns:
            参数列表，每项为 (name, value, source) 元组
        """
        params: List[Tuple[str, str, str]] = []

        # 1. URL query params
        parsed = urlparse(request.url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        for name, values in query_params.items():
            value = values[0] if values else ""
            params.append((name, value, "query"))

        # 2. Headers (非标准头部)
        standard_headers = {
            "host", "connection", "content-length", "content-type",
            "accept", "accept-encoding", "accept-language", "cache-control",
            "user-agent", "referer", "origin",
        }
        for name, value in request.headers.items():
            if name.lower() not in standard_headers:
                params.append((name, str(value), "header"))

        # 3. Body params
        if request.body:
            try:
                body_data = json.loads(request.body)
                if isinstance(body_data, dict):
                    for key, value in body_data.items():
                        params.append((key, str(value), "body"))
            except (json.JSONDecodeError, TypeError):
                # Try form data
                try:
                    form_params = parse_qs(request.body, keep_blank_values=True)
                    for name, values in form_params.items():
                        value = values[0] if values else ""
                        params.append((name, value, "body"))
                except Exception:
                    pass

        # 4. Cookies
        cookie_value = request.headers.get("Cookie") or request.headers.get("cookie")
        if cookie_value:
            cookies = cookie_value.split(";")
            for cookie in cookies:
                cookie = cookie.strip()
                if "=" in cookie:
                    name, value = cookie.split("=", 1)
                    params.append((name.strip(), value.strip(), "cookie"))

        return params

    def _classify_single_param(self, name: str, value: str) -> str:
        """对单个参数进行分类

        Returns:
            分类结果: "static", "session", "dynamic"
        """
        name_lower = name.lower()

        # 1. 静态参数
        if name_lower in STATIC_PARAM_NAMES:
            return "static"

        # 2. 会话参数
        for pattern in SESSION_PARAM_PATTERNS:
            if pattern.match(name):
                return "session"

        # 3. 动态参数（名称匹配）
        for pattern in DYNAMIC_PARAM_PATTERNS:
            if pattern.match(name):
                return "dynamic"

        # 4. 动态参数（值模式：hex hash）
        if re.match(r"^[0-9a-fA-F]{32}$", value):  # MD5
            return "dynamic"
        if re.match(r"^[0-9a-fA-F]{40}$", value):  # SHA1
            return "dynamic"
        if re.match(r"^[0-9a-fA-F]{64}$", value):  # SHA256
            return "dynamic"

        # 5. 默认归为 static（对于无法确定的参数，按设计文档要求只有三类）
        return "static"

    def _matches_user_target(
        self,
        request: CapturedRequest,
        api_type: APIType,
        target: CaptureTarget,
    ) -> bool:
        """判断接口是否匹配用户目标

        基于用户的 target_data 描述和接口类型进行匹配
        """
        if not target.target_data:
            return False

        target_keywords = target.target_data.lower().split()
        if not target_keywords:
            return False

        # 检查 URL 路径是否包含目标关键词
        parsed = urlparse(request.url)
        path_lower = parsed.path.lower()

        for keyword in target_keywords:
            if len(keyword) > 2 and keyword in path_lower:
                return True

        # 检查响应内容是否包含目标关键词
        if request.response_body:
            response_lower = request.response_body.lower()
            match_count = sum(
                1 for kw in target_keywords
                if len(kw) > 2 and kw in response_lower
            )
            if match_count >= 2:
                return True

        # LIST 和 DETAIL 类型更可能匹配用户目标
        if api_type in (APIType.LIST, APIType.DETAIL, APIType.MEDIA):
            # 检查 endpoint 中是否有相关词
            for keyword in target_keywords:
                if len(keyword) > 2 and keyword in path_lower:
                    return True

        return False
