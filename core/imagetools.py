"""图片预处理：纠 EXIF 方向、统一转 RGB、限制最长边。

手机拍的照片通常 3000~4000 像素，直接 OCR 又慢又容易糊；
缩到最长边约 2200 像素在清晰度和速度之间比较平衡。
"""
from __future__ import annotations

from pathlib import Path

MAX_SIDE = 2200


def normalize_image(src: str | Path, dest: str | Path, max_side: int = MAX_SIDE) -> str:
    """把任意图片规范化后另存为 JPEG，返回目标路径。"""
    from PIL import Image, ImageOps

    src = Path(src)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = Image.open(src)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_side > 0:
            scale = max_side / float(max(w, h))
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        img.save(dest, "JPEG", quality=90)
    except Exception:
        # 兜底：直接复制原文件，交由 OCR 自行处理
        import shutil

        shutil.copyfile(src, dest)
    return str(dest)


def copy_original(src: str | Path, dest: str | Path) -> str:
    """原图另存（用于页面预览，保持清晰）。"""
    import shutil

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return str(dest)


def image_is_pdf(path: str | Path) -> bool:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return True
    try:
        with open(p, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False
