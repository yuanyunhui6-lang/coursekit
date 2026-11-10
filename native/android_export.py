"""Android 端导出：把文件写入手机「下载」目录（Download/课件通）。

策略按 Android 版本分支：

* Android 10（API 29）及以上：使用 ``MediaStore.Downloads`` 插入记录后写流，
  **不需要任何存储权限**，文件出现在系统「下载」App 里。
* Android 9（API 28）及以下：``MediaStore.Downloads`` 不存在，
  退回直接写公共目录 ``Download/课件通``，此时需要 WRITE_EXTERNAL_STORAGE 权限
  （已在 buildozer.spec 的 android.permissions 中声明，并由
  ``native.android_permissions`` 在运行时申请）。

对外接口（冻结）：

    save_to_downloads(filename: str, data: bytes, mime: str) -> str | None

返回值：
* 成功：可用来定位文件的字符串。API 29+ 返回 ``content://`` URI，
  旧版本返回绝对文件路径；两种都只用于展示/日志，不要当本地路径打开。
* 失败（非 Android、无权限、写入异常）：返回 ``None``，绝不抛异常。
"""

from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)

# 下载目录下的子文件夹名（用户可见）
_SUB_DIR_NAME = "课件通"


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


def _safe_filename(filename: str, default_name: str = "课件通导出文件") -> str:
    """清洗文件名：去掉路径分隔符，防止写到其他目录。"""
    try:
        raw = str(filename or "").replace("\\", "/")
        name = os.path.basename(raw).strip()
    except Exception:
        name = ""
    if not name or name in (".", ".."):
        name = default_name
    return name


def _normalize_data(data) -> bytes:
    """把传入的数据统一成 bytes。"""
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    if isinstance(data, str):
        return data.encode("utf-8")
    raise TypeError("导出数据必须是 bytes，实际类型：%s" % type(data).__name__)


def _write_bytes(stream, payload: bytes) -> None:
    """把 bytes 写入 Java OutputStream。

    注意：pyjnius 会把 Python bytes 转成 Java byte[]，
    对应 ``OutputStream.write([B)V`` 重载，这里不能传 str。
    """
    if stream is None:
        raise IOError("输出流为空")
    stream.write(payload)
    stream.flush()


def _close_quietly(stream, name: str) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except Exception:
        _LOG.debug("关闭 %s 失败（可忽略）", name, exc_info=True)


def _save_on_android(filename: str, payload: bytes, mime_type: str) -> str | None:
    """真正写入手机下载目录的实现（只在 Android 上执行）。"""
    # 延迟导入：桌面环境没有 pyjnius，模块顶层导入会直接崩溃。
    from jnius import autoclass

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    activity = PythonActivity.mActivity
    if activity is None:
        _LOG.error("导出失败：当前 Activity 为空")
        return None

    BuildVersion = autoclass("android.os.Build$VERSION")
    sdk_int = int(BuildVersion.SDK_INT)
    resolver = activity.getContentResolver()

    if sdk_int >= 29:
        return _save_via_mediastore(activity, resolver, filename, payload, mime_type)

    return _save_via_legacy_path(filename, payload)


def _save_via_mediastore(activity, resolver, filename: str, payload: bytes, mime_type: str) -> str | None:
    """API 29+：通过 MediaStore.Downloads 写入公共下载目录（免权限）。"""
    from jnius import autoclass

    Downloads = autoclass("android.provider.MediaStore$Downloads")
    MediaColumns = autoclass("android.provider.MediaStore$MediaColumns")
    ContentValues = autoclass("android.content.ContentValues")
    Environment = autoclass("android.os.Environment")

    uri = None
    stream = None
    try:
        values = ContentValues()
        values.put(MediaColumns.DISPLAY_NAME, filename)
        values.put(MediaColumns.MIME_TYPE, mime_type)
        try:
            # 在「下载」下再建一个「课件通」子目录，方便用户找到导出的文件。
            values.put(MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/" + _SUB_DIR_NAME)
        except Exception:
            # RELATIVE_PATH 是 API 29 才有的列；个别魔改 ROM 上取不到常量时忽略即可，
            # 文件会直接落在「下载」根目录。
            _LOG.warning("当前系统不支持下载子目录，文件将直接写入下载根目录", exc_info=True)

        uri = resolver.insert(Downloads.EXTERNAL_CONTENT_URI, values)
        if uri is None:
            _LOG.error("导出失败：MediaStore.insert 返回空 URI")
            return None

        stream = resolver.openOutputStream(uri)
        _write_bytes(stream, payload)
        return str(uri)
    except Exception:
        _LOG.exception("通过 MediaStore 导出失败：%s", filename)
        # 写入失败时删掉刚插入的空记录，避免下载列表里出现 0 字节文件。
        if uri is not None:
            try:
                resolver.delete(uri, None, None)
            except Exception:
                _LOG.debug("删除失败的 MediaStore 记录时出错（可忽略）", exc_info=True)
        return None
    finally:
        _close_quietly(stream, "OutputStream")


def _save_via_legacy_path(filename: str, payload: bytes) -> str | None:
    """API 28 及以下：直接写公共下载目录（需要 WRITE_EXTERNAL_STORAGE 权限）。"""
    from jnius import autoclass

    Environment = autoclass("android.os.Environment")
    File = autoclass("java.io.File")
    FileOutputStream = autoclass("java.io.FileOutputStream")

    stream = None
    try:
        downloads_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        if downloads_dir is None:
            _LOG.error("导出失败：无法获取公共下载目录")
            return None

        target_dir = File(downloads_dir, _SUB_DIR_NAME)
        if not target_dir.exists():
            if not target_dir.mkdirs():
                _LOG.error("导出失败：无法创建下载子目录")
                return None

        target_file = File(target_dir, filename)
        stream = FileOutputStream(target_file)
        _write_bytes(stream, payload)
        return str(target_file.getAbsolutePath())
    except Exception:
        _LOG.exception("通过文件路径导出失败：%s", filename)
        return None
    finally:
        _close_quietly(stream, "FileOutputStream")


def save_to_downloads(filename: str, data: bytes, mime: str = "application/octet-stream") -> str | None:
    """把 ``data`` 写入手机「下载/课件通」目录（阻塞式，建议在后台线程调用）。

    参数:
        filename: 文件名（会做路径清洗，例如 ``复习笔记.md``）。
        data: 文件内容，必须是 bytes（str 会按 UTF-8 编码）。
        mime: MIME 类型，例如 ``text/markdown``、``application/vnd.openxmlformats-officedocument.wordprocessingml.document``。

    返回:
        成功返回位置字符串（``content://`` URI 或旧系统的绝对路径）；
        失败返回 ``None``（非 Android 环境、无权限、写入异常都不会抛异常）。
    """
    try:
        safe_name = _safe_filename(filename)
    except Exception:
        safe_name = "课件通导出文件"

    try:
        payload = _normalize_data(data)
    except Exception:
        _LOG.exception("导出失败：文件内容不是 bytes")
        return None

    mime_type = str(mime or "").strip() or "application/octet-stream"

    if not _is_android():
        _LOG.info("导出跳过：当前不是 Android 环境，请由 core/ 层写入桌面文件系统")
        return None

    try:
        return _save_on_android(safe_name, payload, mime_type)
    except Exception:
        _LOG.exception("导出失败（已捕获）：%s", safe_name)
        return None
