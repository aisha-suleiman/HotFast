"""Сторож HTTP-сессии Telegram.

Долгий обрыв сети «отравляет» соединение: aiohttp держит пул к адресу, которого больше
нет, и продолжает биться в него даже после того, как интернет вернулся. Наблюдалось вживую
— бот полтора часа сыпал ``Failed to fetch updates``, хотя параллельный запрос из соседнего
процесса проходил с первого раза. Для владельца это выглядит как «бот умер»: с телефона он
просто молчит.

Опрос Telegram сам себя не чинит, поэтому за ним присматривает отдельная задача: если связи
нет несколько проверок подряд, она закрывает сессию. Следующий запрос создаст новую — с
чистым пулом соединений и свежим DNS.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

logger = logging.getLogger(__name__)

#: Как часто проверять связь.
CHECK_INTERVAL_SEC = 60
#: Сколько неудач подряд считать зависанием, а не рябью на линии.
FAILURES_BEFORE_RESET = 3


async def session_watchdog(
    bot: Bot,
    interval: int = CHECK_INTERVAL_SEC,
    failures_before_reset: int = FAILURES_BEFORE_RESET,
) -> None:
    failures = 0
    while True:
        await asyncio.sleep(interval)
        try:
            await bot.get_me()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — сторож не должен умирать сам
            failures += 1
            logger.warning(
                "Telegram не отвечает (%d из %d до пересоздания сессии): %s",
                failures,
                failures_before_reset,
                exc,
            )
            if failures >= failures_before_reset:
                await _reset(bot)
                failures = 0
            continue

        if failures:
            logger.info("Связь с Telegram восстановилась")
        failures = 0


async def _reset(bot: Bot) -> None:
    """Закрывает сессию. aiogram создаст новую при следующем запросе."""
    logger.warning("Пересоздаю HTTP-сессию: соединение зависло после обрыва сети")
    try:
        await bot.session.close()
    except Exception:  # noqa: BLE001 — закрыть сломанную сессию тоже может не выйти
        logger.exception("Не удалось закрыть сессию, следующая попытка через минуту")
