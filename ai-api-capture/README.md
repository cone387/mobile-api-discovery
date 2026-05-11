# AI API Capture

AI 辅助的移动端接口抓取与分析工具。通过 mitmproxy 抓包 + AI 分析流量，快速将任意 App 的接口转化为结构化的接口文档。

## 概述

**核心理念**：以最低逆向成本，快速将 App 接口转化为可用的数据源文档。

**工作方式**：
1. AI 引导用户明确抓取目标（什么 App、什么数据、哪些页面）
2. 自动配置 mitmproxy 代理环境
3. 用户手动操作 App 触发接口请求
4. AI 自动过滤、分析流量并生成结构化接口报告

**重要说明**：本工具不自动操控设备，全程由用户手动操作 App。AI 负责需求引导、环境准备和流量分析。

## 安装

### 前置要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (推荐的 Python 包管理器)
- mitmproxy 10.1.0+
- adb (Android SDK Platform Tools)
- 已连接的 Android 设备（真机或模拟器，如 MuMu）

### 方式 1：作为 Kiro Skill 使用（推荐）

如果你使用 [Kiro](https://kiro.dev) 开发环境，可以直接将本项目作为 AI Skill 使用：

```bash
# 1. 克隆项目
git clone <repository-url>
cd ai-api-capture

# 2. 安装依赖
uv sync

# 3. 将 skill 文件复制到 Kiro skills 目录
# 工作区级别（仅当前项目生效）：
cp skill/ai-api-capture.md .kiro/skills/

# 或全局级别（所有项目生效）：
cp skill/ai-api-capture.md ~/.kiro/skills/
```

安装完成后，在 Kiro 中直接用自然语言触发：
```
帮我抓取某App的首页列表接口和详情接口
```

AI 会自动激活本 Skill 并引导完成整个流程。

### 方式 2：作为 Python 包安装

```bash
# 克隆项目
git clone <repository-url>
cd ai-api-capture

# 使用 uv 安装（推荐）
uv sync

# 安装开发依赖
uv sync --extra dev

# 或使用 pip
pip install -e ".[dev]"
```

### 方式 3：发布到 PyPI

```bash
# 构建
uv build

# 发布（需要 PyPI 账号）
uv publish
```

## 快速开始

### 作为 Kiro Skill（自然语言交互）

在 Kiro 中直接描述需求：

```
帮我抓取河马漫剧的首页列表和详情接口，设备是 127.0.0.1:16384
```

AI 会自动完成：需求确认 → 环境配置 → 等待操作 → 流量分析 → 生成报告。

### 编程方式使用

```python
from src.capture_system import CaptureSystem
from src.models import CaptureTarget

# 初始化系统
system = CaptureSystem(
    storage_path="./output/captures",
    output_dir="./output/analysis",
)

# 阶段 1: 需求收集（自然语言解析）
status = system.collect_requirements("抓取河马漫剧的首页列表和详情接口")
print(status.message)

# 或直接设置目标
target = CaptureTarget(
    app_name="河马漫剧",
    target_data="首页列表、详情页剧集列表",
    operation_pages="首页、详情页",
)
system.set_target(target)

# 阶段 2: 环境准备（由 EnvironmentManager 处理）
env = system.environment_manager
await env.check_device("127.0.0.1:16384")
await env.set_proxy("127.0.0.1:16384", "10.0.2.2", 8080)
await env.start_mitmdump("addons/capture_addon.py", 8080)
system.mark_environment_ready()

# 阶段 3: 录制（用户操作 App 期间）
system.start_recording()
# ... 用户在手机上操作 App ...
summary = system.stop_recording()  # 自动触发分析

# 阶段 4: 查看结果
print(summary)
print(f"报告路径: {system.report_path}")
```

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                  CaptureSystem（主协调器）                     │
├──────────────┬───────────────┬──────────────┬───────────────┤
│ Requirement  │  Environment  │   Traffic    │  API Analyzer │
│  Collector   │   Manager     │ Interceptor  │  + Reporter   │
├──────────────┼───────────────┼──────────────┼───────────────┤
│  NLP 解析    │  adb + proxy  │  mitmproxy   │  模式识别     │
│  需求引导    │  证书安装     │  4层过滤     │  报告生成     │
└──────────────┴───────────────┴──────────────┴───────────────┘
```

**四阶段工作流**：

1. **需求收集** — RequirementCollector 解析用户意图，提取 App 名称、目标数据、操作页面
2. **环境准备** — EnvironmentManager 通过 adb 配置设备代理、安装证书、启动 mitmdump
3. **流量录制** — TrafficInterceptor 配合 capture_addon.py 实时过滤并保存业务流量
4. **分析报告** — APIAnalyzer 分析接口特征，ReportGenerator 生成 Markdown 报告

## 流量过滤（内置 4 层）

```python
from src.traffic_interceptor import TrafficInterceptor
from src.models import FilterRules

interceptor = TrafficInterceptor(
    storage_path="./output/captures",
    filter_rules=FilterRules(
        domains=["api.example.com"],           # 域名白名单
        path_patterns=["/api/.*"],             # 路径正则
        content_types=["application/json"],    # Content-Type 过滤
        exclude_domains=["analytics.example.com"],  # 排除域名
    ),
)
```

**4 层过滤机制**：
1. 静态资源过滤（image/font/video/css/js）
2. 第三方 SDK 域名黑名单（埋点、广告、推送、崩溃上报等）
3. 路径黑名单（/sdk/、/reportBatchData 等）
4. 业务 API 白名单（JSON 响应 + API 路径模式）

## 输出结构

```
output/
├── captures/          # 捕获的原始流量（JSON，每个请求一个文件）
├── analysis/          # 分析报告
│   ├── {app}_api_report.md   # AI 撰写的接口报告
│   └── samples/              # 接口请求/响应样本
│       ├── portal_1125_request.json
│       ├── portal_1125_response.json
│       └── ...
├── generated/         # 生成的采集代码（预留）
└── data/              # 批量采集的数据（预留）
```

## 项目结构

```
ai-api-capture/
├── src/                          # 核心源码
│   ├── __init__.py
│   ├── capture_system.py         # 主协调器：串联四阶段流程
│   ├── requirement_collector.py  # 需求收集：NLP 解析用户意图
│   ├── environment_manager.py    # 环境管理：adb/代理/证书/mitmdump
│   ├── traffic_interceptor.py    # 流量拦截：过滤规则 + 存储
│   ├── api_analyzer.py           # 接口分析：参数分类与模式识别
│   ├── report_generator.py       # 报告生成：Markdown 格式报告
│   ├── models.py                 # 数据模型：所有核心数据结构
│   └── storage.py                # 存储层：JSON 文件管理
├── addons/
│   └── capture_addon.py          # mitmproxy addon 脚本（实时过滤）
├── skill/
│   └── ai-api-capture.md         # AI Skill 指令文件（v4.0.0）
├── tests/                        # 测试文件
│   ├── test_api_analyzer.py      # 分析器单元测试
│   ├── test_analyzer_property.py # 属性测试：参数分类一致性
│   ├── test_filter_property.py   # 属性测试：过滤规则不变量
│   ├── test_filter_rules.py      # 过滤规则单元测试
│   ├── test_integration.py       # 集成测试
│   ├── test_models.py            # 数据模型测试
│   ├── test_report_generator.py  # 报告生成器测试
│   ├── test_storage.py           # 存储层测试
│   └── test_traffic_interceptor.py
├── output/                       # 默认输出目录
├── pyproject.toml                # 项目配置与依赖
├── README.md                     # 本文件
└── LICENSE                       # MIT License
```

## 开发

### 运行测试

```bash
# 使用 uv 运行全部测试
uv run pytest -v --timeout=30

# 运行特定模块
uv run pytest tests/test_api_analyzer.py -v

# 运行属性测试
uv run pytest tests/test_analyzer_property.py tests/test_filter_property.py -v

# 带覆盖率
uv run pytest --cov=src
```

### 代码规范

- Python 3.11+ 类型注解
- 异步模块使用 `async/await`
- 数据模型使用 `@dataclass`
- 测试使用 pytest + hypothesis（属性测试）

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Python 3.11+ | 异步支持、类型注解 |
| 流量拦截 | mitmproxy (Python API) | 深度集成、实时过滤 |
| 设备管理 | adb | 代理设置、证书安装 |
| HTTP 客户端 | requests / httpx / aiohttp | 同步+异步 |
| 数据存储 | JSON 文件 | 保持可读性 |
| 测试框架 | pytest + hypothesis | 单元测试 + 属性测试 |
| 包管理 | uv + hatchling | 现代 Python 工具链 |

## 许可证

MIT License
