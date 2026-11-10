"""四个主界面：课件库（首页）、作业本、收藏夹、资料详情。"""
from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from . import theme as T
from . import utils
from .cards import DocCard, FavQuestionCard, HomeworkCard, QuestionCard
from .modals import (
    ConfirmModal,
    EditDocModal,
    ExportModal,
    HelpModal,
    HomeworkModal,
    ImportModal,
    MenuModal,
)
from .widgets import (
    Chip,
    EmptyState,
    FilterChip,
    HLine,
    MutedLabel,
    PillButton,
    SearchBox,
    TitleLabel,
    WrapLabel,
)


# ---------------------------------------------------------------- 首页
class HomeScreen(Screen):
    def __init__(self, app, **kwargs):
        kwargs.setdefault("name", "home")
        super().__init__(**kwargs)
        self.app = app
        self._subject = ""
        self._tag = ""
        self._favorites = False

        root = FloatLayout()
        main = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(8), dp(16), dp(6)],
            spacing=dp(9),
        )

        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(54), spacing=dp(8))
        titles = BoxLayout(orientation="vertical", spacing=dp(1))
        title = TitleLabel(text="课件通", font_size=sp(24))
        title.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.stats_lbl = MutedLabel(
            text="正在加载…", font_size=sp(11.5), size_hint_y=None, height=dp(16)
        )
        titles.add_widget(title)
        titles.add_widget(self.stats_lbl)
        header.add_widget(titles)
        help_btn = PillButton(
            text="?",
            font_size=sp(17),
            bold=True,
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(38),
        )
        help_btn.bind(on_release=lambda *a: HelpModal().open())
        header.add_widget(help_btn)
        main.add_widget(header)

        self.search = SearchBox(on_text=self._on_search)
        main.add_widget(self.search)

        self.chip_scroll = ScrollView(
            size_hint_y=None,
            height=dp(40),
            do_scroll_x=True,
            do_scroll_y=False,
            bar_width=0,
            scroll_type=["content"],
        )
        self.chip_box = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint=(None, None),
            height=dp(36),
        )
        self.chip_box.bind(minimum_width=self.chip_box.setter("width"))
        self.chip_scroll.add_widget(self.chip_box)
        main.add_widget(self.chip_scroll)

        self.list_scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.list_box = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.list_scroll.add_widget(self.list_box)
        main.add_widget(self.list_scroll)

        root.add_widget(main)
        self.fab = PillButton(
            text="＋",
            font_size=sp(26),
            bold=True,
            size_hint=(None, None),
            size=(dp(56), dp(56)),
            pos_hint={"right": 0.94, "y": 0.03},
        )
        self.fab.bind(on_release=lambda *a: ImportModal(on_choice=self._on_import_choice).open())
        root.add_widget(self.fab)
        self.add_widget(root)

    def on_pre_enter(self, *args):
        self.refresh()

    def _on_search(self, text: str):
        self.refresh(rebuild_chips=False)

    def refresh(self, rebuild_chips: bool = True):
        keyword = self.search.input.text.strip()
        try:
            docs = self.app.service.db.list_documents(
                keyword=keyword,
                subject=self._subject,
                tag=self._tag,
                favorite_only=self._favorites,
            )
            stats = self.app.service.stats()
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"读取数据失败：{exc}")
            docs, stats = [], {}
        self.list_box.clear_widgets()
        if not docs:
            if keyword:
                self.list_box.add_widget(
                    EmptyState("没有找到匹配的资料", "换个关键词，或点「全部」清除筛选条件")
                )
            else:
                self.list_box.add_widget(
                    EmptyState("还没有资料", "点右下角「＋」拍照、选图片或导入 PDF，开始整理课件")
                )
        else:
            for doc in docs:
                self.list_box.add_widget(DocCard(self.app, doc))
        if stats:
            self.stats_lbl.text = (
                f"{stats.get('documents', 0)} 份资料 · "
                f"{stats.get('questions', 0)} 道题 · "
                f"{stats.get('homework_pending', 0)} 项作业待完成"
            )
        if rebuild_chips:
            self._rebuild_chips()

    def _rebuild_chips(self):
        self.chip_box.clear_widgets()
        self._add_chip("全部", not self._subject and not self._tag and not self._favorites, self._clear_filters)
        self._add_chip("收藏", self._favorites, self._toggle_favorites)
        try:
            subjects = self.app.service.db.list_subjects()[:6]
            tags = self.app.service.db.list_tags()[:6]
        except Exception:
            subjects, tags = [], []
        for item in subjects:
            name = item["name"]
            self._add_chip(name, self._subject == name, lambda n=name: self._set_subject(n))
        for item in tags:
            name = item["name"]
            self._add_chip("#" + name, self._tag == name, lambda n=name: self._set_tag(n))

    def _add_chip(self, label: str, active: bool, callback):
        chip = FilterChip(text=label, active=active)
        chip.bind(on_release=lambda *a: callback())
        self.chip_box.add_widget(chip)

    def _clear_filters(self):
        self._subject = ""
        self._tag = ""
        self._favorites = False
        self.refresh()

    def _toggle_favorites(self):
        self._favorites = not self._favorites
        self.refresh()

    def _set_subject(self, name: str):
        self._subject = "" if self._subject == name else name
        self._tag = ""
        self.refresh()

    def _set_tag(self, name: str):
        self._tag = "" if self._tag == name else name
        self._subject = ""
        self.refresh()

    def _on_import_choice(self, mode: str, subject: str):
        if mode == "camera":
            self.app.take_photo(subject=subject)
        elif mode == "image":
            self.app.pick_file("image", subject=subject)
        else:
            self.app.pick_file("pdf", subject=subject)


