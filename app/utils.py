"""App 层小工具：后台线程、日期计算、文件大小。"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta

from kivy.clock import Clock


def run_in_thread(func, on_done=None, on_error=None):
    """后台执行 func，结果/异常通过 Clock 切回主线程回调。"""

    def target():
        try:
            result = func()
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                Clock.schedule_once(lambda dt: on_error(exc), 0)
        else:
            if on_done is not None:
                Clock.schedule_once(lambda dt: on_done(result), 0)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


def parse_due(due: str) -> date | None:
    """解析 YYYY-MM-DD，失败返回 None。"""
    text = (due or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m-%d", "%m/%d"):
        try:
            dt = datetime.strptime(text, fmt)
            if fmt in ("%m-%d", "%m/%d"):
                dt = dt.replace(year=date.today().year)
            return dt.date()
        except ValueError:
            continue
    return None


def days_until(due: str) -> int | None:
    d = parse_due(due)
    if d is None:
        return None
    return (d - date.today()).days


def due_text(due: str, done: bool = False) -> str:
    if done:
        return "已完成"
    d = parse_due(due)
    if d is None:
        return "未设置截止日期"
    left = (d - date.today()).days
    if left < 0:
        return f"已逾期 {abs(left)} 天（{d:%m-%d}）"
    if left == 0:
        return f"今天截止（{d:%m-%d}）"
    if left == 1:
        return f"明天截止（{d:%m-%d}）"
    return f"还剩 {left} 天（{d:%m-%d}）"


def default_due(days: int = 7) -> str:
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


def human_size(num: int) -> str:
    size = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"
