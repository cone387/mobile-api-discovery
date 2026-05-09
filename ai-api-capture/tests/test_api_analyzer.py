"""API Analyzer 模块测试

测试覆盖：
- classify_api_type: 接口类型识别（LIST/PAGINATION/DETAIL/MEDIA/CONFIG/AUX）
- classify_parameters: 参数分类（static/session/dynamic）
- detect_data_links: 数据链路检测
- analyze_all: 综合分析（目标匹配、报告生成）
"""

import json
import pytest
from datetime import datetime

from src.api_analyzer import APIAnalyzer
from src.models import (
    APIAnalysisResult,
    APIType,
    AnalysisReport,
    CapturedRequest,
    CaptureTarget,
    DataLink,
    ParameterInfo,
)


# === Fixtures ===


@pytest.fixture
def analyzer():
    """创建 APIAnalyzer 实例"""
    return APIAnalyzer()


def make_request(
    url: str = "https://api.example.com/v1/data",
    method: str = "GET",
    headers: dict = None,
    body: str = None,
    response_body: str = None,
    response_status: int = 200,
    request_id: str = "req-001",
) -> CapturedRequest:
    """辅助函数：创建 CapturedRequest"""
    return CapturedRequest(
        id=request_id,
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        method=method,
        url=url,
        headers=headers or {},
        body=body,
        response_status=response_status,
        response_headers={"Content-Type": "application/json"},
        response_body=response_body,
        is_decrypted=True,
    )


# === 接口类型识别测试 ===


