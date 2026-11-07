"""Подсчёт денег. Всё в целых минорных единицах — никакой плавающей точки."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


class HasLineTotal(Protocol):
    @property
    def line_total(self) -> int: ...


class HasPriceDelta(Protocol):
    price_delta: int


def unit_price(base_price: int, options: Iterable[HasPriceDelta]) -> int:
    """Цена одной штуки товара с учётом выбранных опций."""
    return base_price + sum(o.price_delta for o in options)


def subtotal(items: Iterable[HasLineTotal]) -> int:
    return sum(item.line_total for item in items)


@dataclass(frozen=True, slots=True)
class Totals:
    subtotal: int
    delivery_fee: int
    total: int
    #: True, если доставка обнулилась по порогу бесплатной доставки.
    delivery_is_free: bool


def totals(
    *,
    items_subtotal: int,
    delivery_fee: int,
    free_delivery_from: int = 0,
) -> Totals:
    """Итоги заказа. ``free_delivery_from=0`` выключает порог бесплатной доставки."""
    is_free = (
        delivery_fee > 0 and free_delivery_from > 0 and items_subtotal >= free_delivery_from
    )
    fee = 0 if is_free else delivery_fee
    return Totals(
        subtotal=items_subtotal,
        delivery_fee=fee,
        total=items_subtotal + fee,
        delivery_is_free=is_free,
    )


def below_minimum(items_subtotal: int, min_order_total: int) -> int:
    """Сколько не хватает до минимальной суммы заказа. 0 — всё в порядке.

    Минимум считается по стоимости блюд: доплачивать доставкой до минимального заказа
    было бы нечестно по отношению к клиенту.
    """
    if min_order_total <= 0:
        return 0
    return max(0, min_order_total - items_subtotal)
