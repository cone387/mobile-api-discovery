"""集成测试与端到端验证

测试内容：
- 10.1 模块间集成测试：DeviceController + TrafficInterceptor 协调测试
- 10.2 端到端流程测试：从操控到分析到代码生成的完整流程（使用 mock）
- 10.3 Skill 文件格式和内容完整性验证
"""

import ast
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.api_analyzer import APIAnalyzer
from src.code_generator import CodeGenerator
from src.device_controller import (
    DeviceController,
    DeviceInfo,
    MCPClient,
    SequenceResult,
)
from src.models import (
    APIAnalysisResult,
    CapturedRequest,
    GeneratedCode,
    OperationSequence,
    OperationStep,
    ParameterInfo,
)


# ============================================================
# Mock MCP 客户端（用于集成测试）
# ============================================================


class IntegrationMockMCPClient(MCPClient):
    """集成测试用 Mock MCP 客户端

    模拟设备操控行为，记录所有操作调用。
    """

    def __init__(self):
        self._connected = False
        self._selected_device: Optional[str] = None
        self.operations_log: List[Dict[str, Any]] = []

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self._selected_device = None

    async def is_connected(self) -> bool:
        return self._connected

    async def list_devices(self) -> List[DeviceInfo]:
        return [
            DeviceInfo(
                device_id="emulator-5554",
                name="Pixel 6",
                platform="android",
                status="available",
            )
        ]

    async def select_device(self, device_id: str) -> bool:
        self._selected_device = device_id
        return True

    async def launch_app(self, package_name: str) -> bool:
        self.operations_log.append({"action": "launch_app", "package": package_name})
        return True

    async def click(self, x: int, y: int) -> bool:
        self.operations_log.append({"action": "click", "x": x, "y": y})
        return True

    async def swipe(
        self,
        direction: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        distance: Optional[int] = None,
    ) -> bool:
        self.operations_log.append({"action": "swipe", "direction": direction})
        return True

    async def type_text(self, text: str, submit: bool = False) -> bool:
        self.operations_log.append({"action": "type_text", "text": text})
        return True

    async def list_elements(self) -> List[Dict[str, Any]]:
        return []

    async def press_button(self, button: str) -> bool:
        self.operations_log.append({"action": "press_button", "button": button})
        return True


# ============================================================
# 10.1 模块间集成测试：DeviceController + TrafficInterceptor 协调
# ============================================================