class TestClassifyAPIType:
    """测试 classify_api_type 方法"""

    def test_list_type_basic(self, analyzer):
        """LIST: 响应含数组，元素含 id + 名称字段"""
        response = json.dumps({
            "data": [
                {"id": 1, "name": "Item 1", "price": 10},
                {"id": 2, "name": "Item 2", "price": 20},
            ]
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.LIST

    def test_list_type_with_title_field(self, analyzer):
        """LIST: 元素含 id + title 字段"""
        response = json.dumps({
            "items": [
                {"id": "abc", "title": "Article 1", "author": "John"},
                {"id": "def", "title": "Article 2", "author": "Jane"},
            ]
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.LIST

    def test_list_type_top_level_array(self, analyzer):
        """LIST: 顶层就是数组"""
        response = json.dumps([
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
        ])
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.LIST

    def test_not_list_without_id(self, analyzer):
        """非 LIST: 数组元素无 id 字段"""
        response = json.dumps({
            "data": [
                {"value": 1, "label": "Option 1"},
                {"value": 2, "label": "Option 2"},
            ]
        })
        req = make_request(response_body=response)
        # 没有 id 字段，不应该是 LIST
        result = analyzer.classify_api_type(req)
        assert result != APIType.LIST

    def test_not_list_without_name_field(self, analyzer):
        """非 LIST: 数组元素有 id 但无名称类字段"""
        response = json.dumps({
            "data": [
                {"id": 1, "count": 10, "status": "active"},
                {"id": 2, "count": 20, "status": "inactive"},
            ]
        })
        req = make_request(response_body=response)
        result = analyzer.classify_api_type(req)
        assert result != APIType.LIST

    def test_pagination_type(self, analyzer):
        """PAGINATION: 请求含分页参数 + 响应含分页标识"""
        response = json.dumps({
            "data": [{"id": 1, "name": "Item"}],
            "hasMore": True,
            "total": 100,
        })
        req = make_request(
            url="https://api.example.com/v1/list?page=1&pageSize=20",
            response_body=response,
        )
        assert analyzer.classify_api_type(req) == APIType.PAGINATION

    def test_pagination_with_offset(self, analyzer):
        """PAGINATION: offset 参数 + total 响应"""
        response = json.dumps({
            "items": [{"id": 1, "name": "Item"}],
            "total": 50,
        })
        req = make_request(
            url="https://api.example.com/v1/items?offset=0&limit=10",
            response_body=response,
        )
        assert analyzer.classify_api_type(req) == APIType.PAGINATION

    def test_pagination_with_cursor(self, analyzer):
        """PAGINATION: cursor 参数 + nextCursor 响应"""
        response = json.dumps({
            "data": [{"id": 1, "name": "Item"}],
            "nextCursor": "abc123",
        })
        req = make_request(
            url="https://api.example.com/v1/feed?cursor=xyz",
            response_body=response,
        )
        assert analyzer.classify_api_type(req) == APIType.PAGINATION

    def test_detail_type(self, analyzer):
        """DETAIL: 请求含 id 参数 + 响应字段多"""
        # 先设置列表元素字段数参考
        analyzer._list_element_field_counts = [3]

        response = json.dumps({
            "id": 123,
            "name": "Product",
            "description": "A great product",
            "price": 99.9,
            "category": "electronics",
            "brand": "BrandX",
            "stock": 50,
        })
        req = make_request(
            url="https://api.example.com/v1/product?id=123",
            response_body=response,
        )
        assert analyzer.classify_api_type(req) == APIType.DETAIL

    def test_detail_type_with_item_id(self, analyzer):
        """DETAIL: 请求含 itemId 参数"""
        analyzer._list_element_field_counts = [3]

        response = json.dumps({
            "id": 456,
            "title": "Article",
            "content": "Long content here",
            "author": "John",
            "created_at": "2024-01-01",
            "tags": ["tech", "ai"],
        })
        req = make_request(
            url="https://api.example.com/v1/article?itemId=456",
            response_body=response,
        )
        assert analyzer.classify_api_type(req) == APIType.DETAIL

    def test_media_type_mp4(self, analyzer):
        """MEDIA: 响应含 .mp4 URL"""
        response = json.dumps({
            "url": "https://cdn.example.com/video/123.mp4",
            "quality": "1080p",
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.MEDIA

    def test_media_type_m3u8(self, analyzer):
        """MEDIA: 响应含 .m3u8 URL"""
        response = json.dumps({
            "playUrl": "https://cdn.example.com/stream/live.m3u8",
            "title": "Live Stream",
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.MEDIA

    def test_media_type_mp3(self, analyzer):
        """MEDIA: 响应含 .mp3 URL"""
        response = json.dumps({
            "audioUrl": "https://cdn.example.com/audio/song.mp3",
            "duration": 240,
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.MEDIA

    def test_media_type_path_pattern(self, analyzer):
        """MEDIA: 响应含 /video/ 路径"""
        response = json.dumps({
            "src": "https://cdn.example.com/video/play/123",
            "type": "hls",
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.MEDIA

    def test_config_type(self, analyzer):
        """CONFIG: 响应含 config/settings 字段"""
        response = json.dumps({
            "config": {"theme": "dark", "language": "zh"},
            "version": "2.0.1",
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.CONFIG

    def test_config_type_settings(self, analyzer):
        """CONFIG: 响应含 settings 字段"""
        response = json.dumps({
            "settings": {"notifications": True, "autoPlay": False},
        })
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.CONFIG

    def test_aux_type_simple_response(self, analyzer):
        """AUX: 简单响应"""
        response = json.dumps({"success": True, "code": 0})
        req = make_request(response_body=response)
        assert analyzer.classify_api_type(req) == APIType.AUX

    def test_aux_type_null_response(self, analyzer):
        """AUX: 空响应"""
        req = make_request(response_body=None)
        assert analyzer.classify_api_type(req) == APIType.AUX

    def test_aux_type_invalid_json(self, analyzer):
        """AUX: 无效 JSON 响应"""
        req = make_request(response_body="not json")
        assert analyzer.classify_api_type(req) == APIType.AUX


# === 参数分类测试 ===


class TestClassifyParameters:
    """测试 classify_parameters 方法"""

    def test_static_params(self, analyzer):
        """静态参数分类"""
        req = make_request(
            url="https://api.example.com/v1/data?version=2.0&platform=android&channel=official"
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert param_map["version"].category == "static"
        assert param_map["platform"].category == "static"
        assert param_map["channel"].category == "static"

    def test_session_params(self, analyzer):
        """会话参数分类"""
        req = make_request(
            url="https://api.example.com/v1/data?token=abc123&userId=12345"
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert param_map["token"].category == "session"
        assert param_map["userId"].category == "session"

    def test_session_params_from_header(self, analyzer):
        """会话参数 - 来自 header"""
        req = make_request(
            url="https://api.example.com/v1/data",
            headers={"Authorization": "Bearer token123"},
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert param_map["Authorization"].category == "session"
        assert param_map["Authorization"].source == "header"

    def test_dynamic_params_by_name(self, analyzer):
        """动态参数 - 名称匹配"""
        req = make_request(
            url="https://api.example.com/v1/data?sign=abc&nonce=xyz&timestamp=1704067200"
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert param_map["sign"].category == "dynamic"
        assert param_map["nonce"].category == "dynamic"
        assert param_map["timestamp"].category == "dynamic"

    def test_dynamic_params_by_value_md5(self, analyzer):
        """动态参数 - MD5 哈希值"""
        req = make_request(
            url="https://api.example.com/v1/data?data=d41d8cd98f00b204e9800998ecf8427e"
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert param_map["data"].category == "dynamic"

    def test_body_params_json(self, analyzer):
        """从 JSON body 提取参数"""
        body = json.dumps({"userId": "12345", "sign": "abc123"})
        req = make_request(
            url="https://api.example.com/v1/data",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert "userId" in param_map
        assert param_map["userId"].category == "session"
        assert param_map["userId"].source == "body"
        assert param_map["sign"].category == "dynamic"

    def test_body_params_form(self, analyzer):
        """从 form data body 提取参数"""
        req = make_request(
            url="https://api.example.com/v1/data",
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body="platform=ios&token=abc123",
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert param_map["platform"].category == "static"
        assert param_map["token"].category == "session"

    def test_cookie_params(self, analyzer):
        """从 Cookie 提取参数"""
        req = make_request(
            url="https://api.example.com/v1/data",
            headers={"Cookie": "session_id=sess123; uid=user456"},
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert "session_id" in param_map
        assert param_map["session_id"].category == "session"
        assert param_map["session_id"].source == "cookie"
        assert param_map["uid"].category == "session"

    def test_all_params_have_valid_category(self, analyzer):
        """所有参数分类结果必须是 static/session/dynamic 之一"""
        req = make_request(
            url="https://api.example.com/v1/data?version=1&token=abc&sign=xyz&custom=hello"
        )
        params = analyzer.classify_parameters(req)

        for p in params:
            assert p.category in ("static", "session", "dynamic"), (
                f"Parameter '{p.name}' has invalid category '{p.category}'"
            )

    def test_param_source_tracking(self, analyzer):
        """参数来源正确标记"""
        req = make_request(
            url="https://api.example.com/v1/data?version=1",
            headers={"Authorization": "Bearer token"},
            body=json.dumps({"sign": "abc"}),
        )
        params = analyzer.classify_parameters(req)

        param_map = {p.name: p for p in params}
        assert param_map["version"].source == "query"
        assert param_map["Authorization"].source == "header"
        assert param_map["sign"].source == "body"


# === 数据链路检测测试 ===


class TestDetectDataLinks:
    """测试 detect_data_links 方法"""

    def test_list_to_detail_link(self, analyzer):
        """检测 list → detail 链路"""
        # 模拟 LIST 接口的 ID 值缓存
        analyzer._list_id_values = {
            "/v1/books": {"101", "102", "103"},
        }
        analyzer._detail_id_values = {}

        results = [
            APIAnalysisResult(
                request_id="req-1",
                endpoint="/v1/books",
                api_type=APIType.LIST,
                parameters=[],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
            APIAnalysisResult(
                request_id="req-2",
                endpoint="/v1/book/detail",
                api_type=APIType.DETAIL,
                parameters=[
                    ParameterInfo(name="bookId", value_sample="101", category="static", source="query"),
                ],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
        ]

        links = analyzer.detect_data_links(results)

        assert len(links) == 1
        assert links[0].source_endpoint == "/v1/books"
        assert links[0].target_endpoint == "/v1/book/detail"
        assert links[0].link_field == "bookId"
        assert links[0].link_type == "list_to_detail"

    def test_list_to_media_link(self, analyzer):
        """检测 list → media 链路"""
        analyzer._list_id_values = {
            "/v1/videos": {"v001", "v002"},
        }
        analyzer._detail_id_values = {}

        results = [
            APIAnalysisResult(
                request_id="req-1",
                endpoint="/v1/videos",
                api_type=APIType.LIST,
                parameters=[],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
            APIAnalysisResult(
                request_id="req-2",
                endpoint="/v1/video/play",
                api_type=APIType.MEDIA,
                parameters=[
                    ParameterInfo(name="videoId", value_sample="v001", category="static", source="query"),
                ],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
        ]

        links = analyzer.detect_data_links(results)

        assert len(links) == 1
        assert links[0].link_type == "list_to_media"

    def test_no_link_when_ids_dont_match(self, analyzer):
        """ID 不匹配时不建立链路"""
        analyzer._list_id_values = {
            "/v1/books": {"101", "102"},
        }
        analyzer._detail_id_values = {}

        results = [
            APIAnalysisResult(
                request_id="req-1",
                endpoint="/v1/books",
                api_type=APIType.LIST,
                parameters=[],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
            APIAnalysisResult(
                request_id="req-2",
                endpoint="/v1/book/detail",
                api_type=APIType.DETAIL,
                parameters=[
                    ParameterInfo(name="bookId", value_sample="999", category="static", source="query"),
                ],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
        ]

        links = analyzer.detect_data_links(results)
        assert len(links) == 0

    def test_detail_to_media_link(self, analyzer):
        """检测 detail → media 链路"""
        analyzer._list_id_values = {}
        analyzer._detail_id_values = {
            "/v1/book/detail": {"chapter-001"},
        }

        results = [
            APIAnalysisResult(
                request_id="req-1",
                endpoint="/v1/book/detail",
                api_type=APIType.DETAIL,
                parameters=[],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
            APIAnalysisResult(
                request_id="req-2",
                endpoint="/v1/audio/play",
                api_type=APIType.MEDIA,
                parameters=[
                    ParameterInfo(name="chapterId", value_sample="chapter-001", category="static", source="query"),
                ],
                has_signature=False,
                signature_fields=[],
                matches_target=False,
                call_count=1,
            ),
        ]

        links = analyzer.detect_data_links(results)

        assert len(links) == 1
        assert links[0].link_type == "detail_to_media"


# === 综合分析测试 ===


class TestAnalyzeAll:
    """测试 analyze_all 方法"""

    def test_basic_analysis(self, analyzer):
        """基本综合分析"""
        requests = [
            make_request(
                request_id="req-1",
                url="https://api.example.com/v1/books?page=1",
                response_body=json.dumps({
                    "data": [
                        {"id": 1, "name": "Book 1"},
                        {"id": 2, "name": "Book 2"},
                    ],
                    "hasMore": True,
                }),
            ),
            make_request(
                request_id="req-2",
                url="https://api.example.com/v1/config",
                response_body=json.dumps({
                    "config": {"theme": "dark"},
                    "version": "1.0",
                }),
            ),
        ]
        target = CaptureTarget(
            app_name="TestApp",
            target_data="books list",
            operation_pages="home page",
        )

        report = analyzer.analyze_all(requests, target)

        assert isinstance(report, AnalysisReport)
        assert report.total_captured == 2
        assert report.total_analyzed == 2
        assert len(report.results) == 2

    def test_target_matching(self, analyzer):
        """目标匹配逻辑"""
        requests = [
            make_request(
                request_id="req-1",
                url="https://api.example.com/v1/books?page=1",
                response_body=json.dumps({
                    "data": [
                        {"id": 1, "name": "Book 1"},
                    ],
                    "hasMore": True,
                }),
            ),
            make_request(
                request_id="req-2",
                url="https://api.example.com/v1/ads/banner",
                response_body=json.dumps({"banners": []}),
            ),
        ]
        target = CaptureTarget(
            app_name="TestApp",
            target_data="books",
            operation_pages="home",
        )

        report = analyzer.analyze_all(requests, target)

        # books 接口应该匹配目标
        books_result = next(r for r in report.results if "/books" in r.endpoint)
        assert books_result.matches_target is True

    def test_no_target_match(self, analyzer):
        """未找到匹配目标时 target_matched 为 0"""
        requests = [
            make_request(
                request_id="req-1",
                url="https://api.example.com/v1/ads/banner",
                response_body=json.dumps({"success": True}),
            ),
        ]
        target = CaptureTarget(
            app_name="TestApp",
            target_data="videos streaming",
            operation_pages="play page",
        )

        report = analyzer.analyze_all(requests, target)
        assert report.target_matched == 0

    def test_signature_detection(self, analyzer):
        """签名检测"""
        requests = [
            make_request(
                request_id="req-1",
                url="https://api.example.com/v1/data?sign=abc123&nonce=xyz&version=2.0",
                response_body=json.dumps({"data": "ok"}),
            ),
        ]
        target = CaptureTarget(app_name="App", target_data="data", operation_pages="home")

        report = analyzer.analyze_all(requests, target)

        result = report.results[0]
        assert result.has_signature is True
        assert "sign" in result.signature_fields
        assert "nonce" in result.signature_fields

    def test_call_count(self, analyzer):
        """调用次数统计"""
        requests = [
            make_request(
                request_id="req-1",
                url="https://api.example.com/v1/data?page=1",
                response_body=json.dumps({"data": "ok"}),
            ),
            make_request(
                request_id="req-2",
                url="https://api.example.com/v1/data?page=2",
                response_body=json.dumps({"data": "ok"}),
            ),
            make_request(
                request_id="req-3",
                url="https://api.example.com/v1/data?page=3",
                response_body=json.dumps({"data": "ok"}),
            ),
        ]
        target = CaptureTarget(app_name="App", target_data="data", operation_pages="home")

        report = analyzer.analyze_all(requests, target)

        # 同一 endpoint 只分析一次，但 call_count 应为 3
        assert len(report.results) == 1
        assert report.results[0].call_count == 3

    def test_data_link_detection_in_analyze_all(self, analyzer):
        """analyze_all 中的数据链路检测"""
        requests = [
            make_request(
                request_id="req-1",
                url="https://api.example.com/v1/books?page=1",
                response_body=json.dumps({
                    "data": [
                        {"id": "book-001", "name": "Book 1"},
                        {"id": "book-002", "name": "Book 2"},
                    ],
                    "hasMore": True,
                }),
            ),
            make_request(
                request_id="req-2",
                url="https://api.example.com/v1/book/detail?id=book-001",
                response_body=json.dumps({
                    "id": "book-001",
                    "name": "Book 1",
                    "author": "Author",
                    "description": "A great book",
                    "chapters": 10,
                    "rating": 4.5,
                }),
            ),
        ]
        target = CaptureTarget(app_name="App", target_data="books", operation_pages="home")

        report = analyzer.analyze_all(requests, target)

        # 应该检测到 list → detail 链路
        assert len(report.data_links) >= 1
        link = report.data_links[0]
        assert link.source_endpoint == "/v1/books"
        assert link.target_endpoint == "/v1/book/detail"
        assert link.link_type == "list_to_detail"

    def test_report_type_counts(self, analyzer):
        """报告中各类型接口数量之和等于 total_analyzed"""
        requests = [
            make_request(
                request_id="req-1",
                url="https://api.example.com/v1/items?page=1",
                response_body=json.dumps({
                    "data": [{"id": 1, "name": "Item"}],
                    "total": 10,
                }),
            ),
            make_request(
                request_id="req-2",
                url="https://api.example.com/v1/play",
                response_body=json.dumps({
                    "url": "https://cdn.example.com/video.mp4",
                }),
            ),
            make_request(
                request_id="req-3",
                url="https://api.example.com/v1/status",
                response_body=json.dumps({"code": 0, "msg": "ok"}),
            ),
        ]
        target = CaptureTarget(app_name="App", target_data="items", operation_pages="home")

        report = analyzer.analyze_all(requests, target)

        # 各类型数量之和应等于 total_analyzed
        type_counts = {}
        for r in report.results:
            type_counts[r.api_type] = type_counts.get(r.api_type, 0) + 1

        assert sum(type_counts.values()) == report.total_analyzed
