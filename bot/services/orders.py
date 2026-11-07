"""Машина состояний заказа.

Один словарь :data:`ALLOWED` — единственный источник правды. Из него строятся и кнопки в
группе кухни, и валидация перехода. Так они не могут разъехаться: нельзя добавить кнопку,
которая ведёт в запрещённый статус, или запретить переход, оставив кнопку.
"""

from __future__ import annotations

from bot.db.enums import (
    TERMINAL_STATUSES,
    Fulfillment,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from bot.db.models import CartItem, Option, OrderItem

S = OrderStatus

ALLOWED: dict[OrderStatus, frozenset[OrderStatus]] = {
    S.NEW: frozenset({S.AWAITING_PAYMENT, S.ACCEPTED, S.CANCELLED}),
    S.AWAITING_PAYMENT: frozenset({S.PAYMENT_SUBMITTED, S.CANCELLED}),
    S.PAYMENT_SUBMITTED: frozenset({S.ACCEPTED, S.PAYMENT_REJECTED, S.CANCELLED}),
    # Отклонённая оплата — не тупик: клиент может прислать правильный чек.
    S.PAYMENT_REJECTED: frozenset({S.PAYMENT_SUBMITTED, S.CANCELLED}),
    S.ACCEPTED: frozenset({S.COOKING, S.CANCELLED}),
    S.COOKING: frozenset({S.READY, S.CANCELLED}),
    S.READY: frozenset({S.ON_THE_WAY, S.PICKED_UP, S.CANCELLED}),
    S.ON_THE_WAY: frozenset({S.DELIVERED, S.CANCELLED}),
    S.DELIVERED: frozenset(),
    S.PICKED_UP: frozenset(),
    S.CANCELLED: frozenset(),
}

#: Переходы, которые совершает клиент, а не кухня, — кнопок в группе для них нет.
CLIENT_DRIVEN = frozenset({S.PAYMENT_SUBMITTED})


class InvalidTransition(RuntimeError):
    def __init__(self, from_status: OrderStatus, to_status: OrderStatus) -> None:
        super().__init__(f"Переход {from_status} -> {to_status} запрещён")
        self.from_status = from_status
        self.to_status = to_status


def initial_status(payment_method: PaymentMethod) -> OrderStatus:
    """При ShamCash заказ сразу ждёт оплату, при наличных — решения кухни."""
    return S.AWAITING_PAYMENT if payment_method == PaymentMethod.SHAMCASH else S.NEW


def initial_payment_status(payment_method: PaymentMethod) -> PaymentStatus:
    return (
        PaymentStatus.AWAITING
        if payment_method == PaymentMethod.SHAMCASH
        else PaymentStatus.NOT_REQUIRED
    )


def allowed_from(status: OrderStatus, fulfillment: Fulfillment) -> list[OrderStatus]:
    """Разрешённые переходы с учётом способа получения.

    Из ``READY`` доставка ведёт в ``ON_THE_WAY``, а самовывоз — в ``PICKED_UP``;
    показывать кухне обе кнопки значило бы предлагать заведомо неверную.
    """
    targets = ALLOWED[status]
    if status == S.READY:
        drop = S.PICKED_UP if fulfillment == Fulfillment.DELIVERY else S.ON_THE_WAY
        targets = targets - {drop}
    return sorted(targets, key=_ORDER_OF_APPEARANCE.index)


def kitchen_buttons(status: OrderStatus, fulfillment: Fulfillment) -> list[OrderStatus]:
    """Что показывать кухне: всё разрешённое, кроме переходов, которые делает клиент."""
    return [s for s in allowed_from(status, fulfillment) if s not in CLIENT_DRIVEN]


def can_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    return to_status in ALLOWED[from_status]


def is_terminal(status: OrderStatus) -> bool:
    return status in TERMINAL_STATUSES


def apply_transition(order, to_status: OrderStatus) -> OrderStatus:
    """Меняет статус заказа и связанный с ним статус оплаты. Возвращает прежний статус.

    Бросает :class:`InvalidTransition`, если переход запрещён, — в том числе при повторном
    нажатии кнопки в группе, когда заказ уже уехал дальше.
    """
    from_status: OrderStatus = order.status
    if not can_transition(from_status, to_status):
        raise InvalidTransition(from_status, to_status)

    order.status = to_status
    _sync_payment_status(order, from_status, to_status)
    return from_status


def _sync_payment_status(order, from_status: OrderStatus, to_status: OrderStatus) -> None:
    if order.payment_method != PaymentMethod.SHAMCASH:
        return
    if to_status == S.AWAITING_PAYMENT:
        order.payment_status = PaymentStatus.AWAITING
    elif to_status == S.PAYMENT_SUBMITTED:
        order.payment_status = PaymentStatus.SUBMITTED
    elif to_status == S.PAYMENT_REJECTED:
        order.payment_status = PaymentStatus.REJECTED
    elif to_status == S.ACCEPTED and from_status == S.PAYMENT_SUBMITTED:
        # Кухня приняла заказ после проверки чека — значит, деньги пришли.
        order.payment_status = PaymentStatus.CONFIRMED


#: Порядок для сортировки кнопок: сначала движение вперёд, отмена последней.
_ORDER_OF_APPEARANCE = [
    S.AWAITING_PAYMENT,
    S.PAYMENT_SUBMITTED,
    S.ACCEPTED,
    S.COOKING,
    S.READY,
    S.ON_THE_WAY,
    S.DELIVERED,
    S.PICKED_UP,
    S.PAYMENT_REJECTED,
    S.CANCELLED,
]

STATUS_EMOJI: dict[OrderStatus, str] = {
    S.NEW: "🆕",
    S.AWAITING_PAYMENT: "⏳",
    S.PAYMENT_SUBMITTED: "🧾",
    S.PAYMENT_REJECTED: "⚠️",
    S.ACCEPTED: "✅",
    S.COOKING: "👨‍🍳",
    S.READY: "🥙",
    S.ON_THE_WAY: "🛵",
    S.DELIVERED: "🎉",
    S.PICKED_UP: "🎉",
    S.CANCELLED: "❌",
}


def snapshot_items(
    cart_items: list[CartItem], options_by_id: dict[int, Option]
) -> list[OrderItem]:
    """Превращает корзину в позиции заказа со снимком названий и цен.

    Снимок обязателен: завтра товар подорожает или уедет в стоп-лист, а в истории заказа
    должно остаться то, что клиент реально купил.
    """
    result: list[OrderItem] = []
    for item in cart_items:
        chosen = [options_by_id[oid] for oid in (item.option_ids or []) if oid in options_by_id]
        result.append(
            OrderItem(
                product_id=item.product_id,
                name_ar=item.product.name_ar,
                name_ru=item.product.name_ru,
                options_text_ar=", ".join(o.name_ar for o in chosen) or None,
                options_text_ru=", ".join(o.name_ru for o in chosen) or None,
                option_ids=[o.id for o in chosen],
                unit_price=item.unit_price,
                qty=item.qty,
                line_total=item.line_total,
            )
        )
    return result
