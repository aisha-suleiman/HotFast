"""Рабочие часы, в том числе интервал через полночь."""

from __future__ import annotations

from datetime import time

import pytest

from bot.services.schedule import format_hours, is_open_at

NIGHT = (time(11, 0), time(2, 0))   # 11:00–02:00, через полночь
DAY = (time(9, 0), time(18, 0))     # обычный дневной интервал


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (time(11, 0), True),    # ровно открытие
        (time(23, 30), True),   # поздний вечер
        (time(0, 30), True),    # уже после полуночи
        (time(1, 59), True),    # последняя минута
        (time(2, 0), False),    # ровно закрытие
        (time(3, 0), False),
        (time(10, 59), False),
    ],
)
def test_overnight_interval(now: time, expected: bool):
    assert is_open_at(now, *NIGHT) is expected


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (time(8, 59), False),
        (time(9, 0), True),
        (time(17, 59), True),
        (time(18, 0), False),
        (time(23, 0), False),
    ],
)
def test_same_day_interval(now: time, expected: bool):
    assert is_open_at(now, *DAY) is expected


def test_equal_bounds_mean_round_the_clock():
    assert is_open_at(time(4, 0), time(0, 0), time(0, 0)) is True


def test_hours_are_formatted_for_display():
    assert format_hours(*NIGHT) == "11:00–02:00"
