#!/usr/bin/env python3
"""OpenClaw 使用数据看板聚合 CLI。

读取本地 jsonl 会话日志(文件或目录)，按 用户×(日/周/月)×(对话/token/skill)
预聚合成前端看板用的 stats.json。无需 openclaw 运行环境。

用法:
  python3 scripts/openclaw_dashboard_stats.py PATH [PATH ...] \
      [--user U]... [--default-user unknown] [--out stats.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from openclaw_stats_lib.buckets import aggregate
from openclaw_stats_lib.dashboard_render import to_dashboard_json


def _iter_jsonl_files(path: Path) -> list[Path]:
    if path.is_dir():
        files = sorted(path.rglob("*.jsonl"))
        files += sorted(path.rglob("*.jsonl.reset.*"))
        return files
    return [path]


def _records_from_file(path: Path, user: str) -> Iterator[tuple[str, dict]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield (user, obj)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openclaw_dashboard_stats",
        description="把本地 OpenClaw jsonl 聚合为看板 stats.json。",
    )
    p.add_argument("paths", nargs="+", help="jsonl 文件或目录，可多个")
    p.add_argument("--user", action="append", default=None,
                   help="与 paths 一一对应的用户名；不足部分用 --default-user")
    p.add_argument("--default-user", default="unknown",
                   help="paths 没有对应 --user 时的用户名 (默认: unknown)")
    p.add_argument("--out", default=None, help="输出文件 (默认: stdout)")
    p.add_argument("--generated-at", default=None,
                   help="覆盖 generated_at（默认当前 UTC 时间，主要给测试用）")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    users = args.user or []

    records: list[tuple[str, dict]] = []
    for i, raw_path in enumerate(args.paths):
        user = users[i] if i < len(users) else args.default_user
        path = Path(raw_path).expanduser()
        if not path.exists():
            print(f"warn: 路径不存在，跳过: {path}", file=sys.stderr)
            continue
        for f in _iter_jsonl_files(path):
            records.extend(_records_from_file(f, user))

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
