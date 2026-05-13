---
name: ai-api-capture
description: AI-assisted mobile app API capture and analysis. Guides users through mitmproxy setup, captures HTTP traffic while users manually operate apps, then analyzes and generates structured API documentation. Works with any app. Self-contained - all scripts are generated at runtime.
---

# AI API Capture Skill

## 概述

通用的移动端接口抓取与分析方案。AI 首先引导用户明确抓取目标（什么 App、什么数据、哪些页面），然后自动配置 mitmproxy 代理环境，通知用户手动操作 App，最后分析录制的流量，基于通用的响应结构模式识别业务接口类型，生成结构化的接口分析报告。

**核心目标**：以最低逆向成本，快速将任意 App 的接口转化为可用的数据源文档，供其他 AI 或开发者参考使用。

**重要说明**：
- 本 skill 是通用方案，适用于任意 App 的接口抓取，不绑定特定 App 或特定字段名
- 本 skill 不使用 Mobile MCP 操控设备，全程由用户手动操作 App
- AI 只负责：需求引导、环境准备、流量分析
- **本 skill 完全自包含**：所有代码和脚本在运行时动态生成，无需额外安装

## 系统要求

AI 会在运行时自动检查并引导安装：
- Python 3.8+（用于运行 mitmproxy）
- mitmproxy（AI 会自动检查，未安装时提供安装命令）
- adb（Android 模拟器通常自带）

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

## 执行流程

### 阶段 0：环境自检（自动执行）

AI 在开始前自动检查环境，**不需要用户操心**：

**自检命令**：
```bash
mitmdump --version
adb version
adb devices
```

**如果 mitmproxy 未安装，按优先级选择安装方式**：
```bash
# 优先级 1：当前目录有 pyproject.toml → 添加到项目依赖
uv add mitmproxy
# 后续用 uv run mitmdump 启动

# 优先级 2：有 uv 但无项目上下文 → 临时运行
uvx mitmdump --version
# 后续用 uvx mitmdump 启动

# 优先级 3：有 pipx → 隔离安装
pipx install mitmproxy

# 优先级 4：兜底
pip install mitmproxy
```

### 阶段 1：需求收集与引导

AI 在开始抓包前，先确保用户的需求足够清晰：

**必须明确的信息**：
1. 目标 App 名称
2. 期望获取的数据类型（列表？详情？搜索？媒体播放？）
3. 需要操作的页面（首页？搜索页？详情页？）

**引导策略**：
- 如果用户只说"帮我抓某App的接口"，AI 应追问具体数据和页面
- 如果用户一次性说清楚了，直接确认并进入下一阶段

### 阶段 2：环境准备

AI 自动完成以下步骤：

1. **生成 capture_addon.py**（如果不存在）— 将「内嵌脚本」章节的代码写入工作目录
2. **检查设备连接** — `adb devices`
3. **安装系统级 CA 证书**（如果需要 HTTPS 解密）
4. **设置设备代理** — `adb shell settings put global http_proxy <host_ip>:8080`
5. **启动 mitmdump + 过滤脚本**：
   ```bash
   # 根据阶段 0 检测结果选择：
   # 项目环境：uv run mitmdump --set block_global=false -s capture_addon.py -p 8080
   # uvx 方式：uvx mitmdump --set block_global=false -s capture_addon.py -p 8080
   # PATH 可用：mitmdump --set block_global=false -s capture_addon.py -p 8080
   ```
6. **通知用户操作 App**

### 阶段 3：等待用户操作

AI 在此阶段不执行任何操作，等待用户在手机上完成操作。
触发继续：用户说"操作完了"、"完成了"、"好了"等。

### 阶段 4：流量过滤（内置 4 层）

1. **静态资源过滤** — image/font/video/audio/css/js
2. **第三方 SDK 域名黑名单** — 埋点、广告、推送、崩溃上报等
3. **路径黑名单** — /sdk/app/、/reportBatchData 等
4. **API 白名单** — JSON 响应 + API 路径模式

### 阶段 5：AI 分析流量并撰写报告

AI 读取 `output/captures/*.json`，识别业务域名，分析接口，撰写报告。

**报告包含**：
- 数据链路图（接口间调用关系）
- 关键字段对照表
- 接口概览表
- 每个接口的详细分析（请求参数、响应结构、cURL）

**输出结构**：
```
output/analysis/
├── {app_name}_api_report.md
└── samples/
    ├── endpoint_name_request.json
    └── endpoint_name_response.json
```

## 内嵌脚本：capture_addon.py

**AI 在阶段 2 开始时，如果工作目录下不存在 `capture_addon.py`，应自动创建此文件：**

