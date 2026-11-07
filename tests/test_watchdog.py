"""Сторож HTTP-сессии: чинит зависшее соединение и не трогает исправное.

Поведение из реальной поломки: после полуторачасового обрыва VPN бот продолжал сыпать
``Failed to fetch updates``, хотя параллельный запрос из соседнего процесса проходил с
первого раза. Сессия оставалась мёртвой навсегда, и для владельца бот выглядел умершим.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from bot.services.watchdog import session_watchdog


class Boom(RuntimeError):
    pass


@dataclass
class FakeSession:
    closed: int = 0

    async def close(self) -> None:
        self.closed += 1


@dataclass
class FakeBot:
    """Отдаёт ошибку, пока не закроют сессию, — как зависший пул соединений."""

    fail_until_reset: bool = False
    always_fail: bool = False
    calls: int = 0
    session: FakeSession = field(default_factory=FakeSession)
    _reset_seen: int = 0

    async def get_me(self):
        self.calls += 1
        if self.always_fail:
            raise Boom("сеть недоступна")
        if self.fail_until_reset and self.session.closed == self._reset_seen:
            raise Boom("соединение зависло")
        return object()


async def run_watchdog(bot: FakeBot, ticks: int, failures_before_reset: int = 3) -> None:
    """Прогоняет заданное число проверок и снимает задачу."""
    task = asyncio.create_task(
        session_watchdog(bot, interval=0, failures_before_reset=failures_before_reset)
    )
    for _ in range(ticks * 4):  # даём событийному циклу прокрутиться
        await asyncio.sleep(0)
        if bot.calls >= ticks:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_healthy_session_is_left_alone():
    """Пока Telegram отвечает, сессию трогать нельзя."""
    bot = FakeBot()
    await run_watchdog(bot, ticks=5)

    assert bot.calls >= 5
    assert bot.session.closed == 0


async def test_single_hiccup_does_not_reset():
    """Одна осечка на линии — не повод рвать соединение."""
    bot = FakeBot(always_fail=True)
    await run_watchdog(bot, ticks=2, failures_before_reset=3)

    assert bot.session.closed == 0


async def test_sustained_failure_resets_the_session():
    bot = FakeBot(always_fail=True)
    await run_watchdog(bot, ticks=3, failures_before_reset=3)

    assert bot.session.closed >= 1


async def test_reset_actually_revives_the_bot():
    """Главное: после пересоздания сессии запросы снова проходят."""
    bot = FakeBot(fail_until_reset=True)
    await run_watchdog(bot, ticks=6, failures_before_reset=3)

    assert bot.session.closed == 1
    assert await bot.get_me() is not None


async def test_watchdog_survives_a_broken_close():
    """Даже если закрыть сессию не удалось, сторож продолжает работать."""

    class StubbornSession(FakeSession):
        async def close(self) -> None:
            self.closed += 1
            raise Boom("не закрывается")

    bot = FakeBot(always_fail=True, session=StubbornSession())
    await run_watchdog(bot, ticks=8, failures_before_reset=2)

    assert bot.session.closed >= 2, "сторож должен пробовать снова, а не сдаться"
