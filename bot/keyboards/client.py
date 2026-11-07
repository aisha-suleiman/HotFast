"""Клавиатуры клиентской части."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.db.models import Branch, Category, Order, Product
from bot.i18n import Translator
from bot.keyboards.callbacks import (
    CartCB,
    CatalogCB,
    CheckoutCB,
    LangCB,
    NavCB,
    OrderCB,
    ProductCB,
)

#: Сколько товаров показываем на одной странице списка.
PAGE_SIZE = 8


def language_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇸🇾 العربية", callback_data=LangCB(lang="ar"))
    builder.button(text="🇷🇺 Русский", callback_data=LangCB(lang="ru"))
    builder.adjust(2)
    return builder.as_markup()


def main_menu_kb(i18n: Translator) -> ReplyKeyboardMarkup:
    """Постоянная клавиатура снизу: до меню и корзины всегда один тап."""
    builder = ReplyKeyboardBuilder()
    for key in ("menu-catalog", "menu-cart", "menu-orders", "menu-contacts", "menu-language"):
        builder.add(KeyboardButton(text=i18n(key)))
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def categories_kb(categories: list[Category], lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        label = f"{category.emoji} {category.name(lang)}" if category.emoji else category.name(lang)
        builder.button(text=label, callback_data=CatalogCB(action="open", category_id=category.id))
    builder.adjust(2)
    return builder.as_markup()


def products_kb(
    products: list[Product],
    *,
    category_id: int,
    page: int,
    total: int,
    lang: str,
    i18n: Translator,
    price_of,
    show_back: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.button(
            text=f"{product.name(lang)} · {price_of(product.price)}",
            callback_data=ProductCB(action="open", product_id=product.id, page=page),
        )
    builder.adjust(1)

    pages = max(1, -(-total // PAGE_SIZE))
    if pages > 1:
        nav = [
            InlineKeyboardButton(
                text="‹",
                callback_data=CatalogCB(
                    action="open", category_id=category_id, page=(page - 1) % pages
                ).pack(),
            ),
            InlineKeyboardButton(
                text=i18n("page-of", page=page + 1, pages=pages),
                callback_data=NavCB(to="noop").pack(),
            ),
            InlineKeyboardButton(
                text="›",
                callback_data=CatalogCB(
                    action="open", category_id=category_id, page=(page + 1) % pages
                ).pack(),
            ),
        ]
        builder.row(*nav)

    if show_back:
        builder.row(
            InlineKeyboardButton(
                text=i18n("btn-back"), callback_data=CatalogCB(action="list").pack()
            )
        )
    return builder.as_markup()


def quick_menu_kb(
    variants,
    counts: dict,
    *,
    lang: str,
    i18n: Translator,
    price_of,
    cart_total: str | None,
) -> InlineKeyboardMarkup:
    """Всё меню одним экраном: каждая позиция со своим счётчиком.

    Пока позиции нет в корзине, показываем одну широкую кнопку — нажатие добавляет штуку.
    Как только количество больше нуля, рядом появляются «минус» и «плюс». Так экран не
    рябит от кнопок, пока клиент ещё ничего не выбрал.
    """
    builder = InlineKeyboardBuilder()

    for variant in variants:
        label = f"{variant.name(lang)} · {price_of(variant.price)}"
        opt_id = variant.option.id if variant.option else 0

        if variant.needs_card:
            # Сложные опции одной кнопкой не выбрать — отправляем в карточку товара.
            builder.row(
                InlineKeyboardButton(
                    text=label,
                    callback_data=ProductCB(
                        action="open", product_id=variant.product.id
                    ).pack(),
                )
            )
            continue

        qty = counts.get(variant.key, 0)
        add = InlineKeyboardButton(
            text=f"{label} · ×{qty}" if qty else label,
            callback_data=ProductCB(
                action="qinc", product_id=variant.product.id, opt_id=opt_id
            ).pack(),
        )
        if not qty:
            builder.row(add)
            continue

        builder.row(
            InlineKeyboardButton(
                text="➖",
                callback_data=ProductCB(
                    action="qdec", product_id=variant.product.id, opt_id=opt_id
                ).pack(),
            ),
            add,
            InlineKeyboardButton(
                text="➕",
                callback_data=ProductCB(
                    action="qinc", product_id=variant.product.id, opt_id=opt_id
                ).pack(),
            ),
        )

    if cart_total is not None:
        builder.row(
            InlineKeyboardButton(
                text=i18n("btn-go-to-cart", total=cart_total),
                callback_data=CartCB(action="show").pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=i18n("btn-checkout"), callback_data=CartCB(action="checkout").pack()
            )
        )
    return builder.as_markup()


def product_card_kb(
    product: Product,
    *,
    selected: set[int],
    qty: int,
    page: int,
    lang: str,
    i18n: Translator,
    add_price: str,
    price_of,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for group in product.option_groups:
        options = [o for o in group.options if o.is_active]
        if not options:
            continue
        builder.row(
            InlineKeyboardButton(
                text=f"— {group.name(lang)} —", callback_data=NavCB(to="noop").pack()
            )
        )
        row: list[InlineKeyboardButton] = []
        for option in options:
            mark = "✅" if option.id in selected else "▫️"
            extra = f" +{price_of(option.price_delta)}" if option.price_delta else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{mark} {option.name(lang)}{extra}",
                    callback_data=ProductCB(
                        action="opt", product_id=product.id, opt_id=option.id, page=page
                    ).pack(),
                )
            )
        # По две опции в ряд: длинные названия иначе обрезаются.
        for i in range(0, len(row), 2):
            builder.row(*row[i : i + 2])

    builder.row(
        InlineKeyboardButton(
            text="➖",
            callback_data=ProductCB(action="dec", product_id=product.id, page=page).pack(),
        ),
        InlineKeyboardButton(text=str(qty), callback_data=NavCB(to="noop").pack()),
        InlineKeyboardButton(
            text="➕",
            callback_data=ProductCB(action="inc", product_id=product.id, page=page).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=i18n("btn-add-to-cart", price=add_price),
            callback_data=ProductCB(action="add", product_id=product.id, page=page).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=i18n("btn-back"),
            callback_data=CatalogCB(
                action="open", category_id=product.category_id, page=page
            ).pack(),
        )
    )
    return builder.as_markup()


def added_to_cart_kb(
    i18n: Translator, *, category_id: int, page: int, total: str
) -> InlineKeyboardMarkup:
    """Экран после добавления в корзину.

    Раньше карточка просто перерисовывалась со сброшенным на единицу счётчиком, и это
    читалось как «количество уменьшилось»: набрал три, нажал — стало один. Человек жал
    второй раз и добавлял лишнее. Теперь вместо счётчика показан итог и два очевидных
    выхода: в корзину или выбрать ещё.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n("btn-go-to-cart", total=total),
        callback_data=CartCB(action="show"),
    )
    builder.button(
        text=i18n("btn-continue-shopping"),
        callback_data=CatalogCB(action="open", category_id=category_id, page=page),
    )
    builder.adjust(1)
    return builder.as_markup()


