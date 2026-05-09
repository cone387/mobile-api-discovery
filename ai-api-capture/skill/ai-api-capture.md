---
name: AI API Capture
description: 通用的 AI 辅助移动端接口抓取与分析 skill。AI 引导用户明确抓取目标，自动配置抓包环境，用户手动操作 App 触发接口，AI 自动过滤、分析并生成结构化接口报告。适用于任意 App。
version: 4.0.0
keywords:
  - api
  - capture
  - mobile
  - mitmproxy
  - crawl
  - reverse-engineering
  - 抓取接口
  - App 接口
  - 移动端抓包
  - 接口采集
  - 数据采集
  - 接口分析
  - 接口逆向
dependencies:
  tools:
    - mitmproxy (>=10.1.0)
    - adb
  python:
    - mitmproxy
    - requests
---

# AI API Capture Skill

## 概述

通用的移动端接口抓取与分析方案。AI 首先引导用户明确抓取目标（什么 App、什么数据、哪些页面），然后自动配置 mitmproxy 代理环境，通知用户手动操作 App，最后分析录制的流量，基于通用的响应结构模式识别业务接口类型，生成结构化的接口分析报告。

**核心目标**：以最低逆向成本，快速将任意 App 的接口转化为可用的数据源文档，供其他 AI 或开发者参考使用。

**重要说明**：
- 本 skill 是通用方案，适用于任意 App 的接口抓取，不绑定特定 App 或特定字段名
- 本 skill 不使用 Mobile MCP 操控设备，全程由用户手动操作 App
- AI 只负责：需求引导、环境准备、流量分析

## 触发条件

当用户消息中包含以下关键词或意图时激活：

- "抓取接口"、"抓取 API"、"App 接口"
- "移动端抓包"、"接口逆向"
- "采集 App 数据"、"接口报告"
- "capture API"、"mobile API capture"
- "分析接口"、"接口分析"
- "抓包"、"逆向分析"

## 输入参数

| 参数名 | 必填 | 说明 | 示例 |
|--------|------|------|------|
| app_name | 是 | 目标 App 名称 | `某短视频App`、`某电商App` |
| device_id | 是 | 设备标识符 | `127.0.0.1:16384`、`emulator-5554` |
| target_data | 是 | 期望获取的数据描述 | "首页推荐列表、搜索结果、商品详情" |
| operation_pages | 否 | 需要操作的页面说明 | "首页、搜索页、详情页" |
| filter_domains | 否 | 关注的域名白名单 | `["api.example.com"]` |
| proxy_port | 否 | mitmproxy 监听端口（默认 8080） | `8080` |

**注意**：如果用户未提供完整参数，AI 应主动引导用户补充。

## 执行流程

### 阶段 1：需求收集与引导

AI 在开始抓包前，先确保用户的需求足够清晰：

**必须明确的信息**：
1. 目标 App 名称
2. 期望获取的数据类型（列表？详情？搜索？媒体播放？）
3. 需要操作的页面（首页？搜索页？详情页？）

**引导策略**：

- 如果用户只说"帮我抓某App的接口"，AI 应追问：
  ```
  好的，我来帮你抓取 [App名] 的接口。为了精准分析，我需要了解：
  1. 你想获取什么数据？（比如：内容列表、详情信息、搜索结果、播放地址等）
  2. 你打算操作哪些页面？（比如：首页浏览、搜索、点击详情、播放等）
  
  这样我可以在分析阶段重点关注你需要的接口。
  ```

- 如果用户一次性说清楚了（如"帮我抓某App的首页列表接口和详情接口"），直接确认并进入下一阶段。

**确认模板**：
```
收到，确认你的抓取目标：
- App：[app_name]
- 目标数据：[target_data]
- 操作计划：[operation_pages]

接下来我会配置抓包环境，请提供设备连接信息（device_id）。
```

### 阶段 2：环境准备

AI 自动完成以下步骤：

1. **检查设备连接**
   ```bash
   adb devices  # 确认设备在线
   ```

2. **安装系统级 CA 证书**（如果需要 HTTPS 解密）
   ```bash
   # 通过 adb 使用 tmpfs overlay 方式安装到系统证书目录
   adb shell "su 0 mount -t tmpfs tmpfs /system/etc/security/cacerts"
   adb shell "cp /data/local/tmp/certs/* /system/etc/security/cacerts/"
   ```

