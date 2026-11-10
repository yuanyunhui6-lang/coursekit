"""列表卡片：资料卡、题目卡、作业卡、收藏题目卡。"""
from __future__ import annotations

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from . import theme as T
from . import utils
from .modals import PageImageModal
from .widgets import Card, Chip, MutedLabel, NumBadge, PillButton, StarButton, TapCard, WrapLabel


def _hrow(**kwargs) -> BoxLayout:
    kwargs.setdefault("orientation", "horizontal")
    kwargs.setdefault("size_hint_y", None)
    row = BoxLayout(**kwargs)
    row.bind(minimum_height=row.setter("height"))
    return row


def _meta_text(doc: dict) -> str:
    parts: list[str] = []
    if doc.get("subject"):
        parts.append(str(doc["subject"]))
    created = str(doc.get("created_at", ""))[:10]
    if created:
        parts.append(created)
    if doc.get("page_count"):
        parts.append(f"{doc['page_count']} 页")
    if doc.get("question_count"):
        parts.append(f"{doc['question_count']} 题")
    if doc.get("doc_type") == "pdf":
        parts.append("PDF")
    return " · ".join(parts)


def _pending_homework(doc: dict) -> dict | None:
    for hw in doc.get("homework") or []:
        if not hw.get("done"):
            return hw
    return None


class DocCard(TapCard):
    """资料卡：标题、科目、时间、页数/题数、标签、作业截止提醒、收藏星。"""

    def __init__(self, app, doc: dict, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("padding", [dp(14), dp(12)])
        kwargs.setdefault("spacing", dp(5))
        kwargs.setdefault("radius", dp(14))
        super().__init__(**kwargs)
        self.app = app
        self.doc = doc
        self.bind(minimum_height=self.setter("height"))
        self.bind(on_release=lambda *a: app.open_doc(doc.get("id")))

        top = _hrow(spacing=dp(6))
        title = WrapLabel(
            text=str(doc.get("title") or "未命名资料"),
            font_size=sp(16),
            bold=True,
            size_hint_x=1,
        )
        top.add_widget(title)
        self.star = StarButton(active=bool(doc.get("favorite")))
        self.star.bind(on_release=self._toggle_favorite)
        top.add_widget(self.star)
        self.add_widget(top)

        self.add_widget(MutedLabel(text=_meta_text(doc), font_size=sp(12)))

        if doc.get("tags"):
            tags = " ".join(f"#{t}" for t in doc["tags"][:6])
            self.add_widget(MutedLabel(text=tags, font_size=sp(11.5)))

        hw = _pending_homework(doc)
        if hw:
            left = utils.days_until(hw.get("due_date", ""))
            if left is None:
                bg, fg = list(T.CHIP), list(T.SUB)
            elif left < 0:
                bg, fg = list(T.DANGER_SOFT), list(T.DANGER)
            elif left <= 2:
                bg, fg = list(T.WARN_SOFT), list(T.WARN)
            else:
                bg, fg = list(T.PRIMARY_SOFT), list(T.PRIMARY)
            chip = Chip(text="作业：" + utils.due_text(hw.get("due_date", "")), fg_color=fg)
            chip.bg_color = bg
            chip.color = fg
            row = _hrow(spacing=dp(6))
            row.add_widget(chip)
            self.add_widget(row)

    def _toggle_favorite(self, *args):
        try:
            fav = self.app.service.db.toggle_document_favorite(self.doc["id"])
            self.doc["favorite"] = fav
            self.star.active = bool(fav)
            self.app.toast("已加入收藏" if fav else "已取消收藏")
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"操作失败：{exc}")


class QuestionCard(Card):
    """题目卡：题号、正文、答案、收藏、查看原页。"""

    def __init__(self, app, question: dict, page_image: str = "", **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("padding", [dp(12), dp(10)])
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("radius", dp(12))
        super().__init__(**kwargs)
        self.app = app
        self.question = question
        self.bind(minimum_height=self.setter("height"))

        top = _hrow(spacing=dp(8))
        number = str(question.get("number") or question.get("order_no") or "")
        top.add_widget(NumBadge(text=number))
        top.add_widget(
            WrapLabel(text=str(question.get("text", "")), font_size=sp(14.5), size_hint_x=1)
        )
        star = StarButton(active=bool(question.get("favorite")))
        star.bind(on_release=lambda *a: self._toggle(star))
        top.add_widget(star)
        self.add_widget(top)

        if question.get("answer"):
            self.add_widget(
                WrapLabel(
                    text="答案 / 解析：" + str(question["answer"]),
                    font_size=sp(13),
                    color=list(T.OK),
                )
            )
        if page_image:
            from kivy.uix.boxlayout import BoxLayout as _BL

            btn_row = _BL(orientation="horizontal", size_hint_y=None, height=dp(30), spacing=dp(6))
            btn_row.add_widget(Label(size_hint_x=1))
            btn = PillButton(
                text="看原页",
                bg_color=list(T.PRIMARY_SOFT),
                pressed_color=list(T.BORDER),
                color=list(T.PRIMARY),
                font_size=sp(12),
                autosize=True,
                pad_x=dp(12),
                pad_y=dp(4),
            )
            btn.bind(on_release=lambda *a: PageImageModal(page_image).open())
            btn_row.add_widget(btn)
            self.add_widget(btn_row)

    def _toggle(self, star, *args):
        try:
            fav = self.app.service.db.toggle_question_favorite(int(self.question["id"]))
            self.question["favorite"] = fav
            star.active = bool(fav)
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"操作失败：{exc}")


