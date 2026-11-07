"""Одна сессия БД на апдейт, с коммитом в конце и откатом при исключении."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.repo import Repos


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            data["repos"] = Repos.build(session)
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            # Хендлеры только flush-ат; единый коммит здесь означает, что упавший
            # апдейт не оставит заказ наполовину созданным.
            await session.commit()
            return result
