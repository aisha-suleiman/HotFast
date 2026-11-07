"""Репозитории. В хендлеры приходит один объект ``Repos`` — меньше аргументов и один
источник сессии на весь апдейт."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repo.cart import CartRepo
from bot.db.repo.menu import MenuRepo
from bot.db.repo.orders import OrderRepo
from bot.db.repo.rates import RateRepo
from bot.db.repo.users import UserRepo

__all__ = ["CartRepo", "MenuRepo", "OrderRepo", "RateRepo", "Repos", "UserRepo"]


@dataclass(slots=True)
class Repos:
    session: AsyncSession
    users: UserRepo
    menu: MenuRepo
    cart: CartRepo
    orders: OrderRepo
    rates: RateRepo

    @classmethod
    def build(cls, session: AsyncSession) -> Repos:
        return cls(
            session=session,
            users=UserRepo(session),
            menu=MenuRepo(session),
            cart=CartRepo(session),
            orders=OrderRepo(session),
            rates=RateRepo(session),
        )
