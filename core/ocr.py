"""OCR 统一入口。

- 电脑（Windows/macOS/Linux）：RapidOCR + onnxruntime，本地离线。
- 安卓：native.android_ocr 调 Google ML Kit（中文，随包离线模型）。
两边都返回按阅读顺序排好的 OcrLine 列表。
"""
from __future__ import annotations

import os

from .layout import order_lines
from .models import OcrLine
from .paths import is_android


def _android_recognize(image_path: str) -> list[OcrLine]:
    from native.android_ocr import recognize_lines as native_recognize

    raw = native_recognize(image_path) or []
    lines: list[OcrLine] = []
    for item in raw:
        if isinstance(item, OcrLine):
            lines.append(item)
        elif isinstance(item, dict):
            lines.append(OcrLine.from_dict(item))
    return lines


def _desktop_recognize(image_path: str) -> list[OcrLine]:
    from .ocr_desktop import recognize_lines as desktop_recognize

    return desktop_recognize(image_path)


def recognize_lines(image_path: str) -> list[OcrLine]:
    """识别一张图片，返回按阅读顺序排序的行。"""
    if is_android():
        lines = _android_recognize(str(image_path))
    else:
        lines = _desktop_recognize(str(image_path))
    return order_lines(lines)


def ocr_available() -> tuple[bool, str]:
    """检查当前平台 OCR 是否可用，返回 (可用, 说明)。"""
    if is_android():
        try:
            import native.android_ocr as mod  # noqa: F401

            return True, "ML Kit（安卓离线）"
        except Exception as exc:  # pragma: no cover - 仅安卓分支
            return False, f"ML Kit 不可用：{exc}"
    try:
        import rapidocr_onnxruntime  # noqa: F401

        return True, "RapidOCR（本地离线）"
    except Exception:
        return False, "未安装 RapidOCR：pip install rapidocr-onnxruntime"


def engine_label() -> str:
    return "ML Kit" if is_android() else "RapidOCR"


def warmup() -> None:
    """提前加载模型（电脑端首次加载约 2~5 秒），避免首张图片等待过久。"""
    if is_android() or os.environ.get("COURSEKIT_SKIP_WARMUP"):
        return
    try:
        from .ocr_desktop import get_engine

        get_engine()
    except Exception:
        pass
