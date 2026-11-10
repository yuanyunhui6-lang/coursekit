"""系统文件选择器（SAF）与系统相机拍照（异步接口，供 UI 调用）。

为什么需要这个模块？
    Android 10+ 的分区存储下，直接按路径读取别处的 PDF / 图片很可能失败。
    通过 ``ACTION_OPEN_DOCUMENT``（Storage Access Framework）让用户自己选文件，
    系统会把读取权限临时授予本 App，从而**不依赖存储权限**就能读取「下载」里的 PDF；
    拍照则用 MediaStore 生成 ``content://`` 输出 URI，避免 ``Uri.fromFile``
    在 Android 7+ 抛 FileUriExposedException。

对外接口（冻结，UI 端这样调用）::

    from native.android_picker import pick_document, take_photo

    pick_document(lambda path: ..., mime="application/pdf")
    take_photo(lambda path: ...)

回调协议（callback 只会被调用一次）：

    * 成功：``callback(local_path)``，local_path 是 App 私有临时目录
      （``$ANDROID_PRIVATE/tmp/``）下已复制完成的文件路径，可直接打开/OCR；
    * 取消、失败、超时：``callback(None)``；
    * ``pick_document(..., allow_multiple=True)`` 且用户真的选了多个文件时，
      ``callback`` 会收到 ``list[str]``（单文件仍然是 ``str``）；
    * 回调在 **Kivy 主线程** 执行（内部用 ``Clock.schedule_once`` 调度），
      回调里不要做耗时操作，把路径交给自己的后台线程处理。

线程模型：
    ``on_activity_result`` 由 Android 主线程触发，本模块在回调里只取出 URI，
    真正的文件复制放到后台线程，复制完成后通过 Kivy Clock 把结果送回主线程。
    这样既不会阻塞 UI，也保证回调线程安全。
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time

_LOG = logging.getLogger(__name__)

_RESULT_OK = -1
_RESULT_CANCELED = 0

# startActivityForResult 的 requestCode 只支持 16 位（0~65535）。
# 从 0x4100 开始递增，尽量避开第三方库常用的 0/1/2 等值。
_REQUEST_CODE_BASE = 0x4100
_REQUEST_CODE_MAX = 0x7EFF
_next_request_code = _REQUEST_CODE_BASE

# request_code -> 请求信息（callback / kind / extra / timer）
_REQUESTS: dict = {}
_REQUESTS_LOCK = threading.RLock()
_bound = False

# 系统界面超过这个时间还没回来，就认为请求丢失（例如 Activity 被回收），
# 主动回调 None 并清理，避免回调永远不触发。
_CALLBACK_TIMEOUT_SECONDS = 600.0

# 私有临时目录里的文件保留多久（秒）；超过后在新一次复制时顺手清理。
_TMP_MAX_AGE_SECONDS = 24 * 3600


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
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


def _safe_call(callback, value) -> None:
    """执行回调并吞掉回调自身的异常（不能把异常抛给 Java 线程）。"""
    if callback is None:
        return
    try:
        callback(value)
    except Exception:
        _LOG.exception("选择器回调执行出错（已捕获）")


def _deliver(callback, value) -> None:
    """把结果送到 Kivy 主线程回调。

    优先通过 ``kivy.clock.Clock`` 调度（主线程事件循环）；
    Kivy 不可用时退回直接调用（桌面调试场景）。
    """
    if callback is None:
        return
    try:
        from kivy.clock import Clock

        Clock.schedule_once(lambda _dt: _safe_call(callback, value), 0)
        return
    except Exception:
        _LOG.warning("无法通过 Kivy Clock 调度回调，改在当前线程调用", exc_info=True)

    _safe_call(callback, value)


def _get_activity():
    """获取当前 Android Activity（Java 对象）。"""
    from jnius import autoclass

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    activity = PythonActivity.mActivity
    if activity is None:
        raise RuntimeError("无法获取当前 Activity（App 可能已退到后台）")
    return activity


def _get_android_activity_module():
    """获取 python-for-android 的 ``android.activity`` 事件模块。"""
    from android import activity as android_activity

    return android_activity


# ---------------------------------------------------------------------------
# 请求注册 / 解绑 / 超时 / 结果分发
# ---------------------------------------------------------------------------
def _on_activity_result(request_code, result_code, intent) -> None:
    """系统界面返回时的统一入口（Android 主线程）。"""
    with _REQUESTS_LOCK:
        request = _REQUESTS.pop(request_code, None)
        if request is not None:
            _unbind_if_idle_locked()
    if request is None:
        # 不是本模块发起的请求（可能是其他库的），直接忽略。
        return

    _cancel_timer(request)

    try:
        if result_code != _RESULT_OK:
            _LOG.info("用户在系统界面取消了操作（%s）", request["kind"])
            if request["kind"] == "camera":
                _delete_media_uri(request["extra"].get("camera_uri"))
            _deliver(request["callback"], None)
            return

        uris = _extract_result_uris(request, intent)
        if not uris:
            _LOG.warning("系统没有返回可用的文件（%s）", request["kind"])
            if request["kind"] == "camera":
                _delete_media_uri(request["extra"].get("camera_uri"))
            _deliver(request["callback"], None)
            return

        # 复制文件可能耗时（PDF 动辄几 MB），放到后台线程，不阻塞主线程。
        worker = threading.Thread(
            target=_copy_and_finish,
            args=(request, uris),
            name="coursekit-picker-copy",
            daemon=True,
        )
        worker.start()
    except Exception:
        _LOG.exception("处理系统返回结果失败（%s）", request["kind"])
        _deliver(request["callback"], None)


def _unbind_if_idle_locked() -> None:
    """没有未完成请求时解绑 on_activity_result，避免全局回调泄漏。"""
    global _bound
    if _REQUESTS or not _bound:
        return
    try:
        _get_android_activity_module().unbind(on_activity_result=_on_activity_result)
        _bound = False
    except Exception:
        _LOG.exception("解绑 on_activity_result 失败")


def _ensure_bound_locked() -> None:
    """第一次发起请求时绑定 on_activity_result（只绑一次）。"""
    global _bound
    if _bound:
        return
    _get_android_activity_module().bind(on_activity_result=_on_activity_result)
    _bound = True


def _cancel_timer(request) -> None:
    """取消超时定时器。"""
    timer = request.get("timer") if request else None
    if timer is None:
        return
    try:
        timer.cancel()
    except Exception:
        pass


def _expire(request_code) -> None:
    """超时未收到系统返回：清理请求并回调 None。"""
    with _REQUESTS_LOCK:
        request = _REQUESTS.pop(request_code, None)
        if request is not None:
            _unbind_if_idle_locked()
    if request is None:
        return
    _LOG.warning("等待系统界面返回超时（code=%s），回调 None", request_code)
    if request["kind"] == "camera":
        _delete_media_uri(request["extra"].get("camera_uri"))
    _deliver(request["callback"], None)


def _register(kind: str, callback, extra: dict | None = None):
    """注册一次系统界面请求，返回 requestCode；失败返回 None（并回调 None）。"""
    global _next_request_code
    try:
        with _REQUESTS_LOCK:
            _ensure_bound_locked()
    except Exception:
        _LOG.exception("绑定 on_activity_result 失败，无法启动系统界面")
        _deliver(callback, None)
        return None

    stale_callbacks = []
    request = {
        "kind": kind,
        "callback": callback,
        "extra": dict(extra or {}),
        "timer": None,
    }

    with _REQUESTS_LOCK:
        # 同类请求只保留最新的一个：旧请求立即回调 None，
        # 避免用户连点两次导致旧结果“串台”或回调重复。
        for code in [c for c, req in _REQUESTS.items() if req["kind"] == kind]:
            stale = _REQUESTS.pop(code, None)
            if stale is not None:
                stale_callbacks.append(stale)
        if stale_callbacks:
            _LOG.warning("同类请求（%s）重复发起，已取消 %d 个旧请求", kind, len(stale_callbacks))

        _next_request_code += 1
        if _next_request_code > _REQUEST_CODE_MAX:
            _next_request_code = _REQUEST_CODE_BASE
        while _next_request_code in _REQUESTS:
            _next_request_code += 1
        request_code = _next_request_code
        _REQUESTS[request_code] = request

    for stale in stale_callbacks:
        _cancel_timer(stale)
        _deliver(stale["callback"], None)

    timer = threading.Timer(_CALLBACK_TIMEOUT_SECONDS, _expire, args=(request_code,))
    timer.daemon = True
    request["timer"] = timer
    timer.start()
    return request_code


def _finish_without_activity(request_code, value) -> None:
    """启动系统界面失败时，手动结束该请求（保证回调只触发一次）。"""
    with _REQUESTS_LOCK:
        request = _REQUESTS.pop(request_code, None)
        if request is not None:
            _unbind_if_idle_locked()
    if request is None:
        return
    _cancel_timer(request)
    if request["kind"] == "camera":
        _delete_media_uri(request["extra"].get("camera_uri"))
    _deliver(request["callback"], value)


# ---------------------------------------------------------------------------
# 结果解析与文件复制
# ---------------------------------------------------------------------------
def _extract_result_uris(request, intent) -> list:
    """从 on_activity_result 的 Intent 中取出文件 URI 列表。"""
    if request["kind"] == "camera":
        uri = request["extra"].get("camera_uri")
        return [uri] if uri is not None else []

    if intent is None:
        return []

    uris = []
    # 多选时结果在 ClipData 里；单选时在 getData()。
    try:
        clip_data = intent.getClipData()
    except Exception:
        clip_data = None
    if clip_data is not None:
        try:
            for index in range(int(clip_data.getItemCount())):
                item = clip_data.getItemAt(index)
                if item is None:
                    continue
                uri = item.getUri()
                if uri is not None:
                    uris.append(uri)
        except Exception:
            _LOG.exception("读取多选文件列表失败")

    if not uris:
        try:
            uri = intent.getData()
        except Exception:
            uri = None
        if uri is not None:
            uris.append(uri)

    return uris


def _copy_and_finish(request, uris) -> None:
    """后台线程：把选中的 URI 复制到私有临时目录，再回调主线程。"""
    local_paths = []
    try:
        mime = str(request["extra"].get("mime") or "")
        for uri in uris:
            path = _copy_uri_to_private(uri, mime=mime)
            if path:
                local_paths.append(path)
        if not local_paths:
            raise RuntimeError("所有文件复制均失败")
    except Exception:
        _LOG.exception("复制系统返回的文件失败（%s）", request["kind"])
        _deliver(request["callback"], None)
        return

    result = local_paths[0] if len(local_paths) == 1 else local_paths
    _deliver(request["callback"], result)


def _private_tmp_dir(activity=None) -> str:
    """App 私有临时目录：``$ANDROID_PRIVATE/tmp``（不存在则创建）。"""
    base = os.environ.get("ANDROID_PRIVATE")
    if not base and activity is not None:
        try:
            base = str(activity.getFilesDir().getAbsolutePath())
        except Exception:
            base = None
    if not base:
        import tempfile

        base = tempfile.gettempdir()

    tmp_dir = os.path.join(base, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    return tmp_dir


def _cleanup_old_tmp(tmp_dir: str) -> None:
    """清理私有临时目录里超过保留期的旧文件（防止越积越多）。"""
    try:
        now = time.time()
        for name in os.listdir(tmp_dir):
            path = os.path.join(tmp_dir, name)
            try:
                if os.path.isfile(path) and now - os.path.getmtime(path) > _TMP_MAX_AGE_SECONDS:
                    os.remove(path)
            except Exception:
                continue
    except Exception:
        _LOG.debug("清理临时文件失败（可忽略）", exc_info=True)


def _guess_extension(mime: str) -> str:
    """根据 MIME 猜一个扩展名（URI 文件名没有后缀时使用）。"""
    value = (mime or "").lower()
    if "pdf" in value:
        return ".pdf"
    if "jpeg" in value or "jpg" in value:
        return ".jpg"
    if "png" in value:
        return ".png"
    if "webp" in value:
        return ".webp"
    if "word" in value or "docx" in value:
        return ".docx"
    if "markdown" in value:
        return ".md"
    return ".bin"


def _guess_local_name(uri, mime: str = "") -> str:
    """从 URI 取一个安全的本地文件名（保留中文，去掉路径分隔符）。"""
    raw = ""
    try:
        segment = uri.getLastPathSegment()
        raw = str(segment) if segment else ""
    except Exception:
        raw = ""

    name = os.path.basename(raw.replace("\\", "/")).strip()
    # 只保留字母/数字/下划线/点/横线/中文，避免出现奇怪字符。
    name = re.sub(r"[^\w.\-]", "_", name)
    if not name:
        name = "coursekit_picked"
    if "." not in name:
        name += _guess_extension(mime)
    return name


def _copy_uri_to_private(uri, mime: str = "") -> str:
    """把 content:// URI 指向的文件复制到 App 私有临时目录，返回本地路径。

    优先用 ``ContentResolver.openFileDescriptor`` 拿到文件描述符，
    再在 Python 侧用 ``os.read`` 按块复制（比 Java InputStream 逐字节读快得多）；
    个别 ContentProvider 不支持 fd 时退回 InputStream 逐字节读取。
    """
    activity = _get_activity()
    resolver = activity.getContentResolver()
    tmp_dir = _private_tmp_dir(activity)
    local_path = os.path.join(
        tmp_dir, "%d_%s" % (int(time.time() * 1000), _guess_local_name(uri, mime))
    )

    copied = False
    descriptor = None
    try:
        descriptor = resolver.openFileDescriptor(uri, "r")
        if descriptor is not None:
            file_descriptor = int(descriptor.getFd())
            with open(local_path, "wb") as file_obj:
                while True:
                    chunk = os.read(file_descriptor, 65536)
                    if not chunk:
                        break
                    file_obj.write(chunk)
            copied = True
    except Exception:
        _LOG.exception("通过文件描述符复制失败，尝试 InputStream 回退方案")
    finally:
        if descriptor is not None:
            try:
                descriptor.close()
            except Exception:
                _LOG.debug("关闭 ParcelFileDescriptor 失败（可忽略）", exc_info=True)

    if not copied:
        _copy_via_input_stream(resolver, uri, local_path)

    _cleanup_old_tmp(tmp_dir)

    if not os.path.isfile(local_path):
        raise IOError("复制后的文件不存在：%s" % local_path)
    return local_path


def _copy_via_input_stream(resolver, uri, local_path: str) -> None:
    """兜底方案：InputStream 逐字节读（慢，但兼容性最好）。"""
    stream = resolver.openInputStream(uri)
    if stream is None:
        raise IOError("openInputStream 返回空")
    try:
        with open(local_path, "wb") as file_obj:
            while True:
                value = stream.read()
                if value == -1:
                    break
                file_obj.write(bytes((value,)))
    finally:
        try:
            stream.close()
        except Exception:
            _LOG.debug("关闭 InputStream 失败（可忽略）", exc_info=True)


# ---------------------------------------------------------------------------
# 媒体库辅助（拍照用的 content:// URI）
# ---------------------------------------------------------------------------
def _insert_camera_image(activity):
    """在 MediaStore 里插入一张待拍摄图片记录，返回 content:// URI。"""
    from jnius import autoclass

    BuildVersion = autoclass("android.os.Build$VERSION")
    sdk_int = int(BuildVersion.SDK_INT)
    resolver = activity.getContentResolver()
    Images = autoclass("android.provider.MediaStore$Images")
    MediaColumns = autoclass("android.provider.MediaStore$MediaColumns")
    ContentValues = autoclass("android.content.ContentValues")
    Environment = autoclass("android.os.Environment")
    File = autoclass("java.io.File")

    display_name = "coursekit_%s.jpg" % time.strftime("%Y%m%d_%H%M%S")
    values = ContentValues()
    values.put(MediaColumns.DISPLAY_NAME, display_name)
    values.put(MediaColumns.MIME_TYPE, "image/jpeg")

    if sdk_int >= 29:
        try:
            values.put(
                MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_PICTURES + "/CourseKit",
            )
        except Exception:
            _LOG.warning("当前系统不支持 RELATIVE_PATH，照片将放在图片根目录", exc_info=True)
    else:
        # Android 9 及以下：MediaStore 需要 DATA 列指向真实文件路径。
        try:
            pictures_dir = Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_PICTURES
            )
            target_dir = File(pictures_dir, "CourseKit")
            if not target_dir.exists():
                target_dir.mkdirs()
            target_file = File(target_dir, display_name)
            values.put("_data", str(target_file.getAbsolutePath()))
        except Exception:
            _LOG.exception("构造旧版本图片路径失败，继续尝试 MediaStore 默认行为")

    uri = resolver.insert(Images.EXTERNAL_CONTENT_URI, values)
    if uri is None:
        raise RuntimeError("MediaStore.insert 返回空 URI")
    return uri


