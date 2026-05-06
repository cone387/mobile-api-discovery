# 设计文档

## 概述

本设计文档描述 AI 驱动的移动端接口抓取与代码生成系统的技术架构和实现方案。系统采用模块化设计，核心流程分为三个阶段：设备操控与流量捕获、接口分析与分类、分路径数据采集。

## 技术栈

- **语言**: Python 3.11+
- **设备操控**: Mobile MCP (通过 MCP 协议操控移动设备)
- **流量拦截**: mitmproxy (Python API 模式)
- **HTTP 客户端**: requests / httpx
- **数据存储**: JSON 文件 + SQLite（索引和元数据）
- **AI 分析**: LLM API（通过 AI 代理调用）
- **并发控制**: asyncio + aiohttp
- **Skill 格式**: Markdown steering 文件

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    Capture System (协调层)                 │
├─────────────┬──────────────┬──────────────┬─────────────┤
│  Device     │   Traffic    │    API       │    Code     │
│  Controller │   Interceptor│    Analyzer  │    Generator│
├─────────────┼──────────────┼──────────────┼─────────────┤
│  MCP Client │   mitmproxy  │   LLM API   │   Template  │
│             │   (Python)   │             │   Engine    │
└─────────────┴──────────────┴──────────────┴─────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
   Mobile Device   Proxy Server   AI Service   Generated Code
```

## 数据模型

### CapturedRequest（捕获的请求）

```python
@dataclass
class CapturedRequest:
    id: str                    # 唯一标识
    timestamp: datetime        # 捕获时间
    operation_step_id: str     # 关联的操作步骤 ID
    method: str                # HTTP 方法
    url: str                   # 完整 URL
    headers: dict              # 请求头
    body: Optional[bytes]      # 请求体
    response_status: int       # 响应状态码
    response_headers: dict     # 响应头
    response_body: Optional[bytes]  # 响应体
    is_decrypted: bool         # 是否成功解密 HTTPS
```

### OperationStep（操作步骤）

```python
@dataclass
class OperationStep:
    id: str                    # 步骤 ID
    sequence_id: str           # 所属操作序列 ID
    action_type: str           # 操作类型: click, swipe, input, navigate, wait
    target: Optional[str]      # 操作目标（元素标识或坐标）
    parameters: dict           # 操作参数
    status: str                # 执行状态: pending, success, failed, skipped
    error_message: Optional[str]  # 失败原因
```

### OperationSequence（操作序列）

```python
@dataclass
class OperationSequence:
    id: str                    # 序列 ID
    app_package: str           # 目标 App 包名
    intent_description: str    # 操作意图描述
    steps: List[OperationStep] # 操作步骤列表
    created_at: datetime       # 创建时间
```

### APIAnalysisResult（接口分析结果）

```python
@dataclass
class ParameterInfo:
    name: str                  # 参数名
    value_sample: str          # 样本值
    category: str              # 分类: static, session, dynamic, unknown
    source: str                # 来源位置: query, header, body, cookie
    reasoning: str             # 分类依据

@dataclass
class APIAnalysisResult:
    request_id: str            # 关联的请求 ID
    endpoint: str              # 接口路径
    purpose: str               # 接口用途（feed/user/comment/search 等）
    parameters: List[ParameterInfo]  # 参数分析列表
    reproducibility: str       # 可复现性: reproducible, complex, unknown
    reproducibility_reason: str # 判定依据
    confidence: float          # 置信度 0-1
```

### GeneratedCode（生成的代码）

```python
@dataclass
class GeneratedCode:
    api_id: str                # 关联的接口分析 ID
    code: str                  # 生成的 Python 代码
    session_params: List[str]  # 需要用户配置的会话参数名
    verification_status: str   # 验证状态: pending, passed, failed
    failure_reason: Optional[str]  # 验证失败原因
```

### CrawlTask（采集任务）

```python
@dataclass
class CrawlTask:
    id: str                    # 任务 ID
    api_id: str                # 目标接口 ID
    mode: str                  # 采集模式: batch, replay
    config: CrawlConfig        # 采集配置
    status: str                # 任务状态: running, paused, completed, failed
    stats: CrawlStats          # 采集统计

@dataclass
class CrawlConfig:
    concurrency: int           # 并发数（batch 模式）
    interval_ms: int           # 请求间隔毫秒
    max_rounds: int            # 最大轮次（replay 模式）
    failure_threshold: int     # 连续失败阈值
    round_interval_ms: int     # 轮次间隔（replay 模式）

