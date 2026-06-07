# Openclaw 使用数据看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个轻量看板：Python 脚本把 OpenClaw 会话 jsonl 按 用户×(日/周/月)×(对话次数/token/skill) 预聚合成静态 `stats.json`，Vue3 前端直读渲染，支持周期切换、维度切换、升降序排序、skill 行展开看用户明细。

**Architecture:** 两段式、静态文件对接、无后端。沿用并扩展现有 `scripts/openclaw_stats_lib`（jsonl 解析骨架），**新增**独立的 skill 识别函数与桶聚合模块，不改动现有 CLI（`openclaw_stats.py`）的行为。skill 识别从 toolCall 的 `arguments` 路径里抽 `.openclaw/.../skills/<name>/`，按 toolCall 次数累加。

**Tech Stack:** Python 3.11+（标准库，pytest 测试）；Vue 3 + Vite + 原生 CSS（前端）。

---

## 设计约束 / 关键事实（实现前必读）

1. **不要破坏现有 CLI**。`scripts/openclaw_stats.py` 和它的 `parser.aggregate_line` 当前把所有 toolCall 名（read/exec）计入 `skill_calls`，且 `tests/test_openclaw_stats.py` 断言了这个行为。**不要修改** `aggregate_line` 的 `skill_calls` 逻辑。skill 识别是一个**新函数**，dashboard 聚合基于它。

2. **skill 识别口径**：扫 `message.role=="assistant"` 行的 `content[*]`，对 `type=="toolCall"` 项，把它的 `arguments` 用 `json.dumps` 序列化后用正则
   `\.openclaw/[^"'\\]*?/skills/([A-Za-z0-9_-]+)/`
   匹配；一个 toolCall 内同名只算一次，不同名各算一次。**每个命中的 toolCall 该 skill +1**。

3. **真实样例事实**（`examples/example-log.jsonl`，已核对）：
   - assistant 行（对话次数）= **33**
   - skill `biz-meeting-summary` = **13**；无其他 skill
   - token：input=167537, output=6166, totalTokens=1419527
   - 全部时间戳都在 `2026-05-25`（该日是周一）→ week bucket=`2026-05-25` / label=`2026-W22`；month=`2026-05`

4. **测试目录约定**：`scripts/tests/` 下，`conftest.py` 已把 `scripts/` 加进 `sys.path`，所以 import 写 `from openclaw_stats_lib import ...`。运行用 `cd scripts && pytest tests/ -v` 或 `pytest scripts/tests -v`（仓库根都行，conftest 处理路径）。

5. **运行测试的统一命令**（本计划所有 pytest 步骤都用它，按需替换 `::` 节点）：
   ```bash
   python3 -m pytest scripts/tests -v
   ```

---

## File Structure

**新建（Python）：**
- `scripts/openclaw_stats_lib/skills.py` — skill 路径识别（纯函数，无状态）。
- `scripts/openclaw_stats_lib/buckets.py` — 时间桶 key 计算 + 按 用户×周期 聚合 + skill 排行。
- `scripts/openclaw_stats_lib/dashboard_render.py` — 把聚合结果渲染成 `stats.json` 结构。
- `scripts/openclaw_dashboard_stats.py` — CLI 入口：读本地 jsonl 文件/目录 → 输出 stats.json。
- `scripts/tests/test_skills.py` — skill 识别单测 + 真实样例断言。
- `scripts/tests/test_buckets.py` — 时间桶 + 聚合单测。
- `scripts/tests/test_dashboard_render.py` — 输出结构单测。
- `scripts/tests/test_dashboard_cli.py` — CLI 端到端（吃 example-log.jsonl）。

**新建（前端）：**
- `dashboard/package.json`, `dashboard/vite.config.js`, `dashboard/index.html`
- `dashboard/public/stats.json`（脚本产物，开发期放样例聚合）
- `dashboard/src/main.js`, `dashboard/src/api.js`, `dashboard/src/App.vue`
- `dashboard/src/components/PeriodTabs.vue`, `MetricTabs.vue`, `RankingTable.vue`
- `dashboard/README.md`

**不改动：** `scripts/openclaw_stats.py`、`scripts/openclaw_stats_lib/parser.py`（除非某任务明确说改）、`scripts/openclaw_stats_lib/render.py`、`scripts/openclaw_stats_lib/docker_io.py`。

---

## Task 1: skill 路径识别函数

**Files:**
- Create: `scripts/openclaw_stats_lib/skills.py`
- Test: `scripts/tests/test_skills.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_skills.py`:

```python
import json
from pathlib import Path

from openclaw_stats_lib.skills import skills_in_toolcall, skills_in_message

EXAMPLE = Path(__file__).resolve().parents[1].parent / "examples" / "example-log.jsonl"


class TestSkillsInToolcall:
    def test_matches_skill_path_in_arguments(self):
        tc = {"type": "toolCall", "name": "read",
              "arguments": {"path": "~/.openclaw/workspace/skills/biz-meeting-summary/SKILL.md"}}
        assert skills_in_toolcall(tc) == {"biz-meeting-summary"}

    def test_matches_absolute_workspace_path(self):
        tc = {"type": "toolCall", "name": "edit",
              "arguments": {"path": "/home/node/.openclaw/workspace/skills/foo-bar/scripts/x.py"}}
        assert skills_in_toolcall(tc) == {"foo-bar"}

    def test_same_skill_twice_in_one_call_counts_once(self):
        tc = {"type": "toolCall", "name": "exec",
              "arguments": {"command": "cat ~/.openclaw/workspace/skills/foo/a "
                                       "~/.openclaw/workspace/skills/foo/b"}}
        assert skills_in_toolcall(tc) == {"foo"}

    def test_two_different_skills_in_one_call(self):
        tc = {"type": "toolCall", "name": "exec",
              "arguments": {"command": "diff ~/.openclaw/workspace/skills/a/x "
                                       "~/.openclaw/workspace/skills/b/y"}}
        assert skills_in_toolcall(tc) == {"a", "b"}

    def test_plain_skills_path_without_openclaw_is_ignored(self):
        tc = {"type": "toolCall", "name": "read",
              "arguments": {"path": "/repo/skills/not-a-skill/file"}}
        assert skills_in_toolcall(tc) == set()

    def test_non_toolcall_returns_empty(self):
        assert skills_in_toolcall({"type": "text", "text": "skills/foo/"}) == set()


class TestSkillsInMessage:
    def test_counts_per_toolcall(self):
        msg = {"role": "assistant", "content": [
            {"type": "toolCall", "name": "read",
             "arguments": {"path": "~/.openclaw/workspace/skills/foo/SKILL.md"}},
            {"type": "toolCall", "name": "exec",
             "arguments": {"command": "python3 ~/.openclaw/workspace/skills/foo/run.py"}},
            {"type": "text", "text": "hi"},
        ]}
        # 两个 toolCall 各命中 foo -> foo 计 2
        assert skills_in_message(msg) == {"foo": 2}

    def test_non_assistant_returns_empty(self):
        msg = {"role": "user", "content": [
            {"type": "toolCall", "name": "read",
             "arguments": {"path": "~/.openclaw/workspace/skills/foo/SKILL.md"}}]}
        assert skills_in_message(msg) == {}


class TestRealExampleLog:
    def test_biz_meeting_summary_counts_13(self):
        from collections import Counter
        total = Counter()
        with EXAMPLE.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "message":
                    continue
                for name, cnt in skills_in_message(obj.get("message") or {}).items():
                    total[name] += cnt
        assert dict(total) == {"biz-meeting-summary": 13}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_skills.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'openclaw_stats_lib.skills'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/openclaw_stats_lib/skills.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_skills.py -v`
Expected: PASS（含 `test_biz_meeting_summary_counts_13`）

- [ ] **Step 5: Commit**

```bash
git add scripts/openclaw_stats_lib/skills.py scripts/tests/test_skills.py
git commit -m "feat: skill 路径识别(从 toolCall 参数抽 .openclaw/skills/<name>)"
```

---

## Task 2: 时间桶 key 计算

**Files:**
- Create: `scripts/openclaw_stats_lib/buckets.py`
- Test: `scripts/tests/test_buckets.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_buckets.py`:

```python
from datetime import datetime, timezone

from openclaw_stats_lib.buckets import bucket_keys


class TestBucketKeys:
    def test_day_week_month_for_a_monday(self):
        # 2026-05-25 是周一
        dt = datetime(2026, 5, 25, 15, 2, tzinfo=timezone.utc)
        keys = bucket_keys(dt)
        assert keys["day"] == ("2026-05-25", "2026-05-25")
        assert keys["week"] == ("2026-05-25", "2026-W22")
        assert keys["month"] == ("2026-05", "2026-05")

    def test_week_anchors_to_monday(self):
        # 2026-05-28 是周四 -> 周一仍是 2026-05-25
        dt = datetime(2026, 5, 28, 9, 0, tzinfo=timezone.utc)
        assert bucket_keys(dt)["week"] == ("2026-05-25", "2026-W22")

    def test_naive_datetime_supported(self):
        dt = datetime(2026, 1, 1, 0, 0)  # 周四
        keys = bucket_keys(dt)
        assert keys["day"] == ("2026-01-01", "2026-01-01")
        assert keys["month"] == ("2026-01", "2026-01")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_buckets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'openclaw_stats_lib.buckets'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/openclaw_stats_lib/buckets.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_buckets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/openclaw_stats_lib/buckets.py scripts/tests/test_buckets.py
git commit -m "feat: 时间桶 key 计算(日/周/月, 周锚定周一)"
```