def _delete_media_uri(uri) -> None:
    """删除拍照时插入的 MediaStore 记录（用户取消/失败时用）。"""
    if uri is None:
        return
    try:
        _get_activity().getContentResolver().delete(uri, None, None)
    except Exception:
        _LOG.debug("删除 MediaStore 记录失败（可忽略）", exc_info=True)


# ---------------------------------------------------------------------------
# 对外接口 1：选择文件（PDF / 图片 / 任意文档）
# ---------------------------------------------------------------------------
def pick_document(callback, mime: str = "*/*", allow_multiple: bool = False) -> None:
    """打开系统文件选择器，让用户挑一个文件（或图片/PDF）。

    Android 10+ 通过 SAF 的临时授权读文件，不需要存储权限。

    参数:
        callback: ``callback(local_path)``，取消/失败时 ``callback(None)``；
                  只在 Kivy 主线程被调用一次。
        mime: MIME 过滤，例如 ``"application/pdf"``、``"image/*"``；
              默认 ``"*/*"``。
        allow_multiple: 是否允许一次选多个文件；为 True 且确实选了多个时，
                        回调参数是 ``list[str]``。

    返回:
        无（异步）。启动失败也会回调 ``callback(None)``。
    """
    if not _is_android():
        _LOG.warning("pick_document 仅在 Android 上可用")
        _deliver(callback, None)
        return

    try:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        activity = _get_activity()

        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(str(mime or "*/*"))
        if allow_multiple:
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)

        request_code = _register(
            "pick",
            callback,
            extra={"mime": str(mime or ""), "multiple": bool(allow_multiple)},
        )
        if request_code is None:
            return

        try:
            activity.startActivityForResult(intent, request_code)
        except Exception:
            _LOG.exception("启动系统文件选择器失败")
            _finish_without_activity(request_code, None)
    except Exception:
        _LOG.exception("打开系统文件选择器失败（已捕获）")
        _deliver(callback, None)


