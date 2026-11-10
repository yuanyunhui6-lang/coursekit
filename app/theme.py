"""视觉主题：配色、字体、尺寸。

深色模式暂不做，浅色更适合看课件、导出打印。
"""
from __future__ import annotations

import os

from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex

# 主色板（浅色系）
BG = get_color_from_hex("#F3F5FA")
CARD = get_color_from_hex("#FFFFFF")
TEXT = get_color_from_hex("#1B2333")
SUB = get_color_from_hex("#68738A")
PRIMARY = get_color_from_hex("#2C64DB")
PRIMARY_DARK = get_color_from_hex("#1E4CAE")
PRIMARY_SOFT = get_color_from_hex("#E9EFFC")
BORDER = get_color_from_hex("#E2E6EF")
CHIP = get_color_from_hex("#EFF1F6")
DANGER = get_color_from_hex("#D64545")
DANGER_SOFT = get_color_from_hex("#FCEBEB")
WARN = get_color_from_hex("#E2951E")
WARN_SOFT = get_color_from_hex("#FDF3E2")
OK = get_color_from_hex("#1FA46B")
OK_SOFT = get_color_from_hex("#E7F6EF")
WHITE = [1.0, 1.0, 1.0, 1.0]

FONT_NAME = "CJK"

# 中文字体候选：Windows / Android / Linux
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/DroidSansFallbackFull.ttf",
    "/system/fonts/DroidSansFallback.ttf",
    "/system/fonts/NotoSansCJKsc-Regular.otf",
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/NotoSansSC-Regular.otf",
    "/system/fonts/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]


def register_fonts() -> str:
    """注册中文字体；同时覆盖 Kivy 默认字体族名，避免中文变方框。"""
    from kivy.core.text import LabelBase

    for path in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            LabelBase.register(name="CJK", fn_regular=path)
            LabelBase.register(name="Roboto", fn_regular=path)
            return path
        except Exception:
            continue
    return ""


def rgba(color, alpha: float):
    """调整透明度，返回新的颜色列表。"""
    return [color[0], color[1], color[2], alpha]
