"""SQLite 数据库访问层。

设计要点：
- 单一连接 + RLock，UI 线程和 OCR 工作线程可安全共用。
- 全文检索用 LIKE（中文按子串匹配），安卓内置 SQLite 也兼容。
- 文档 / 页面 / 题目 / 标签 / 作业五张主表，删除文档级联清理。
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    subject     TEXT NOT NULL DEFAULT '',
    doc_type    TEXT NOT NULL DEFAULT 'image',
    source_name TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    favorite    INTEGER NOT NULL DEFAULT 0,
    page_count  INTEGER NOT NULL DEFAULT 0,
    full_text   TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'done'
);

CREATE TABLE IF NOT EXISTS pages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     TEXT NOT NULL,
    page_no    INTEGER NOT NULL,
    image_path TEXT NOT NULL DEFAULT '',
    text       TEXT NOT NULL DEFAULT '',
    lines_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE (doc_id, page_no)
);

CREATE TABLE IF NOT EXISTS questions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id    TEXT NOT NULL,
    page_no   INTEGER NOT NULL DEFAULT 1,
    order_no  INTEGER NOT NULL DEFAULT 0,
    number    TEXT NOT NULL DEFAULT '',
    text      TEXT NOT NULL DEFAULT '',
    answer    TEXT NOT NULL DEFAULT '',
    favorite  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS doc_tags (
    doc_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (doc_id, tag_id)
);

CREATE TABLE IF NOT EXISTS homework (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     TEXT NOT NULL DEFAULT '',
    subject    TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL,
    due_date   TEXT NOT NULL DEFAULT '',
    done       INTEGER NOT NULL DEFAULT 0,
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pages_doc ON pages (doc_id);
CREATE INDEX IF NOT EXISTS idx_questions_doc ON questions (doc_id);
CREATE INDEX IF NOT EXISTS idx_questions_fav ON questions (favorite);
CREATE INDEX IF NOT EXISTS idx_docs_fav ON documents (favorite);
CREATE INDEX IF NOT EXISTS idx_docs_subject ON documents (subject);
CREATE INDEX IF NOT EXISTS idx_hw_due ON homework (due_date);
"""