```python
"""mitmproxy addon - 4 层过滤 + JSON 存储（自包含，无外部依赖）"""

import json
import os
import uuid
from datetime import datetime
from urllib.parse import urlparse

from mitmproxy import http, tls

# === 过滤规则 ===

CONTENT_TYPE_BLACKLIST = [
    "image/", "font/", "video/", "audio/", "text/css", "application/javascript",
]

DOMAIN_BLACKLIST = [
    "analytics.oceanengine.com", "sss.umeng.com", "tracking.miui.com",
    "pro.bugly.qq.com", "bugly.qq.com",
    "pbaccess.video.qq.com", "amdcopen.m.taobao.com",
    "gepush.com", "sdk-open-phone.getui.com",
    "tingyun.com", "wkdcm1.tingyun.com",
    "203.107.1.1", "cbsipv4.shuzilm.cn",
    "mssdk", "polaris", "gecko.zijieapi.com",
    "report.mumu.nie.netease.com", "api.mumu.nie.netease.com",
]

PATH_BLACKLIST = [
    "/sdk/app/", "/reportBatchData", "/upload-json", "/api/v2/al",
    "/api/v1/attribute", "/api/collection", "/getMobileRedirectHost",
    "/initMobileApp", "/track/v4",
]

CONTENT_TYPE_WHITELIST = ["json"]
API_PATH_PATTERNS = ["/api/", "/v1/", "/v2/", "/v3/", "/portal/", "/gateway/"]

# === 配置（通过环境变量） ===

STORAGE_PATH = os.environ.get("CAPTURE_STORAGE_PATH", "./output/captures")
USER_WHITELIST = os.environ.get("CAPTURE_USER_DOMAIN_WHITELIST", "")
USER_BLACKLIST = os.environ.get("CAPTURE_USER_DOMAIN_BLACKLIST", "")

user_domain_whitelist = [d.strip() for d in USER_WHITELIST.split(",") if d.strip()] or None
user_domain_blacklist = [d.strip() for d in USER_BLACKLIST.split(",") if d.strip()] or None

os.makedirs(STORAGE_PATH, exist_ok=True)


# === 工具函数 ===

def domain_matches(hostname, domain_list):
    if not hostname:
        return False
    for domain in domain_list:
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


def should_capture(flow):
    parsed = urlparse(flow.request.pretty_url)
    hostname = parsed.hostname or ""
    path = parsed.path or ""
    ct = ""
    if flow.response and flow.response.headers:
        ct = flow.response.headers.get("content-type", "").lower()

    if user_domain_whitelist:
        if not domain_matches(hostname, user_domain_whitelist):
            return False
    if user_domain_blacklist:
        if domain_matches(hostname, user_domain_blacklist):
            return False

    for bl in CONTENT_TYPE_BLACKLIST:
        if bl.lower() in ct:
            return False
    if domain_matches(hostname, DOMAIN_BLACKLIST):
        return False
    for bp in PATH_BLACKLIST:
        if bp in path:
            return False

    for wl in CONTENT_TYPE_WHITELIST:
        if wl.lower() in ct:
            return True
    for pattern in API_PATH_PATTERNS:
        if pattern in path:
            return True
    return False


# === mitmproxy Addon ===

class CaptureAddon:
    def response(self, flow: http.HTTPFlow):
        if should_capture(flow):
            self._save(flow)

    def tls_failed_client_hello(self, client_hello: tls.ClientHelloData):
        sni = "unknown"
        if client_hello.context and client_hello.context.client:
            sni = client_hello.context.client.sni or "unknown"
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "method": "CONNECT",
            "url": f"https://{sni}/",
            "headers": {}, "body": None,
            "response_status": 0, "response_headers": {},
            "response_body": None, "is_decrypted": False,
        }
        self._write(record)

    def _save(self, flow: http.HTTPFlow):
        req_body = None
        if flow.request.content:
            try:
                req_body = flow.request.content.decode("utf-8", errors="replace")
            except Exception:
                pass
        resp_body = None
        if flow.response and flow.response.content:
            try:
                resp_body = flow.response.content.decode("utf-8", errors="replace")
            except Exception:
                pass
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "headers": dict(flow.request.headers),
            "body": req_body,
            "response_status": flow.response.status_code if flow.response else 0,
            "response_headers": dict(flow.response.headers) if flow.response else {},
            "response_body": resp_body,
            "is_decrypted": True,
        }
        self._write(record)

    def _write(self, record):
        filepath = os.path.join(STORAGE_PATH, f"{record['id']}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


addons = [CaptureAddon()]
```

## 使用示例

**示例 1：短视频 App**
```
用户：帮我抓取某短视频App的接口
AI：好的，你想获取什么数据？
用户：推荐视频列表和视频播放地址
AI：确认目标：推荐列表 + 播放地址，操作首页和播放页。请提供设备ID...
```

**示例 2：电商 App（信息完整，跳过引导）**
```
用户：帮我抓某电商App的商品列表和详情接口，操作首页和商品详情页，设备是 emulator-5554
AI：信息完整，直接开始配置环境...
```

## 依赖

| 工具 | 用途 | 安装方式（按优先级） |
|------|------|----------|
| mitmproxy | HTTPS 流量拦截 | `uv add mitmproxy` / `uvx mitmdump` / `pipx install mitmproxy` |
| adb | 设备连接/代理设置 | Android SDK 或模拟器自带 |