---

## Task 3: 按 用户×周期 聚合

**Files:**
- Modify: `scripts/openclaw_stats_lib/buckets.py`（追加聚合函数）
- Test: `scripts/tests/test_buckets.py`（追加测试类）

- [ ] **Step 1: Write the failing test**

在 `scripts/tests/test_buckets.py` 末尾追加：

```python
import json
from pathlib import Path

from openclaw_stats_lib.buckets import aggregate

EXAMPLE = Path(__file__).resolve().parents[1].parent / "examples" / "example-log.jsonl"


def _line(role, ts, content=None, usage=None):
    msg = {"role": role, "content": content or []}
    if usage is not None:
        msg["usage"] = usage
    return json.dumps({"type": "message", "timestamp": ts, "message": msg})


class TestAggregate:
    def test_two_users_two_days_conversations_and_tokens(self):
        records = [
            ("weiwu2", _line("assistant", "2026-05-25T10:00:00Z",
                             usage={"input": 100, "output": 10, "totalTokens": 110})),
            ("weiwu2", _line("assistant", "2026-05-26T10:00:00Z",
                             usage={"input": 5, "output": 1, "totalTokens": 6})),
            ("bnzhu", _line("assistant", "2026-05-25T11:00:00Z",
                            usage={"input": 200, "output": 20, "totalTokens": 220})),
            ("weiwu2", _line("user", "2026-05-25T09:00:00Z")),  # user 不计对话
        ]
        agg = aggregate((u, json.loads(l)) for u, l in records)
        day = {b["bucket"]: b for b in agg["day"]}
        u0525 = {x["user"]: x for x in day["2026-05-25"]["users"]}
        assert u0525["weiwu2"]["conversations"] == 1
        assert u0525["weiwu2"]["tokens"]["total"] == 110
        assert u0525["bnzhu"]["conversations"] == 1
        assert day["2026-05-26"]["users"][0]["conversations"] == 1
        # 月桶把两天合并
        month = {b["bucket"]: b for b in agg["month"]}
        m = {x["user"]: x for x in month["2026-05"]["users"]}
        assert m["weiwu2"]["conversations"] == 2
        assert m["weiwu2"]["tokens"]["total"] == 116

    def test_skill_ranking_with_by_user(self):
        tc = lambda: [{"type": "toolCall", "name": "read",
                       "arguments": {"path": "~/.openclaw/workspace/skills/foo/SKILL.md"}}]
        records = [
            ("weiwu2", json.loads(_line("assistant", "2026-05-25T10:00:00Z", content=tc(),
                                        usage={"input": 1, "output": 1, "totalTokens": 2}))),
            ("weiwu2", json.loads(_line("assistant", "2026-05-25T10:01:00Z", content=tc(),
                                        usage={"input": 1, "output": 1, "totalTokens": 2}))),
            ("bnzhu", json.loads(_line("assistant", "2026-05-25T10:02:00Z", content=tc(),
                                       usage={"input": 1, "output": 1, "totalTokens": 2}))),
        ]
        agg = aggregate(records)
        day = {b["bucket"]: b for b in agg["day"]}
        ranking = day["2026-05-25"]["skills_ranking"]
        assert ranking[0]["name"] == "foo"
        assert ranking[0]["count"] == 3
        by_user = {x["user"]: x["count"] for x in ranking[0]["by_user"]}
        assert by_user == {"weiwu2": 2, "bnzhu": 1}
        # 用户对象里也带 skills 明细
        u = {x["user"]: x for x in day["2026-05-25"]["users"]}
        assert u["weiwu2"]["skills"] == [{"name": "foo", "count": 2}]

    def test_corrupt_and_bad_timestamp_skipped(self):
        records = [
            ("weiwu2", json.loads(_line("assistant", "not-a-date",
                                        usage={"input": 1, "output": 1, "totalTokens": 2}))),
            ("weiwu2", json.loads(_line("assistant", "2026-05-25T10:00:00Z",
                                        usage={"input": 1, "output": 1, "totalTokens": 2}))),
        ]
        agg = aggregate(records)
        # 坏时间戳那条不归桶
        assert len(agg["day"]) == 1
        assert agg["day"][0]["bucket"] == "2026-05-25"

    def test_real_example_single_user(self):
        with EXAMPLE.open() as fh:
            records = []
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records.append(("weiwu2", obj))
        agg = aggregate(records)
        day = {b["bucket"]: b for b in agg["day"]}
        bucket = day["2026-05-25"]
        u = bucket["users"][0]
        assert u["user"] == "weiwu2"
        assert u["conversations"] == 33
        assert u["tokens"]["total"] == 1419527
        assert bucket["skills_ranking"][0] == {
            "name": "biz-meeting-summary", "count": 13,
            "by_user": [{"user": "weiwu2", "count": 13}],
        }
        # 周/月桶也应各有一个
        assert {b["bucket"] for b in agg["week"]} == {"2026-05-25"}
        assert {b["bucket"] for b in agg["month"]} == {"2026-05"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_buckets.py::TestAggregate -v`
