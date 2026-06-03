"""Fetch 节点：下载候选来源的全文内容

HTML 通过 Crawl4AI REST API 获取 markdown，PDF 通过 requests 下载后提取文本。
当 profile 允许 pdf_extract 且 HTML 页面判断为"报告介绍页"（内容短且含下载指引）时，
尝试从页面中提取 PDF 直链并直接下载全文，以获取比摘要更完整的报告内容。
候选逐篇串行下载（Celery gevent worker，requests 被 monkey-patch 自动协作式让出）；
各 requests 调用自带超时故整体有界，单篇失败回退 snippet，不阻塞其余来源。
"""

import logging
import re
from urllib.parse import urljoin

import requests
from billiard.exceptions import SoftTimeLimitExceeded

from src.config import get_settings
from src.research_agent.config import FETCH_HTML_TIMEOUT, FETCH_PDF_TIMEOUT
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)


def fetch_node(state: ResearchState) -> dict:
    """串行逐篇下载全文，产出 documents 列表

    单篇失败回退 snippet，不阻塞其余来源。SoftTimeLimitExceeded 必须向上传播
    （见 _fetch_one），否则任务无法在 soft_time_limit 时优雅标 failed、只能硬等强杀。
    """
    selected = state.get("selected", [])
    if not selected:
        return {"documents": []}

    profile = get_profile(state.get("profile_name"))
    fetcher_cfg = profile.fetcher
    max_content_len = fetcher_cfg.max_content_len
    pdf_timeout = FETCH_PDF_TIMEOUT

    from src.research_agent.nodes.filter import _is_fetch_blocked

    def _snippet_doc(candidate: dict) -> dict | None:
        """全文缺失时回退 snippet（无 snippet 则丢弃该候选）"""
        snippet = candidate.get("snippet", "")
        if not snippet:
            return None
        return {
            "url": candidate["url"],
            "title": candidate["title"],
            "content": snippet,
            "source": candidate.get("source", ""),
            "content_type": "snippet",
            "page_count": None,
            "published_date": candidate.get("published_date", ""),
        }

    def _fetch_one(candidate: dict) -> dict | None:
        """下载单篇候选全文，返回 document（None=丢弃）；失败回退 snippet"""
        url = candidate["url"]
        content_type = candidate.get("content_type", "html")

        # Exa 搜索已返回全文，直接使用（优先级最高，不受封堵名单影响）
        prefetched = candidate.get("full_text", "").strip()
        if prefetched:
            return {
                "url": url,
                "title": candidate["title"],
                "content": prefetched[:max_content_len],
                "source": candidate.get("source", ""),
                "content_type": content_type,
                "page_count": None,
                "published_date": candidate.get("published_date", ""),
            }

        # 已知封堵域名：直接降级 snippet，省掉 Crawl4AI + httpx / PDF 下载的无谓等待
        # (filter 层已降分；HTML 页面均为 JS SPA，Crawl4AI 和 httpx 均无法渲染)
        if _is_fetch_blocked(url):
            logger.info("跳过已知封堵域名，降级 snippet: %s", url)
            return _snippet_doc(candidate)

        try:
            if content_type == "pdf":
                text = _fetch_pdf(url, timeout=pdf_timeout)
            else:
                text = _fetch_html(url)
                # profile 允许时，HTML 为介绍页时尝试从页面提取 PDF 链接下载全文
                if (
                    text
                    and fetcher_cfg.enable_pdf_extract
                    and _is_landing_page(
                        text,
                        fetcher_cfg.landing_page_max_len,
                        fetcher_cfg.download_indicators,
                    )
                ):
                    pdf_text = _extract_and_fetch_pdf(
                        text, base_url=url, timeout=pdf_timeout
                    )
                    if pdf_text:
                        logger.info("从介绍页提取到 PDF 全文: %s", url)
                        text = pdf_text
                        content_type = "pdf"
        except SoftTimeLimitExceeded:
            raise  # 软超时必须向上传播，让任务层更新 DB 状态（与 analyze 节点一致）
        except Exception:
            logger.warning("fetch 失败: %s", url, exc_info=True)
            text = None

        if text and text.strip():
            return {
                "url": url,
                "title": candidate["title"],
                "content": text[:max_content_len],
                "source": candidate.get("source", ""),
                "content_type": content_type,
                "page_count": None,
                "published_date": candidate.get("published_date", ""),
            }
        # 全文获取失败时回退到 snippet
        return _snippet_doc(candidate)

    # 串行逐篇下载：Crawl4AI 是单实例容器，重页面下并发会放大它的 500（shm 压力），
    # 串行对它最温和；各 requests 调用自带超时，整体有界。failed 项返回 None，丢弃。
    documents = []
    for candidate in selected:
        doc = _fetch_one(candidate)
        if doc is not None:
            documents.append(doc)

    logger.info(
        "fetch 节点: %d 个来源, %d 全文成功, %d 回退 snippet",
        len(selected),
        sum(1 for d in documents if d["content_type"] != "snippet"),
        sum(1 for d in documents if d["content_type"] == "snippet"),
    )
    return {"documents": documents}


_CRAWLER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
# Crawl4AI 返回内容低于此长度时视为抓取失败，降级到 httpx 直接获取
_MIN_CRAWL_CONTENT_LEN = 300


