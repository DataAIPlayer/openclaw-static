"""把聚合后的 UserStats 列表渲染为 JSON / 表格字符串。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .parser import UserStats


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_dt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def to_json(
    stats: list[UserStats],
    *,
    corrupt_lines: int = 0,
    containers_without_sessions: list[str] | None = None,
) -> str:
    sorted_stats = sorted(stats, key=lambda s: s.total_tokens, reverse=True)
    totals = {
        "containers": len(stats),
        "requests": sum(s.requests for s in stats),
        "input_tokens": sum(s.input_tokens for s in stats),
        "output_tokens": sum(s.output_tokens for s in stats),
        "total_tokens": sum(s.total_tokens for s in stats),
        "cost_total": round(sum(s.cost_total for s in stats), 6),
    }
    users = []
    for s in sorted_stats:
        users.append({
            "user": s.user,
            "container": s.container,
            "requests": s.requests,
            "input_tokens": s.input_tokens,
            "output_tokens": s.output_tokens,
            "total_tokens": s.total_tokens,
            "cache_read": s.cache_read,
            "cache_write": s.cache_write,
            "cost_total": round(s.cost_total, 6),
            "models": sorted(s.models),
            "skill_calls": dict(s.skill_calls.most_common()),
            "sessions": len(s.sessions_files),
            "first_seen": _fmt_dt(s.first_seen),
            "last_seen": _fmt_dt(s.last_seen),
        })
    payload = {
        "scan_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": totals,
        "users": users,
        "errors": {
            "corrupt_lines": corrupt_lines,
            "containers_without_sessions": containers_without_sessions or [],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def to_table(stats: list[UserStats], *, top_skills: int = 5) -> str:
    sorted_stats = sorted(stats, key=lambda s: s.total_tokens, reverse=True)
    totals_requests = sum(s.requests for s in stats)
    totals_tokens = sum(s.total_tokens for s in stats)
    totals_cost = sum(s.cost_total for s in stats)
    scan = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    out = []
    out.append("OpenClaw 用户使用统计")
    out.append(f"扫描时间: {scan}")
    out.append(
        f"容器数: {len(stats)}  | 总请求: {_fmt_int(totals_requests)}  "
        f"| 总 token: {_fmt_int(totals_tokens)}  | 总成本: ${totals_cost:.2f}"
    )
    out.append("")

    headers = ["用户", "请求", "输入", "输出", "总tok", "成本($)", "会话", "最近活跃"]
    rows = []
    for s in sorted_stats:
        rows.append([
            s.user,
            _fmt_int(s.requests),
            _fmt_int(s.input_tokens),
            _fmt_int(s.output_tokens),
            _fmt_int(s.total_tokens),
            f"{s.cost_total:.2f}",
            str(len(s.sessions_files)),
            s.last_seen.strftime("%Y-%m-%d") if s.last_seen else "-",
        ])

    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    out.append(fmt.format(*headers))
    out.append("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for r in rows:
        out.append(fmt.format(*r))

    out.append("")
    out.append(f"每用户 skill 调用 Top {top_skills}:")
    out.append("-" * 50)
    for s in sorted_stats:
        top = s.skill_calls.most_common(top_skills)
        rest = sum(c for _, c in s.skill_calls.most_common()[top_skills:])
        parts = [f"{name}({cnt})" for name, cnt in top]
        if rest > 0:
            parts.append(f"...others({rest})")
        out.append(f"{s.user}: {', '.join(parts) if parts else '(无)'}")

    return "\n".join(out)
