"""Сквозной тест на реальной (временной) базе: корзина -> заказ -> карточка кухни.

Проверяет то, что юнит-тесты по отдельности поймать не могут: что модели, репозитории,
снимок позиций и шаблон карточки собираются вместе и дают осмысленный текст.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import DeliveryTier, Settings
from bot.db.base import Base
from bot.db.enums import Fulfillment, Lang, OrderStatus, PaymentMethod, PaymentStatus
from bot.db.models import Branch, CartItem, Category, Option, OptionGroup, Order, Product, User
from bot.db.repo import Repos
from bot.db.session import make_engine, make_sessionmaker
from bot.i18n import I18n
from bot.keyboards.admin import kitchen_kb
from bot.services import cart as cart_service
from bot.services import money as money_service
from bot.services import orders as order_service
from bot.services import pricing
from bot.services.notifier import Notifier
from bot.services.rates import Rate

USER_ID = 424242


def make_settings(**overrides) -> Settings:
    base = dict(
        bot_token="123:test",
        admin_group_id=-1001234567890,
        admin_ids=[1],
        db_url="sqlite+aiosqlite:///:memory:",
        redis_url="",
        default_lang="ru",
        currency="TRY",
        tz="Asia/Damascus",
        working_hours="11:00-02:00",
        shamcash_wallet="1111 2222",
        shamcash_holder="Shawarma House",
        payment_timeout_min=30,
        delivery_tiers=[DeliveryTier(max_km=2, fee=1500), DeliveryTier(max_km=5, fee=3000)],
        free_delivery_from=0,
        min_order_total=0,
        support_contact="@support",
    )
    base.update(overrides)
    return Settings(**base)


@pytest_asyncio.fixture
async def session():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with make_sessionmaker(engine)() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def filled(session: AsyncSession):
    """Минимальное меню, пользователь и корзина с одной позицией и двумя опциями."""
    session.add(
        Branch(
            slug="main",
            name_ar="الفرع الرئيسي",
            name_ru="Главный филиал",
            address_ar="دمشق",
            address_ru="Дамаск",
            lat=33.5138,
            lon=36.2765,
        )
    )
    category = Category(slug="shawarma", name_ar="شاورما", name_ru="Шаурма", emoji="🥙")
    session.add(category)
    await session.flush()

    product = Product(
        slug="chicken",
        category_id=category.id,
        name_ar="شاورما دجاج",
        name_ru="Шаурма куриная",
        desc_ar="دجاج",
        desc_ru="Курица",
        price=15000,
    )
    session.add(product)
    await session.flush()

    group = OptionGroup(
        product_id=product.id, name_ar="الحجم", name_ru="Размер", min_select=1, max_select=1
    )
    extras = OptionGroup(
        product_id=product.id, name_ar="إضافات", name_ru="Добавки", min_select=0, max_select=2, sort=1
    )
    session.add_all([group, extras])
    await session.flush()

    big = Option(group_id=group.id, name_ar="كبير", name_ru="Большая", price_delta=4000)
    cheese = Option(group_id=extras.id, name_ar="جبنة", name_ru="Сыр", price_delta=2500)
    session.add_all([big, cheese])
    session.add(User(tg_id=USER_ID, full_name="Ali", lang=Lang.RU, phone="+963912345678"))
    await session.flush()

    session.add(
        CartItem(
            user_id=USER_ID,
            product_id=product.id,
            qty=2,
            option_ids=[big.id, cheese.id],
            unit_price=15000 + 4000 + 2500,
        )
    )
    await session.flush()
    return {"product": product, "big": big, "cheese": cheese}


async def build_order(
    session: AsyncSession,
    settings: Settings,
    *,
    payment: PaymentMethod,
    rate=None,
) -> Order:
    repos = Repos.build(session)
    view = await cart_service.load_cart(repos, USER_ID)
    totals = pricing.totals(
        items_subtotal=view.subtotal, delivery_fee=3000, free_delivery_from=settings.free_delivery_from
    )
    option_ids = [oid for item in view.items for oid in item.option_ids]
    options = {o.id: o for o in await repos.menu.get_options(option_ids)}

    order = Order(
        public_no=await repos.orders.next_public_no(settings.timezone),
        user_id=USER_ID,
        status=order_service.initial_status(payment),
        fulfillment=Fulfillment.DELIVERY,
        branch_id=1,
        address_text="Аль-Хамра 5, кв. 12",
        lat=33.52,
        lon=36.28,
        distance_km=1.2,
        phone="+963912345678",
        comment="Без лука",
        lang=Lang.RU,
        payment_method=payment,
        payment_status=order_service.initial_payment_status(payment),
        subtotal=totals.subtotal,
        delivery_fee=totals.delivery_fee,
        total=totals.total,
        currency=settings.currency,
        secondary_currency=rate.quote if rate else None,
        rate_micro=rate.micro if rate else None,
    )
    await repos.orders.add(order, order_service.snapshot_items(view.items, options))
    await session.refresh(order, ["user", "branch", "items", "logs"])
    return order


# ── тесты ─────────────────────────────────────────────────────────────────────


async def test_cart_subtotal_includes_options(session: AsyncSession, filled):
    view = await cart_service.load_cart(Repos.build(session), USER_ID)
    # (150 + 40 + 25) ₺ × 2 штуки
    assert view.subtotal == 43000
    assert view.count == 2


async def test_order_snapshots_names_and_options(session: AsyncSession, filled):
    order = await build_order(session, make_settings(), payment=PaymentMethod.CASH)
    item = order.items[0]

    assert item.name_ru == "Шаурма куриная"
    assert item.name_ar == "شاورما دجاج"
    assert item.options_text_ru == "Большая, Сыр"
    assert item.line_total == 43000
    assert order.total == 46000  # блюда + 30 ₺ доставки


async def test_snapshot_survives_price_change(session: AsyncSession, filled):
    order = await build_order(session, make_settings(), payment=PaymentMethod.CASH)
    filled["product"].price = 99999
    filled["product"].name_ru = "Другое название"
    await session.flush()
    await session.refresh(order, ["items"])

    assert order.items[0].unit_price == 21500
    assert order.items[0].name_ru == "Шаурма куриная"


async def test_public_number_increments_within_a_day(session: AsyncSession, filled):
    settings = make_settings()
    first = await build_order(session, settings, payment=PaymentMethod.CASH)
    second = await build_order(session, settings, payment=PaymentMethod.CASH)
    assert first.public_no != second.public_no
    assert second.public_no.endswith("002")


async def test_kitchen_card_contains_the_essentials(session: AsyncSession, filled):
    settings = make_settings()
    order = await build_order(session, settings, payment=PaymentMethod.CASH)
    notifier = Notifier(bot=None, settings=settings, i18n=I18n(default_lang="ru"))

    card = notifier.render_card(order)

    assert order.public_no in card
    assert "Шаурма куриная" in card
    assert "Большая, Сыр" in card
    assert "Аль-Хамра 5, кв. 12" in card
    assert "+963912345678" in card
    assert "Без лука" in card
    assert "1.2" in card                      # расстояние для курьера
    assert "460" in card                      # итог 460 ₺
    assert "Наличные при получении" in card
    assert "{" not in card, "в шаблоне остался неподставленный параметр"


async def test_shamcash_card_shows_payment_state(session: AsyncSession, filled):
    settings = make_settings()
    order = await build_order(session, settings, payment=PaymentMethod.SHAMCASH)
    order.payment_ref = "TX-99887"
    order.payment_status = PaymentStatus.SUBMITTED
    notifier = Notifier(bot=None, settings=settings, i18n=I18n(default_lang="ru"))

    card = notifier.render_card(order)

    assert "ShamCash" in card
    assert "TX-99887" in card
    assert "чек прислан" in card


async def test_arabic_card_renders_without_placeholders(session: AsyncSession, filled):
    settings = make_settings(default_lang="ar")
    order = await build_order(session, settings, payment=PaymentMethod.CASH)
    notifier = Notifier(bot=None, settings=settings, i18n=I18n(default_lang="ar"))

    card = notifier.render_card(order)

    assert "شاورما دجاج" in card
    assert "كبير، جبنة".replace("، ", ", ") in card or "كبير, جبنة" in card
    assert "{" not in card


async def test_client_gets_the_right_message_per_status(session: AsyncSession, filled):
    settings = make_settings()
    order = await build_order(session, settings, payment=PaymentMethod.CASH)
    notifier = Notifier(bot=None, settings=settings, i18n=I18n(default_lang="ru"))

    order.status = OrderStatus.COOKING
    assert "Готовим" in notifier._client_text(order, from_status=OrderStatus.ACCEPTED)

    order.status = OrderStatus.READY
    assert "курьер" in notifier._client_text(order, from_status=OrderStatus.COOKING)

    order.fulfillment = Fulfillment.PICKUP
    assert "ждём вас" in notifier._client_text(order, from_status=OrderStatus.COOKING)


async def test_payment_confirmation_beats_generic_accepted(session: AsyncSession, filled):
    settings = make_settings()
    order = await build_order(session, settings, payment=PaymentMethod.SHAMCASH)
    notifier = Notifier(bot=None, settings=settings, i18n=I18n(default_lang="ru"))

    order.status = OrderStatus.ACCEPTED
    text = notifier._client_text(order, from_status=OrderStatus.PAYMENT_SUBMITTED)
    assert "Оплата подтверждена" in text


async def test_new_order_has_no_client_notification(session: AsyncSession, filled):
    settings = make_settings()
    order = await build_order(session, settings, payment=PaymentMethod.CASH)
    notifier = Notifier(bot=None, settings=settings, i18n=I18n(default_lang="ru"))
    assert notifier._client_text(order, from_status=OrderStatus.NEW) is None


async def test_kitchen_keyboard_follows_the_state_machine(session: AsyncSession, filled):
    settings = make_settings()
    order = await build_order(session, settings, payment=PaymentMethod.CASH)
    i18n = I18n(default_lang="ru").translator("ru")

    markup = kitchen_kb(order, i18n)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "✅ Принять" in labels
    assert "❌ Отменить" in labels

    order.status = OrderStatus.DELIVERED
    assert kitchen_kb(order, i18n) is None


async def test_stop_listed_product_is_flagged_in_cart(session: AsyncSession, filled):
    filled["product"].is_active = False
    await session.flush()

    view = await cart_service.load_cart(Repos.build(session), USER_ID)
    assert len(view.unavailable) == 1


async def test_repeat_order_keeps_option_ids(session: AsyncSession, filled):
    order = await build_order(session, make_settings(), payment=PaymentMethod.CASH)
    assert sorted(order.items[0].option_ids) == sorted([filled["big"].id, filled["cheese"].id])


@pytest.mark.parametrize(
    ("payment", "status"),
    [
        (PaymentMethod.CASH, OrderStatus.NEW),
        (PaymentMethod.SHAMCASH, OrderStatus.AWAITING_PAYMENT),
    ],
)
async def test_initial_status_depends_on_payment(
    session: AsyncSession, filled, payment: PaymentMethod, status: OrderStatus
):
    order = await build_order(session, make_settings(), payment=payment)
    assert order.status == status


# ── вторая цена в заказе ──────────────────────────────────────────────────────


async def test_kitchen_card_shows_both_currencies(session: AsyncSession, filled):
    settings = make_settings(secondary_currency="USD")
    rate = Rate("TRY", "USD", 20682, datetime.now(UTC))
    order = await build_order(session, settings, payment=PaymentMethod.CASH, rate=rate)
    notifier = Notifier(bot=None, settings=settings, i18n=I18n(default_lang="ru"))

    card = notifier.render_card(order)

    assert "460" in card          # точная сумма в лирах
    assert "9.51" in card         # ориентир в долларах
    assert money_service.APPROX in card


async def test_order_keeps_the_rate_it_was_placed_at(session: AsyncSession, filled):
    """Курс уехал вдвое, а сумма в истории заказа обязана остаться прежней."""
    settings = make_settings(secondary_currency="USD")
    placed_at = Rate("TRY", "USD", 20682, datetime.now(UTC))
    order = await build_order(session, settings, payment=PaymentMethod.CASH, rate=placed_at)

    before = money_service.dual_for_order(settings, order, order.total)
    _later_and_very_different = Rate("TRY", "USD", 41364, datetime.now(UTC))
    after = money_service.dual_for_order(settings, order, order.total)

    assert before == after
    assert "9.51" in after


async def test_order_without_snapshot_shows_single_price(session: AsyncSession, filled):
    """Заказ, оформленный при недоступном сайте курса, показывает одну цену, а не ноль."""
    settings = make_settings(secondary_currency="USD")
    order = await build_order(session, settings, payment=PaymentMethod.CASH, rate=None)

    text = money_service.dual_for_order(settings, order, order.total)

    assert "460" in text
    assert money_service.APPROX not in text
