"""创意研究 Profile — Fetcher 节点规则"""

from src.research_agent.profiles.base import FetcherRules

# 创意站不存在"介绍页指向 PDF 报告"的模式，禁用 PDF 提取分支
FETCHER_RULES = FetcherRules(
    download_indicators=(),
    landing_page_max_len=3000,  # 占位值，enable_pdf_extract=False 时不会生效
    max_content_len=40000,  # 创意文章普遍比报告短，降低截断上限减少 LLM 开销
    enable_pdf_extract=False,
)
