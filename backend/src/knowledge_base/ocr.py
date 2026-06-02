"""DeepSeek-OCR via SiliconFlow — PDF 图片化页 OCR fallback

pdfplumber 只能提取文本流，对图片化表格、infographic、扫描页几乎无能为力。
本模块在 PDF 文本流稀疏时，把对应页渲染为 PNG 调用 DeepSeek-OCR
(SiliconFlow 托管，OpenAI-compatible)，得到结构化 Markdown 输出。

同步模块 — 由调用方通过 src.utils.run_cpu_bound_task 包到线程池中执行；
HTTP 调用使用 httpx.Client (同步)，阻塞的是 worker 线程而非事件循环。
"""

from __future__ import annotations

import base64
import io
import logging
import re

import httpx
import pdfplumber
import pypdfium2 as pdfium

from src.config import settings

logger = logging.getLogger(__name__)


# DeepSeek-OCR 官方推荐 prompt（详见 https://github.com/deepseek-ai/DeepSeek-OCR）
# `<image>` 是图片占位符，`<|grounding|>` 启用 layout-aware 模式（保留表格/标题结构）
_OCR_USER_PROMPT = "<image>\n<|grounding|>Convert the document to markdown."

# DeepSeek-OCR grounding 模式输出会带 layout 坐标标记，对下游 LLM 是噪声
# 形如：<|ref|>sub_title<|/ref|><|det|>[[270, 690, 488, 721]]<|/det|>
_GROUNDING_TOKEN_PATTERN = re.compile(
    r"<\|ref\|>[^<]*<\|/ref\|>\s*<\|det\|>\[\[[^\]]*\]\]<\|/det\|>",
    re.DOTALL,
)


def _strip_grounding_tokens(markdown: str) -> str:
    """剥离 DeepSeek-OCR grounding 坐标标记，保留正文 Markdown 内容"""
    cleaned = _GROUNDING_TOKEN_PATTERN.sub("", markdown)
    # 清理由删除标记产生的连续空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _render_page_to_png(
    pdf_doc: pdfium.PdfDocument, page_index: int, scale: float
) -> bytes:
    """渲染 PDF 单页为 PNG 字节"""
    page = pdf_doc[page_index]
    bitmap = page.render(scale=scale)
    pil_image = bitmap.to_pil()
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _ocr_image_via_siliconflow(image_bytes: bytes, *, timeout: float) -> str:
    """调用 DeepSeek-OCR 转写图片为 Markdown

    返回提取出的 Markdown 文本；调用失败抛 RuntimeError（由上层捕获降级）。
    """
    api_key = settings.OCR_API_KEY or settings.EMBEDDING_API_KEY
    if not api_key:
        raise RuntimeError(
            "OCR_API_KEY / EMBEDDING_API_KEY 未配置，无法调用 DeepSeek-OCR"
        )

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": settings.OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                    {"type": "text", "text": _OCR_USER_PROMPT},
                ],
            }
        ],
        "stream": False,
        "temperature": 0.0,  # 关闭采样：避免模型偏离图片内容生成幻觉文本
        "max_tokens": settings.OCR_MAX_OUTPUT_TOKENS,
    }

    url = f"{settings.OCR_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 限免模型服务波动较大，超时/网络错误重试 N 次（不重试 4xx 客户端错误）
    last_exc: Exception | None = None
    for attempt in range(settings.OCR_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            break
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < settings.OCR_MAX_RETRIES:
                logger.warning(
                    "DeepSeek-OCR 调用超时/网络错误（第 %d 次），即将重试: %s",
                    attempt + 1,
                    exc,
                )
                continue
            raise RuntimeError(
                f"DeepSeek-OCR 重试 {settings.OCR_MAX_RETRIES} 次后仍失败: {exc}"
            ) from last_exc

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"DeepSeek-OCR 返回缺少 choices 字段: {data}")

    content = choices[0].get("message", {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("DeepSeek-OCR 返回空内容")

    usage = data.get("usage") or {}
    if usage:
        logger.info(
            "DeepSeek-OCR tokens: prompt=%s completion=%s total=%s",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )

    return _strip_grounding_tokens(content)


def _select_weak_pages(page_texts: list[str]) -> list[int]:
    """决定哪些页需要走 OCR

    判定规则：
    - 全文字符数低于 OCR_FALLBACK_FULL_DOC_THRESHOLD → 整篇走 OCR（短文档图片化概率高）
    - 否则单页字符数低于 OCR_FALLBACK_THRESHOLD → 该页走 OCR
    """
    total_chars = sum(len(t) for t in page_texts)

    if total_chars < settings.OCR_FALLBACK_FULL_DOC_THRESHOLD:
        logger.info(
            "PDF 全文字符数 %d < %d，整篇走 OCR (%d 页)",
            total_chars,
            settings.OCR_FALLBACK_FULL_DOC_THRESHOLD,
            len(page_texts),
        )
        return list(range(len(page_texts)))

    weak = [
        i
        for i, t in enumerate(page_texts)
        if len(t.strip()) < settings.OCR_FALLBACK_THRESHOLD
    ]
    if weak:
        logger.info(
            "PDF %d/%d 页字符稀疏（< %d），走 OCR fallback: pages=%s",
            len(weak),
            len(page_texts),
            settings.OCR_FALLBACK_THRESHOLD,
            [i + 1 for i in weak],
        )
    return weak


def extract_pdf_with_ocr_fallback(file_bytes: bytes) -> str:
    """提取 PDF 文本：pdfplumber 直出 + 字符稀疏页 fallback DeepSeek-OCR

    OCR 调用失败时优雅降级到 pdfplumber 原始文本（可能为空字符串），
    不阻塞主流程。
    """
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]

    if not page_texts:
        return ""

    weak_indices = _select_weak_pages(page_texts)
    if not weak_indices:
        return "\n".join(page_texts)

    pdf_doc = pdfium.PdfDocument(file_bytes)
    ocr_failures = 0
    try:
        for i in weak_indices:
            try:
                image_bytes = _render_page_to_png(pdf_doc, i, settings.OCR_RENDER_SCALE)
                markdown = _ocr_image_via_siliconflow(
                    image_bytes,
                    timeout=settings.OCR_TIMEOUT_SECONDS,
                )
                page_texts[i] = markdown
                logger.debug("OCR page %d 完成，输出 %d 字符", i + 1, len(markdown))
            except Exception as exc:
                ocr_failures += 1
                logger.warning(
                    "OCR page %d 失败，降级使用 pdfplumber 原始文本: %s",
                    i + 1,
                    exc,
                )
    finally:
        pdf_doc.close()

    final_text = "\n".join(page_texts)
    logger.info(
        "PDF 提取完成: %d 页, OCR=%d, OCR失败=%d, 总字符=%d",
        len(page_texts),
        len(weak_indices),
        ocr_failures,
        len(final_text),
    )
    return final_text
