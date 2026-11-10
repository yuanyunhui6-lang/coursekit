"""课件通 Android 原生能力封装包（native）。

本包把 Android 平台相关的能力封装成桌面上安全的 Python 接口：

* 离线中文 OCR（ML Kit）
* PDF 逐页渲染为 PNG（PdfRenderer）
* 导出文件到手机「下载」目录（MediaStore）
* 运行时权限申请
* 系统文件选择器 / 系统相机拍照

设计约定（非常重要）：

1. 所有模块顶层只导入标准库；``pyjnius`` / ``android`` 模块一律在函数内部延迟导入。
   因此在桌面（Windows / Linux / macOS）上 ``import native`` 或导入任一子模块
   都不会崩溃，也不会触发任何 Android 专有依赖。
2. 非 Android 环境调用这些函数时会记录日志并返回空结果
   （``[]`` / ``None`` / 回调 ``None``），由 ``core/`` 层决定是否退回桌面实现
   （RapidOCR、PyMuPDF 等）。
3. 回调（callback）最终都在 Kivy 主线程执行；耗时操作（文件复制、OCR）在后台线程完成，
   具体线程模型见各模块文档字符串。

冻结的对外接口（core/service.py 依赖，签名不要再改）：

    native.android_ocr.recognize_lines(image_path) -> list[dict]
    native.android_pdf.render_pages(pdf_path, out_dir, max_side=2000) -> list[str]
    native.android_export.save_to_downloads(filename, data, mime) -> str | None
    native.android_permissions.ensure_permissions(callback=None)
    native.android_picker.pick_document(callback, mime="*/*", allow_multiple=False) -> None
    native.android_picker.take_photo(callback) -> None
"""

from __future__ import annotations

import os
import sys

__version__ = "0.1.0"

__all__ = ["is_android", "__version__"]


def is_android() -> bool:
    """判断当前是否运行在 Android（python-for-android）设备上。

    python-for-android 启动器会设置 ``ANDROID_ARGUMENT`` / ``ANDROID_PRIVATE``
    等环境变量，这比 ``sys.platform`` 更可靠：p4a 里 ``sys.platform`` 一般是
    ``"linux"``，不能用来区分桌面 Linux 和 Android。
    """
    try:
        if os.environ.get("ANDROID_ARGUMENT") or os.environ.get("ANDROID_PRIVATE"):
            return True
        return sys.platform.startswith("android")
    except Exception:  # 防御式：判断环境本身不能抛异常
        return False
