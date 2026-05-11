"""集成测试与端到端验证

测试内容：
- CaptureSystem 四阶段流程集成测试
- Skill 文件格式和内容完整性验证
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from src.capture_system import CapturePhase, CaptureSystem
from src.models import (
    CaptureTarget,
    FilterRules,
)


# ============================================================
# CaptureSystem 集成测试


class TestCaptureSystemIntegration:
    """CaptureSystem 四阶段流程集成测试"""

    def test_initial_phase_is_idle(self):
        """系统初始化后应处于 IDLE 阶段"""
        system = CaptureSystem()
        assert system.phase == CapturePhase.IDLE

    def test_collect_requirements_transitions_to_collecting(self):
        """收集需求后应进入 COLLECTING 阶段"""
        system = CaptureSystem()
        system.collect_requirements("帮我抓取某App的接口")
        assert system.phase == CapturePhase.COLLECTING

    def test_set_target_works_with_complete_info(self):
        """完整 target 应能正常设置"""
        system = CaptureSystem()
        target = CaptureTarget(
            app_name="河马漫剧",
            target_data="首页列表、详情接口",
            operation_pages="首页、详情页",
        )
        system.set_target(target)
        assert system.target is not None
        assert system.target.app_name == "河马漫剧"

    def test_set_target_rejects_incomplete(self):
        """不完整的 target 应被拒绝"""
        system = CaptureSystem()
        with pytest.raises(ValueError, match="不完整"):
            system.set_target(CaptureTarget(app_name="", target_data="", operation_pages=""))

    def test_mark_environment_ready_requires_target(self):
        """标记环境就绪前必须设置 target"""
        system = CaptureSystem()
        with pytest.raises(RuntimeError):
            system.mark_environment_ready()

    def test_mark_environment_ready_transitions_phase(self):
        """设置 target 后可标记环境就绪"""
        system = CaptureSystem()
        target = CaptureTarget(
            app_name="测试App",
            target_data="列表数据",
            operation_pages="首页",
        )
        system.set_target(target)
        system.mark_environment_ready()
        assert system.phase == CapturePhase.ENVIRONMENT_READY

    def test_start_recording_transitions_phase(self):
        """开始录制应进入 RECORDING 阶段"""
        system = CaptureSystem()
        target = CaptureTarget(
            app_name="测试App",
            target_data="列表数据",
            operation_pages="首页",
        )
        system.set_target(target)
        system.mark_environment_ready()
        system.start_recording()
        assert system.phase == CapturePhase.RECORDING

    def test_start_recording_twice_raises(self):
        """重复开始录制应报错"""
        system = CaptureSystem()
        target = CaptureTarget(
            app_name="测试App",
            target_data="列表数据",
            operation_pages="首页",
        )
        system.set_target(target)
        system.mark_environment_ready()
        system.start_recording()
        with pytest.raises(RuntimeError, match="已在录制中"):
            system.start_recording()

    def test_stop_recording_without_start_raises(self):
        """未开始录制时停止应报错"""
        system = CaptureSystem()
        with pytest.raises(RuntimeError, match="未在录制中"):
            system.stop_recording()


# ============================================================
# Skill 文件完整性测试


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
        """解析 YAML front-matter（简易解析）"""
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
            if not line.strip() or line.strip().startswith("#"):
                continue

            top_match = re.match(r"^(\w[\w-]*):\s*(.*)", line)
            if top_match:
                key = top_match.group(1)
                value = top_match.group(2).strip()
                current_key = key
                current_sub_key = None
                if value:
                    result[key] = value
                else:
                    result[key] = None
                continue

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
        assert "tools" in deps
        assert "python" in deps

    def test_skill_file_dependencies_complete(self):
        """Skill 文件的依赖列表应完整"""
        content = self._read_skill_file()
        frontmatter = self._parse_frontmatter(content)
        deps = frontmatter["dependencies"]

        tools = deps["tools"]
        tool_names = " ".join(tools)
        assert "mitmproxy" in tool_names
        assert "adb" in tool_names

        python_deps = deps["python"]
        python_names = " ".join(python_deps)
        assert "mitmproxy" in python_names
        assert "requests" in python_names

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
        """Skill 文件应包含依赖章节"""
        content = self._read_skill_file()
        assert "依赖" in content

    def test_skill_file_trigger_keywords_present(self):
        """触发条件应包含关键触发词"""
        content = self._read_skill_file()
        assert "抓取接口" in content or "抓取 API" in content
        assert "capture" in content.lower() or "api" in content.lower()

    def test_skill_file_input_params_have_required_fields(self):
        """输入参数应包含必要的参数定义"""
        content = self._read_skill_file()
        assert "app_name" in content
        assert "device_id" in content
        assert "target_data" in content

    def test_skill_file_execution_flow_has_phases(self):
        """执行流程应包含多个阶段"""
        content = self._read_skill_file()
        assert "阶段 1" in content or "阶段1" in content
        assert "阶段 2" in content or "阶段2" in content
        assert "阶段 3" in content or "阶段3" in content
