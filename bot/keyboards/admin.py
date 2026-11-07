"""Клавиатура карточки заказа в группе кухни.

Кнопки строятся из разрешённых переходов, а не задаются вручную: добавить кнопку,
ведущую в запрещённый статус, физически невозможно.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db.enums import OrderStatus
from bot.db.models import Order
from bot.i18n import Translator
from bot.keyboards.callbacks import KitchenCB
from bot.services.orders import kitchen_buttons


def kitchen_kb(order: Order, i18n: Translator) -> InlineKeyboardMarkup | None:
    """None — заказ в терминальном статусе, кнопки больше не нужны."""
    targets = kitchen_buttons(order.status, order.fulfillment)
    if not targets:
        return None

    builder = InlineKeyboardBuilder()
    forward = [s for s in targets if s not in (OrderStatus.CANCELLED, OrderStatus.PAYMENT_REJECTED)]
    negative = [s for s in targets if s in (OrderStatus.CANCELLED, OrderStatus.PAYMENT_REJECTED)]

    for status in forward:
        builder.row(_button(order.id, status, i18n))
    if negative:
        builder.row(*[_button(order.id, status, i18n) for status in negative])
    return builder.as_markup()


def _button(order_id: int, status: OrderStatus, i18n: Translator) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=i18n(f"kitchen-btn-{status.value}"),
        callback_data=KitchenCB(order_id=order_id, to_status=status.value).pack(),
    )
