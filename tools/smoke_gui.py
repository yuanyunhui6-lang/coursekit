"""GUI 冒烟测试 + 截图：用示例图片造数据，依次打开各页面并截图。

用法：python tools/smoke_gui.py
截图输出：docs/screenshots/
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
SMOKE_DATA = ROOT / "smoke_data"
SHOTS = ROOT / "build_artifacts" / "screenshots"
shutil.rmtree(SMOKE_DATA, ignore_errors=True)
os.environ["COURSEKIT_DATA"] = str(SMOKE_DATA)
SHOTS.mkdir(parents=True, exist_ok=True)
for old in SHOTS.glob("*.png"):
    if old.name != "diag_home0001.png" and old.name != "diag_home0002.png":
        old.unlink(missing_ok=True)

from core.models import OcrLine  # noqa: E402
from core.service import Service  # noqa: E402

SLIDE_LINES = [
    "第三章 导数与微分",
    "一、选择题",
    "1. 函数 f(x)=x²+2x 的导数是（ ）",
    "A. 2x+2  B. x+2  C. 2x  D. x²",
    "2. 下列说法正确的是（ ）",
    "A. 可导必连续  B. 连续必可导",
    "3. 计算极限 lim(x→0) sin x / x",
    "二、填空题",
    "4. 若 y=ln x，则 y'=____。",
    "5. 曲线 y=x³ 在点 (1,1) 处的切线斜率为 ____。",
]

HOMEWORK_LINES = [
    "高等数学 作业（第三章）",
    "1. 求函数 y=x³-3x²+2 的单调区间和极值。",
    "2. 计算定积分 ∫₀¹ (2x+1) dx。",
    "3. 设 f(x)=e^{2x}，求 f'(x) 与 f''(x)。",
]


def fake_ocr(path):
    name = str(path).lower()
    texts = HOMEWORK_LINES if "homework" in name else SLIDE_LINES
    return [OcrLine(text=t, page=1) for t in texts]


def seed() -> str:
    import core.ocr as ocr_mod

    ocr_mod.recognize_lines = fake_ocr  # type: ignore[assignment]
    service = Service()
    slide = service.import_file(
        ROOT / "samples" / "sample_slide.jpg",
        subject="高等数学",
        tags=["期中", "重点"],
        title="高数第三章 导数与微分",
    )
    homework = service.import_file(
        ROOT / "samples" / "sample_homework.jpg",
        subject="高等数学",
        tags=["作业"],
        title="第三章作业",
    )
    today = date.today()
    service.db.add_homework(
        title="第三章习题（1-6 题）",
        subject="高等数学",
        due_date=today.isoformat(),
        doc_id=homework["doc_id"],
    )
    service.db.add_homework(
        title="预习：第四章 不定积分",
        subject="高等数学",
        due_date=(today + timedelta(days=10)).isoformat(),
    )
    questions = service.db.get_document(slide["doc_id"])["questions"]
    if questions:
        service.db.toggle_question_favorite(int(questions[0]["id"]))
    service.close()
    return slide["doc_id"]


def main() -> int:
    from kivy.clock import Clock
    from kivy.core.window import Window

    from app.app import CourseKitApp

    Window.size = (645, 1320)  # 逻辑尺寸 x 1.5 DPI -> 968x1980 物理像素
    doc_id = seed()
    app = CourseKitApp()

    def shot(prefix: str):
        try:
            Window.screenshot(name=str(SHOTS / f"{prefix}.png"))
        except Exception as exc:  # noqa: BLE001
            print("截图失败：", exc)

    def log_sizes(dt):
        print("Window 尺寸：", Window.size, "根布局尺寸：", app.root.size if app.root else None)

    def step_home(dt):
        shot("01_home")

    def step_open(dt):
        app.open_doc(doc_id)

    def step_text(dt):
        shot("02_detail_text")
        app.detail._switch_tab("questions")  # noqa: SLF001

    def step_questions(dt):
        shot("03_detail_questions")
        app.navigate("homework")

    def step_homework(dt):
        shot("04_homework")
        app.navigate("favorites")

    def step_favorites(dt):
        shot("05_favorites")
        app.navigate("home")

    def step_stop(dt):
        app.stop()

    Clock.schedule_once(log_sizes, 1.0)
    Clock.schedule_once(step_home, 1.8)
    Clock.schedule_once(step_open, 2.2)
    Clock.schedule_once(step_text, 3.0)
    Clock.schedule_once(step_questions, 3.8)
    Clock.schedule_once(step_homework, 4.6)
    Clock.schedule_once(step_favorites, 5.4)
    Clock.schedule_once(step_stop, 6.2)
    app.run()
    print("GUI 冒烟测试结束，截图在：", SHOTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
