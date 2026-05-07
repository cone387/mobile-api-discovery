"""Code Generator 模块测试

测试覆盖：
- 5.1 Jinja2 模板渲染
- 5.2 CodeGenerator.generate() 方法
- 5.3 会话参数提取和可配置变量生成
- 5.4 代码验证执行器
- 5.5 验证失败降级逻辑
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import patch

import pytest

from src.code_generator import CodeGenerator, SessionParam, VerificationResult
from src.models import (
    APIAnalysisResult,
    CapturedRequest,
    GeneratedCode,
    ParameterInfo,
)


# === 测试 Fixtures ===


def make_request(
    method="GET",
    url="https://api.example.com/v1/feed?page=1&size=20",
    headers=None,
    body=None,
    response_body=None,
) -> CapturedRequest:
    """创建测试用 CapturedRequest"""
    if headers is None:
        headers = {
            "Authorization": "Bearer test_token_123",
            "Content-Type": "application/json",
            "User-Agent": "TestApp/1.0",
            "X-App-Version": "2.0.0",
        }
    return CapturedRequest(
        id="req-001",
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        operation_step_id="step-001",
        method=method,
        url=url,
        headers=headers,
        body=body,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=response_body or b'{"data": [], "total": 100}',
        is_decrypted=True,
    )


def make_analysis(
    params=None, reproducibility="reproducible", endpoint="/v1/feed", purpose="feed"
) -> APIAnalysisResult:
    """创建测试用 APIAnalysisResult"""
    if params is None:
        params = [
            ParameterInfo(
                name="Authorization",
                value_sample="Bearer test_token_123",
                category="session",
                source="header",
                reasoning="参数名匹配会话参数模式",
            ),
            ParameterInfo(
                name="page",
                value_sample="1",
                category="static",
                source="query",
                reasoning="分页参数",
            ),
            ParameterInfo(
                name="size",
                value_sample="20",
                category="static",
                source="query",
                reasoning="分页参数",
            ),
        ]
    return APIAnalysisResult(
        request_id="req-001",
        endpoint=endpoint,
        purpose=purpose,
        parameters=params,
        reproducibility=reproducibility,
        reproducibility_reason="所有参数均为静态或会话类型",
        confidence=0.9,
    )


# === 5.1 模板渲染测试 ===


class TestTemplateRendering:
    """测试 Jinja2 模板渲染"""

    def setup_method(self):
        self.generator = CodeGenerator()

    def test_template_renders_import_statement(self):
        """模板应包含 import requests"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert "import requests" in result.code

    def test_template_renders_function_definition(self):
        """模板应生成正确的函数定义"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert "def fetch_v1_feed(" in result.code

    def test_template_renders_error_handling(self):
        """模板应包含 try/except 错误处理"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert "try:" in result.code
        assert "except requests.RequestException" in result.code

    def test_template_renders_main_block(self):
        """模板应包含 if __name__ == '__main__' 块"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert 'if __name__ == "__main__":' in result.code

    def test_template_renders_session_params_as_variables(self):
        """模板应将会话参数渲染为顶部变量"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert "AUTHORIZATION" in result.code


# === 5.2 CodeGenerator.generate() 测试 ===