Expected: FAIL — `ImportError: cannot import name 'aggregate'`

- [ ] **Step 3: Write minimal implementation**

在 `scripts/openclaw_stats_lib/buckets.py` 顶部 import 区追加，并在文件末尾追加聚合实现：

```python
# --- 追加到文件顶部的 import ---
import json
from collections import Counter, defaultdict
from collections.abc import Iterable

from .skills import skills_in_message
```

```python
# --- 追加到文件末尾 ---
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_buckets.py -v`
Expected: PASS（含 `test_real_example_single_user`）

- [ ] **Step 5: Commit**

```bash
git add scripts/openclaw_stats_lib/buckets.py scripts/tests/test_buckets.py
git commit -m "feat: 按 用户x周期 聚合(对话/token/skill 排行 + by_user 明细)"
```

---

## Task 4: stats.json 渲染

**Files:**
- Create: `scripts/openclaw_stats_lib/dashboard_render.py`
- Test: `scripts/tests/test_dashboard_render.py`

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_dashboard_render.py`:

```python
import json

from openclaw_stats_lib.dashboard_render import to_dashboard_json


def test_wraps_periods_and_generated_at():
    periods = {"day": [{"bucket": "2026-05-25", "label": "2026-05-25",
                        "users": [], "skills_ranking": []}],
               "week": [], "month": []}
    out = to_dashboard_json(periods, generated_at="2026-06-08T00:00:00Z")
    parsed = json.loads(out)
    assert parsed["generated_at"] == "2026-06-08T00:00:00Z"
    assert parsed["periods"]["day"][0]["bucket"] == "2026-05-25"
    assert parsed["periods"]["week"] == []
    assert parsed["periods"]["month"] == []


def test_is_valid_pretty_json_utf8():
    periods = {"day": [], "week": [], "month": []}
    out = to_dashboard_json(periods, generated_at="2026-06-08T00:00:00Z")
    # 缩进 + 不转义非 ASCII
    assert "\n" in out
    json.loads(out)  # 不抛即合法
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_dashboard_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'openclaw_stats_lib.dashboard_render'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/openclaw_stats_lib/dashboard_render.py`:

```python
"""把聚合结果渲染成前端看板用的 stats.json 字符串。"""

from __future__ import annotations

import json


