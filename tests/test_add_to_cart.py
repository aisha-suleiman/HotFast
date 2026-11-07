"""Добавление в корзину: что клиент видит после нажатия «В корзину».

Из жалобы заказчика: «набираешь количество, жмёшь в корзину — количество уменьшается».
Так и было: карточка перерисовывалась со счётчиком, сброшенным на единицу, и набранная
тройка превращалась в единицу. В корзину при этом ложилось верное количество, но человек
видел сбой, жал второй раз и добавлял лишнее.
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
from bot.handlers.catalog import product_actions
from bot.i18n import I18n
from bot.keyboards.callbacks import ProductCB
from bot.services import cart as cart_service
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

    async def answer_photo(self, photo, caption=None, reply_markup=None, **kwargs):
        self.text, self.markup = caption, reply_markup
        return self

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.text, self.markup = text, reply_markup
        return self

    async def edit_caption(self, caption=None, reply_markup=None, **kwargs):
        self.text, self.markup = caption, reply_markup
        return self

    async def delete(self) -> None:
        pass

    def buttons(self) -> list[str]:
        return [b.text for row in self.markup.inline_keyboard for b in row]

    def counter(self) -> str | None:
        """Число между ➖ и ➕, если счётчик вообще есть на экране."""
        for row in self.markup.inline_keyboard:
            texts = [b.text for b in row]
            if "➖" in texts and "➕" in texts:
                return texts[texts.index("➖") + 1]
        return None


@dataclass
class FakeCallback:
    message: FakeMessage = field(default_factory=FakeMessage)
    alerts: list[str] = field(default_factory=list)

    async def answer(self, text=None, show_alert=False, **kwargs):
        if text:
            self.alerts.append(text)


@dataclass
class FakeState:
    data: dict = field(default_factory=dict)

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, data=None, **kwargs):
        if data:
            self.data.update(data)
        self.data.update(kwargs)


@pytest_asyncio.fixture
async def shop():
    """Настоящее меню в памяти плюс всё, что нужно хендлеру каталога."""
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
        products, _ = await repos.menu.products_page(category.id, offset=0, limit=2)

        yield {
            "repos": repos,
            "user": await repos.users.get(USER_ID),
            "i18n": I18n(default_lang="ru").translator("ru"),
            "settings": settings,
            "rates": RateProvider(settings),
            "products": products,
            "callback": FakeCallback(),
            "state": FakeState(),
        }
    await engine.dispose()


async def tap(shop, action: str, product_id: int | None = None):
    await product_actions(
        shop["callback"],
        ProductCB(action=action, product_id=product_id or shop["products"][0].id, page=0),
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


def base_price(shop) -> int:
    """Цена блюда берётся из меню: тест не должен падать от смены прайса."""
    return shop["products"][0].price


# ── набор количества ──────────────────────────────────────────────────────────


async def test_counter_grows_with_each_tap(shop):
    assert (await tap(shop, "open")).counter() == "1"
    assert (await tap(shop, "inc")).counter() == "2"
    assert (await tap(shop, "inc")).counter() == "3"


async def test_nothing_lands_in_the_cart_until_add(shop):
    await tap(shop, "open")
    await tap(shop, "inc")
    assert (await cart_of(shop)).count == 0


async def test_counter_never_drops_below_one(shop):
    await tap(shop, "open")
    for _ in range(3):
        await tap(shop, "dec")
    assert (await tap(shop, "dec")).counter() == "1"


# ── экран после добавления ────────────────────────────────────────────────────


async def test_chosen_quantity_lands_in_the_cart(shop):
    await tap(shop, "open")
    await tap(shop, "inc")
    await tap(shop, "inc")
    await tap(shop, "add")

    view = await cart_of(shop)
    assert view.count == 3
    assert view.subtotal == base_price(shop) * 3


async def test_confirmation_shows_the_quantity_that_was_added(shop):
    """Ровно та жалоба: «3» не должно превращаться в «1»."""
    await tap(shop, "open")
    await tap(shop, "inc")
    await tap(shop, "inc")
    message = await tap(shop, "add")

    assert "× 3" in message.text
    assert message.counter() is None, "счётчика на экране подтверждения быть не должно"


async def test_confirmation_offers_cart_and_more_shopping(shop):
    await tap(shop, "open")
    message = await tap(shop, "add")

    labels = message.buttons()
    assert any("Корзина" in label for label in labels)
    assert any("Выбрать ещё" in label for label in labels)


async def test_cart_total_is_shown_on_the_button(shop):
    await tap(shop, "open")
    await tap(shop, "inc")
    message = await tap(shop, "add")

    expected = str(base_price(shop) * 2 // 100)
    assert any(expected in label for label in message.buttons())


# ── повторное добавление ──────────────────────────────────────────────────────


async def test_second_product_adds_up_rather_than_replaces(shop):
    await tap(shop, "open")
    await tap(shop, "add")

    second = shop["products"][1]
    await tap(shop, "open", second.id)
    await tap(shop, "inc", second.id)
    await tap(shop, "add", second.id)

    view = await cart_of(shop)
    assert view.count == 3
    assert len(view.items) == 2, "разные блюда — разные позиции"


async def test_repeat_of_the_same_dish_merges_into_one_line(shop):
    await tap(shop, "open")
    await tap(shop, "add")
    await tap(shop, "open")
    await tap(shop, "add")

    view = await cart_of(shop)
    assert view.count == 2
    assert len(view.items) == 1, "одно и то же блюдо не должно плодить строки"


async def test_quantity_starts_from_one_again_for_the_next_dish(shop):
    """После добавления набор начинается заново — но уже на новом экране, без обмана."""
    await tap(shop, "open")
    await tap(shop, "inc")
    await tap(shop, "add")

    assert (await tap(shop, "open")).counter() == "1"
