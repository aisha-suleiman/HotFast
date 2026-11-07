"""Заливка меню из seed/menu.yaml в базу.

Запуск::

    py -m scripts.seed_menu              # обновить меню
    py -m scripts.seed_menu --create     # создать таблицы и залить (быстрый старт без Alembic)

Скрипт синхронизирует базу с файлом, а не просто дополняет её. Сущности сопоставляются по
``slug`` (филиалы, категории, товары) и по порядковому номеру внутри товара (группы опций и
сами опции). Повторный запуск обновляет названия и цены, не ломая ссылки из уже оформленных
заказов.

Чего в файле нет:

* товары и категории **снимаются с продажи** (``is_active = false``), но не удаляются —
  на них ссылается история заказов, и удаление стёрло бы её;
* лишние группы опций и опции **удаляются** — на них история не ссылается (в позицию заказа
  их названия записаны снимком), а оставлять в карточке товара варианты, которых больше нет
  в меню, нельзя.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.base import Base
from bot.db.models import Branch, Category, Option, OptionGroup, Product
from bot.db.session import make_engine, make_sessionmaker

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "menu.yaml"


async def seed(session: AsyncSession, data: dict) -> Report:
    report = Report()
    for raw in data.get("branches", []):
        await _upsert_branch(session, raw)

    categories = data.get("categories", [])
    for raw in categories:
        await _upsert_category(session, raw, report)

    await _retire_missing(session, categories, report)
    await session.commit()
    return report


@dataclass
class Report:
    """Что скрипт сделал — печатается в конце, чтобы правка меню была видна глазами."""

    products: int = 0
    retired_products: list[str] = field(default_factory=list)
    retired_categories: list[str] = field(default_factory=list)
    removed_groups: int = 0

    def lines(self) -> list[str]:
        rows = [f"Товаров в меню: {self.products}"]
        if self.retired_products:
            rows.append("Сняты с продажи: " + ", ".join(self.retired_products))
        if self.retired_categories:
            rows.append("Скрыты категории: " + ", ".join(self.retired_categories))
        if self.removed_groups:
            rows.append(f"Удалено лишних групп опций: {self.removed_groups}")
        return rows


async def _retire_missing(session: AsyncSession, categories: list[dict], report: Report) -> None:
    """Убирает из продажи всё, чего больше нет в файле."""
    kept_categories = {raw["slug"] for raw in categories}
    kept_products = {
        product["slug"] for raw in categories for product in raw.get("products", [])
    }

    for product in await session.scalars(select(Product).where(Product.is_active.is_(True))):
        if product.slug not in kept_products:
            product.is_active = False
            report.retired_products.append(product.slug)

    for category in await session.scalars(select(Category).where(Category.is_active.is_(True))):
        if category.slug not in kept_categories:
            category.is_active = False
            report.retired_categories.append(category.slug)

    await session.flush()


async def _upsert_branch(session: AsyncSession, raw: dict) -> None:
    branch = await session.scalar(select(Branch).where(Branch.slug == raw["slug"]))
    if branch is None:
        branch = Branch(slug=raw["slug"])
        session.add(branch)
    for attr in ("name_ar", "name_ru", "address_ar", "address_ru", "phone", "lat", "lon"):
        if attr in raw:
            setattr(branch, attr, raw[attr])
    branch.sort = raw.get("sort", 0)
    branch.is_active = raw.get("is_active", True)
    await session.flush()


async def _upsert_category(session: AsyncSession, raw: dict, report: Report) -> None:
    category = await session.scalar(select(Category).where(Category.slug == raw["slug"]))
    if category is None:
        category = Category(slug=raw["slug"])
        session.add(category)
    category.name_ar = raw["name_ar"]
    category.name_ru = raw["name_ru"]
    category.emoji = raw.get("emoji")
    category.sort = raw.get("sort", 0)
    category.is_active = raw.get("is_active", True)
    await session.flush()

    for raw_product in raw.get("products", []):
        await _upsert_product(session, category, raw_product, report)
        report.products += 1


async def _upsert_product(
    session: AsyncSession, category: Category, raw: dict, report: Report
) -> None:
    product = await session.scalar(select(Product).where(Product.slug == raw["slug"]))
    if product is None:
        product = Product(slug=raw["slug"])
        session.add(product)
    product.category_id = category.id
    product.name_ar = raw["name_ar"]
    product.name_ru = raw["name_ru"]
    product.desc_ar = raw.get("desc_ar")
    product.desc_ru = raw.get("desc_ru")
    product.price = raw["price"]
    product.sort = raw.get("sort", 0)
    product.is_active = raw.get("is_active", True)
    await session.flush()

    groups = raw.get("option_groups", [])
    for raw_group in groups:
        await _upsert_group(session, product, raw_group)
    report.removed_groups += await _remove_extra_groups(session, product, groups)


async def _upsert_group(session: AsyncSession, product: Product, raw: dict) -> None:
    sort = raw.get("sort", 0)
    group = await session.scalar(
        select(OptionGroup).where(
            OptionGroup.product_id == product.id, OptionGroup.sort == sort
        )
    )
    if group is None:
        group = OptionGroup(product_id=product.id, sort=sort)
        session.add(group)
    group.name_ar = raw["name_ar"]
    group.name_ru = raw["name_ru"]
    group.min_select = raw.get("min_select", 0)
    group.max_select = raw.get("max_select", 1)
    await session.flush()

    options = raw.get("options", [])
    for raw_option in options:
        await _upsert_option(session, group, raw_option)

    # Вариант, убранный из файла, не должен остаться кнопкой в карточке товара.
    kept = {raw_option.get("sort", 0) for raw_option in options}
    for stale in await session.scalars(
        select(Option).where(Option.group_id == group.id, Option.sort.notin_(kept or {-1}))
    ):
        await session.delete(stale)
    await session.flush()


async def _remove_extra_groups(
    session: AsyncSession, product: Product, groups: list[dict]
) -> int:
    """Удаляет группы опций, которых больше нет в файле, вместе с их вариантами."""
    kept = {raw.get("sort", 0) for raw in groups}
    stale = await session.scalars(
        select(OptionGroup).where(
            OptionGroup.product_id == product.id, OptionGroup.sort.notin_(kept or {-1})
        )
    )
    removed = 0
    for group in stale:
        await session.delete(group)
        removed += 1
    await session.flush()
    return removed


async def _upsert_option(session: AsyncSession, group: OptionGroup, raw: dict) -> None:
    sort = raw.get("sort", 0)
    option = await session.scalar(
        select(Option).where(Option.group_id == group.id, Option.sort == sort)
    )
    if option is None:
        option = Option(group_id=group.id, sort=sort)
        session.add(option)
    option.name_ar = raw["name_ar"]
    option.name_ru = raw["name_ru"]
    option.price_delta = raw.get("price_delta", 0)
    option.is_active = raw.get("is_active", True)
    await session.flush()


async def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.db_url)

    if "--create" in sys.argv:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Таблицы созданы.")

    data = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))
    sessionmaker = make_sessionmaker(engine)
    async with sessionmaker() as session:
        report = await seed(session, data)

    await engine.dispose()
    print(f"Меню синхронизировано с {SEED_FILE.name}.")
    for line in report.lines():
        print(" ", line)


if __name__ == "__main__":
    asyncio.run(main())
