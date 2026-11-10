"""导出：Markdown / 纯文本 / Word（.docx，纯 zip 手写，无第三方依赖，安卓可用）。"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape


def _doc_meta_lines(doc: dict[str, Any]) -> list[str]:
    lines = []
    if doc.get("subject"):
        lines.append(f"科目：{doc['subject']}")
    if doc.get("tags"):
        lines.append("标签：" + "、".join(doc["tags"]))
    if doc.get("created_at"):
        lines.append(f"导入时间：{doc['created_at']}")
    if doc.get("page_count"):
        lines.append(f"页数：{doc['page_count']}")
    if doc.get("note"):
        lines.append(f"备注：{doc['note']}")
    return lines


def build_markdown(doc: dict[str, Any]) -> str:
    """生成 Markdown 复习稿。"""
    out: list[str] = [f"# {doc.get('title', '未命名')}", ""]
    meta = _doc_meta_lines(doc)
    if meta:
        out.extend(f"- {m}" for m in meta)
        out.append("")
    if doc.get("note"):
        out.extend(["> " + doc["note"], ""])

    questions = doc.get("questions") or []
    pages = doc.get("pages") or []
    if questions:
        out.extend(["## 题目", ""])
        for q in questions:
            num = q.get("number") or str(q.get("order_no", ""))
            out.append(f"### {num}")
            out.append("")
            out.append(str(q.get("text", "")).strip())
            out.append("")
            if q.get("answer"):
                out.append(f"**答案/解析：** {str(q['answer']).strip()}")
                out.append("")
        out.extend(["---", "", "## 全文", ""])
    for page in pages:
        text = str(page.get("text", "")).strip()
        if not text:
            continue
        if len(pages) > 1:
            out.extend([f"### 第 {page.get('page_no', 0)} 页", ""])
        out.extend([text, ""])
    return "\n".join(out).rstrip() + "\n"


def build_text(doc: dict[str, Any]) -> str:
    """生成纯文本复习稿。"""
    out: list[str] = [str(doc.get("title", "未命名")), "=" * 40]
    meta = _doc_meta_lines(doc)
    if meta:
        out.extend(meta)
    questions = doc.get("questions") or []
    pages = doc.get("pages") or []
    if questions:
        out.extend(["", "【题目】"])
        for q in questions:
            num = q.get("number") or str(q.get("order_no", ""))
            out.extend(["", f"{num} {str(q.get('text', '')).strip()}"])
            if q.get("answer"):
                out.append(f"答案/解析：{str(q['answer']).strip()}")
        out.extend(["", "【全文】"])
    for page in pages:
        text = str(page.get("text", "")).strip()
        if text:
            if len(pages) > 1:
                out.extend(["", f"—— 第 {page.get('page_no', 0)} 页 ——"])
            out.append(text)
    return "\n".join(out).rstrip() + "\n"


def safe_filename(title: str, ext: str) -> str:
    """把标题变成安全的文件名。"""
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", title or "课件").strip(" ._")
    name = name[:60] or "课件"
    return f"{name}_{datetime.now().strftime('%Y%m%d_%H%M')}.{ext}"


# ---------------------------------------------------------------- Word 导出
_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:eastAsia="微软雅黑" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
</w:styles>"""

_XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _run(text: str, bold: bool = False, size: int = 0) -> str:
    """一个 Word 文字 run。size 单位为半磅（22 = 11pt）。"""
    text = _XML_INVALID.sub("", str(text))
    props = ""
    if bold or size:
        props = "<w:rPr>"
        if bold:
            props += "<w:b/>"
        if size:
            props += f'<w:sz w:val="{int(size)}"/><w:szCs w:val="{int(size)}"/>'
        props += "</w:rPr>"
    parts = []
    for i, chunk in enumerate(text.split("\n")):
        if i:
            parts.append("<w:br/>")
        parts.append(f'<w:t xml:space="preserve">{escape(chunk)}</w:t>')
    return f'<w:r>{props}{"".join(parts)}</w:r>'


def _para(text: str = "", bold: bool = False, size: int = 0) -> str:
    return f"<w:p>{_run(text, bold=bold, size=size)}</w:p>" if text else "<w:p/>"


def build_docx(doc: dict[str, Any]) -> bytes:
    """生成 Word 文档（不依赖 python-docx，安卓端也能用）。"""
    body: list[str] = [_para(str(doc.get("title", "未命名")), bold=True, size=36)]
    for line in _doc_meta_lines(doc):
        body.append(_para(line, size=20))
    body.append(_para(""))

    questions = doc.get("questions") or []
    pages = doc.get("pages") or []
    if questions:
        body.append(_para("题目", bold=True, size=28))
        for q in questions:
            num = q.get("number") or str(q.get("order_no", ""))
            body.append(_para(f"{num} {str(q.get('text', '')).strip()}", bold=True, size=24))
            if q.get("answer"):
                body.append(_para(f"答案/解析：{str(q['answer']).strip()}", size=22))
        body.append(_para(""))
        body.append(_para("全文", bold=True, size=28))
    for page in pages:
        text = str(page.get("text", "")).strip()
        if not text:
            continue
        if len(pages) > 1:
            body.append(_para(f"第 {page.get('page_no', 0)} 页", size=20))
        for line in text.splitlines():
            body.append(_para(line))
        body.append(_para(""))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
        "</w:body></w:document>"
    )

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CT)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        zf.writestr("word/styles.xml", _STYLES)
    return buf.getvalue()


def build(doc: dict[str, Any], fmt: str) -> tuple[str, bytes]:
    """按格式生成导出文件，返回 (文件名, 字节内容)。fmt: md/txt/docx。"""
    fmt = (fmt or "md").lower().lstrip(".")
    if fmt in ("md", "markdown"):
        return safe_filename(doc.get("title", "课件"), "md"), build_markdown(doc).encode("utf-8")
    if fmt in ("txt", "text"):
        return safe_filename(doc.get("title", "课件"), "txt"), build_text(doc).encode("utf-8")
    if fmt in ("docx", "word"):
        return safe_filename(doc.get("title", "课件"), "docx"), build_docx(doc)
    raise ValueError(f"不支持的导出格式：{fmt}")
