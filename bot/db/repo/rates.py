"""Хранение последнего известного курса."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ExchangeRate
from bot.services.rates import Rate


class RateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, base: str, quote: str) -> Rate | None:
        stmt = select(ExchangeRate).where(
            ExchangeRate.base == base, ExchangeRate.quote == quote
        )
        row = await self.session.scalar(stmt)
        if row is None:
            return None
        return Rate(base=row.base, quote=row.quote, micro=row.micro, fetched_at=row.fetched_at)

    async def save(self, rate: Rate) -> None:
        """Одна строка на пару валют — история курсов заведению не нужна."""
        stmt = select(ExchangeRate).where(
            ExchangeRate.base == rate.base, ExchangeRate.quote == rate.quote
        )
        row = await self.session.scalar(stmt)
        if row is None:
            row = ExchangeRate(base=rate.base, quote=rate.quote)
            self.session.add(row)
        row.micro = rate.micro
        row.fetched_at = rate.fetched_at
        await self.session.flush()
