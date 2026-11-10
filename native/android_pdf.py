"""Android 端 PDF 渲染：用系统自带的 ``android.graphics.pdf.PdfRenderer`` 把 PDF 逐页转 PNG。

为什么不用 PyMuPDF？——PyMuPDF 没有可用的 python-for-android 配方，
安卓端由系统 PdfRenderer 负责渲染，避免把桌面依赖（PyMuPDF / opencv / numpy）
带进 APK。

对外接口（冻结）：

    render_pages(pdf_path: str, out_dir: str, max_side: int = 2000) -> list[str]

* 返回按页序排列的 PNG 文件路径列表，文件名 ``page_0001.png``、``page_0002.png`` ...
* 单页渲染失败会跳过该页继续下一页；整体失败返回 ``[]`` 或已渲染的部分。
* 非 Android 环境直接返回 ``[]``（由 core/ 层使用桌面 PDF 方案）。

坐标系说明：
    ``PdfRenderer.Page.getWidth()/getHeight()`` 返回的是 PDF 页面尺寸（单位 pt，
    1/72 英寸）。若直接用 ``page.render(bitmap, None, None, ...)``（恒等矩阵），
    页面只会画在位图左上角，且尺寸固定为 pt；所以要传入缩放的 ``Matrix``，
    位图尺寸 = 页面尺寸 × scale，视觉比例才正确。
"""

from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)

# 渲染比例上限：超过 2 倍对手机屏幕来说没有意义，只会白占内存。
_MAX_SCALE = 2.0
# 渲染比例下限：防止 max_side 参数异常导致位图变成 1x1。
_MIN_SCALE = 0.1
_DEFAULT_MAX_SIDE = 2000


def _is_android() -> bool:
    """是否运行在 Android（python-for-android）上。"""
    try:
        return bool(
            os.environ.get("ANDROID_ARGUMENT")
            or os.environ.get("ANDROID_PRIVATE")
            or os.sys.platform.startswith("android")
        )
    except Exception:
        return False


def _close_quietly(obj, name: str) -> None:
    """安静地关闭 Java 对象（close 失败不能影响主流程）。"""
    if obj is None:
        return
    try:
        obj.close()
    except Exception:
        _LOG.debug("关闭 %s 失败（可忽略）", name, exc_info=True)


def _recycle_quietly(bitmap) -> None:
    """安静地回收 Bitmap，避免大图占用内存。"""
    if bitmap is None:
        return
    try:
        bitmap.recycle()
    except Exception:
        _LOG.debug("回收 Bitmap 失败（可忽略）", exc_info=True)


def _render_on_android(pdf_path: str, out_dir: str, max_side: int) -> list[str]:
    """真正调用 PdfRenderer 的实现（只在 Android 上执行）。"""
    # 延迟导入：桌面环境没有 pyjnius，模块顶层导入会直接崩溃。
    from jnius import autoclass

    ParcelFileDescriptor = autoclass("android.os.ParcelFileDescriptor")
    PdfRenderer = autoclass("android.graphics.pdf.PdfRenderer")
    Page = autoclass("android.graphics.pdf.PdfRenderer$Page")
    Bitmap = autoclass("android.graphics.Bitmap")
    BitmapConfig = autoclass("android.graphics.Bitmap$Config")
    CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
    Matrix = autoclass("android.graphics.Matrix")
    Color = autoclass("android.graphics.Color")
    File = autoclass("java.io.File")
    FileOutputStream = autoclass("java.io.FileOutputStream")

    outputs: list[str] = []
    fd = None
    renderer = None
    try:
        fd = ParcelFileDescriptor.open(File(pdf_path), ParcelFileDescriptor.MODE_READ_ONLY)
        renderer = PdfRenderer(fd)
        page_count = int(renderer.getPageCount())
        _LOG.info("开始渲染 PDF：%s，共 %d 页", pdf_path, page_count)

        for index in range(page_count):
            page = None
            bitmap = None
            stream = None
            try:
                page = renderer.openPage(index)
                source_width = int(page.getWidth())
                source_height = int(page.getHeight())
                if source_width <= 0 or source_height <= 0:
                    _LOG.warning("第 %d 页尺寸异常（%dx%d），跳过", index + 1, source_width, source_height)
                    continue

                longest_side = float(max(source_width, source_height))
                scale = min(_MAX_SCALE, float(max_side) / longest_side)
                scale = max(_MIN_SCALE, scale)
                out_width = max(1, int(round(source_width * scale)))
                out_height = max(1, int(round(source_height * scale)))

                bitmap = Bitmap.createBitmap(out_width, out_height, BitmapConfig.ARGB_8888)
                # PDF 背景默认透明，先刷成白色，导出的 PNG 才适合直接做 OCR / 预览。
                bitmap.eraseColor(Color.WHITE)

                matrix = Matrix()
                matrix.setScale(scale, scale)
                page.render(bitmap, None, matrix, Page.RENDER_MODE_FOR_DISPLAY)

                out_path = os.path.join(out_dir, "page_%04d.png" % (index + 1))
                stream = FileOutputStream(File(out_path))
                if not bitmap.compress(CompressFormat.PNG, 100, stream):
                    raise IOError("Bitmap.compress 返回 False")
                stream.flush()
                outputs.append(out_path)
            except Exception:
                # 单页失败不影响其他页，继续渲染。
                _LOG.exception("渲染第 %d 页失败，已跳过", index + 1)
            finally:
                _close_quietly(stream, "FileOutputStream")
                _recycle_quietly(bitmap)
                _close_quietly(page, "PdfRenderer.Page")
    finally:
        _close_quietly(renderer, "PdfRenderer")
        _close_quietly(fd, "ParcelFileDescriptor")

    return outputs


def render_pages(pdf_path: str, out_dir: str, max_side: int = _DEFAULT_MAX_SIDE) -> list[str]:
    """把 PDF 每一页渲染成 PNG 写入 ``out_dir``（阻塞式，建议在后台线程调用）。

    参数:
        pdf_path: 本地 PDF 路径（App 私有目录，例如系统文件选择器复制过来的文件）。
        out_dir: 输出目录，不存在会自动创建。
        max_side: 输出图片最长边上限（像素），默认 2000。

    返回:
        list[str]，PNG 路径列表，按页序排列；任何失败返回 ``[]`` 或已渲染的部分。
    """
    try:
        input_path = os.fspath(pdf_path) if pdf_path is not None else ""
    except Exception:
        input_path = ""
    if not input_path:
        _LOG.warning("PDF 渲染跳过：路径为空")
        return []
    if not os.path.isfile(input_path):
        _LOG.warning("PDF 渲染跳过：文件不存在 %s", input_path)
        return []
    if not _is_android():
        _LOG.info("PDF 渲染跳过：当前不是 Android 环境，请由 core/ 层使用桌面 PDF 方案")
        return []

    try:
        max_side_value = int(max_side)
    except Exception:
        max_side_value = _DEFAULT_MAX_SIDE
    if max_side_value <= 0:
        max_side_value = _DEFAULT_MAX_SIDE

    try:
        output_dir = os.fspath(out_dir) if out_dir is not None else ""
    except Exception:
        output_dir = ""
    if not output_dir:
        _LOG.warning("PDF 渲染跳过：输出目录为空")
        return []

    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception:
        _LOG.exception("创建 PDF 渲染输出目录失败：%s", output_dir)
        return []

    try:
        return _render_on_android(input_path, output_dir, max_side_value)
    except Exception:
        _LOG.exception("PDF 渲染失败（已捕获）：%s", input_path)
        return []
