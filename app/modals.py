"""弹窗类组件：处理进度、导入、文件选择、导出、编辑、作业、帮助、看图。"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from . import theme as T
from . import utils
from .widgets import (
    Card,
    Chip,
    EmptyState,
    HLine,
    MutedLabel,
    PillButton,
    TapCard,
    TitleLabel,
    WrapLabel,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic", ".heif"}


# ---------------------------------------------------------------- 基础弹窗
class BaseModal(ModalView):
    """统一的全屏遮罩 + 居中/底部卡片。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("auto_dismiss", True)
        kwargs.setdefault("background_color", (0, 0, 0, 0.42))
        kwargs.setdefault("size_hint", (1, 1))
        super().__init__(**kwargs)
        self.container = FloatLayout()
        self.add_widget(self.container)

    def show_card(self, card: Card) -> Card:
        self.container.add_widget(card)
        return card

    def _close(self, *args):
        self.dismiss()


def make_card(width: float = 0.92, height=None, **kwargs) -> Card:
    """创建居中卡片。

    height 为 None 时按内容撑开；0~1 的小数视为相对高度；其余视为 dp 固定高。
    """
    kwargs.setdefault("orientation", "vertical")
    kwargs.setdefault("padding", [dp(16), dp(14)])
    kwargs.setdefault("spacing", dp(10))
    kwargs.setdefault("radius", dp(18))
    kwargs.setdefault("pos_hint", {"center_x": 0.5, "center_y": 0.5})
    if height is None:
        kwargs.setdefault("size_hint", (width, None))
    elif isinstance(height, float) and 0 < height <= 1:
        kwargs.setdefault("size_hint", (width, height))
    else:
        kwargs.setdefault("size_hint", (width, None))
        kwargs.setdefault("height", height)
    return Card(**kwargs)


def field_input(hint: str, text: str = "", multiline: bool = False) -> TextInput:
    """统一样式的输入框。"""
    ti = TextInput(
        hint_text=hint,
        text=text,
        multiline=multiline,
        font_name=T.FONT_NAME,
        font_size=sp(14.5),
        background_normal="",
        background_active="",
        background_color=list(T.CHIP),
        foreground_color=list(T.TEXT),
        cursor_color=list(T.PRIMARY),
        hint_text_color=list(T.SUB),
        padding=[dp(12), dp(12)],
    )
    if multiline:
        ti.size_hint_y = None
        ti.height = dp(84)
    else:
        ti.size_hint_y = None
        ti.height = dp(46)
    return ti


def _field(label: str, widget) -> object:
    from kivy.uix.boxlayout import BoxLayout

    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    box.add_widget(MutedLabel(text=label, font_size=sp(12), size_hint_y=None))
    box.add_widget(widget)
    box.bind(minimum_height=box.setter("height"))
    return box


# ---------------------------------------------------------------- 进度
class ProcessingModal(BaseModal):
    def __init__(self, **kwargs):
        kwargs["auto_dismiss"] = False
        super().__init__(**kwargs)
        self.card = make_card(width=0.86, height=dp(206))
        self.title = Label(
            text="正在处理…",
            font_name=T.FONT_NAME,
            font_size=sp(18),
            bold=True,
            color=list(T.TEXT),
            size_hint_y=None,
            height=dp(30),
            halign="center",
        )
        self.status = WrapLabel(
            text="准备中",
            halign="center",
            font_size=sp(13.5),
            color=list(T.SUB),
            size_hint_y=None,
        )
        self.bar = ProgressBar(max=1.0, value=0.0, size_hint_y=None, height=dp(6))
        hint = MutedLabel(
            text="文字识别在手机本地完成，不会上传服务器",
            halign="center",
            font_size=sp(11),
            size_hint_y=None,
        )
        self.card.add_widget(self.title)
        self.card.add_widget(self.status)
        self.card.add_widget(self.bar)
        self.card.add_widget(hint)
        self.show_card(self.card)

    def update(self, done: int, total: int, message: str = "") -> None:
        try:
            self.bar.value = max(0.0, min(1.0, float(done) / max(1.0, float(total))))
        except (TypeError, ValueError, ZeroDivisionError):
            self.bar.value = 0.0
        if message:
            self.status.text = message