# ---------------------------------------------------------------- 作业本
class HomeworkScreen(Screen):
    def __init__(self, app, **kwargs):
        kwargs.setdefault("name", "homework")
        super().__init__(**kwargs)
        self.app = app
        root = BoxLayout(
            orientation="vertical", padding=[dp(16), dp(8), dp(16), dp(6)], spacing=dp(9)
        )
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(54), spacing=dp(8))
        titles = BoxLayout(orientation="vertical", spacing=dp(1))
        title = TitleLabel(text="作业本", font_size=sp(24))
        title.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.summary = MutedLabel(text="", font_size=sp(11.5), size_hint_y=None, height=dp(16))
        titles.add_widget(title)
        titles.add_widget(self.summary)
        header.add_widget(titles)
        add_btn = PillButton(
            text="＋ 新建",
            font_size=sp(13.5),
            size_hint=(None, 1),
            width=dp(72),
        )
        add_btn.bind(on_release=lambda *a: self._add_homework())
        header.add_widget(add_btn)
        root.add_widget(header)

        self.list_scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.list_box = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)
        self.add_widget(root)

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):
        try:
            items = self.app.service.db.list_homework()
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"读取作业失败：{exc}")
            items = []
        pending = [h for h in items if not h.get("done")]
        overdue = [h for h in pending if (utils.days_until(h.get("due_date", "")) or 0) < 0]
        self.summary.text = f"待完成 {len(pending)} 项 · 已逾期 {len(overdue)} 项"
        self.list_box.clear_widgets()
        if not items:
            self.list_box.add_widget(
                EmptyState("还没有作业", "点右上角「＋ 新建」，或从资料详情里「设为作业」")
            )
            return
        for hw in items:
            self.list_box.add_widget(HomeworkCard(self.app, hw, self.refresh))

    def _add_homework(self):
        def save(title, subject, due, note):
            try:
                self.app.service.db.add_homework(
                    title=title, subject=subject, due_date=due, note=note
                )
                self.app.toast("作业已添加")
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                self.app.toast(f"添加失败：{exc}")

        HomeworkModal(on_save=save).open()


# ---------------------------------------------------------------- 收藏
class FavoritesScreen(Screen):
    def __init__(self, app, **kwargs):
        kwargs.setdefault("name", "favorites")
        super().__init__(**kwargs)
        self.app = app
        root = BoxLayout(
            orientation="vertical", padding=[dp(16), dp(8), dp(16), dp(6)], spacing=dp(9)
        )
        header = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(54), spacing=dp(1))
        title = TitleLabel(text="收藏夹", font_size=sp(24))
        title.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.summary = MutedLabel(text="重点题、错题都收在这里", font_size=sp(11.5), size_hint_y=None)
        header.add_widget(title)
        header.add_widget(self.summary)
        root.add_widget(header)

        self.list_scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.list_box = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)
        self.add_widget(root)

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):
        try:
            questions = self.app.service.db.list_questions(favorite_only=True)
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"读取收藏失败：{exc}")
            questions = []
        self.summary.text = f"已收藏 {len(questions)} 道题" if questions else "重点题、错题都收在这里"
        self.list_box.clear_widgets()
        if not questions:
            self.list_box.add_widget(
                EmptyState("还没有收藏题目", "在资料详情里点题目右侧的「☆」，就能收进这里")
            )
            return
        for question in questions:
            self.list_box.add_widget(FavQuestionCard(self.app, question))


