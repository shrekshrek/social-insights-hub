"""Research Agent 硬编码常量

环境变量（TAVILY_API_KEY 等）在 src/config.py 中定义。
各 profile 的兜底域名在 profiles/<name>/__init__.py 中以 `search_fallback_domains` 字段定义，
Planner LLM 会根据研究主题从 profile 的 planner_context 中按需挑选额外域名。
本文件仅包含不需要运行时调整的常量。
"""

# 搜索控制
MAX_ROUNDS = 4
MAX_CANDIDATES_PER_ROUND = 15

# 超时（秒）
FETCH_HTML_TIMEOUT = 45  # HTML 抓取（Crawl4AI + httpx 渲染）
FETCH_PDF_TIMEOUT = 120  # PDF 下载：文件通常 5-20MB，网络慢时 45s 不够

# 并发
MAX_CONCURRENT_TASKS = 10