def _fetch_html(url: str) -> str | None:
    """通过 Crawl4AI REST API 获取 HTML 全文 markdown

    失败时自动重试一次；内容过短时降级到 httpx 直接 GET（适合无 JS 的静态页）。
    """
    result = _crawl4ai_fetch(url)
    if result and len(result.strip()) >= _MIN_CRAWL_CONTENT_LEN:
        return result

    # Crawl4AI 失败或内容过短：重试一次
    if result is None:
        logger.info("Crawl4AI 首次失败，重试: %s", url)
        import gevent

        gevent.sleep(2)
        result = _crawl4ai_fetch(url)
        if result and len(result.strip()) >= _MIN_CRAWL_CONTENT_LEN:
            return result

    # 仍然失败或内容过短：降级到 httpx 直接 GET（静态页兜底）
    logger.info("Crawl4AI 内容不足，降级 httpx 直接获取: %s", url)
    return _httpx_fetch(url)


def _crawl4ai_fetch(url: str) -> str | None:
    """单次 Crawl4AI 调用"""
    settings = get_settings()
    base_url = settings.CRAWL4AI_BASE_URL
    if not base_url:
        return None

    payload = {
        "urls": [url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": FETCH_HTML_TIMEOUT * 1000,
            "headers": {"User-Agent": _CRAWLER_UA},
        },
    }

    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    try:
        with requests.Session() as session:
            resp = session.post(
                f"{base_url}/crawl",
                json=payload,
                headers=headers,
                timeout=FETCH_HTML_TIMEOUT + 15,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        markdown = results[0].get("markdown", {})
        return markdown.get("fit_markdown") or markdown.get("raw_markdown", "")
    except (requests.RequestException, KeyError, ValueError):
        logger.warning("Crawl4AI 调用失败: %s", url, exc_info=True)
        return None


def _httpx_fetch(url: str) -> str | None:
    """requests 直接 GET，用于 Crawl4AI 失败时的静态页兜底

    仅对静态页有效；JS 渲染站（McKinsey、BCG 等）会超时，属预期行为。
    超时故意设短（10s），避免对必定失败的站点白白等待。
    """
    try:
        resp = requests.get(
            url,
            timeout=10,
            allow_redirects=True,
            headers={"User-Agent": _CRAWLER_UA},
        )
        resp.raise_for_status()
        # 只处理 HTML，二进制文件交给 _fetch_pdf
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type:
            return None
        # 粗提取：去掉 HTML 标签返回纯文本（简单但够用作兜底）
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text) >= _MIN_CRAWL_CONTENT_LEN else None
    except Exception:
        logger.debug(
            "requests 直接获取失败（JS站或超时，正常降级）: %s", url, exc_info=False
        )
        return None


def _is_landing_page(text: str, max_len: int, indicators: tuple[str, ...]) -> bool:
    """判断 HTML markdown 是否为报告介绍页（而非正文）"""
    if not indicators:
        return False
    if len(text) > max_len:
        return False
    text_lower = text.lower()
    return any(ind.lower() in text_lower for ind in indicators)


def _extract_and_fetch_pdf(text: str, base_url: str, timeout: int) -> str | None:
    """从页面 markdown 中提取 PDF 链接并尝试下载

    匹配两种格式：
    - [锚文本](https://example.com/report.pdf)
    - [锚文本](/relative/path/report.pdf)
    """
    # 绝对 URL
    abs_pattern = r"\[[^\]]*\]\((https?://[^\)]*\.pdf[^\)]*)\)"
    for match in re.finditer(abs_pattern, text, re.IGNORECASE):
        pdf_url = match.group(1).strip()
        result = _fetch_pdf(pdf_url, timeout=timeout)
        if result and result.strip():
            return result

    # 相对路径（拼接 base_url）
    rel_pattern = r"\[[^\]]*\]\((/[^\)]*\.pdf[^\)]*)\)"
    for match in re.finditer(rel_pattern, text, re.IGNORECASE):
        pdf_url = urljoin(base_url, match.group(1).strip())
        result = _fetch_pdf(pdf_url, timeout=timeout)
        if result and result.strip():
            return result

    return None


def _fetch_pdf(url: str, timeout: int = FETCH_PDF_TIMEOUT) -> str | None:
    """下载 PDF 并提取文本

    网络错误（DNS / 连接失败）时重试一次；4xx/5xx 不重试（主动拦截无意义）。
    """
    try:
        import pdfplumber
        from io import BytesIO
    except ImportError:
        logger.warning("pdfplumber 不可用，跳过 PDF: %s", url)
        return None

    def _download(u: str) -> bytes:
        resp = requests.get(u, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.content

    try:
        content = _download(url)
    except requests.HTTPError:
        # 4xx/5xx（如 429 限流、403 封锁）：重试无意义，直接放弃
        logger.warning("PDF 下载失败（HTTP 错误，不重试）: %s", url, exc_info=True)
        return None
    except Exception:
        # 网络层错误（DNS、连接超时等）：等待后重试一次
        logger.info("PDF 下载网络错误，重试: %s", url)
        import gevent

        gevent.sleep(2)
        try:
            content = _download(url)
        except Exception:
            logger.warning("PDF 下载/解析失败: %s", url, exc_info=True)
            return None

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            pages = []
            for page in pdf.pages[:100]:  # 最多读 100 页
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages) if pages else None
    except Exception:
        logger.warning("PDF 解析失败: %s", url, exc_info=True)
        return None
