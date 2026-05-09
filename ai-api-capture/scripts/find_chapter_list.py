"""查找包含剧集列表的接口"""
import json
from pathlib import Path

data = json.load(Path(r"ai-api-capture/output/captures/hema_captured.json").open("r", encoding="utf-8"))

# 搜索所有响应中包含 chapterList 或 chapterIndex 数组的接口
for d in data:
    url = d.get("url", "")
    if "freevideo" not in url:
        continue
    resp = d.get("response_body", "")
    if not resp:
        continue
    
    # 找包含剧集列表的响应
    if "chapterList" in resp or "chapterIndex" in resp:
        try:
            parsed = json.loads(resp)
            resp_data = parsed.get("data", {})
            
            # 检查是否有 chapterList
            if isinstance(resp_data, dict):
                for key in resp_data:
                    val = resp_data[key]
                    if isinstance(val, dict) and "chapterList" in str(val)[:100]:
                        print(f"\nURL: {url}")
                        print(f"  Key: {key}")
                        # 找到 chapterList
                        def find_chapter_list(obj, path=""):
                            if isinstance(obj, dict):
                                if "chapterList" in obj:
                                    cl = obj["chapterList"]
                                    if isinstance(cl, list) and len(cl) > 0:
                                        print(f"  Found chapterList at {path}.chapterList ({len(cl)} items)")
                                        print(f"  First item keys: {list(cl[0].keys()) if cl else 'empty'}")
                                        print(f"  Sample: {json.dumps(cl[0], ensure_ascii=False)[:200]}")
                                for k, v in obj.items():
                                    find_chapter_list(v, f"{path}.{k}")
                            elif isinstance(obj, list):
                                for i, item in enumerate(obj[:2]):
                                    find_chapter_list(item, f"{path}[{i}]")
                        find_chapter_list(resp_data)
                        break
                        
                # 也检查 unLockConfigs 等可能包含章节信息的字段
                if "unLockConfigs" in resp_data or "chapterList" in str(resp_data)[:5000]:
                    path = url.split("freevideo")[1].split("?")[0] if "freevideo" in url else url
                    
                    # 直接搜索 chapterList
                    def deep_find(obj, target_key, path="root"):
                        results = []
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if k == target_key and isinstance(v, list):
                                    results.append((f"{path}.{k}", v))
                                results.extend(deep_find(v, target_key, f"{path}.{k}"))
                        elif isinstance(obj, list):
                            for i, item in enumerate(obj[:3]):
                                results.extend(deep_find(item, target_key, f"{path}[{i}]"))
                        return results
                    
                    found = deep_find(resp_data, "chapterList")
                    if found:
                        print(f"\nURL: {url}")
                        for fpath, fval in found:
                            print(f"  chapterList at: {fpath} ({len(fval)} items)")
                            if fval:
                                print(f"  Keys: {list(fval[0].keys())}")
                                print(f"  Sample: {json.dumps(fval[0], ensure_ascii=False)[:300]}")
        except:
            pass

# 也搜索 1139 接口（之前分析显示它有 maxChapter 等字段）
print("\n\n=== portal/1139 responses ===")
for d in data:
    url = d.get("url", "")
    if "portal/1139" not in url:
        continue
    resp = d.get("response_body", "")
    if resp:
        try:
            parsed = json.loads(resp)
            resp_data = parsed.get("data", {})
            print(f"\nURL: {url}")
            print(f"  Data keys: {list(resp_data.keys()) if isinstance(resp_data, dict) else 'not dict'}")
            if isinstance(resp_data, dict) and "chapterList" in resp_data:
                cl = resp_data["chapterList"]
                print(f"  chapterList: {len(cl)} items")
                if cl:
                    print(f"  First: {json.dumps(cl[0], ensure_ascii=False)[:300]}")
        except:
            pass
