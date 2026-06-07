"""时间桶 key 计算 + 按 用户×周期 聚合 OpenClaw 使用数据。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta

from .skills import skills_in_message


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


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class _UserBucket:
    __slots__ = ("conversations", "t_in", "t_out", "t_total", "skills")

    def __init__(self):
        self.conversations = 0
        self.t_in = 0
        self.t_out = 0
        self.t_total = 0
        self.skills = Counter()


def aggregate(records: Iterable) -> dict:
    """把 (user, message_obj) 记录序列聚合为 day/week/month 三周期结构。

    record: (user: str, obj: dict)，obj 是整行解析后的 {"type","timestamp","message"}。
    返回 {"day":[...], "week":[...], "month":[...]}，每元素见 dashboard 设计 §6。
    """
    # period -> bucket_key -> {"label": str, "users": {user: _UserBucket}}
    periods: dict[str, dict[str, dict]] = {"day": {}, "week": {}, "month": {}}

    for user, obj in records:
        if not isinstance(obj, dict) or obj.get("type") != "message":
            continue
        msg = obj.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        dt = _parse_ts(obj.get("timestamp"))
        if dt is None:
            continue

        usage = msg.get("usage") or {}
        t_in = int(usage.get("input") or 0)
        t_out = int(usage.get("output") or 0)
        t_total = int(usage.get("totalTokens") or 0)
        skills = skills_in_message(msg)

        for period, (bkey, label) in bucket_keys(dt).items():
            buckets = periods[period]
            if bkey not in buckets:
                buckets[bkey] = {"label": label, "users": defaultdict(_UserBucket)}
            ub = buckets[bkey]["users"][user]
            ub.conversations += 1
            ub.t_in += t_in
            ub.t_out += t_out
            ub.t_total += t_total
            for name, cnt in skills.items():
                ub.skills[name] += cnt

    return {p: _render_period(periods[p]) for p in ("day", "week", "month")}


def _render_period(buckets: dict) -> list:
    out = []
    for bkey in sorted(buckets):
        entry = buckets[bkey]
        users_out = []
        skill_user_counts: dict[str, Counter] = defaultdict(Counter)
        for user, ub in entry["users"].items():
            users_out.append({
                "user": user,
                "conversations": ub.conversations,
                "tokens": {"input": ub.t_in, "output": ub.t_out, "total": ub.t_total},
                "skills": [{"name": n, "count": c}
                           for n, c in ub.skills.most_common()],
            })
            for n, c in ub.skills.items():
                skill_user_counts[n][user] += c

        skills_ranking = []
        for name, per_user in skill_user_counts.items():
            skills_ranking.append({
                "name": name,
                "count": sum(per_user.values()),
                "by_user": [{"user": u, "count": c}
                            for u, c in per_user.most_common()],
            })
        skills_ranking.sort(key=lambda s: s["count"], reverse=True)

        out.append({
            "bucket": bkey,
            "label": entry["label"],
            "users": users_out,
            "skills_ranking": skills_ranking,
        })
    return out
