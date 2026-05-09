"""流量拦截模块 - 读取 capture_addon 写入的 JSON 文件并提供过滤和查询接口

本模块实现 TrafficInterceptor 类，负责：
- 管理录制状态（start_recording / stop_recording）
- 从存储目录读取 capture_addon.py 写入的 JSON 文件
- 实现 4 层过滤逻辑：静态资源过滤、域名黑名单、路径黑名单、API 白名单
- 支持用户自定义域名白名单/黑名单
- 提供 get_captured_requests() 和 get_stats() 查询方法

设计说明：
- mitmdump 作为独立进程运行（由 EnvironmentManager 启动）
- capture_addon.py 将捕获的请求写入 JSON 文件
- TrafficInterceptor 读取这些 JSON 文件并提供过滤/查询接口
"""

import json
import os
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from src.models import CapturedRequest, FilterRules


class TrafficInterceptor:
    """流量拦截器，读取 capture_addon 写入的 JSON 文件并提供过滤和查询接口。

    mitmdump 作为独立进程运行，capture_addon.py 将捕获的请求写入 JSON 文件。
    TrafficInterceptor 读取这些文件，应用 4 层过滤逻辑，并提供查询接口。

    使用示例:
        from src.models import FilterRules

        filter_rules = FilterRules(
            domain_blacklist=["analytics.example.com"],
            user_domain_whitelist=["api.myapp.com"],
        )
        interceptor = TrafficInterceptor(
            storage_path="./output/captures",
            filter_rules=filter_rules,
        )
        interceptor.start_recording()
        # ... 用户操作 App，mitmdump 捕获流量 ...
        interceptor.stop_recording()
        requests = interceptor.get_captured_requests()
        stats = interceptor.get_stats()
    """

    def __init__(self, storage_path: str, filter_rules: Optional[FilterRules] = None):
        """初始化 TrafficInterceptor。

        Args:
            storage_path: capture_addon.py 写入 JSON 文件的目录路径
            filter_rules: 过滤规则配置，为 None 时使用默认规则
        """
        self._storage_path = storage_path
        self._filter_rules = filter_rules or FilterRules()
        self._recording = False
        self._start_time: Optional[datetime] = None
        self._stop_time: Optional[datetime] = None

    @property
    def is_recording(self) -> bool:
        """是否正在录制。"""
        return self._recording

    @property
    def filter_rules(self) -> FilterRules:
        """当前过滤规则。"""
        return self._filter_rules

    @filter_rules.setter
    def filter_rules(self, rules: FilterRules) -> None:
        """更新过滤规则。"""
        self._filter_rules = rules

    def start_recording(self) -> None:
        """标记录制开始。

        记录开始时间，后续 get_captured_requests() 将只返回
        开始时间之后捕获的请求。

        Raises:
            RuntimeError: 如果已在录制中
        """
        if self._recording:
            raise RuntimeError("Already recording")
        self._recording = True
        self._start_time = datetime.now()
        self._stop_time = None

    def stop_recording(self) -> None:
        """标记录制停止。

        记录停止时间，后续 get_captured_requests() 将只返回
        开始时间到停止时间之间捕获的请求。

        Raises:
            RuntimeError: 如果未在录制中
        """
        if not self._recording:
            raise RuntimeError("Not recording")
        self._recording = False
        self._stop_time = datetime.now()

    def get_captured_requests(self) -> List[CapturedRequest]:
        """读取存储目录中的 JSON 文件，应用过滤规则后返回 CapturedRequest 列表。

        读取所有 JSON 文件，按时间戳排序，应用 4 层过滤逻辑，
        返回通过过滤的请求列表。

        Returns:
            过滤后的 CapturedRequest 对象列表，按时间戳排序
        """
        all_requests = self._read_all_json_files()

        # 按时间戳排序
        all_requests.sort(key=lambda r: r.timestamp)

        # 应用时间范围过滤（如果设置了录制时间范围）
        if self._start_time is not None:
            all_requests = [
                r for r in all_requests if r.timestamp >= self._start_time
            ]
        if self._stop_time is not None:
            all_requests = [
                r for r in all_requests if r.timestamp <= self._stop_time
            ]

        # 应用 4 层过滤
        filtered = [r for r in all_requests if self._should_keep(r)]
        return filtered

    def get_stats(self) -> dict:
        """返回捕获统计信息。

        Returns:
            包含统计信息的字典：
            - total_files: 存储目录中的 JSON 文件总数
            - total_filtered: 通过过滤的请求数
            - is_recording: 是否正在录制
            - start_time: 录制开始时间（ISO 格式字符串或 None）
            - stop_time: 录制停止时间（ISO 格式字符串或 None）
        """
        all_requests = self._read_all_json_files()
        filtered = [r for r in all_requests if self._should_keep(r)]

        return {
            "total_files": len(all_requests),
            "total_filtered": len(filtered),
            "is_recording": self._recording,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "stop_time": self._stop_time.isoformat() if self._stop_time else None,
        }

    def _read_all_json_files(self) -> List[CapturedRequest]:
        """读取存储目录中的所有 JSON 文件并转换为 CapturedRequest。

        Returns:
            CapturedRequest 对象列表
        """
        requests: List[CapturedRequest] = []

        if not os.path.isdir(self._storage_path):
            return requests

        for filename in os.listdir(self._storage_path):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self._storage_path, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                req = CapturedRequest.from_dict(data)
                requests.append(req)
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                # 跳过无法解析的文件
                continue

        return requests

    def _should_keep(self, request: CapturedRequest) -> bool:
        """应用 4 层过滤逻辑判断请求是否应保留。

        过滤顺序：
        1. 静态资源过滤：Content-Type 在黑名单中则排除
        2. 域名黑名单：域名匹配黑名单则排除
        3. 路径黑名单：路径匹配黑名单则排除
        4. API 白名单：Content-Type 含 json 或路径匹配 API 模式则保留

        额外规则：
        - 用户域名白名单：如果设置了，只保留白名单中的域名
        - 用户域名黑名单：如果设置了，排除黑名单中的域名

        Args:
            request: 待检查的请求

        Returns:
            True 表示请求应保留
        """
        parsed_url = urlparse(request.url)
        hostname = parsed_url.hostname or ""
        path = parsed_url.path or ""

        # 获取响应 Content-Type
        response_content_type = ""
        if request.response_headers:
            # Content-Type 头可能大小写不一致
            for key, value in request.response_headers.items():
                if key.lower() == "content-type":
                    response_content_type = value.lower()
                    break

        # === 用户域名白名单（如果设置了，只保留白名单中的域名）===
        if self._filter_rules.user_domain_whitelist:
            if not self._domain_matches_list(hostname, self._filter_rules.user_domain_whitelist):
                return False

        # === 用户域名黑名单 ===
        if self._filter_rules.user_domain_blacklist:
            if self._domain_matches_list(hostname, self._filter_rules.user_domain_blacklist):
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
        """检查 Content-Type 是否为静态资源（在黑名单中）。

        Args:
            content_type: 响应的 Content-Type（已转小写）

        Returns:
            True 表示是静态资源，应排除
        """
        for blacklisted in self._filter_rules.content_type_blacklist:
            if blacklisted.lower() in content_type:
                return True
        return False

    def _is_blacklisted_domain(self, hostname: str) -> bool:
        """检查域名是否在黑名单中。

        支持精确匹配和子域名匹配。

        Args:
            hostname: 请求的主机名

        Returns:
            True 表示域名在黑名单中，应排除
        """
        return self._domain_matches_list(hostname, self._filter_rules.domain_blacklist)

    def _is_blacklisted_path(self, path: str) -> bool:
        """检查路径是否在黑名单中。

        使用包含匹配（路径中包含黑名单中的模式即匹配）。

        Args:
            path: 请求的路径

        Returns:
            True 表示路径在黑名单中，应排除
        """
        for blacklisted_path in self._filter_rules.path_blacklist:
            if blacklisted_path in path:
                return True
        return False

    def _matches_api_whitelist(self, content_type: str, path: str) -> bool:
        """检查请求是否匹配 API 白名单。

        匹配条件（满足任一即可）：
        1. Content-Type 包含白名单中的关键词（如 "json"）
        2. 路径包含已知 API 模式（如 /api/、/v1/ 等）

        Args:
            content_type: 响应的 Content-Type（已转小写）
            path: 请求的路径

        Returns:
            True 表示匹配 API 白名单，应保留
        """
        # 检查 Content-Type 白名单
        for whitelisted in self._filter_rules.content_type_whitelist:
            if whitelisted.lower() in content_type:
                return True

        # 检查 API 路径模式
        for pattern in self._filter_rules.api_path_patterns:
            if pattern in path:
                return True

        return False

    @staticmethod
    def _domain_matches_list(hostname: str, domain_list: List[str]) -> bool:
        """检查主机名是否匹配域名列表中的任一项。

        支持精确匹配和子域名匹配。

        Args:
            hostname: 请求的主机名
            domain_list: 域名列表

        Returns:
            True 表示匹配列表中的某个域名
        """
        if not hostname:
            return False
        for domain in domain_list:
            if hostname == domain or hostname.endswith("." + domain):
                return True
        return False