# ---------------------------------------------------------------- 资料详情
class DocDetailScreen(Screen):
    def __init__(self, app, **kwargs):
        kwargs.setdefault("name", "detail")
        super().__init__(**kwargs)
        self.app = app
        self.doc_id = ""
        self.doc: dict | None = None
        self.tab = "text"

        root = BoxLayout(
            orientation="vertical", padding=[dp(14), dp(6), dp(14), dp(4)], spacing=dp(8)
        )
        # 顶栏
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(6))
        back = PillButton(
            text="<",
            font_size=sp(20),
            bold=True,
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.TEXT),
            size_hint=(None, 1),
            width=dp(36),
        )
        back.bind(on_release=lambda *a: self.app.navigate("home"))
        header.add_widget(back)
        self.title_lbl = Label(
            text="",
            font_name=T.FONT_NAME,
            font_size=sp(17),
            bold=True,
            color=list(T.TEXT),
            halign="left",
            valign="middle",
            size_hint_x=1,
            shorten=True,
            shorten_from="right",
        )
        self.title_lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        header.add_widget(self.title_lbl)
        self.star = PillButton(
            text="☆",
            font_size=sp(20),
            bg_color=[0, 0, 0, 0],
            pressed_color=list(T.CHIP),
            color=list(T.SUB),
            size_hint=(None, 1),
            width=dp(38),
        )
        self.star.bind(on_release=lambda *a: self._toggle_favorite())
        header.add_widget(self.star)
        menu_btn = PillButton(
            text="…",
            font_size=sp(20),
            bold=True,
            bg_color=list(T.CHIP),
            pressed_color=list(T.BORDER),
            color=list(T.TEXT),
            size_hint=(None, 1),
            width=dp(38),
        )
        menu_btn.bind(on_release=lambda *a: self._open_menu())
        header.add_widget(menu_btn)
        root.add_widget(header)

        self.meta_lbl = MutedLabel(text="", font_size=sp(11.5), size_hint_y=None)
        root.add_widget(self.meta_lbl)
        self.tags_lbl = MutedLabel(text="", font_size=sp(11.5), size_hint_y=None)
        root.add_widget(self.tags_lbl)
        self.due_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.due_box.bind(minimum_height=self.due_box.setter("height"))
        root.add_widget(self.due_box)

        tabs = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(38), spacing=dp(8))
        self.tab_text = FilterChip(text="全文", active=True)
        self.tab_text.bind(on_release=lambda *a: self._switch_tab("text"))
        self.tab_q = FilterChip(text="题目", active=False)
        self.tab_q.bind(on_release=lambda *a: self._switch_tab("questions"))
        tabs.add_widget(self.tab_text)
        tabs.add_widget(self.tab_q)
        tabs.add_widget(Widget())
        root.add_widget(tabs)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.content = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        root.add_widget(self.scroll)
        self.add_widget(root)

    # ---------------------------------------------------------- 加载
    def load(self, doc_id: str):
        self.doc_id = doc_id
        self.tab = "text"
        self._reload()

    def on_pre_enter(self, *args):
        if self.doc_id:
            self._reload()

    def _reload(self):
        if not self.doc_id:
            return
        try:
            self.doc = self.app.service.db.get_document(self.doc_id)
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"读取资料失败：{exc}")
            self.doc = None
            return
        if not self.doc:
            self.app.toast("资料不存在或已被删除")
            self.app.navigate("home")
            return
        self._rebuild()

    def _rebuild(self):
        doc = self.doc or {}
        self.title_lbl.text = str(doc.get("title", "未命名资料"))
        self.star.text = "★" if doc.get("favorite") else "☆"
        self.star.color = list(T.WARN) if doc.get("favorite") else list(T.SUB)

        meta_parts = []
        if doc.get("subject"):
            meta_parts.append(str(doc["subject"]))
        meta_parts.append(str(doc.get("created_at", ""))[:16])
        meta_parts.append(f"{doc.get('page_count', 0)} 页")
        meta_parts.append(f"{doc.get('question_count', 0)} 题")
        if doc.get("doc_type") == "pdf":
            meta_parts.append("PDF")
        self.meta_lbl.text = " · ".join(meta_parts)
        tags = doc.get("tags") or []
        self.tags_lbl.text = (" ".join(f"#{t}" for t in tags)) if tags else ""

        self._rebuild_due()
        self.tab_text.active = self.tab == "text"
        self.tab_q.active = self.tab == "questions"
        self._rebuild_content()

    def _rebuild_due(self):
        self.due_box.clear_widgets()
        doc = self.doc or {}
        hw_list = doc.get("homework") or []
        if hw_list:
            for hw in hw_list:
                row = BoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(28),
                    spacing=dp(6),
                )
                left = utils.days_until(hw.get("due_date", ""))
                if hw.get("done"):
                    fg, bg = list(T.OK), list(T.OK_SOFT)
                elif left is not None and left < 0:
                    fg, bg = list(T.DANGER), list(T.DANGER_SOFT)
                elif left is not None and left <= 2:
                    fg, bg = list(T.WARN), list(T.WARN_SOFT)
                else:
                    fg, bg = list(T.PRIMARY), list(T.PRIMARY_SOFT)
                chip = Chip(text="作业 · " + utils.due_text(hw.get("due_date", ""), bool(hw.get("done"))), fg_color=fg)
                chip.bg_color = bg
                chip.color = fg
                row.add_widget(chip)
                row.add_widget(Widget())
                self.due_box.add_widget(row)
        else:
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(32), spacing=dp(8))
            btn = PillButton(
                text="＋ 设为作业（设置截止日期）",
                bg_color=list(T.PRIMARY_SOFT),
                pressed_color=list(T.BORDER),
                color=list(T.PRIMARY),
                font_size=sp(12),
                autosize=True,
                pad_x=dp(12),
                pad_y=dp(5),
            )
            btn.bind(on_release=lambda *a: self._make_homework())
            row.add_widget(btn)
            row.add_widget(Widget())
            self.due_box.add_widget(row)

    def _rebuild_content(self):
        self.content.clear_widgets()
        if not self.doc:
            return
        if self.tab == "questions":
            questions = self.doc.get("questions") or []
            pages = {int(p.get("page_no", 0)): p.get("image_path", "") for p in self.doc.get("pages") or []}
            if not questions:
                self.content.add_widget(
                    EmptyState(
                        "没有识别到题目",
                        "这份资料可能是纯讲义。全文标签里仍能查看文字；也可以点右上角「…」→「重新切分题目」。",
                    )
                )
                return
            for question in questions:
                page_image = pages.get(int(question.get("page_no", 0)), "")
                self.content.add_widget(QuestionCard(self.app, question, page_image))
            return

        pages = self.doc.get("pages") or []
        if not pages:
            self.content.add_widget(EmptyState("没有内容", "这份资料还没有可显示的文字"))
            return
        for page in pages:
            head = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(24))
            head.add_widget(
                MutedLabel(text=f"第 {page.get('page_no', 0)} 页", font_size=sp(11.5))
            )
            self.content.add_widget(head)
            text = str(page.get("text", "")).strip()
            if text:
                self.content.add_widget(WrapLabel(text=text, font_size=sp(14)))
            else:
                self.content.add_widget(
                    MutedLabel(text="（本页没有识别到文字）", font_size=sp(12))
                )
            self.content.add_widget(HLine())

    # ---------------------------------------------------------- 操作
    def _switch_tab(self, tab: str):
        self.tab = tab
        self._rebuild()

    def _toggle_favorite(self):
        if not self.doc:
            return
        try:
            fav = self.app.service.db.toggle_document_favorite(self.doc_id)
            self.doc["favorite"] = fav
            self._rebuild()
            self.app.toast("已加入收藏" if fav else "已取消收藏")
        except Exception as exc:  # noqa: BLE001
            self.app.toast(f"操作失败：{exc}")

    def _open_menu(self):
        MenuModal(
            [
                ("导出 Markdown / Word / 文本", self._show_export),
                ("编辑标题 / 科目 / 标签", self._edit_doc),
                ("重新切分题目", self._resplit),
                ("设为作业 / 修改截止日期", self._make_homework),
                ("删除本资料", self._confirm_delete, True),
            ]
        ).open()

    def _show_export(self):
        ExportModal(on_choose=lambda fmt: self.app.export_doc(self.doc_id, fmt)).open()

    def _edit_doc(self):
        if not self.doc:
            return

        def save(title, subject, tags, note):
            self.app.update_doc(self.doc_id, title, subject, tags, note)

        EditDocModal(self.doc, on_save=save).open()

    def _resplit(self):
        def done(count):
            self.app.toast(
                f"已重新切分，得到 {count} 道题" if count else "没有识别到题号，可查看全文"
            )
            self._reload()

        self.app.toast("正在重新切分题目…")
        utils.run_in_thread(
            lambda: self.app.service.resplit(self.doc_id),
            on_done=done,
            on_error=lambda exc: self.app.toast(f"切分失败：{exc}"),
        )

    def _make_homework(self):
        doc = self.doc or {}

        def save(title, subject, due, note):
            self.app.service.db.add_homework(
                title=title or doc.get("title", "作业"),
                subject=subject,
                due_date=due,
                note=note,
                doc_id=self.doc_id,
            )
            self.app.toast("已设为作业")
            self._reload()

        HomeworkModal(
            on_save=save,
            title=str(doc.get("title", "")),
            subject=str(doc.get("subject", "")),
            due=utils.default_due(7),
        ).open()

    def _confirm_delete(self):
        def do_delete():
            self.app.delete_doc(self.doc_id)

        ConfirmModal(
            title="删除资料",
            message="删除后文字、题目和页面图片都会移除，无法恢复。确定删除吗？",
            on_confirm=do_delete,
            danger=True,
        ).open()
