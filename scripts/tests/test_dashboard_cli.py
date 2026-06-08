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


def _example_lines():
    return EXAMPLE.read_text(encoding="utf-8").splitlines()


class TestDockerSource:
    def test_scans_containers_and_extracts_user(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["openclaw-weiwu2-gateway"],
        )
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter(_example_lines()),
        )
        rc = cli.main(["--source", "docker",
                       "--generated-at", "2026-06-08T00:00:00Z"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        day = {b["bucket"]: b for b in parsed["periods"]["day"]}
        u = day["2026-05-25"]["users"][0]
        assert u["user"] == "weiwu2"
        assert u["conversations"] == 33
        assert day["2026-05-25"]["skills_ranking"][0]["name"] == "biz-meeting-summary"
        assert day["2026-05-25"]["skills_ranking"][0]["count"] == 13

    def test_skips_unparseable_container_name(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["nginx", "openclaw-weiwu2-gateway"],
        )
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter([]),
        )
        rc = cli.main(["--source", "docker",
                       "--generated-at", "2026-06-08T00:00:00Z"])
        assert rc == 0
        parsed = json.loads(capsys.readouterr().out)
        # nginx 不是 openclaw-{user}-gateway，被跳过；无数据则三周期为空
        assert parsed["periods"]["day"] == []

    def test_user_filter_limits_containers(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["openclaw-weiwu2-gateway", "openclaw-bnzhu-gateway"],
        )
        seen = []

        def fake_read(container):
            seen.append(container)
            return iter(_example_lines()) if "weiwu2" in container else iter([])

        monkeypatch.setattr(cli.docker_io, "read_container_sessions", fake_read)
        rc = cli.main(["--source", "docker", "--user", "weiwu2",
                       "--generated-at", "2026-06-08T00:00:00Z"])
        assert rc == 0
        # 只读了 weiwu2 的容器
        assert seen == ["openclaw-weiwu2-gateway"]
        parsed = json.loads(capsys.readouterr().out)
        users = parsed["periods"]["month"][0]["users"]
        assert [u["user"] for u in users] == ["weiwu2"]

    def test_docker_writes_out_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            cli.docker_io, "list_containers",
            lambda **kw: ["openclaw-weiwu2-gateway"],
        )
        monkeypatch.setattr(
            cli.docker_io, "read_container_sessions",
            lambda c: iter(_example_lines()),
        )
        out = tmp_path / "stats.json"
        rc = cli.main(["--source", "docker", "--out", str(out),
                       "--generated-at", "2026-06-08T00:00:00Z"])
        assert rc == 0
        parsed = json.loads(out.read_text(encoding="utf-8"))
        day = {b["bucket"]: b for b in parsed["periods"]["day"]}
        assert day["2026-05-25"]["users"][0]["conversations"] == 33
