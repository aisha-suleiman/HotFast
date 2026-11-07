"""Сборка приложения: диспетчер, роутеры, фильтры и клавиатуры.

Ошибки в проводке (опечатка в имени роутера, несуществующий ключ локали в кнопке,
callback_data длиннее лимита Telegram) не видны ни линтеру, ни юнит-тестам сервисов —
здесь они всплывают до запуска бота.
"""

from __future__ import annotations

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.__main__ import build_dispatcher
from bot.handlers.common import MenuText, build_menu_index
from bot.i18n import SUPPORTED, I18n
from bot.keyboards.callbacks import (
    CartCB,
    CatalogCB,
    CheckoutCB,
    KitchenCB,
    LangCB,
    NavCB,
    OrderCB,
    ProductCB,
)
from bot.keyboards.client import language_kb, main_menu_kb
from tests.test_order_flow import make_settings

#: Telegram обрезает callback_data длиннее 64 байт — упавшая кнопка молчит.
CALLBACK_LIMIT = 64


@pytest.fixture(scope="module")
def dispatcher():
    """Роутеры — модульные синглтоны, привязать их можно только к одному диспетчеру,
    поэтому собираем его один раз на весь модуль."""
    bot = Bot(
        "123456:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    settings = make_settings()
    return build_dispatcher(bot, settings, I18n(default_lang=settings.default_lang))


def test_dispatcher_builds_with_all_routers(dispatcher):
    names = {router.name for router in dispatcher.sub_routers}
    assert names == {
        "errors",
        "kitchen",
        "admin",
        "start",
        "catalog",
        "cart",
        "checkout",
        "profile",
        "payment",
    }


def test_payment_router_is_last(dispatcher):
    """Приём чека ловит свободный текст — он обязан стоять после всех остальных."""
    assert dispatcher.sub_routers[-1].name == "payment"


def test_workflow_data_has_everything_handlers_ask_for(dispatcher):
    for key in ("settings", "i18n_hub", "notifier", "sessionmaker", "engine"):
        assert key in dispatcher.workflow_data


# ── фильтры нижней клавиатуры ─────────────────────────────────────────────────


@pytest.mark.parametrize("lang", SUPPORTED)
async def test_menu_buttons_recognised_in_both_languages(lang: str):
    """Клавиатура на старом языке может висеть у клиента после переключения."""
    i18n = I18n(default_lang="ar")
    build_menu_index(i18n)

    class FakeMessage:
        def __init__(self, text: str) -> None:
            self.text = text

    for key in ("menu-catalog", "menu-cart", "menu-orders", "btn-cancel"):
        message = FakeMessage(i18n.get(lang, key))
        assert await MenuText(key)(message) is True
        assert await MenuText("menu-contacts")(message) is (key == "menu-contacts")


async def test_unrelated_text_does_not_match_menu():
    i18n = I18n(default_lang="ar")
    build_menu_index(i18n)

    class FakeMessage:
        text = "просто сообщение"

    assert await MenuText("menu-cart")(FakeMessage()) is False


# ── callback_data ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "packed",
    [
        LangCB(lang="ar").pack(),
        NavCB(to="noop").pack(),
        CatalogCB(action="open", category_id=999999, page=99).pack(),
        ProductCB(action="opt", product_id=999999, opt_id=999999, page=99).pack(),
        CartCB(action="inc", item_id=99999999).pack(),
        CheckoutCB(step="fulfillment", value="delivery").pack(),
        OrderCB(action="repeat", order_id=99999999).pack(),
        KitchenCB(order_id=99999999, to_status="payment_submitted").pack(),
    ],
)
def test_callback_data_fits_telegram_limit(packed: str):
    assert len(packed.encode()) <= CALLBACK_LIMIT, packed


def test_noop_callback_matches_the_handler_filter():
    """start.noop ловит строку напрямую — она должна совпадать с тем, что пакует NavCB."""
    assert NavCB(to="noop").pack() == "nv:noop"


# ── клавиатуры ────────────────────────────────────────────────────────────────


def test_language_keyboard_offers_both_languages():
    labels = [b.text for row in language_kb().inline_keyboard for b in row]
    assert any("العربية" in label for label in labels)
    assert any("Русский" in label for label in labels)


@pytest.mark.parametrize("lang", SUPPORTED)
def test_main_menu_renders_in_each_language(lang: str):
    i18n = I18n(default_lang="ar").translator(lang)
    labels = [b.text for row in main_menu_kb(i18n).keyboard for b in row]
    assert len(labels) == 5
    assert all(label and not label.startswith("menu-") for label in labels)
