"""生成河马剧场接口报告 v2 - 正确的接口识别 + curl 命令"""
import json
from pathlib import Path

data = json.load(Path(r"ai-api-capture/output/captures/hema_captured.json").open("r", encoding="utf-8"))
OUTPUT = Path("ai-api-capture/output/analysis/hema_api_report.md")

# 按路径分组
apis = {}
for d in data:
    url = d.get("url", "")
    if "freevideo" not in url or "portal" not in url:
        continue
    if "zqqds.cn" in url:
        path = url.split("freevideo.zqqds.cn")[1].split("?")[0]
    elif "dzkjk.cn" in url:
        path = url.split("freevideo.dzkjk.cn")[1].split("?")[0]
    else:
        continue
    apis.setdefault(path, []).append(d)

# 目标接口
targets = {
    "/free-video-portal/portal/1113": "首页推荐列表（含分页）",
    "/free-video-portal/portal/1125": "剧场分类列表（漫剧tab）",
    "/free-video-portal/portal/1131": "短剧详情（剧集列表+播放信息）",
}


def gen_curl(sample: dict) -> str:
    """生成 curl 命令"""
    method = sample["method"]
    url = sample["url"]
    headers = sample["request_headers"]
    body = sample.get("request_body")
    
    parts = [f"curl -X {method}"]
    parts.append(f"  '{url}'")
    
    for k, v in headers.items():
        if k.lower() in ("connection", "accept-encoding", "content-length"):
            continue
        # 转义单引号
        v_escaped = v.replace("'", "'\\''")
        parts.append(f"  -H '{k}: {v_escaped}'")
    
    if body:
        body_escaped = body.replace("'", "'\\''")
        if len(body_escaped) > 500:
            body_escaped = body_escaped[:500] + "...[TRUNCATED]"
        parts.append(f"  -d '{body_escaped}'")
    
    return " \\\n".join(parts)


lines = []
lines.append("# 河马剧场 API 接口报告")
lines.append("")
lines.append("## 概览")
lines.append("")
lines.append("| 接口 | 用途 | 请求次数 |")
lines.append("|------|------|----------|")
for path, desc in targets.items():
    count = len(apis.get(path, []))
    lines.append(f"| `{path}` | {desc} | {count} |")
lines.append("")
lines.append("> ⚠️ 所有接口都包含动态签名（sign header + nonce + timestamp），无法脱离 App 独立调用。")
lines.append("> 采集策略：通过 mobile-mcp 操控 App + mitmproxy 拦截响应数据。")
lines.append("")

for path, desc in targets.items():
    items = apis.get(path, [])
    if not items:
        continue
    
    sample = items[0]
    
    lines.append("---")
    lines.append("")
    lines.append(f"## `{path}` — {desc}")
    lines.append("")
    lines.append(f"**方法**: `{sample['method']}`  ")
    lines.append(f"**URL**: `{sample['url']}`  ")
    lines.append(f"**调用次数**: {len(items)}")
    lines.append("")
    
    # 请求体
    lines.append("### 请求体 (Request Body)")
    lines.append("")
    req_body = sample.get("request_body", "")
    if req_body:
        lines.append("```json")
        try:
            parsed = json.loads(req_body)
            lines.append(json.dumps(parsed, ensure_ascii=False, indent=2))
        except:
            lines.append(req_body[:1000])
        lines.append("```")
    else:
        lines.append("无")
    lines.append("")
    
    # 响应体
    lines.append("### 响应体 (Response Body Sample)")
    lines.append("")
    resp = sample.get("response_body", "")
    if resp:
        lines.append("```json")
        try:
            parsed = json.loads(resp)
            formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
            if len(formatted) > 4000:
                formatted = formatted[:4000] + "\n...[TRUNCATED]"
            lines.append(formatted)
        except:
            lines.append(resp[:4000])
        lines.append("```")
    lines.append("")
    
    # curl 命令
    lines.append("### cURL 命令")
    lines.append("")
    lines.append("```bash")
    lines.append(gen_curl(sample))
    lines.append("```")
    lines.append("")
    
    # 分页说明（如果有）
    if req_body:
        try:
            rb = json.loads(req_body)
            if "pageFlag" in rb:
                lines.append("### 分页说明")
                lines.append("")
                lines.append("- `pageFlag`: 空字符串表示第一页，后续页使用响应中返回的 `data.pageFlag` 值")
                lines.append("- `hasMore`: 响应中 `data.hasMore` 为 true 表示还有下一页")
                lines.append("")
                # 找第二次调用看分页参数
                if len(items) > 1:
                    second = items[1]
                    try:
                        rb2 = json.loads(second.get("request_body", "{}"))
                        if rb2.get("pageFlag"):
                            lines.append(f"**第二页请求 pageFlag**: `{rb2['pageFlag']}`")
                            lines.append("")
                    except:
                        pass
        except:
            pass

report_text = "\n".join(lines)
OUTPUT.write_text(report_text, encoding="utf-8")
print(f"Report saved: {OUTPUT}")
print(f"Lines: {len(lines)}")