# ---------------------------------------------------------------- 确认
class ConfirmModal(BaseModal):
    def __init__(self, title: str, message: str, on_confirm=None, danger: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._on_confirm = on_confirm
        card = make_card(width=0.88, height=dp(188))
        card.add_widget(
            Label(
                text=title,
                font_name=T.FONT_NAME,
                font_size=sp(17),
                bold=True,
                color=list(T.TEXT),
                size_hint_y=None,
                height=dp(30),
            )
        )
        card.add_widget(WrapLabel(text=message, size_hint_y=None))
        card.add_widget(Label(size_hint_y=None, height=dp(2)))
        row = self._buttons(danger)
        card.add_widget(row)
        self.show_card(card)

    def _buttons(self, danger: bool):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(10))
        cancel = PillButton(
            text="取消",
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.TEXT),
            font_size=sp(14),
            size_hint=(1, 1),
        )
        ok_color = list(T.DANGER) if danger else list(T.PRIMARY)
        ok = PillButton(
            text="确定",
            bg_color=ok_color,
            pressed_color=list(T.DANGER_SOFT) if danger else list(T.PRIMARY_DARK),
            font_size=sp(14),
            size_hint=(1, 1),
        )
        cancel.bind(on_release=lambda *a: self.dismiss())
        ok.bind(on_release=self._confirm)
        row.add_widget(cancel)
        row.add_widget(ok)
        return row

    def _confirm(self, *args):
        callback = self._on_confirm
        self.dismiss()
        if callback:
            callback()


# ---------------------------------------------------------------- 导入
class ImportModal(BaseModal):
    """底部导入面板：拍照 / 图片 / PDF，可选科目。"""

    def __init__(self, on_choice, subject_default: str = "", is_android: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._on_choice = on_choice
        card = make_card(width=0.94, height=dp(392))
        card.pos_hint = {"center_x": 0.5, "center_y": 0.44}
        header = self._header("导入资料")
        card.add_widget(header)
        card.add_widget(MutedLabel(text="科目（可选，方便以后按课程复习）", font_size=sp(12)))
        self.subject = field_input("例如：高等数学 / 数据结构", subject_default)
        card.add_widget(self.subject)
        card.add_widget(Label(size_hint_y=None, height=dp(2)))

        card.add_widget(
            self._option("拍", "拍照识别", "打开相机拍课件 / 板书", "camera", is_android)
        )
        card.add_widget(
            self._option("图", "相册 / 图片", "从手机相册或电脑文件夹选图片", "image", True)
        )
        card.add_widget(
            self._option("PDF", "PDF 文件", "电子版讲义、扫描版作业都能导入", "pdf", True)
        )
        self.show_card(card)

    def _header(self, title: str):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        lbl = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(18),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        close = PillButton(
            text="×",
            font_size=sp(20),
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(34),
        )
        close.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(lbl)
        row.add_widget(close)
        return row

    def _option(self, icon: str, title: str, subtitle: str, mode: str, enabled: bool) -> TapCard:
        row = TapCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(62),
            padding=[dp(12), dp(9)],
            spacing=dp(12),
            radius=dp(12),
            bg_color=list(T.CHIP),
        )
        icon_lbl = Label(
            text=icon,
            font_name=T.FONT_NAME,
            font_size=sp(15),
            bold=True,
            color=list(T.PRIMARY),
            size_hint=(None, 1),
            width=dp(34),
            halign="center",
            valign="middle",
        )
        from kivy.uix.boxlayout import BoxLayout

        texts = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
        texts.bind(minimum_height=texts.setter("height"))
        t = WrapLabel(
            text=title,
            font_size=sp(15),
            bold=True,
            color=list(T.TEXT) if enabled else list(T.SUB),
        )
        s = MutedLabel(text=subtitle, font_size=sp(11.5))
        texts.add_widget(t)
        texts.add_widget(s)
        row.add_widget(icon_lbl)
        row.add_widget(texts)
        if not enabled:
            row.bind(on_release=lambda *a: self._disabled())
        else:
            row.bind(on_release=lambda *a: self._pick(mode))
        return row

    def _disabled(self, *args):
        from kivy.app import App

        App.get_running_app().toast("电脑端请用「相册 / 图片」导入，手机端可直接拍照")

    def _pick(self, mode: str):
        subject = self.subject.text.strip()
        self.dismiss()
        Clock.schedule_once(lambda dt: self._on_choice(mode, subject), 0.05)


