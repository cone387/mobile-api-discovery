"""生成河马剧场接口报告 v3
- 响应保存到 samples/ 目录
- 报告中只引用文件路径
- 完整数据链路：list → 短剧详情(含剧集列表) → 剧集播放
- 附带 curl 命令
"""
import json
import os
from pathlib import Path

INPUT = Path(r"ai-api-capture/output/captures/hema_captured.json")
SAMPLES_DIR = Path("ai-api-capture/output/analysis/samples")
OUTPUT = Path("ai-api-capture/output/analysis/hema_api_report.md")

SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

data = json.load(INPUT.open("r", encoding="utf-8"))

# 按路径分组
apis = {}
for d in data:
    url = d.get("url", "")
    if "freevideo" not in url or "portal" not in url:
        continue
    for domain in ("zqqds.cn", "dzkjk.cn"):
        if domain in url:
            path = url.split(f"freevideo.{domain}")[1].split("?")[0]
            apis.setdefault(path, []).append(d)
            break

# 目标接口 - 完整数据链路
targets = [
    {
        "path": "/free-video-portal/portal/1113",
        "name": "短剧推荐列表",
        "desc": "首页推荐流，返回短剧列表（含封面、简介、标签、播放量等）。通过 pageFlag 实现分页。",
        "role": "LIST",
    },
    {
        "path": "/free-video-portal/portal/1125",
        "name": "剧场分类列表（漫剧tab）",
        "desc": "剧场页面的分类数据，包含频道分组（推荐/穿越/重生/古装等）和频道下的短剧列表。",
        "role": "LIST",
    },
    {
        "path": "/free-video-portal/portal/1131",
        "name": "短剧详情（含剧集列表+当前集播放信息）",
        "desc": "传入 bookId + chapterId，返回短剧完整信息（videoInfo）、剧集列表（chapterList）和当前集的播放地址（mp4Url）。",
        "role": "DETAIL",
    },
    {
        "path": "/free-video-portal/portal/1139",
        "name": "剧集播放信息（切集时调用）",
        "desc": "切换剧集时调用，传入 bookId + chapterIds，返回指定集的播放地址和解锁状态。",
        "role": "EPISODE",
    },
]


def save_sample(name: str, sample: dict) -> str:
    """保存响应样本到文件，返回相对路径"""
    # 保存完整请求+响应
    filepath = SAMPLES_DIR / f"{name}.json"
    filepath.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"samples/{name}.json"


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
        v_escaped = v.replace("'", "'\\''")
        parts.append(f"  -H '{k}: {v_escaped}'")
    
    if body:
        body_escaped = body.replace("'", "'\\''")
        parts.append(f"  -d '{body_escaped}'")
    
    return " \\\n".join(parts)


# 生成报告
lines = []
lines.append("# 河马剧场 API 接口报告")
lines.append("")
lines.append("## 数据链路")
lines.append("")
lines.append("```")
lines.append("短剧列表 (/portal/1113 或 /portal/1125)")
lines.append("  │")
lines.append("  │  返回 dataList: [{bookId, bookName, coverWap, chapterId, ...}]")
lines.append("  │")
lines.append("  ▼")
lines.append("短剧详情+剧集列表 (/portal/1131)")
lines.append("  │  请求: {bookId, chapterId}")
lines.append("  │  返回: videoInfo + chapterList + mp4Url")
lines.append("  │")
lines.append("  ▼")
lines.append("切集播放 (/portal/1139)")
lines.append("  │  请求: {bookId, chapterIds}")
lines.append("  │  返回: 指定集的播放地址")
lines.append("```")
lines.append("")

lines.append("## 接口概览")
lines.append("")
lines.append("| # | 接口 | 用途 | 角色 | 请求次数 |")
lines.append("|---|------|------|------|----------|")
for i, t in enumerate(targets, 1):
    count = len(apis.get(t["path"], []))
    lines.append(f"| {i} | `{t['path']}` | {t['name']} | {t['role']} | {count} |")
lines.append("")

lines.append("> **签名机制**: 所有接口通过 `sign` header 签名 + `datas` header 传递设备/用户信息 + `nonce`/`timestamp` 防重放。")
lines.append("> **采集策略**: 无法脱离 App 独立调用，需通过 mobile-mcp 操控 + mitmproxy 拦截。")
lines.append("")