# ---------------------------------------------------------------------------
# 对外接口 2：系统相机拍照
# ---------------------------------------------------------------------------
def take_photo(callback) -> None:
    """调用系统相机拍一张照片，返回 App 私有目录下的本地图片路径。

    因为 Android 7+ 禁止把 ``file://`` URI 传给别的应用，这里先用 MediaStore
    插入一个 ``content://`` 输出 URI，再把它作为 ``EXTRA_OUTPUT`` 交给系统相机。

    参数:
        callback: ``callback(local_path)``，取消/失败（含没有相机 App、
                  权限被拒绝）时 ``callback(None)``；只在 Kivy 主线程调用一次。

    返回:
        无（异步）。
    """
    if not _is_android():
        _LOG.warning("take_photo 仅在 Android 上可用")
        _deliver(callback, None)
        return

    try:
        _ensure_camera_permission(
            lambda granted: _start_camera(callback) if granted else _on_camera_denied(callback)
        )
    except Exception:
        _LOG.exception("检查相机权限失败，直接尝试启动相机（已捕获）")
        _start_camera(callback)


def _on_camera_denied(callback) -> None:
    """相机权限被拒绝：记录日志并回调 None（UI 可引导用户改用相册选择）。"""
    _LOG.warning("相机权限被拒绝，无法拍照，请引导用户改用相册/文件选择器")
    _deliver(callback, None)


