"""Операции над корзиной, которым нужны и репозитории, и правила меню."""

from __future__ import annotations

from dataclasses import dataclass, field

from bot.db.models import CartItem, Option, OptionGroup, Product
from bot.db.repo import Repos
from bot.services import pricing


@dataclass(slots=True)
class CartView:
    items: list[CartItem]
    subtotal: int
    #: Позиции, товар которых уехал в стоп-лист, — оформить заказ с ними нельзя.
    unavailable: list[CartItem] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def count(self) -> int:
        return sum(i.qty for i in self.items)


async def load_cart(repos: Repos, user_id: int) -> CartView:
    items = await repos.cart.items(user_id)
    unavailable = [i for i in items if not i.product.is_active]
    return CartView(
        items=items,
        subtotal=pricing.subtotal(items),
        unavailable=unavailable,
    )


async def drop_unavailable(repos: Repos, view: CartView) -> None:
    for item in view.unavailable:
        await repos.cart.remove(item)


def validate_selection(product: Product, selected_ids: set[int]) -> OptionGroup | None:
    """Первая группа опций, требования которой нарушены, либо None, если всё в порядке."""
    for group in product.option_groups:
        ids = {o.id for o in group.options if o.is_active}
        picked = len(selected_ids & ids)
        if picked < group.min_select or picked > group.max_select:
            return group
    return None


def toggle_option(
    product: Product, selected_ids: set[int], option_id: int
) -> set[int]:
    """Переключает опцию с учётом ограничений её группы.

    В группе с ``max_select == 1`` (размер) выбор нового варианта заменяет прежний, а не
    добавляется к нему — иначе клиент упрётся в ошибку валидации и не поймёт почему.
    """
    group = _group_of(product, option_id)
    if group is None:
        return selected_ids

    result = set(selected_ids)
    sibling_ids = {o.id for o in group.options}

    if option_id in result:
        # Повторное нажатие снимает выбор, но не ниже обязательного минимума.
        if len(result & sibling_ids) > group.min_select:
            result.discard(option_id)
        return result

    if group.max_select == 1:
        result -= sibling_ids
    elif len(result & sibling_ids) >= group.max_select:
        return result  # лимит группы исчерпан, молча игнорируем
    result.add(option_id)
    return result


def default_selection(product: Product) -> set[int]:
    """Предвыбор для обязательных групп: первый активный вариант размера и т.п."""
    selected: set[int] = set()
    for group in product.option_groups:
        if group.min_select > 0:
            active = [o for o in group.options if o.is_active]
            selected.update(o.id for o in active[: group.min_select])
    return selected


def price_with_options(product: Product, options: list[Option]) -> int:
    return pricing.unit_price(product.price, options)


def _group_of(product: Product, option_id: int) -> OptionGroup | None:
    for group in product.option_groups:
        if any(o.id == option_id for o in group.options):
            return group
    return None


def options_text(item: CartItem, lang: str) -> str:
    """Названия выбранных опций строкой: «острая, большая».

    Опции берутся из уже загруженного товара — без похода в базу на каждую позицию.
    """
    if not item.option_ids:
        return ""
    chosen = set(item.option_ids)
    return ", ".join(
        option.name(lang)
        for group in item.product.option_groups
        for option in group.options
        if option.id in chosen
    )


def options_of(product: Product, selected_ids: set[int]) -> list[Option]:
    """Выбранные опции в порядке групп — так они читаются в карточке и в заказе."""
    result: list[Option] = []
    for group in product.option_groups:
        result.extend(o for o in group.options if o.id in selected_ids)
    return result
