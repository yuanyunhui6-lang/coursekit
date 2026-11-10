"""数据库层单元测试。"""
import pytest

from core.db import Database


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "coursekit.db")
    yield database
    database.close()


def _add(db: Database, doc_id="d1", title="高数第三章", subject="高等数学", tags=("期中", "重点")):
    db.add_document(
        doc_id=doc_id,
        title=title,
        doc_type="image",
        subject=subject,
        pages=[
            {"page_no": 1, "image_path": "/tmp/p1.png", "text": "1. 求导数", "lines_json": "[]"},
        ],
        questions=[
            {"order_no": 1, "number": "1", "text": "求导数", "answer": "", "page_no": 1},
        ],
        tags=tags,
        full_text="1. 求导数 y=x^2",
    )


def test_add_and_get(db):
    _add(db)
    doc = db.get_document("d1")
    assert doc is not None
    assert doc["title"] == "高数第三章"
    assert doc["subject"] == "高等数学"
    assert doc["page_count"] == 1
    assert doc["question_count"] == 1
    assert sorted(doc["tags"]) == ["期中", "重点"]
    assert doc["pages"][0]["text"].startswith("1.")


def test_list_and_filters(db):
    _add(db, "d1", "高数第三章", "高等数学")
    _add(db, "d2", "数据结构作业", "计算机", tags=("作业",))
    docs = db.list_documents()
    assert len(docs) == 2
    assert db.list_documents(subject="计算机")[0]["title"] == "数据结构作业"
    assert db.list_documents(tag="期中")[0]["id"] == "d1"
    assert db.list_documents(keyword="导数")[0]["id"] == "d1"  # 命中题目
    assert db.list_documents(favorite_only=True) == []


def test_favorites(db):
    _add(db)
    assert db.toggle_document_favorite("d1") == 1
    assert len(db.list_documents(favorite_only=True)) == 1
    question_id = db.get_document("d1")["questions"][0]["id"]
    assert db.toggle_question_favorite(question_id) == 1
    assert len(db.list_questions(favorite_only=True)) == 1
    assert db.stats()["favorite_questions"] == 1


def test_update_and_tags(db):
    _add(db)
    db.update_document("d1", title="改名后的资料", note="备注")
    db.set_tags("d1", ["期末", "易错"])
    doc = db.get_document("d1")
    assert doc["title"] == "改名后的资料"
    assert doc["note"] == "备注"
    assert sorted(doc["tags"]) == sorted(["期末", "易错"])
    assert {t["name"] for t in db.list_tags()} >= {"期末", "易错"}


def test_delete_cascades(db):
    _add(db)
    db.delete_document("d1")
    assert db.get_document("d1") is None
    assert db.list_questions() == []
    assert db.list_documents() == []


def test_homework_crud(db):
    day = "2030-01-01"
    hw_id = db.add_homework(title="第三章习题", subject="高数", due_date=day, doc_id="d1")
    items = db.list_homework()
    assert items[0]["title"] == "第三章习题"
    assert items[0]["due_date"] == day
    assert db.stats()["homework_pending"] == 1

    db.update_homework(hw_id, done=1, note="已交")
    assert db.list_homework(include_done=False) == []
    assert db.list_homework()[0]["done"] == 1
    db.delete_homework(hw_id)
    assert db.list_homework() == []


def test_search_escapes_wildcards(db):
    _add(db)
    assert db.list_documents(keyword="100%") == []  # 不能把 % 当通配符
    assert db.list_documents(keyword="导数")