def to_dashboard_json(periods: dict, *, generated_at: str) -> str:
    """periods: {"day":[...],"week":[...],"month":[...]}（来自 buckets.aggregate）。"""
    payload = {"generated_at": generated_at, "periods": periods}
    return json.dumps(payload, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_dashboard_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/openclaw_stats_lib/dashboard_render.py scripts/tests/test_dashboard_render.py
git commit -m "feat: stats.json 渲染(generated_at + periods)"
```

---

## Task 5: dashboard CLI 入口

**Files:**
- Create: `scripts/openclaw_dashboard_stats.py`
- Test: `scripts/tests/test_dashboard_cli.py`

读取约定：CLI 接受若干路径（文件或目录）。目录会递归找 `*.jsonl` 与 `*.jsonl.reset.*`。每个输入路径关联一个用户名（`--user` 与位置参数一一对应；不足则用 `--default-user`，默认 `unknown`）。输出写到 `--out`（默认 stdout）。

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_dashboard_cli.py`:

```python
import json
from pathlib import Path

import openclaw_dashboard_stats as cli

EXAMPLE = Path(__file__).resolve().parents[1].parent / "examples" / "example-log.jsonl"


def test_main_reads_example_and_writes_json(tmp_path, capsys):
    out = tmp_path / "stats.json"
    rc = cli.main([str(EXAMPLE), "--user", "weiwu2", "--out", str(out),
                   "--generated-at", "2026-06-08T00:00:00Z"])
    assert rc == 0
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["generated_at"] == "2026-06-08T00:00:00Z"
    day = {b["bucket"]: b for b in parsed["periods"]["day"]}
    u = day["2026-05-25"]["users"][0]
    assert u["user"] == "weiwu2"
    assert u["conversations"] == 33
    assert day["2026-05-25"]["skills_ranking"][0]["name"] == "biz-meeting-summary"
    assert day["2026-05-25"]["skills_ranking"][0]["count"] == 13


def test_main_default_user_when_not_given(tmp_path):
    out = tmp_path / "stats.json"
    rc = cli.main([str(EXAMPLE), "--out", str(out),
                   "--generated-at", "2026-06-08T00:00:00Z"])
    assert rc == 0
    parsed = json.loads(out.read_text(encoding="utf-8"))
    users = parsed["periods"]["month"][0]["users"]
    assert users[0]["user"] == "unknown"


def test_main_directory_input(tmp_path):
    d = tmp_path / "sessions"
    d.mkdir()
    (d / "a.jsonl").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "stats.json"
    rc = cli.main([str(d), "--user", "weiwu2", "--out", str(out),
                   "--generated-at", "2026-06-08T00:00:00Z"])
    assert rc == 0
    parsed = json.loads(out.read_text(encoding="utf-8"))
    day = {b["bucket"]: b for b in parsed["periods"]["day"]}
    assert day["2026-05-25"]["users"][0]["conversations"] == 33


def test_main_to_stdout(capsys):
    rc = cli.main([str(EXAMPLE), "--user", "weiwu2",
                   "--generated-at", "2026-06-08T00:00:00Z"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["periods"]["day"][0]["users"][0]["conversations"] == 33
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/tests/test_dashboard_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'openclaw_dashboard_stats'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/openclaw_dashboard_stats.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/tests/test_dashboard_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite to confirm no regression in existing CLI**

Run: `python3 -m pytest scripts/tests -v`
Expected: PASS（包括既有 `test_openclaw_stats.py` 全部用例，证明没碰坏旧 CLI）

- [ ] **Step 6: Commit**

```bash
git add scripts/openclaw_dashboard_stats.py scripts/tests/test_dashboard_cli.py
git commit -m "feat: dashboard 聚合 CLI(本地 jsonl -> stats.json)"
```

---

## Task 6: 生成开发用 stats.json

**Files:**
- Create: `dashboard/public/stats.json`（脚本产物，提交进仓库供前端开发）

- [ ] **Step 1: 建目录并生成**

```bash
mkdir -p dashboard/public
python3 scripts/openclaw_dashboard_stats.py examples/example-log.jsonl \
    --user weiwu2 --out dashboard/public/stats.json
```

- [ ] **Step 2: 校验产物**

Run:
```bash
python3 -c "import json; d=json.load(open('dashboard/public/stats.json')); \
b={x['bucket']:x for x in d['periods']['day']}['2026-05-25']; \
print('conv', b['users'][0]['conversations']); \
print('skill', b['skills_ranking'][0])"
```
Expected 输出：
```
conv 33
skill {'name': 'biz-meeting-summary', 'count': 13, 'by_user': [{'user': 'weiwu2', 'count': 13}]}
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/public/stats.json
git commit -m "chore: 生成开发用 stats.json(样例聚合)"
```

---

## Task 7: 前端脚手架（Vite + Vue3）

**Files:**
- Create: `dashboard/package.json`, `dashboard/vite.config.js`, `dashboard/index.html`,
  `dashboard/src/main.js`, `dashboard/.gitignore`

- [ ] **Step 1: 写 package.json**

Create `dashboard/package.json`:

```json
{
  "name": "openclaw-dashboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.2.0"
  }
}
```

- [ ] **Step 2: 写 vite 配置、入口 html、main.js、gitignore**

Create `dashboard/vite.config.js`:

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
})
```

Create `dashboard/index.html`:

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Openclaw 使用看板</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

Create `dashboard/src/main.js`:

```js
import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')
```

Create `dashboard/.gitignore`:

```
node_modules
dist
```

- [ ] **Step 3: 安装依赖并确认能装**

Run: `cd dashboard && npm install`
Expected: 安装成功，生成 `node_modules`（未被 git 跟踪）。
（若环境无网络，记录为已知限制，跳过 `npm install`，后续 Task 9 再装。）

- [ ] **Step 4: Commit**

```bash
git add dashboard/package.json dashboard/vite.config.js dashboard/index.html \
        dashboard/src/main.js dashboard/.gitignore
git commit -m "chore: 前端脚手架(Vite + Vue3)"
```

---

## Task 8: 前端组件与样式

**Files:**
- Create: `dashboard/src/style.css`, `dashboard/src/api.js`, `dashboard/src/App.vue`,
  `dashboard/src/components/PeriodTabs.vue`, `MetricTabs.vue`, `RankingTable.vue`

