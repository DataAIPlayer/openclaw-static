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
