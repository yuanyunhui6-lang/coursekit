"""题目切分单元测试。"""
from core.layout import order_lines
from core.models import OcrLine, QuestionBlock
from core.split import split_document_pages, split_questions


def lines(*texts, page: int = 0):
    return [OcrLine(text=t, page=page) for t in texts]


def test_split_basic_numbering():
    blocks = split_questions(
        lines(
            "高等数学 第三章 习题",
            "1. 求下列函数的导数：y = x^2 + 3x",
            "2、计算定积分 ∫_0^1 x^2 dx",
            "3) 证明：sin^2 x + cos^2 x = 1",
        )
    )
    assert len(blocks) == 3
    assert blocks[0].number == "1"
    assert "x^2 + 3x" in blocks[0].text
    assert blocks[1].number == "2"
    assert blocks[2].number == "3"


def test_split_paren_and_chinese_markers():
    blocks = split_questions(
        lines(
            "（1）已知 A = {1,2,3}，求子集个数。",
            "（2）求 sin30° 的值。",
            "一、选择题",
            "1、下列正确的是（ ）",
            "A. 选项一",
            "B. 选项二",
        )
    )
    assert len(blocks) == 3
    assert blocks[0].number == "1"
    assert blocks[1].number == "2"
    assert "A. 选项一" in blocks[2].text
    assert "B. 选项二" in blocks[2].text


def test_decimal_not_treated_as_marker():
    blocks = split_questions(
        lines(
            "1. 计算 3.14 × 2",
            "2. 计算 1.5 + 2.5",
        )
    )
    assert len(blocks) == 2
    assert "3.14" in blocks[0].text
    assert "1.5" in blocks[1].text


def test_answer_line_attached():
    blocks = split_questions(
        lines(
            "1. 选择题：下列说法正确的是",
            "A. 甲",
            "B. 乙",
            "答案：B",
            "2. 填空题：1+1=____",
            "解析：显然等于 2",
        )
    )
    assert len(blocks) == 2
    assert "答案" in blocks[0].answer
    assert blocks[0].answer.startswith("答案：B")
    assert "解析" in blocks[1].answer


def test_single_question_dropped():
    """只有一个候选块时视为误判（课程幻灯片常见），不生成题库。"""
    blocks = split_questions(lines("1. 这是普通编号列表", "不是题目"))
    assert blocks == []


def test_noise_lines_ignored():
    blocks = split_questions(
        lines(
            "- 3 -",
            "第 2 页",
            "1. 第一题",
            "2. 第二题",
        )
    )
    assert len(blocks) == 2


def test_split_multipage_keeps_page_numbers():
    pages = [
        {"page_no": 1, "text": "1. 第一页第一题", "lines_json": "[]"},
        {"page_no": 2, "text": "2. 第二页第二题", "lines_json": "[]"},
    ]
    blocks = split_document_pages(pages)
    assert len(blocks) == 2
    assert blocks[0].page_no == 1
    assert blocks[1].page_no == 2


def test_order_lines_reading_order():
    raw = [
        OcrLine(text="second", x0=100, y0=10, x1=180, y1=30),
        OcrLine(text="first", x0=10, y0=11, x1=80, y1=31),
        OcrLine(text="third", x0=10, y0=60, x1=80, y1=80),
    ]
    ordered = order_lines(raw)
    assert [ln.text for ln in ordered] == ["first", "second", "third"]