无 e2e 框架（保持轻量，见设计 §9）。验证在 Task 9 手动跑。

- [ ] **Step 1: api.js — 取数据**

Create `dashboard/src/api.js`:

```js
export async function loadStats() {
  const res = await fetch('./stats.json')
  if (!res.ok) throw new Error(`加载 stats.json 失败: ${res.status}`)
  return await res.json()
}
```

- [ ] **Step 2: style.css — 基础样式**

Create `dashboard/src/style.css`:

```css
:root {
  --bg: #0f1115;
  --panel: #1a1d24;
  --line: #2a2f3a;
  --text: #e6e9ef;
  --muted: #8b93a7;
  --accent: #5b8cff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, "Segoe UI", "PingFang SC", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
}
#app { max-width: 960px; margin: 0 auto; padding: 24px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.meta { color: var(--muted); font-size: 12px; margin-bottom: 20px; }
.controls { display: flex; flex-wrap: wrap; gap: 16px; align-items: center;
  margin-bottom: 16px; }
.group { display: flex; gap: 6px; align-items: center; }
.group > label { color: var(--muted); font-size: 13px; margin-right: 4px; }
button.tab {
  background: var(--panel); color: var(--text); border: 1px solid var(--line);
  padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
button.tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }
select {
  background: var(--panel); color: var(--text); border: 1px solid var(--line);
  padding: 6px 10px; border-radius: 6px; font-size: 13px;
}
table { width: 100%; border-collapse: collapse; background: var(--panel);
  border-radius: 8px; overflow: hidden; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line);
  font-size: 13px; }
th { color: var(--muted); font-weight: 500; cursor: pointer; user-select: none; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.skill-row { cursor: pointer; }
tr.detail td { background: #14171d; color: var(--muted); padding-left: 28px; }
.empty { color: var(--muted); padding: 24px; text-align: center; }
```

- [ ] **Step 3: PeriodTabs.vue**

Create `dashboard/src/components/PeriodTabs.vue`:

```vue
<script setup>
defineProps({ modelValue: String })
defineEmits(['update:modelValue'])
const items = [
  { key: 'day', label: '日' },
  { key: 'week', label: '周' },
  { key: 'month', label: '月' },
]
</script>

<template>
  <div class="group">
    <label>周期</label>
    <button
      v-for="it in items"
      :key="it.key"
      class="tab"
      :class="{ active: modelValue === it.key }"
      @click="$emit('update:modelValue', it.key)"
    >{{ it.label }}</button>
  </div>
</template>
```

- [ ] **Step 4: MetricTabs.vue**

Create `dashboard/src/components/MetricTabs.vue`:

```vue
<script setup>
defineProps({ modelValue: String })
defineEmits(['update:modelValue'])
const items = [
  { key: 'conversations', label: '对话次数' },
  { key: 'tokens', label: 'Token' },
  { key: 'skills', label: 'Skill' },
]
</script>

<template>
  <div class="group">
    <label>维度</label>
    <button
      v-for="it in items"
      :key="it.key"
      class="tab"
      :class="{ active: modelValue === it.key }"
      @click="$emit('update:modelValue', it.key)"
    >{{ it.label }}</button>
  </div>
</template>
```

- [ ] **Step 5: RankingTable.vue**

Create `dashboard/src/components/RankingTable.vue`:

