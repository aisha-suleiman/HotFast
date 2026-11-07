"""Защита от протухших нажатий.

Telegram хранит callback-запрос около минуты. Если бот в этот момент лежал, ответ на
кнопку отклоняется с ``query is too old``. Само по себе это пустяк — клиент просто не
увидит всплывающую подсказку. Опасно другое: исключение доходит до
:class:`~bot.middlewares.db.DbSessionMiddleware`, та откатывает транзакцию, и **уже
сделанная смена статуса пропадает** — карточка на кухне перерисована, а в базе заказ
остался прежним.

Поэтому такие ошибки гасятся здесь, внутри транзакции: работа хендлера считается
выполненной и коммитится, а не отвечает Telegram только всплывашка.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)

#: Формулировки Telegram, означающие «кнопка устарела».
STALE_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
)


def is_stale_callback(exc: TelegramBadRequest) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in STALE_MARKERS)


class StaleCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramBadRequest as exc:
            if not is_stale_callback(exc):
                raise
            logger.info("Нажатие устарело, Telegram не принял ответ на кнопку: %s", exc)
            return None
