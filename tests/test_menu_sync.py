"""Синхронизация меню из seed/menu.yaml и поведение карточки с одной группой опций.

Меню — единственное, что заказчик правит сам, поэтому проверяем не только «залилось», но и
«убралось»: снятое с продажи блюдо не должно всплыть в каталоге после правки файла.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.base import Base
from bot.db.models import Option, OptionGroup, Product
from bot.db.repo import Repos
from bot.db.session import make_engine, make_sessionmaker
from bot.i18n import I18n
from bot.keyboards.client import products_kb
from bot.services import cart as cart_service
from scripts.seed_menu import SEED_FILE, seed

MENU = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def session():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with make_sessionmaker(engine)() as s:
        yield s
    await engine.dispose()


# ── содержимое меню ───────────────────────────────────────────────────────────


def test_menu_file_has_exactly_two_products():
    products = [p for c in MENU["categories"] for p in c.get("products", [])]
    assert [p["slug"] for p in products] == ["shawarma", "doner"]


def test_every_product_offers_the_double_portion():
    for category in MENU["categories"]:
        for product in category["products"]:
            groups = product["option_groups"]
            assert len(groups) == 1, "порция — единственная группа опций"
            names = [o["name_ru"] for o in groups[0]["options"]]
            assert names == ["Обычная", "Дубль"]


def test_portion_is_a_single_required_choice():
    group = MENU["categories"][0]["products"][0]["option_groups"][0]
    assert (group["min_select"], group["max_select"]) == (1, 1)


def test_double_portion_costs_more():
    options = MENU["categories"][0]["products"][0]["option_groups"][0]["options"]
    regular, double = options
    assert regular["price_delta"] == 0
    assert double["price_delta"] > 0


# ── заливка ───────────────────────────────────────────────────────────────────


async def test_seed_creates_the_menu(session: AsyncSession):
    report = await seed(session, MENU)
    repos = Repos.build(session)

    assert report.products == 2
    categories = await repos.menu.categories()
    assert len(categories) == 1

    products, total = await repos.menu.products_page(categories[0].id, offset=0, limit=10)
    assert total == 2
    assert {p.slug for p in products} == {"shawarma", "doner"}


async def test_seed_is_idempotent(session: AsyncSession):
    await seed(session, MENU)
    await seed(session, MENU)

    assert await session.scalar(select(Product).where(Product.slug == "shawarma")) is not None
    assert len(list(await session.scalars(select(Product)))) == 2
    assert len(list(await session.scalars(select(Option)))) == 4


async def test_dropped_products_leave_the_menu(session: AsyncSession):
    """Блюдо, удалённое из файла, перестаёт продаваться, но остаётся ради истории."""
    await seed(session, MENU)

    shrunk = {
        "categories": [
            {**MENU["categories"][0], "products": MENU["categories"][0]["products"][:1]}
        ]
    }
    report = await seed(session, shrunk)

    assert report.retired_products == ["doner"]
    doner = await session.scalar(select(Product).where(Product.slug == "doner"))
    assert doner is not None, "удалять нельзя: на товар ссылается история заказов"
    assert doner.is_active is False

    _, total = await Repos.build(session).menu.products_page(
        (await Repos.build(session).menu.categories())[0].id, offset=0, limit=10
    )
    assert total == 1


async def test_dropped_category_is_hidden(session: AsyncSession):
    await seed(session, MENU)
    await seed(session, {"categories": []})

    assert await Repos.build(session).menu.categories() == []


async def test_removed_option_group_disappears(session: AsyncSession):
    """У товара была ещё группа «Соус» — после правки файла её кнопок быть не должно."""
    with_sauce = {
        "categories": [
            {
                **MENU["categories"][0],
                "products": [
                    {
                        **MENU["categories"][0]["products"][0],
                        "option_groups": [
                            *MENU["categories"][0]["products"][0]["option_groups"],
                            {
                                "name_ar": "الصلصة",
                                "name_ru": "Соус",
                                "min_select": 0,
                                "max_select": 1,
                                "sort": 2,
                                "options": [
                                    {"name_ar": "ثوم", "name_ru": "Чеснок", "sort": 1},
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }
    await seed(session, with_sauce)
    assert len(list(await session.scalars(select(OptionGroup)))) == 2

    report = await seed(session, MENU)

    assert report.removed_groups == 1
    groups = list(await session.scalars(select(OptionGroup)))
    assert [g.name_ru for g in groups] == ["Порция", "Порция"]
    assert not [o for o in await session.scalars(select(Option)) if o.name_ru == "Чеснок"]


async def test_retired_product_returns_when_put_back(session: AsyncSession):
    await seed(session, MENU)
    await seed(session, {"categories": []})
    await seed(session, MENU)

    products = await Repos.build(session).menu.categories()
    assert len(products) == 1
    _, total = await Repos.build(session).menu.products_page(
        products[0].id, offset=0, limit=10
    )
    assert total == 2


# ── карточка товара ───────────────────────────────────────────────────────────


async def test_regular_portion_is_preselected(session: AsyncSession):
    """Обязательная группа предвыбрана: клиент может сразу нажать «В корзину»."""
    await seed(session, MENU)
    repos = Repos.build(session)
    product = await repos.menu.get_product(
        (await repos.menu.products_page(
            (await repos.menu.categories())[0].id, offset=0, limit=1
        ))[0][0].id
    )

    selected = cart_service.default_selection(product)

    assert len(selected) == 1
    assert cart_service.validate_selection(product, selected) is None
    chosen = cart_service.options_of(product, selected)[0]
    assert chosen.name_ru == "Обычная"


async def test_double_replaces_regular_rather_than_adding(session: AsyncSession):
    """max_select=1: нажатие на дубль снимает обычную, а не копит обе."""
    await seed(session, MENU)
    repos = Repos.build(session)
    product = await repos.menu.get_product(
        (await repos.menu.products_page(
            (await repos.menu.categories())[0].id, offset=0, limit=1
        ))[0][0].id
    )
    regular, double = product.option_groups[0].options

    selected = cart_service.toggle_option(product, {regular.id}, double.id)

    assert selected == {double.id}
    assert cart_service.price_with_options(
        product, cart_service.options_of(product, selected)
    ) == product.price + double.price_delta


async def test_required_choice_cannot_be_emptied(session: AsyncSession):
    """Повторное нажатие не должно оставить товар вообще без порции."""
    await seed(session, MENU)
    repos = Repos.build(session)
    product = await repos.menu.get_product(
        (await repos.menu.products_page(
            (await repos.menu.categories())[0].id, offset=0, limit=1
        ))[0][0].id
    )
    regular = product.option_groups[0].options[0]

    assert cart_service.toggle_option(product, {regular.id}, regular.id) == {regular.id}


# ── навигация ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("show_back", [True, False])
def test_back_button_only_when_there_are_other_categories(show_back: bool):
    i18n = I18n(default_lang="ru").translator("ru")
    markup = products_kb(
        [],
        category_id=1,
        page=0,
        total=0,
        lang="ru",
        i18n=i18n,
        price_of=lambda v: "0",
        show_back=show_back,
    )
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert (i18n("btn-back") in labels) is show_back
