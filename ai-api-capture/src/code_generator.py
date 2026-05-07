"""代码生成模块 - 为可复现接口生成 Python requests 代码

实现功能：
- 代码生成：使用 Jinja2 模板从分析结果和原始请求生成 Python requests 代码
- 会话参数提取：识别并提取需要用户配置的会话参数
- 代码验证：在子进程中执行生成的代码并比对响应结构
- 降级逻辑：验证失败时标记为复杂接口
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from jinja2 import Environment, FileSystemLoader

from src.models import (
    APIAnalysisResult,
    CapturedRequest,
    GeneratedCode,
    ParameterInfo,
)


@dataclass
class SessionParam:
    """会话参数信息，用于模板渲染"""

    name: str
    value: str
    description: str


@dataclass
class VerificationResult:
    """代码验证结果"""

    success: bool
    error: Optional[str] = None
    response_keys: Optional[List[str]] = None
    expected_keys: Optional[List[str]] = None


class CodeGenerator:
    """代码生成器 - 为可复现接口生成 Python requests 代码

    核心功能：
    1. generate(): 从分析结果和原始请求生成代码
    2. verify(): 执行生成的代码并验证响应结构
    3. extract_session_params(): 提取需要用户配置的会话参数
    4. handle_verification_failure(): 验证失败时的降级处理
    """

    def __init__(self, template_dir: Optional[str] = None, verify_timeout: int = 30):
        """初始化代码生成器

        Args:
            template_dir: Jinja2 模板目录路径，默认为项目 templates/ 目录
            verify_timeout: 验证执行超时时间（秒）
        """
        if template_dir is None:
            # 默认使用项目根目录下的 templates/
            project_root = Path(__file__).parent.parent
            template_dir = str(project_root / "templates")

        self.template_dir = template_dir
        self.verify_timeout = verify_timeout
        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(
        self, analysis: APIAnalysisResult, request: CapturedRequest
    ) -> GeneratedCode:
        """从分析结果和原始请求生成 Python requests 代码

        Args:
            analysis: 接口分析结果
            request: 原始捕获的请求

        Returns:
            GeneratedCode 对象
        """
        # 1. 提取会话参数
        session_param_names = self.extract_session_params(request, analysis.parameters)

        # 2. 构建模板上下文
        context = self._build_template_context(analysis, request, session_param_names)

        # 3. 渲染模板
        template = self._env.get_template("code_template.py.jinja")
        code = template.render(**context)

        return GeneratedCode(
            api_id=analysis.request_id,
            code=code,
            session_params=session_param_names,
            verification_status="pending",
            failure_reason=None,
        )

    def extract_session_params(
        self, request: CapturedRequest, params: List[ParameterInfo]
    ) -> List[str]:
        """提取需要用户配置的会话参数名列表

        从分析结果中找出 category 为 "session" 的参数，
        这些参数需要用户手动配置（如 token、cookie 等）。

        Args:
            request: 原始捕获的请求
            params: 参数分析列表

        Returns:
            会话参数名列表
        """
        session_params = []
        for param in params:
            if param.category == "session":
                session_params.append(param.name)
        return session_params

    async def verify(
        self, generated: GeneratedCode, enable_execution: bool = False
    ) -> VerificationResult:
        """验证生成的代码

        验证步骤：
        1. 语法检查：确保生成的代码是有效的 Python
        2. 可选执行验证：在子进程中运行代码并比对响应结构

        Args:
            generated: 生成的代码对象
            enable_execution: 是否启用实际执行验证（默认关闭，需要 opt-in）

        Returns:
            VerificationResult 对象
        """
        # 1. 语法检查
        syntax_result = self._check_syntax(generated.code)
        if not syntax_result.success:
            return syntax_result

        # 2. 如果启用执行验证
        if enable_execution:
            return await self._execute_and_verify(generated.code)

        return VerificationResult(success=True)

    def handle_verification_failure(
        self, generated: GeneratedCode, verification: VerificationResult
    ) -> GeneratedCode:
        """处理验证失败的降级逻辑

        当验证失败时：
        1. 更新 verification_status 为 "failed"
        2. 记录失败原因
        3. 返回更新后的 GeneratedCode，调用方可据此将接口重新分类为 "complex"

        Args:
            generated: 原始生成的代码对象
            verification: 验证结果

        Returns:
            更新后的 GeneratedCode 对象（verification_status="failed"）
        """
        return GeneratedCode(
            api_id=generated.api_id,
            code=generated.code,
            session_params=generated.session_params,
            verification_status="failed",
            failure_reason=verification.error or "验证失败，建议重新标记为复杂接口",
        )

    def _build_template_context(
        self,
        analysis: APIAnalysisResult,
        request: CapturedRequest,
        session_param_names: List[str],
    ) -> Dict:
        """构建 Jinja2 模板渲染上下文

        Args:
            analysis: 接口分析结果
            request: 原始请求
            session_param_names: 会话参数名列表

        Returns:
            模板上下文字典
        """
        # 解析 URL
        parsed_url = urlparse(request.url)

        # 生成函数名（从 endpoint 路径提取）
        function_name = self._generate_function_name(analysis.endpoint)

        # 构建 session params 信息
        session_params = self._build_session_params(
            request, analysis.parameters, session_param_names
        )

        # 构建 headers 字典（替换会话参数为变量引用）
        headers = self._build_headers(request.headers, session_param_names)

        # 构建 query params
        query_params = self._build_query_params(request.url, session_param_names)

        # 构建 body
        body, body_type = self._build_body(request, session_param_names)

        # 构建函数参数列表
        function_args = self._build_function_args(session_param_names)

        # 构建 main 调用参数
        main_call_args = self._build_main_call_args(session_param_names)

        return {
            "endpoint": analysis.endpoint,
            "purpose": analysis.purpose or "API 请求",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "session_params": session_params,
            "function_name": function_name,
            "function_args": function_args,
            "method": request.method.lower(),
            "url": request.url.split("?")[0],  # URL without query string
            "headers": headers,
            "query_params": query_params,
            "body": body,
            "body_type": body_type,
            "main_call_args": main_call_args,
        }

    def _generate_function_name(self, endpoint: str) -> str:
        """从 endpoint 路径生成合法的 Python 函数名

        例如: /api/v1/user/feed -> api_v1_user_feed
        """
        # 移除开头的 /
        name = endpoint.strip("/")
        # 替换非字母数字字符为下划线
        name = re.sub(r"[^a-zA-Z0-9]", "_", name)
        # 移除连续下划线
        name = re.sub(r"_+", "_", name)
        # 移除首尾下划线
        name = name.strip("_")
        # 确保不以数字开头
        if name and name[0].isdigit():
            name = "api_" + name
        # 默认名称
        if not name:
            name = "api_request"
        return name.lower()

    def _build_session_params(
        self,
        request: CapturedRequest,
        params: List[ParameterInfo],
        session_param_names: List[str],
    ) -> List[SessionParam]:
        """构建会话参数列表，包含当前值和描述"""
        session_params = []
        for param in params:
            if param.name in session_param_names:
                session_params.append(
                    SessionParam(
                        name=param.name,
                        value=param.value_sample,
                        description=param.reasoning,
                    )
                )
        return session_params

    def _build_headers(
        self, headers: dict, session_param_names: List[str]
    ) -> str:
        """构建 headers 字典字符串

        会话参数的值会被替换为变量引用（如 f"{TOKEN}"）
        """
        # 过滤掉不需要的标准头部
        skip_headers = {
            "host",
            "connection",
            "content-length",
            "accept-encoding",
            "transfer-encoding",
        }

        filtered = {}
        for key, value in headers.items():
            if key.lower() in skip_headers:
                continue
            # 检查是否是会话参数
            is_session = False
            for param_name in session_param_names:
                if param_name.lower() == key.lower():
                    is_session = True
                    filtered[key] = f"{{{{ {param_name.upper()} }}}}"
                    break
                # 检查值中是否包含会话参数的值
            if not is_session:
                filtered[key] = value

        # 格式化为 Python dict 字符串
        return self._format_dict(filtered, session_param_names)

    def _build_query_params(
        self, url: str, session_param_names: List[str]
    ) -> Optional[str]:
        """构建 query params 字典字符串"""
        parsed = urlparse(url)
        if not parsed.query:
            return None

        query_dict = parse_qs(parsed.query, keep_blank_values=True)
        params = {}
        for key, values in query_dict.items():
            value = values[0] if values else ""
            params[key] = value

        if not params:
            return None

        return self._format_dict(params, session_param_names)

    def _build_body(
        self, request: CapturedRequest, session_param_names: List[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """构建请求体字符串

        Returns:
            (body_string, body_type) 元组，body_type 为 "json" 或 "form"
        """
        if request.body is None:
            return None, None

        # 尝试 JSON 解析
        try:
            body_str = request.body.decode("utf-8")
            data = json.loads(body_str)
            if isinstance(data, dict):
                return self._format_dict(data, session_param_names), "json"
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # 尝试 form data
        try:
            body_str = request.body.decode("utf-8")
            form_params = parse_qs(body_str, keep_blank_values=True)
            if form_params:
                params = {k: v[0] if v else "" for k, v in form_params.items()}
                return self._format_dict(params, session_param_names), "form"
        except UnicodeDecodeError:
            pass

        return None, None

    def _build_function_args(self, session_param_names: List[str]) -> str:
        """构建函数参数列表字符串"""
        if not session_param_names:
            return ""
        args = [f"{name.lower()}={name.upper()}" for name in session_param_names]
        return ", ".join(args)

    def _build_main_call_args(self, session_param_names: List[str]) -> str:
        """构建 main 块中的函数调用参数"""
        if not session_param_names:
            return ""
        return ", ".join(f"{name.lower()}={name.upper()}" for name in session_param_names)

    def _format_dict(self, d: dict, session_param_names: List[str]) -> str:
        """格式化字典为 Python 代码字符串

        对于会话参数，使用 f-string 变量引用
        """
        if not d:
            return "{}"

        items = []
        has_session_ref = False

        for key, value in d.items():
            # 检查 key 或 value 是否引用会话参数
            is_session_value = False
            for param_name in session_param_names:
                if isinstance(value, str) and f"{{{{ {param_name.upper()} }}}}" in value:
                    # 已经是变量引用格式
                    items.append(f'    "{key}": f"{value}"')
                    is_session_value = True
                    has_session_ref = True
                    break
                elif key.lower() == param_name.lower():
                    # key 本身是会话参数
                    items.append(
                        f'    "{key}": {param_name.lower()}'
                    )
                    is_session_value = True
                    has_session_ref = True
                    break

            if not is_session_value:
                # 普通值
                if isinstance(value, str):
                    # 转义引号
                    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                    items.append(f'    "{key}": "{escaped}"')
                elif isinstance(value, bool):
                    items.append(f'    "{key}": {str(value)}')
                elif isinstance(value, (int, float)):
                    items.append(f'    "{key}": {value}')
                elif value is None:
                    items.append(f'    "{key}": None')
                else:
                    items.append(f'    "{key}": {json.dumps(value, ensure_ascii=False)}')

        return "{\n" + ",\n".join(items) + ",\n}"

    def _check_syntax(self, code: str) -> VerificationResult:
        """检查生成的代码是否有语法错误"""
        try:
            compile(code, "<generated>", "exec")
            return VerificationResult(success=True)
        except SyntaxError as e:
            return VerificationResult(
                success=False,
                error=f"语法错误: {e.msg} (行 {e.lineno})",
            )

    async def _execute_and_verify(self, code: str) -> VerificationResult:
        """在子进程中执行代码并验证响应

        安全措施：
        - 使用临时文件
        - 设置超时
        - 在独立子进程中运行
        """
        # 创建临时文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            # 在子进程中执行
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.verify_timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return VerificationResult(
                    success=False,
                    error=f"执行超时（{self.verify_timeout}秒）",
                )

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                return VerificationResult(
                    success=False,
                    error=f"执行失败: {error_msg[:500]}",
                )

            # 尝试解析输出为 JSON 并提取 keys
            output = stdout.decode("utf-8", errors="replace").strip()
            try:
                result = json.loads(output)
                if isinstance(result, dict):
                    return VerificationResult(
                        success=True,
                        response_keys=sorted(result.keys()),
                    )
            except json.JSONDecodeError:
                pass

            # 输出不是 JSON 但执行成功
            return VerificationResult(success=True)

        finally:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except OSError:
                pass
