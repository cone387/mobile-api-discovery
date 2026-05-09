"""需求收集与引导模块

负责引导用户明确抓取目标（App 名称、数据类型、操作页面），
解析用户输入提取关键信息，并在信息完整时生成操作计划摘要。

核心设计原则：
- 通用性：不绑定任何特定 App
- 当用户一次性提供完整信息时跳过逐步引导
- 当信息不完整时返回缺失字段供 AI 追问
"""

import re
from typing import List, Optional

from .models import CaptureTarget, RequirementStatus


# 常见数据类型关键词映射
_DATA_TYPE_KEYWORDS = {
    "列表": "列表数据",
    "list": "列表数据",
    "详情": "详情数据",
    "detail": "详情数据",
    "搜索": "搜索结果",
    "search": "搜索结果",
    "媒体": "媒体播放地址",
    "视频": "媒体播放地址",
    "音频": "媒体播放地址",
    "播放": "媒体播放地址",
    "media": "媒体播放地址",
    "video": "媒体播放地址",
    "audio": "媒体播放地址",
    "全部": "全部接口数据",
    "所有": "全部接口数据",
    "all": "全部接口数据",
    "商品": "商品数据",
    "小说": "小说/章节数据",
    "章节": "小说/章节数据",
    "评论": "评论数据",
    "用户": "用户数据",
}

# 常见页面关键词映射
_PAGE_KEYWORDS = {
    "首页": "首页",
    "主页": "首页",
    "home": "首页",
    "搜索页": "搜索页",
    "search": "搜索页",
    "详情页": "详情页",
    "detail": "详情页",
    "播放页": "播放页",
    "play": "播放页",
    "列表页": "列表页",
    "分类页": "分类页",
    "category": "分类页",
    "个人中心": "个人中心",
    "我的": "个人中心",
    "profile": "个人中心",
}

# 必填字段定义
_REQUIRED_FIELDS = ["app_name", "target_data", "operation_pages"]


