"""运行接口分析 - 读取 captures 目录的 JSON 文件，生成分析报告

使用用户域名白名单只关注业务域名，排除广告 SDK。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api_analyzer import APIAnalyzer
from src.report_generator import ReportGenerator
from src.traffic_interceptor import TrafficInterceptor
from src.models import CaptureTarget, FilterRules

# 配置
storage_path = "./output/captures"
output_dir = "./output/analysis"

# 创建目标
target = CaptureTarget(
    app_name="河马漫剧",
    target_data="漫剧首页列表、分页加载、详情页剧集列表、单集详情",
    operation_pages="首页、详情页",
    filter_domains=["freevideo.zqqds.cn"],
)

# 使用用户域名白名单只保留业务域名
filter_rules = FilterRules(
    user_domain_whitelist=["freevideo.zqqds.cn"],
)

# 读取并过滤
interceptor = TrafficInterceptor(storage_path=storage_path, filter_rules=filter_rules)
all_requests = interceptor.get_captured_requests()

print(f"过滤后有效请求数: {len(all_requests)}")
for req in all_requests:
    print(f"  [{req.method}] {req.url[:80]}")

if len(all_requests) == 0:
    print("没有有效请求，请检查 captures 目录")
    sys.exit(1)

# 分析
analyzer = APIAnalyzer()
report = analyzer.analyze_all(all_requests, target)

# 生成报告
os.makedirs(output_dir, exist_ok=True)
generator = ReportGenerator()
report_path = generator.generate(report, output_dir)

# 保存样本
samples_dir = os.path.join(output_dir, "samples")
generator.save_samples(all_requests, report.results, samples_dir)

print(f"\n{'='*60}")
print(f"分析完成！")
print(f"- 总捕获请求数: {report.total_captured}")
print(f"- 分析接口数: {report.total_analyzed}")
print(f"- 匹配目标接口数: {report.target_matched}")
print(f"- 报告路径: {report_path}")
print(f"{'='*60}")

# 打印接口概览
print(f"\n接口概览 ({report.total_analyzed} 个)：")
for result in report.results:
    match_icon = "✅" if result.matches_target else "  "
    sig_icon = "🔒" if result.has_signature else "  "
    print(f"  {match_icon} {sig_icon} [{result.api_type.value:10}] {result.endpoint} (x{result.call_count})")

if report.data_links:
    print(f"\n数据链路：")
    for link in report.data_links:
        print(f"  {link.source_endpoint} --[{link.link_field}]--> {link.target_endpoint}")
