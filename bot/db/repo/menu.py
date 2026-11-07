"""Доступ к меню: категории, товары, опции, филиалы."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import Branch, Category, Option, OptionGroup, Product


class MenuRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def categories(self) -> list[Category]:
        stmt = (
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort, Category.id)
        )
        return list(await self.session.scalars(stmt))

    async def get_category(self, category_id: int) -> Category | None:
        return await self.session.get(Category, category_id)

    async def products_page(
        self, category_id: int, *, offset: int, limit: int
    ) -> tuple[list[Product], int]:
        """Страница товаров категории и общее число активных товаров в ней."""
        base = (Product.category_id == category_id, Product.is_active.is_(True))
        total = await self.session.scalar(
            select(func.count()).select_from(Product).where(*base)
        )
        stmt = (
            select(Product)
            .where(*base)
            .order_by(Product.sort, Product.id)
            .offset(offset)
            .limit(limit)
        )
        return list(await self.session.scalars(stmt)), int(total or 0)

    async def get_product(self, product_id: int) -> Product | None:
        """Товар вместе с группами опций — карточке нужны все они сразу."""
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.option_groups).selectinload(OptionGroup.options))
        )
        return await self.session.scalar(stmt)

    async def get_options(self, option_ids: list[int]) -> list[Option]:
        if not option_ids:
            return []
        stmt = (
            select(Option)
            .where(Option.id.in_(option_ids))
            .options(selectinload(Option.group))
            .order_by(Option.sort, Option.id)
        )
        return list(await self.session.scalars(stmt))

    async def branches(self) -> list[Branch]:
        stmt = (
            select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.sort, Branch.id)
        )
        return list(await self.session.scalars(stmt))

    async def get_branch(self, branch_id: int) -> Branch | None:
        return await self.session.get(Branch, branch_id)

    async def default_branch(self) -> Branch | None:
        """Филиал, от которого считается зона доставки, — первый активный."""
        branches = await self.branches()
        return branches[0] if branches else None
