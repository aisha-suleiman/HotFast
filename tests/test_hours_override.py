"""Временный круглосуточный приём заказов.

Нужен, чтобы проверять бота в нерабочее время. Задаётся моментом окончания и гаснет сам:
режим, включённый ради теста, не должен остаться включённым навсегда и собрать ночные
заказы, которые некому готовить.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.services.schedule import accepting_orders
from tests.test_order_flow import make_settings

TZ = ZoneInfo("Asia/Damascus")


def at(hour: int, minute: int = 0, day: int = 10) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=TZ)


def settings(until: datetime | None = None, hours: str = "10:00-22:00"):
    return make_settings(working_hours=hours, hours_override_until=until, tz="Asia/Damascus")


# ── обычные часы, без режима ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("moment", "expected"),
    [(at(9, 59), False), (at(10, 0), True), (at(21, 59), True), (at(22, 0), False)],
)
def test_plain_working_hours(moment: datetime, expected: bool):
    assert accepting_orders(settings(), at=moment) is expected


# ── режим включён ─────────────────────────────────────────────────────────────


def test_override_opens_the_shop_before_working_hours():
    assert accepting_orders(settings(until=at(10, 0)), at=at(8, 30)) is True


def test_override_expires_exactly_at_its_moment():
    """Ровно в 10:00 режим кончается — дальше работают обычные часы."""
    s = settings(until=at(10, 0))
    assert accepting_orders(s, at=at(9, 59)) is True
    assert accepting_orders(s, at=at(10, 0)) is True    # уже по обычным часам
    assert accepting_orders(s, at=at(22, 0)) is False   # режима нет, вечер закрыт


def test_expired_override_does_not_reopen_the_night():
    """Главное свойство: назавтра ночью бот закрыт, хотя строка в .env осталась."""
    assert accepting_orders(settings(until=at(10, 0)), at=at(3, 0, day=11)) is False


def test_override_in_the_past_is_harmless():
    assert accepting_orders(settings(until=at(10, 0, day=1)), at=at(8, 0)) is False


def test_override_without_timezone_is_read_as_local():
    """В .env время удобнее писать без смещения — считаем его сирийским."""
    naive = datetime(2026, 9, 10, 10, 0)
    s = settings(until=naive)
    assert accepting_orders(s, at=at(9, 0)) is True
    assert accepting_orders(s, at=at(3, 0, day=11)) is False


def test_override_does_not_shorten_normal_hours():
    """Режим только открывает, но никогда не закрывает раньше времени."""
    s = settings(until=at(10, 0))
    assert accepting_orders(s, at=at(15, 0)) is True


def test_no_override_configured():
    assert accepting_orders(settings(until=None), at=at(8, 0)) is False


# ── ночной интервал через полночь ─────────────────────────────────────────────


def test_override_works_with_overnight_hours():
    s = settings(until=at(10, 0), hours="11:00-02:00")
    assert accepting_orders(s, at=at(9, 0)) is True     # режим
    assert accepting_orders(s, at=at(10, 30)) is False  # режим кончился, до 11 закрыто
    assert accepting_orders(s, at=at(23, 0)) is True    # обычные часы
    assert accepting_orders(s, at=at(1, 0, day=11)) is True


# ── момент берётся в часовом поясе заведения ──────────────────────────────────


def test_moment_is_converted_to_shop_timezone():
    """Сервер может стоять в другой стране — решает время Сирии, а не машины."""
    s = settings(until=at(10, 0))
    utc_moment = datetime(2026, 9, 10, 12, 0, tzinfo=ZoneInfo("UTC"))  # 15:00 в Сирии
    assert accepting_orders(s, at=utc_moment) is True
