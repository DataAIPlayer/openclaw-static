#!/usr/bin/env python3
"""OpenClaw 用户使用统计 CLI。

在云服务器上运行，扫描所有 openclaw-*-gateway 容器内的会话日志，
按用户聚合 token 用量、请求次数和 skill 调用。
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from openclaw_stats_lib import docker_io
from openclaw_stats_lib.parser import (
    UserStats,
    aggregate_lines_into,
    user_from_container_name,
)
from openclaw_stats_lib.render import to_json, to_table


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openclaw_stats",
        description="按用户聚合 OpenClaw 容器内会话日志的使用数据。",
    )
    p.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="输出格式 (默认: table)",
    )
    p.add_argument(
        "--user", action="append", default=None,
        help="只统计指定用户，可多次指定",
    )
    p.add_argument(
        "--top-skills", type=int, default=5,
        help="表格里每用户 skill Top N (默认: 5)",
    )
    p.add_argument(
        "--container-filter", default="openclaw-",
        help="docker name 子串过滤 (默认: openclaw-)；CLI 内再用 regex 精确匹配 openclaw-{user}-gateway",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    containers = docker_io.list_containers(name_substring=args.container_filter)
    total_corrupt = 0
    no_sessions: list[str] = []
    stats_by_user: dict[str, UserStats] = {}

    for container in containers:
        user = user_from_container_name(container)
        if user is None:
            # 不是 openclaw-{user}-gateway 的子串命中（比如旧命名），静默跳过
            continue
        if args.user and user not in args.user:
            continue

        if user not in stats_by_user:
            stats_by_user[user] = UserStats(user=user, container=container)
        stats = stats_by_user[user]

        lines = list(docker_io.read_container_sessions(container))
        if not lines:
            no_sessions.append(container)
            continue
        corrupt = aggregate_lines_into(stats, container, iter(lines))
        total_corrupt += corrupt

    stats_list = list(stats_by_user.values())

    if args.format == "json":
        print(to_json(
            stats_list,
            corrupt_lines=total_corrupt,
            containers_without_sessions=no_sessions,
        ))
    else:
        print(to_table(stats_list, top_skills=args.top_skills))
        if total_corrupt:
            print(f"\nwarn: 跳过 {total_corrupt} 行损坏 JSON", file=sys.stderr)
        if no_sessions:
            print(
                f"warn: 以下容器无 sessions 数据: {', '.join(no_sessions)}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
