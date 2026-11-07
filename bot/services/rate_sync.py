"""Фоновое обновление курса и его сохранение между запусками.

Отдельный модуль, потому что :mod:`bot.services.rates` ничего не знает о базе — иначе
репозиторий и сервис импортировали бы друг друга по кругу.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.repo.rates import RateRepo
from bot.services.rates import RateProvider, RateUnavailable

logger = logging.getLogger(__name__)

#: Как часто проверять, не пора ли обновиться. Само обновление реже — по RATE_TTL_MIN.
CHECK_INTERVAL_SEC = 60


async def warm_up(
    provider: RateProvider, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """Поднимает последний известный курс из базы и пробует обновить его на старте.

    Если сайт недоступен, бот всё равно запустится и покажет вчерашний курс: падать
    из-за чужого сайта нельзя — заказы важнее второй цены.
    """
    if not provider.enabled:
        return

    async with sessionmaker() as session:
        stored = await RateRepo(session).get(
            provider.settings.currency, provider.settings.secondary_currency
        )
    provider.prime(stored)
    if stored is not None:
        logger.info("Курс из базы: 1 %s = %.6f %s", stored.base, stored.as_float, stored.quote)

    await sync_once(provider, sessionmaker)


async def adopt_stored(
    provider: RateProvider, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """Подхватывает курс из базы без обращения к сайту — для serverless-инстансов."""
    if not provider.enabled:
        return
    async with sessionmaker() as session:
        stored = await RateRepo(session).get(
            provider.settings.currency, provider.settings.secondary_currency
        )
    provider.adopt(stored)


async def sync_once(
    provider: RateProvider, sessionmaker: async_sessionmaker[AsyncSession]
) -> bool:
    """Обновляет курс и сохраняет его. True — получилось."""
    try:
        rate = await provider.refresh()
    except RateUnavailable as exc:
        logger.warning("Курс не обновлён (%s). Работаем с последним известным.", exc)
        return False

    async with sessionmaker() as session:
        await RateRepo(session).save(rate)
        await session.commit()
    return True


async def rates_loop(
    provider: RateProvider,
    sessionmaker: async_sessionmaker[AsyncSession],
    interval: int = CHECK_INTERVAL_SEC,
) -> None:
    while True:
        await asyncio.sleep(interval)
        if not provider.enabled or not provider.is_stale:
            continue
        try:
            await sync_once(provider, sessionmaker)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — цикл не должен умирать из-за одной итерации
            logger.exception("Ошибка в задаче обновления курса")
