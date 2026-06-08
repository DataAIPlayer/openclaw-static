import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import openclaw_stats as cli
from openclaw_stats_lib import docker_io, parser, render
from openclaw_stats_lib.parser import (
    UserStats,
    aggregate_line,
    aggregate_lines,
    aggregate_lines_into,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.jsonl"


class TestUserFromContainerName:
    @pytest.mark.parametrize(
        "container,expected",
        [
            ("openclaw-weiwu2-gateway", "weiwu2"),
            ("openclaw-xyyu30-gateway", "xyyu30"),
            ("openclaw-jieyang26-gateway", "jieyang26"),
            ("openclaw-mclin-gateway", "mclin"),
        ],
    )
    def test_valid_names(self, container, expected):
        assert parser.user_from_container_name(container) == expected

    def test_invalid_name_returns_none(self):
        assert parser.user_from_container_name("nginx") is None
        assert parser.user_from_container_name("openclaw-weiwu2") is None
        assert parser.user_from_container_name("foo-bar-gateway") is None


class TestAggregateLine:
    def test_assistant_with_usage(self):
        stats = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
        line = json.dumps({
            "type": "message",
            "timestamp": "2026-05-03T02:00:03.739Z",
            "message": {
                "role": "assistant",
                "model": "gpt-5.4",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {
                    "input": 100, "output": 20,
                    "cacheRead": 0, "cacheWrite": 0,
                    "totalTokens": 120,
                    "cost": {"input": 0.001, "output": 0.002,
                             "cacheRead": 0, "cacheWrite": 0,
                             "total": 0.003},
                },
            },
        })
        aggregate_line(stats, line)
        assert stats.requests == 1
        assert stats.input_tokens == 100
        assert stats.output_tokens == 20
        assert stats.total_tokens == 120
        assert stats.cost_total == pytest.approx(0.003)
        assert stats.models == {"gpt-5.4"}

    def test_assistant_with_toolcall(self):
        stats = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
        line = json.dumps({
            "type": "message",
            "timestamp": "2026-05-03T02:00:03.739Z",
            "message": {
                "role": "assistant",
                "model": "gpt-5.4",
                "content": [
                    {"type": "toolCall", "id": "c1", "name": "read", "arguments": {}},
                    {"type": "toolCall", "id": "c2", "name": "read", "arguments": {}},
                    {"type": "toolCall", "id": "c3", "name": "exec", "arguments": {}},
                ],
                "usage": {"input": 1, "output": 1, "totalTokens": 2,
                          "cacheRead": 0, "cacheWrite": 0,
                          "cost": {"total": 0.0}},
            },
        })
        aggregate_line(stats, line)
        assert stats.skill_calls == {"read": 2, "exec": 1}

    def test_assistant_without_usage(self):
        stats = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
        line = json.dumps({
            "type": "message",
            "timestamp": "2026-05-03T02:00:03.739Z",
            "message": {"role": "assistant", "content": []},
        })
        aggregate_line(stats, line)
        assert stats.requests == 1
        assert stats.input_tokens == 0
        assert stats.total_tokens == 0

    def test_user_role_does_not_count_as_request(self):
        stats = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
        line = json.dumps({
            "type": "message",
            "timestamp": "2026-05-03T02:00:00Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        })
        aggregate_line(stats, line)
        assert stats.requests == 0

    def test_corrupt_line_returns_false(self):
        stats = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
        ok = aggregate_line(stats, "{not json")
        assert ok is False
        assert stats.requests == 0

    def test_timestamp_tracks_first_and_last(self):
        stats = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
        for ts in ["2026-05-03T02:00:00Z", "2026-05-04T02:00:00Z", "2026-05-01T02:00:00Z"]:
            line = json.dumps({
                "type": "message",
                "timestamp": ts,
                "message": {"role": "user", "content": []},
            })
            aggregate_line(stats, line)
        assert stats.first_seen.isoformat().startswith("2026-05-01")
        assert stats.last_seen.isoformat().startswith("2026-05-04")


class TestAggregateLines:
    def test_fixture_aggregation(self):
        with FIXTURE.open() as fh:
            stats, corrupt = aggregate_lines(
                user="weiwu2",
                container="openclaw-weiwu2-gateway",
                source_name="sample.jsonl",
                lines=fh,
            )
        assert stats.requests == 3
        assert stats.input_tokens == 350
        assert stats.output_tokens == 60
        assert stats.total_tokens == 410
        assert stats.cache_read == 100
        assert stats.cache_write == 0
        assert stats.cost_total == pytest.approx(0.01)
        assert stats.models == {"gpt-5.4"}
        assert stats.skill_calls == {"read": 1, "exec": 1}
        assert stats.first_seen.isoformat().startswith("2026-05-03T02:00:00")
        assert stats.last_seen.isoformat().startswith("2026-05-03T02:00:13")
        assert "sample.jsonl" in stats.sessions_files
        assert corrupt == 1

    def test_multiple_sources_merge_into_same_stats(self):
        stats = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
        with FIXTURE.open() as fh:
            corrupt1 = aggregate_lines_into(stats, "a.jsonl", fh)
        with FIXTURE.open() as fh:
            corrupt2 = aggregate_lines_into(stats, "b.jsonl", fh)
        assert stats.requests == 6
        assert stats.total_tokens == 820
        assert stats.sessions_files == {"a.jsonl", "b.jsonl"}
        assert corrupt1 + corrupt2 == 2


class TestDockerIO:
    def test_list_containers_parses_output(self, monkeypatch):
        fake = MagicMock()
        fake.stdout = "openclaw-weiwu2-gateway\nopenclaw-bnzhu-gateway\n\n"
        fake.returncode = 0
        called = {}

        def fake_run(cmd, **kwargs):
            called["cmd"] = cmd
            return fake

        monkeypatch.setattr(docker_io.subprocess, "run", fake_run)
        result = docker_io.list_containers(name_substring="openclaw-")
        assert result == ["openclaw-weiwu2-gateway", "openclaw-bnzhu-gateway"]
        assert "docker" in called["cmd"]
        assert "ps" in called["cmd"]
        assert "name=openclaw-" in " ".join(called["cmd"])

    def test_read_container_sessions_yields_lines(self, monkeypatch):
        fake = MagicMock()
        fake.stdout = '{"type":"message"}\n{"type":"message","id":"2"}\n'
        fake.returncode = 0

        monkeypatch.setattr(docker_io.subprocess, "run", lambda cmd, **kw: fake)
        lines = list(docker_io.read_container_sessions("openclaw-weiwu2-gateway"))
        assert lines == ['{"type":"message"}', '{"type":"message","id":"2"}']

    def test_read_container_sessions_handles_missing_dir(self, monkeypatch):
        fake = MagicMock()
        fake.stdout = ""
        fake.stderr = "No such file or directory"
        fake.returncode = 1

        monkeypatch.setattr(docker_io.subprocess, "run", lambda cmd, **kw: fake)
        lines = list(docker_io.read_container_sessions("openclaw-weiwu2-gateway"))
        assert lines == []

    def test_list_containers_handles_missing_docker(self, monkeypatch):
        def raise_fnf(cmd, **kw):
            raise FileNotFoundError("docker")

        monkeypatch.setattr(docker_io.subprocess, "run", raise_fnf)
        assert docker_io.list_containers() == []

    def test_read_container_sessions_handles_missing_docker(self, monkeypatch):
        def raise_fnf(cmd, **kw):
            raise FileNotFoundError("docker")

        monkeypatch.setattr(docker_io.subprocess, "run", raise_fnf)
        assert list(docker_io.read_container_sessions("openclaw-x-gateway")) == []


def _sample_stats() -> list[UserStats]:
    s1 = UserStats(user="weiwu2", container="openclaw-weiwu2-gateway")
    s1.requests = 842
    s1.input_tokens = 1_234_567
    s1.output_tokens = 45_678
    s1.total_tokens = 1_280_245
    s1.cost_total = 4.56
    s1.models = {"gpt-5.4"}
    s1.skill_calls = Counter({"read": 312, "exec": 208, "bash": 95})
    s1.first_seen = datetime(2026, 5, 1, tzinfo=timezone.utc)
    s1.last_seen = datetime(2026, 5, 24, tzinfo=timezone.utc)
    s1.sessions_files = {"a.jsonl", "b.jsonl"}

    s2 = UserStats(user="bnzhu", container="openclaw-bnzhu-gateway")
    s2.requests = 100
    s2.total_tokens = 50_000
    s2.cost_total = 1.0
    return [s1, s2]


class TestRenderJSON:
    def test_json_structure(self):
        stats = _sample_stats()
        out = render.to_json(stats, corrupt_lines=2, containers_without_sessions=["x"])
        parsed = json.loads(out)
        assert parsed["totals"]["containers"] == 2
        assert parsed["totals"]["requests"] == 942
        assert parsed["totals"]["total_tokens"] == 1_330_245
        assert parsed["totals"]["cost_total"] == pytest.approx(5.56)
        assert len(parsed["users"]) == 2
        # 用户应按 total_tokens 降序
        assert parsed["users"][0]["user"] == "weiwu2"
        assert parsed["users"][0]["skill_calls"] == {"read": 312, "exec": 208, "bash": 95}
        assert parsed["users"][0]["sessions"] == 2
        assert parsed["users"][0]["first_seen"].startswith("2026-05-01")
        assert parsed["errors"]["corrupt_lines"] == 2
        assert parsed["errors"]["containers_without_sessions"] == ["x"]


class TestRenderTable:
    def test_table_contains_headers_and_users(self):
        stats = _sample_stats()
        out = render.to_table(stats, top_skills=3)
        assert "OpenClaw 用户使用统计" in out
        assert "weiwu2" in out
        assert "bnzhu" in out
        assert "read(312)" in out
        # 应有汇总行
        assert "总请求" in out or "请求" in out

    def test_table_top_skills_limit(self):
        stats = _sample_stats()
        stats[0].skill_calls = Counter({"a": 5, "b": 4, "c": 3, "d": 2, "e": 1})
        out = render.to_table(stats, top_skills=2)
        assert "a(5)" in out
        assert "b(4)" in out
        # top 2 之外应聚合为 ...others
        assert "others" in out


class TestCLI:
    def test_main_table_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["openclaw-weiwu2-gateway"],
        )
        with FIXTURE.open() as fh:
            sample_lines = fh.read().splitlines()
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter(sample_lines),
        )
        rc = cli.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "weiwu2" in out
        assert "OpenClaw 用户使用统计" in out

    def test_main_json_output(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["openclaw-weiwu2-gateway"],
        )
        with FIXTURE.open() as fh:
            sample_lines = fh.read().splitlines()
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter(sample_lines),
        )
        rc = cli.main(["--format", "json"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["totals"]["requests"] == 3
        assert parsed["totals"]["total_tokens"] == 410
        assert parsed["users"][0]["user"] == "weiwu2"
        assert parsed["errors"]["corrupt_lines"] == 1

    def test_main_filter_user(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: [
                "openclaw-weiwu2-gateway",
                "openclaw-bnzhu-gateway",
            ],
        )
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter([]),
        )
        rc = cli.main(["--user", "weiwu2", "--format", "json"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert [u["user"] for u in parsed["users"]] == ["weiwu2"]

    def test_main_skips_unparseable_container_name(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["nginx", "openclaw-weiwu2-gateway"],
        )
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter([]),
        )
        rc = cli.main(["--format", "json"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert [u["user"] for u in parsed["users"]] == ["weiwu2"]

    def test_main_user_with_no_sessions_appears_in_output_with_zeros(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["openclaw-emptyuser-gateway"],
        )
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter([]),
        )
        rc = cli.main(["--format", "json"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        assert [u["user"] for u in parsed["users"]] == ["emptyuser"]
        assert parsed["users"][0]["requests"] == 0
        assert parsed["users"][0]["total_tokens"] == 0
        assert parsed["errors"]["containers_without_sessions"] == [
            "openclaw-emptyuser-gateway"
        ]
