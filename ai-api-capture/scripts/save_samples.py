"""保存业务接口的 samples 文件（用有意义的文件名）"""
import json
import os
from urllib.parse import urlparse

captures_dir = "output/captures"
samples_dir = "output/analysis/samples"
os.makedirs(samples_dir, exist_ok=True)

# 只保留 freevideo.zqqds.cn 的业务接口
business_domain = "freevideo.zqqds.cn"

# 按 endpoint 分组，每个 endpoint 只保存第一个请求
saved_endpoints = {}

for f in sorted(os.listdir(captures_dir)):
    if not f.endswith(".json"):
        continue
    filepath = os.path.join(captures_dir, f)
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    
    if not isinstance(data, dict):
        continue
    
    url = data.get("url", "")
    if business_domain not in url:
        continue
    
    parsed = urlparse(url)
    path = parsed.path
    
    # 生成有意义的文件名：portal_1125, portal_1131 等
    path_parts = [p for p in path.split("/") if p]
    if len(path_parts) >= 2:
        filename_base = f"{path_parts[-2]}_{path_parts[-1]}"
    else:
        filename_base = path_parts[-1] if path_parts else "unknown"
    
    # 如果已保存过这个 endpoint，加序号
    if filename_base in saved_endpoints:
        saved_endpoints[filename_base] += 1
        filename_base = f"{filename_base}_{saved_endpoints[filename_base]}"
    else:
        saved_endpoints[filename_base] = 0
    
    # 保存 request
    request_data = {
        "method": data.get("method"),
        "url": data.get("url"),
        "headers": data.get("headers", {}),
        "body": data.get("body"),
    }
    req_path = os.path.join(samples_dir, f"{filename_base}_request.json")
    with open(req_path, "w", encoding="utf-8") as fh:
        json.dump(request_data, ensure_ascii=False, indent=2, fp=fh)
    
    # 保存 response
    response_data = {
        "status": data.get("response_status"),
        "headers": data.get("response_headers", {}),
        "body": data.get("response_body"),
    }
    resp_path = os.path.join(samples_dir, f"{filename_base}_response.json")
    with open(resp_path, "w", encoding="utf-8") as fh:
        json.dump(response_data, ensure_ascii=False, indent=2, fp=fh)
    
    print(f"  ✅ {filename_base} ({data.get('method')} {path})")

print(f"\n共保存 {sum(v+1 for v in saved_endpoints.values())} 个接口的 samples")