```vue
<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  bucket: { type: Object, default: null },  // 单个时间桶 {users, skills_ranking}
  metric: { type: String, required: true }, // conversations | tokens | skills
  desc: { type: Boolean, default: true },   // 降序
})

const expanded = ref(new Set())
function toggle(name) {
  const s = new Set(expanded.value)
  s.has(name) ? s.delete(name) : s.add(name)
  expanded.value = s
}

const isSkill = computed(() => props.metric === 'skills')

// 用户维度(对话/token): 取 users，按选中数值排序
const userRows = computed(() => {
  const users = props.bucket?.users ?? []
  const val = (u) => props.metric === 'tokens' ? u.tokens.total : u.conversations
  return [...users].sort((a, b) => props.desc ? val(b) - val(a) : val(a) - val(b))
})

// skill 维度: 取 skills_ranking，按 count 排序
const skillRows = computed(() => {
  const ranking = props.bucket?.skills_ranking ?? []
  return [...ranking].sort((a, b) => props.desc ? b.count - a.count : a.count - b.count)
})

function fmt(n) { return (n ?? 0).toLocaleString() }
</script>

<template>
  <div v-if="!bucket" class="empty">该周期暂无数据</div>

  <table v-else-if="!isSkill">
    <thead>
      <tr>
        <th>#</th>
        <th>用户</th>
        <th class="num">对话次数</th>
        <th class="num">Token</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(u, i) in userRows" :key="u.user">
        <td>{{ i + 1 }}</td>
        <td>{{ u.user }}</td>
        <td class="num">{{ fmt(u.conversations) }}</td>
        <td class="num">{{ fmt(u.tokens.total) }}</td>
      </tr>
      <tr v-if="userRows.length === 0"><td colspan="4" class="empty">无数据</td></tr>
    </tbody>
  </table>

  <table v-else>
    <thead>
      <tr>
        <th>#</th>
        <th>Skill</th>
        <th class="num">使用次数</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <template v-for="(s, i) in skillRows" :key="s.name">
        <tr class="skill-row" @click="toggle(s.name)">
          <td>{{ i + 1 }}</td>
          <td>{{ s.name }}</td>
          <td class="num">{{ fmt(s.count) }}</td>
          <td>{{ expanded.has(s.name) ? '▾' : '▸' }}</td>
        </tr>
        <tr v-if="expanded.has(s.name)" class="detail"
            v-for="bu in s.by_user" :key="s.name + '|' + bu.user">
          <td></td>
          <td>{{ bu.user }}</td>
          <td class="num">{{ fmt(bu.count) }}</td>
          <td></td>
        </tr>
      </template>
      <tr v-if="skillRows.length === 0"><td colspan="4" class="empty">无 skill 数据</td></tr>
    </tbody>
  </table>
</template>
```

- [ ] **Step 6: App.vue — 组装**

Create `dashboard/src/App.vue`:

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { loadStats } from './api.js'
import PeriodTabs from './components/PeriodTabs.vue'
import MetricTabs from './components/MetricTabs.vue'
import RankingTable from './components/RankingTable.vue'

const stats = ref(null)
const error = ref(null)
const period = ref('day')        // day | week | month
const metric = ref('conversations')
const desc = ref(true)
const bucketKey = ref(null)

onMounted(async () => {
  try {
    stats.value = await loadStats()
    pickDefaultBucket()
  } catch (e) {
    error.value = e.message
  }
})

const buckets = computed(() => stats.value?.periods?.[period.value] ?? [])

function pickDefaultBucket() {
  const list = buckets.value
  // 默认选最近一个(bucket 已按时间升序，取最后)
  bucketKey.value = list.length ? list[list.length - 1].bucket : null
}

function onPeriodChange(p) {
  period.value = p
  pickDefaultBucket()
}

const currentBucket = computed(() =>
  buckets.value.find((b) => b.bucket === bucketKey.value) ?? null,
)
</script>

<template>
  <h1>Openclaw 使用看板</h1>
  <div class="meta" v-if="stats">生成时间：{{ stats.generated_at }}</div>

  <div v-if="error" class="empty">加载失败：{{ error }}</div>

  <template v-else-if="stats">
    <div class="controls">
      <PeriodTabs :model-value="period" @update:model-value="onPeriodChange" />
      <div class="group">
        <label>时间桶</label>
        <select v-model="bucketKey">
          <option v-for="b in buckets" :key="b.bucket" :value="b.bucket">
            {{ b.label }}
          </option>
        </select>
      </div>
      <MetricTabs v-model="metric" />
      <div class="group">
        <label>排序</label>
        <button class="tab" @click="desc = !desc">{{ desc ? '↓ 降序' : '↑ 升序' }}</button>
      </div>
    </div>

    <RankingTable :bucket="currentBucket" :metric="metric" :desc="desc" />
  </template>

  <div v-else class="empty">加载中…</div>
</template>
```

- [ ] **Step 7: Commit**

```bash
git add dashboard/src
git commit -m "feat: 看板前端(周期/维度切换, 升降序, skill 行展开)"
```

---

## Task 9: 手动验证前端

**Files:** 无（验证步骤）

- [ ] **Step 1: 安装依赖（若 Task 7 未装）**

Run: `cd dashboard && npm install`
Expected: 成功。若无网络无法安装，记录限制并请用户在有网环境跑。

- [ ] **Step 2: 启动 dev server**

Run: `cd dashboard && npm run dev`
Expected: Vite 打印本地 URL（如 `http://localhost:5173`）。

- [ ] **Step 3: 浏览器逐项验证**

打开 URL，确认：
- 标题 + generated_at 正常显示。
- 周期 [日][周][月] 可切；切换后时间桶下拉相应变化，默认选最近桶。
- 维度 [对话次数] 默认显示用户列表，weiwu2 对话=33。
- 切 [Token]：列表按 Token 排，weiwu2 Token=1,419,527。
- 切 [Skill]：列表行是 skill；`biz-meeting-summary` 次数=13；点击该行展开看到 `weiwu2 13`。
- [↓降序]/[↑升序] 切换会反转列表顺序。

