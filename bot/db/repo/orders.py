"""Доступ к заказам."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.enums import ACTIVE_STATUSES, OrderStatus
from bot.db.models import Order, OrderItem, OrderStatusLog


class OrderRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, order_id: int) -> Order | None:
        return await self.session.get(Order, order_id)

    async def next_public_no(self, tz: ZoneInfo) -> str:
        """Номер вида 0907-014: день-месяц и порядковый номер заказа за эти сутки."""
        now_local = datetime.now(tz)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await self.session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.created_at >= day_start.astimezone(UTC))
        )
        return f"{now_local:%d%m}-{int(today_count or 0) + 1:03d}"

    async def add(self, order: Order, items: list[OrderItem]) -> Order:
        order.items = items
        self.session.add(order)
        await self.session.flush()
        self.session.add(
            OrderStatusLog(order_id=order.id, from_status=None, to_status=order.status)
        )
        await self.session.flush()
        return order

    async def log_transition(
        self,
        order: Order,
        *,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_tg_id: int | None,
        actor_name: str | None,
    ) -> None:
        self.session.add(
            OrderStatusLog(
                order_id=order.id,
                from_status=from_status,
                to_status=to_status,
                actor_tg_id=actor_tg_id,
                actor_name=actor_name,
            )
        )
        await self.session.flush()

    async def user_orders(self, user_id: int, *, limit: int = 10) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(await self.session.scalars(stmt))

    async def active_for_user(self, user_id: int) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id, Order.status.in_(list(ACTIVE_STATUSES)))
            .order_by(Order.created_at.desc())
        )
        return list(await self.session.scalars(stmt))

    async def awaiting_payment_for_user(self, user_id: int) -> Order | None:
        """Последний заказ клиента, по которому мы ждём подтверждение оплаты.

        Отклонённая оплата тоже сюда попадает: клиент может прислать правильный чек.
        """
        stmt = (
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.status.in_([OrderStatus.AWAITING_PAYMENT, OrderStatus.PAYMENT_REJECTED]),
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def stale_unpaid(self, *, timeout_min: int) -> list[Order]:
        """Заказы, по которым клиент так и не прислал подтверждение оплаты."""
        deadline = datetime.now(UTC) - timedelta(minutes=timeout_min)
        stmt = select(Order).where(
            Order.status == OrderStatus.AWAITING_PAYMENT,
            Order.created_at < deadline,
        )
        return list(await self.session.scalars(stmt))