# ---------------------------------------------------------------- 文件选择
def default_picker_path() -> str:
    from core.paths import is_android

    if is_android():
        candidates = [
            "/storage/emulated/0/Download",
            "/storage/emulated/0/DCIM/Camera",
            "/storage/emulated/0/Pictures",
            "/storage/emulated/0",
        ]
    else:
        home = str(Path.home())
        candidates = [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Pictures"),
            home,
        ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return str(Path.home())


class FilePickerPopup(BaseModal):
    """自绘的文件浏览器（比 Kivy 自带 FileChooser 更适合触屏）。"""

    def __init__(self, mode: str = "image", on_select=None, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self._on_select = on_select
        self.path = default_picker_path()
        card = make_card(width=0.94, height=0.88)
        card.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        card.add_widget(self._header())
        self.path_lbl = MutedLabel(text=self.path, font_size=sp(11), size_hint_y=None)
        card.add_widget(self.path_lbl)

        tools = self._tools()
        card.add_widget(tools)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.list_box = self._make_list_box()
        self.scroll.add_widget(self.list_box)
        card.add_widget(self.scroll)
        self.show_card(card)
        self._refresh()

    def _make_list_box(self):
        from kivy.uix.boxlayout import BoxLayout

        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
        box.bind(minimum_height=box.setter("height"))
        return box

    def _header(self):
        from kivy.uix.boxlayout import BoxLayout

        title = {
            "image": "选择图片",
            "pdf": "选择 PDF",
            "any": "选择文件",
        }.get(self.mode, "选择文件")
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        lbl = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(17),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        close = PillButton(
            text="×",
            font_size=sp(20),
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(34),
        )
        close.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(lbl)
        row.add_widget(close)
        return row

    def _tools(self):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))
        up = PillButton(
            text="上一级",
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.TEXT),
            font_size=sp(12.5),
            size_hint=(None, 1),
            width=dp(74),
        )
        up.bind(on_release=lambda *a: self._go_parent())
        row.add_widget(up)
        row.add_widget(Label())  # 占位
        return row

    def _go_parent(self, *args):
        parent = os.path.dirname(self.path.rstrip("/\\"))
        if parent and os.path.isdir(parent):
            self.path = parent
            self._refresh()

    def _allowed(self, name: str) -> bool:
        ext = os.path.splitext(name)[1].lower()
        if self.mode == "image":
            return ext in IMAGE_EXTS
        if self.mode == "pdf":
            return ext == ".pdf"
        return ext in IMAGE_EXTS or ext == ".pdf"

    def _refresh(self):
        self.path_lbl.text = self.path
        self.list_box.clear_widgets()
        try:
            entries = list(os.scandir(self.path))
        except OSError as exc:
            self.list_box.add_widget(WrapLabel(text=f"无法读取此目录：{exc}", color=list(T.DANGER)))
            return
        dirs = []
        files = []
        for entry in entries:
            try:
                name = entry.name
                if name.startswith("."):
                    continue
                if entry.is_dir():
                    dirs.append(name)
                elif self._allowed(name):
                    files.append((name, entry.stat().st_size))
            except OSError:
                continue
        dirs.sort()
        files.sort(key=lambda item: item[0].lower())
        if not dirs and not files:
            self.list_box.add_widget(
                EmptyState("这个文件夹里没有可导入的文件", "点「上一级」换个文件夹找找")
            )
        for name in dirs[:200]:
            self._entry_row(f"» {name}", "", True, os.path.join(self.path, name))
        for name, size in files[:300]:
            self._entry_row(name, utils.human_size(size), False, os.path.join(self.path, name))

    def _entry_row(self, name: str, size_text: str, is_dir: bool, full_path: str):
        from kivy.uix.boxlayout import BoxLayout

        row = TapCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(10), 0],
            spacing=dp(6),
            radius=dp(10),
            bg_color=list(T.CARD),
        )
        lbl = Label(
            text=name,
            font_name=T.FONT_NAME,
            font_size=sp(13.5),
            color=list(T.TEXT) if not is_dir else list(T.PRIMARY),
            halign="left",
            valign="middle",
            shorten=True,
            shorten_from="right",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        row.add_widget(lbl)
        if size_text:
            sz = MutedLabel(text=size_text, font_size=sp(11), size_hint=(None, 1), width=dp(58))
            row.add_widget(sz)
        if is_dir:
            row.bind(on_release=lambda *a: self._enter(full_path))
        else:
            row.bind(on_release=lambda *a: self._choose(full_path))
        self.list_box.add_widget(row)

    def _enter(self, path: str):
        self.path = path
        self._refresh()

    def _choose(self, path: str):
        callback = self._on_select
        self.dismiss()
        if callback:
            Clock.schedule_once(lambda dt: callback(path), 0.05)


# ---------------------------------------------------------------- 导出
class ExportModal(BaseModal):
    def __init__(self, on_choose, **kwargs):
        super().__init__(**kwargs)
        self._on_choose = on_choose
        card = make_card(width=0.92, height=dp(330))
        card.add_widget(self._title("导出为…"))
        card.add_widget(self._option("Markdown", "带题号与答案，适合复习软件 / 笔记导入", "md"))
        card.add_widget(self._option("Word 文档", "排版好的 .docx，可直接打印或交作业", "docx"))
        card.add_widget(self._option("纯文本", "最通用的 .txt 格式", "txt"))
        self.show_card(card)

    def _title(self, text: str):
        row = self._header_row(text)
        return row

    def _header_row(self, text: str):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        lbl = Label(
            text=text,
            font_name=T.FONT_NAME,
            font_size=sp(18),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        close = PillButton(
            text="×",
            font_size=sp(20),
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(34),
        )
        close.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(lbl)
        row.add_widget(close)
        return row

    def _option(self, title: str, subtitle: str, fmt: str) -> TapCard:
        from kivy.uix.boxlayout import BoxLayout

        row = TapCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(64),
            padding=[dp(12), dp(8)],
            spacing=dp(2),
            radius=dp(12),
            bg_color=list(T.CHIP),
        )
        t = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(15),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="bottom",
        )
        t.bind(size=lambda w, s: setattr(w, "text_size", s))
        row.add_widget(t)
        row.add_widget(MutedLabel(text=subtitle, font_size=sp(11.5)))
        row.bind(on_release=lambda *a: self._choose(fmt))
        return row

    def _choose(self, fmt: str):
        callback = self._on_choose
        self.dismiss()
        if callback:
            Clock.schedule_once(lambda dt: callback(fmt), 0.05)