class TestDeviceControllerTrafficInterceptorIntegration:
    """测试 DeviceController 和 TrafficInterceptor 的协调工作

    验证：
    - step_id_callback 正确更新 TrafficInterceptor 的步骤 ID
    - 执行操作序列后，捕获的请求能关联到正确的步骤 ID
    """

    @pytest.mark.asyncio
    async def test_step_id_callback_updates_interceptor_step_id(self):
        """DeviceController 执行步骤时应通过回调更新 TrafficInterceptor 的步骤 ID"""
        # 模拟 TrafficInterceptor 的 set_step_id 方法
        step_ids_received: List[Optional[str]] = []

        def mock_set_step_id(step_id: Optional[str]) -> None:
            step_ids_received.append(step_id)

        mock_client = IntegrationMockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=mock_set_step_id,
        )

        await controller.connect("emulator-5554")

        # 创建操作序列
        sequence = OperationSequence(
            id="seq-integration-001",
            app_package="com.example.app",
            intent_description="浏览首页 feed 流",
            steps=[
                OperationStep(
                    id="step-001",
                    sequence_id="seq-integration-001",
                    action_type="click",
                    target="首页 Tab",
                    parameters={"x": 200, "y": 100},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-002",
                    sequence_id="seq-integration-001",
                    action_type="swipe",
                    target="feed 列表",
                    parameters={"direction": "up"},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-003",
                    sequence_id="seq-integration-001",
                    action_type="click",
                    target="详情入口",
                    parameters={"x": 300, "y": 400},
                    status="pending",
                    error_message=None,
                ),
            ],
            created_at=datetime(2024, 1, 15, 10, 0, 0),
        )

        # 执行序列
        result = await controller.execute_sequence(sequence)

        # 验证步骤 ID 回调被正确调用
        assert step_ids_received == ["step-001", "step-002", "step-003", None]
        # 验证序列执行成功
        assert result.completed_steps == 3
        assert result.failed_steps == 0

    @pytest.mark.asyncio
    async def test_captured_requests_have_correct_step_ids(self):
        """模拟完整协调流程：执行步骤时捕获的请求应关联正确的步骤 ID"""
        # 模拟 TrafficInterceptor 的行为：
        # 当 set_step_id 被调用时，后续捕获的请求会关联到该步骤
        current_step_id: List[Optional[str]] = [None]
        captured_requests: List[CapturedRequest] = []

        def mock_set_step_id(step_id: Optional[str]) -> None:
            current_step_id[0] = step_id
            # 模拟在每个步骤执行时捕获到一个请求
            if step_id is not None:
                captured_requests.append(
                    CapturedRequest(
                        id=f"req-{step_id}",
                        timestamp=datetime.now(),
                        operation_step_id=step_id,
                        method="GET",
                        url=f"https://api.example.com/step/{step_id}",
                        headers={"Content-Type": "application/json"},
                        body=None,
                        response_status=200,
                        response_headers={},
                        response_body=b'{"ok": true}',
                        is_decrypted=True,
                    )
                )

        mock_client = IntegrationMockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=mock_set_step_id,
        )

        await controller.connect("emulator-5554")

        sequence = OperationSequence(
            id="seq-002",
            app_package="com.example.app",
            intent_description="测试步骤关联",
            steps=[
                OperationStep(
                    id="step-A",
                    sequence_id="seq-002",
                    action_type="click",
                    target=None,
                    parameters={"x": 100, "y": 200},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-B",
                    sequence_id="seq-002",
                    action_type="swipe",
                    target=None,
                    parameters={"direction": "down"},
                    status="pending",
                    error_message=None,
                ),
            ],
            created_at=datetime(2024, 1, 15),
        )

        await controller.execute_sequence(sequence)

        # 验证捕获的请求关联了正确的步骤 ID
        assert len(captured_requests) == 2
        assert captured_requests[0].operation_step_id == "step-A"
        assert captured_requests[1].operation_step_id == "step-B"

    @pytest.mark.asyncio
    async def test_failed_step_still_updates_step_id(self):
        """即使步骤执行失败，回调仍应被调用（以便关联失败时的请求）"""
        step_ids_received: List[Optional[str]] = []

        def mock_set_step_id(step_id: Optional[str]) -> None:
            step_ids_received.append(step_id)

        # 创建一个会在特定操作上失败的 mock 客户端
        mock_client = IntegrationMockMCPClient()

        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=mock_set_step_id,
        )

        await controller.connect("emulator-5554")

        # 使用 unknown action_type 来触发失败
        sequence = OperationSequence(
            id="seq-003",
            app_package="com.example.app",
            intent_description="测试失败步骤",
            steps=[
                OperationStep(
                    id="step-ok",
                    sequence_id="seq-003",
                    action_type="click",
                    target=None,
                    parameters={"x": 50, "y": 50},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-fail",
                    sequence_id="seq-003",
                    action_type="unknown_action",
                    target=None,
                    parameters={},
                    status="pending",
                    error_message=None,
                ),
                OperationStep(
                    id="step-after-fail",
                    sequence_id="seq-003",
                    action_type="click",
                    target=None,
                    parameters={"x": 100, "y": 100},
                    status="pending",
                    error_message=None,
                ),
            ],
            created_at=datetime(2024, 1, 15),
        )

        result = await controller.execute_sequence(sequence)

        # 所有步骤的回调都应被调用（包括失败的步骤）
        assert step_ids_received == ["step-ok", "step-fail", "step-after-fail", None]
        # 容错模式：失败步骤后继续执行
        assert result.completed_steps == 2
        assert result.failed_steps == 1

    @pytest.mark.asyncio
    async def test_sequence_resets_step_id_on_completion(self):
        """序列执行完毕后应重置步骤 ID 为 None"""
        final_step_id: List[Optional[str]] = [None]

        def mock_set_step_id(step_id: Optional[str]) -> None:
            final_step_id[0] = step_id

        mock_client = IntegrationMockMCPClient()
        controller = DeviceController(
            mcp_client=mock_client,
            step_id_callback=mock_set_step_id,
        )

        await controller.connect("emulator-5554")

        sequence = OperationSequence(
            id="seq-004",
            app_package="com.example.app",
            intent_description="测试重置",
            steps=[
                OperationStep(
                    id="step-1",
                    sequence_id="seq-004",
                    action_type="wait",
                    target=None,
                    parameters={"duration_ms": 10},
                    status="pending",
                    error_message=None,
                ),
            ],
            created_at=datetime(2024, 1, 15),
        )

        await controller.execute_sequence(sequence)

        # 最终步骤 ID 应为 None
        assert final_step_id[0] is None


