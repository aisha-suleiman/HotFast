"""Рабочие часы. Кухня закрывается после полуночи, поэтому интервал может её пересекать."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


def is_open_at(now: time, start: time, end: time) -> bool:
    """Открыто ли в момент ``now``.

    ``start < end``  — обычный интервал внутри одних суток (11:00–23:00).
    ``start > end``  — интервал через полночь (11:00–02:00): открыто и в 23:30, и в 01:30.
    ``start == end`` — круглосуточно.
    """
    if start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end


def is_open(start: time, end: time, tz: ZoneInfo, *, at: datetime | None = None) -> bool:
    moment = at.astimezone(tz) if at else datetime.now(tz)
    return is_open_at(moment.time(), start, end)


def accepting_orders(settings, at: datetime | None = None) -> bool:
    """Принимаем ли заказы прямо сейчас.

    Кроме обычных часов работы учитывает временный круглосуточный режим: он задаётся
    моментом окончания и выключается сам, когда этот момент наступил. Так режим,
    включённый для проверки, не может остаться включённым навсегда и собрать ночные
    заказы, которые некому готовить.
    """
    now = (at or datetime.now(settings.timezone)).astimezone(settings.timezone)

    until = settings.hours_override_until
    if until is not None:
        if until.tzinfo is None:
            # В .env время удобнее писать без смещения — считаем его местным.
            until = until.replace(tzinfo=settings.timezone)
        if now < until:
            return True

    return is_open_at(now.time(), *settings.hours)


def format_hours(start: time, end: time) -> str:
    return f"{start:%H:%M}–{end:%H:%M}"
