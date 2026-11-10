"""题目切分：从 OCR 文本行里按题号切出一道道题。

启发式规则（针对中文课件/作业）：
- 起始标记：1. 1、 1) （1） 一、 ① 第1题 等
- 选项行（A. B. C. D.）并入当前题
- "答案/解析/答：" 行作为题目答案
- 若整篇识别出的题块少于 2 个，认为不是题库型文档，不生成题目列表
"""
from __future__ import annotations

import re
from typing import Iterable

from .layout import lines_to_text
from .models import OcrLine, QuestionBlock

# 行首题目起始标记（按优先级）
_MARKERS: list[re.Pattern[str]] = [
    # ① ② ... ⑳
    re.compile(r"^\s*([①-⑳])\s*"),
    # （1） (1)
    re.compile(r"^\s*[（(]\s*(\d{1,3})\s*[)）]\s*"),
    # 第 1 题 / 第1题
    re.compile(r"^\s*(第\s*\d{1,3}\s*题)\s*[、.．:：]?\s*"),
    # 1. 1、 1) 1） —— 注意排除 1.5 这种小数
    re.compile(r"^\s*(\d{1,3})\s*(?:[、．)）]|[.])\s*(?!\d)"),
    # 一、 二、 三、
    re.compile(r"^\s*([一二三四五六七八九十百零]{1,3})\s*[、.．)）]\s*"),
]

# A. B. C. D. 选项行，不切题
_OPTION_RE = re.compile(r"^\s*[（(]?\s*[A-Ha-h]\s*[)）.、．]\s*\S")
# 答案/解析行
_ANSWER_RE = re.compile(r"^\s*(答案|答|解析|解|参考答案|分析)\s*[:：]?\s*")
# 噪声行：页码、页眉页脚、纯符号
_NOISE_RES = [
    re.compile(r"^\s*[-—–－]?\s*\d{1,3}\s*[-—–－]?\s*$"),
    re.compile(r"^\s*(第\s*\d+\s*页|共\s*\d+\s*页|Page\s*\d+.*)$", re.IGNORECASE),
    re.compile(r"^\s*[·．.…\-\s]+$"),
]

# 章节类标题（单独成行时不做题目，但保留在全文）
_SECTION_RE = re.compile(
    r"^\s*(?:[一二三四五六七八九十百零]{1,3}\s*[、.．]\s*)?"
    r"(?:选择题|填空题|判断题|单选题|多选题|简答题|计算题|解答题|证明题|"
    r"名词解释|论述题|案例分析|综合题|例题|习题|练习)\s*\d*\s*[：:、.．]?\s*$"
)


def _is_noise(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    return any(r.match(t) for r in _NOISE_RES)


def _match_marker(text: str) -> re.Match[str] | None:
    for pat in _MARKERS:
        m = pat.match(text)
        if m:
            return m
    return None


def _clean_number(marker: str) -> str:
    """把 "（ 3 ）" 之类的标记收敛成 "3" / "①"。"""
    s = marker.strip()
    s = re.sub(r"^第\s*", "", s)
    s = re.sub(r"\s*题\s*$", "", s)
    s = s.strip("()（）[]【】、.．:： ")
    return s


def split_questions(
    lines: Iterable[OcrLine] | Iterable[dict],
    min_questions: int = 2,
) -> list[QuestionBlock]:
    """按题号切分，返回题目块列表。"""
    prepared: list[OcrLine] = []
    for ln in lines:
        if isinstance(ln, OcrLine):
            prepared.append(ln)
        elif isinstance(ln, dict):
            prepared.append(OcrLine.from_dict(ln))
    prepared = [ln for ln in prepared if ln.text and ln.text.strip()]

    blocks: list[QuestionBlock] = []
    current: QuestionBlock | None = None

    for ln in prepared:
        text = ln.text.strip()
        if _is_noise(text):
            continue
        if _SECTION_RE.match(text):
            continue
        if _OPTION_RE.match(text):
            # 选项行永远属于当前题
            if current is not None:
                current.text += "\n" + text
            continue

        m = _match_marker(text)
        if m and not _OPTION_RE.match(text):
            remainder = text[m.end():].strip()
            # "1." 后面什么都没有，且很可能是分页/编号噪声，继续归到当前题
            if not remainder and current is not None:
                current.text += "\n" + text
                continue
            if current is not None:
                blocks.append(current)
            current = QuestionBlock(
                order_no=len(blocks) + 1,
                number=_clean_number(m.group(0)),
                text=remainder,
                page_no=ln.page,
            )
            continue

        if current is None:
            # 第一道题之前的说明文字，忽略（全文里仍保留）
            continue
        if _ANSWER_RE.match(text):
            current.answer = (current.answer + "\n" + text).strip()
        else:
            current.text = (current.text + "\n" + text).strip()

    if current is not None:
        blocks.append(current)

    # 清理：去掉正文为空或纯标点的题块
    cleaned: list[QuestionBlock] = []
    for b in blocks:
        body = b.text.strip()
        if not body or not re.search(r"[\w\u4e00-\u9fff]", body):
            continue
        b.text = body
        b.answer = b.answer.strip()
        b.order_no = len(cleaned) + 1
        cleaned.append(b)

    if len(cleaned) < max(1, int(min_questions)):
        return []
    return cleaned


def split_document_pages(pages: list[dict], min_questions: int = 2) -> list[QuestionBlock]:
    """多页文档统一切题（pages 元素含 lines_json/text/page_no）。"""
    all_lines: list[OcrLine] = []
    for page in pages:
        page_no = int(page.get("page_no", 1))
        raw_lines = page.get("lines") or []
        if raw_lines:
            for d in raw_lines:
                ln = OcrLine.from_dict(d) if isinstance(d, dict) else d
                ln.page = page_no
                all_lines.append(ln)
            continue
        for raw in str(page.get("text", "")).splitlines():
            if raw.strip():
                all_lines.append(OcrLine(text=raw.strip(), page=page_no))
    return split_questions(all_lines, min_questions=min_questions)


def questions_to_dicts(blocks: list[QuestionBlock]) -> list[dict]:
    return [
        {
            "order_no": b.order_no,
            "number": b.number,
            "text": b.text,
            "answer": b.answer,
            "page_no": b.page_no,
        }
        for b in blocks
    ]
