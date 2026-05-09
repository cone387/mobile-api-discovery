# 需求文档

## 简介

AI 辅助的通用移动端接口抓取与分析系统。该系统适用于任意 App 的接口逆向分析场景。AI 首先引导用户明确抓取目标（什么 App、什么数据、哪些页面），然后自动完成 mitmproxy 代理环境配置，通知用户手动操作 App，最后分析录制的流量，自动过滤无关请求，基于通用的响应结构模式识别业务接口类型，并生成结构化的接口分析报告供其他 AI 或开发者使用。

核心设计原则：
- **通用性**：不绑定任何特定 App 或特定字段名，基于响应结构的通用模式进行接口识别
- **用户驱动**：用户提供目标数据描述来指导分析重点
- **AI 引导**：当用户需求不清晰时，AI 主动引导用户理清抓取目标

## 术语表

- **Capture_System**: 本系统的整体名称，负责协调需求收集、环境准备、流量抓取、接口分析和报告生成的完整流程
- **Requirement_Collector**: 需求收集模块，负责引导用户明确抓取目标，包括目标 App、期望数据、操作页面等
- **Environment_Manager**: 环境管理模块，负责启动 mitmproxy、配置设备代理、安装 CA 证书等抓包环境准备工作
- **Traffic_Interceptor**: 基于 mitmproxy 的流量拦截模块，负责在用户操作 App 期间捕获设备发出的所有 HTTP/HTTPS 请求与响应
- **API_Analyzer**: 接口分析模块，负责对抓取到的请求进行过滤、分类、参数依赖分析和接口用途识别
- **Report_Generator**: 报告生成模块，负责将分析结果输出为结构化的 Markdown 报告和请求样本文件，供其他 AI 使用
- **列表接口**: 响应中包含数组数据的 API，数组元素为结构化对象（通常含 id、名称、图片等字段），不限定具体字段名
- **分页接口**: 支持翻页加载的 API，请求中包含 page/pageFlag/offset/cursor 等分页参数，响应中包含 hasMore/totalPage/nextCursor 等分页标识
- **详情接口**: 返回单条记录详细信息的 API，请求中包含 id 参数，响应中包含比列表更丰富的字段
- **媒体接口**: 响应中包含媒体资源 URL（mp4、m3u8、audio 等格式）的 API
- **业务接口**: 与 App 核心功能相关的 API，区别于 SDK 上报、广告、推送等第三方接口
- **操作通知**: AI 完成环境准备后向用户发出的通知，告知用户可以开始在手机上操作 App
- **目标数据描述**: 用户提供的期望抓取的数据说明，用于指导 AI 在分析阶段重点关注哪些接口

## 需求

### 需求 1：需求收集与引导

**用户故事：** 作为数据工程师，我希望 AI 能引导我明确抓取目标和操作计划，以便后续的抓包和分析能精准聚焦在我关心的接口上。

#### 验收标准

1. WHEN 用户激活接口抓取任务时，THE Requirement_Collector SHALL 向用户询问目标 App 名称、期望获取的数据类型和需要操作的页面
2. WHEN 用户的需求描述缺少目标 App 名称时，THE Requirement_Collector SHALL 主动询问用户要抓取哪个 App 的接口
3. WHEN 用户的需求描述缺少期望数据类型时，THE Requirement_Collector SHALL 提供常见数据类型选项引导用户选择（如：列表数据、详情数据、搜索结果、媒体播放地址等）
4. WHEN 用户的需求描述缺少操作页面说明时，THE Requirement_Collector SHALL 建议用户说明需要操作哪些页面（如：首页列表、搜索页、详情页、播放页等）
5. WHEN 用户提供了完整的目标描述后，THE Requirement_Collector SHALL 生成操作计划摘要并请用户确认
6. IF 用户一次性提供了完整的目标信息（App 名称、数据类型、操作页面），THEN THE Requirement_Collector SHALL 跳过逐步引导，直接确认并进入环境准备阶段

### 需求 2：抓包环境准备

