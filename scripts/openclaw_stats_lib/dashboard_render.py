"""把聚合结果渲染成前端看板用的 stats.json 字符串。"""

from __future__ import annotations

import json


def to_dashboard_json(periods: dict, *, generated_at: str) -> str:
    """periods: {"day":[...],"week":[...],"month":[...]}（来自 buckets.aggregate）。"""
    payload = {"generated_at": generated_at, "periods": periods}
    return json.dumps(payload, ensure_ascii=False, indent=2)
