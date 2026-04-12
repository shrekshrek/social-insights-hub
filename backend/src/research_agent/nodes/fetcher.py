"""Fetch 节点：下载候选来源的全文内容

HTML 通过 Crawl4AI REST API 获取 markdown，PDF 通过 httpx 下载后提取文本。
同步调用（gevent 兼容），per-document 30s 超时，失败不阻塞。
"""

import logging

import httpx

from src.config import get_settings
from src.research_agent.config import FETCH_TIMEOUT
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)


def fetch_node(state: ResearchState) -> dict:
    """并行下载全文，产出 documents 列表"""
    selected = state.get("selected", [])
    if not selected:
        return {"documents": []}

    profile = get_profile(state.get("research_type"))
    is_report = profile.content_strategy == "report"
    # report 策略：允许更长内容截断，充分利用报告全文
    max_content_len = 60000 if is_report else 30000
    pdf_timeout = FETCH_TIMEOUT * 2 if is_report else FETCH_TIMEOUT

    documents = []
    for candidate in selected:
        url = candidate["url"]
        content_type = candidate.get("content_type", "html")

        try:
            if content_type == "pdf":
                text = _fetch_pdf(url, timeout=pdf_timeout)
            else:
                text = _fetch_html(url)
        except Exception:
            logger.warning("fetch 失败: %s", url, exc_info=True)
            text = None

        if text and text.strip():
            documents.append({
                "url": url,
                "title": candidate["title"],
                "content": text[:max_content_len],
                "source": candidate.get("source", ""),
                "content_type": content_type,
                "page_count": None,
            })
        else:
            # 全文获取失败时回退到 snippet
            snippet = candidate.get("snippet", "")
            if snippet:
                documents.append({
                    "url": url,
                    "title": candidate["title"],
                    "content": snippet,
                    "source": candidate.get("source", ""),
                    "content_type": "snippet",
                    "page_count": None,
                })

    logger.info(
        "fetch 节点: %d 个来源, %d 全文成功, %d 回退 snippet",
        len(selected),
        sum(1 for d in documents if d["content_type"] != "snippet"),
        sum(1 for d in documents if d["content_type"] == "snippet"),
    )
    return {"documents": documents}


def _fetch_html(url: str) -> str | None:
    """通过 Crawl4AI REST API 获取 HTML 全文 markdown"""
    settings = get_settings()
    base_url = settings.CRAWL4AI_BASE_URL
    if not base_url:
        return None

    payload = {
        "urls": [url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": FETCH_TIMEOUT * 1000,
        },
    }

    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    try:
        with httpx.Client(timeout=FETCH_TIMEOUT + 10) as client:
            resp = client.post(
                f"{base_url}/crawl",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        markdown = results[0].get("markdown", {})
        return markdown.get("fit_markdown") or markdown.get("raw_markdown", "")
    except (httpx.HTTPError, KeyError, ValueError):
        logger.warning("Crawl4AI 失败: %s", url, exc_info=True)
        return None


def _fetch_pdf(url: str, timeout: int = FETCH_TIMEOUT) -> str | None:
    """下载 PDF 并提取文本"""
    try:
        import pdfplumber
        from io import BytesIO
    except ImportError:
        logger.warning("pdfplumber 不可用，跳过 PDF: %s", url)
        return None

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()

        with pdfplumber.open(BytesIO(resp.content)) as pdf:
            pages = []
            for page in pdf.pages[:100]:  # 最多读 100 页
                text = page.extract_text()
                if text:
                    pages.append(text)

            return "\n\n".join(pages) if pages else None
    except Exception:
        logger.warning("PDF 下载/解析失败: %s", url, exc_info=True)
        return None
