---
name: AI API Capture
description: AI 驱动的移动端接口抓取与代码生成，通过操控真实移动设备触发 App 行为，自动抓包、过滤、分析接口并生成接口报告
version: 2.0.0
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
  - 短剧
  - 数据采集
dependencies:
  tools:
    - mitmproxy (>=10.1.0)
    - mobile-mcp
    - adb
  python:
    - mitmproxy
    - requests
---

# AI API Capture Skill

## 概述

通过 AI 操控真实移动设备触发 App 行为，利用 mitmproxy 抓取网络请求，自动过滤无关流量，分析业务接口并生成结构化的接口报告。

**核心目标**：以最低逆向成本，快速将 App 接口转化为可用的数据源文档。

## 触发条件

当用户消息中包含以下关键词或意图时激活：

- "抓取接口"、"抓取 API"、"App 接口"
- "移动端抓包"、"接口逆向"
- "采集 App 数据"、"接口报告"
- "capture API"、"mobile API capture"

## 输入参数

| 参数名 | 必填 | 说明 | 示例 |
|--------|------|------|------|
| app_package | 是 | 目标 App 包名 | `com.dz.hmjc` |
| device_id | 是 | 设备标识符 | `127.0.0.1:16384` |
| operation_intent | 是 | 操作意图描述 | "进入剧场漫剧tab，滑动列表，点击一个短剧进入详情" |
| target_data | 否 | 期望获取的数据 | "短剧列表+详情+播放量" |
| filter_domains | 否 | 关注的域名 | `["freevideo.zqqds.cn"]` |

## 执行流程

### 阶段 1：环境准备与抓包启动

1. **检查设备连接**
   ```
   mobile_list_available_devices → 确认设备在线
   ```

2. **安装系统级 CA 证书**（如果需要 HTTPS 解密）
   ```bash
   # 通过 adb 使用 tmpfs overlay 方式安装到系统证书目录
   adb shell "su 0 mount -t tmpfs tmpfs /system/etc/security/cacerts"
   adb shell "cp /data/local/tmp/certs/* /system/etc/security/cacerts/"
   ```

3. **设置设备代理**
   ```bash
   adb shell settings put global http_proxy 10.0.2.2:8080
   ```

4. **启动 mitmdump + 过滤脚本**
   ```bash
   mitmdump --set block_global=false -s scripts/capture_to_json.py
   ```

### 阶段 2：设备操控触发接口

**操控原则**：
- 滑动时从屏幕边缘/空白区域起始，避免误触封面进入详情
- 每次操作后等待 1-2 秒让网络请求完成
- 按用户指定的操作意图逐步执行

**典型操作序列**：
```
1. 启动 App → 等待首页加载（触发首页 list 接口）
2. 点击目标 tab → 等待加载（触发分类 list 接口）
3. 从空白区域向上滑动 → 触发分页加载（触发 pagination 接口）
4. 点击某个内容项 → 进入详情页（触发 detail 接口）
```

**滑动注意事项**：
- 使用 `swipe_on_screen(direction="up", distance=800, x=450, y=1290)` 从底部空白区滑动
- 不要从内容封面中心滑动，否则会触发点击进入详情

### 阶段 3：流量过滤（内置 4 层过滤）

在抓包阶段就排除无关流量，减少后续分析的数据量和 token 消耗：

**第 1 层：静态资源过滤**
- 跳过 image/、font/、video/、audio/、text/css、application/javascript

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
- 或 URL 路径含 /api/、/v1/、/v2/、/portal/ 等已知 API 模式

### 阶段 4：接口分析与报告生成

**接口识别逻辑**（基于响应结构，不是猜测）：

| 响应特征 | 接口类型 |
|----------|----------|
| 响应含 `dataList` / `list` 数组 | LIST（列表接口） |
| 响应含 `hasMore` + `pageFlag` | LIST + 分页 |
| 响应含 `chapterList` / `episodeList` | DETAIL（详情，含剧集列表） |
| 响应含 `mp4Url` / `videoUrl` / `playUrl` | PLAY（播放接口） |
| 响应含 `commentNum` / `result` 简单值 | AUX（辅助接口，非核心） |
| 响应含 `config` / `settings` | CONFIG（配置接口） |

**数据链路自动识别**：
- 分析 list 接口响应中的 ID 字段（如 bookId）
- 检查 detail 接口请求中是否使用了该 ID
- 自动建立 list → detail → play 的调用链

**参数分类**：

| 类型 | 判断规则 |
|------|----------|
| 静态 | version, pname, os, brand, model, channelCode |
| 会话 | token, userId, session, uid |
| 动态 | sign, nonce, timestamp, boxId（每次请求值不同） |

**签名机制识别**：
- 如果请求头有 `sign` + `nonce` + `timestamp` → 有动态签名
- 结论：无法脱离 App 独立调用，需通过回放方式采集

### 阶段 5：报告输出

**输出结构**：
```
output/analysis/
├── {app}_api_report.md      # 接口报告（Markdown）
└── samples/
    ├── portal_1113_request.json    # 请求样本
    ├── portal_1113_response.json   # 响应样本（完整 JSON）
    ├── portal_1131_request.json
    └── portal_1131_response.json
```

**报告内容**：
1. **数据链路图**：list → detail → play 的调用关系
2. **接口概览表**：路径、用途、角色、调用次数
3. **每个接口详情**：
   - 请求参数表（参数名 + 示例值）
   - 响应结构概览（data 字段的 key 列表）
   - 列表数据的第一条记录字段
   - 完整响应引用：`📁 [portal_xxx_response.json](samples/portal_xxx_response.json)`
   - cURL 命令（可直接复制执行）
4. **签名机制说明**
5. **采集策略建议**

**报告中不内联大段 JSON**，所有原始数据保存到 `samples/` 目录。

## 暂停点

### 暂停点 1：操作确认
**时机**：阶段 2 开始前
**展示**：当前屏幕截图 + 计划的操作序列
**用户决策**：确认操作 / 修改操作意图

### 暂停点 2：接口分析结果确认
**时机**：阶段 4 完成后
**展示**：识别到的接口列表 + 数据链路
**用户决策**：确认 / 要求补充抓取（如"详情接口没抓到，再点一个进去"）

### 暂停点 3：报告交付
**时机**：阶段 5 完成后
**展示**：报告摘要 + 文件路径
**用户决策**：确认完成 / 要求补充分析

## 约束与限制

- 需要真实设备或模拟器（MuMu、Android Studio Emulator 等）
- 部分 App 有 SSL Pinning（如字节系），需要 Frida/Xposed 绕过才能解密 HTTPS
- 有动态签名的接口无法脱离 App 独立调用，只能通过回放方式采集
- tmpfs 方式安装的系统证书在设备重启后会丢失，需要重新安装
- 滑动操作可能误触内容进入详情，需要从空白区域操作

## 依赖

| 工具 | 用途 | 安装 |
|------|------|------|
| mitmproxy | HTTPS 流量拦截 | `uv add mitmproxy` |
| mobile-mcp | 设备操控 | Kiro 内置 |
| adb | 设备连接/证书安装/代理设置 | Android SDK 或模拟器自带 |