DOC_FIELDS = (
    "title",
    "subject",
    "doc_type",
    "source_name",
    "page_count",
    "full_text",
    "note",
    "status",
    "favorite",
)
HW_FIELDS = ("doc_id", "subject", "title", "due_date", "done", "note")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _like(kw: str) -> str:
    """转义 LIKE 通配符，拼成 %kw%。"""
    kw = kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{kw}%"


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # ------------------------------------------------------------------ 基础
    def _q(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.conn.execute(sql, tuple(params)).fetchall())

    def _one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    def _w(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.execute(sql, tuple(params))
            self.conn.commit()
            return cur

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ 文档
    def add_document(
        self,
        doc_id: str,
        title: str,
        doc_type: str = "image",
        subject: str = "",
        source_name: str = "",
        pages: list[dict[str, Any]] | None = None,
        questions: list[dict[str, Any]] | None = None,
        tags: Iterable[str] | None = None,
        full_text: str = "",
        status: str = "done",
    ) -> None:
        ts = now_str()
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO documents
                   (id, title, subject, doc_type, source_name, created_at, updated_at,
                    favorite, page_count, full_text, note, status)
                   VALUES (?,?,?,?,?,?,?,0,?,?,?,?)""",
                (
                    doc_id,
                    title or "未命名",
                    subject or "",
                    doc_type,
                    source_name or "",
                    ts,
                    ts,
                    len(pages or []),
                    full_text or "",
                    "",
                    status,
                ),
            )
            self.conn.execute("DELETE FROM pages WHERE doc_id=?", (doc_id,))
            for p in pages or []:
                self.conn.execute(
                    """INSERT INTO pages (doc_id, page_no, image_path, text, lines_json)
                       VALUES (?,?,?,?,?)""",
                    (
                        doc_id,
                        int(p.get("page_no", 1)),
                        p.get("image_path", ""),
                        p.get("text", ""),
                        p.get("lines_json", "[]"),
                    ),
                )
            self.conn.execute("DELETE FROM questions WHERE doc_id=?", (doc_id,))
            self._insert_questions(doc_id, questions or [])
            self._apply_tags(doc_id, tags or [])
            self.conn.commit()

    def _insert_questions(self, doc_id: str, questions: list[dict[str, Any]]) -> None:
        for idx, q in enumerate(questions or []):
            self.conn.execute(
                """INSERT INTO questions (doc_id, page_no, order_no, number, text, answer, favorite)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    doc_id,
                    int(q.get("page_no", 1)),
                    int(q.get("order_no", idx)),
                    str(q.get("number", "")),
                    str(q.get("text", "")),
                    str(q.get("answer", "")),
                    int(q.get("favorite", 0) or 0),
                ),
            )

    def replace_questions(self, doc_id: str, questions: list[dict[str, Any]]) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM questions WHERE doc_id=?", (doc_id,))
            self._insert_questions(doc_id, questions)
            self.conn.commit()

    def update_document(self, doc_id: str, **fields: Any) -> None:
        data = {k: v for k, v in fields.items() if k in DOC_FIELDS}
        if not data:
            return
        data["updated_at"] = now_str()
        cols = ", ".join(f"{k}=?" for k in data)
        with self._lock:
            self.conn.execute(f"UPDATE documents SET {cols} WHERE id=?", (*data.values(), doc_id))
            self.conn.commit()

    def set_tags(self, doc_id: str, names: Iterable[str]) -> None:
        with self._lock:
            self._apply_tags(doc_id, names)
            self.conn.commit()

    def _apply_tags(self, doc_id: str, names: Iterable[str]) -> None:
        self.conn.execute("DELETE FROM doc_tags WHERE doc_id=?", (doc_id,))
        for raw in names or []:
            name = str(raw).strip()
            if not name:
                continue
            self.conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
            row = self.conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
            if row:
                self.conn.execute(
                    "INSERT OR IGNORE INTO doc_tags (doc_id, tag_id) VALUES (?,?)",
                    (doc_id, row["id"]),
                )

    def _tags_of(self, doc_id: str) -> list[str]:
        rows = self._q(
            """SELECT t.name FROM tags t
               JOIN doc_tags dt ON dt.tag_id = t.id
               WHERE dt.doc_id=? ORDER BY t.name""",
            (doc_id,),
        )
        return [r["name"] for r in rows]

    def get_document(
        self,
        doc_id: str,
        include_pages: bool = True,
        include_questions: bool = True,
    ) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM documents WHERE id=?", (doc_id,))
        if not row:
            return None
        doc = dict(row)
        doc["tags"] = self._tags_of(doc_id)
        if include_pages:
            pages = self._q("SELECT * FROM pages WHERE doc_id=? ORDER BY page_no", (doc_id,))
            doc["pages"] = [dict(p) for p in pages]
        if include_questions:
            qs = self._q(
                "SELECT * FROM questions WHERE doc_id=? ORDER BY order_no, id", (doc_id,)
            )
            doc["questions"] = [dict(q) for q in qs]
            doc["question_count"] = len(doc["questions"])
        hw = self._q("SELECT * FROM homework WHERE doc_id=? ORDER BY due_date", (doc_id,))
        doc["homework"] = [dict(h) for h in hw]
        return doc

    def list_documents(
        self,
        keyword: str = "",
        subject: str = "",
        tag: str = "",
        favorite_only: bool = False,
        doc_type: str = "",
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if keyword.strip():
            pat = _like(keyword.strip())
            where.append(
                "(d.title LIKE ? ESCAPE '\\' OR d.full_text LIKE ? ESCAPE '\\' "
                "OR d.subject LIKE ? ESCAPE '\\' "
                "OR EXISTS (SELECT 1 FROM questions q WHERE q.doc_id=d.id AND q.text LIKE ? ESCAPE '\\'))"
            )
            params += [pat, pat, pat, pat]
        if subject.strip():
            where.append("d.subject = ?")
            params.append(subject.strip())
        if favorite_only:
            where.append("d.favorite = 1")
        if doc_type.strip():
            where.append("d.doc_type = ?")
            params.append(doc_type.strip())
        if tag.strip():
            where.append(
                "EXISTS (SELECT 1 FROM doc_tags dt JOIN tags t ON t.id=dt.tag_id "
                "WHERE dt.doc_id=d.id AND t.name=?)"
            )
            params.append(tag.strip())
        sql = "SELECT d.* FROM documents d"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY d.updated_at DESC, d.created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        rows = self._q(sql, params)
        docs: list[dict[str, Any]] = []
        for r in rows:
            doc = dict(r)
            doc["tags"] = self._tags_of(doc["id"])
            cnt = self._one("SELECT COUNT(*) AS c FROM questions WHERE doc_id=?", (doc["id"],))
            doc["question_count"] = cnt["c"] if cnt else 0
            docs.append(doc)
        return docs

    def delete_document(self, doc_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM pages WHERE doc_id=?", (doc_id,))
            self.conn.execute("DELETE FROM questions WHERE doc_id=?", (doc_id,))
            self.conn.execute("DELETE FROM doc_tags WHERE doc_id=?", (doc_id,))
            self.conn.execute("DELETE FROM homework WHERE doc_id=?", (doc_id,))
            self.conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            self.conn.commit()

    def toggle_document_favorite(self, doc_id: str) -> int:
        row = self._one("SELECT favorite FROM documents WHERE id=?", (doc_id,))
        fav = 0 if not row else (0 if row["favorite"] else 1)
        self.update_document(doc_id, favorite=fav)
        return fav

    # ------------------------------------------------------------------ 题目
    def list_questions(
        self,
        keyword: str = "",
        favorite_only: bool = False,
        subject: str = "",
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if keyword.strip():
            pat = _like(keyword.strip())
            where.append("(q.text LIKE ? ESCAPE '\\' OR q.answer LIKE ? ESCAPE '\\')")
            params += [pat, pat]
        if favorite_only:
            where.append("q.favorite = 1")
        if subject.strip():
            where.append("d.subject = ?")
            params.append(subject.strip())
        sql = (
            "SELECT q.*, d.title AS doc_title, d.subject AS subject, d.doc_type AS doc_type "
            "FROM questions q JOIN documents d ON d.id = q.doc_id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY q.favorite DESC, d.updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        return [dict(r) for r in self._q(sql, params)]

    def toggle_question_favorite(self, question_id: int) -> int:
        row = self._one("SELECT favorite FROM questions WHERE id=?", (question_id,))
        fav = 0 if not row else (0 if row["favorite"] else 1)
        self._w("UPDATE questions SET favorite=? WHERE id=?", (fav, question_id))
        return fav

    def set_question_answer(self, question_id: int, answer: str) -> None:
        self._w("UPDATE questions SET answer=? WHERE id=?", (answer or "", question_id))

    # ------------------------------------------------------------------ 标签/科目
    def list_tags(self) -> list[dict[str, Any]]:
        rows = self._q(
            """SELECT t.name AS name, COUNT(dt.doc_id) AS count
               FROM tags t LEFT JOIN doc_tags dt ON dt.tag_id = t.id
               GROUP BY t.id ORDER BY count DESC, t.name"""
        )
        return [dict(r) for r in rows]

    def list_subjects(self) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT subject AS name, COUNT(*) AS count FROM documents "
            "WHERE subject <> '' GROUP BY subject ORDER BY count DESC, subject"
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ 作业
    def add_homework(
        self,
        title: str,
        subject: str = "",
        due_date: str = "",
        doc_id: str = "",
        note: str = "",
    ) -> int:
        cur = self._w(
            """INSERT INTO homework (doc_id, subject, title, due_date, done, note, created_at)
               VALUES (?,?,?,?,0,?,?)""",
            (doc_id or "", subject or "", title, due_date or "", note or "", now_str()),
        )
        return int(cur.lastrowid or 0)

    def update_homework(self, hw_id: int, **fields: Any) -> None:
        data = {k: v for k, v in fields.items() if k in HW_FIELDS}
        if not data:
            return
        cols = ", ".join(f"{k}=?" for k in data)
        self._w(f"UPDATE homework SET {cols} WHERE id=?", (*data.values(), hw_id))

    def delete_homework(self, hw_id: int) -> None:
        self._w("DELETE FROM homework WHERE id=?", (hw_id,))

    def list_homework(self, include_done: bool = True, keyword: str = "") -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if not include_done:
            where.append("done = 0")
        if keyword.strip():
            pat = _like(keyword.strip())
            where.append("(title LIKE ? ESCAPE '\\' OR subject LIKE ? ESCAPE '\\')")
            params += [pat, pat]
        sql = "SELECT * FROM homework"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY done ASC, due_date = '' ASC, due_date ASC, id DESC"
        return [dict(r) for r in self._q(sql, params)]

    # ------------------------------------------------------------------ 统计
    def stats(self) -> dict[str, int]:
        def count(sql: str) -> int:
            row = self._one(sql)
            return int(row[0]) if row else 0

        return {
            "documents": count("SELECT COUNT(*) FROM documents"),
            "questions": count("SELECT COUNT(*) FROM questions"),
            "favorite_docs": count("SELECT COUNT(*) FROM documents WHERE favorite=1"),
            "favorite_questions": count("SELECT COUNT(*) FROM questions WHERE favorite=1"),
            "homework_pending": count("SELECT COUNT(*) FROM homework WHERE done=0"),
            "tags": count("SELECT COUNT(*) FROM tags"),
        }
