# Implementation Plan: AI API Capture 通用接口抓取与分析系统

## Overview

基于通用方案重构现有代码，将系统从绑定特定 App 的实现转变为通用的移动端接口抓取与分析系统。按模块依赖顺序实施：先更新数据模型，再实现各功能模块，最后集成和测试。

## Tasks

- [ ] 1. 更新数据模型和基础设施
  - [x] 1.1 重写 `src/models.py` 数据模型
    - 实现 CaptureTarget、FilterRules、CapturedRequest、ParameterInfo、APIType、APIAnalysisResult、DataLink、AnalysisReport 等 dataclass
    - 移除旧版绑定特定 App 的模型定义
    - 添加 APIType 枚举（LIST, PAGINATION, DETAIL, MEDIA, CONFIG, AUX）
    - 添加 RequirementStatus、ConnectionResult、CertResult、ProxyResult、ProcessResult 等结果类型
    - _Requirements: 5.2, 5.3, 5.4, 6.2_

  - [x] 1.2 更新 `src/storage.py` 存储模块
    - 实现 CapturedRequest 的 JSON 序列化/反序列化
    - 支持增量写入（每个请求独立 JSON 文件）
    - 实现流量数据的批量读取接口
    - 确保存储路径为 `output/captures/` 和 `output/analysis/samples/`
    - _Requirements: 3.6_

  - [ ]* 1.3 编写数据模型属性测试 - Property 1: 请求存储 Round-Trip
    - **Property 1: 请求存储 Round-Trip**
    - 对任意有效 CapturedRequest 对象，序列化为 JSON 再反序列化应产生等价对象
    - **Validates: Requirements 3.6**

  - [ ]* 1.4 编写数据模型单元测试
    - 测试各 dataclass 的创建和字段验证
    - 测试 APIType 枚举值
    - 测试 JSON 序列化/反序列化的边界情况
    - _Requirements: 3.2, 3.3_

- [ ] 2. 实现 Requirement_Collector 需求收集模块
  - [ ] 2.1 创建 `src/requirement_collector.py`
    - 实现 RequirementCollector 类
    - 实现 analyze_input() 方法：解析用户输入提取 app_name、target_data、operation_pages
    - 实现 get_missing_fields() 方法：返回缺失的必填字段列表
    - 实现 generate_summary() 方法：生成操作计划摘要
    - 实现 is_complete() 方法：判断目标信息是否完整
    - 当用户一次性提供完整信息时跳过逐步引导
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.2 编写需求收集属性测试 - Property 7: 缺失字段检测
    - **Property 7: 缺失字段检测**
    - 对任意 CaptureTarget，若必填字段为空/None，get_missing_fields() 必须返回包含这些字段名的非空列表
    - **Validates: Requirements 1.2, 1.3, 1.4**

  - [ ]* 2.3 编写需求收集单元测试
    - 测试完整输入直接跳过引导
    - 测试缺少 app_name 时的引导
    - 测试缺少 target_data 时的引导
    - 测试缺少 operation_pages 时的引导
    - 测试 generate_summary 输出格式
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 3. 实现 Environment_Manager 环境管理模块
  - [ ] 3.1 创建 `src/environment_manager.py`
    - 实现 EnvironmentManager 类
    - 实现 check_device() 方法：通过 adb 验证设备连接
    - 实现 install_certificate() 方法：使用 tmpfs overlay 安装 CA 证书
    - 实现 set_proxy() 方法：通过 adb 设置 HTTP 代理
    - 实现 start_mitmdump() 方法：启动 mitmdump 子进程并加载 addon
    - 实现 cleanup() 方法：清理代理设置和证书
    - 每个步骤失败时返回具体错误信息和建议
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 3.2 编写环境管理单元测试
    - 使用 mock subprocess 测试 adb 命令执行
    - 测试设备连接成功/失败场景
    - 测试证书安装成功/失败场景
    - 测试代理设置成功/失败场景
    - 测试 mitmdump 启动成功/失败场景
    - _Requirements: 2.1, 2.6, 2.7, 2.8_