# ---------------------------------------------------------------- 编辑资料
class EditDocModal(BaseModal):
    def __init__(self, doc: dict, on_save, **kwargs):
        super().__init__(**kwargs)
        self._on_save = on_save
        from kivy.uix.boxlayout import BoxLayout

        card = make_card(width=0.94, height=0.72)
        card.add_widget(self._header("编辑资料"))

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        body.bind(minimum_height=body.setter("height"))
        scroll.add_widget(body)
        card.add_widget(scroll)

        self.title_in = field_input("资料标题", doc.get("title", ""))
        self.subject_in = field_input("科目，如：高等数学", doc.get("subject", ""))
        self.tags_in = field_input("标签，用逗号分隔，如：期中,重点", "、".join(doc.get("tags") or []))
        self.note_in = field_input("备注（可选）", doc.get("note", ""), multiline=True)

        for label, widget in (
            ("标题", self.title_in),
            ("科目", self.subject_in),
            ("标签", self.tags_in),
            ("备注", self.note_in),
        ):
            body.add_widget(_field(label, widget))

        save = PillButton(text="保存", font_size=sp(15), size_hint_y=None, height=dp(44))
        save.bind(on_release=self._save)
        card.add_widget(save)
        self.show_card(card)

    def _header(self, title: str):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        lbl = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(18),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        close = PillButton(
            text="×",
            font_size=sp(20),
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(34),
        )
        close.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(lbl)
        row.add_widget(close)
        return row

    def _save(self, *args):
        title = self.title_in.text.strip() or "未命名资料"
        subject = self.subject_in.text.strip()
        raw_tags = self.tags_in.text.replace(",", "、").replace("，", "、")
        tags = [t.strip() for t in raw_tags.split("、") if t.strip()]
        note = self.note_in.text.strip()
        callback = self._on_save
        self.dismiss()
        if callback:
            callback(title, subject, tags, note)


