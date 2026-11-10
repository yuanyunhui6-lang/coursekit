"""通用 UI 组件：卡片、按钮、标签、输入框、空状态、底部导航。

全部用 Kivy 原生控件手绘，不依赖 KivyMD，方便打包和保持体积。
"""
from __future__ import annotations

from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from . import theme as T


# ---------------------------------------------------------------- 文本
class WrapLabel(Label):
    """自动换行、高度随内容撑开的标签。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("font_name", T.FONT_NAME)
        kwargs.setdefault("font_size", sp(15))
        kwargs.setdefault("color", list(T.TEXT))
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "top")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("markup", False)
        super().__init__(**kwargs)
        self.text_size = (max(self.width, 100), None)
        self.bind(width=self._sync_size, texture_size=self._sync_size)
        self._sync_size()

    def _sync_size(self, *args):
        width = self.width if self.width > 1 else 100
        if tuple(self.text_size) != (width, None):
            self.text_size = (width, None)
        self.height = max(dp(18), self.texture_size[1])


class MutedLabel(WrapLabel):
    def __init__(self, **kwargs):
        kwargs.setdefault("font_size", sp(12.5))
        kwargs.setdefault("color", list(T.SUB))
        super().__init__(**kwargs)


class TitleLabel(Label):
    def __init__(self, **kwargs):
        kwargs.setdefault("font_name", T.FONT_NAME)
        kwargs.setdefault("font_size", sp(22))
        kwargs.setdefault("bold", True)
        kwargs.setdefault("color", list(T.TEXT))
        super().__init__(**kwargs)


class Card(BoxLayout):
    """白色圆角卡片。"""

    bg_color = ListProperty(list(T.CARD))
    radius = NumericProperty(dp(16))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*self.bg_color)
            self._rect = RoundedRectangle(radius=[self.radius])
        self.bind(pos=self._sync, size=self._sync, bg_color=self._sync_color, radius=self._sync_radius)
        self._sync()

    def _sync(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _sync_color(self, *args):
        self._color.rgba = self.bg_color

    def _sync_radius(self, *args):
        self._rect.radius = [self.radius]


class TapCard(ButtonBehavior, Card):
    """可点击的卡片，按下时轻微变色。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._base_bg = list(self.bg_color)
        self.bind(state=self._on_state)

    def _on_state(self, *args):
        if self.state == "down":
            self.bg_color = [c * 0.955 for c in self._base_bg[:3]] + [self._base_bg[3]]
        else:
            self.bg_color = self._base_bg