- [ ] 4. 更新流量拦截模块
  - [ ] 4.1 更新 `src/traffic_interceptor.py`
    - 重构 TrafficInterceptor 类，使用新的 FilterRules 和 CapturedRequest 模型
    - 实现 start_recording() / stop_recording() 控制方法
    - 实现 get_captured_requests() 和 get_stats() 查询方法
    - 实现 4 层过滤逻辑：静态资源过滤、域名黑名单、路径黑名单、API 白名单
    - 支持用户自定义域名白名单/黑名单
    - 为每条记录附加捕获时间戳
    - 标记 HTTPS 解密失败的请求（is_decrypted=False）
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 4.2 更新 `addons/capture_addon.py` mitmproxy addon
    - 重构 CaptureAddon 类，使用新的 FilterRules 模型
    - 实现 response() 回调中的 4 层过滤
    - 实现实时写入 JSON 文件（每个请求独立文件）
    - 支持通过命令行参数传入 storage_path 和过滤规则
    - _Requirements: 3.1, 3.6, 4.1, 4.2, 4.3, 4.4_

  - [ ]* 4.3 编写过滤规则属性测试 - Property 2: 过滤规则不变量
    - **Property 2: 过滤规则不变量**
    - 对任意请求列表和 FilterRules 配置，通过过滤的请求必须满足：Content-Type 不在黑名单、域名不在黑名单、路径不在黑名单、且匹配 API 白名单
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ]* 4.4 编写时间戳属性测试 - Property 4: 时间戳单调递增
    - **Property 4: 时间戳单调递增**
    - 对单次录制会话中的请求序列，按捕获顺序排列时时间戳必须单调非递减
    - **Validates: Requirements 3.3**

  - [ ]* 4.5 编写流量拦截单元测试
    - 测试具体域名的黑名单过滤效果
    - 测试具体路径的黑名单过滤效果
    - 测试 Content-Type 过滤效果
    - 测试 API 白名单匹配逻辑
    - 测试用户自定义过滤规则
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 5. Checkpoint - 确保基础模块测试通过
  - 确保所有测试通过，ask the user if questions arise.

- [ ] 6. 通用化 API_Analyzer 接口分析模块
  - [ ] 6.1 重构 `src/api_analyzer.py`
    - 重写 APIAnalyzer 类，移除所有特定 App 绑定的逻辑
    - 实现 classify_api_type() 方法：基于通用响应结构模式识别接口类型
    - 实现 LIST 识别：响应含数组，元素为结构化对象（含 id + 名称类字段）
    - 实现 PAGINATION 识别：请求含分页参数 + 响应含分页标识
    - 实现 DETAIL 识别：请求含 id 参数 + 响应字段数 > 列表元素字段数 1.5 倍
    - 实现 MEDIA 识别：响应含媒体 URL 模式
    - 实现 classify_parameters() 方法：将参数分为 static/session/dynamic 三类
    - 实现 detect_data_links() 方法：自动识别接口间的数据链路关系
    - 实现 analyze_all() 方法：结合用户目标数据描述进行综合分析
    - 标注与用户目标最相关的接口
    - 未找到匹配目标时明确说明并列出所有已识别接口
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.2 编写接口类型识别属性测试 - Property 6: 接口类型识别一致性
    - **Property 6: 接口类型识别一致性**
    - 被分类为 LIST 的请求，响应体必须含结构化对象数组；被分类为 PAGINATION 的请求，必须含分页参数
    - **Validates: Requirements 5.2**

  - [ ]* 6.3 编写参数分类属性测试 - Property 3: 参数分类一致性
    - **Property 3: 参数分类一致性**
    - 对任意 ParameterInfo，category 必须为 static/session/dynamic 之一，且分类是确定性的
    - **Validates: Requirements 5.3**

  - [ ]* 6.4 编写数据链路属性测试 - Property 9: 数据链路检测
    - **Property 9: 数据链路检测**
    - 当 LIST 接口响应含 ID 值出现在 DETAIL/MEDIA 接口请求参数中时，detect_data_links 必须识别该关系
    - **Validates: Requirements 5.4**

  - [ ]* 6.5 编写接口分析单元测试
    - 测试具体 JSON 响应结构的分类结果
    - 测试参数分类的具体案例
    - 测试数据链路检测的具体案例
    - 测试目标匹配逻辑
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 7. 更新 Report_Generator 报告生成模块
  - [ ] 7.1 重构 `src/report_generator.py`
    - 重写 ReportGenerator 类，使用新的 AnalysisReport 模型
    - 实现 render_markdown() 方法：生成完整的 Markdown 报告
    - 报告包含：抓取目标摘要、数据链路图、接口概览表、每个接口详情
    - 实现 generate_curl() 方法：为每个接口生成可执行的 cURL 命令
    - 实现 save_samples() 方法：保存请求/响应 JSON 到 samples/ 目录
    - 报告中以相对路径引用 samples/ 文件
    - 包含签名机制说明
    - 确保报告格式适合 AI 解析（清晰标题层级、表格、代码块）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 7.2 编写 cURL 命令属性测试 - Property 8: cURL 命令正确性
    - **Property 8: cURL 命令正确性**
    - 对任意 CapturedRequest，生成的 cURL 命令必须包含正确的 HTTP 方法、完整 URL 和所有非平凡请求头
    - **Validates: Requirements 6.3**

  - [ ]* 7.3 编写报告数据属性测试 - Property 5: 报告数据一致性
    - **Property 5: 报告数据一致性**
    - 对任意 AnalysisReport，各类型接口数量之和必须等于 total_analyzed
    - **Validates: Requirements 6.2**

  - [ ]* 7.4 编写报告生成单元测试
    - 测试报告格式和内容完整性
    - 测试 cURL 命令生成的具体案例
    - 测试 samples 文件保存逻辑
    - 测试报告中的相对路径引用
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7_

