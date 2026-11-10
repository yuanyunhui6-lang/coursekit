"""课件通 App 主类：窗口、字体、底部导航、导入/导出等全局操作。"""
from __future__ import annotations

import os
import traceback

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, ScreenManager

from core.paths import is_android
from core.service import Service

from . import theme as T
from . import utils
from .modals import FilePickerPopup, ProcessingModal
from .screens import DocDetailScreen, FavoritesScreen, HomeworkScreen, HomeScreen
from .widgets import Card, HLine, NavItem


class CourseKitApp(App):
    """应用主类：手机 / 电脑共用一套界面。"""

    title = "课件通"

    # ------------------------------------------------------------ 构建
    def build(self):
        T.register_fonts()
        Window.clearcolor = list(T.BG)
        if is_android():
            try:
                Window.softinput_mode = "below_target"
            except Exception:
                pass

        self.service = Service()
        self._toast_widget = None
        self._native_picker = None
        self._init_native_picker()

        root = BoxLayout(orientation="vertical")
        self.sm = ScreenManager(transition=NoTransition())
        self.home = HomeScreen(self)
        self.homework = HomeworkScreen(self)
        self.favorites = FavoritesScreen(self)
        self.detail = DocDetailScreen(self)
        for screen in (self.home, self.homework, self.favorites, self.detail):
            self.sm.add_widget(screen)
        root.add_widget(self.sm)
        root.add_widget(HLine())
        root.add_widget(self._nav_bar())
        return root

    def _nav_bar(self):
        bar = Card(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(58),
            padding=[dp(10), dp(2)],
            spacing=dp(4),
            radius=0,
            bg_color=list(T.CARD),
        )
        self.nav_home = NavItem(icon="课", label_text="课件")
        self.nav_hw = NavItem(icon="作", label_text="作业")
        self.nav_fav = NavItem(icon="★", label_text="收藏")
        self.nav_home.bind(on_release=lambda *a: self.navigate("home"))
        self.nav_hw.bind(on_release=lambda *a: self.navigate("homework"))
        self.nav_fav.bind(on_release=lambda *a: self.navigate("favorites"))
        for item in (self.nav_home, self.nav_hw, self.nav_fav):
            item.size_hint_x = 1
            bar.add_widget(item)
        return bar

    def _init_native_picker(self):
        if not is_android():
            return
        try:
            import native.android_picker as picker  # noqa: F401

            self._native_picker = picker
        except Exception:
            self._native_picker = None

    # ------------------------------------------------------------ 生命周期
    def on_start(self):
        self._sync_nav()
        try:
            self.home.refresh()
        except Exception:
            traceback.print_exc()
        Window.bind(on_keyboard=self._on_keyboard)
        if is_android():
            Clock.schedule_once(lambda dt: self._request_android_permissions(), 0.4)
        else:
            utils.run_in_thread(self._warmup_ocr)

    def _warmup_ocr(self):
        try:
            from core.ocr import warmup

            warmup()
        except Exception:
            pass

    def _request_android_permissions(self):
        try:
            from native.android_permissions import ensure_permissions

            ensure_permissions()
        except Exception:
            pass

    def on_pause(self):
        return True

    def on_stop(self):
        try:
            Window.unbind(on_keyboard=self._on_keyboard)
        except Exception:
            pass
        try:
            self.service.close()
        except Exception:
            pass

    def _on_keyboard(self, window, key, *args):
        if key == 27:  # 安卓返回键 / 桌面 Esc
            if self.sm.current != "home":
                self.navigate("home")
                return True
        return False

    # ------------------------------------------------------------ 导航
    def navigate(self, name: str):
        if name not in ("home", "homework", "favorites", "detail"):
            name = "home"
        if self.sm.current != name:
            self.sm.current = name
        self._sync_nav()

    def _sync_nav(self):
        current = self.sm.current
        self.nav_home.active = current in ("home", "detail")
        self.nav_hw.active = current == "homework"
        self.nav_fav.active = current == "favorites"

    def open_doc(self, doc_id: str):
        if not doc_id:
            return
        self.detail.load(doc_id)
        self.sm.current = "detail"
        self._sync_nav()

    # ------------------------------------------------------------ 导入
    def pick_file(self, mode: str, subject: str = ""):
        mime = {"image": "image/*", "pdf": "application/pdf", "any": "*/*"}.get(mode, "*/*")
        if self._native_picker is not None and hasattr(self._native_picker, "pick_document"):
            def callback(path):
                if path:
                    self._import_path(path, subject=subject)
                else:
                    self.toast("已取消选择")

            try:
                self._native_picker.pick_document(callback, mime=mime)
                return
            except Exception:
                pass
        FilePickerPopup(
            mode=mode,
            on_select=lambda path: self._import_path(path, subject=subject),
        ).open()

    def take_photo(self, subject: str = ""):
        if self._native_picker is not None and hasattr(self._native_picker, "take_photo"):
            def callback(path):
                if path:
                    self._import_path(path, subject=subject, is_photo=True)
                else:
                    self.toast("已取消拍照")

            try:
                self._native_picker.take_photo(callback)
                return
            except Exception as exc:
                self.toast(f"相机启动失败：{str(exc)[:40]}")
                return
        self.toast("当前设备不支持直接拍照，请用「相册 / 图片」导入")

    def _import_path(self, path: str, subject: str = "", is_photo: bool = False):
        if not path or not os.path.exists(path):
            self.toast("文件不存在或无法读取")
            return
        modal = ProcessingModal()
        modal.open()

        def progress(done, total, message):
            Clock.schedule_once(
                lambda dt, d=done, t=total, m=message: modal.update(d, t, m), 0
            )

        def work():
            return self.service.import_file(
                path, subject=subject, is_photo=is_photo, progress=progress
            )

        def done(result):
            modal.dismiss()
            self.toast(
                f"已导入「{result['title']}」，识别到 {result['question_count']} 道题"
            )
            try:
                self.home.refresh()
            except Exception:
                pass
            self.open_doc(result["doc_id"])

        def error(exc):
            modal.dismiss()
            self.toast(f"导入失败：{str(exc)[:60]}")

        utils.run_in_thread(work, on_done=done, on_error=error)

    # ------------------------------------------------------------ 资料操作
    def update_doc(self, doc_id: str, title: str, subject: str, tags, note: str):
        try:
            self.service.db.update_document(
                doc_id, title=title, subject=subject, note=note
            )
            self.service.db.set_tags(doc_id, tags)
            self.toast("资料已更新")
        except Exception as exc:  # noqa: BLE001
            self.toast(f"保存失败：{str(exc)[:40]}")
            return
        try:
            self.detail._reload()  # noqa: SLF001 - 详情页自身刷新
            self.home.refresh()
        except Exception:
            pass

    def export_doc(self, doc_id: str, fmt: str):
        self.toast("正在生成导出文件…")

        def work():
            return self.service.export(doc_id, fmt)

        def done(result):
            if is_android():
                self.toast(f"已保存到手机「下载」：{result['filename']}")
            else:
                self.toast(f"已导出：{result['path']}")

        utils.run_in_thread(
            work, on_done=done, on_error=lambda exc: self.toast(f"导出失败：{str(exc)[:50]}")
        )

    def delete_doc(self, doc_id: str):
        try:
            self.service.delete_document(doc_id)
        except Exception as exc:  # noqa: BLE001
            self.toast(f"删除失败：{str(exc)[:50]}")
            return
        self.detail.doc_id = ""
        self.detail.doc = None
        self.toast("资料已删除")
        try:
            self.home.refresh()
        except Exception:
            pass
        self.navigate("home")

    def refresh_favorites(self):
        try:
            self.favorites.refresh()
        except Exception:
            pass
        try:
            self.home.refresh()
        except Exception:
            pass

    # ------------------------------------------------------------ 轻提示
    def toast(self, text: str, duration: float = 2.8):
        """底部浮层提示，自动消失。"""
        if not text:
            return
        self._remove_toast()
        width = min(Window.width * 0.88, dp(420))
        card = Card(
            orientation="vertical",
            size_hint=(None, None),
            width=width,
            height=dp(44),
            padding=[dp(14), dp(8)],
            radius=dp(18),
            bg_color=[0.11, 0.13, 0.18, 0.94],
        )
        label = Label(
            text=str(text),
            font_name=T.FONT_NAME,
            font_size=sp(13),
            color=[1, 1, 1, 1],
            size_hint=(None, None),
            halign="center",
            valign="middle",
        )
        label.text_size = (width - dp(28), None)
        card.add_widget(label)
        self._toast_widget = card
        Window.add_widget(card)

        def fit(*_args):
            label.height = max(dp(20), label.texture_size[1])
            label.width = width - dp(28)
            card.height = label.height + dp(16)
            card.pos = (Window.width / 2.0 - width / 2.0, dp(86))

        label.bind(texture_size=lambda *a: Clock.schedule_once(lambda dt: fit(), 0))
        Clock.schedule_once(lambda dt: fit(), 0)
        Clock.schedule_once(lambda dt: self._remove_toast(card), duration)

    def _remove_toast(self, widget=None):
        current = getattr(self, "_toast_widget", None)
        if current is None:
            return
        if widget is not None and widget is not current:
            return
        try:
            Window.remove_widget(current)
        except Exception:
            pass
        self._toast_widget = None
