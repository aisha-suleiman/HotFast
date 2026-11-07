"""Меню одним экраном: все блюда и варианты сразу, со счётчиками.

Просьба заказчика: «чтобы можно было выбирать и шаурму, и донер с одной страницы».
Раньше путь был «список -> карточка -> подтверждение -> назад», и ради второго блюда
приходилось возвращаться. Теперь каждая покупаемая позиция — своя строка с ➖ и ➕.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest_asyncio
import yaml

from bot.db.base import Base
from bot.db.enums import Lang
from bot.db.models import User
from bot.db.repo import Repos
from bot.db.session import make_engine, make_sessionmaker
from bot.handlers.catalog import _menu_screen, product_actions
from bot.i18n import I18n
from bot.keyboards.callbacks import ProductCB
from bot.services import cart as cart_service
from bot.services import menu as menu_service
from bot.services.rates import RateProvider
from scripts.seed_menu import SEED_FILE, seed
from tests.test_order_flow import make_settings

USER_ID = 777
MENU = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))


@dataclass
class FakeMessage:
    photo: Any = None
    text: str = ""
    markup: Any = None

    async def answer(self, text, reply_markup=None, **kwargs):
        self.text, self.markup = text, reply_markup
        return self

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.text, self.markup = text, reply_markup
        return self

    async def delete(self) -> None:
        pass


@dataclass
class FakeCallback:
    message: FakeMessage = field(default_factory=FakeMessage)

    async def answer(self, *args, **kwargs) -> None:
        pass


@dataclass
class FakeState:
    data: dict = field(default_factory=dict)

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, data=None, **kwargs):
        if data:
            self.data.update(data)
        self.data.update(kwargs)


def labels(markup) -> list[str]:
    return [b.text for row in markup.inline_keyboard for b in row]


@pytest_asyncio.fixture
async def shop():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with make_sessionmaker(engine)() as session:
        await seed(session, MENU)
        session.add(User(tg_id=USER_ID, lang=Lang.RU, username="client"))
        await session.flush()

        repos = Repos.build(session)
        settings = make_settings()
        category = (await repos.menu.categories())[0]
        products, _ = await repos.menu.products_page(category.id, offset=0, limit=5)
        detailed = [await repos.menu.get_product(p.id) for p in products]

        yield {
            "repos": repos,
            "user": await repos.users.get(USER_ID),
            "i18n": I18n(default_lang="ru").translator("ru"),
            "settings": settings,
            "rates": RateProvider(settings),
            "category_id": category.id,
            "products": detailed,
            "callback": FakeCallback(),
            "state": FakeState(),
        }
    await engine.dispose()


async def screen(shop):
    return await _menu_screen(
        shop["repos"],
        shop["i18n"],
        shop["user"],
        shop["settings"],
        shop["rates"],
        shop["category_id"],
    )


async def tap(shop, product, option_index: int, action: str = "qinc"):
    option = product.option_groups[0].options[option_index]
    await product_actions(
        shop["callback"],
        ProductCB(action=action, product_id=product.id, opt_id=option.id),
        shop["state"],
        shop["repos"],
        shop["i18n"],
        shop["user"],
        shop["settings"],
        shop["rates"],
    )
    return shop["callback"].message


async def cart_of(shop):
    return await cart_service.load_cart(shop["repos"], USER_ID)


def prices(shop) -> tuple[int, int]:
    """Цены обычной порции и дубля — из меню, а не числами в тесте."""
    product = shop["products"][0]
    regular, double = product.option_groups[0].options
    return product.price + regular.price_delta, product.price + double.price_delta


# ── состав экрана ─────────────────────────────────────────────────────────────


async def test_both_dishes_are_on_one_screen(shop):
    _, markup = await screen(shop)
    joined = " ".join(labels(markup))

    assert "Шаурма" in joined
    assert "Донер" in joined


async def test_every_portion_is_its_own_row(shop):
    """Обычная и дубль — разные покупки, значит разные строки."""
    _, markup = await screen(shop)
    joined = " ".join(labels(markup))

    assert joined.count("Обычная") == 2
    assert joined.count("Дубль") == 2


async def test_descriptions_are_shown_above_the_buttons(shop):
    """Карточки блюда больше нет — состав должен остаться на виду."""
    text, _ = await screen(shop)

    assert "Курица на гриле" in text
    assert "Мясо донер" in text


async def test_empty_cart_hides_cart_buttons(shop):
    _, markup = await screen(shop)
    joined = " ".join(labels(markup))

    assert "Корзина" not in joined
    assert "Оформить" not in joined


# ── счётчики прямо на экране ──────────────────────────────────────────────────


async def test_tap_adds_one_and_shows_the_count(shop):
    message = await tap(shop, shop["products"][0], 0)

    assert any("×1" in label for label in labels(message.markup))
    assert (await cart_of(shop)).count == 1


async def test_plus_and_minus_appear_only_after_first_tap(shop):
    _, markup = await screen(shop)
    assert "➖" not in labels(markup), "пока ничего не выбрано, кнопки не нужны"

    message = await tap(shop, shop["products"][0], 0)
    assert "➖" in labels(message.markup)


async def test_minus_removes_the_row_at_zero(shop):
    product = shop["products"][0]
    await tap(shop, product, 0)
    message = await tap(shop, product, 0, action="qdec")

    assert "×" not in " ".join(labels(message.markup))
    assert (await cart_of(shop)).count == 0


async def test_minus_on_empty_position_does_nothing(shop):
    await tap(shop, shop["products"][0], 0, action="qdec")

    assert (await cart_of(shop)).count == 0


# ── главное: оба блюда без ухода с экрана ─────────────────────────────────────


async def test_shawarma_and_doner_collected_without_leaving_the_screen(shop):
    shawarma, doner = shop["products"][0], shop["products"][1]

    await tap(shop, shawarma, 0)
    await tap(shop, shawarma, 0)
    await tap(shop, shawarma, 1)  # дубль
    message = await tap(shop, doner, 0)

    view = await cart_of(shop)
    regular, double = prices(shop)
    assert view.count == 4
    assert len(view.items) == 3, "обычная, дубль и донер — три разные позиции"
    assert view.subtotal == regular * 3 + double

    joined = " ".join(labels(message.markup))
    assert "Корзина" in joined and "Оформить" in joined


async def test_cart_total_on_the_button_follows_the_taps(shop):
    await tap(shop, shop["products"][0], 0)
    message = await tap(shop, shop["products"][1], 0)

    expected = str(prices(shop)[0] * 2 // 100)
    assert any(expected in label for label in labels(message.markup))


# ── разворачивание меню в варианты ────────────────────────────────────────────


def test_dish_without_options_is_a_single_row():
    from bot.db.models import Product

    product = Product(id=1, name_ru="Кола", name_ar="كولا", price=3000)
    product.option_groups = []

    variants = menu_service.expand(product)

    assert len(variants) == 1
    assert variants[0].option is None
    assert variants[0].price == 3000


def test_complex_options_fall_back_to_the_card():
    """Добавки перебирать кнопками бессмысленно — такой товар открывает карточку."""
    from bot.db.models import Option, OptionGroup, Product

    product = Product(id=1, name_ru="Шаурма", name_ar="شاورما", price=10000)
    extras = OptionGroup(name_ru="Добавки", name_ar="إضافات", min_select=0, max_select=3)
    extras.options = [
        Option(id=1, name_ru="Сыр", name_ar="جبنة", price_delta=2500, is_active=True)
    ]
    product.option_groups = [extras]

    variants = menu_service.expand(product)

    assert len(variants) == 1
    assert variants[0].needs_card is True


def test_variant_price_includes_the_option():
    from bot.db.models import Option, OptionGroup, Product

    product = Product(id=1, name_ru="Шаурма", name_ar="شاورما", price=10000)
    group = OptionGroup(name_ru="Порция", name_ar="الحجم", min_select=1, max_select=1)
    group.options = [
        Option(id=1, name_ru="Обычная", name_ar="عادي", price_delta=0, is_active=True),
        Option(id=2, name_ru="Дубль", name_ar="دوبل", price_delta=2500, is_active=True),
    ]
    product.option_groups = [group]

    regular, double = menu_service.expand(product)

    assert (regular.price, double.price) == (10000, 12500)
    assert double.name("ru") == "Шаурма · Дубль"
