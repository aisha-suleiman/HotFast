"""Перечисления заказа. Значения пишутся в БД строками — читаемо в SQL и переживает миграции."""

from __future__ import annotations

from enum import StrEnum


class Lang(StrEnum):
    AR = "ar"
    RU = "ru"


class Fulfillment(StrEnum):
    DELIVERY = "delivery"
    PICKUP = "pickup"


class PaymentMethod(StrEnum):
    CASH = "cash"
    SHAMCASH = "shamcash"


class PaymentStatus(StrEnum):
    NOT_REQUIRED = "not_required"   # наличные при получении
    AWAITING = "awaiting"           # ждём скриншот от клиента
    SUBMITTED = "submitted"         # клиент прислал чек, ждём админа
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class OrderStatus(StrEnum):
    NEW = "new"
    AWAITING_PAYMENT = "awaiting_payment"
    PAYMENT_SUBMITTED = "payment_submitted"
    PAYMENT_REJECTED = "payment_rejected"
    ACCEPTED = "accepted"
    COOKING = "cooking"
    READY = "ready"
    ON_THE_WAY = "on_the_way"
    DELIVERED = "delivered"
    PICKED_UP = "picked_up"
    CANCELLED = "cancelled"


#: Статусы, из которых нет выхода.
TERMINAL_STATUSES = frozenset(
    {OrderStatus.DELIVERED, OrderStatus.PICKED_UP, OrderStatus.CANCELLED}
)

#: Статусы, в которых заказ считается активным для клиента.
ACTIVE_STATUSES = frozenset(set(OrderStatus) - set(TERMINAL_STATUSES))
