"""Android 运行时权限申请。

申请哪些权限（按系统版本分支）：

* ``CAMERA``：拍照（系统相机其实自己就有权限，但本 App 声明了 CAMERA，
  在 Android 6+ 若声明了却未授权，调用 ACTION_IMAGE_CAPTURE 会抛 SecurityException，
  所以必须主动申请）。
* ``READ_EXTERNAL_STORAGE`` / ``WRITE_EXTERNAL_STORAGE``：
  Android 9 及以下读写外部存储（导出到下载目录、读取相册）。
* ``READ_MEDIA_IMAGES``：Android 13（API 33）起替代 READ_EXTERNAL_STORAGE。
* ``POST_NOTIFICATIONS``：Android 13（API 33）起的通知权限（作业截止提醒用）。

注意：POST_NOTIFICATIONS 只有在 ``buildozer.spec`` 的 ``android.permissions``
里声明过才会真正弹窗，否则系统会直接拒绝（不会崩溃）。

对外接口（冻结）：

    ensure_permissions(callback=None)

``callback`` 可选，接受两种签名（二选一均可）：

    callback(permissions: list[str], grants: list[bool])
    callback()                      # 无参

回调由系统权限弹窗返回时触发（Android 上是主线程），桌面环境会立即回调
``callback([], [])``。任何异常都只记录日志，不向外抛。
"""

from __future__ import annotations

import inspect
import logging
import os

_LOG = logging.getLogger(__name__)

# 权限名字符串直接用 android.permission.* 全名，
# 避免不同 p4a 版本的 Permission 常量缺失（例如旧版没有 READ_MEDIA_IMAGES）。
_PERM_CAMERA = "android.permission.CAMERA"
_PERM_READ_STORAGE = "android.permission.READ_EXTERNAL_STORAGE"
_PERM_WRITE_STORAGE = "android.permission.WRITE_EXTERNAL_STORAGE"
_PERM_READ_MEDIA_IMAGES = "android.permission.READ_MEDIA_IMAGES"
_PERM_POST_NOTIFICATIONS = "android.permission.POST_NOTIFICATIONS"


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


def _get_sdk_int() -> int:
    """读取 Build.VERSION.SDK_INT，失败时按 targetSdk 33 处理。"""
    try:
        from jnius import autoclass

        return int(autoclass("android.os.Build$VERSION").SDK_INT)
    except Exception:
        _LOG.warning("无法读取系统 API 版本，按 Android 13（API 33）处理", exc_info=True)
        return 33


def _build_permission_list(sdk_int: int) -> list[str]:
    """按系统版本组装需要申请的权限列表。"""
    permissions: list[str] = [_PERM_CAMERA]

    if sdk_int >= 33:
        # Android 13+：照片权限由 READ_MEDIA_IMAGES 接管
        permissions.append(_PERM_READ_MEDIA_IMAGES)
    else:
        permissions.append(_PERM_READ_STORAGE)

    if sdk_int <= 28:
        # Android 9 及以下导出到公共下载目录需要写权限
        permissions.append(_PERM_WRITE_STORAGE)

    if sdk_int >= 33:
        # 通知权限（作业截止提醒）
        permissions.append(_PERM_POST_NOTIFICATIONS)

    return permissions


def _callback_arity(callback) -> int:
    """尽量判断回调接受几个位置参数，用于兼容 ``callback()`` 写法。"""
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return 2
    total = 0
    for parameter in signature.parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            return 2
        total += 1
    return total


def _invoke_callback(callback, permissions, grants) -> None:
    """安全地执行回调（回调里的异常不能影响权限流程）。"""
    if callback is None:
        return
    try:
        arity = _callback_arity(callback)
        if arity >= 2:
            callback(permissions, grants)
        elif arity == 1:
            callback(permissions)
        else:
            callback()
    except Exception:
        _LOG.exception("权限回调执行出错（已捕获）")


def ensure_permissions(callback=None) -> None:
    """申请 App 运行所需的全部权限（异步；回调在系统弹窗出结果后触发）。

    参数:
        callback: 可选回调，见模块文档字符串中的两种签名。

    行为:
        * 桌面环境 / 无法导入 android 模块：立即回调 ``callback([], [])``；
        * Android：弹出系统权限对话框，返回后回调
          ``callback(permissions, grants)``，``grants`` 是对应的 bool 列表。
        * 即使权限被拒绝也不会抛异常（后续功能各自做降级处理）。
    """
    if not _is_android():
        _LOG.info("权限申请跳过：当前不是 Android 环境")
        _invoke_callback(callback, [], [])
        return

    try:
        # python-for-android 提供的 android 模块（只在设备上存在）
        from android.permissions import request_permissions

        sdk_int = _get_sdk_int()
        permissions = _build_permission_list(sdk_int)
        _LOG.info("申请 Android 权限（API %d）：%s", sdk_int, permissions)

        def _on_result(granted_permissions, grant_results):
            try:
                # grants 是 Java boolean[]，转成 Python bool 列表再往下传。
                grants = [bool(item) for item in grant_results]
                denied = [
                    name
                    for name, granted in zip(granted_permissions, grants)
                    if not granted
                ]
                if denied:
                    _LOG.warning("以下权限被拒绝：%s", denied)
                else:
                    _LOG.info("所需权限已全部授权")
            except Exception:
                _LOG.exception("解析权限申请结果失败")
                grants = []
            finally:
                _invoke_callback(callback, granted_permissions, grants)

        request_permissions(permissions, _on_result)
    except Exception:
        _LOG.exception("权限申请流程失败（已捕获）")
        _invoke_callback(callback, [], [])
