"""Service 导入/导出流程测试（用假 OCR，不加载真实模型）。"""
import json

import pytest

import core.ocr as ocr_mod
from core.models import OcrLine
from core.service import Service


@pytest.fixture()
def fake_ocr(monkeypatch):
    def recognize(image_path):
        return [
            OcrLine(text="1. 求下列函数的导数：y=x^2+2x", x0=10, y0=10, x1=300, y1=30),
            OcrLine(text="2. 计算定积分 ∫_0^1 x^2 dx", x0=10, y0=40, x1=300, y1=60),
        ]

    monkeypatch.setattr(ocr_mod, "recognize_lines", recognize)


@pytest.fixture()
def service(tmp_path, fake_ocr):
    svc = Service(data_dir=tmp_path / "data")
    yield svc
    svc.close()


def _make_image(path):
    from PIL import Image

    img = Image.new("RGB", (400, 200), (255, 255, 255))
    img.save(path)
    return path


def test_import_image_pipeline(service, tmp_path):
    image = _make_image(tmp_path / "page.jpg")
    progress_calls = []

    result = service.import_file(
        image,
        subject="高等数学",
        tags=["期中", "重点"],
        title="第三章测验",
        progress=lambda d, t, m: progress_calls.append((d, t, m)),
    )
    assert result["doc_id"]
    assert result["question_count"] == 2
    assert progress_calls, "应当有进度回调"

    doc = service.db.get_document(result["doc_id"])
    assert doc["title"] == "第三章测验"
    assert doc["subject"] == "高等数学"
    assert set(doc["tags"]) == {"期中", "重点"}
    assert doc["page_count"] == 1
    assert "y=x^2+2x" in doc["full_text"]
    assert len(doc["questions"]) == 2
    assert doc["questions"][0]["number"] == "1"

    # 导出
    exported = service.export(result["doc_id"], "md")
    assert exported["filename"].endswith(".md")
    with open(exported["local_path"], encoding="utf-8") as fh:
        content = fh.read()
    assert "第三章测验" in content and "定积分" in content

    # 重新切题
    assert service.resplit(result["doc_id"]) == 2

    # 删除
    image_dir = service.images_root / result["doc_id"]
    assert image_dir.exists()
    service.delete_document(result["doc_id"])
    assert service.db.get_document(result["doc_id"]) is None
    assert not image_dir.exists()


def test_import_pdf_pipeline(service, tmp_path):
    import fitz

    pdf_path = tmp_path / "homework.pdf"
    pdf = fitz.open()
    pdf.new_page(width=595, height=842)
    pdf.save(str(pdf_path))
    pdf.close()

    result = service.import_pdf(pdf_path, subject="数学", title="作业 PDF", tags=("作业",))
    assert result["page_count"] == 1
    assert result["question_count"] == 2
    doc = service.db.get_document(result["doc_id"])
    page = doc["pages"][0]
    assert page["image_path"].endswith(".png")
    from pathlib import Path

    assert Path(page["image_path"]).exists()
    logged = json.loads(page["lines_json"])
    assert len(logged) == 2


def test_import_file_not_found(service):
    with pytest.raises(FileNotFoundError):
        service.import_file("D:/definitely/not/here.jpg")
