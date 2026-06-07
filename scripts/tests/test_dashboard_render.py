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
