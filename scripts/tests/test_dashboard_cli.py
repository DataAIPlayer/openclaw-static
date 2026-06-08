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