class RequirementCollector:
    """需求收集器

    负责解析用户输入，提取抓取目标信息，
    并在信息不完整时提供引导。
    """

    def analyze_input(self, user_message: str) -> RequirementStatus:
        """解析用户输入，提取抓取目标信息

        从自然语言输入中提取 app_name、target_data、operation_pages，
        返回当前收集状态。

        Args:
            user_message: 用户的自然语言输入

        Returns:
            RequirementStatus: 包含是否完整、缺失字段和提示消息
        """
        target = self._extract_target(user_message)
        missing = self.get_missing_fields(target)

        if not missing:
            return RequirementStatus(
                is_complete=True,
                missing_fields=[],
                message=self.generate_summary(target),
            )

        return RequirementStatus(
            is_complete=False,
            missing_fields=missing,
            message=self._generate_guidance(missing),
        )

    def get_missing_fields(self, target: CaptureTarget) -> List[str]:
        """返回缺失的必填字段列表

        检查 CaptureTarget 中哪些必填字段为空。

        Args:
            target: 当前的抓取目标

        Returns:
            缺失字段名列表
        """
        missing = []
        if not target.app_name or not target.app_name.strip():
            missing.append("app_name")
        if not target.target_data or not target.target_data.strip():
            missing.append("target_data")
        if not target.operation_pages or not target.operation_pages.strip():
            missing.append("operation_pages")
        return missing

    def generate_summary(self, target: CaptureTarget) -> str:
        """生成操作计划摘要

        当所有必填字段完整时，生成供用户确认的操作计划。

        Args:
            target: 完整的抓取目标

        Returns:
            操作计划摘要文本
        """
        lines = [
            "## 操作计划摘要",
            "",
            f"**目标 App**: {target.app_name}",
            f"**期望数据**: {target.target_data}",
            f"**操作页面**: {target.operation_pages}",
        ]

        if target.filter_domains:
            lines.append(f"**域名白名单**: {', '.join(target.filter_domains)}")

        lines.extend([
            "",
            "### 执行步骤",
            "1. 配置抓包环境（代理 + 证书）",
            "2. 请您在手机上操作以上页面",
            "3. 操作完成后通知我，开始分析流量",
            "4. 生成接口分析报告",
            "",
            "请确认以上信息是否正确，确认后将开始环境准备。",
        ])

        return "\n".join(lines)

    def is_complete(self, target: CaptureTarget) -> bool:
        """判断目标信息是否完整

        Args:
            target: 当前的抓取目标

        Returns:
            True 如果所有必填字段都已填写
        """
        return len(self.get_missing_fields(target)) == 0

    def _extract_target(self, user_message: str) -> CaptureTarget:
        """从用户输入中提取抓取目标信息

        使用关键词匹配和模式识别从自然语言中提取结构化信息。

        Args:
            user_message: 用户的自然语言输入

        Returns:
            提取到的 CaptureTarget（可能部分字段为空）
        """
        app_name = self._extract_app_name(user_message)
        target_data = self._extract_target_data(user_message)
        operation_pages = self._extract_operation_pages(user_message)
        filter_domains = self._extract_filter_domains(user_message)

        return CaptureTarget(
            app_name=app_name,
            target_data=target_data,
            operation_pages=operation_pages,
            filter_domains=filter_domains if filter_domains else None,
        )

    def _extract_app_name(self, text: str) -> str:
        """提取 App 名称

        尝试从文本中识别 App 名称，支持多种表达方式。
        """
        # 常见的非 App 名称词汇（助词、动词等）
        _non_app_words = {
            "一下", "一些", "这个", "那个", "什么", "哪个", "所有",
            "全部", "某个", "某些", "帮我", "帮忙", "可以", "能否",
        }

        # 模式: "抓取/分析 XXX 的接口" 或 "XXX App"
        patterns = [
            r"(?:抓取|分析|捕获|逆向|抓包)\s*[「「]?([^\s「」」,，。、的]{2,15}?)[」」]?\s*(?:的|app|应用|接口|api)",
            r"(?:目标|target)\s*(?:app|应用)?\s*[:：]\s*[「「]?([^\s「」」,，。、]{2,15}?)[」」]?(?:\s|$|,|，|。)",
            r"[「「]([^\s「」」,，。、]{2,15}?)[」」]\s*(?:的|app|应用|接口)",
            r"(?:app|应用)\s*[:：]\s*[「「]?([^\s「」」,，。、]{2,15}?)[」」]?(?:\s|$|,|，|。)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name and len(name) >= 2 and name not in _non_app_words:
                    return name

        return ""

    def _extract_target_data(self, text: str) -> str:
        """提取期望获取的数据类型

        通过关键词匹配识别用户想要的数据类型。
        """
        # 先尝试显式声明模式
        explicit_patterns = [
            r"(?:想要|需要|获取|抓取|期望|希望得到)\s*(?:的\s*)?(.{2,30}?)(?:数据|接口|信息|内容)",
            r"(?:数据|data)\s*[:：]\s*(.{2,30}?)(?:\s|$|,|，|。)",
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data_desc = match.group(1).strip()
                if data_desc and len(data_desc) >= 2:
                    return data_desc

        # 通过关键词匹配
        found_types = []
        text_lower = text.lower()
        for keyword, data_type in _DATA_TYPE_KEYWORDS.items():
            if keyword in text_lower and data_type not in found_types:
                found_types.append(data_type)

        if found_types:
            return "、".join(found_types)

        return ""

    def _extract_operation_pages(self, text: str) -> str:
        """提取需要操作的页面

        通过关键词匹配识别用户需要操作的页面。
        """
        # 先尝试显式声明模式
        explicit_patterns = [
            r"(?:操作|浏览|打开|进入|访问)\s*(?:的?\s*)?(?:页面|page)\s*[:：]?\s*(.{2,50}?)(?:\s*$|。)",
            r"(?:页面|page)\s*[:：]\s*(.{2,50}?)(?:\s|$|,|，|。)",
        ]

        for pattern in explicit_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pages_desc = match.group(1).strip()
                if pages_desc and len(pages_desc) >= 2:
                    return pages_desc

        # 通过关键词匹配
        found_pages = []
        text_lower = text.lower()
        for keyword, page_name in _PAGE_KEYWORDS.items():
            if keyword in text_lower and page_name not in found_pages:
                found_pages.append(page_name)

        if found_pages:
            return "、".join(found_pages)

        return ""

    def _extract_filter_domains(self, text: str) -> Optional[List[str]]:
        """提取用户指定的域名过滤规则

        识别用户提供的域名白名单。
        """
        # 模式: "域名: xxx.com, yyy.com" 或 "只关注 xxx.com"
        patterns = [
            r"(?:域名|domain)\s*[:：]\s*([a-zA-Z0-9.,\s\-]+\.[a-zA-Z]{2,}(?:\s*[,，、]\s*[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})*)",
            r"(?:只关注|只看|仅关注)\s*([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}(?:\s*[,，、]\s*[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                domains_str = match.group(1)
                domains = re.split(r"[,，、\s]+", domains_str)
                domains = [d.strip() for d in domains if d.strip() and "." in d]
                if domains:
                    return domains

        return None

    def _generate_guidance(self, missing_fields: List[str]) -> str:
        """根据缺失字段生成引导提示

        Args:
            missing_fields: 缺失的字段名列表

        Returns:
            引导提示文本
        """
        guidance_map = {
            "app_name": "请告诉我您要抓取哪个 App 的接口？",
            "target_data": (
                "请告诉我您期望获取什么数据？常见选项：\n"
                "- 列表数据（商品列表、文章列表等）\n"
                "- 详情数据（商品详情、文章内容等）\n"
                "- 搜索结果\n"
                "- 媒体播放地址（视频、音频等）\n"
                "- 全部接口数据"
            ),
            "operation_pages": (
                "请告诉我您需要操作哪些页面？常见选项：\n"
                "- 首页列表\n"
                "- 搜索页\n"
                "- 详情页\n"
                "- 播放页\n"
                "- 分类页"
            ),
        }

        messages = []
        for field_name in missing_fields:
            if field_name in guidance_map:
                messages.append(guidance_map[field_name])

        return "\n\n".join(messages)
