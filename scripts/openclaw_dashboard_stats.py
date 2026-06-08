#!/usr/bin/env python3
"""OpenClaw 使用数据看板聚合 CLI。

按 用户×(日/周/月)×(对话/token/skill) 预聚合成前端看板用的 stats.json。

两种数据源:
  - local (默认): 读本地 jsonl 文件/目录,无需 openclaw 运行环境,适合开发。
  - docker: 在服务器上扫所有 openclaw-{user}-gateway 容器,docker exec 读容器内
    /home/node/.openclaw/agents/main/sessions/*.jsonl*,按容器名提取用户。

用法:
  # 本地
  python3 scripts/openclaw_dashboard_stats.py PATH [PATH ...] \
      [--user U]... [--default-user unknown] [--out stats.json]
  # docker (服务器上手动/cron 跑)
  python3 scripts/openclaw_dashboard_stats.py --source docker \
      [--user U]... [--container-filter openclaw-] [--out stats.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from openclaw_stats_lib import docker_io
from openclaw_stats_lib.buckets import aggregate
from openclaw_stats_lib.dashboard_render import to_dashboard_json
from openclaw_stats_lib.parser import user_from_container_name


def _iter_jsonl_files(path: Path) -> list[Path]:
    if path.is_dir():
        files = sorted(path.rglob("*.jsonl"))
        files += sorted(path.rglob("*.jsonl.reset.*"))
        return files
    return [path]


def _record_from_line(line: str, user: str) -> tuple[str, dict] | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return (user, obj)


def _records_from_file(path: Path, user: str) -> Iterator[tuple[str, dict]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = _record_from_line(line, user)
            if rec is not None:
                yield rec


def _collect_local(paths: list[str], users: list[str], default_user: str
                   ) -> list[tuple[str, dict]]:
    records: list[tuple[str, dict]] = []
    for i, raw_path in enumerate(paths):
        user = users[i] if i < len(users) else default_user
        path = Path(raw_path).expanduser()
        if not path.exists():
            print(f"warn: 路径不存在，跳过: {path}", file=sys.stderr)
            continue
        for f in _iter_jsonl_files(path):
            records.extend(_records_from_file(f, user))
    return records


def _collect_docker(user_filter: list[str], container_filter: str
                    ) -> list[tuple[str, dict]]:
    records: list[tuple[str, dict]] = []
    skipped: list[str] = []
    for container in docker_io.list_containers(name_substring=container_filter):
        user = user_from_container_name(container)
        if user is None:
            # 不是 openclaw-{user}-gateway,静默跳过(记录用于告警)
            skipped.append(container)
            continue
        if user_filter and user not in user_filter:
            continue
        for line in docker_io.read_container_sessions(container):
            rec = _record_from_line(line, user)
            if rec is not None:
                records.append(rec)
    if skipped:
        print(f"warn: 跳过非 openclaw-*-gateway 容器: {', '.join(skipped)}",
              file=sys.stderr)
    return records


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openclaw_dashboard_stats",
        description="把 OpenClaw jsonl 聚合为看板 stats.json(本地或 docker 源)。",
    )
    p.add_argument("paths", nargs="*",
                   help="jsonl 文件或目录,可多个 (source=local 时使用)")
    p.add_argument("--source", choices=["local", "docker"], default="local",
                   help="数据源 (默认: local)")
    p.add_argument("--user", action="append", default=None,
                   help="local: 与 paths 一一对应的用户名; docker: 只采这些用户")
    p.add_argument("--default-user", default="unknown",
                   help="local 下 paths 没有对应 --user 时的用户名 (默认: unknown)")
    p.add_argument("--container-filter", default="openclaw-",
                   help="docker name 子串过滤 (默认: openclaw-)")
    p.add_argument("--out", default=None, help="输出文件 (默认: stdout)")
    p.add_argument("--generated-at", default=None,
                   help="覆盖 generated_at(默认当前 UTC 时间,主要给测试用)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    users = args.user or []

    if args.source == "docker":
        records = _collect_docker(users, args.container_filter)
    else:
        if not args.paths:
            print("error: source=local 需要至少一个 PATH 参数", file=sys.stderr)
            return 2
        records = _collect_local(args.paths, users, args.default_user)

    periods = aggregate(records)
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    out_str = to_dashboard_json(periods, generated_at=generated_at)

    if args.out:
        Path(args.out).expanduser().write_text(out_str + "\n", encoding="utf-8")
    else:
        print(out_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