class PillButton(ButtonBehavior, Label):
    """圆角胶囊按钮。"""

    bg_color = ListProperty(list(T.PRIMARY))
    pressed_color = ListProperty(list(T.PRIMARY_DARK))
    autosize = BooleanProperty(False)
    pad_x = NumericProperty(dp(16))
    pad_y = NumericProperty(dp(9))

    def __init__(self, **kwargs):
        kwargs.setdefault("font_name", T.FONT_NAME)
        kwargs.setdefault("font_size", sp(15))
        kwargs.setdefault("color", list(T.WHITE))
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*self.bg_color)
            self._rect = RoundedRectangle(radius=[dp(999)])
        if self.autosize:
            self.size_hint = (None, None)
        self.bind(
            pos=self._sync,
            size=self._sync,
            bg_color=self._sync_color,
            state=self._sync_state,
        )
        self.bind(texture_size=self._fit)
        self._sync()
        self._fit()

    def _sync(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
        # 胶囊圆角取高度的一半，避免大圆角在宽按钮上变成椭圆
        self._rect.radius = [min(max(1.0, self.height) / 2.0, max(1.0, self.width) / 2.0)]
        if not self.autosize:
            desired = (max(1.0, self.width - self.pad_x * 0.6), None)
            if tuple(self.text_size) != desired:
                self.text_size = desired

    def _sync_color(self, *args):
        if self.state != "down":
            self._color.rgba = self.bg_color

    def _sync_state(self, *args):
        self._color.rgba = self.pressed_color if self.state == "down" else self.bg_color

    def _fit(self, *args):
        """自动宽度按钮：按文字纹理撑开（禁止换行，避免尺寸循环）。"""
        if not self.autosize:
            return
        tw, th = self.texture_size
        if tw <= 0:
            return
        width = tw + self.pad_x
        height = max(dp(38), th + self.pad_y)
        if abs(self.width - width) > 0.5:
            self.width = width
        if abs(self.height - height) > 0.5:
            self.height = height


class FilterChip(PillButton):
    """可切换的筛选标签。"""

    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("autosize", True)
        kwargs.setdefault("font_size", sp(13))
        kwargs.setdefault("pad_x", dp(14))
        kwargs.setdefault("pad_y", dp(7))
        super().__init__(**kwargs)
        self.bind(active=self._sync_active)
        self._sync_active()

    def _sync_active(self, *args):
        if self.active:
            self.bg_color = list(T.PRIMARY_SOFT)
            self.color = list(T.PRIMARY)
        else:
            self.bg_color = list(T.CHIP)
            self.color = list(T.SUB)


class Chip(Label):
    """只读的小标签（展示科目/标签/截止日期）。"""

    bg_color = ListProperty(list(T.CHIP))
    fg_color = ListProperty(list(T.SUB))

    def __init__(self, **kwargs):
        kwargs.setdefault("font_name", T.FONT_NAME)
        kwargs.setdefault("font_size", sp(11.5))
        kwargs.setdefault("color", self.fg_color)
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("padding", [dp(9), dp(4)])
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*self.bg_color)
            self._rect = RoundedRectangle(radius=[dp(999)])
        self.bind(
            pos=self._sync,
            size=self._sync,
            texture_size=self._fit,
            bg_color=self._sync_color,
        )
        self._fit()

    def _fit(self, *args):
        self.width = self.texture_size[0] + dp(18)
        self.height = max(dp(22), self.texture_size[1] + dp(8))

    def _sync(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._rect.radius = [max(1.0, self.height) / 2.0]

    def _sync_color(self, *args):
        self._color.rgba = self.bg_color


class HLine(Widget):
    """1dp 分隔线。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(1))
        super().__init__(**kwargs)
        with self.canvas:
            self._color = Color(*T.BORDER)
            self._line = Line(points=[self.x, self.y, self.right, self.y], width=1)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *args):
        self._line.points = [self.x, self.center_y, self.right, self.center_y]


class SectionHeader(BoxLayout):
    """小节标题 + 右侧操作。"""

    def __init__(self, title: str, action=None, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(34))
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)
        self._label = Label(
            text=title,
            font_name=T.FONT_NAME,
            font_size=sp(15),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
        )
        self._label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self._label)
        if action is not None:
            self.add_widget(action)
        else:
            self.add_widget(Widget())


class EmptyState(BoxLayout):
    """空列表提示。"""

    def __init__(self, title: str, subtitle: str = "", **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", [dp(24), dp(48)])
        kwargs.setdefault("spacing", dp(10))
        super().__init__(**kwargs)
        self.add_widget(
            Label(
                text=title,
                font_name=T.FONT_NAME,
                font_size=sp(17),
                bold=True,
                color=list(T.SUB),
                halign="center",
                valign="middle",
            )
        )
        if subtitle:
            lbl = MutedLabel(text=subtitle, halign="center", font_size=sp(13))
            lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
            self.add_widget(lbl)


class SearchBox(Card):
    """搜索框：圆角底 + 输入框 + 清除按钮。"""

    def __init__(self, hint: str = "搜索课件、题目、标签…", on_text=None, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(48))
        kwargs.setdefault("padding", [dp(14), dp(2), dp(6), dp(2)])
        kwargs.setdefault("spacing", dp(6))
        kwargs.setdefault("radius", dp(14))
        super().__init__(**kwargs)
        self.input = TextInput(
            hint_text=hint,
            font_name=T.FONT_NAME,
            font_size=sp(14.5),
            multiline=False,
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=list(T.TEXT),
            cursor_color=list(T.PRIMARY),
            hint_text_color=list(T.SUB),
            padding=[dp(2), dp(12), dp(2), dp(8)],
        )
        self.add_widget(self.input)
        self._clear = PillButton(
            text="×",
            font_size=sp(20),
            color=list(T.SUB),
            bg_color=[0, 0, 0, 0],
            pressed_color=list(T.CHIP),
            size_hint=(None, 1),
            width=dp(30),
        )
        self._clear.bind(on_release=self._clear_text)
        self.add_widget(self._clear)
        if on_text:
            self.input.bind(text=lambda w, v: on_text(v))

    def _clear_text(self, *args):
        self.input.text = ""


class NavItem(ButtonBehavior, BoxLayout):
    """底部导航项。"""

    icon = StringProperty("")
    label_text = StringProperty("")
    active = BooleanProperty(False)

    def __init__(self, icon: str = "", label_text: str = "", **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("spacing", dp(2))
        super().__init__(**kwargs)
        self.icon = icon
        self.label_text = label_text
        self._icon_lbl = Label(
            text=icon, font_name=T.FONT_NAME, font_size=sp(17), color=list(T.SUB)
        )
        self._text_lbl = Label(
            text=label_text, font_name=T.FONT_NAME, font_size=sp(11), color=list(T.SUB)
        )
        self.add_widget(self._icon_lbl)
        self.add_widget(self._text_lbl)
        self.bind(active=self._sync_active)
        self._sync_active()

    def _sync_active(self, *args):
        color = list(T.PRIMARY) if self.active else list(T.SUB)
        self._icon_lbl.color = color
        self._text_lbl.color = color


class NumBadge(Label):
    """题号圆形徽标（固定尺寸，数字用居中排版，避免尺寸循环）。"""

    def __init__(self, text: str = "", **kwargs):
        kwargs.setdefault("font_name", T.FONT_NAME)
        kwargs.setdefault("font_size", sp(12.5))
        kwargs.setdefault("bold", True)
        kwargs.setdefault("color", list(T.PRIMARY))
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("width", dp(34))
        kwargs.setdefault("height", dp(34))
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        super().__init__(**kwargs)
        if text:
            self.text = text
        self.text_size = (dp(34), None)
        with self.canvas.before:
            self._color = Color(*T.PRIMARY_SOFT)
            self._rect = RoundedRectangle(radius=[dp(17)])
        self.bind(pos=self._sync, size=self._sync)
        self._sync()

    def _sync(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._rect.radius = [min(max(1.0, self.width), max(1.0, self.height)) / 2.0]


class StarButton(ButtonBehavior, Label):
    """收藏星标。"""

    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("font_name", T.FONT_NAME)
        kwargs.setdefault("font_size", sp(20))
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("width", dp(38))
        kwargs.setdefault("height", dp(38))
        kwargs.setdefault("halign", "center")
        kwargs.setdefault("valign", "middle")
        super().__init__(**kwargs)
        self.bind(active=self._sync)
        self._sync()

    def _sync(self, *args):
        self.text = "★" if self.active else "☆"
        self.color = list(T.WARN) if self.active else list(T.SUB)


def toastable_clock(callback, delay=0.0):
    """把回调切回主线程执行。"""
    Clock.schedule_once(lambda dt: callback(), delay)
