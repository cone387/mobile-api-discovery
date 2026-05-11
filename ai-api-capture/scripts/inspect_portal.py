"""检查 portal 接口的响应内容"""
import json
import os

captures_dir = "output/captures"

for f in sorted(os.listdir(captures_dir)):
    if not f.endswith(".json"):
        continue
    filepath = os.path.join(captures_dir, f)
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    
    url = data.get("url", "")
    if "portal/1125" in url or "portal/1131" in url or "portal/1139" in url or "portal/1231" in url:
        print(f"\n{'='*60}")
        print(f"URL: {url[:120]}")
        print(f"Method: {data['method']}")
        
        # 响应体前 500 字符
        resp_body = data.get("response_body", "")
        if resp_body:
            try:
                parsed = json.loads(resp_body)
                # 打印结构概览
                if isinstance(parsed, dict):
                    print(f"Response keys: {list(parsed.keys())}")
                    data_field = parsed.get("data") or parsed.get("result")
                    if isinstance(data_field, dict):
                        print(f"  data keys: {list(data_field.keys())[:15]}")
                        # 检查是否有列表
                        for k, v in data_field.items():
                            if isinstance(v, list) and len(v) > 0:
                                print(f"  data.{k} is list[{len(v)}], first item keys: {list(v[0].keys())[:10] if isinstance(v[0], dict) else type(v[0]).__name__}")
                                break
                    elif isinstance(data_field, list) and len(data_field) > 0:
                        print(f"  data is list[{len(data_field)}]")
                        if isinstance(data_field[0], dict):
                            print(f"  first item keys: {list(data_field[0].keys())[:10]}")
                else:
                    print(f"Response type: {type(parsed).__name__}")
            except:
                print(f"Response (raw): {resp_body[:200]}")