**用户故事：** 作为数据工程师，我希望 AI 能自动完成抓包环境的配置和启动，以便我可以直接开始操作 App 而无需手动配置代理。

#### 验收标准

1. WHEN 用户指定目标设备标识符时，THE Environment_Manager SHALL 通过 adb 验证设备连接状态并返回连接结果
2. WHEN 设备连接确认后，THE Environment_Manager SHALL 在设备上安装 mitmproxy 的 CA 证书到系统证书目录
3. WHEN 证书安装完成后，THE Environment_Manager SHALL 通过 adb 将设备的 HTTP 代理设置为运行 mitmproxy 的主机地址和端口
4. WHEN 代理设置完成后，THE Environment_Manager SHALL 启动 mitmdump 进程并加载流量捕获脚本
5. WHEN mitmdump 进程启动成功后，THE Environment_Manager SHALL 向用户发送操作通知，包含环境配置结果和基于需求收集阶段确定的操作指引
6. IF 设备连接失败，THEN THE Environment_Manager SHALL 返回包含设备标识和连接失败原因的错误信息
7. IF CA 证书安装失败，THEN THE Environment_Manager SHALL 返回证书安装失败的具体原因并提供手动安装指引
8. IF mitmdump 启动失败，THEN THE Environment_Manager SHALL 返回启动失败原因并建议检查端口占用情况

### 需求 3：用户操作等待与流量录制

**用户故事：** 作为数据工程师，我希望在环境准备好后自己操作 App，系统在后台持续录制流量，以便我能按自己的节奏触发需要分析的接口。

#### 验收标准

1. WHILE 用户在手机上操作 App 期间，THE Traffic_Interceptor SHALL 持续捕获设备发出的所有 HTTP 和 HTTPS 请求及其完整响应
2. THE Traffic_Interceptor SHALL 为每个捕获的请求记录以下字段：请求方法、URL、请求头、请求体、响应状态码、响应头和响应体
3. WHEN 捕获到请求时，THE Traffic_Interceptor SHALL 为每条记录附加捕获时间戳
4. WHEN 用户告知 AI 操作已完成时，THE Capture_System SHALL 停止流量录制并进入分析阶段
5. IF 设备未正确配置代理证书导致 HTTPS 解密失败，THEN THE Traffic_Interceptor SHALL 记录该请求的 URL 并标记为"未解密"
6. WHILE 流量录制进行期间，THE Traffic_Interceptor SHALL 将捕获的请求-响应对实时写入本地 JSON 文件

### 需求 4：流量过滤

**用户故事：** 作为数据工程师，我希望系统能自动过滤掉无关的第三方 SDK 流量和静态资源请求，以便分析阶段只处理真正的业务接口。

#### 验收标准

1. WHEN 捕获到请求时，THE Traffic_Interceptor SHALL 根据响应 Content-Type 过滤掉静态资源请求（image、font、video、audio、css、javascript 类型）
2. WHEN 捕获到请求时，THE Traffic_Interceptor SHALL 根据域名黑名单过滤掉第三方 SDK 请求（数据上报、崩溃上报、广告、推送、性能监控、设备指纹等通用 SDK 域名）
3. WHEN 捕获到请求时，THE Traffic_Interceptor SHALL 根据路径黑名单过滤掉已知的非业务路径（SDK 初始化、埋点上报等通用路径模式）
4. THE Traffic_Interceptor SHALL 仅保存响应 Content-Type 包含 json 的请求，或 URL 路径匹配已知 API 模式（含 /api/、/v1/、/v2/、/v3/、/portal/、/gateway/ 等）的请求
5. WHEN 用户指定额外的过滤规则时，THE Traffic_Interceptor SHALL 将用户指定的域名加入白名单或黑名单

### 需求 5：接口智能分析与分类

**用户故事：** 作为数据工程师，我希望 AI 能基于通用的响应结构模式自动识别接口类型，以便我快速了解 App 的接口结构。

#### 验收标准

