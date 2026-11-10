"""核心数据结构（纯 Python，便于单测）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OcrLine:
    """一行识别结果，坐标基于原图/页图像素。"""

    text: str
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    page: int = 0

    @property
    def height(self) -> float:
        return abs(self.y1 - self.y0)

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "x0": round(self.x0, 1),
            "y0": round(self.y0, 1),
            "x1": round(self.x1, 1),
            "y1": round(self.y1, 1),
            "page": self.page,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OcrLine":
        return cls(
            text=str(d.get("text", "")),
            x0=float(d.get("x0", 0) or 0),
            y0=float(d.get("y0", 0) or 0),
            x1=float(d.get("x1", 0) or 0),
            y1=float(d.get("y1", 0) or 0),
            page=int(d.get("page", 0) or 0),
        )


@dataclass
class PageResult:
    """一页 OCR/文本结果。"""

    page_no: int
    image_path: str = ""
    text: str = ""
    lines: list[OcrLine] = field(default_factory=list)


@dataclass
class QuestionBlock:
    """切分出来的一道题。"""

    order_no: int
    number: str
    text: str
    answer: str = ""
    page_no: int = 1


def confidence_ok(score: Any, minimum: float = 0.35) -> bool:
    """OCR 置信度过滤（不同引擎返回格式不一）。"""
    try:
        return float(score) >= minimum
    except (TypeError, ValueError):
        return True