class TestCodeGeneratorGenerate:
    """测试 CodeGenerator.generate() 方法"""

    def setup_method(self):
        self.generator = CodeGenerator()

    def test_generate_returns_generated_code(self):
        """generate() 应返回 GeneratedCode 对象"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert isinstance(result, GeneratedCode)
        assert result.api_id == "req-001"
        assert result.verification_status == "pending"
        assert result.failure_reason is None

    def test_generate_get_request(self):
        """GET 请求应使用 requests.get"""
        request = make_request(method="GET")
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert "requests.get(" in result.code

    def test_generate_post_request_with_json_body(self):
        """POST 请求应使用 requests.post 并包含 json body"""
        body = json.dumps({"title": "test", "content": "hello"}).encode("utf-8")
        request = make_request(
            method="POST",
            url="https://api.example.com/v1/comment",
            body=body,
        )
        analysis = make_analysis(endpoint="/v1/comment", purpose="comment")
        result = self.generator.generate(analysis, request)
        assert "requests.post(" in result.code
        assert "json=json_data" in result.code

    def test_generate_put_request(self):
        """PUT 请求应使用 requests.put"""
        body = json.dumps({"name": "updated"}).encode("utf-8")
        request = make_request(
            method="PUT",
            url="https://api.example.com/v1/user/profile",
            body=body,
        )
        analysis = make_analysis(endpoint="/v1/user/profile", purpose="user")
        result = self.generator.generate(analysis, request)
        assert "requests.put(" in result.code

    def test_generate_delete_request(self):
        """DELETE 请求应使用 requests.delete"""
        request = make_request(
            method="DELETE",
            url="https://api.example.com/v1/comment/123",
        )
        analysis = make_analysis(endpoint="/v1/comment/123", purpose="comment")
        result = self.generator.generate(analysis, request)
        assert "requests.delete(" in result.code

    def test_generate_includes_headers(self):
        """生成的代码应包含请求头"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert "headers" in result.code
        assert "Content-Type" in result.code

    def test_generate_includes_query_params(self):
        """生成的代码应包含 query 参数"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        assert "params" in result.code
        assert "page" in result.code
        assert "size" in result.code

    def test_generate_valid_python_syntax(self):
        """生成的代码应是有效的 Python 语法"""
        request = make_request()
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        # 应该不抛出 SyntaxError
        compile(result.code, "<test>", "exec")

    def test_generate_no_query_params(self):
        """无 query 参数时不应生成 params 变量"""
        request = make_request(url="https://api.example.com/v1/feed")
        analysis = make_analysis()
        result = self.generator.generate(analysis, request)
        # 不应有 params = { 这样的赋值
        assert "params = {" not in result.code


# === 5.3 会话参数提取测试 ===


class TestSessionParamExtraction:
    """测试会话参数提取和可配置变量生成"""

    def setup_method(self):
        self.generator = CodeGenerator()

    def test_extract_session_params_basic(self):
        """应正确提取 session 类型的参数"""
        request = make_request()
        params = [
            ParameterInfo("Authorization", "Bearer token", "session", "header", ""),
            ParameterInfo("page", "1", "static", "query", ""),
            ParameterInfo("session_id", "abc123", "session", "cookie", ""),
        ]
        result = self.generator.extract_session_params(request, params)
        assert "Authorization" in result
        assert "session_id" in result
        assert "page" not in result

    def test_extract_session_params_empty(self):
        """无会话参数时应返回空列表"""
        request = make_request()
        params = [
            ParameterInfo("page", "1", "static", "query", ""),
            ParameterInfo("size", "20", "static", "query", ""),
        ]
        result = self.generator.extract_session_params(request, params)
        assert result == []

    def test_session_params_rendered_as_configurable_variables(self):
        """会话参数应在生成代码顶部作为可配置变量"""
        request = make_request()
        params = [
            ParameterInfo(
                "Authorization",
                "Bearer test_token",
                "session",
                "header",
                "需要用户配置的 token",
            ),
            ParameterInfo("page", "1", "static", "query", "分页参数"),
        ]
        analysis = make_analysis(params=params)
        result = self.generator.generate(analysis, request)
        # 应有大写变量名
        assert "AUTHORIZATION" in result.code
        # 应有注释说明
        assert "会话参数" in result.code

    def test_multiple_session_params(self):
        """多个会话参数应全部提取"""
        request = make_request()
        params = [
            ParameterInfo("token", "abc", "session", "header", ""),
            ParameterInfo("uid", "123", "session", "query", ""),
            ParameterInfo("api_key", "key123", "session", "header", ""),
        ]
        result = self.generator.extract_session_params(request, params)
        assert len(result) == 3
        assert "token" in result
        assert "uid" in result
        assert "api_key" in result


# === 5.4 代码验证执行器测试 ===


class TestCodeVerification:
    """测试代码验证执行器"""

    def setup_method(self):
        self.generator = CodeGenerator()

    @pytest.mark.asyncio
    async def test_verify_syntax_valid(self):
        """有效语法的代码应通过验证"""
        code = GeneratedCode(
            api_id="test",
            code='import requests\nprint("hello")\n',
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        result = await self.generator.verify(code)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_verify_syntax_invalid(self):
        """无效语法的代码应验证失败"""
        code = GeneratedCode(
            api_id="test",
            code="def foo(\n  # missing closing paren",
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        result = await self.generator.verify(code)
        assert result.success is False
        assert "语法错误" in result.error

    @pytest.mark.asyncio
    async def test_verify_execution_disabled_by_default(self):
        """默认不执行代码，仅做语法检查"""
        code = GeneratedCode(
            api_id="test",
            code='import requests\nraise RuntimeError("should not run")\n',
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        # 不启用执行验证，应该通过（仅语法检查）
        result = await self.generator.verify(code, enable_execution=False)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_verify_execution_success(self):
        """启用执行验证时，成功执行的代码应通过"""
        code = GeneratedCode(
            api_id="test",
            code='import json\nprint(json.dumps({"key": "value"}))\n',
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        result = await self.generator.verify(code, enable_execution=True)
        assert result.success is True
        assert result.response_keys == ["key"]

    @pytest.mark.asyncio
    async def test_verify_execution_failure(self):
        """启用执行验证时，执行失败的代码应返回错误"""
        code = GeneratedCode(
            api_id="test",
            code='raise RuntimeError("test error")\n',
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        result = await self.generator.verify(code, enable_execution=True)
        assert result.success is False
        assert "执行失败" in result.error

    @pytest.mark.asyncio
    async def test_verify_execution_timeout(self):
        """执行超时应返回超时错误"""
        generator = CodeGenerator(verify_timeout=1)
        code = GeneratedCode(
            api_id="test",
            code="import time\ntime.sleep(10)\n",
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        result = await generator.verify(code, enable_execution=True)
        assert result.success is False
        assert "超时" in result.error


# === 5.5 验证失败降级逻辑测试 ===


class TestVerificationFailureDegradation:
    """测试验证失败时的降级逻辑"""

    def setup_method(self):
        self.generator = CodeGenerator()

    def test_handle_failure_updates_status(self):
        """验证失败应将 verification_status 更新为 failed"""
        generated = GeneratedCode(
            api_id="req-001",
            code="some code",
            session_params=["token"],
            verification_status="pending",
            failure_reason=None,
        )
        verification = VerificationResult(
            success=False, error="执行失败: connection refused"
        )
        result = self.generator.handle_verification_failure(generated, verification)
        assert result.verification_status == "failed"

    def test_handle_failure_records_reason(self):
        """降级应记录失败原因"""
        generated = GeneratedCode(
            api_id="req-001",
            code="some code",
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        verification = VerificationResult(
            success=False, error="响应结构不匹配"
        )
        result = self.generator.handle_verification_failure(generated, verification)
        assert result.failure_reason == "响应结构不匹配"

    def test_handle_failure_preserves_code(self):
        """降级不应修改已生成的代码"""
        generated = GeneratedCode(
            api_id="req-001",
            code="original code here",
            session_params=["token"],
            verification_status="pending",
            failure_reason=None,
        )
        verification = VerificationResult(success=False, error="some error")
        result = self.generator.handle_verification_failure(generated, verification)
        assert result.code == "original code here"
        assert result.session_params == ["token"]
        assert result.api_id == "req-001"

    def test_handle_failure_default_reason(self):
        """无具体错误信息时应使用默认降级原因"""
        generated = GeneratedCode(
            api_id="req-001",
            code="code",
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        verification = VerificationResult(success=False, error=None)
        result = self.generator.handle_verification_failure(generated, verification)
        assert "复杂接口" in result.failure_reason

    def test_failed_code_signals_reclassification(self):
        """失败的 GeneratedCode 应允许调用方重新分类接口"""
        generated = GeneratedCode(
            api_id="req-001",
            code="code",
            session_params=[],
            verification_status="pending",
            failure_reason=None,
        )
        verification = VerificationResult(success=False, error="验证失败")
        result = self.generator.handle_verification_failure(generated, verification)
        # 调用方可以检查 verification_status == "failed" 来决定重新分类
        assert result.verification_status == "failed"
        assert result.failure_reason is not None


# === 辅助方法测试 ===


class TestHelperMethods:
    """测试辅助方法"""

    def setup_method(self):
        self.generator = CodeGenerator()

    def test_generate_function_name_basic(self):
        """基本路径应正确转换为函数名"""
        assert self.generator._generate_function_name("/v1/feed") == "v1_feed"
        assert self.generator._generate_function_name("/api/user/profile") == "api_user_profile"

    def test_generate_function_name_special_chars(self):
        """特殊字符应被替换为下划线"""
        assert self.generator._generate_function_name("/api/v2.0/data") == "api_v2_0_data"

    def test_generate_function_name_numeric_start(self):
        """数字开头应添加 api_ 前缀"""
        assert self.generator._generate_function_name("/123/data") == "api_123_data"

    def test_generate_function_name_empty(self):
        """空路径应返回默认名称"""
        assert self.generator._generate_function_name("/") == "api_request"
        assert self.generator._generate_function_name("") == "api_request"

    def test_format_dict_empty(self):
        """空字典应返回 '{}'"""
        assert self.generator._format_dict({}, []) == "{}"

    def test_format_dict_with_values(self):
        """字典应正确格式化"""
        result = self.generator._format_dict({"key": "value"}, [])
        assert '"key": "value"' in result