3. **设置设备代理**
   ```bash
   adb shell settings put global http_proxy <host_ip>:8080
   ```

4. **启动 mitmdump + 过滤脚本**
   ```bash
   mitmdump --set block_global=false -s addons/capture_addon.py
   ```

5. **通知用户**（基于需求收集阶段的信息定制操作指引）
   ```
   ✅ 抓包环境已就绪！
   - 代理已设置：<host_ip>:8080
   - 流量录制已开始
   
   请在手机上操作 [app_name]，完成以下操作：
   - [根据 target_data 和 operation_pages 生成的具体操作步骤]
   - 每次操作后稍等 1-2 秒让网络请求完成
   
   操作完成后请告诉我"操作完了"。
   ```

### 阶段 3：等待用户操作

**AI 在此阶段不执行任何操作**，等待用户在手机上完成操作。

用户操作期间，mitmdump 在后台持续录制流量到本地 JSON 文件。

**触发继续**：用户说"操作完了"、"完成了"、"好了"等表示操作结束的话语。

### 阶段 4：流量过滤（内置 4 层过滤）

在抓包阶段就排除无关流量，减少后续分析的数据量和 token 消耗：

**第 1 层：静态资源过滤**
- 跳过 Content-Type 为 image/、font/、video/、audio/、text/css、application/javascript 的响应

**第 2 层：第三方 SDK 域名黑名单**
```
# 数据上报/埋点
analytics.oceanengine.com, sss.umeng.com, tracking.miui.com, sc-sa.*.cn

# 崩溃上报
pro.bugly.qq.com, bugly.qq.com

# 广告
ad-union.*.cn, pbaccess.video.qq.com, amdcopen.m.taobao.com

# 推送
gepush.com, sdk-open-phone.getui.com

# 性能监控
tingyun.com, wkdcm1.tingyun.com

# DNS/CDN 探测
203.107.1.1, cbsipv4.shuzilm.cn

# 设备指纹/安全
mssdk, polaris, gecko.zijieapi.com

# 模拟器自身
report.mumu.nie.netease.com, api.mumu.nie.netease.com
```

**第 3 层：路径黑名单**
```
/sdk/app/, /reportBatchData, /upload-json, /api/v2/al,
/api/v1/attribute, /api/collection, /getMobileRedirectHost,
/initMobileApp, /track/v4
```

**第 4 层：业务 API 白名单**
- 只保留 Content-Type 含 "json" 的响应
- 或 URL 路径含 /api/、/v1/、/v2/、/v3/、/portal/、/gateway/ 等已知 API 模式

### 阶段 5：接口分析与报告生成

**通用接口识别逻辑**（基于响应结构模式，不绑定特定字段名）：

| 响应特征 | 接口类型 | 识别规则 |
|----------|----------|----------|
| 响应含数组，数组元素为结构化对象（含 id 字段 + 名称/标题类字段） | LIST（列表接口） | 数组长度 > 1，元素含 id + 至少一个 name/title/label 模式字段 |
| 请求含分页参数，响应含分页标识 | LIST + PAGINATION（分页列表） | 请求含 page/offset/cursor/pageFlag，响应含 hasMore/total/nextPage |
| 请求含 id 参数，响应字段数量明显多于列表元素 | DETAIL（详情接口） | 响应对象字段数 > 列表元素字段数的 1.5 倍 |
| 响应含媒体 URL 模式 | MEDIA（媒体接口） | URL 含 .mp4/.m3u8/.mp3 或路径含 video/play/stream/media |
| 响应含 config/settings/version 等配置字段 | CONFIG（配置接口） | - |
| 响应为简单值或状态码 | AUX（辅助接口） | - |

**数据链路自动识别**：
- 分析列表接口响应中的 ID 字段
- 检查详情接口或媒体接口请求中是否使用了该 ID
- 自动建立接口间的调用链（如 list → detail → media）

**参数分类**（通用规则）：

