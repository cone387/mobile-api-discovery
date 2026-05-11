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

### 阶段 5：AI 分析流量并撰写报告

**重要：报告由 AI 阅读 samples 文件后撰写，不是代码自动生成。**

用户操作完成后，AI 执行以下步骤：

1. **读取 captures 目录**：`output/captures/*.json`，每个文件是一个请求-响应对
2. **识别业务域名**：排除广告 SDK（快手、穿山甲、百度等），找到 App 自身的业务域名
3. **逐个阅读业务接口的响应体**：理解每个接口返回了什么数据
4. **撰写高质量报告**：参考下方报告模板

**AI 分析时的思考框架**：
- 这个接口返回的是什么数据？（列表？详情？播放地址？配置？）
- 响应中哪些字段是用户关心的？（标题、封面、播放量、章节列表等）
- 接口之间的调用关系是什么？（列表中的 ID 是否被详情接口使用？）
- 有没有签名机制？能否脱离 App 独立调用？

**报告模板**（参考 [`hema_manju_api_report.md`](../output/analysis/hema_manju_api_report.md) 的格式）：

```markdown
# {App名} API 接口报告

## 数据链路

（用 ASCII 图展示接口间的调用关系，标注每个接口返回的关键数据）

## 关键字段对照

（表格：字段名 | 含义 | 所在接口 | 示例值）

## 接口概览

（表格：# | 接口路径 | 用途（中文描述） | 角色 | 请求次数）

## 每个接口详情

### N. `/path/to/endpoint` — 中文用途说明

> 一句话描述这个接口干什么的

**方法**: POST/GET
**域名**: xxx.com
**调用次数**: N

#### 请求参数
（表格：参数 | 示例值 | 说明）

#### 响应结构
📁 完整响应: [filename.json](samples/filename.json)

**data 字段结构**:
（展开 data 下的 key 列表，标注类型和含义）

**关键数据示例**（如 dataList[0] 或 chapterList[0] 的字段展开）

#### cURL
（完整可执行的 cURL 命令）
```

**报告质量要求**：
- 每个接口必须有**中文用途说明**（不能只写 "detail" "media"）
- 必须展开响应结构，展示关键字段和含义
- 列表接口必须展示第一条数据的完整字段
- 必须标注哪些字段是用户关心的数据（如播放量、章节列表等）
- 数据链路图必须清晰展示接口间的调用关系和数据流向

**输出结构**：
```
output/analysis/
├── {app_name}_api_report.md      # AI 撰写的接口报告
└── samples/
    ├── portal_1125_request.json
    ├── portal_1125_response.json
    ├── portal_1131_request.json
    ├── portal_1131_response.json
    └── ...
```

**samples 文件命名规则**：
- 使用接口路径中有意义的部分命名（如 `portal_1125`），不要用 UUID
- 每个接口保存 `_request.json` 和 `_response.json` 两个文件

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
**AI 动作**：停止 mitmdump，清理代理，开始读取 samples 分析

### 暂停点 4：报告交付
**时机**：阶段 5 完成后
**展示**：完整的接口分析报告（Markdown）
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

## 完整 Demo：河马漫剧

以下是使用本 skill 分析河马漫剧 App 的完整流程记录，作为其他 AI 参考的 demo。

### Demo 需求

```
用户：分析河马漫剧的首页+分页+详情页（需要能拿到剧集list+单集详情）
```

### Demo 流程

**阶段 1：需求确认**
```
AI：收到，确认你的抓取目标：
- App：河马漫剧
- 目标数据：首页漫剧列表、分页加载、详情页剧集列表、单集详情
- 操作页面：首页（剧场tab）、详情页
```

**阶段 2：环境准备**
```bash
# 连接 MuMu 模拟器
adb connect 127.0.0.1:16384

# 设置代理（10.0.2.2 是模拟器访问宿主机的地址）
adb -s 127.0.0.1:16384 shell settings put global http_proxy 10.0.2.2:8080

# 启动 mitmdump
mitmdump --set block_global=false -s addons/capture_addon.py -p 8080
```

**阶段 3：用户操作**
```
AI：✅ 抓包环境已就绪！请在手机上操作河马漫剧 App：
    1. 浏览首页漫剧列表
    2. 向下滑动加载更多（触发分页）
    3. 点击一部漫剧进入详情页

用户：操作完了，最后点击的详情页短剧是"遇遇跑路"
```

**阶段 4：停止录制 + 清理**
```bash
# 停止 mitmdump（Ctrl+C）
# 清理代理
adb -s 127.0.0.1:16384 shell settings put global http_proxy :0
```

**阶段 5：AI 分析并撰写报告**

AI 读取 `output/captures/` 目录中的 JSON 文件，识别出业务域名 `freevideo.zqqds.cn`，
排除广告 SDK（快手、穿山甲、百度等），分析 3 个核心业务接口，撰写报告。

### Demo 产出

📁 完整报告：[`output/analysis/hema_manju_api_report.md`](../output/analysis/hema_manju_api_report.md)

**识别到的核心接口**：

| 接口 | 用途 | 关键数据 |
|------|------|----------|
| `/portal/1125` | 剧场分类列表 | 漫剧列表 + 播放量（coverBottomTips） + 分页（pageFlag/hasMore） |
| `/portal/1131` | 短剧详情 | 剧集列表（chapterList 49集） + 当前集播放地址（mp4Url） |
| `/portal/1139` | 切集播放 | 批量获取指定集播放地址 + 评论数 |

**数据链路**：`/portal/1125`(bookId) → `/portal/1131`(bookId) → `/portal/1139`(bookId + chapterIds)

**签名机制**：所有接口含 `sign` 动态签名 + `nonce` + `timestamp`，无法脱离 App 独立调用。

## 依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| mitmproxy | HTTPS 流量拦截 | `uv add mitmproxy` |
| adb | 设备连接/证书安装/代理设置 | Android SDK 或模拟器自带 |