def _ensure_camera_permission(on_ready) -> None:
    """确认 CAMERA 权限；未授权时先申请，授权结果通过 on_ready(bool) 返回。"""
    called = {"done": False}

    def _ready(granted: bool) -> None:
        # 保证 on_ready 只执行一次，避免系统重复回调导致启动两个相机界面。
        if called["done"]:
            return
        called["done"] = True
        try:
            on_ready(bool(granted))
        except Exception:
            _LOG.exception("相机权限回调处理失败（已捕获）")

    try:
        from android.permissions import check_permission, request_permissions, Permission
    except Exception:
        _LOG.warning("android.permissions 不可用，跳过权限检查直接启动相机", exc_info=True)
        _ready(True)
        return

    try:
        if check_permission("android.permission.CAMERA"):
            _ready(True)
            return
        permission = getattr(Permission, "CAMERA", "android.permission.CAMERA")

        def _on_permission_result(permissions, grants):
            try:
                granted = bool(grants) and all(bool(item) for item in grants)
            except Exception:
                granted = False
            _ready(granted)

        request_permissions([permission], _on_permission_result)
    except Exception:
        _LOG.exception("申请相机权限失败，直接尝试启动相机（已捕获）", exc_info=True)
        _ready(True)


def _start_camera(callback) -> None:
    """真正启动系统相机（调用方需已确保 CAMERA 权限）。"""
    try:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        MediaStore = autoclass("android.provider.MediaStore")
        ClipData = autoclass("android.content.ClipData")

        activity = _get_activity()
        camera_uri = _insert_camera_image(activity)

        intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        intent.putExtra(MediaStore.EXTRA_OUTPUT, camera_uri)
        # 把输出 URI 的读写权限一并授给相机 App，兼容部分厂商相机。
        try:
            intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            intent.setClipData(ClipData.newRawUri("output", camera_uri))
        except Exception:
            _LOG.warning("无法为拍照 Intent 附加 URI 权限，部分机型可能拍照失败", exc_info=True)

        request_code = _register("camera", callback, extra={"camera_uri": camera_uri})
        if request_code is None:
            _delete_media_uri(camera_uri)
            return

        try:
            activity.startActivityForResult(intent, request_code)
        except Exception:
            _LOG.exception("启动系统相机失败（可能没有相机应用）")
            _finish_without_activity(request_code, None)
    except Exception:
        _LOG.exception("拍照流程失败（已捕获）")
        _deliver(callback, None)
