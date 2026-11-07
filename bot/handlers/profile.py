"""История заказов и повтор заказа."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repos
from bot.handlers.common import MenuText
from bot.i18n import Translator
from bot.keyboards.callbacks import OrderCB
from bot.keyboards.client import orders_kb
from bot.services import cart as cart_service
from bot.services import money as money_service
from bot.utils.format import escape_html, rtl

router = Router(name="profile")

# Клиентские сценарии живут только в личке. В группе кухни «клиента» нет — там у
# хендлеров не будет ни пользователя, ни его языка, и любое нажатие роняло бы бота.
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

#: Сколько последних заказов показываем в истории.
HISTORY_LIMIT = 5


@router.message(MenuText("menu-orders"))
async def my_orders(
    message: Message, repos: Repos, i18n: Translator, user: User, settings: Settings
) -> None:
    orders = await repos.orders.user_orders(user.tg_id, limit=HISTORY_LIMIT)
    if not orders:
        await message.answer(i18n("orders-empty"))
        return

    lines = [i18n("orders-title"), ""]
    for order in orders:
        lines.append(
            i18n(
                "orders-line",
                no=order.public_no,
                date=order.created_at.astimezone(settings.timezone).strftime("%d.%m %H:%M"),
                status=i18n(f"status-name-{order.status.value}"),
                total=money_service.dual_for_order(settings, order, order.total),
            )
        )

    await message.answer(
        rtl("\n".join(lines), is_rtl=i18n.is_rtl), reply_markup=orders_kb(orders, i18n)
    )


@router.callback_query(OrderCB.filter())
async def repeat_order(
    callback: CallbackQuery,
    callback_data: OrderCB,
    repos: Repos,
    i18n: Translator,
    user: User,
) -> None:
    order = await repos.orders.get(callback_data.order_id)
    if order is None or order.user_id != user.tg_id:
        await callback.answer(i18n("error-stale-button"), show_alert=True)
        return

    added, skipped = 0, []
    for item in order.items:
        product = (
            await repos.menu.get_product(item.product_id) if item.product_id else None
        )
        if product is None or not product.is_active:
            skipped.append(item.name(user.lang.value))
            continue

        # Опции могли исчезнуть из меню — берём только те, что ещё активны, и
        # пересчитываем цену по сегодняшнему прайсу, а не по цене из истории.
        wanted = set(item.option_ids or [])
        still_available = {
            option.id
            for group in product.option_groups
            for option in group.options
            if option.id in wanted and option.is_active
        }
        options = cart_service.options_of(product, still_available)
        await repos.cart.add(
            user.tg_id,
            product_id=product.id,
            qty=item.qty,
            option_ids=[o.id for o in options],
            unit_price=cart_service.price_with_options(product, options),
        )
        added += 1

    if not added:
        await callback.answer(i18n("orders-repeat-empty"), show_alert=True)
        return

    await callback.answer(i18n("orders-repeat-done"))
    if skipped:
        await callback.message.answer(
            i18n("orders-repeat-partial", names=escape_html(", ".join(skipped)))
        )
