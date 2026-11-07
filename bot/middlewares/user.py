"""Пользователь и его язык в каждом хендлере."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser

from bot.db.enums import Lang
from bot.db.repo import Repos
from bot.i18n import I18n


class UserMiddleware(BaseMiddleware):
    """Кладёт в data ``user`` (модель) и ``i18n`` (переводчик на языке пользователя).

    В групповых чатах записи пользователя нет и она не нужна: карточка кухни рисуется
    на языке заведения, поэтому туда уходит переводчик с языком по умолчанию.
    """

    def __init__(self, i18n: I18n, default_lang: str, admin_group_id: int) -> None:
        self.i18n = i18n
        self.default_lang = default_lang
        self.admin_group_id = admin_group_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        chat = data.get("event_chat")
        is_kitchen = chat is not None and chat.id == self.admin_group_id

        if tg_user is None or tg_user.is_bot or is_kitchen:
            data["user"] = None
            data["i18n"] = self.i18n.translator(self.default_lang)
            return await handler(event, data)

        repos: Repos = data["repos"]
        user, created = await repos.users.get_or_create(
            tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            default_lang=Lang(self.default_lang),
        )
        data["user"] = user
        data["is_new_user"] = created
        data["i18n"] = self.i18n.translator(user.lang.value)
        return await handler(event, data)