| 类型 | 判断规则 |
|------|----------|
| 静态参数 | version, platform, os, brand, model, channel, appVersion 等固定值 |
| 会话参数 | token, userId, session, uid, authorization 等用户身份标识 |
| 动态参数 | sign, nonce, timestamp, signature 等每次请求值不同的参数 |

**签名机制识别**：
- 如果请求含 sign/signature + nonce + timestamp → 有动态签名
- 结论：无法脱离 App 独立调用，需通过回放方式采集

**目标匹配**：
- 结合用户在阶段 1 提供的 target_data，标注哪些接口与用户目标最相关
- 如果未找到匹配目标的接口，明确告知用户并列出所有已识别的业务接口

### 阶段 6：报告输出

**输出结构**：
```
output/analysis/
├── {app_name}_api_report.md      # 接口报告（Markdown）
└── samples/
    ├── {endpoint_1}_request.json    # 请求样本
    ├── {endpoint_1}_response.json   # 响应样本（完整 JSON）
    ├── {endpoint_2}_request.json
    └── {endpoint_2}_response.json
```

**报告内容**：
1. **抓取目标摘要**：用户的目标数据描述和操作页面
2. **数据链路图**：接口间的调用关系（如 list → detail → media）
3. **接口概览表**：路径、用途、类型、调用次数、是否匹配用户目标
4. **每个接口详情**：
   - 请求参数表（参数名 + 类型 + 示例值）
   - 响应结构概览（data 字段的 key 列表和类型）
   - 列表数据的第一条记录字段（展示数据结构）
   - 完整响应引用：`📁 [{endpoint}_response.json](samples/{endpoint}_response.json)`
   - cURL 命令（可直接复制执行）
5. **签名机制说明**
6. **采集策略建议**

**报告中不内联大段 JSON**，所有原始数据保存到 `samples/` 目录。

**报告用途**：该报告是给其他 AI 或开发者使用的，需要格式清晰、结构化程度高，便于 AI 解析和理解接口结构。

## 暂停点

### 暂停点 1：需求确认
**时机**：阶段 1 完成后
**展示**：抓取目标摘要
**用户动作**：确认目标 / 补充修改

### 暂停点 2：环境就绪通知
**时机**：阶段 2 完成后
**展示**：环境配置结果 + 定制化的用户操作指引
**用户动作**：开始在手机上操作 App

### 暂停点 3：操作完成确认
**时机**：用户告知操作完成后
**展示**：捕获到的请求数量统计
**AI 动作**：开始分析流量

### 暂停点 4：报告交付
**时机**：阶段 6 完成后
**展示**：报告摘要 + 文件路径
**用户决策**：确认完成 / 要求补充分析（如"详情接口没抓到，再操作一次"）

## 约束与限制

- 需要真实设备或模拟器（MuMu、Android Studio Emulator 等）通过 adb 连接
- 本 skill 不使用 Mobile MCP 操控设备，全程由用户手动操作 App
- 部分 App 有 SSL Pinning（如字节系），需要 Frida/Xposed 绕过才能解密 HTTPS
- 有动态签名的接口无法脱离 App 独立调用
- tmpfs 方式安装的系统证书在设备重启后会丢失，需要重新安装
- 接口识别基于通用的响应结构模式，可能需要用户确认分类结果

## 使用示例

**示例 1：短视频 App**
```
用户：帮我抓取某短视频App的接口
AI：好的，我来帮你。你想获取什么数据？
用户：推荐视频列表和视频播放地址
AI：收到。你打算操作哪些页面？
用户：首页刷视频，点进去看播放
AI：确认目标：推荐列表接口 + 播放地址接口，操作首页和播放页。请提供设备ID...
```

**示例 2：电商 App**
```
用户：帮我抓某电商App的商品列表和详情接口，操作首页和商品详情页，设备是 emulator-5554
AI：信息完整，直接开始配置环境...
```

**示例 3：漫画/小说 App**
```
用户：帮我抓某漫画App的作品列表、章节列表和阅读接口
AI：收到。操作计划：首页浏览列表 → 点击作品看详情 → 点击章节看内容。确认？
```

## 依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| mitmproxy | HTTPS 流量拦截 | `uv add mitmproxy` |
| adb | 设备连接/证书安装/代理设置 | Android SDK 或模拟器自带 |
