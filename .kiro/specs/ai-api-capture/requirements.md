# 需求文档

## 简介

AI 驱动的移动端接口抓取与代码生成系统。该系统通过 AI 操控真实移动设备触发 App 行为，利用 mitmproxy 抓取网络请求，再由 AI 分析接口特征并自动分类：可直接复现的接口生成 Python requests 代码进行批量抓取；复杂接口（含签名/加密）则继续通过客户端触发配合代理拦截保存数据。核心目标是以最低逆向成本，快速将 App 接口转化为可用数据源。

## 术语表

- **Capture_System**: 本系统的整体名称，负责协调 AI 操控、流量抓取、接口分析和代码生成的完整流程
- **Device_Controller**: 通过 MCP（Mobile Control Protocol）操控移动设备的模块，负责模拟用户在 App 中的真实操作行为
- **Traffic_Interceptor**: 基于 mitmproxy 的流量拦截模块，负责捕获移动设备发出的所有 HTTP/HTTPS 请求与响应
- **API_Analyzer**: AI 分析模块，负责对抓取到的请求进行分类、参数依赖分析和可复现性判断
- **Code_Generator**: 代码生成模块，负责为可复现接口生成独立的 Python requests 调用代码
- **Batch_Crawler**: 批量抓取执行器，运行 Code_Generator 生成的代码进行脱离设备的数据采集
- **Replay_Controller**: 回放控制器，对无法直接复现的复杂接口，继续通过 Device_Controller 操作 App 触发请求并由 Traffic_Interceptor 拦截保存
- **可复现接口**: 不依赖动态签名、加密参数或设备状态，可通过标准 HTTP 请求库独立调用的接口
- **复杂接口**: 包含动态签名、加密参数、设备指纹或时效性 Token 等，无法脱离 App 环境独立调用的接口
- **操作序列**: 一组有序的设备操作指令（点击、滑动、输入等），用于触发特定的 App 行为和接口请求

## 需求

### 需求 1：设备操控与 App 行为触发

**用户故事：** 作为数据工程师，我希望通过 AI 自动操控移动设备执行 App 操作，以便触发真实的接口请求。

#### 验收标准

1. WHEN 用户指定目标 App 和操作意图时，THE Device_Controller SHALL 通过 MCP 连接到目标移动设备并启动指定 App
2. WHEN App 启动完成后，THE Device_Controller SHALL 根据 AI 生成的操作序列执行页面导航、按钮点击、列表滑动和详情进入等操作
3. WHILE Device_Controller 执行操作序列期间，THE Traffic_Interceptor SHALL 持续捕获设备发出的所有 HTTP 和 HTTPS 请求及其完整响应
4. WHEN 操作序列执行完毕时，THE Traffic_Interceptor SHALL 将所有捕获的请求-响应对以结构化格式存储到本地文件系统
5. IF Device_Controller 无法连接到目标设备，THEN THE Capture_System SHALL 返回包含设备标识和连接失败原因的错误信息
6. IF 操作序列中某一步骤执行失败，THEN THE Device_Controller SHALL 记录失败步骤信息并尝试继续执行后续步骤

### 需求 2：流量捕获与存储

**用户故事：** 作为数据工程师，我希望系统能完整捕获 App 的网络流量，以便后续进行接口分析。

#### 验收标准

1. WHEN Traffic_Interceptor 启动时，THE Traffic_Interceptor SHALL 配置 mitmproxy 作为设备的网络代理并开始拦截流量
2. THE Traffic_Interceptor SHALL 为每个捕获的请求记录以下字段：请求方法、URL、请求头、请求体、响应状态码、响应头和响应体
3. WHEN 捕获到请求时，THE Traffic_Interceptor SHALL 为每条记录附加时间戳和关联的操作步骤标识
4. IF 设备未正确配置代理证书导致 HTTPS 解密失败，THEN THE Traffic_Interceptor SHALL 记录该请求的 URL 并标记为"未解密"
5. WHEN 用户指定过滤规则时，THE Traffic_Interceptor SHALL 仅保存符合规则的请求（按域名、路径或内容类型过滤）

### 需求 3：接口智能分析与分类

**用户故事：** 作为数据工程师，我希望 AI 能自动分析抓取到的接口并判断其可复现性，以便我知道哪些接口可以用代码直接调用。

#### 验收标准

1. WHEN Traffic_Interceptor 完成一批流量捕获后，THE API_Analyzer SHALL 对所有捕获的请求进行语义分析，识别接口用途类别（如 feed 流、用户信息、评论、搜索等）
2. WHEN 分析单个接口时，THE API_Analyzer SHALL 识别该接口依赖的所有参数，并将参数分为静态参数（固定值）、会话参数（Token/Cookie）和动态参数（签名/加密/时间戳）三类
3. WHEN 参数分析完成后，THE API_Analyzer SHALL 根据以下规则判定接口可复现性：仅包含静态参数和会话参数的接口标记为"可复现"；包含动态签名或加密参数的接口标记为"复杂接口"
4. THE API_Analyzer SHALL 为每个分析完成的接口生成分析报告，包含：接口用途、参数列表及分类、可复现性判定结果和判定依据
5. IF API_Analyzer 无法确定某个参数的类型，THEN THE API_Analyzer SHALL 将该参数标记为"待确认"并在报告中说明原因

