"""弹窗与交互冒烟测试：依次打开各弹窗并截图，检查无异常。

用法：python tools/smoke_modals.py
截图输出：docs/screenshots/modals/
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("KIVY_HOME", str(ROOT / ".kivy"))
os.environ["KIVY_NO_ARGS"] = "1"
DATA = ROOT / "smoke_data2"
shutil.rmtree(DATA, ignore_errors=True)
os.environ["COURSEKIT_DATA"] = str(DATA)
SHOTS = ROOT / "build_artifacts" / "screenshots" / "modals"
shutil.rmtree(SHOTS, ignore_errors=True)
SHOTS.mkdir(parents=True, exist_ok=True)

from core.models import OcrLine  # noqa: E402
from core.service import Service  # noqa: E402


def fake_ocr(path):
    if "homework" in str(path).lower():
        return [OcrLine(t) for t in ("1. 求函数 y=x³-3x²+2 的单调区间和极值。", "2. 计算定积分 ∫₀¹ (2x+1) dx。")]
    return [
        OcrLine("1. 函数 f(x)=x²+2x 的导数是（ ）"),
        OcrLine("A. 2x+2  B. x+2  C. 2x  D. x²"),
        OcrLine("2. 下列说法正确的是（ ）"),
        OcrLine("A. 可导必连续  B. 连续必可导"),
    ]


def seed() -> str:
    import core.ocr as ocr_mod

    ocr_mod.recognize_lines = fake_ocr  # type: ignore[assignment]
    svc = Service()
    slide = svc.import_file(
        ROOT / "samples" / "sample_slide.jpg",
        subject="高等数学",
        tags=["期中", "重点"],
        title="高数第三章 导数与微分",
    )
    svc.db.add_homework(
        title="第三章习题（1-6 题）",
        subject="高等数学",
        due_date=(date.today() + timedelta(days=1)).isoformat(),
        doc_id=slide["doc_id"],
    )
    svc.close()
    return slide["doc_id"]


def main() -> int:
    from kivy.clock import Clock
    from kivy.core.window import Window

    from app.app import CourseKitApp
    from app.modals import (
        ExportModal,
        FilePickerPopup,
        HelpModal,
        HomeworkModal,
        ImportModal,
        PageImageModal,
    )

    Window.size = (645, 1320)
    doc_id = seed()
    app = CourseKitApp()

    def snap(name: str):
        try:
            Window.screenshot(name=str(SHOTS / f"{name}.png"))
        except Exception as exc:  # noqa: BLE001
            print("截图失败：", exc)

    steps = []

    def add(delay, fn):
        Clock.schedule_once(fn, delay)

    def open_import():
        ImportModal(on_choice=lambda mode, subject: print("import choice:", mode, subject)).open()

    def close_and(name, factory):
        def step(dt):
            from kivy.uix.modalview import ModalView

            for modal in [w for w in Window.children if isinstance(w, ModalView)]:
                modal.dismiss()
            Clock.schedule_once(lambda dt2: (factory(), Clock.schedule_once(lambda dt3: snap(name), 0.6)), 0.15)

        return step

    def open_export():
        ExportModal(on_choose=lambda fmt: print("export:", fmt)).open()

    def open_homework():
        HomeworkModal(on_save=lambda *a: print("homework save", a), title="第三章习题", subject="高等数学").open()

    def open_help():
        HelpModal().open()

    def open_picker():
        FilePickerPopup(mode="image", on_select=lambda p: print("pick:", p)).open()

    def open_page():
        img = ROOT / "samples" / "sample_slide.jpg"
        PageImageModal(str(img), "第 1 页").open()

    def open_edit():
        from app.modals import EditDocModal

        doc = app.service.db.get_document(doc_id)
        EditDocModal(doc, on_save=lambda *a: print("edit save")).open()

    def finish(dt=None):
        from kivy.uix.modalview import ModalView

        for modal in [w for w in Window.children if isinstance(w, ModalView)]:
            modal.dismiss()
        app.stop()

    schedule = [
        (1.2, close_and("01_import", open_import)),
        (2.0, close_and("02_export", open_export)),
        (2.8, close_and("03_homework", open_homework)),
        (3.6, close_and("04_help", open_help)),
        (4.4, close_and("05_picker", open_picker)),
        (5.2, close_and("06_page", open_page)),
        (6.0, close_and("07_edit", open_edit)),
        (6.8, finish),
    ]
    for delay, fn in schedule:
        add(delay, fn)

    app.run()
    print("弹窗冒烟测试结束：", SHOTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
