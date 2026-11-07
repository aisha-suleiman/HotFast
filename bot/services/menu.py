"""Разворачивание меню в покупаемые варианты.

Раньше блюдо открывалось отдельной карточкой, и чтобы взять шаурму и донер, приходилось
ходить туда-обратно. Для маленького меню это лишние экраны: проще показать все варианты
списком, у каждого свой счётчик.

Вариант — это блюдо вместе с выбором обязательной опции: «Шаурма» и «Шаурма · Дубль» —
две отдельные строки, потому что это две разные покупки с разной ценой.
"""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.models import CartItem, Option, Product


@dataclass(frozen=True, slots=True)
class Variant:
    """Одна покупаемая позиция меню."""

    product: Product
    option: Option | None = None
    #: True — одной кнопкой не купить, нужна карточка с опциями.
    needs_card: bool = False

    @property
    def price(self) -> int:
        return self.product.price + (self.option.price_delta if self.option else 0)

    @property
    def option_ids(self) -> list[int]:
        return [self.option.id] if self.option else []

    @property
    def key(self) -> tuple[int, tuple[int, ...]]:
        """Чем позиция отличается от других в корзине: товар плюс набор опций."""
        return self.product.id, tuple(sorted(self.option_ids))

    def name(self, lang: str) -> str:
        base = self.product.name(lang)
        return f"{base} · {self.option.name(lang)}" if self.option else base


def expand(product: Product) -> list[Variant]:
    """Разворачивает блюдо в строки меню.

    Разворачиваем только простой и самый частый случай: одна обязательная группа с выбором
    ровно одного варианта (порция). Всё сложнее — добавки, несколько групп — остаётся за
    карточкой: пытаться уместить перебор сочетаний в список кнопок бессмысленно.
    """
    groups = [g for g in product.option_groups if any(o.is_active for o in g.options)]

    if not groups:
        return [Variant(product)]

    if len(groups) == 1:
        group = groups[0]
        if group.min_select == 1 and group.max_select == 1:
            return [
                Variant(product, option)
                for option in group.options
                if option.is_active
            ]

    return [Variant(product, needs_card=True)]


def variants_of(products: list[Product]) -> list[Variant]:
    return [variant for product in products for variant in expand(product)]


def cart_counts(items: list[CartItem]) -> dict[tuple[int, tuple[int, ...]], int]:
    """Сколько каждого варианта уже лежит в корзине."""
    counts: dict[tuple[int, tuple[int, ...]], int] = {}
    for item in items:
        key = (item.product_id, tuple(sorted(item.option_ids or [])))
        counts[key] = counts.get(key, 0) + item.qty
    return counts
