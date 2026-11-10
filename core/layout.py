"""把 OCR 的行框按阅读顺序排好（行内从左到右，行间从上到下）。

RapidOCR 与 ML Kit 返回的框顺序不一定稳定，特别是拍照有倾斜时。
"""
from __future__ import annotations

from .models import OcrLine


def order_lines(lines: list[OcrLine]) -> list[OcrLine]:
    """返回按阅读顺序排序后的行列表。"""
    if not lines:
        return []
    items = [ln for ln in lines if ln.text and ln.text.strip()]
    if not items:
        return []

    heights = sorted(ln.height for ln in items if ln.height > 1)
    median_h = heights[len(heights) // 2] if heights else 12.0
    tol = max(6.0, median_h * 0.55)

    # 先按纵向中心排序，再按“属于同一行”聚簇
    items.sort(key=lambda ln: (ln.center_y, ln.x0))
    rows: list[list[OcrLine]] = []
    for ln in items:
        placed = False
        # 只和最近几行比较，避免误差累积
        for row in reversed(rows[-3:]):
            if abs(ln.center_y - row[0].center_y) <= tol:
                row.append(ln)
                placed = True
                break
        if not placed:
            rows.append([ln])

    ordered: list[OcrLine] = []
    for row in rows:
        row.sort(key=lambda ln: ln.x0)
        ordered.extend(row)
    return ordered


def lines_to_text(lines: list[OcrLine], sep: str = "\n") -> str:
    """行列表转纯文本。"""
    return sep.join(ln.text.strip() for ln in lines if ln.text and ln.text.strip())
