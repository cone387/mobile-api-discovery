"""mitmdump addon: 捕获河马剧场 API 请求"""
import json
import os
from datetime import datetime
from mitmproxy import http

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "captures")
os.makedirs(OUTPUT_DIR, exist_ok=True)
captured = []

def response(flow: http.HTTPFlow) -> None:
    content_type = flow.response.headers.get("content-type", "")
    if any(t in content_type for t in ["image/", "font/", "video/", "audio/"]):
        return
    
    url = flow.request.pretty_url
    is_api = ("json" in content_type or "/api/" in url or "/v1/" in url or "/v2/" in url or "/v3/" in url)
    if not is_api:
        return

    try:
        resp_body = flow.response.get_content().decode("utf-8", errors="replace") if flow.response.raw_content else None
    except Exception:
        resp_body = flow.response.raw_content.hex()[:500] if flow.response.raw_content else None

    try:
        req_body = flow.request.get_content().decode("utf-8", errors="replace") if flow.request.raw_content else None
    except Exception:
        req_body = flow.request.raw_content.hex()[:500] if flow.request.raw_content else None

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
    print(f"[API] {flow.request.method} {url[:120]} -> {flow.response.status_code} ({len(resp_body or '')} chars)")
    
    with open(os.path.join(OUTPUT_DIR, "hema_captured.json"), "w", encoding="utf-8") as f:
        json.dump(captured, f, ensure_ascii=False, indent=2)
