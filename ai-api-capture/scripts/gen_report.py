"""从抓包数据中提取指定接口的报告"""
import json
import sys
from pathlib import Path

INPUT = Path("ai-api-capture/output/captures/hema_captured.json")
OUTPUT = Path("ai-api-capture/output/analysis/hema_api_report.md")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

data = json.load(INPUT.open("r", encoding="utf-8"))

# 提取目标接口
targets = {
    "1113": {"name": "首页漫剧列表", "items": []},
    "3106": {"name": "分页加载更多", "items": []},
    "1302": {"name": "短剧详情/播放信息", "items": []},
}

for d in data:
    url = d.get("url", "")
    for code in targets:
        if f"portal/{code}" in url:
            targets[code]["items"].append(d)
            break

# 生成 Markdown 报告
lines = []
lines.append("# 河马剧场 API 接口报告")
lines.append("")
lines.append("## 概览")
lines.append("")
lines.append("| 接口编号 | 用途 | 请求次数 | 域名 |")
lines.append("|----------|------|----------|------|")
for code, info in targets.items():
    domain = ""
    if info["items"]:
        domain = info["items"][0]["url"].split("/free-video")[0]
    lines.append(f"| /portal/{code} | {info['name']} | {len(info['items'])} | {domain} |")
lines.append("")

# 每个接口的详细报告
for code, info in targets.items():
    if not info["items"]:
        continue
    
    sample = info["items"][0]
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## /portal/{code} — {info['name']}")
    lines.append(f"")
    lines.append(f"**请求方法**: {sample['method']}")
    lines.append(f"")
    lines.append(f"**URL**: `{sample['url']}`")
    lines.append(f"")
    
    # 请求头
    lines.append(f"### 请求头")
    lines.append(f"")
    lines.append("```json")
    # 只保留关键头部
    key_headers = {k: v for k, v in sample["request_headers"].items() 
                   if k.lower() not in ("accept-encoding", "connection", "content-length")}
    lines.append(json.dumps(key_headers, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    
    # 请求体
    lines.append(f"### 请求体")
    lines.append(f"")
    if sample.get("request_body"):
        body = sample["request_body"]
        if len(body) > 1500:
            body = body[:1500] + "\n...[TRUNCATED]"
        lines.append("```json")
        # 尝试格式化 JSON
        try:
            parsed = json.loads(body)
            lines.append(json.dumps(parsed, ensure_ascii=False, indent=2))
        except:
            lines.append(body)
        lines.append("```")
    else:
        lines.append("无请求体")
    lines.append("")
    
    # 响应状态
    lines.append(f"### 响应")
    lines.append(f"")
    lines.append(f"**状态码**: {sample['response_status']}")
    lines.append(f"")
    
    # 响应体（截断）
    if sample.get("response_body"):
        resp = sample["response_body"]
        lines.append("```json")
        try:
            parsed = json.loads(resp)
            formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
            if len(formatted) > 3000:
                formatted = formatted[:3000] + "\n...[TRUNCATED]"
            lines.append(formatted)
        except:
            if len(resp) > 3000:
                resp = resp[:3000] + "\n...[TRUNCATED]"
            lines.append(resp)
        lines.append("```")
    lines.append("")
    
    # 参数分析
    lines.append(f"### 参数分析")
    lines.append(f"")
    
    # 从 datas header 提取签名参数
    datas_header = sample["request_headers"].get("datas", "")
    if datas_header:
        try:
            datas = json.loads(datas_header)
            lines.append("**签名参数（datas header）**:")
            lines.append("")
            lines.append("| 参数 | 示例值 | 类型推测 |")
            lines.append("|------|--------|----------|")
            for k, v in datas.items():
                val_str = str(v)[:50]
                if k in ("version", "pname", "channelCode", "os", "brand", "model", "manu", "osv"):
                    ptype = "静态"
                elif k in ("token", "userId", "session1", "session2"):
                    ptype = "会话"
                elif k in ("nonce", "timestamp", "boxId", "sign"):
                    ptype = "动态"
                else:
                    ptype = "未知"
                lines.append(f"| {k} | `{val_str}` | {ptype} |")
            lines.append("")
        except:
            pass
    
    sign_header = sample["request_headers"].get("sign", "")
    if sign_header:
        lines.append(f"**签名 (sign header)**: `{sign_header}`")
        lines.append("")
        lines.append("> ⚠️ 该接口包含动态签名，无法脱离 App 独立调用。归类为**复杂接口**，需通过回放方式采集。")
        lines.append("")

report_text = "\n".join(lines)
OUTPUT.write_text(report_text, encoding="utf-8")
print(f"Report saved to: {OUTPUT}")
print(f"Total lines: {len(lines)}")