# ---------------------------------------------------------------- 作业
class HomeworkModal(BaseModal):
    def __init__(self, on_save, title: str = "", subject: str = "", due: str = "", note: str = "", **kwargs):
        super().__init__(**kwargs)
        self._on_save = on_save
        from kivy.uix.boxlayout import BoxLayout

        card = make_card(width=0.94, height=0.72)
        card.add_widget(self._header("添加作业"))

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        body.bind(minimum_height=body.setter("height"))
        scroll.add_widget(body)
        card.add_widget(scroll)

        self.title_in = field_input("作业标题，如：第三章习题", title)
        self.subject_in = field_input("科目", subject)
        self.due_in = field_input("截止日期，如 2026-11-20", due or utils.default_due(7))
        self.note_in = field_input("备注（可选）", note, multiline=True)
        for label, widget in (
            ("标题", self.title_in),
            ("科目", self.subject_in),
            ("截止日期", self.due_in),
            ("备注", self.note_in),
        ):
            body.add_widget(_field(label, widget))

        body.add_widget(self._quick_dates())

        save = PillButton(text="保存", font_size=sp(15), size_hint_y=None, height=dp(44))
        save.bind(on_release=self._save)
        card.add_widget(save)
        self.show_card(card)

    def _header(self, title: str):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        lbl = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(18),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        close = PillButton(
            text="×",
            font_size=sp(20),
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(34),
        )
        close.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(lbl)
        row.add_widget(close)
        return row

    def _quick_dates(self):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))
        for label, days in (("今天", 0), ("明天", 1), ("一周后", 7), ("两周后", 14)):
            btn = PillButton(
                text=label,
                bg_color=list(T.CHIP),
                pressed_color=list(T.BORDER),
                color=list(T.TEXT),
                font_size=sp(12.5),
                autosize=True,
                pad_x=dp(12),
                pad_y=dp(6),
            )
            btn.bind(on_release=lambda w, d=days: setattr(self.due_in, "text", utils.default_due(d)))
            row.add_widget(btn)
        row.add_widget(Label())
        return row

    def _save(self, *args):
        title = self.title_in.text.strip()
        if not title:
            from kivy.app import App

            App.get_running_app().toast("请先填写作业标题")
            return
        due = self.due_in.text.strip()
        callback = self._on_save
        self.dismiss()
        if callback:
            callback(title, self.subject_in.text.strip(), due, self.note_in.text.strip())


