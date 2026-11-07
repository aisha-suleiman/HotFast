"""Доступ к корзине."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import CartItem, OptionGroup, Product

#: Опции нужны, чтобы показать в строке корзины «(острая, большая)». В асинхронной
#: сессии ленивая подгрузка невозможна, поэтому тянем их сразу.
_WITH_OPTIONS = selectinload(CartItem.product).selectinload(
    Product.option_groups
).selectinload(OptionGroup.options)


class CartRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def items(self, user_id: int) -> list[CartItem]:
        stmt = (
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .order_by(CartItem.id)
            .options(_WITH_OPTIONS)
        )
        return list(await self.session.scalars(stmt))

    async def get_item(self, item_id: int, user_id: int) -> CartItem | None:
        """Всегда с проверкой владельца: id позиции приходит из callback-данных."""
        stmt = (
            select(CartItem)
            .where(CartItem.id == item_id, CartItem.user_id == user_id)
            .options(_WITH_OPTIONS)
        )
        return await self.session.scalar(stmt)

    async def add(
        self,
        user_id: int,
        *,
        product_id: int,
        qty: int,
        option_ids: list[int],
        unit_price: int,
    ) -> CartItem:
        """Тот же товар с тем же набором опций не плодит строки, а увеличивает количество."""
        same = await self._find_same(user_id, product_id, option_ids)
        if same is not None:
            same.qty += qty
            await self.session.flush()
            return same

        item = CartItem(
            user_id=user_id,
            product_id=product_id,
            qty=qty,
            option_ids=sorted(option_ids),
            unit_price=unit_price,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def find(
        self, user_id: int, product_id: int, option_ids: list[int]
    ) -> CartItem | None:
        """Позиция корзины с ровно таким товаром и набором опций."""
        return await self._find_same(user_id, product_id, option_ids)

    async def _find_same(
        self, user_id: int, product_id: int, option_ids: list[int]
    ) -> CartItem | None:
        wanted = sorted(option_ids)
        stmt = select(CartItem).where(
            CartItem.user_id == user_id, CartItem.product_id == product_id
        )
        for item in await self.session.scalars(stmt):
            if sorted(item.option_ids or []) == wanted:
                return item
        return None

    async def change_qty(self, item: CartItem, delta: int) -> CartItem | None:
        """Возвращает позицию либо None, если количество упало до нуля и строка удалена."""
        item.qty += delta
        if item.qty <= 0:
            await self.session.delete(item)
            await self.session.flush()
            return None
        await self.session.flush()
        return item

    async def remove(self, item: CartItem) -> None:
        await self.session.delete(item)
        await self.session.flush()

    async def clear(self, user_id: int) -> None:
        await self.session.execute(delete(CartItem).where(CartItem.user_id == user_id))
        await self.session.flush()