class HomeworkCard(Card):
    """作业卡：状态、截止日期、完成/查看/删除。"""

    def __init__(self, app, hw: dict, on_change, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("padding", [dp(12), dp(10)])
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("radius", dp(12))
        super().__init__(**kwargs)
        self.app = app
        self.hw = hw
        self._on_change = on_change
        self.bind(minimum_height=self.setter("height"))

        done = bool(hw.get("done"))
        left = utils.days_until(hw.get("due_date", ""))
        if done:
            status_text, bg, fg = "已完成", list(T.OK_SOFT), list(T.OK)
        elif left is not None and left < 0:
            status_text, bg, fg = "已逾期", list(T.DANGER_SOFT), list(T.DANGER)
        elif left == 0:
            status_text, bg, fg = "今天截止", list(T.WARN_SOFT), list(T.WARN)
        else:
            status_text, bg, fg = "待完成", list(T.PRIMARY_SOFT), list(T.PRIMARY)

        top = _hrow(spacing=dp(8))
        title = WrapLabel(
            text=str(hw.get("title", "作业")),
            font_size=sp(15.5),
            bold=True,
            size_hint_x=1,
            color=list(T.SUB) if done else list(T.TEXT),
        )
        top.add_widget(title)
        status = Chip(text=status_text, fg_color=fg)
        status.bg_color = bg
        status.color = fg
        top.add_widget(status)
        self.add_widget(top)

        meta = utils.due_text(hw.get("due_date", ""), done=done)
        if hw.get("subject"):
            meta = f"{hw['subject']} · {meta}"
        if hw.get("note"):
            meta += f" · {hw['note']}"
        self.add_widget(MutedLabel(text=meta, font_size=sp(12)))

        buttons = _hrow(spacing=dp(8), padding=[0, dp(2), 0, 0])
        done_btn = PillButton(
            text="撤销完成" if done else "标记完成",
            bg_color=list(T.OK_SOFT) if not done else list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.OK) if not done else list(T.SUB),
            font_size=sp(12),
            autosize=True,
            pad_x=dp(12),
            pad_y=dp(4),
        )
        done_btn.bind(on_release=self._toggle_done)
        buttons.add_widget(done_btn)

        if hw.get("doc_id"):
            open_btn = PillButton(
                text="查看资料",
                bg_color=list(T.PRIMARY_SOFT),
                pressed_color=list(T.BORDER),
                color=list(T.PRIMARY),
                font_size=sp(12),
                autosize=True,
                pad_x=dp(12),
                pad_y=dp(4),
            )
            open_btn.bind(on_release=lambda *a: self.app.open_doc(hw["doc_id"]))
            buttons.add_widget(open_btn)

        del_btn = PillButton(
            text="删除",
            bg_color=list(T.DANGER_SOFT),
            pressed_color=list(T.BORDER),
            color=list(T.DANGER),
            font_size=sp(12),
            autosize=True,
            pad_x=dp(12),
            pad_y=dp(4),
        )
        del_btn.bind(on_release=self._delete)
        buttons.add_widget(del_btn)
        buttons.add_widget(Label(size_hint_x=1))
        self.add_widget(buttons)

    def _toggle_done(self, *args):
        done = 0 if self.hw.get("done") else 1
        try:
            self.app.service.db.update_homework(int(self.hw["id"]), done=done)
            self.app.toast("已标记完成" if done else "已恢复待完成")
            self._on_change()
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"操作失败：{exc}")

    def _delete(self, *args):
        from .modals import ConfirmModal

        def do_delete():
            try:
                self.app.service.db.delete_homework(int(self.hw["id"]))
                self.app.toast("已删除作业")
                self._on_change()
            except Exception as exc:  # noqa: BLE001
                self.app.toast(f"删除失败：{exc}")

        ConfirmModal(
            title="删除作业",
            message=f"确定删除「{self.hw.get('title', '')}」吗？此操作不可恢复。",
            on_confirm=do_delete,
            danger=True,
        ).open()


class FavQuestionCard(TapCard):
    """收藏题目卡：点一下跳转到对应资料。"""

    def __init__(self, app, question: dict, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("padding", [dp(12), dp(10)])
        kwargs.setdefault("spacing", dp(5))
        kwargs.setdefault("radius", dp(12))
        super().__init__(**kwargs)
        self.app = app
        self.question = question
        self.bind(minimum_height=self.setter("height"))
        self.bind(on_release=lambda *a: app.open_doc(question.get("doc_id")))

        top = _hrow(spacing=dp(8))
        top.add_widget(NumBadge(text=str(question.get("number") or question.get("order_no") or "")))
        top.add_widget(
            WrapLabel(text=str(question.get("text", "")), font_size=sp(14), size_hint_x=1)
        )
        star = StarButton(active=True)
        star.bind(on_release=lambda *a: self._unfavorite(star))
        top.add_widget(star)
        self.add_widget(top)

        source = str(question.get("doc_title", ""))
        if question.get("subject"):
            source = f"{source} · {question['subject']}"
        self.add_widget(MutedLabel(text="来自：" + source, font_size=sp(11.5)))

    def _unfavorite(self, star, *args):
        try:
            self.app.service.db.toggle_question_favorite(int(self.question["id"]))
            self.app.refresh_favorites()
            self.app.toast("已取消收藏")
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"操作失败：{exc}")