# 每个接口详情
for i, t in enumerate(targets, 1):
    items = apis.get(t["path"], [])
    if not items:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## {i}. `{t['path']}` — {t['name']}")
        lines.append(f"")
        lines.append(f"**未抓到该接口请求**（需要在 App 中触发对应操作）")
        lines.append("")
        continue
    
    sample = items[0]
    
    # 保存样本文件
    sample_name = f"portal_{t['path'].split('/')[-1]}"
    # 保存请求样本
    req_sample = {
        "url": sample["url"],
        "method": sample["method"],
        "headers": sample["request_headers"],
        "body": sample.get("request_body"),
    }
    save_sample(f"{sample_name}_request", req_sample)
    
    # 保存响应样本
    resp_data = sample.get("response_body", "")
    try:
        resp_parsed = json.loads(resp_data)
        save_sample(f"{sample_name}_response", resp_parsed)
    except:
        save_sample(f"{sample_name}_response", {"raw": resp_data[:5000]})
    
    lines.append("---")
    lines.append("")
    lines.append(f"## {i}. `{t['path']}` — {t['name']}")
    lines.append("")
    lines.append(f"> {t['desc']}")
    lines.append("")
    lines.append(f"**方法**: `{sample['method']}`  ")
    lines.append(f"**域名**: `freevideo.zqqds.cn` / `freevideo.dzkjk.cn`  ")
    lines.append(f"**调用次数**: {len(items)}")
    lines.append("")
    
    # 请求体
    lines.append("### 请求参数")
    lines.append("")
    req_body = sample.get("request_body", "")
    if req_body:
        try:
            rb = json.loads(req_body)
            lines.append("| 参数 | 示例值 | 说明 |")
            lines.append("|------|--------|------|")
            for k, v in rb.items():
                val = str(v)[:60]
                lines.append(f"| `{k}` | `{val}` | |")
        except:
            lines.append(f"```\n{req_body[:500]}\n```")
    else:
        lines.append("无请求体")
    lines.append("")
    
    # 响应结构
    lines.append("### 响应结构")
    lines.append("")
    lines.append(f"📁 完整响应: [`{sample_name}_response.json`](samples/{sample_name}_response.json)")
    lines.append("")
    
    # 简要描述响应结构
    try:
        resp = json.loads(resp_data)
        d = resp.get("data", {})
        if isinstance(d, dict):
            lines.append("**data 字段结构**:")
            lines.append("")
            lines.append("```")
            for k, v in d.items():
                if isinstance(v, list) and v:
                    lines.append(f"  {k}: [{type(v[0]).__name__}, ...] ({len(v)} items)")
                elif isinstance(v, dict):
                    lines.append(f"  {k}: {{{', '.join(list(v.keys())[:5])}...}}")
                else:
                    lines.append(f"  {k}: {str(v)[:50]}")
            lines.append("```")
            lines.append("")
            
            # 如果有列表数据，展示第一条的 key
            for list_key in ("dataList", "chapterList", "channelGroupData"):
                if list_key in d and isinstance(d[list_key], list) and d[list_key]:
                    first_item = d[list_key][0]
                    if isinstance(first_item, dict):
                        lines.append(f"**{list_key}[0] 字段**:")
                        lines.append("")
                        lines.append("```")
                        for fk, fv in first_item.items():
                            val_preview = str(fv)[:60]
                            lines.append(f"  {fk}: {val_preview}")
                        lines.append("```")
                        lines.append("")
    except:
        pass
    
    # curl 命令
    lines.append("### cURL")
    lines.append("")
    lines.append(f"📁 完整请求: [`{sample_name}_request.json`](samples/{sample_name}_request.json)")
    lines.append("")
    lines.append("```bash")
    lines.append(gen_curl(sample))
    lines.append("```")
    lines.append("")

report_text = "\n".join(lines)
OUTPUT.write_text(report_text, encoding="utf-8")
print(f"Report: {OUTPUT}")
print(f"Samples: {list(SAMPLES_DIR.glob('*.json'))}")
