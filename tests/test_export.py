"""导出功能单元测试：Markdown / 文本 / Word。"""
import io
import zipfile
import xml.etree.ElementTree as ET

from core.export import build, build_docx, build_markdown, build_text, safe_filename

DOC = {
    "title": "高数第三章",
    "subject": "高等数学",
    "tags": ["期中", "重点"],
    "created_at": "2026-11-10 21:30:00",
    "page_count": 1,
    "note": "复习用",
    "questions": [
        {"number": "1", "text": "求 y=x^2 的导数", "answer": "y'=2x"},
        {"number": "2", "text": "计算 1+1", "answer": ""},
    ],
    "pages": [{"page_no": 1, "text": "1. 求 y=x^2 的导数\n2. 计算 1+1 <特殊&字符>"}],
}


def test_markdown_content():
    md = build_markdown(DOC)
    assert "# 高数第三章" in md
    assert "科目：高等数学" in md
    assert "标签：期中、重点" in md
    assert "### 1" in md
    assert "y'=2x" in md
    assert "全文" in md


def test_text_content():
    text = build_text(DOC)
    assert "高数第三章" in text
    assert "求 y=x^2 的导数" in text
    assert "【题目】" in text


def test_docx_is_valid_zip():
    data = build_docx(DOC)
    assert data[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "word/document.xml" in names
        assert "[Content_Types].xml" in names
        assert "word/styles.xml" in names
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    texts = [t.text or "" for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")]
    joined = "".join(texts)
    assert "高数第三章" in joined
    assert "求 y=x^2 的导数" in joined
    # XML 特殊字符必须被转义后仍可解析
    assert "特殊&字符" in joined


def test_build_dispatch_and_filename():
    name, data = build(DOC, "md")
    assert name.endswith(".md")
    assert data.startswith(b"# ")
    name2, data2 = build(DOC, "docx")
    assert name2.endswith(".docx") and data2[:2] == b"PK"
    try:
        build(DOC, "exe")
    except ValueError:
        pass
    else:
        raise AssertionError("不支持的格式应抛 ValueError")


def test_safe_filename_strips_illegal_chars():
    name = safe_filename('高数/第三章: "导数"', "md")
    for ch in '\\/:*?"<>|':
        assert ch not in name
    assert name.endswith(".md")
