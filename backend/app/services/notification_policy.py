"""Deterministic quiet-hour and delivery-cap policy for proactive notifications."""

from datetime import datetime


def within_quiet_hours(hour: int, start: int, end: int) -> bool:
    if start == end:
        return True
    return hour >= start or hour < end if start > end else start <= hour < end


def apply_notification_policy(items: list[dict], *, now: datetime, start: int, end: int, daily_cap: int) -> list[dict]:
    if within_quiet_hours(now.hour, start, end) or daily_cap == 0:
        return []
    return items[:max(0, daily_cap)]