- [ ] 8. Checkpoint - 确保分析和报告模块测试通过
  - 确保所有测试通过，ask the user if questions arise.

- [ ] 9. 更新主协调器和清理废弃模块
  - [ ] 9.1 删除废弃模块
    - 删除 `src/device_controller.py`（功能已由 environment_manager 替代）
    - 删除 `src/code_generator.py`（不再生成代码，改为生成报告）
    - 删除 `src/batch_crawler.py`（不再需要批量采集）
    - 删除 `src/replay_controller.py`（不再需要回放控制）
    - 删除对应的测试文件：test_device_controller.py、test_code_generator.py、test_batch_crawler.py、test_replay_controller.py
    - 删除 `templates/code_template.py.jinja`（不再需要代码模板）
    - _Requirements: 7.1_

  - [ ] 9.2 重构 `src/capture_system.py` 主协调器
    - 重写 CaptureSystem 类，协调四阶段流程
    - 集成 RequirementCollector：需求收集与引导
    - 集成 EnvironmentManager：环境准备
    - 集成 TrafficInterceptor：流量录制控制
    - 集成 APIAnalyzer + ReportGenerator：分析与报告生成
    - 实现阶段间的状态流转和暂停点
    - 实现 stop_recording() 触发分析流程
    - 向用户展示报告摘要和文件保存路径
    - _Requirements: 3.4, 6.6, 7.2, 7.3, 7.4_

  - [ ] 9.3 更新 `src/__init__.py` 导出
    - 更新模块导出，移除废弃模块引用
    - 添加新模块（requirement_collector、environment_manager）的导出
    - _Requirements: 7.1_

- [ ] 10. 集成测试
  - [ ]* 10.1 编写端到端集成测试
    - 测试从流量 JSON 文件到分析报告的完整流程
    - 使用 mock flow 测试 mitmproxy addon 的过滤和存储逻辑
    - 使用 mock subprocess 测试环境管理的 adb/mitmdump 命令执行
    - 测试主协调器的阶段流转逻辑
    - _Requirements: 3.4, 5.1, 6.1, 6.6_

  - [ ]* 10.2 清理旧测试文件并更新测试配置
    - 更新 test_integration.py 为新的集成测试
    - 确保 pyproject.toml 中的测试配置正确
    - 确保所有测试可以通过 `pytest` 运行
    - _Requirements: 7.5_

- [ ] 11. Final checkpoint - 确保所有测试通过
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (9 properties from design)
- Unit tests validate specific examples and edge cases
- skill 文件（`skill/ai-api-capture.md`）已更新为通用方案，无需额外任务
- 实现语言为 Python 3.11+，使用 Hypothesis 进行属性测试
- 废弃模块在任务 9.1 中统一删除，避免中间状态的导入错误
