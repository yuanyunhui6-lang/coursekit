"""端到端自测：真实 RapidOCR 识别示例图片 → 切题 → 入库 → 导出。

用法：python tools/ocr_check.py samples/sample_slide.jpg
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import ocr, split  # noqa: E402
from core.layout import lines_to_text  # noqa: E402
from core.service import Service  # noqa: E402


def main(image_path: str) -> int:
    path = Path(image_path)
    print("OCR 引擎：", ocr.engine_label())
    lines = ocr.recognize_lines(str(path))
    print(f"识别到 {len(lines)} 行：")
    for line in lines:
        print("  ", line.text)
    text = lines_to_text(lines)
    blocks = split.split_questions(lines)
    print(f"\n切分出 {len(blocks)} 道题：")
    for block in blocks:
        print(f"  [{block.number}] {block.text[:40]}")

    with tempfile.TemporaryDirectory() as tmp:
        service = Service(data_dir=Path(tmp) / "data")
        result = service.import_file(path, subject="高等数学", tags=["课件"])
        doc = service.db.get_document(result["doc_id"])
        print("\n入库结果：", result)
        print("题目数量：", doc["question_count"], "页面图片：", doc["pages"][0]["image_path"])
        md = service.export(result["doc_id"], "md")
        docx = service.export(result["doc_id"], "docx")
        print("导出：", md["filename"], md["size"], "字节；", docx["filename"], docx["size"], "字节")
        ok = doc["question_count"] >= 5 and "导数" in doc["full_text"]
        service.close()
    print("\n端到端检查：", "通过" if ok else "未通过（题目数不足或未识别关键词）")
    return 0 if ok else 1


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "samples/sample_slide.jpg"
    raise SystemExit(main(target))