### 需求 4：可复现接口的代码生成

**用户故事：** 作为数据工程师，我希望系统能为可复现的接口自动生成 Python 请求代码，以便我可以脱离手机进行批量数据采集。

#### 验收标准

1. WHEN API_Analyzer 将接口标记为"可复现"时，THE Code_Generator SHALL 为该接口生成可独立运行的 Python requests 代码
2. THE Code_Generator SHALL 在生成的代码中包含：完整的请求头设置、参数构造、错误处理和响应解析逻辑
3. WHEN 接口依赖会话参数时，THE Code_Generator SHALL 在生成的代码中将会话参数提取为可配置变量，并添加注释说明获取方式
4. WHEN 代码生成完成后，THE Code_Generator SHALL 使用捕获的原始请求参数执行一次验证请求，确认生成的代码能获得与原始请求一致的响应结构
5. IF 验证请求失败，THEN THE Code_Generator SHALL 将该接口重新标记为"复杂接口"并记录失败原因

### 需求 5：批量数据采集执行

**用户故事：** 作为数据工程师，我希望能使用生成的代码进行批量数据采集，以便高效获取大量数据。

#### 验收标准

1. WHEN 用户启动批量采集任务时，THE Batch_Crawler SHALL 加载指定接口的生成代码并按用户配置的并发数和请求间隔执行批量请求
2. THE Batch_Crawler SHALL 将采集到的数据以 JSON 格式存储，每条记录包含请求参数、响应数据和采集时间戳
3. WHILE 批量采集执行期间，THE Batch_Crawler SHALL 监控请求成功率，当连续失败次数超过用户配置的阈值时暂停采集并通知用户
4. IF 采集过程中检测到接口返回认证失败响应，THEN THE Batch_Crawler SHALL 暂停当前任务并提示用户更新会话参数

### 需求 6：复杂接口的客户端触发采集

**用户故事：** 作为数据工程师，我希望对于无法直接复现的复杂接口，系统能继续通过操控 App 来采集数据，以便不遗漏任何需要的数据。

#### 验收标准

1. WHEN API_Analyzer 将接口标记为"复杂接口"时，THE Replay_Controller SHALL 生成针对该接口的操作序列，定义触发该接口所需的 App 操作步骤
2. WHEN 用户启动复杂接口采集任务时，THE Replay_Controller SHALL 通过 Device_Controller 按操作序列重复执行 App 操作，同时由 Traffic_Interceptor 拦截并保存目标接口的响应数据
3. THE Replay_Controller SHALL 支持用户配置采集轮次和每轮之间的等待间隔
4. IF 操作序列执行后未能捕获到目标接口的请求，THEN THE Replay_Controller SHALL 重试一次，若仍失败则标记该接口为"采集失败"并记录原因

### 需求 7：分析报告与结果输出

**用户故事：** 作为数据工程师，我希望系统能生成完整的分析报告，以便我了解所有接口的状态和采集结果。

#### 验收标准

1. WHEN 一次完整的抓取-分析流程结束后，THE Capture_System SHALL 生成汇总报告，包含：总接口数量、可复现接口数量、复杂接口数量和各接口的分析摘要
2. THE Capture_System SHALL 将报告以 Markdown 格式输出到用户指定的路径
3. WHEN 用户请求查看特定接口详情时，THE Capture_System SHALL 展示该接口的完整分析报告、生成的代码（如有）和采集状态

### 需求 8：通用 Skill 封装与集成

**用户故事：** 作为开发者，我希望将整个流程封装为通用的 AI skill，以便在任何支持 skill 规范的 AI 开发环境中（包括但不限于 Kiro）通过自然语言指令快速启动和执行接口抓取任务。

#### 验收标准

1. THE Capture_System SHALL 提供符合通用 skill 规范的配置文件，包含 skill 元数据（名称、描述、版本、关键词）、触发条件、输入参数定义和执行流程描述
2. THE Capture_System SHALL 将 skill 配置以 Markdown 格式的指令文件呈现，定义 AI 代理在执行该 skill 时应遵循的步骤、约束和决策逻辑
3. WHEN 用户在 AI 开发环境中激活该 skill 时，THE Capture_System SHALL 通过 skill 指令引导 AI 代理收集目标 App 信息、设备连接参数和采集目标
4. THE Capture_System SHALL 将完整的三阶段流程（操控触发、分析分类、分路径采集）封装为 skill 指令中的执行步骤，支持逐步推进或一键执行全流程
5. IF skill 执行过程中需要用户决策（如确认接口分类结果），THEN THE Capture_System SHALL 在 skill 指令中定义暂停点，要求 AI 代理向用户展示决策所需的上下文信息并等待确认
6. THE Capture_System SHALL 提供 skill 的依赖声明，列出所需的外部工具（mitmproxy、MCP 服务器）和 Python 包，以便在不同环境中快速配置
