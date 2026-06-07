"""时间桶 key 计算 + 按 用户×周期 聚合 OpenClaw 使用数据。"""

from __future__ import annotations

from datetime import datetime, timedelta


def bucket_keys(dt: datetime) -> dict[str, tuple[str, str]]:
    """返回 day/week/month 三个周期的 (bucket_key, label)。

    week 锚定到该周周一(ISO，周一为周首)。
    """
    day_key = dt.strftime("%Y-%m-%d")
    monday = dt - timedelta(days=dt.weekday())
    iso = dt.isocalendar()
    week_label = f"{iso[0]}-W{iso[1]:02d}"
    month_key = dt.strftime("%Y-%m")
    return {
        "day": (day_key, day_key),
        "week": (monday.strftime("%Y-%m-%d"), week_label),
        "month": (month_key, month_key),
    }
