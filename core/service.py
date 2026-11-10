"""业务门面：UI 只跟 Service 打交道。

职责：
- 图片 / PDF 导入（OCR → 全文 → 切题 → 入库）
- 删除、重新切题、导出
- 进度回调（UI 在工作线程调用，回调里需自行切回主线程）
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from . import export as export_mod
from . import imagetools, ocr, paths, pdf as pdf_mod, split
from .db import Database
from .layout import lines_to_text
from .models import OcrLine, PageResult

ProgressFn = Callable[[int, int, str], None]
"""progress(done, total, message)：done/total 为步骤数，message 为中文状态。"""


def _mime_of(fmt: str) -> str:
    return {
        "md": "text/markdown",
        "markdown": "text/markdown",
        "txt": "text/plain",
        "text": "text/plain",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get((fmt or "").lower(), "application/octet-stream")


class Service:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else paths.data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_root = self.data_dir / "images"
        self.images_root.mkdir(parents=True, exist_ok=True)
        self.exports_root = self.data_dir / "exports"
        self.exports_root.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "coursekit.db")

    # ------------------------------------------------------------------ 导入
    @staticmethod
    def _new_doc_id() -> str:
        return datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]

    def _default_title(self, path: Path, is_photo: bool) -> str:
        stem = path.stem.strip()
        if stem and not stem.lower().startswith(("image", "img_", "screenshot", "微信图片", "mmexport")):
            return stem[:60]
        prefix = "拍照" if is_photo else "课件"
        return f"{prefix} {datetime.now():%Y-%m-%d %H:%M}"

    def import_file(
        self,
        file_path: str | Path,
        subject: str = "",
        tags: Iterable[str] | None = None,
        title: str = "",
        is_photo: bool = False,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        """导入单个图片或 PDF，返回导入结果摘要。"""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"文件不存在：{p}")
        if imagetools.image_is_pdf(p):
            return self.import_pdf(p, subject=subject, tags=tags, title=title, progress=progress)
        return self.import_image(
            p, subject=subject, tags=tags, title=title, is_photo=is_photo, progress=progress
        )

    def _image_page(
        self, src: Path, doc_dir: Path, page_no: int = 1
    ) -> tuple[dict[str, Any], list[OcrLine]]:
        """规范化并 OCR 一张图片，返回 (页面记录, 行列表)。"""
        target = doc_dir / f"page_{page_no:04d}.jpg"
        try:
            from PIL import Image  # noqa: F401  # 有 PIL 时统一转 JPEG + 缩放

            ocr_source = imagetools.normalize_image(src, target)
            image_path = target
        except Exception:
            # 安卓端未安装 Pillow：直接复制原文件，ML Kit 可自行处理方向和尺寸
            suffix = (src.suffix or ".jpg").lower()
            image_path = doc_dir / f"page_{page_no:04d}{suffix}"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, image_path)
            ocr_source = str(image_path)

        lines = ocr.recognize_lines(ocr_source)
        page = {
            "page_no": page_no,
            "image_path": str(image_path),
            "text": lines_to_text(lines),
            "lines_json": json.dumps([ln.to_dict() for ln in lines], ensure_ascii=False),
        }
        return page, lines

    def import_image(
        self,
        file_path: str | Path,
        subject: str = "",
        tags: Iterable[str] | None = None,
        title: str = "",
        is_photo: bool = False,
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        src = Path(file_path)
        doc_id = self._new_doc_id()
        doc_dir = self.images_root / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        if progress:
            progress(0, 2, "正在识别图片文字…")
        try:
            page, _lines = self._image_page(src, doc_dir, page_no=1)
        except Exception:
            shutil.rmtree(doc_dir, ignore_errors=True)
            raise
        if progress:
            progress(1, 2, "正在切分题目…")

        pages = [page]
        blocks = split.split_document_pages(pages)
        questions = split.questions_to_dicts(blocks)
        full_text = page["text"]
        doc_title = title.strip() or self._default_title(src, bool(is_photo))
        self.db.add_document(
            doc_id=doc_id,
            title=doc_title,
            doc_type="image",
            subject=(subject or "").strip(),
            source_name=src.name,
            pages=pages,
            questions=questions,
            tags=list(tags or []),
            full_text=full_text,
        )
        if progress:
            progress(2, 2, "完成")
        return self._summary(doc_id, doc_title, 1, len(questions))

    def import_pdf(
        self,
        file_path: str | Path,
        subject: str = "",
        tags: Iterable[str] | None = None,
        title: str = "",
        progress: ProgressFn | None = None,
    ) -> dict[str, Any]:
        src = Path(file_path)
        doc_id = self._new_doc_id()
        doc_dir = self.images_root / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        try:
            if paths.is_android():
                pages = self._extract_pdf_android(src, doc_dir, progress)
            else:
                pages = self._extract_pdf_desktop(src, doc_dir, progress)
        except Exception:
            shutil.rmtree(doc_dir, ignore_errors=True)
            raise

        if not pages:
            shutil.rmtree(doc_dir, ignore_errors=True)
            raise RuntimeError("PDF 没有可用页面（可能文件损坏或加密）")

        if progress:
            progress(1, 1, "正在切分题目…")
        blocks = split.split_document_pages(pages)
        questions = split.questions_to_dicts(blocks)
        full_text = "\n\n".join(p.get("text", "") for p in pages if p.get("text"))
        doc_title = title.strip() or src.stem[:60] or "PDF 课件"
        page_dicts = [
            {
                "page_no": p["page_no"],
                "image_path": p["image_path"],
                "text": p["text"],
                "lines_json": p.get("lines_json", "[]"),
            }
            for p in pages
        ]
        self.db.add_document(
            doc_id=doc_id,
            title=doc_title,
            doc_type="pdf",
            subject=(subject or "").strip(),
            source_name=src.name,
            pages=page_dicts,
            questions=questions,
            tags=list(tags or []),
            full_text=full_text,
        )
        return self._summary(doc_id, doc_title, len(page_dicts), len(questions))

    def _page_dict(self, page_no: int, image_path: str, lines: list[OcrLine]) -> dict[str, Any]:
        return {
            "page_no": page_no,
            "image_path": image_path,
            "text": lines_to_text(lines),
            "lines_json": json.dumps([ln.to_dict() for ln in lines], ensure_ascii=False),
        }

    def _extract_pdf_desktop(
        self, src: Path, doc_dir: Path, progress: ProgressFn | None
    ) -> list[dict[str, Any]]:
        """电脑端：优先文字层，扫描页再 OCR。"""
        total_pages = max(1, pdf_mod.page_count(src))
        total_steps = total_pages * 2

        def render_progress(done: int, total: int) -> None:
            if progress:
                progress(done - 1, total_steps, f"正在渲染第 {done}/{total} 页…")

        results: list[PageResult] = pdf_mod.extract_pdf(src, doc_dir, render_progress)
        pages: list[dict[str, Any]] = []
        for idx, pr in enumerate(results):
            try:
                if pr.text:
                    lines = pdf_mod.text_lines_to_ocr_lines(pr.text, pr.page_no)
                else:
                    if progress:
                        progress(
                            total_pages + idx,
                            total_steps,
                            f"正在识别第 {idx + 1}/{len(results)} 页文字…",
                        )
                    lines = ocr.recognize_lines(pr.image_path)
                    pr.text = lines_to_text(lines)
            except Exception:
                lines = []
                pr.text = pr.text or ""
            pages.append(self._page_dict(pr.page_no, pr.image_path, lines))
        return pages

    def _extract_pdf_android(
        self, src: Path, doc_dir: Path, progress: ProgressFn | None
    ) -> list[dict[str, Any]]:
        """安卓端：PdfRenderer 渲染成图 → ML Kit 逐页 OCR。"""
        from native.android_pdf import render_pages

        if progress:
            progress(0, 1, "正在渲染 PDF 页面…")
        rendered = render_pages(str(src), str(doc_dir)) or []
        if not rendered:
            return []
        pages: list[dict[str, Any]] = []
        total = len(rendered)
        for idx, image_path in enumerate(rendered, start=1):
            if progress:
                progress(idx, total + 1, f"正在识别第 {idx}/{total} 页…")
            try:
                lines = ocr.recognize_lines(image_path)
            except Exception:
                lines = []
            pages.append(self._page_dict(idx, image_path, lines))
        return pages

    @staticmethod
    def _summary(doc_id: str, title: str, page_count: int, question_count: int) -> dict[str, Any]:
        return {
            "doc_id": doc_id,
            "title": title,
            "page_count": page_count,
            "question_count": question_count,
        }

    # ------------------------------------------------------------------ 维护
    def delete_document(self, doc_id: str) -> None:
        self.db.delete_document(doc_id)
        shutil.rmtree(self.images_root / doc_id, ignore_errors=True)

    def resplit(self, doc_id: str) -> int:
        """按当前页面文字重新切题，返回题目数量。"""
        doc = self.db.get_document(doc_id)
        if not doc:
            return 0
        pages = [
            {
                "page_no": p["page_no"],
                "text": p["text"],
                "lines_json": p.get("lines_json", "[]"),
            }
            for p in doc.get("pages", [])
        ]
        blocks = split.split_document_pages(pages)
        questions = split.questions_to_dicts(blocks)
        self.db.replace_questions(doc_id, questions)
        return len(questions)

    # ------------------------------------------------------------------ 导出
    def export(self, doc_id: str, fmt: str = "md") -> dict[str, Any]:
        """导出文档，返回 {filename, path, mime}；安卓端同时写入系统“下载”目录。"""
        doc = self.db.get_document(doc_id)
        if not doc:
            raise KeyError(f"找不到文档：{doc_id}")
        filename, data = export_mod.build(doc, fmt)
        local = self.exports_root / filename
        local.write_bytes(data)
        saved_path = ""
        if paths.is_android():
            try:
                from native.android_export import save_to_downloads

                saved_path = save_to_downloads(filename, data, _mime_of(fmt)) or ""
            except Exception:
                saved_path = ""
        return {
            "filename": filename,
            "path": saved_path or str(local),
            "local_path": str(local),
            "mime": _mime_of(fmt),
            "size": len(data),
        }

    def stats(self) -> dict[str, int]:
        return self.db.stats()

    def close(self) -> None:
        """释放数据库连接（App 退出时调用）。"""
        try:
            self.db.close()
        except Exception:
            pass
