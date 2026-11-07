"""Доступ к пользователям."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.enums import Lang
from bot.db.models import User


class UserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tg_id: int) -> User | None:
        return await self.session.get(User, tg_id)

    async def get_or_create(
        self,
        tg_id: int,
        *,
        username: str | None,
        full_name: str | None,
        default_lang: Lang,
    ) -> tuple[User, bool]:
        """Возвращает (пользователь, создан_ли_только_что)."""
        user = await self.session.get(User, tg_id)
        if user is not None:
            # Имя и username меняются на стороне Telegram — держим актуальными.
            if user.username != username or user.full_name != full_name:
                user.username, user.full_name = username, full_name
            return user, False

        user = User(tg_id=tg_id, username=username, full_name=full_name, lang=default_lang)
        self.session.add(user)
        await self.session.flush()
        return user, True

    async def set_lang(self, user: User, lang: Lang) -> None:
        user.lang = lang
        await self.session.flush()

    async def set_phone(self, user: User, phone: str) -> None:
        user.phone = phone
        await self.session.flush()

    async def count(self) -> int:
        return await self.session.scalar(select(func.count()).select_from(User)) or 0
