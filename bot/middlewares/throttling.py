"""Антифлуд на inline-кнопки.

Двойной тап по «➕» — обычное дело на медленной сети: пользователь не видит реакции и
жмёт ещё раз. Без ограничителя это молча удваивает количество в корзине.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

#: Минимальный интервал между нажатиями одного пользователя, секунды.
DEFAULT_RATE = 0.4
#: Сколько пользователей помним. Ограничение нужно, чтобы словарь не рос бесконечно.
MAX_TRACKED = 10_000


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = DEFAULT_RATE) -> None:
        self.rate = rate
        self._last: OrderedDict[int, float] = OrderedDict()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        now = time.monotonic()
        user_id = event.from_user.id
        previous = self._last.get(user_id)

        if previous is not None and now - previous < self.rate:
            # Отвечаем на callback, иначе у клиента останется «часики» на кнопке.
            await event.answer()
            return None

        self._last[user_id] = now
        self._last.move_to_end(user_id)
        while len(self._last) > MAX_TRACKED:
            self._last.popitem(last=False)

        return await handler(event, data)