# ---------------------------------------------------------------- 菜单
class MenuModal(BaseModal):
    def __init__(self, items, **kwargs):
        """items: [(label, callback, danger_bool), ...]"""
        super().__init__(**kwargs)
        from kivy.uix.boxlayout import BoxLayout

        card = make_card(width=0.9, height=dp(64 + 46 * len(items)))
        for index, item in enumerate(items):
            label, callback = item[0], item[1]
            danger = bool(item[2]) if len(item) > 2 else False
            btn = PillButton(
                text=label,
                bg_color=list(T.DANGER_SOFT) if danger else list(T.CHIP),
                pressed_color=list(T.BORDER),
                color=list(T.DANGER) if danger else list(T.TEXT),
                font_size=sp(14.5),
                size_hint_y=None,
                height=dp(42),
            )
            btn.bind(on_release=lambda w, cb=callback: self._run(cb))
            card.add_widget(btn)
        self.show_card(card)

    def _run(self, callback):
        self.dismiss()
        if callback:
            Clock.schedule_once(lambda dt: callback(), 0.05)


# ---------------------------------------------------------------- 看图
class PageImageModal(BaseModal):
    def __init__(self, image_path: str, title: str = "", **kwargs):
        super().__init__(**kwargs)
        self.card = make_card(width=0.96, height=0.94)
        self.card.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        self.card.add_widget(self._header(title or "原页对照"))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.image = Image(source=image_path, size_hint=(1, None), allow_stretch=True, keep_ratio=True)
        self.image.bind(texture=self._fit, size=lambda *a: self._fit())
        scroll.add_widget(self.image)
        self.card.add_widget(scroll)
        self.show_card(self.card)

    def _header(self, title: str):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        lbl = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(16),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        close = PillButton(
            text="×",
            font_size=sp(20),
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(34),
        )
        close.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(lbl)
        row.add_widget(close)
        return row

    def _fit(self, *args):
        texture = self.image.texture
        if not texture or texture.width <= 0:
            return
        width = self.card.width - dp(32) if self.card.width > dp(60) else 300
        self.image.height = width * texture.height / texture.width


# ---------------------------------------------------------------- 帮助
class HelpModal(BaseModal):
    TEXT = (
        "【怎么用】\n"
        "1. 点首页右下角「＋」：拍照、选相册图片，或导入 PDF。\n"
        "2. 等几秒，App 会自动识别文字，并按 1. /（1）/ 一、 等题号切分题目。\n"
        "3. 在首页按科目、标签、收藏筛选；点开资料可看全文、题目和原页。\n"
        "4. 右下角「作业」把资料设为作业，填截止日期，就不会忘交。\n"
        "5. 资料页右上角「…」可导出 Markdown / Word，方便打印或导入笔记软件。\n"
        "\n【识别效果】\n"
        "• 打印体、PPT 截图：效果好。\n"
        "• 手写、复杂公式、艺术字：可能识别不全，可对照原页复习。\n"
        "• 电子版 PDF 会优先读取文字层，准确率最高。\n"
        "\n【隐私】\n"
        "文字识别全部在本机离线完成，图片和文字只保存在本机数据库，不会上传。\n"
        "\n【小提示】\n"
        "拍照时尽量正对、光线充足、避免反光，识别会准很多。"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        card = make_card(width=0.94, height=0.86)
        card.add_widget(self._header("使用帮助"))
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        body = WrapLabel(text=self.TEXT, font_size=sp(13.5), size_hint_y=None)
        scroll.add_widget(body)
        card.add_widget(scroll)
        self.show_card(card)

    def _header(self, title: str):
        from kivy.uix.boxlayout import BoxLayout

        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6))
        lbl = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(18),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        close = PillButton(
            text="×",
            font_size=sp(20),
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(34),
        )
        close.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(lbl)
        row.add_widget(close)
        return row
