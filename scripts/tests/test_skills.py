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
