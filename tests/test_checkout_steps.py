"""Шаги оформления: адрес, контакт и экран оплаты.

Проверка на живом коде хендлеров, а не на клавиатурах по отдельности: между «реквизиты
заполнены» и «клиент увидел кнопку» лежит цепочка из состояния FSM, подтверждения контакта
и передачи флага в клавиатуру — сломаться может любое звено.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from bot.config import DeliveryTier
from bot.db.enums import Lang
from bot.db.models import User
from bot.handlers.checkout import confirm_contact, got_location
from bot.i18n import I18n
from bot.states.checkout import Checkout
from tests.test_order_flow import make_settings


@dataclass
class FakeMessage:
    """Ловит всё, что хендлер отправляет клиенту."""

    text: str | None = None
    location: Any = None
    sent: list[tuple[str, Any]] = field(default_factory=list)
    deleted: bool = False

    async def answer(self, text: str, reply_markup: Any = None, **kwargs: Any):
        self.sent.append((text, reply_markup))
        return self

    async def delete(self) -> None:
        self.deleted = True

    def buttons(self) -> list[str]:
        labels: list[str] = []
        for _, markup in self.sent:
            for row in getattr(markup, "inline_keyboard", []):
                labels.extend(b.text for b in row)
        return labels


@dataclass
class FakeCallback:
    message: FakeMessage = field(default_factory=FakeMessage)
    answered: bool = False

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        self.answered = True


@dataclass
class FakeState:
    state: Any = None
    data: dict = field(default_factory=dict)

    async def set_state(self, state):
        self.state = state

    async def update_data(self, **kwargs):
        self.data.update(kwargs)


@dataclass
class FakeBranch:
    lat: float = 35.9317159
    lon: float = 36.636137
    id: int = 1


@dataclass
class FakeMenuRepo:
    branch: FakeBranch | None = field(default_factory=FakeBranch)

    async def default_branch(self):
        return self.branch


@dataclass
class FakeRepos:
    menu: FakeMenuRepo = field(default_factory=FakeMenuRepo)


@dataclass
class FakeLocation:
    latitude: float
    longitude: float


def translator(lang: str = "ru"):
    return I18n(default_lang="ar").translator(lang)


TIERS = [DeliveryTier(max_km=2, fee=1500), DeliveryTier(max_km=15, fee=9000)]


# ── адрес: только геолокация ──────────────────────────────────────────────────


async def send_location(lat: float, lon: float, username: str | None = "client"):
    message, state = FakeMessage(), FakeState()
    message.location = FakeLocation(lat, lon)
    user = User(tg_id=1, lang=Lang.RU, username=username)
    settings = make_settings(delivery_tiers=TIERS)
    await got_location(message, state, FakeRepos(), translator(), user, settings)
    return message, state


async def test_location_leads_straight_to_the_contact_step():
    """Адрес текстом не спрашиваем: в Сирии улиц и номеров домов часто просто нет."""
    _, state = await send_location(35.9350, 36.6400)

    assert state.state == Checkout.contact
    assert "address_text" not in state.data
    assert state.data["lat"] == 35.9350


async def test_location_saves_distance_and_fee():
    _, state = await send_location(35.9350, 36.6400)

    assert state.data["delivery_fee"] == 1500
    assert 0 < state.data["distance_km"] < 2


async def test_out_of_zone_stops_before_the_contact_step():
    message, state = await send_location(36.4, 37.1)  # заведомо далеко

    assert state.state is None
    assert "delivery_fee" not in state.data
    assert "не доезжаем" in message.sent[0][0]


# ── контакт вместо телефона ───────────────────────────────────────────────────


async def test_contact_button_shows_the_clients_username():
    """Клиент должен видеть, по какому аккаунту с ним свяжутся."""
    message, _ = await send_location(35.9350, 36.6400, username="BintApandi")

    assert "📨 Отправить @BintApandi" in message.buttons()


async def test_without_username_the_button_still_offers_telegram():
    message, _ = await send_location(35.9350, 36.6400, username=None)

    labels = message.buttons()
    assert "📨 Писать мне в Telegram" in labels
    assert not any("@" in label for label in labels)


async def test_phone_is_never_requested():
    """Ни на одном экране не должно остаться просьбы прислать номер."""
    message, _ = await send_location(35.9350, 36.6400)

    texts = " ".join(text for text, _ in message.sent).lower()
    assert "номер" not in texts
    assert "телефон" not in texts


async def run_confirm(username: str | None, lang: Lang = Lang.RU, **settings_overrides):
    callback, state = FakeCallback(), FakeState()
    user = User(tg_id=1, lang=lang, username=username)
    await confirm_contact(
        callback,
        state,
        translator(lang.value),
        user,
        make_settings(**settings_overrides),
    )
    return callback, state


async def test_confirming_contact_opens_the_payment_screen():
    callback, state = await run_confirm("BintApandi", shamcash_wallet="1111")

    assert state.state == Checkout.payment
    assert state.data["username"] == "BintApandi"
    assert "📱 ShamCash" in callback.message.buttons()
    assert callback.message.deleted, "экран контакта должен смениться, а не остаться висеть"


async def test_client_without_username_also_reaches_payment():
    callback, state = await run_confirm(None, shamcash_wallet="1111")

    assert state.state == Checkout.payment
    assert state.data["username"] is None
    assert "📱 ShamCash" in callback.message.buttons()


# ── экран оплаты ──────────────────────────────────────────────────────────────


async def test_shamcash_is_offered_when_wallet_is_configured():
    callback, _ = await run_confirm("client", shamcash_wallet="1111 2222 3333 4444")

    assert "📱 ShamCash" in callback.message.buttons()
    assert "💵 Наличными при получении" in callback.message.buttons()


async def test_shamcash_is_hidden_when_wallet_is_empty():
    """Пустой SHAMCASH_WALLET — единственная причина, по которой кнопки может не быть."""
    callback, _ = await run_confirm("client", shamcash_wallet="")

    assert "📱 ShamCash" not in callback.message.buttons()
    assert "💵 Наличными при получении" in callback.message.buttons()


async def test_arabic_client_sees_shamcash_too():
    callback, _ = await run_confirm("client", lang=Lang.AR, shamcash_wallet="1111")

    assert "📱 شام كاش" in callback.message.buttons()


# ── карточка кухни ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["ru", "ar"])
def test_kitchen_contact_lines_exist_in_both_locales(lang: str):
    hub = I18n(default_lang="ru")
    assert "t.me" in hub.get(lang, "kitchen-contact-username", username="x")
    assert hub.get(lang, "kitchen-no-phone")