@dataclass
class CrawlStats:
    total_requests: int        # 总请求数
    success_count: int         # 成功数
    failure_count: int         # 失败数
    consecutive_failures: int  # 当前连续失败数
    data_collected: int        # 已采集数据条数
```

## 模块设计

### 1. Device_Controller 模块

**职责**: 通过 MCP 协议操控移动设备

**核心接口**:
```python
class DeviceController:
    async def connect(self, device_id: str) -> ConnectionResult
    async def launch_app(self, package_name: str) -> bool
    async def execute_sequence(self, sequence: OperationSequence) -> SequenceResult
    async def execute_step(self, step: OperationStep) -> StepResult
    async def get_screen_elements(self) -> List[ScreenElement]
    async def disconnect(self) -> None
```

**实现要点**:
- 使用 MCP 客户端连接 mobile-mcp 服务器
- 操作步骤之间添加适当等待时间，模拟真实用户行为
- 步骤失败时记录错误并继续执行后续步骤（容错模式）
- 支持截图用于 AI 分析当前页面状态

### 2. Traffic_Interceptor 模块

**职责**: 通过 mitmproxy 捕获和存储网络流量

**核心接口**:
```python
class TrafficInterceptor:
    async def start(self, config: ProxyConfig) -> None
    async def stop(self) -> None
    async def set_filter(self, rules: FilterRules) -> None
    async def get_captured_requests(self) -> List[CapturedRequest]
    async def clear(self) -> None
    def on_request_captured(self, callback: Callable) -> None
```

**实现要点**:
- 使用 mitmproxy 的 Python API（mitmdump + addon 脚本）
- 通过 addon 脚本实时捕获请求并写入存储
- 支持域名、路径、Content-Type 过滤
- 为每条记录关联当前正在执行的操作步骤 ID
- HTTPS 解密失败时标记为 `is_decrypted=False`

**mitmproxy addon 脚本设计**:
```python
class CaptureAddon:
    def __init__(self, storage_path: str, filter_rules: FilterRules):
        self.storage_path = storage_path
        self.filter_rules = filter_rules
        self.current_step_id = None

    def request(self, flow: http.HTTPFlow) -> None:
        # 记录请求开始时间
        flow.metadata["capture_time"] = datetime.now().isoformat()
        flow.metadata["step_id"] = self.current_step_id

    def response(self, flow: http.HTTPFlow) -> None:
        if self._matches_filter(flow):
            self._save_flow(flow)

    def tls_failed_client_hello(self, client_hello):
        # 标记 HTTPS 解密失败
        pass
```

### 3. API_Analyzer 模块

**职责**: 分析接口特征并判定可复现性

**核心接口**:
```python
class APIAnalyzer:
    async def analyze_batch(self, requests: List[CapturedRequest]) -> List[APIAnalysisResult]
    async def analyze_single(self, request: CapturedRequest) -> APIAnalysisResult
    def classify_parameter(self, name: str, value: str, context: RequestContext) -> ParameterInfo
    def determine_reproducibility(self, params: List[ParameterInfo]) -> Tuple[str, str]
```

**参数分类规则**:
- **静态参数**: 多次请求中值不变的参数（如 app_version, platform）
- **会话参数**: 符合 Token/Cookie 模式的参数（如 Authorization, session_id）
- **动态参数**: 每次请求值都不同且无法预测的参数（如 sign, nonce, encrypted_data）
- **未知参数**: 无法确定分类的参数

**可复现性判定逻辑**:
```python
def determine_reproducibility(self, params: List[ParameterInfo]) -> Tuple[str, str]:
    dynamic_params = [p for p in params if p.category == "dynamic"]
    unknown_params = [p for p in params if p.category == "unknown"]
    
    if not dynamic_params and not unknown_params:
        return ("reproducible", "所有参数均为静态或会话类型，可直接复现")
    elif dynamic_params:
        return ("complex", f"包含动态参数: {[p.name for p in dynamic_params]}")
    else:
        return ("unknown", f"包含未确定参数: {[p.name for p in unknown_params]}")
