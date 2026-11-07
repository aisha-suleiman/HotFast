"""Корзина: просмотр, изменение количества, очистка, переход к оформлению."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db.models import User
from bot.db.repo import Repos
from bot.handlers.checkout import start_checkout
from bot.handlers.common import MenuText, fmt_dual, fmt_money, replace
from bot.i18n import Translator
from bot.keyboards.callbacks import CartCB
from bot.keyboards.client import cart_kb
from bot.services import cart as cart_service
from bot.services.cart import CartView
from bot.services.rates import RateProvider
from bot.utils.format import escape_html, rtl

router = Router(name="cart")

# Клиентские сценарии живут только в личке. В группе кухни «клиента» нет — там у
# хендлеров не будет ни пользователя, ни его языка, и любое нажатие роняло бы бота.
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)


@router.message(MenuText("menu-cart"))
async def show_cart_message(
    message: Message,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    view = await _clean_view(message, repos, i18n, user)
    if view.is_empty:
        await message.answer(i18n("cart-empty"))
        return
    await message.answer(
        _render(view, i18n, user, settings, rates),
        reply_markup=cart_kb(view.items, i18n, user.lang.value),
    )


@router.callback_query(CartCB.filter())
async def cart_actions(
    callback: CallbackQuery,
    callback_data: CartCB,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> None:
    action = callback_data.action

    if action == "checkout":
        await start_checkout(callback, state, repos, i18n, user, settings)
        return

    if action == "clear":
        await repos.cart.clear(user.tg_id)
        await replace(callback.message, i18n("cart-cleared"))
        await callback.answer()
        return

    if action in ("inc", "dec", "del"):
        item = await repos.cart.get_item(callback_data.item_id, user.tg_id)
        if item is None:
            await callback.answer(i18n("error-stale-button"))
        elif action == "del":
            await repos.cart.remove(item)
        else:
            await repos.cart.change_qty(item, 1 if action == "inc" else -1)

    view = await _clean_view(callback.message, repos, i18n, user)
    if view.is_empty:
        await replace(callback.message, i18n("cart-empty"))
        await callback.answer()
        return

    text = _render(view, i18n, user, settings, rates)
    markup = cart_kb(view.items, i18n, user.lang.value)

    if action == "show":
        # Приходим сюда с экрана «добавлено», а он может быть и фотографией товара:
        # редактировать текст в нём нельзя, только заменить сообщение целиком.
        await replace(callback.message, text, reply_markup=markup)
    else:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


async def _clean_view(
    message: Message, repos: Repos, i18n: Translator, user: User
) -> CartView:
    """Загружает корзину и выбрасывает из неё то, что уехало в стоп-лист.

    Проверять это только при оформлении поздно: клиент успеет посчитать сумму с блюдом,
    которого уже нет.
    """
    view = await cart_service.load_cart(repos, user.tg_id)
    if view.unavailable:
        names = ", ".join(i.product.name(user.lang.value) for i in view.unavailable)
        await cart_service.drop_unavailable(repos, view)
        await message.answer(i18n("cart-unavailable-removed", names=escape_html(names)))
        view = await cart_service.load_cart(repos, user.tg_id)
    return view


def _render(
    view: CartView,
    i18n: Translator,
    user: User,
    settings: Settings,
    rates: RateProvider,
) -> str:
    lang = user.lang.value
    lines = [i18n("cart-title")]
    for index, item in enumerate(view.items, start=1):
        options = cart_service.options_text(item, lang)
        lines.append(
            i18n(
                "cart-line",
                index=index,
                name=escape_html(item.product.name(lang)),
                options=f" ({escape_html(options)})" if options else "",
                qty=item.qty,
                price=fmt_money(settings, item.unit_price),
                total=fmt_money(settings, item.line_total),
            )
        )
    lines.append("")
    lines.append(i18n("cart-subtotal", subtotal=fmt_dual(settings, rates, view.subtotal)))
    return rtl("\n".join(lines), is_rtl=i18n.is_rtl)
