"""电脑端 OCR 实现：RapidOCR（onnxruntime，离线中文识别）。

首次调用会加载三个模型（检测/方向分类/识别），约 2~5 秒，之后复用单例。
"""
from __future__ import annotations

import threading

from .models import OcrLine

_engine = None
_engine_lock = threading.Lock()


def get_engine():
    """返回 RapidOCR 单例（线程安全）。"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR

                _engine = RapidOCR()
    return _engine


def _box_to_rect(box) -> tuple[float, float, float, float]:
    """RapidOCR 的 4 点框 -> 外接矩形。"""
    xs: list[float] = []
    ys: list[float] = []
    for point in box:
        try:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
        except (TypeError, ValueError, IndexError):
            continue
    if not xs or not ys:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def recognize_lines(image_path: str) -> list[OcrLine]:
    """识别图片，返回原始行（未排序）。"""
    engine = get_engine()
    result, _elapse = engine(str(image_path))
    lines: list[OcrLine] = []
    for item in result or []:
        try:
            box, text, score = item[0], item[1], item[2]
        except (TypeError, ValueError, IndexError):
            continue
        text = str(text or "").strip()
        if not text:
            continue
        try:
            if float(score) < 0.3:
                continue
        except (TypeError, ValueError):
            pass
        x0, y0, x1, y1 = _box_to_rect(box)
        lines.append(OcrLine(text=text, x0=x0, y0=y0, x1=x1, y1=y1))
    return lines