def cart_kb(items, i18n: Translator, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, item in enumerate(items, start=1):
        builder.row(
            InlineKeyboardButton(
                text=f"{index}. {item.product.name(lang)}",
                callback_data=NavCB(to="noop").pack(),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="➖", callback_data=CartCB(action="dec", item_id=item.id).pack()
            ),
            InlineKeyboardButton(
                text=str(item.qty), callback_data=NavCB(to="noop").pack()
            ),
            InlineKeyboardButton(
                text="➕", callback_data=CartCB(action="inc", item_id=item.id).pack()
            ),
            InlineKeyboardButton(
                text="🗑", callback_data=CartCB(action="del", item_id=item.id).pack()
            ),
        )

    builder.row(
        InlineKeyboardButton(
            text=i18n("btn-checkout"), callback_data=CartCB(action="checkout").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=i18n("btn-clear-cart"), callback_data=CartCB(action="clear").pack()
        ),
        InlineKeyboardButton(
            text=i18n("menu-catalog"), callback_data=CatalogCB(action="list").pack()
        ),
    )
    return builder.as_markup()


def fulfillment_kb(i18n: Translator) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n("btn-delivery"), callback_data=CheckoutCB(step="fulfillment", value="delivery")
    )
    builder.button(
        text=i18n("btn-pickup"), callback_data=CheckoutCB(step="fulfillment", value="pickup")
    )
    builder.button(text=i18n("btn-cancel"), callback_data=CheckoutCB(step="cancel"))
    builder.adjust(2, 1)
    return builder.as_markup()


def branches_kb(branches: list[Branch], lang: str, i18n: Translator) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for branch in branches:
        builder.button(
            text=f"{branch.name(lang)} — {branch.address(lang)}",
            callback_data=CheckoutCB(step="branch", value=str(branch.id)),
        )
    builder.button(text=i18n("btn-cancel"), callback_data=CheckoutCB(step="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def payment_kb(i18n: Translator, *, shamcash_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n("btn-pay-cash"), callback_data=CheckoutCB(step="payment", value="cash")
    )
    if shamcash_enabled:
        builder.button(
            text=i18n("btn-pay-shamcash"),
            callback_data=CheckoutCB(step="payment", value="shamcash"),
        )
    builder.button(text=i18n("btn-cancel"), callback_data=CheckoutCB(step="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def location_kb(i18n: Translator) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=i18n("btn-send-location"), request_location=True))
    builder.add(KeyboardButton(text=i18n("btn-cancel")))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def contact_kb(i18n: Translator, username: str | None) -> InlineKeyboardMarkup:
    """Подтверждение контакта вместо запроса телефона.

    Телефон не спрашиваем: связь с клиентом идёт через Telegram. На кнопке показываем
    сам ``@username``, чтобы клиент видел, по какому аккаунту с ним свяжутся, — а если
    имени пользователя нет, зовём кухню писать в чат по имени.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text=(
            i18n("btn-send-username", username=username)
            if username
            else i18n("btn-contact-telegram")
        ),
        callback_data=CheckoutCB(step="contact"),
    )
    builder.button(text=i18n("btn-cancel"), callback_data=CheckoutCB(step="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def comment_kb(i18n: Translator) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn-skip"), callback_data=CheckoutCB(step="comment_skip"))
    builder.button(text=i18n("btn-cancel"), callback_data=CheckoutCB(step="cancel"))
    builder.adjust(2)
    return builder.as_markup()


def confirm_kb(i18n: Translator) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n("btn-confirm-order"), callback_data=CheckoutCB(step="confirm"))
    builder.button(text=i18n("btn-cancel"), callback_data=CheckoutCB(step="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def orders_kb(orders: list[Order], i18n: Translator) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        builder.button(
            text=i18n("btn-repeat-order", no=order.public_no),
            callback_data=OrderCB(action="repeat", order_id=order.id),
        )
    builder.adjust(1)
    return builder.as_markup()
