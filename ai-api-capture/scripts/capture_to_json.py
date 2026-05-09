"""mitmdump addon: 将捕获的请求保存为 JSON 文件

内置多层过滤逻辑，在抓包阶段就排除无关流量，减少后续分析的数据量和 token 消耗。

过滤策略：
1. 静态资源过滤：跳过图片、视频、字体、CSS、JS
2. SDK/第三方服务过滤：跳过埋点、崩溃上报、广告SDK、推送等
3. 业务 API 识别：只保留 JSON 响应或已知 API 路径模式
"""
import json
import os
import base64
from datetime import datetime
from mitmproxy import http

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "captures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

captured = []

# ============================================================
# 过滤规则配置
# ============================================================

# 第三方 SDK / 非业务域名黑名单（精确匹配或包含匹配）
BLOCKED_DOMAINS = [
    # 数据上报/埋点
    "analytics.oceanengine.com",
    "sss.umeng.com",
    "tracking.miui.com",
    "clientlognew.hzage.cn",
    "sc-sa.dzfread.cn",
    "log0-misc",
    "abtest",
    # 崩溃上报
    "pro.bugly.qq.com",
    "bugly.qq.com",
    # 广告
    "ad-union.ssread.cn",
    "pbaccess.video.qq.com",
    "amdcopen.m.taobao.com",
    # 推送
    "gepush.com",
    "sdk-open-phone.getui.com",
    # 性能监控
    "tingyun.com",
    "wkdcm1.tingyun.com",
    "wkrt.tingyun.com",
    # DNS / CDN 探测
    "203.107.1.1",
    "cbsipv4.shuzilm.cn",
    # 设备指纹 / 安全
    "mssdk",
    "polaris",
    "gecko.zijieapi.com",
    # MuMu 模拟器自身
    "report.mumu.nie.netease.com",
    "api.mumu.nie.netease.com",
    # 其他非业务
    "dig.bdurl.net",
]

# 路径黑名单（包含匹配）
BLOCKED_PATHS = [
    "/sdk/app/",
    "/sdk/app/config",
    "/reportBatchData",
    "/upload-json",
    "/api/v2/al",
    "/api/v1/attribute",
    "/api/collection",
    "/getMobileRedirectHost",
    "/initMobileApp",
    "/track/v4",
]

# 静态资源 Content-Type 黑名单
BLOCKED_CONTENT_TYPES = [
    "image/",
    "font/",
    "video/",
    "audio/",
    "text/css",
    "application/javascript",
    "text/javascript",
    "application/octet-stream",
]


def _is_blocked_domain(url: str) -> bool:
    """检查 URL 是否属于被屏蔽的域名"""
    for domain in BLOCKED_DOMAINS:
        if domain in url:
            return True
    return False


def _is_blocked_path(url: str) -> bool:
    """检查 URL 路径是否在黑名单中"""
    for path in BLOCKED_PATHS:
        if path in url:
            return True
    return False


def _is_blocked_content_type(content_type: str) -> bool:
    """检查 Content-Type 是否为静态资源"""
    for blocked in BLOCKED_CONTENT_TYPES:
        if blocked in content_type:
            return True
    return False


def response(flow: http.HTTPFlow) -> None:
    """捕获响应并保存（带多层过滤）"""
    url = flow.request.pretty_url
    content_type = flow.response.headers.get("content-type", "")

    # 第 1 层：静态资源过滤
    if _is_blocked_content_type(content_type):
        return

    # 第 2 层：第三方 SDK 域名过滤
    if _is_blocked_domain(url):
        return

    # 第 3 层：路径黑名单过滤
    if _is_blocked_path(url):
        return

    # 第 4 层：只保留 JSON 响应或已知 API 路径模式
    is_api = (
        "json" in content_type
        or "/api/" in url
        or "/v1/" in url
        or "/v2/" in url
        or "/portal/" in url
        or "free-video" in url
    )
    if not is_api:
        return

    # 安全获取请求体
    try:
        req_body = flow.request.get_content().decode("utf-8", errors="replace") if flow.request.raw_content else None
    except Exception:
        req_body = base64.b64encode(flow.request.raw_content).decode("ascii") if flow.request.raw_content else None

    # 安全获取响应体
    try:
        resp_body = flow.response.get_content().decode("utf-8", errors="replace") if flow.response.raw_content else None
    except Exception:
        resp_body = base64.b64encode(flow.response.raw_content).decode("ascii") if flow.response.raw_content else None

    record = {
        "timestamp": datetime.now().isoformat(),
        "method": flow.request.method,
        "url": url,
        "request_headers": dict(flow.request.headers),
        "request_body": req_body,
        "response_status": flow.response.status_code,
        "response_headers": dict(flow.response.headers),
        "response_body": resp_body,
    }
    
    captured.append(record)
    
    # 实时打印
    print(f"[CAPTURED] {flow.request.method} {url[:100]} -> {flow.response.status_code}")
    
    # 每次都保存到文件
    output_file = os.path.join(OUTPUT_DIR, "qimao_captured.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(captured, f, ensure_ascii=False, indent=2)
