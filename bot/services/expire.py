"""Фоновая отмена заказов, по которым так и не пришла оплата.

Без неё неоплаченные заказы копились бы в группе кухни и путали смену: непонятно, ждать
клиента или нет. Таймер один на весь бот и работает поверх собственных сессий БД, потому
что живёт вне обработки апдейтов.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.db.enums import OrderStatus
from bot.db.repo import Repos
from bot.services.notifier import Notifier
from bot.services.orders import InvalidTransition, apply_transition

logger = logging.getLogger(__name__)

#: Как часто проверяем. Минуты достаточно: таймаут измеряется десятками минут.
CHECK_INTERVAL_SEC = 60


async def expire_unpaid_once(
    sessionmaker: async_sessionmaker[AsyncSession],
    notifier: Notifier,
    settings: Settings,
) -> int:
    """Отменяет просроченные заказы. Возвращает, сколько отменил."""
    async with sessionmaker() as session:
        repos = Repos.build(session)
        stale = await repos.orders.stale_unpaid(timeout_min=settings.payment_timeout_min)

        cancelled = 0
        for order in stale:
            try:
                previous = apply_transition(order, OrderStatus.CANCELLED)
            except InvalidTransition:
                continue
            await repos.orders.log_transition(
                order,
                from_status=previous,
                to_status=OrderStatus.CANCELLED,
                actor_tg_id=None,
                actor_name="auto",
            )
            await session.refresh(order, ["logs", "items", "user", "branch"])

            await notifier.refresh(order)
            t = notifier.client_translator(order)
            await notifier.send_to_client(
                order.user_id,
                t("shamcash-timeout", no=order.public_no),
            )
            cancelled += 1

        await session.commit()
        return cancelled


async def expire_unpaid_loop(
    sessionmaker: async_sessionmaker[AsyncSession],
    notifier: Notifier,
    settings: Settings,
    interval: int = CHECK_INTERVAL_SEC,
) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            count = await expire_unpaid_once(sessionmaker, notifier, settings)
            if count:
                logger.info("Отменено по таймауту оплаты: %d", count)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — цикл не должен умирать из-за одной итерации
            logger.exception("Ошибка в задаче отмены неоплаченных заказов")
