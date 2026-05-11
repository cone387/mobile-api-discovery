"""检查 captures 目录中的文件格式"""
import json
import os

captures_dir = "output/captures"
bad = []
good = 0

for f in sorted(os.listdir(captures_dir)):
    if not f.endswith(".json"):
        continue
    filepath = os.path.join(captures_dir, f)
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or "id" not in data:
            bad.append((f, f"type={type(data).__name__}, keys={list(data.keys())[:3] if isinstance(data, dict) else 'N/A'}"))
        else:
            good += 1
    except Exception as e:
        bad.append((f, str(e)[:80]))

print(f"Total JSON files: {good + len(bad)}")
print(f"Good files: {good}")
print(f"Bad files: {len(bad)}")
for b in bad[:10]:
    print(f"  {b[0]}: {b[1]}")
