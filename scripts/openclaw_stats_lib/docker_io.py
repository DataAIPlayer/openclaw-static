"""docker 命令封装。所有 subprocess 调用集中在这里，方便测试 mock。"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

SESSIONS_GLOB = "/home/node/.openclaw/agents/main/sessions/*.jsonl*"


def list_containers(name_substring: str = "openclaw-") -> list[str]:
    """运行 docker ps 列出名字包含子串的容器。

    docker 的 name filter 是子串匹配，不支持通配符。这里用 "openclaw-" 作为
    默认子串可以命中所有 openclaw-{user}-gateway 命名。CLI 层用 regex 做精确过滤。
    """
    cmd = [
        "docker", "ps",
        "--filter", f"name={name_substring}",
        "--format", "{{.Names}}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def read_container_sessions(container: str) -> Iterator[str]:
    """逐行 yield 容器内 sessions 目录下所有 jsonl 文件内容。

    使用 sh -c 让 shell 展开通配符；目录不存在时 docker exec 返回非 0，
    本函数静默返回空（不抛异常）。
    """
    inner = f"cat {SESSIONS_GLOB} 2>/dev/null"
    cmd = ["docker", "exec", container, "sh", "-c", inner]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return
    if result.returncode != 0 and not result.stdout:
        return
    for line in result.stdout.splitlines():
        if line.strip():
            yield line
