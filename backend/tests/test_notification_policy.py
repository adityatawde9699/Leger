from datetime import datetime

from app.services.notification_policy import apply_notification_policy, within_quiet_hours


def test_quiet_hours_support_overnight_and_daytime_windows():
    assert within_quiet_hours(23, 22, 7)
    assert within_quiet_hours(6, 22, 7)
    assert not within_quiet_hours(12, 22, 7)
    assert within_quiet_hours(12, 9, 17)


def test_notification_policy_applies_quiet_hours_and_cap():
    items = [{"id": str(i)} for i in range(5)]
    assert apply_notification_policy(items, now=datetime(2026, 1, 1, 23), start=22, end=7, daily_cap=3) == []
    assert apply_notification_policy(items, now=datetime(2026, 1, 1, 12), start=22, end=7, daily_cap=2) == items[:2]
