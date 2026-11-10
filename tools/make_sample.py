"""生成示例课件图片（用于自测 OCR 和演示截图）。

用法：python tools/make_sample.py [输出目录]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_slide(path: Path) -> None:
    """模拟一张拍照的课件 PPT。"""
    img = Image.new("RGB", (1000, 1320), (250, 250, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1000, 120], fill=(233, 239, 252))
    draw.text((60, 34), "第三章  导数与微分", font=_font(44), fill=(27, 35, 51))

    rows = [
        ("一、选择题", 160, (44, 76, 160), 36),
        ("1. 函数 f(x)=x²+2x 的导数是（  ）", 240, (27, 35, 51), 34),
        ("A. 2x+2      B. x+2      C. 2x      D. x²", 296, (60, 66, 80), 30),
        ("2. 下列说法正确的是（  ）", 380, (27, 35, 51), 34),
        ("A. 可导必连续      B. 连续必可导", 436, (60, 66, 80), 30),
        ("3. 计算极限 lim(x→0) sin x / x", 520, (27, 35, 51), 34),
        ("二、填空题", 620, (44, 76, 160), 36),
        ("4. 若 y = ln x，则 y' = ______ 。", 700, (27, 35, 51), 34),
        ("5. 曲线 y=x³ 在点 (1,1) 处的切线斜率为 ______ 。", 780, (27, 35, 51), 34),
        ("三、解答题", 880, (44, 76, 160), 36),
        ("6. 证明：可导函数一定连续。", 960, (27, 35, 51), 34),
        ("答案：1.A  2.A  3.1  4.1/x  5.3", 1100, (31, 164, 107), 30),
    ]
    for text, top, color, size in rows:
        draw.text((60, top), text, font=_font(size), fill=color)

    # 模拟拍照的轻微暗角，让 OCR 更接近真实场景
    draw.rectangle([0, 0, 999, 1319], outline=(180, 180, 180), width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=92)


def make_homework(path: Path) -> None:
    img = Image.new("RGB", (900, 1200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((70, 50), "高等数学 作业（第三章）", font=_font(40), fill=(20, 20, 20))
    draw.text((70, 130), "姓名：__________    学号：__________", font=_font(28), fill=(40, 40, 40))
    lines = [
        "1. 求函数 y = x³ - 3x² + 2 的单调区间和极值。",
        "2. 计算定积分 ∫₀¹ (2x + 1) dx。",
        "3. 设 f(x) = e^{2x}，求 f'(x) 与 f''(x)。",
    ]
    top = 240
    for line in lines:
        draw.text((70, top), line, font=_font(30), fill=(25, 25, 25))
        top += 150
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=92)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples")
    make_slide(out / "sample_slide.jpg")
    make_homework(out / "sample_homework.jpg")
    print("已生成：", out / "sample_slide.jpg")
    print("已生成：", out / "sample_homework.jpg")
