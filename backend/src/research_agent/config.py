"""Research Agent 硬编码常量

环境变量（TAVILY_API_KEY、RESEARCH_AGENT_TARGET_DOMAINS）在 src/config.py 中定义。
本文件仅包含不需要运行时调整的常量。
"""

# 搜索控制
MAX_ROUNDS = 3
MAX_CANDIDATES_PER_ROUND = 8
# Tavily 候选低于此数时，触发 Crawl4AI 全网补充搜索
MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK = 5

# 超时（秒）
FETCH_TIMEOUT = 30
LLM_TIMEOUT = 60

# 并发
MAX_CONCURRENT_TASKS = 3
