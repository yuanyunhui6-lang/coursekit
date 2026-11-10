"""Android 端离线中文 OCR：通过 pyjnius 调用 Google ML Kit。

依赖（见 ``buildozer.spec``）：

* ``android.gradle_dependencies = com.google.mlkit:text-recognition-chinese:16.0.0``
* ``android.enable_androidx = True``

``text-recognition-chinese`` 是「随包模型」版本，中文识别模型直接打进 APK，
安装后完全离线可用，不需要联网下载模型。

线程模型（务必理解）：

    ML Kit 的 ``Task`` 回调（``addOnSuccessListener`` / ``addOnFailureListener``）
    会被投递到 Android 主线程（UI 线程）的 Looper 上执行。
    所以绝不能在该主线程上同步等待回调（会死锁）。
    ``recognize_lines()`` 是**阻塞式**函数，必须在 Kivy 的后台线程中调用，例如::

        threading.Thread(target=do_ocr, daemon=True).start()

    本模块内部用 ``threading.Event`` 等待识别完成，并带超时保护；
    超时后返回空列表并记录日志，不会让 App 卡死。

对外接口（冻结）：

    recognize_lines(image_path: str) -> list[dict]
        每项形如
        {"text": str, "x0": float, "y0": float, "x1": float, "y1": float}，
        按阅读顺序排列（行：自上而下，同一行内自左向右）。
"""

from __future__ import annotations

import logging
import os
import threading

_LOG = logging.getLogger(__name__)

# 单张图片识别的最长等待时间（秒）。超时说明回调没有回到主线程，
# 与其无限等待，不如返回空列表让上层走别的路径。
_TASK_TIMEOUT_SECONDS = 60.0

# 超时后 ML Kit 仍可能回调（此时监听器对象不能被 GC 回收，否则 JNI 会崩溃），
# 这里保留少量强引用。
_KEEP_ALIVE: list = []
_KEEP_ALIVE_MAX = 8


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


def _keep_alive(obj) -> None:
    """把对象临时强引用住，避免 Java 回调还在队列里时 Python 对象被回收。"""
    try:
        _KEEP_ALIVE.append(obj)
        del _KEEP_ALIVE[:-_KEEP_ALIVE_MAX]
    except Exception:
        pass


