# AI API Capture

AI 驱动的移动端接口抓取与代码生成系统。

## 概述

本系统通过 AI 操控真实移动设备触发 App 行为，利用 mitmproxy 抓取网络请求，再由 AI 分析接口特征并自动分类。核心目标是以最低逆向成本，快速将 App 接口转化为可用数据源。

**核心理念**：

- **可复现接口** → 自动生成 Python requests 代码，脱离设备进行批量数据采集
- **复杂接口**（含签名/加密） → 继续通过客户端触发配合代理拦截保存数据

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                  Capture System（主协调器）                    │
├──────────────┬───────────────┬──────────────┬───────────────┤
│   Device     │    Traffic    │     API      │     Code      │
│  Controller  │  Interceptor  │   Analyzer   │   Generator   │
├──────────────┼───────────────┼──────────────┼───────────────┤
│  MCP Client  │   mitmproxy   │   LLM API   │   Jinja2      │
│              │   (Python)    │              │   Template    │
└──────────────┴───────────────┴──────────────┴───────────────┘
       │               │               │               │
       ▼               ▼               ▼               ▼
  移动设备         代理服务器        AI 服务         生成代码
                                                       │
                                                       ▼
                                              ┌────────────────┐
                                              │  Batch Crawler  │
                                              │  (批量采集器)    │
                                              └────────────────┘
```

**三阶段工作流程**：

1. **操控与捕获** — AI 操控设备执行 App 操作，mitmproxy 捕获所有网络流量
2. **分析与分类** — AI 分析接口参数特征，判定可复现性
3. **分路径采集** — 可复现接口生成代码批量采集；复杂接口通过设备回放采集

## 安装

### 前置要求

- Python 3.11+
- mitmproxy 10.1.0+
- 已连接的 Android/iOS 设备（真机或模拟器）
- mobile-mcp 服务器

### 步骤 1：安装 Python 包

```bash
# 克隆项目
git clone <repository-url>
cd ai-api-capture

# 安装项目及依赖（含开发依赖）
pip install -e ".[dev]"
```

### 步骤 2：安装 mitmproxy

```bash
# macOS
brew install mitmproxy

# 或通过 pip（已包含在项目依赖中）
pip install mitmproxy

# 验证安装
mitmproxy --version
```

### 步骤 3：配置设备代理

#### Android 设备

1. 确保设备与电脑在同一网络
2. 获取电脑 IP 地址（如 `192.168.1.100`）
3. 设备 Wi-Fi 设置 → 修改网络 → 代理 → 手动
   - 主机名：`192.168.1.100`
   - 端口：`8080`
4. 安装 CA 证书：
   - 设备浏览器访问 `http://mitm.it`
   - 下载并安装 Android 证书
   - Android 7+ 需要额外配置系统级证书信任

#### iOS 设备

1. 确保设备与电脑在同一网络
2. 设置 → Wi-Fi → 当前网络 → 配置代理 → 手动
   - 服务器：电脑 IP
   - 端口：`8080`
3. Safari 访问 `http://mitm.it` 下载证书
4. 设置 → 通用 → 关于本机 → 证书信任设置 → 启用 mitmproxy 证书

### 步骤 4：配置 mobile-mcp

确保 mobile-mcp 服务器已启动并可访问。参考 mobile-mcp 文档完成设备连接配置。

```bash
# 验证设备连接
# 通过 AI 代理调用 mobile_list_available_devices 确认设备可见
```

## 快速开始

### 作为 AI Skill 使用（推荐）

在支持 skill 规范的 AI 开发环境中，直接用自然语言描述需求：

```
帮我抓取 com.example.app 的首页 feed 接口，设备是 emulator-5554
```

AI 代理将自动激活本 skill 并引导完成整个流程。

### 编程方式使用

```python
import asyncio
from src.capture_system import CaptureSystem
from src.models import OperationSequence, OperationStep

async def main():
    system = CaptureSystem(output_path="./output")
    
    # 1. 连接设备并启动 App
    await system.connect_device("emulator-5554")
    await system.launch_app("com.example.app")
    
    # 2. 执行操作序列（触发接口请求）
    sequence = OperationSequence(
        id="seq_001",
        app_package="com.example.app",
        intent_description="浏览首页 feed 流",
        steps=[
            OperationStep(id="step_1", sequence_id="seq_001",
                         action_type="swipe", target=None,
                         parameters={"direction": "up"}),
        ]
    )
    await system.execute_and_capture(sequence)
    
    # 3. 分析捕获的接口
    results = await system.analyze_captured_requests()
    
    # 4. 为可复现接口生成代码
    for result in results:
        if result.reproducibility == "reproducible":
            code = system.generate_code(result)
            print(f"生成代码: {code.api_id}")
    
    # 5. 生成报告
    report = system.generate_report()
    print(report)

asyncio.run(main())
```

## 配置选项

### 流量过滤

```python
from src.traffic_interceptor import TrafficInterceptor, FilterRules

interceptor = TrafficInterceptor()
interceptor.set_filter(FilterRules(
    domains=["api.example.com"],           # 仅捕获指定域名
    path_patterns=["/api/.*"],             # 路径正则匹配
    content_types=["application/json"],    # 仅捕获 JSON 响应
    exclude_domains=["analytics.example.com"]  # 排除域名
))
```

