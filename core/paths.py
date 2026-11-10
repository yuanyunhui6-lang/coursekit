"""统一解析数据目录（电脑 / 安卓）。

- 电脑：项目目录下的 data/（可用环境变量 COURSEKIT_DATA 覆盖，测试用）
- 安卓：p4a 注入的 ANDROID_PRIVATE（应用私有 files 目录），无需存储权限
"""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "CourseKit"


def is_android() -> bool:
    """判断是否运行在 Android（p4a 构建）。"""
    if os.environ.get("ANDROID_ARGUMENT") or os.environ.get("ANDROID_PRIVATE"):
        return True
    return "android" in os.sys.platform.lower()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """返回应用数据根目录（自动创建）。"""
    override = os.environ.get("COURSEKIT_DATA")
    if override:
        root = Path(override)
    elif is_android():
        base = os.environ.get("ANDROID_PRIVATE") or os.environ.get("ANDROID_APP_PATH")
        root = (Path(base) if base else Path.home() / ".coursekit") / "coursekit_data"
    else:
        root = _project_root() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return data_dir() / "coursekit.db"


def images_dir() -> Path:
    d = data_dir() / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def exports_dir() -> Path:
    d = data_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def temp_dir() -> Path:
    d = data_dir() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d