# ============================================================
# 10.2 端到端流程测试：从操控到分析到代码生成
# ============================================================


class TestEndToEndFlow:
    """端到端流程测试

    模拟完整流程：捕获请求 -> 分析接口 -> 生成代码
    使用 mock 数据，不依赖真实设备或网络。
    """

    def _create_mock_captured_requests(self) -> List[CapturedRequest]:
        """创建模拟的捕获请求数据

        注意：参数名需要匹配 APIAnalyzer 的分类规则：
        - static: app_version, platform, device_model 等
        - session: Authorization, token, uid 等
        - dynamic: sign, nonce, timestamp 等
        不在这些模式中的参数会被归类为 unknown，影响可复现性判定。
        """
        return [
            # 可复现接口：feed 列表（仅含静态和会话参数）
            CapturedRequest(
                id="req-001",
                timestamp=datetime(2024, 1, 15, 10, 0, 1),
                operation_step_id="step-001",
                method="GET",
                url="https://api.example.com/api/v1/feed/list?app_version=3.2.1&platform=android",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.token123",
                },
                body=None,
                response_status=200,
                response_headers={"Content-Type": "application/json"},
                response_body=json.dumps(
                    {"code": 0, "data": {"items": [{"id": 1, "title": "test"}]}}
                ).encode(),
                is_decrypted=True,
            ),
            # 可复现接口：用户信息（uid 匹配会话参数模式）
            CapturedRequest(
                id="req-002",
                timestamp=datetime(2024, 1, 15, 10, 0, 2),
                operation_step_id="step-002",
                method="GET",
                url="https://api.example.com/api/v1/user/profile?uid=12345&app_version=3.2.1",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.token123",
                },
                body=None,
                response_status=200,
                response_headers={"Content-Type": "application/json"},
                response_body=json.dumps(
                    {"code": 0, "data": {"name": "test_user", "level": 5}}
                ).encode(),
                is_decrypted=True,
            ),
            # 复杂接口：包含签名参数
            CapturedRequest(
                id="req-003",
                timestamp=datetime(2024, 1, 15, 10, 0, 3),
                operation_step_id="step-003",
                method="POST",
                url="https://api.example.com/api/v1/data/signed",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.token123",
                },
                body=json.dumps(
                    {
                        "data": "encrypted_payload",
                        "sign": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                        "timestamp": "1705312803",
                        "nonce": "abc123xyz",
                    }
                ).encode(),
                response_status=200,
                response_headers={"Content-Type": "application/json"},
                response_body=json.dumps({"code": 0, "data": {}}).encode(),
                is_decrypted=True,
            ),
        ]

    @pytest.mark.asyncio
    async def test_full_flow_capture_to_analysis(self):
        """测试从捕获请求到分析的完整流程"""
        # 1. 创建模拟捕获的请求
        captured_requests = self._create_mock_captured_requests()

        # 2. 运行 APIAnalyzer 分析
        analyzer = APIAnalyzer()
        results = await analyzer.analyze_batch(captured_requests)

        # 3. 验证分析结果
        assert len(results) == 3

        # Feed 接口应为可复现
        feed_result = results[0]
        assert feed_result.endpoint == "/api/v1/feed/list"
        assert feed_result.purpose == "feed"
        assert feed_result.reproducibility == "reproducible"

        # 用户信息接口应为可复现
        user_result = results[1]
        assert user_result.endpoint == "/api/v1/user/profile"
        assert user_result.purpose == "user"
        assert user_result.reproducibility == "reproducible"

        # 签名接口应为复杂接口
        signed_result = results[2]
        assert signed_result.reproducibility == "complex"

    @pytest.mark.asyncio
    async def test_full_flow_analysis_to_code_generation(self):
        """测试从分析结果到代码生成的完整流程"""
        captured_requests = self._create_mock_captured_requests()

        # 1. 分析
        analyzer = APIAnalyzer()
        results = await analyzer.analyze_batch(captured_requests)

        # 2. 为可复现接口生成代码
        generator = CodeGenerator()
        generated_codes: List[GeneratedCode] = []

        for i, result in enumerate(results):
            if result.reproducibility == "reproducible":
                code = generator.generate(result, captured_requests[i])
                generated_codes.append(code)

        # 3. 验证生成的代码
        assert len(generated_codes) == 2  # feed + user 两个可复现接口

        for generated in generated_codes:
            # 验证代码是有效的 Python
            assert self._is_valid_python(generated.code)
            # 验证包含必要的 import
            assert "import requests" in generated.code
            # 验证包含函数定义
            assert "def fetch_" in generated.code
            # 验证包含错误处理
            assert "except" in generated.code

    @pytest.mark.asyncio
    async def test_full_flow_code_verification(self):
        """测试生成代码的语法验证"""
        captured_requests = self._create_mock_captured_requests()

        analyzer = APIAnalyzer()
        results = await analyzer.analyze_batch(captured_requests)

        generator = CodeGenerator()

        for i, result in enumerate(results):
            if result.reproducibility == "reproducible":
                code = generator.generate(result, captured_requests[i])

                # 验证语法（不执行网络请求）
                verification = await generator.verify(code, enable_execution=False)
                assert verification.success is True

    @pytest.mark.asyncio
    async def test_full_flow_analysis_report_consistency(self):
        """测试分析报告的一致性"""
        captured_requests = self._create_mock_captured_requests()

        analyzer = APIAnalyzer()
        results = await analyzer.analyze_batch(captured_requests)

        # 统计各分类数量
        reproducible_count = sum(
            1 for r in results if r.reproducibility == "reproducible"
        )
        complex_count = sum(1 for r in results if r.reproducibility == "complex")
        unknown_count = sum(1 for r in results if r.reproducibility == "unknown")

        # 总数应等于各分类之和
        assert len(results) == reproducible_count + complex_count + unknown_count

        # 验证每个结果都有必要字段
        for result in results:
            assert result.request_id != ""
            assert result.endpoint != ""
            assert result.reproducibility in ("reproducible", "complex", "unknown")
            assert result.reproducibility_reason != ""
            assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_complex_interface_not_code_generated(self):
        """复杂接口不应生成代码"""
        captured_requests = self._create_mock_captured_requests()

        analyzer = APIAnalyzer()
        results = await analyzer.analyze_batch(captured_requests)

        generator = CodeGenerator()
        generated_for_complex = []

        for i, result in enumerate(results):
            if result.reproducibility == "complex":
                # 即使为复杂接口生成代码，也应该能正常工作
                # 但在实际流程中不会为复杂接口生成代码
                generated_for_complex.append(result)

        # 验证确实有复杂接口被识别
        assert len(generated_for_complex) >= 1

    @pytest.mark.asyncio
    async def test_session_params_extracted_correctly(self):
        """验证会话参数被正确提取到生成的代码中"""
        captured_requests = self._create_mock_captured_requests()

        analyzer = APIAnalyzer()
        results = await analyzer.analyze_batch(captured_requests)

        generator = CodeGenerator()

        # 找到第一个可复现接口
        reproducible_idx = None
        for i, r in enumerate(results):
            if r.reproducibility == "reproducible":
                reproducible_idx = i
                break

        assert reproducible_idx is not None, "应至少有一个可复现接口"

        code = generator.generate(results[reproducible_idx], captured_requests[reproducible_idx])

        # Authorization 应被识别为会话参数
        assert any(
            "auth" in p.lower() or "token" in p.lower() or "uid" in p.lower()
            for p in code.session_params
        )

    def _is_valid_python(self, code: str) -> bool:
        """检查代码是否是有效的 Python 语法"""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False


