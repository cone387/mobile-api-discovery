# 实现任务

## 1. 项目初始化与基础设施

- [x] 1.1 创建项目结构，初始化 pyproject.toml，配置依赖（requests, httpx, aiohttp, mitmproxy, hypothesis）
- [x] 1.2 定义数据模型（models.py）：CapturedRequest, OperationStep, OperationSequence, APIAnalysisResult, ParameterInfo, GeneratedCode, CrawlTask, CrawlConfig, CrawlStats
- [x] 1.3 实现数据存储层（storage.py）：JSON 文件读写、SQLite 索引管理
- [x] 1.4 编写数据模型的序列化/反序列化单元测试和属性测试（round-trip）

## 2. Traffic_Interceptor 模块（流量拦截）

- [x] 2.1 实现 mitmproxy addon 脚本（addons/capture_addon.py）：请求/响应捕获、字段记录、步骤 ID 关联
- [x] 2.2 实现 TrafficInterceptor 类：启动/停止 mitmproxy、配置代理、管理 addon 生命周期
- [x] 2.3 实现过滤规则引擎：按域名、路径、Content-Type 过滤请求
- [x] 2.4 实现 HTTPS 解密失败检测和标记逻辑
- [x] 2.5 编写过滤规则的属性测试（过滤后结果满足规则、长度不超过原始列表）

## 3. Device_Controller 模块（设备操控）

- [x] 3.1 实现 MCP 客户端连接逻辑：设备发现、连接、断开
- [x] 3.2 实现操作步骤执行器：click, swipe, input, navigate, wait 等操作类型
- [x] 3.3 实现操作序列执行引擎：顺序执行步骤、容错处理（失败继续）、步骤状态记录
- [x] 3.4 实现与 Traffic_Interceptor 的协调：执行步骤时同步更新当前步骤 ID
- [x] 3.5 编写操作序列执行的单元测试（模拟 MCP 调用）

## 4. API_Analyzer 模块（接口分析）

- [x] 4.1 实现参数提取逻辑：从 URL query、headers、body、cookies 中提取所有参数
- [x] 4.2 实现参数分类器：基于规则和模式匹配将参数分为 static/session/dynamic/unknown
- [x] 4.3 实现可复现性判定逻辑：根据参数分类结果判定接口类型
- [x] 4.4 实现接口用途语义分析：调用 LLM 分析接口用途并生成分析报告
- [x] 4.5 编写参数分类和可复现性判定的属性测试（分类一致性）

## 5. Code_Generator 模块（代码生成）

- [x] 5.1 设计并实现代码生成模板（templates/code_template.py.jinja）
- [x] 5.2 实现 CodeGenerator 类：从分析结果和原始请求生成 Python requests 代码
- [x] 5.3 实现会话参数提取和可配置变量生成逻辑
- [x] 5.4 实现代码验证执行器：运行生成的代码并比对响应结构
- [x] 5.5 实现验证失败时的降级逻辑（重新标记为复杂接口）

## 6. Batch_Crawler 模块（批量采集）

- [x] 6.1 实现异步批量请求执行器：并发控制（信号量）、请求间隔
- [x] 6.2 实现采集数据 JSON 存储：写入格式包含请求参数、响应数据、时间戳
- [x] 6.3 实现成功率监控和自动暂停逻辑：连续失败计数、阈值触发
- [x] 6.4 实现认证失败检测和任务暂停通知
- [x] 6.5 编写失败阈值触发的属性测试和数据存储 round-trip 测试

## 7. Replay_Controller 模块（复杂接口回放采集）

- [x] 7.1 实现操作序列精简逻辑：从完整序列中提取触发目标接口的最小子集
- [x] 7.2 实现回放执行引擎：按轮次执行操作序列、配置等待间隔
- [x] 7.3 实现目标接口捕获验证：确认每轮执行后是否成功捕获目标请求
- [x] 7.4 实现重试和失败标记逻辑

## 8. 报告生成与主协调器

- [x] 8.1 实现汇总报告生成器（report_generator.py）：统计数据、Markdown 格式输出
- [x] 8.2 实现接口详情查询：展示分析报告、生成代码和采集状态
- [x] 8.3 实现 CaptureSystem 主协调器：串联三阶段流程、管理模块生命周期
- [x] 8.4 编写报告数据一致性的属性测试（总数 = 各分类之和）

## 9. 通用 Skill 封装

- [x] 9.1 编写 skill 指令文件（skill/ai-api-capture.md）：元数据、触发条件、输入参数、执行流程
- [x] 9.2 定义 skill 暂停点和用户决策交互逻辑
- [x] 9.3 编写 skill 依赖声明和环境配置说明
- [x] 9.4 编写 README.md：项目说明、安装步骤、使用指南

## 10. 集成测试与端到端验证

- [x] 10.1 编写模块间集成测试：Device_Controller + Traffic_Interceptor 协调测试
- [x] 10.2 编写端到端流程测试：从操控到分析到代码生成的完整流程（使用 mock）
- [x] 10.3 验证 skill 文件格式和内容完整性
