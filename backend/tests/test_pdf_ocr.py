"""PDF OCR fallback orchestration tests

测试 src/knowledge_base/ocr.py 中的稀疏页判定和 fallback 编排逻辑。
不打真实 OCR API — 通过 monkeypatch 隔离 HTTP 调用与 PDF 渲染。
"""

from unittest.mock import MagicMock, patch

import pytest

from src.knowledge_base import ocr


def _mock_pdfplumber(page_texts: list[str]):
    """构造 pdfplumber.open() 上下文管理器的 mock，返回指定的 page texts"""
    pdf_mock = MagicMock()
    pdf_mock.pages = [MagicMock(extract_text=lambda t=t: t) for t in page_texts]
    pdf_mock.__enter__ = MagicMock(return_value=pdf_mock)
    pdf_mock.__exit__ = MagicMock(return_value=False)
    return pdf_mock


def _mock_pdfium_doc():
    """构造 pypdfium2.PdfDocument 的 mock，渲染调用永远成功（实际渲染由 _render_page_to_png 负责）"""
    doc = MagicMock()
    doc.close = MagicMock()
    return doc


def test_select_weak_pages_no_weak(monkeypatch):
    """全部页面都有充足文本 → 无稀疏页"""
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_THRESHOLD", 80)
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_FULL_DOC_THRESHOLD", 500)

    page_texts = ["x" * 200, "y" * 300, "z" * 400]
    assert ocr._select_weak_pages(page_texts) == []


def test_select_weak_pages_partial_weak(monkeypatch):
    """部分页面稀疏 → 仅这些页索引返回"""
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_THRESHOLD", 80)
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_FULL_DOC_THRESHOLD", 500)

    page_texts = ["x" * 200, "y" * 10, "z" * 300, ""]
    assert ocr._select_weak_pages(page_texts) == [1, 3]


def test_select_weak_pages_full_doc_below_threshold(monkeypatch):
    """全文极短 → 整篇走 OCR"""
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_THRESHOLD", 80)
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_FULL_DOC_THRESHOLD", 500)

    page_texts = ["x" * 100, "y" * 100, "z" * 100]  # total=300 < 500
    assert ocr._select_weak_pages(page_texts) == [0, 1, 2]


def test_extract_pure_text_pdf_skips_ocr(monkeypatch):
    """纯文本 PDF → OCR 不应被调用"""
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_THRESHOLD", 80)
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_FULL_DOC_THRESHOLD", 500)

    page_texts = ["a" * 200, "b" * 300]
    pdf_mock = _mock_pdfplumber(page_texts)

    ocr_call = MagicMock(side_effect=AssertionError("OCR should not be called"))

    with patch.object(ocr.pdfplumber, "open", return_value=pdf_mock), \
         patch.object(ocr, "_ocr_image_via_siliconflow", ocr_call):
        result = ocr.extract_pdf_with_ocr_fallback(b"fake-pdf-bytes")

    ocr_call.assert_not_called()
    assert "a" * 200 in result
    assert "b" * 300 in result


def test_extract_sparse_pages_triggers_ocr(monkeypatch):
    """稀疏页触发 OCR，输出替换为 OCR 结果"""
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_THRESHOLD", 80)
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_FULL_DOC_THRESHOLD", 500)
    monkeypatch.setattr(ocr.settings, "OCR_RENDER_SCALE", 2.0)
    monkeypatch.setattr(ocr.settings, "OCR_TIMEOUT_SECONDS", 60.0)

    # page 0 充足，page 1 稀疏，page 2 充足
    page_texts = ["x" * 200, "", "y" * 300]
    pdf_mock = _mock_pdfplumber(page_texts)

    ocr_call = MagicMock(return_value="## OCR Markdown for page 1\n| col | col |\n|---|---|\n| a | b |")
    render_call = MagicMock(return_value=b"png-bytes")
    pdf_doc_mock = _mock_pdfium_doc()

    with patch.object(ocr.pdfplumber, "open", return_value=pdf_mock), \
         patch.object(ocr.pdfium, "PdfDocument", return_value=pdf_doc_mock), \
         patch.object(ocr, "_render_page_to_png", render_call), \
         patch.object(ocr, "_ocr_image_via_siliconflow", ocr_call):
        result = ocr.extract_pdf_with_ocr_fallback(b"fake-pdf-bytes")

    ocr_call.assert_called_once()
    render_call.assert_called_once_with(pdf_doc_mock, 1, 2.0)
    assert "## OCR Markdown for page 1" in result
    assert "x" * 200 in result
    assert "y" * 300 in result
    pdf_doc_mock.close.assert_called_once()