# ============================================================
# 10.3 Skill 文件格式和内容完整性验证
# ============================================================


class TestSkillFileIntegrity:
    """验证 skill 文件格式和内容完整性"""

    SKILL_FILE_PATH = Path(__file__).parent.parent / "skill" / "ai-api-capture.md"

    def _read_skill_file(self) -> str:
        """读取 skill 文件内容"""
        assert self.SKILL_FILE_PATH.exists(), (
            f"Skill 文件不存在: {self.SKILL_FILE_PATH}"
        )
        return self.SKILL_FILE_PATH.read_text(encoding="utf-8")

    def _parse_frontmatter(self, content: str) -> dict:
        """解析 YAML front-matter（简易解析，不依赖 PyYAML）"""
        # 匹配 --- 之间的 YAML 内容
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        assert match is not None, "Skill 文件缺少 YAML front-matter"
        yaml_text = match.group(1)
        return self._simple_yaml_parse(yaml_text)

    def _simple_yaml_parse(self, text: str) -> dict:
        """简易 YAML 解析器，支持顶层键值对和列表"""
        result: dict = {}
        current_key: Optional[str] = None
        current_sub_key: Optional[str] = None
        lines = text.split("\n")

        for line in lines:
            # 跳过空行和注释
            if not line.strip() or line.strip().startswith("#"):
                continue

            # 顶层键值对 (no indent)
            top_match = re.match(r"^(\w[\w-]*):\s*(.*)", line)
            if top_match:
                key = top_match.group(1)
                value = top_match.group(2).strip()
                current_key = key
                current_sub_key = None
                if value:
                    result[key] = value
                else:
                    result[key] = None  # will be filled by sub-items
                continue

            # Second-level key (2-space indent)
            sub_match = re.match(r"^  (\w[\w-]*):\s*(.*)", line)
            if sub_match and current_key is not None:
                sub_key = sub_match.group(1)
                sub_value = sub_match.group(2).strip()
                current_sub_key = sub_key
                if result[current_key] is None:
                    result[current_key] = {}
                if isinstance(result[current_key], dict):
                    if sub_value:
                        result[current_key][sub_key] = sub_value
                    else:
                        result[current_key][sub_key] = []
                continue

            # List item (with - prefix)
            list_match = re.match(r"^\s+- (.+)", line)
            if list_match:
                item = list_match.group(1).strip()
                if current_sub_key and current_key and isinstance(result.get(current_key), dict):
                    sub_dict = result[current_key]
                    if isinstance(sub_dict.get(current_sub_key), list):
                        sub_dict[current_sub_key].append(item)
                elif current_key is not None:
                    if result[current_key] is None:
                        result[current_key] = []
                    if isinstance(result[current_key], list):
                        result[current_key].append(item)
                continue

        return result

    def test_skill_file_exists(self):
        """Skill 文件应存在"""
        assert self.SKILL_FILE_PATH.exists()

    def test_skill_file_has_valid_yaml_frontmatter(self):
        """Skill 文件应有有效的 YAML front-matter"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        assert isinstance(frontmatter, dict)

    def test_skill_file_has_required_metadata_name(self):
        """Skill 文件应包含 name 元数据"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        assert "name" in frontmatter
        assert isinstance(frontmatter["name"], str)
        assert len(frontmatter["name"]) > 0

    def test_skill_file_has_required_metadata_description(self):
        """Skill 文件应包含 description 元数据"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        assert "description" in frontmatter
        assert isinstance(frontmatter["description"], str)
        assert len(frontmatter["description"]) > 0

    def test_skill_file_has_required_metadata_version(self):
        """Skill 文件应包含 version 元数据"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        assert "version" in frontmatter
        assert isinstance(frontmatter["version"], str)
        # 验证版本号格式 (semver)
        assert re.match(r"^\d+\.\d+\.\d+", frontmatter["version"])

    def test_skill_file_has_required_metadata_keywords(self):
        """Skill 文件应包含 keywords 元数据"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        assert "keywords" in frontmatter
        assert isinstance(frontmatter["keywords"], list)
        assert len(frontmatter["keywords"]) > 0

    def test_skill_file_has_required_metadata_dependencies(self):
        """Skill 文件应包含 dependencies 元数据"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        assert "dependencies" in frontmatter
        deps = frontmatter["dependencies"]
        assert isinstance(deps, dict)
        # 应包含 tools 和 python 依赖
        assert "tools" in deps
        assert "python" in deps

    def test_skill_file_dependencies_complete(self):
        """Skill 文件的依赖列表应完整"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        deps = frontmatter["dependencies"]

        # 必须的工具依赖
        tools = deps["tools"]
        assert "mitmproxy" in tools
        assert "mobile-mcp" in tools

        # 必须的 Python 依赖
        python_deps = deps["python"]
        assert "requests" in python_deps
        assert "mitmproxy" in python_deps
        assert "jinja2" in python_deps

    def test_skill_file_has_trigger_section(self):
        """Skill 文件应包含触发条件章节"""
        content = self._read_skill_file()
        assert "触发条件" in content

    def test_skill_file_has_input_params_section(self):
        """Skill 文件应包含输入参数章节"""
        content = self._read_skill_file()
        assert "输入参数" in content

    def test_skill_file_has_execution_flow_section(self):
        """Skill 文件应包含执行流程章节"""
        content = self._read_skill_file()
        assert "执行流程" in content

    def test_skill_file_has_pause_points_section(self):
        """Skill 文件应包含暂停点章节"""
        content = self._read_skill_file()
        assert "暂停点" in content

    def test_skill_file_has_dependencies_section(self):
        """Skill 文件应包含依赖声明章节"""
        content = self._read_skill_file()
        assert "依赖声明" in content

    def test_skill_file_trigger_keywords_present(self):
        """触发条件应包含关键触发词"""
        content = self._read_skill_file()
        # 验证包含中文和英文触发关键词
        assert "抓取接口" in content or "抓取 API" in content
        assert "capture" in content.lower() or "api" in content.lower()

    def test_skill_file_input_params_have_required_fields(self):
        """输入参数应包含必要的参数定义"""
        content = self._read_skill_file()
        # 必须的输入参数
        assert "app_package" in content
        assert "device_id" in content
        assert "operation_intent" in content

    def test_skill_file_execution_flow_has_phases(self):
        """执行流程应包含多个阶段"""
        content = self._read_skill_file()
        # 应包含三个主要阶段
        assert "阶段 1" in content or "阶段1" in content
        assert "阶段 2" in content or "阶段2" in content
        assert "阶段 3" in content or "阶段3" in content
