"""分析抓到的接口，找出真正的列表、分页、详情接口"""
import json
from pathlib import Path
from collections import defaultdict

data = json.load(Path(r"ai-api-capture/output/captures/hema_captured.json").open("r", encoding="utf-8"))

# 只看 freevideo 域名的请求
apis = [d for d in data if "freevideo" in d.get("url", "")]

print(f"Total freevideo APIs: {len(apis)}")
print()

# 按 URL 路径分组
groups = defaultdict(list)
for d in apis:
    path = d["url"].split("freevideo.zqqds.cn")[1] if "zqqds.cn" in d["url"] else d["url"].split("freevideo.dzkjk.cn")[1]
    path = path.split("?")[0]
    groups[path].append(d)

# 分析每个接口
for path, items in sorted(groups.items(), key=lambda x: -len(x[1])):
    sample = items[0]
    resp = sample.get("response_body", "")
    
    # 解析响应看数据结构
    data_keys = []
    has_list = False
    list_sample = ""
    try:
        parsed = json.loads(resp)
        d = parsed.get("data", {})
        if isinstance(d, dict):
            data_keys = list(d.keys())[:8]
            if "dataList" in d:
                has_list = True
                if d["dataList"]:
                    list_sample = json.dumps(d["dataList"][0], ensure_ascii=False)[:200]
            elif "chapterList" in d:
                has_list = True
                if d["chapterList"]:
                    list_sample = json.dumps(d["chapterList"][0], ensure_ascii=False)[:200]
    except:
        pass
    
    # 请求体
    req_body = sample.get("request_body", "") or ""
    req_keys = []
    try:
        rb = json.loads(req_body)
        if isinstance(rb, dict):
            req_keys = list(rb.keys())[:8]
    except:
        pass
    
    print(f"{'='*60}")
    print(f"PATH: {path} ({len(items)}x)")
    print(f"  Request body keys: {req_keys}")
    print(f"  Response data keys: {data_keys}")
    if has_list:
        print(f"  *** HAS LIST DATA ***")
        print(f"  List sample: {list_sample}")
    print()
