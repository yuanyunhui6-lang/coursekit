"""GUI 功能测试：导入 → 详情 → 搜索 → 导出 → 编辑 → 收藏 → 删除。

不依赖真实 OCR（用假数据），验证 UI 层与 Service/DB 的联动。
用法：python tools/functional_test.py
"""
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
DATA = ROOT / "functional_data"
shutil.rmtree(DATA, ignore_errors=True)
os.environ["COURSEKIT_DATA"] = str(DATA)

import core.ocr as ocr_mod  # noqa: E402
from core.models import OcrLine  # noqa: E402


def fake_ocr(path):
    if "homework" in str(path).lower():
        return [OcrLine(t) for t in ("1. 求函数 y=x³-3x²+2 的单调区间。", "2. 计算定积分 ∫₀¹ 2x dx。")]
    return [
        OcrLine("1. 函数 f(x)=x²+2x 的导数是（ ）"),
        OcrLine("A. 2x+2  B. x+2"),
        OcrLine("2. 计算极限 lim(x→0) sin x / x"),
    ]


ocr_mod.recognize_lines = fake_ocr  # type: ignore[assignment]

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def main() -> int:
    from kivy.clock import Clock
    from kivy.core.window import Window

    from app.app import CourseKitApp

    Window.size = (645, 1320)
    app = CourseKitApp()
    def db():
        return app.service.db
    state = {"doc_id": "", "retries": 0}

    def wait_until(cond, then, timeout: float = 20.0, interval: float = 0.2):
        waited = [0.0]

        def poll(_dt):
            try:
                ok = cond()
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                then()
                return
            waited[0] += interval
            if waited[0] > timeout:
                check("等待超时", False, f"{timeout:.0f}s")
                app.stop()
                return
            Clock.schedule_once(poll, interval)

        Clock.schedule_once(poll, interval)

    def step_import():
        app._import_path(str(ROOT / "samples" / "sample_slide.jpg"), subject="高等数学")  # noqa: SLF001
        wait_until(
            lambda: len(db().list_documents()) == 1 and app.sm.current == "detail",
            step_import_done,
        )

    def step_import_done():
        docs = db().list_documents()
        state["doc_id"] = docs[0]["id"]
        check("导入图片生成资料", len(docs) == 1, docs[0]["title"] if docs else "")
        check("详情页自动打开", app.sm.current == "detail", app.sm.current)
        doc = db().get_document(state["doc_id"])
        check("题目切分", len(doc["questions"]) == 2, str(len(doc["questions"])))
        check("全文包含关键词", "导数" in doc["full_text"])
        Clock.schedule_once(step_search, 0.3)

    def step_search(_dt=None):
        app.navigate("home")
        app.home.search.input.text = "导数"
        app.home.refresh(rebuild_chips=False)
        check("搜索命中文档", len(app.home.list_box.children) == 1)
        app.home.search.input.text = "不存在的关键词"
        app.home.refresh(rebuild_chips=False)
        check("搜索无结果显示空状态", len(app.home.list_box.children) == 1)
        app.home.search.input.text = ""
        app.home.refresh()
        Clock.schedule_once(step_export, 0.3)

    def step_export(_dt=None):
        app.export_doc(state["doc_id"], "docx")
        wait_until(
            lambda: any(app.service.exports_root.glob("*.docx")),
            step_export_done,
        )

    def step_export_done():
        files = list(app.service.exports_root.glob("*.docx"))
        check("导出 Word 文件", bool(files), files[0].name if files else "")
        Clock.schedule_once(step_update, 0.3)

    def step_update(_dt=None):
        app.update_doc(state["doc_id"], "改名后的高数课件", "数学", ["A", "B"], "备注")
        doc = db().get_document(state["doc_id"])
        check("编辑标题", doc["title"] == "改名后的高数课件", doc["title"])
        check("编辑标签", sorted(doc["tags"]) == ["A", "B"], str(doc["tags"]))
        Clock.schedule_once(step_favorite, 0.3)

    def step_favorite(_dt=None):
        db().toggle_document_favorite(state["doc_id"])
        check("收藏资料", len(db().list_documents(favorite_only=True)) == 1)
        questions = db().list_questions(favorite_only=True)
        check("收藏题目列表", len(questions) == 0)
        qid = db().get_document(state["doc_id"])["questions"][0]["id"]
        db().toggle_question_favorite(int(qid))
        check("收藏单题", len(db().list_questions(favorite_only=True)) == 1)
        app.favorites.refresh()
        check("收藏页刷新", len(app.favorites.list_box.children) == 1)
        Clock.schedule_once(step_export_md, 0.3)

    def step_export_md(_dt=None):
        app.export_doc(state["doc_id"], "md")
        wait_until(
            lambda: any(app.service.exports_root.glob("*.md")),
            step_delete,
        )

    def step_delete(_dt=None):
        app.delete_doc(state["doc_id"])
        check("删除资料", len(db().list_documents()) == 0)
        check("删除后回到首页", app.sm.current == "home", app.sm.current)
        Clock.schedule_once(step_finish, 0.3)

    exit_code = {"value": 1}

    def step_finish(_dt=None):
        failed = [r for r in RESULTS if not r[1]]
        print(f"\n共 {len(RESULTS)} 项检查，失败 {len(failed)} 项")
        exit_code["value"] = 1 if failed else 0
        app.stop()

    Clock.schedule_once(lambda dt: step_import(), 1.0)
    app.run()
    return exit_code["value"]


if __name__ == "__main__":
    raise SystemExit(main())
