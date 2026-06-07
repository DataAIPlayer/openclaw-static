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
