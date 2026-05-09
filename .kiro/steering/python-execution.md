---
inclusion: always
---

# Python 执行约束

## 强制要求

- 本项目 Python 代码必须使用 `uv run` 执行
- 工作目录为 `ai-api-capture`（使用 cwd 参数指定）
- 虚拟环境位于 `D:\codespace\mobile-api-discovery\ai-api-capture\.venv`
- 禁止使用裸 `python` 或 `python.exe` 命令
- **Windows 系统**：shell 是 cmd，不能用 `;` 分隔命令，用 `&` 或 `&&`
- **cwd 参数不可靠时**：直接在命令中用 `cd /d <path> && uv run ...` 的方式切换目录

## 执行方式

由于 cwd 参数在 Windows cmd 下可能不生效，统一使用以下格式：

```cmd
cd /d D:\codespace\mobile-api-discovery\ai-api-capture && uv run pytest tests/test_api_analyzer.py -v --timeout=30
```

## 示例

运行测试：
```cmd
cd /d D:\codespace\mobile-api-discovery\ai-api-capture && uv run pytest tests/test_api_analyzer.py -v --timeout=30
```

运行脚本：
```cmd
cd /d D:\codespace\mobile-api-discovery\ai-api-capture && uv run python scripts/analyze_apis.py
```

导入验证：
```cmd
cd /d D:\codespace\mobile-api-discovery\ai-api-capture && uv run python -c "from src.models import *; print('OK')"
```