1. WHEN 用户告知操作完成后，THE API_Analyzer SHALL 读取所有捕获的请求-响应数据并结合用户的目标数据描述进行分析
2. WHEN 分析单个接口时，THE API_Analyzer SHALL 基于响应体的通用结构模式识别接口类型：响应含数组且数组元素为结构化对象（含 id 字段和至少一个名称类字段）的标记为"列表接口"；请求含分页参数（page/offset/cursor/pageFlag）且响应含分页标识（hasMore/totalPage/nextCursor/total）的标记为"分页接口"；请求含 id 参数且响应字段数量明显多于列表元素的标记为"详情接口"；响应含媒体 URL 模式（.mp4/.m3u8/.mp3 或含 video/play/stream 路径）的标记为"媒体接口"
3. WHEN 分析接口参数时，THE API_Analyzer SHALL 将请求参数分为三类：静态参数（version、platform、os、brand 等固定值）、会话参数（token、userId、session 等用户身份标识）和动态参数（sign、nonce、timestamp 等每次请求值不同的参数）
4. THE API_Analyzer SHALL 自动识别接口间的数据链路关系：从列表接口响应中提取 ID 字段，检查详情接口或媒体接口请求中是否使用了该 ID，建立接口间的调用链
5. THE API_Analyzer SHALL 结合用户的目标数据描述，在分析报告中标注哪些接口与用户目标最相关
6. IF API_Analyzer 在捕获的数据中未找到与用户目标匹配的接口，THEN THE API_Analyzer SHALL 在分析报告中明确说明未找到目标接口，并列出所有已识别的业务接口供用户判断

### 需求 6：分析报告生成

**用户故事：** 作为数据工程师，我希望系统能生成结构化的接口分析报告，以便其他 AI 或开发者可以直接参考该报告理解和调用这些接口。

#### 验收标准

1. WHEN 接口分析完成后，THE Report_Generator SHALL 生成 Markdown 格式的接口分析报告，保存到 output/analysis/ 目录
2. THE Report_Generator SHALL 在报告中包含以下内容：数据链路图（接口间的调用关系）、接口概览表（路径、用途、类型、调用次数）、每个接口的详细分析（请求参数表、响应结构概览、列表数据的第一条记录字段示例）
3. THE Report_Generator SHALL 为每个接口生成可直接执行的 cURL 命令，包含完整的请求头和参数
4. THE Report_Generator SHALL 将每个接口的完整请求和响应 JSON 保存到 output/analysis/samples/ 目录，并在报告中以相对路径引用
5. THE Report_Generator SHALL 在报告中包含签名机制说明，标注哪些接口包含动态签名参数以及签名字段的组成
6. WHEN 报告生成完成后，THE Capture_System SHALL 向用户展示报告摘要和文件保存路径
7. THE Report_Generator SHALL 确保报告格式适合其他 AI 解析，使用清晰的标题层级、表格和代码块

### 需求 7：通用 Skill 封装

**用户故事：** 作为开发者，我希望将整个流程封装为通用的 AI skill，以便在支持 skill 规范的 AI 开发环境中通过自然语言指令快速启动任意 App 的接口抓取任务。

#### 验收标准

1. THE Capture_System SHALL 提供符合通用 skill 规范的 Markdown 格式指令文件，包含 skill 元数据（名称、描述、版本、关键词）、触发条件、输入参数定义和执行流程描述
2. THE Capture_System SHALL 在 skill 指令中定义四阶段执行流程：需求收集与引导、环境准备、等待用户操作、分析与报告生成
3. WHEN 用户在 AI 开发环境中激活该 skill 时，THE Capture_System SHALL 通过 skill 指令引导 AI 代理首先收集用户的抓取目标，再收集设备连接参数
4. THE Capture_System SHALL 在 skill 指令中定义暂停点：需求确认后开始环境准备，环境准备完成后通知用户开始操作，用户操作完成后开始分析
5. THE Capture_System SHALL 提供 skill 的依赖声明，列出所需的外部工具（mitmproxy、adb）和 Python 包
6. THE Capture_System SHALL 在 skill 指令中明确说明该流程不使用 Mobile MCP 操控设备，由用户手动操作 App
