"""行业研究 Profile — Fetcher 节点规则"""

from src.research_agent.profiles.base import FetcherRules

# 介绍页判断：HTML 内容含有这些词时尝试提取 PDF 链接
DOWNLOAD_INDICATORS = (
    "下载报告", "下载完整报告", "下载全文", "下载 PDF", "点击下载", "立即下载",
    "获取报告", "查看全文", "阅读全文",
    "download report", "download pdf", "full report", "get the report",
    "download the full", "access the report",
)


FETCHER_RULES = FetcherRules(
    download_indicators=DOWNLOAD_INDICATORS,
    landing_page_max_len=3000,
    max_content_len=60000,
    enable_pdf_extract=True,
)
