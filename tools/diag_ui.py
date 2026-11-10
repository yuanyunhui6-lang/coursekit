"""UI 尺寸诊断：打印窗口/布局尺寸并截图，用于排查高 DPI 下的布局问题。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("KIVY_HOME", str(ROOT / ".kivy"))
os.environ["KIVY_NO_ARGS"] = "1"
DATA = ROOT / "diag_data"
shutil.rmtree(DATA, ignore_errors=True)
os.environ["COURSEKIT_DATA"] = str(DATA)
OUT = ROOT / "build_artifacts" / "screenshots" / "diag.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

import core.ocr as ocr_mod  # noqa: E402
from core.models import OcrLine  # noqa: E402
from core.service import Service  # noqa: E402


def fake_ocr(_path):
    return [
        OcrLine("1. 第一题：求导数"),
        OcrLine("2. 第二题：求积分"),
    ]


ocr_mod.recognize_lines = fake_ocr  # type: ignore[assignment]
svc = Service()
svc.import_file(ROOT / "samples" / "sample_slide.jpg", subject="高数", tags=["重点"])
svc.close()


def main():
    from kivy.clock import Clock
    from kivy.core.window import Window

    from app.app import CourseKitApp

    Window.size = (645, 1320)
    app = CourseKitApp()

    def report(dt):
        print("Window.size =", Window.size)
        print("Window.dpi/density =", getattr(Window, "dpi", None), getattr(Window, "density", None))
        print("root.size =", app.root.size if app.root else None)
        print("screenmanager.size =", app.sm.size)
        print("home.size =", app.home.size)
        print("home.list_scroll.size =", app.home.list_scroll.size)
        print("home.list_box.size =", app.home.list_box.size)
        print("home.list_box.children =", len(app.home.list_box.children))
        for child in app.home.list_box.children:
            print("  card", child.pos, child.size, "min_h", child.minimum_height)

    def snap(dt):
        Window.screenshot(name=str(OUT.with_name("diag_home.png")))

    def stop(dt):
        app.stop()

    Clock.schedule_once(report, 3.0)
    Clock.schedule_once(snap, 3.2)
    Clock.schedule_once(stop, 3.8)
    app.run()
    print("done:", OUT.with_name("diag_home0001.png"))


if __name__ == "__main__":
    main()
