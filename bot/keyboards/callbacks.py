"""Фабрики callback-данных — единственное место, где описан их формат.

Telegram ограничивает callback_data 64 байтами, поэтому префиксы короткие.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class LangCB(CallbackData, prefix="lg"):
    lang: str


class NavCB(CallbackData, prefix="nv"):
    #: main | catalog | cart | orders | contacts | language | noop
    to: str


class CatalogCB(CallbackData, prefix="ct"):
    #: list — список категорий, open — товары категории
    action: str
    category_id: int = 0
    page: int = 0


class ProductCB(CallbackData, prefix="pr"):
    #: open | inc | dec | opt | add
    action: str
    product_id: int
    #: id опции для action=opt, иначе 0
    opt_id: int = 0
    #: чтобы кнопка «назад» вернула на ту же страницу списка
    page: int = 0


class CartCB(CallbackData, prefix="cr"):
    #: inc | dec | del | clear | checkout | show
    action: str
    item_id: int = 0


class CheckoutCB(CallbackData, prefix="co"):
    #: fulfillment | branch | payment | comment_skip | confirm | cancel
    step: str
    value: str = ""


class OrderCB(CallbackData, prefix="or"):
    #: repeat | show
    action: str
    order_id: int


class KitchenCB(CallbackData, prefix="kt"):
    """Кнопки статусов в группе кухни."""

    order_id: int
    to_status: str