```

### 4. Code_Generator 模块

**职责**: 为可复现接口生成 Python requests 代码

**核心接口**:
```python
class CodeGenerator:
    def generate(self, analysis: APIAnalysisResult, request: CapturedRequest) -> GeneratedCode
    async def verify(self, generated: GeneratedCode) -> VerificationResult
    def extract_session_params(self, request: CapturedRequest, params: List[ParameterInfo]) -> List[str]
```

**代码生成模板结构**:
```python
# 生成的代码模板示例
"""
import requests

# === 会话参数（需要用户配置） ===
# 获取方式: 从浏览器开发者工具或 App 抓包获取
TOKEN = "your_token_here"

# === 请求函数 ===
def fetch_{endpoint_name}({param_args}):
    url = "{url}"
    headers = {headers_dict}
    params = {params_dict}
    
    try:
        response = requests.{method}(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"请求失败: {e}")
        return None
"""
```

### 5. Batch_Crawler 模块

**职责**: 执行批量数据采集

**核心接口**:
```python
class BatchCrawler:
    async def start_task(self, task: CrawlTask) -> None
    async def pause_task(self, task_id: str) -> None
    async def resume_task(self, task_id: str) -> None
    def get_task_stats(self, task_id: str) -> CrawlStats
```

**实现要点**:
- 使用 asyncio + aiohttp 实现并发控制
- 通过信号量控制并发数
- 请求间隔使用 asyncio.sleep
- 连续失败计数器达到阈值时自动暂停
- 检测 401/403 响应码触发认证失败处理

### 6. Replay_Controller 模块

**职责**: 对复杂接口通过设备操作重复触发采集

**核心接口**:
```python
class ReplayController:
    async def generate_replay_sequence(self, api: APIAnalysisResult, original_sequence: OperationSequence) -> OperationSequence
    async def execute_replay(self, task: CrawlTask) -> ReplayResult
```

**实现要点**:
- 从原始操作序列中提取触发目标接口的最小操作子集
- 每轮执行后等待配置的间隔时间
- 通过 Traffic_Interceptor 的过滤功能仅捕获目标接口
- 重试一次后仍失败则标记为"采集失败"

## 文件结构

```
ai-api-capture/
├── src/
│   ├── __init__.py
│   ├── capture_system.py        # 主协调器
│   ├── device_controller.py     # 设备操控模块
│   ├── traffic_interceptor.py   # 流量拦截模块
│   ├── api_analyzer.py          # 接口分析模块
│   ├── code_generator.py        # 代码生成模块
│   ├── batch_crawler.py         # 批量采集模块
│   ├── replay_controller.py     # 回放控制模块
│   ├── models.py                # 数据模型定义
│   ├── storage.py               # 数据存储层
│   └── report_generator.py      # 报告生成模块
├── addons/
│   └── capture_addon.py         # mitmproxy addon 脚本
├── templates/
│   └── code_template.py.jinja   # 代码生成模板
├── skill/
│   └── ai-api-capture.md        # 通用 AI skill 指令文件
├── output/                      # 默认输出目录
│   ├── captures/                # 捕获的流量数据
│   ├── analysis/                # 分析报告
│   ├── generated/               # 生成的代码
│   └── data/                    # 采集的数据
├── tests/
│   ├── test_traffic_interceptor.py
│   ├── test_api_analyzer.py
│   ├── test_code_generator.py
│   ├── test_batch_crawler.py
│   └── test_models.py
├── pyproject.toml
└── README.md
```

## 正确性属性

### 属性 1: 请求存储 Round-Trip（需求 1.4, 2.2）

**类型**: Round-Trip

**描述**: CapturedRequest 对象序列化到 JSON 文件后再反序列化，应得到等价对象。

```python
from hypothesis import given, strategies as st

@given(st.builds(CapturedRequest, ...))
def test_captured_request_roundtrip(request):
    serialized = request.to_json()
    deserialized = CapturedRequest.from_json(serialized)
    assert deserialized == request
```

### 属性 2: 过滤规则不变量（需求 2.5）

**类型**: Metamorphic / Invariant

**描述**: 过滤后的请求列表中每条记录都满足过滤规则；过滤后的列表长度不超过原始列表长度。

```python
@given(requests=st.lists(captured_request_strategy()), rules=filter_rules_strategy())
def test_filter_invariant(requests, rules):
    filtered = apply_filter(requests, rules)
    assert len(filtered) <= len(requests)
    for req in filtered:
        assert matches_rules(req, rules)
