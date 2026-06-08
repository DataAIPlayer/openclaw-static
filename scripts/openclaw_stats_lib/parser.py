"""OpenClaw 会话日志解析与聚合。"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from collections.abc import Iterable
from datetime import datetime

_CONTAINER_RE = re.compile(r"^openclaw-(?P<user>.+)-gateway$")


def user_from_container_name(container: str) -> str | None:
    """从容器名提取用户名。约定命名: openclaw-{user}-gateway。"""
    m = _CONTAINER_RE.match(container)
    return m.group("user") if m else None


@dataclass
class UserStats:
    user: str
    container: str
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_total: float = 0.0
    models: set[str] = field(default_factory=set)
    skill_calls: Counter = field(default_factory=Counter)
    sessions_files: set[str] = field(default_factory=set)
    first_seen: datetime | None = None
    last_seen: datetime | None = None


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def aggregate_line(stats: UserStats, raw: str) -> bool:
    """把一行 jsonl 聚合到 stats。返回 True 表示该行成功解析，False 表示损坏跳过。"""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return False

    if obj.get("type") != "message":
        return True

    ts = _parse_ts(obj.get("timestamp"))
    if ts is not None:
        if stats.first_seen is None or ts < stats.first_seen:
            stats.first_seen = ts
        if stats.last_seen is None or ts > stats.last_seen:
            stats.last_seen = ts

    msg = obj.get("message") or {}
    role = msg.get("role")
    if role != "assistant":
        return True

    stats.requests += 1

    model = msg.get("model")
    if model:
        stats.models.add(model)

    usage = msg.get("usage") or {}
    stats.input_tokens += int(usage.get("input") or 0)
    stats.output_tokens += int(usage.get("output") or 0)
    stats.total_tokens += int(usage.get("totalTokens") or 0)
    stats.cache_read += int(usage.get("cacheRead") or 0)
    stats.cache_write += int(usage.get("cacheWrite") or 0)
    cost = usage.get("cost") or {}
    stats.cost_total += float(cost.get("total") or 0.0)

    for item in msg.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "toolCall":
            name = item.get("name")
            if name:
                stats.skill_calls[name] += 1

    return True


def aggregate_lines_into(
    stats: UserStats,
    source_name: str,
    lines: Iterable[str],
) -> int:
    """把 lines 累加到已有 stats，返回该源中损坏行数。"""
    stats.sessions_files.add(source_name)
    corrupt = 0
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        ok = aggregate_line(stats, raw)
        if not ok:
            corrupt += 1
    return corrupt


def aggregate_lines(
    user: str,
    container: str,
    source_name: str,
    lines: Iterable[str],
) -> tuple[UserStats, int]:
    """便捷函数：新建 UserStats 并把 lines 聚合进去。"""
    stats = UserStats(user=user, container=container)
    corrupt = aggregate_lines_into(stats, source_name, lines)
    return stats, corrupt
