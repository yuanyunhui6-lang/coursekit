"""PDF 处理（电脑端，基于 PyMuPDF）。

策略：
1. 每页先尝试提取文字层（电子版讲义/作业可直接拿到准确文字，速度快、无识别错误）。
2. 文字层太短视为扫描件，渲染成 PNG 再交给 OCR。
无论走哪条路，都保留页面图片，方便复习时对照原页面。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .layout import lines_to_text
from .models import OcrLine, PageResult

TEXT_LAYER_MIN_CHARS = 30
MAX_RENDER_SIDE = 2000


def _load_fitz():
    """PyMuPDF 1.x 用 fitz，2.x 用 pymupdf；两者都兼容。"""
    try:
        import pymupdf as fitz  # type: ignore

        return fitz
    except ImportError:
        import fitz  # type: ignore

        return fitz


def page_count(pdf_path: str | Path) -> int:
    fitz = _load_fitz()

    with fitz.open(str(pdf_path)) as doc:
        return doc.page_count


def _render_page(page, dest: Path) -> str:
    fitz = _load_fitz()

    rect = page.rect
    longest = max(rect.width, rect.height, 1.0)
    zoom = min(2.0, MAX_RENDER_SIDE / longest)
    if zoom <= 0:
        zoom = 1.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    dest.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(dest))
    return str(dest)


def extract_pdf(
    pdf_path: str | Path,
    image_dir: str | Path,
    progress: Callable[[int, int], None] | None = None,
) -> list[PageResult]:
    """解析 PDF，返回每页的文字与页面图片。

    OCR 调用由调用方（service）负责注入，本模块只负责“文字层 or 待 OCR”。
    返回的 PageResult.text 为空字符串表示需要 OCR。
    """
    fitz = _load_fitz()

    pdf_path = Path(pdf_path)
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    pages: list[PageResult] = []

    with fitz.open(str(pdf_path)) as doc:
        total = doc.page_count
        for idx in range(total):
            page = doc.load_page(idx)
            png = _render_page(page, image_dir / f"page_{idx + 1:04d}.png")
            raw_text = ""
            try:
                raw_text = (page.get_text("text") or "").strip()
            except Exception:
                raw_text = ""
            need_ocr = len(raw_text) < TEXT_LAYER_MIN_CHARS
            pages.append(
                PageResult(
                    page_no=idx + 1,
                    image_path=png,
                    text="" if need_ocr else raw_text,
                    lines=[],
                )
            )
            if progress:
                progress(idx + 1, total)
    return pages


def text_lines_to_ocr_lines(text: str, page_no: int = 0) -> list[OcrLine]:
    """把 PDF 文字层按行转成 OcrLine（无坐标，用于统一切题）。"""
    lines: list[OcrLine] = []
    for raw in (text or "").splitlines():
        t = raw.strip()
        if t:
            lines.append(OcrLine(text=t, page=page_no))
    return lines


def page_text_from_lines(lines: list[OcrLine]) -> str:
    return lines_to_text(lines)
