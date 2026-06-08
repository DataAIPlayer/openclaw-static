"""从 toolCall 参数路径里识别 OpenClaw skill。

OpenClaw 的 skill 不是独立工具调用，而是 ~/.openclaw/.../skills/<name>/
目录。agent 用 read/exec/edit 等工具操作该目录下的文件即代表使用了该 skill。
skill 名藏在 toolCall 的 arguments 路径里。
"""

from __future__ import annotations

import json
import re
from collections import Counter

# 锚定到 .openclaw workspace，避免误判无关的 skills/ 路径
_SKILL_RE = re.compile(r"\.openclaw/[^\"'\\]*?/skills/([A-Za-z0-9_-]+)/")


def skills_in_toolcall(item: dict) -> set[str]:
    """返回该 toolCall 命中的 skill 名集合（同名去重）。非 toolCall 返回空。"""
    if not isinstance(item, dict) or item.get("type") != "toolCall":
        return set()
    blob = json.dumps(item.get("arguments") or {}, ensure_ascii=False)
    return set(_SKILL_RE.findall(blob))


def skills_in_message(message: dict) -> dict[str, int]:
    """统计一条 assistant message 里各 skill 的使用次数（按 toolCall 次数累加）。

    非 assistant 角色返回空 dict。
    """
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return {}
    counts: Counter = Counter()
    for item in message.get("content") or []:
        for name in skills_in_toolcall(item):
            counts[name] += 1
    return dict(counts)
