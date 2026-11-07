"""Оформление заказа: способ получения, адрес, телефон, оплата, подтверждение."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.config import Settings
from bot.db.enums import Fulfillment, PaymentMethod
from bot.db.models import Order, User
from bot.db.repo import Repos
from bot.handlers.common import MenuText, fmt_dual, fmt_money, replace
from bot.i18n import Translator
from bot.keyboards.callbacks import CheckoutCB
from bot.keyboards.client import (
    branches_kb,
    comment_kb,
    confirm_kb,
    contact_kb,
    fulfillment_kb,
    location_kb,
    main_menu_kb,
    payment_kb,
)
from bot.services import cart as cart_service
from bot.services import geo, pricing
from bot.services import money as money_service
from bot.services import orders as order_service
from bot.services.notifier import Notifier
from bot.services.rates import RateProvider
from bot.services.schedule import accepting_orders, format_hours
from bot.states.checkout import Checkout
from bot.utils.format import escape_html, rtl

logger = logging.getLogger(__name__)
router = Router(name="checkout")

# Клиентские сценарии живут только в личке. В группе кухни «клиента» нет — там у
# хендлеров не будет ни пользователя, ни его языка, и любое нажатие роняло бы бота.
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)


# ── вход ──────────────────────────────────────────────────────────────────────


async def start_checkout(
    callback: CallbackQuery,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
) -> None:
    """Точка входа из корзины. Все проверки — до первого вопроса клиенту."""
    if not accepting_orders(settings):
        await callback.answer(
            i18n("checkout-closed", hours=format_hours(*settings.hours)), show_alert=True
        )
        return

    view = await cart_service.load_cart(repos, user.tg_id)
    if view.is_empty:
        await callback.answer(i18n("cart-empty"), show_alert=True)
        return

    if view.unavailable:
        names = ", ".join(i.product.name(user.lang.value) for i in view.unavailable)
        await cart_service.drop_unavailable(repos, view)
        await callback.answer(
            i18n("cart-unavailable-removed", names=names), show_alert=True
        )
        return

    missing = pricing.below_minimum(view.subtotal, settings.min_order_total)
    if missing:
        await callback.answer(
            i18n(
                "cart-min-order",
                min=fmt_money(settings, settings.min_order_total),
                left=fmt_money(settings, missing),
            ),
            show_alert=True,
        )
        return

    await state.set_state(Checkout.fulfillment)
    await replace(
        callback.message, i18n("checkout-fulfillment"), reply_markup=fulfillment_kb(i18n)
    )
    await callback.answer()


# ── способ получения ──────────────────────────────────────────────────────────


@router.callback_query(CheckoutCB.filter(F.step == "cancel"))
async def cancel(
    callback: CallbackQuery, state: FSMContext, i18n: Translator
) -> None:
    await state.clear()
    await replace(callback.message, i18n("checkout-cancelled"))
    await callback.message.answer(i18n("main-menu"), reply_markup=main_menu_kb(i18n))
    await callback.answer()


@router.message(MenuText("btn-cancel"))
async def cancel_by_button(message: Message, state: FSMContext, i18n: Translator) -> None:
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer(i18n("checkout-cancelled"), reply_markup=main_menu_kb(i18n))


@router.callback_query(Checkout.fulfillment, CheckoutCB.filter(F.step == "fulfillment"))
async def pick_fulfillment(
    callback: CallbackQuery,
    callback_data: CheckoutCB,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
) -> None:
    await state.update_data(fulfillment=callback_data.value)

    if callback_data.value == Fulfillment.PICKUP:
        branches = await repos.menu.branches()
        await state.set_state(Checkout.branch)
        await replace(
            callback.message,
            i18n("checkout-branch"),
            reply_markup=branches_kb(branches, user.lang.value, i18n),
        )
        await callback.answer()
        return

    await state.set_state(Checkout.location)
    # Кнопку «отправить локацию» несёт reply-клавиатура, а её нельзя приложить
    # к инлайн-сообщению — поэтому старое удаляем и шлём новое одним куском.
    await replace(callback.message, i18n("checkout-location"))
    await callback.message.answer(
        i18n("btn-send-location"), reply_markup=location_kb(i18n)
    )
    await callback.answer()


@router.callback_query(Checkout.branch, CheckoutCB.filter(F.step == "branch"))
async def pick_branch(
    callback: CallbackQuery,
    callback_data: CheckoutCB,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
) -> None:
    branch = await repos.menu.get_branch(int(callback_data.value))
    if branch is None:
        await callback.answer(i18n("error-stale-button"))
        return

    await state.update_data(branch_id=branch.id, delivery_fee=0)
    await replace(
        callback.message,
        i18n(
            "checkout-branch-picked",
            name=escape_html(branch.name(user.lang.value)),
            address=escape_html(branch.address(user.lang.value)),
        ),
    )
    await _ask_contact(callback.message, state, i18n, user)
    await callback.answer()


# ── адрес доставки ────────────────────────────────────────────────────────────


@router.message(Checkout.location, F.location)
async def got_location(
    message: Message,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
) -> None:
    branch = await repos.menu.default_branch()
    if branch is None:
        logger.error("Не настроен ни один филиал — доставку посчитать не от чего")
        await message.answer(i18n("error-generic", support=settings.support_contact))
        return

    quote = geo.resolve_delivery(
        message.location.latitude,
        message.location.longitude,
        branch_lat=branch.lat,
        branch_lon=branch.lon,
        tiers=settings.delivery_tiers,
    )

    if quote is None:
        distance = geo.haversine_km(
            branch.lat, branch.lon, message.location.latitude, message.location.longitude
        )
        await message.answer(
            i18n(
                "checkout-out-of-zone",
                distance=f"{distance:.1f}",
                max=f"{settings.max_delivery_km:g}",
                support=settings.support_contact,
            )
        )
        return

    await state.update_data(
        lat=message.location.latitude,
        lon=message.location.longitude,
        distance_km=quote.distance_km,
        delivery_fee=quote.fee,
        branch_id=branch.id,
    )
    await message.answer(
        i18n(
            "checkout-in-zone",
            fee=fmt_money(settings, quote.fee),
            distance=f"{quote.distance_km:.1f}",
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    # Улицы и номера домов в Сирии сплошь и рядом отсутствуют, поэтому адрес не
    # спрашиваем: точка на карте точнее любого текста, а связь идёт через Telegram.
    # Ориентир, если он нужен, клиент допишет в комментарии к заказу.
    await _ask_contact(message, state, i18n, user)


@router.message(Checkout.location)
async def location_expected(message: Message, i18n: Translator) -> None:
    await message.answer(i18n("checkout-location-invalid"), reply_markup=location_kb(i18n))


# ── контакт ───────────────────────────────────────────────────────────────────


async def _ask_contact(
    message: Message, state: FSMContext, i18n: Translator, user: User
) -> None:
    """Показывает, по какому аккаунту с клиентом свяжутся, и ждёт подтверждения.

    Телефон не спрашивается: в Сирии точных адресов часто нет, зато Telegram есть у
    всех, и кухне удобнее писать в тот же чат, где сделан заказ.
    """
    await state.set_state(Checkout.contact)
    await message.answer(
        i18n("checkout-contact"), reply_markup=contact_kb(i18n, user.username)
    )


@router.callback_query(Checkout.contact, CheckoutCB.filter(F.step == "contact"))
async def confirm_contact(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: Translator,
    user: User,
    settings: Settings,
) -> None:
    await state.update_data(username=user.username)
    await callback.message.delete()
    await _go_to_payment(callback.message, state, i18n, settings)
    await callback.answer()


async def _go_to_payment(
    message: Message, state: FSMContext, i18n: Translator, settings: Settings
) -> None:
    await state.set_state(Checkout.payment)
    await message.answer(
        i18n("checkout-payment"),
        # ShamCash предлагается, только если реквизиты действительно настроены.
        reply_markup=payment_kb(i18n, shamcash_enabled=bool(settings.shamcash_wallet)),
    )


# ── оплата и комментарий ──────────────────────────────────────────────────────


@router.callback_query(Checkout.payment, CheckoutCB.filter(F.step == "payment"))
async def pick_payment(
    callback: CallbackQuery,
    callback_data: CheckoutCB,
    state: FSMContext,
    i18n: Translator,
) -> None:
    await state.update_data(payment_method=callback_data.value)
    await state.set_state(Checkout.comment)
    await replace(callback.message, i18n("checkout-comment"), reply_markup=comment_kb(i18n))
    await callback.answer()


@router.message(Checkout.comment, F.text)
async def got_comment(
    message: Message,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    await state.update_data(comment=message.text.strip()[:500])
    await _show_confirmation(message, state, repos, i18n, user, settings, rates)


@router.callback_query(Checkout.comment, CheckoutCB.filter(F.step == "comment_skip"))
async def skip_comment(
    callback: CallbackQuery,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    await state.update_data(comment=None)
    await callback.message.delete()
    await _show_confirmation(callback.message, state, repos, i18n, user, settings, rates)
    await callback.answer()


# ── подтверждение ─────────────────────────────────────────────────────────────


async def _show_confirmation(
    message: Message,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    data = await state.get_data()
    view = await cart_service.load_cart(repos, user.tg_id)
    if view.is_empty:
        await state.clear()
        await message.answer(i18n("cart-empty"), reply_markup=main_menu_kb(i18n))
        return

    lang = user.lang.value
    total = pricing.totals(
        items_subtotal=view.subtotal,
        delivery_fee=int(data.get("delivery_fee") or 0),
        free_delivery_from=settings.free_delivery_from,
    )

    lines = [i18n("checkout-confirm-title"), ""]
    for index, item in enumerate(view.items, start=1):
        options = cart_service.options_text(item, lang)
        lines.append(
            i18n(
                "cart-line",
                index=index,
                name=escape_html(item.product.name(lang)),
                options=f" ({escape_html(options)})" if options else "",
                qty=item.qty,
                price=fmt_money(settings, item.unit_price),
                total=fmt_money(settings, item.line_total),
            )
        )
    lines.append("")

    if data.get("fulfillment") == Fulfillment.DELIVERY:
        lines.append(
            i18n(
                "checkout-confirm-delivery",
                distance=f"{float(data.get('distance_km') or 0):.1f}",
            )
        )
        lines.append(
            i18n("checkout-confirm-delivery-free")
            if total.delivery_is_free
            else i18n(
                "checkout-confirm-delivery-fee",
                fee=fmt_money(settings, total.delivery_fee),
            )
        )
    else:
        branch = await repos.menu.get_branch(int(data.get("branch_id") or 0))
        lines.append(
            i18n(
                "checkout-confirm-pickup",
                branch=escape_html(branch.name(lang) if branch else "—"),
            )
        )

    username = data.get("username")
    lines.append(
        i18n("checkout-confirm-contact", username=escape_html(username))
        if username
        else i18n("checkout-confirm-no-username")
    )
    if data.get("comment"):
        lines.append(
            i18n("checkout-confirm-comment", comment=escape_html(data["comment"]))
        )
    method_key = (
        "payment-method-shamcash"
        if data.get("payment_method") == PaymentMethod.SHAMCASH
        else "payment-method-cash"
    )
    lines.append(i18n("checkout-confirm-payment", method=i18n(method_key)))
    lines.append("")
    lines.append(
        i18n("checkout-confirm-total", total=fmt_dual(settings, rates, total.total))
    )

    await state.set_state(Checkout.confirm)
    await message.answer(
        rtl("\n".join(lines), is_rtl=i18n.is_rtl), reply_markup=confirm_kb(i18n)
    )


@router.callback_query(Checkout.confirm, CheckoutCB.filter(F.step == "confirm"))
async def confirm_order(
    callback: CallbackQuery,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
    notifier: Notifier,
) -> None:
    data = await state.get_data()
    view = await cart_service.load_cart(repos, user.tg_id)

    if view.is_empty or view.unavailable:
        await state.clear()
        await callback.answer(i18n("cart-empty"), show_alert=True)
        return

    order = await _create_order(repos, user, data, view, settings, rates)
    await repos.cart.clear(user.tg_id)
    await state.clear()

    await notifier.publish(order)
    await repos.session.flush()

    await callback.message.delete()
    if order.payment_method == PaymentMethod.SHAMCASH:
        await callback.message.answer(
            i18n("order-created-shamcash", no=order.public_no),
            reply_markup=main_menu_kb(i18n),
        )
        await callback.message.answer(
            i18n(
                "shamcash-instructions",
                total=money_service.dual_for_order(settings, order, order.total),
                wallet=escape_html(settings.shamcash_wallet),
                holder=escape_html(settings.shamcash_holder),
            )
        )
    else:
        await callback.message.answer(
            i18n("order-created-cash", no=order.public_no),
            reply_markup=main_menu_kb(i18n),
        )
    await callback.answer()


async def _create_order(
    repos: Repos,
    user: User,
    data: dict,
    view: cart_service.CartView,
    settings: Settings,
    rates: RateProvider,
) -> Order:
    fulfillment = Fulfillment(data.get("fulfillment", Fulfillment.DELIVERY))
    payment_method = PaymentMethod(data.get("payment_method", PaymentMethod.CASH))

    total = pricing.totals(
        items_subtotal=view.subtotal,
        delivery_fee=int(data.get("delivery_fee") or 0),
        free_delivery_from=settings.free_delivery_from,
    )

    # Курс фиксируется здесь: клиент подтверждает сумму, которую видит, и позже она
    # не должна измениться от того, что доллар подорожал.
    snapshot = money_service.live_rate(settings, rates)

    option_ids = [oid for item in view.items for oid in (item.option_ids or [])]
    options_by_id = {o.id: o for o in await repos.menu.get_options(option_ids)}
    items = order_service.snapshot_items(view.items, options_by_id)

    order = Order(
        public_no=await repos.orders.next_public_no(settings.timezone),
        user_id=user.tg_id,
        status=order_service.initial_status(payment_method),
        fulfillment=fulfillment,
        branch_id=data.get("branch_id"),
        address_text=data.get("address_text"),
        lat=data.get("lat"),
        lon=data.get("lon"),
        distance_km=data.get("distance_km"),
        phone=None,
        comment=data.get("comment"),
        lang=user.lang,
        payment_method=payment_method,
        payment_status=order_service.initial_payment_status(payment_method),
        subtotal=total.subtotal,
        delivery_fee=total.delivery_fee,
        total=total.total,
        currency=settings.currency,
        secondary_currency=snapshot.quote if snapshot else None,
        rate_micro=snapshot.micro if snapshot else None,
    )
    await repos.orders.add(order, items)
    # Карточке кухни нужны связанные объекты — подтягиваем их до рендера.
    await repos.session.refresh(order, ["user", "branch", "items", "logs"])
    return order