- [ ] **Step 4: 构建产物自检**

Run: `cd dashboard && npm run build`
Expected: 生成 `dashboard/dist/`，无报错。（dist 已被 .gitignore 忽略，不提交。）

- [ ] **Step 5: 提交 README（如有调整）**

Create `dashboard/README.md`:

```markdown
# Openclaw 使用看板（前端）

读取 `public/stats.json` 渲染的轻量看板。stats.json 由
`scripts/openclaw_dashboard_stats.py` 生成。

## 开发

```bash
# 1) 生成/更新数据
python3 ../scripts/openclaw_dashboard_stats.py ../examples/example-log.jsonl \
    --user weiwu2 --out public/stats.json

# 2) 启动
npm install
npm run dev
```

## 构建

```bash
npm run build   # 产物在 dist/
```

## 交互

- 周期：日 / 周 / 月切换 + 时间桶下拉
- 维度：对话次数 / Token（按用户排）、Skill（按 skill 排，行可展开看用户明细）
- 排序：升 / 降序切换
```

```bash
git add dashboard/README.md
git commit -m "docs: dashboard 前端 README"
```

---

## Task 10: 收尾 — 全量回归 + 顶层 README 指引

**Files:**
- Modify: `scripts/README.md`（追加 dashboard 段落）

- [ ] **Step 1: 全量测试回归**

Run: `python3 -m pytest scripts/tests -v`
Expected: 全绿（新旧用例都过）。

- [ ] **Step 2: 在 scripts/README.md 追加段落**

在 `scripts/README.md` 末尾追加：

```markdown

## openclaw_dashboard_stats.py — 看板数据聚合

把本地 OpenClaw 会话 jsonl 按 用户×(日/周/月)×(对话/token/skill) 聚合成
前端看板用的 stats.json。**无需 openclaw 运行环境**。

skill 识别口径：skill = `~/.openclaw/.../skills/<name>/` 目录；统计 agent 用
read/exec/edit 等工具操作该目录的 toolCall 次数（不是把 read/exec 当 skill）。

### 用法

```bash
# 单文件，指定用户，写到前端 public 目录
python3 scripts/openclaw_dashboard_stats.py examples/example-log.jsonl \
    --user weiwu2 --out dashboard/public/stats.json

# 多用户(路径与 --user 一一对应)
python3 scripts/openclaw_dashboard_stats.py \
    /data/weiwu2/sessions /data/bnzhu/sessions \
    --user weiwu2 --user bnzhu --out dashboard/public/stats.json
```

### 前端

见 [dashboard/README.md](../dashboard/README.md)。

### 设计 / 计划

- [docs/superpowers/specs/2026-06-08-openclaw-dashboard-design.md](../docs/superpowers/specs/2026-06-08-openclaw-dashboard-design.md)
- [docs/superpowers/plans/2026-06-08-openclaw-dashboard.md](../docs/superpowers/plans/2026-06-08-openclaw-dashboard.md)
```

- [ ] **Step 3: Commit**

```bash
git add scripts/README.md
git commit -m "docs: README 增加 dashboard 聚合脚本说明"
```

---

## Self-Review 结果

- **Spec 覆盖**：§2 skill 识别→Task1；§5 时间桶→Task2；§5/§6 聚合+结构→Task3/4；
  §3 用户识别(本地默认用户)→Task5；样例产物→Task6；§7 前端交互(周期/维度/排序/skill展开)
  →Task7/8；§9 测试(脚本侧 pytest 真实样例 + 前端手动)→各 Task 测试步 + Task9；
  §10 健康规则(坏 JSON/坏时间戳跳过)→Task3 `test_corrupt_and_bad_timestamp_skipped`、
  Task5 CLI 解析容错。全部有对应任务。
- **占位符扫描**：无 TBD/TODO；每个代码步都有完整代码。
- **类型/命名一致**：`skills_in_message`/`skills_in_toolcall`(Task1)、`bucket_keys`/`aggregate`
  (Task2/3)、`to_dashboard_json`(Task4)、CLI `main`(Task5)在前后任务里命名一致；
  stats.json 字段(`conversations`/`tokens.total`/`skills_ranking`/`by_user`)在脚本(Task3)
  与前端(Task8 RankingTable/App)里一致。
- **不破坏旧 CLI**：skill 识别走新模块 `skills.py`，未改 `parser.aggregate_line`；Task5 Step5
  专门跑全量回归确认旧用例不挂。