def test_extract_ocr_failure_falls_back_to_pdfplumber(monkeypatch):
    """OCR 调用失败 → 优雅降级到 pdfplumber 原始文本，不抛异常"""
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_THRESHOLD", 80)
    monkeypatch.setattr(ocr.settings, "OCR_FALLBACK_FULL_DOC_THRESHOLD", 500)
    monkeypatch.setattr(ocr.settings, "OCR_RENDER_SCALE", 2.0)
    monkeypatch.setattr(ocr.settings, "OCR_TIMEOUT_SECONDS", 60.0)

    page_texts = ["x" * 200, "weak", "y" * 300]  # page 1 sparse
    pdf_mock = _mock_pdfplumber(page_texts)

    ocr_call = MagicMock(side_effect=RuntimeError("API down"))
    render_call = MagicMock(return_value=b"png-bytes")
    pdf_doc_mock = _mock_pdfium_doc()

    with patch.object(ocr.pdfplumber, "open", return_value=pdf_mock), \
         patch.object(ocr.pdfium, "PdfDocument", return_value=pdf_doc_mock), \
         patch.object(ocr, "_render_page_to_png", render_call), \
         patch.object(ocr, "_ocr_image_via_siliconflow", ocr_call):
        result = ocr.extract_pdf_with_ocr_fallback(b"fake-pdf-bytes")

    ocr_call.assert_called_once()
    # 降级后保留原始 "weak" 文本，不抛异常
    assert "weak" in result
    assert "x" * 200 in result
    assert "y" * 300 in result
    pdf_doc_mock.close.assert_called_once()


def test_extract_empty_pdf_returns_empty(monkeypatch):
    """空 PDF（无页面）→ 返回空字符串，不调用 OCR"""
    pdf_mock = _mock_pdfplumber([])
    ocr_call = MagicMock(side_effect=AssertionError("OCR should not be called"))

    with patch.object(ocr.pdfplumber, "open", return_value=pdf_mock), \
         patch.object(ocr, "_ocr_image_via_siliconflow", ocr_call):
        result = ocr.extract_pdf_with_ocr_fallback(b"fake-pdf-bytes")

    assert result == ""
    ocr_call.assert_not_called()


def test_strip_grounding_tokens_removes_coords_keeps_content():
    """DeepSeek-OCR grounding 模式输出的 <|ref|>...<|det|>...<|/det|> 坐标标记应被剥离"""
    raw = (
        "<|ref|>sub_title<|/ref|><|det|>[[270, 690, 488, 721]]<|/det|>\n"
        "## HOW & WHAT TO PURCHASE?\n\n"
        "<|ref|>table<|/ref|><|det|>[[260, 740, 625, 963]]<|/det|>\n"
        "| 价值观 | TGI |\n|---|---|\n| 信任素人口碑 | 197 |\n"
    )
    cleaned = ocr._strip_grounding_tokens(raw)

    assert "<|ref|>" not in cleaned
    assert "<|det|>" not in cleaned
    assert "## HOW & WHAT TO PURCHASE?" in cleaned
    assert "信任素人口碑" in cleaned
    assert "197" in cleaned


def test_strip_grounding_tokens_collapses_excess_blank_lines():
    """剥离标记后产生的连续空行应被压缩为最多一个空行"""
    raw = (
        "<|ref|>x<|/ref|><|det|>[[1,2,3,4]]<|/det|>\n\n\n\n"
        "正文 A\n\n\n\n正文 B"
    )
    cleaned = ocr._strip_grounding_tokens(raw)

    assert "\n\n\n" not in cleaned
    assert "正文 A" in cleaned
    assert "正文 B" in cleaned


@pytest.mark.parametrize("missing_key_attr", ["OCR_API_KEY", "EMBEDDING_API_KEY"])
def test_ocr_requires_api_key(monkeypatch, missing_key_attr):
    """两个 API key 都缺失时显式报错（不静默返回空字符串）"""
    monkeypatch.setattr(ocr.settings, "OCR_API_KEY", None)
    monkeypatch.setattr(ocr.settings, "EMBEDDING_API_KEY", None)

    with pytest.raises(RuntimeError, match="未配置"):
        ocr._ocr_image_via_siliconflow(b"png-bytes", timeout=10.0)