```

### 属性 3: 参数分类与可复现性判定一致性（需求 3.3）

**类型**: Invariant

**描述**: 如果接口被标记为"可复现"，则其参数列表中不包含 category 为 "dynamic" 的参数。

```python
@given(params=st.lists(parameter_info_strategy()))
def test_reproducibility_consistency(params):
    result, reason = determine_reproducibility(params)
    if result == "reproducible":
        assert all(p.category != "dynamic" for p in params)
        assert all(p.category != "unknown" for p in params)
    elif result == "complex":
        assert any(p.category == "dynamic" for p in params)
```

### 属性 4: 时间戳单调递增（需求 2.3）

**类型**: Invariant

**描述**: 同一操作序列中捕获的请求，按捕获顺序排列时时间戳应单调递增。

```python
@given(requests=st.lists(captured_request_strategy(), min_size=2))
def test_timestamp_monotonic(requests):
    sorted_requests = sorted(requests, key=lambda r: r.timestamp)
    for i in range(1, len(sorted_requests)):
        assert sorted_requests[i].timestamp >= sorted_requests[i-1].timestamp
```

### 属性 5: 批量采集失败阈值触发（需求 5.3）

**类型**: Invariant

**描述**: 当连续失败次数达到配置阈值时，采集任务状态必须变为 paused。

```python
@given(threshold=st.integers(min_value=1, max_value=100),
       results=st.lists(st.booleans(), min_size=1))
def test_failure_threshold_triggers_pause(threshold, results):
    crawler = BatchCrawler(config=CrawlConfig(failure_threshold=threshold))
    for success in results:
        crawler.record_result(success)
    
    if crawler.stats.consecutive_failures >= threshold:
        assert crawler.status == "paused"
```

### 属性 6: 汇总报告数据一致性（需求 7.1）

**类型**: Invariant

**描述**: 汇总报告中的总接口数量等于可复现接口数量加复杂接口数量加未知接口数量。

```python
@given(analyses=st.lists(api_analysis_result_strategy(), min_size=1))
def test_report_counts_consistency(analyses):
    report = generate_summary_report(analyses)
    assert report.total_count == report.reproducible_count + report.complex_count + report.unknown_count
    assert report.total_count == len(analyses)
```

### 属性 7: 采集数据存储 Round-Trip（需求 5.2）

**类型**: Round-Trip

**描述**: 采集到的数据以 JSON 格式写入后再读取，应得到等价数据。

```python
@given(data=crawl_data_strategy())
def test_crawl_data_roundtrip(data):
    json_str = json.dumps(data.to_dict())
    restored = CrawlData.from_dict(json.loads(json_str))
    assert restored == data
```

## Skill 文件设计

skill 指令文件 (`skill/ai-api-capture.md`) 结构：

```markdown
---
name: AI API Capture
description: AI 驱动的移动端接口抓取与代码生成
version: 1.0.0
keywords: [api, capture, mobile, mitmproxy, crawl, reverse-engineering]
dependencies:
  tools: [mitmproxy, mobile-mcp]
  python: [requests, httpx, aiohttp, mitmproxy]
---

# AI API Capture Skill

## 触发条件
当用户提到"抓取接口"、"App 接口"、"移动端抓包"等关键词时激活。

## 输入参数
- 目标 App 包名
- 设备标识
- 操作意图描述
- 采集目标（可选）

## 执行流程
### 阶段 1: 操控与捕获
...
### 阶段 2: 分析与分类
...
### 阶段 3: 分路径采集
...

## 暂停点
- 接口分类结果确认
- 复杂接口处理策略确认
```

## 关键设计决策

1. **mitmproxy 使用 Python API 模式而非命令行模式**: 便于与系统深度集成，实时获取流量数据，支持动态过滤规则。

2. **操作序列由 AI 生成而非预定义**: 利用 LLM 的理解能力，根据用户意图和当前页面状态动态生成操作步骤，适应不同 App 的 UI 结构。

3. **验证失败自动降级为复杂接口**: 保守策略，避免生成无法工作的代码。用户可以手动覆盖分类结果。

4. **SQLite 用于索引，JSON 用于数据存储**: JSON 保持数据的完整性和可读性，SQLite 提供快速查询和关联能力。

5. **异步架构**: 设备操控、流量捕获和数据采集都是 IO 密集型操作，使用 asyncio 提高并发效率。