def _sort_reading_order(lines: list[dict]) -> list[dict]:
    """把 ML Kit 返回的行按阅读顺序排序。

    ML Kit 的 ``getTextBlocks()`` 顺序基本可信，但多栏/贴图混排时并不稳定。
    这里做一次兜底排序：

    1. 先按每行垂直中心从上到下排；
    2. 垂直中心相差不足半行高的行视为「同一行」，再按左边界从左到右排。
    """
    if not lines:
        return []

    # 用行高的中位数作为「同一行」的容差基准，抗噪声。
    heights = sorted(max(1.0, float(item["y1"]) - float(item["y0"])) for item in lines)
    median_height = heights[len(heights) // 2]
    row_tolerance = max(8.0, median_height * 0.6)

    ordered = sorted(
        lines,
        key=lambda item: (float(item["y0"]) + float(item["y1"])) / 2.0,
    )

    rows: list[dict] = []
    for line in ordered:
        center_y = (float(line["y0"]) + float(line["y1"])) / 2.0
        if rows and abs(center_y - rows[-1]["center_y"]) <= row_tolerance:
            rows[-1]["lines"].append(line)
        else:
            rows.append({"center_y": center_y, "lines": [line]})

    result: list[dict] = []
    for row in rows:
        result.extend(sorted(row["lines"], key=lambda item: float(item["x0"])))
    return result


def _parse_mlkit_text(result) -> list[dict]:
    """把 ML Kit 的 Text 对象解析成本模块约定的行列表。

    注意：Java 的 ``List`` 在 pyjnius 里不保证支持 for-in 迭代，
    因此统一用 ``.size()`` + ``.get(i)`` 访问。
    """
    lines: list[dict] = []
    try:
        blocks = result.getTextBlocks()
    except Exception:
        _LOG.exception("读取 ML Kit 文本块失败")
        return []

    if blocks is None:
        return []

    try:
        block_count = int(blocks.size())
    except Exception:
        _LOG.exception("文本块列表异常（size() 失败）")
        return []

    for block_index in range(block_count):
        try:
            block = blocks.get(block_index)
            if block is None:
                continue
            block_lines = block.getLines()
            if block_lines is None:
                continue
            for line_index in range(int(block_lines.size())):
                line = block_lines.get(line_index)
                if line is None:
                    continue
                text = line.getText()
                if not text:
                    continue
                box = line.getBoundingBox()
                if box is None:
                    # 极少数情况没有包围盒，跳过该行，避免返回无效坐标。
                    continue
                lines.append(
                    {
                        "text": str(text),
                        "x0": float(box.left),
                        "y0": float(box.top),
                        "x1": float(box.right),
                        "y1": float(box.bottom),
                    }
                )
        except Exception:
            _LOG.exception("解析第 %d 个文本块失败，跳过该块", block_index)

    return _sort_reading_order(lines)


def _recognize_on_android(image_path: str) -> list[dict]:
    """真正调用 ML Kit 的实现（只在 Android 上执行）。"""
    # 延迟导入：桌面环境没有 pyjnius，模块顶层导入会直接崩溃。
    from jnius import PythonJavaClass, autoclass, java_method

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    activity = PythonActivity.mActivity
    if activity is None:
        _LOG.error("OCR 失败：当前 Activity 为空（App 可能已退到后台）")
        return []

    File = autoclass("java.io.File")
    Uri = autoclass("android.net.Uri")
    InputImage = autoclass("com.google.mlkit.vision.common.InputImage")
    TextRecognition = autoclass("com.google.mlkit.vision.text.TextRecognition")
    ChineseOptionsBuilder = autoclass(
        "com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions$Builder"
    )

    # 图片来自 App 私有目录（拍照/选择器复制后的文件），File URI 可安全使用。
    image_uri = Uri.fromFile(File(image_path))
    try:
        input_image = InputImage.fromFilePath(activity, image_uri)
    except Exception:
        # pyjnius 对重载方法的解析在不同版本上可能有差异，
        # fromFilePath 还有一个带 rotationDegrees 的三参重载，这里兜底重试一次。
        _LOG.warning("InputImage.fromFilePath(context, uri) 失败，尝试带旋转参数的重载", exc_info=True)
        input_image = InputImage.fromFilePath(activity, image_uri, 0)

    if input_image is None:
        _LOG.error("OCR 失败：无法从文件解码图片 %s", image_path)
        return []

    recognizer = None
    try:
        options = ChineseOptionsBuilder().build()
        recognizer = TextRecognition.getClient(options)
    except Exception:
        # pyjnius 的重载解析在不同 p4a/pyjnius 版本上偶有差异，
        # 这里退回默认识别器（拉丁语模型）保证不崩，只是中文效果会明显下降。
        _LOG.exception("创建中文 OCR 识别器失败，退回默认识别器（中文识别质量会下降）")
        recognizer = TextRecognition.getClient()

    holder = {"lines": [], "error": None, "done": threading.Event()}

    class _SuccessListener(PythonJavaClass):
        """ML Kit Task 成功回调（Java 接口 com.google.android.gms.tasks.OnSuccessListener）。"""

        __javainterfaces__ = ["com/google/android/gms/tasks/OnSuccessListener"]
        __javacontext__ = "app"

        @java_method("(Ljava/lang/Object;)V")
        def onSuccess(self, result):
            # 回调运行在 Java 线程，这里抛异常会直接让进程崩溃，必须全部吞掉。
            try:
                holder["lines"] = _parse_mlkit_text(result)
            except Exception as exc:
                holder["error"] = exc
                _LOG.exception("解析 ML Kit 识别结果失败")
            finally:
                holder["done"].set()

    class _FailureListener(PythonJavaClass):
        """ML Kit Task 失败回调（Java 接口 com.google.android.gms.tasks.OnFailureListener）。"""

        __javainterfaces__ = ["com/google/android/gms/tasks/OnFailureListener"]
        __javacontext__ = "app"

        @java_method("(Ljava/lang/Exception;)V")
        def onFailure(self, exception):
            try:
                holder["error"] = exception
                _LOG.error("ML Kit OCR 任务失败：%s", exception)
            finally:
                holder["done"].set()

    success_listener = _SuccessListener()
    failure_listener = _FailureListener()

    try:
        task = recognizer.process(input_image)
        task.addOnSuccessListener(success_listener)
        task.addOnFailureListener(failure_listener)

        if not holder["done"].wait(_TASK_TIMEOUT_SECONDS):
            _LOG.error(
                "OCR 超时（等待 %.0f 秒）：识别结果没有回到回调，"
                "请确认调用线程不是 Android 主线程",
                _TASK_TIMEOUT_SECONDS,
            )
            # 超时后不再关闭 recognizer，交给 GC + 强引用列表保底，避免 JNI 崩溃。
            _keep_alive((recognizer, success_listener, failure_listener, holder))
            return []

        if holder["error"] is not None:
            return []
        return holder["lines"] or []
    finally:
        if holder["done"].is_set():
            try:
                recognizer.close()
            except Exception:
                _LOG.debug("关闭 OCR 识别器时出错（可忽略）", exc_info=True)


def recognize_lines(image_path: str) -> list[dict]:
    """识别图片中的中文文字，按阅读顺序返回行列表（阻塞式）。

    参数:
        image_path: 本地图片文件路径（建议是 App 私有目录下的文件）。

    返回:
        list[dict]，每项 ``{"text", "x0", "y0", "x1", "y1"}``。
        任何失败（非 Android 环境、文件不存在、识别异常、超时）都返回 ``[]``。

    警告:
        必须在后台线程调用；在 Android 主线程调用会阻塞 UI 甚至死锁。
    """
    try:
        path = os.fspath(image_path) if image_path is not None else ""
    except Exception:
        path = ""

    if not path:
        _LOG.warning("OCR 跳过：图片路径为空")
        return []
    if not os.path.isfile(path):
        _LOG.warning("OCR 跳过：图片文件不存在 %s", path)
        return []
    if not _is_android():
        _LOG.info("OCR 跳过：当前不是 Android 环境，请由 core/ 层使用桌面 OCR 方案")
        return []

    try:
        return _recognize_on_android(path)
    except Exception:
        _LOG.exception("OCR 识别失败（已捕获，返回空列表）：%s", path)
        return []