### 批量采集配置

```python
from src.models import CrawlConfig

config = CrawlConfig(
    concurrency=5,           # 并发请求数
    interval_ms=1000,        # 请求间隔（毫秒）
    max_rounds=100,          # 最大采集轮次
    failure_threshold=10,    # 连续失败阈值（达到后自动暂停）
    round_interval_ms=5000   # 轮次间隔（毫秒，回放模式）
)
```

### 输出目录结构

```
output/
├── captures/      # 捕获的原始流量数据（JSON）
├── analysis/      # 接口分析报告（Markdown）
├── generated/     # 生成的 Python 采集代码
└── data/          # 批量采集的数据（JSON）
```

## 使用示例

### 示例 1：抓取电商 App 商品列表接口

```
目标：采集某电商 App 的商品列表数据
操作意图：打开 App → 进入商品分类页 → 滑动浏览商品列表

预期结果：
- 识别出商品列表 API（如 /api/products/list）
- 判定为可复现接口（仅含分页参数和会话 Token）
- 生成批量采集代码，支持翻页采集全部商品
```

### 示例 2：抓取社交 App Feed 流

```
目标：采集某社交 App 的 Feed 流内容
操作意图：打开 App → 在首页上下滑动浏览 Feed

预期结果：
- 识别出 Feed 接口（如 /api/feed/recommend）
- 可能包含动态签名参数 → 标记为复杂接口
- 通过回放方式持续采集 Feed 数据
```

### 示例 3：抓取新闻 App 文章详情

```
目标：采集新闻 App 的文章详情内容
操作意图：打开 App → 点击文章列表中的多篇文章 → 获取详情

预期结果：
- 识别出文章详情 API（如 /api/article/{id}）
- 判定为可复现接口
- 生成代码，支持传入文章 ID 列表批量获取详情
```

## 项目结构

```
ai-api-capture/
├── src/                          # 核心源码
│   ├── __init__.py
│   ├── capture_system.py         # 主协调器：串联三阶段流程
│   ├── device_controller.py      # 设备操控：MCP 协议操控移动设备
│   ├── traffic_interceptor.py    # 流量拦截：mitmproxy 捕获与存储
│   ├── api_analyzer.py           # 接口分析：参数分类与可复现性判定
│   ├── code_generator.py         # 代码生成：生成 Python requests 代码
│   ├── batch_crawler.py          # 批量采集：异步并发数据采集
│   ├── replay_controller.py      # 回放控制：复杂接口的设备回放采集
│   ├── report_generator.py       # 报告生成：Markdown 格式汇总报告
│   ├── models.py                 # 数据模型：所有核心数据结构定义
│   └── storage.py                # 存储层：JSON 文件 + SQLite 索引
├── addons/
│   └── capture_addon.py          # mitmproxy addon 脚本
├── templates/
│   └── code_template.py.jinja    # 代码生成 Jinja2 模板
├── skill/
│   └── ai-api-capture.md         # AI Skill 指令文件
├── output/                       # 默认输出目录
│   ├── captures/                 # 捕获的流量数据
│   ├── analysis/                 # 分析报告
│   ├── generated/                # 生成的代码
│   └── data/                     # 采集的数据
├── tests/                        # 测试文件
│   ├── test_api_analyzer.py
│   ├── test_analyzer_property.py # 属性测试：参数分类一致性
│   ├── test_batch_crawler.py
│   ├── test_code_generator.py
│   ├── test_device_controller.py
│   ├── test_filter_property.py   # 属性测试：过滤规则不变量
│   ├── test_filter_rules.py
│   ├── test_models.py
│   ├── test_replay_controller.py
│   ├── test_report_generator.py
│   ├── test_storage.py
│   └── test_traffic_interceptor.py
├── pyproject.toml                # 项目配置与依赖声明
├── README.md                     # 本文件
└── LICENSE
```

## 开发指南

### 环境搭建

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -e ".[dev]"
```

### 运行测试

```bash
# 运行全部测试
pytest

# 运行特定模块测试
pytest tests/test_api_analyzer.py

# 运行属性测试
pytest tests/test_analyzer_property.py tests/test_filter_property.py

# 带详细输出
pytest -v

# 运行测试并显示覆盖率
pytest --cov=src
```

### 代码规范

- 使用 Python 3.11+ 类型注解
- 异步模块使用 `async/await` 语法
- 数据模型使用 `@dataclass` 装饰器
- 模板文件使用 Jinja2 语法

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Python 3.11+ | 异步支持、类型注解 |
| 设备操控 | Mobile MCP | 通过 MCP 协议操控移动设备 |
| 流量拦截 | mitmproxy (Python API) | 深度集成、实时过滤 |
| HTTP 客户端 | requests / httpx / aiohttp | 同步+异步，覆盖不同场景 |
| 数据存储 | JSON + SQLite | JSON 保持可读性，SQLite 提供索引 |
| 代码生成 | Jinja2 模板 | 灵活的模板引擎 |
| 测试框架 | pytest + hypothesis | 单元测试 + 属性测试 |

## 许可证

MIT License
