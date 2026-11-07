"""Каталог: категории, страницы товаров, карточка товара с опциями."""

from __future__ import annotations

from functools import partial

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db.models import Product, User
from bot.db.repo import Repos
from bot.handlers.common import MenuText, fmt_dual, fmt_money, replace
from bot.i18n import Translator
from bot.keyboards.callbacks import CatalogCB, ProductCB
from bot.keyboards.client import (
    PAGE_SIZE,
    added_to_cart_kb,
    categories_kb,
    product_card_kb,
    quick_menu_kb,
)
from bot.services import cart as cart_service
from bot.services import menu as menu_service
from bot.services.rates import RateProvider
from bot.utils.format import escape_html, rtl

router = Router(name="catalog")

# Клиентские сценарии живут только в личке. В группе кухни «клиента» нет — там у
# хендлеров не будет ни пользователя, ни его языка, и любое нажатие роняло бы бота.
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

#: Состояние открытой карточки живёт в FSM: одна карточка на пользователя за раз.
CARD_KEY = "card"


@router.message(MenuText("menu-catalog"))
async def show_menu_message(
    message: Message,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    categories = await repos.menu.categories()
    if not categories:
        await message.answer(i18n("catalog-empty"))
        return

    if len(categories) > 1:
        await message.answer(
            i18n("catalog-title"), reply_markup=categories_kb(categories, user.lang.value)
        )
        return

    text, markup = await _menu_screen(repos, i18n, user, settings, rates, categories[0].id)
    await message.answer(text, reply_markup=markup)


async def _menu_screen(
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
    category_id: int,
):
    """Экран меню: все блюда сразу, у каждого свой счётчик.

    Один экран вместо цепочки «список -> карточка -> подтверждение -> назад»: чтобы взять
    и шаурму, и донер, ходить между экранами больше не нужно.
    """
    products, _ = await repos.menu.products_page(category_id, offset=0, limit=PAGE_SIZE)
    if not products:
        return i18n("category-empty"), None

    detailed = [await repos.menu.get_product(p.id) for p in products]
    variants = menu_service.variants_of([p for p in detailed if p is not None])

    view = await cart_service.load_cart(repos, user.tg_id)
    counts = menu_service.cart_counts(view.items)

    lines = [i18n("menu-pick"), ""]
    for product in detailed:
        if product is None:
            continue
        desc = product.desc(user.lang.value)
        if desc:
            lines.append(
                i18n(
                    "menu-dish",
                    name=escape_html(product.name(user.lang.value)),
                    desc=escape_html(desc),
                )
            )
    text = rtl("\n".join(lines).strip(), is_rtl=i18n.is_rtl)
    markup = quick_menu_kb(
        variants,
        counts,
        lang=user.lang.value,
        i18n=i18n,
        price_of=partial(fmt_money, settings),
        cart_total=fmt_dual(settings, rates, view.subtotal) if not view.is_empty else None,
    )
    return text, markup


@router.callback_query(CatalogCB.filter())
async def catalog_nav(
    callback: CallbackQuery,
    callback_data: CatalogCB,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    if callback_data.action == "list":
        categories = await repos.menu.categories()
        await replace(
            callback.message,
            i18n("catalog-title"),
            reply_markup=categories_kb(categories, user.lang.value),
        )
        await callback.answer()
        return

    text, markup = await _menu_screen(
        repos, i18n, user, settings, rates, callback_data.category_id
    )
    await replace(callback.message, text, reply_markup=markup)
    await callback.answer()


@router.callback_query(ProductCB.filter())
async def product_actions(
    callback: CallbackQuery,
    callback_data: ProductCB,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    product = await repos.menu.get_product(callback_data.product_id)
    if product is None or not product.is_active:
        await callback.answer(i18n("product-unavailable", name="—"), show_alert=True)
        return

    action = callback_data.action

    if action in ("qinc", "qdec"):
        await _change_from_menu(
            callback, callback_data, repos, i18n, user, settings, rates, product
        )
        return

    card = await _load_card(state, product, callback_data.product_id)

    if action == "inc":
        card["qty"] = min(card["qty"] + 1, 50)
    elif action == "dec":
        card["qty"] = max(card["qty"] - 1, 1)
    elif action == "opt":
        card["opts"] = sorted(
            cart_service.toggle_option(product, set(card["opts"]), callback_data.opt_id)
        )
    elif action == "add":
        await _add_to_cart(
            callback, repos, product, card, i18n, user, settings, rates,
            page=callback_data.page,
        )
        await state.update_data({CARD_KEY: None})
        return

    await state.update_data({CARD_KEY: card})
    await _render_card(
        callback, product, card, i18n, user, settings, rates,
        page=callback_data.page,
        edit=action != "open",
    )
    await callback.answer()


async def _change_from_menu(
    callback: CallbackQuery,
    callback_data: ProductCB,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
    product: Product,
) -> None:
    """Плюс и минус прямо на странице меню: правят корзину и перерисовывают экран."""
    option_ids = [callback_data.opt_id] if callback_data.opt_id else []
    item = await repos.cart.find(user.tg_id, product.id, option_ids)

    if callback_data.action == "qinc":
        if item is None:
            options = cart_service.options_of(product, set(option_ids))
            await repos.cart.add(
                user.tg_id,
                product_id=product.id,
                qty=1,
                option_ids=option_ids,
                unit_price=cart_service.price_with_options(product, options),
            )
        else:
            await repos.cart.change_qty(item, 1)
    elif item is not None:
        await repos.cart.change_qty(item, -1)

    text, markup = await _menu_screen(
        repos, i18n, user, settings, rates, product.category_id
    )
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


async def _load_card(state: FSMContext, product: Product, product_id: int) -> dict:
    data = await state.get_data()
    card = data.get(CARD_KEY)
    if not card or card.get("pid") != product_id:
        card = {
            "pid": product_id,
            "qty": 1,
            "opts": sorted(cart_service.default_selection(product)),
        }
    return card


async def _add_to_cart(
    callback: CallbackQuery,
    repos: Repos,
    product: Product,
    card: dict,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
    *,
    page: int,
) -> None:
    selected = set(card["opts"])
    bad_group = cart_service.validate_selection(product, selected)
    if bad_group is not None:
        await callback.answer(
            i18n("option-group-required", group=bad_group.name(user.lang.value)),
            show_alert=True,
        )
        return

    options = cart_service.options_of(product, selected)
    await repos.cart.add(
        user.tg_id,
        product_id=product.id,
        qty=card["qty"],
        option_ids=sorted(selected),
        unit_price=cart_service.price_with_options(product, options),
    )
    await callback.answer(
        i18n("cart-added", name=product.name(user.lang.value), qty=card["qty"])
    )

    # Карточку заменяем итогом, а не перерисовываем со сброшенным счётчиком: набранное
    # количество должно остаться на виду, иначе «3» превращается в «1» и выглядит сбоем.
    view = await cart_service.load_cart(repos, user.tg_id)
    text = i18n(
        "cart-added-title",
        name=escape_html(product.name(user.lang.value)),
        qty=card["qty"],
    )
    await replace(
        callback.message,
        rtl(text, is_rtl=i18n.is_rtl),
        reply_markup=added_to_cart_kb(
            i18n,
            category_id=product.category_id,
            page=page,
            total=fmt_dual(settings, rates, view.subtotal),
        ),
    )


async def _render_card(
    callback: CallbackQuery,
    product: Product,
    card: dict,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
    *,
    page: int,
    edit: bool,
) -> None:
    lang = user.lang.value
    selected = set(card["opts"])
    options = cart_service.options_of(product, selected)
    unit = cart_service.price_with_options(product, options)

    text = i18n(
        "product-card",
        name=escape_html(product.name(lang)),
        desc=escape_html(product.desc(lang) or ""),
    )
    text += "\n" + i18n("product-price-line", price=fmt_dual(settings, rates, unit))
    text = rtl(text, is_rtl=i18n.is_rtl)

    markup = product_card_kb(
        product,
        selected=selected,
        qty=card["qty"],
        page=page,
        lang=lang,
        i18n=i18n,
        add_price=fmt_money(settings, unit * card["qty"]),
        price_of=partial(fmt_money, settings),
    )

    if edit and callback.message.photo and product.photo_file_id:
        await callback.message.edit_caption(caption=text, reply_markup=markup)
    elif edit and not callback.message.photo and not product.photo_file_id:
        await callback.message.edit_text(text, reply_markup=markup)
    else:
        # Тип сообщения меняется (текст ↔ фото) — редактировать нельзя, только заменить.
        await replace(
            callback.message, text, reply_markup=markup, photo=product.photo_file_id
        )
