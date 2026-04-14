"""Research Agent 硬编码常量

环境变量（TAVILY_API_KEY、RESEARCH_AGENT_TARGET_DOMAINS）在 src/config.py 中定义。
RESEARCH_AGENT_TARGET_DOMAINS 仅包含通用兜底域名（政府统计、国际数据平台、广域媒体），
垂直领域域名由 Planner LLM 根据研究主题从 profiles.py 的候选列表中按需选择。
本文件仅包含不需要运行时调整的常量。
"""

# 搜索控制
MAX_ROUNDS = 4
MAX_CANDIDATES_PER_ROUND = 15
# Tavily 候选低于此数时，触发 Crawl4AI 全网补充搜索
MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK = 5

# 超时（秒）
FETCH_HTML_TIMEOUT = 45  # HTML 抓取（Crawl4AI + httpx 渲染）
FETCH_PDF_TIMEOUT = 120  # PDF 下载：文件通常 5-20MB，网络慢时 45s 不够

# 并发
MAX_CONCURRENT_TASKS = 10
