"""Общие фильтры и хелперы хендлеров."""

from __future__ import annotations

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import Message

from bot.config import Settings
from bot.i18n import SUPPORTED, I18n
from bot.services import money as money_service
from bot.services.rates import RateProvider
from bot.utils.format import money

#: Текст кнопки нижней клавиатуры -> ключ локали. Заполняется один раз на старте.
_MENU_INDEX: dict[str, str] = {}

#: Ключи, которые попадают на reply-клавиатуру и должны распознаваться на обоих языках.
MENU_KEYS = (
    "menu-catalog",
    "menu-cart",
    "menu-orders",
    "menu-contacts",
    "menu-language",
    "btn-cancel",
)


def build_menu_index(i18n: I18n) -> None:
    """Строит обратный индекс для reply-кнопок.

    Пользователь может переключить язык, когда старая клавиатура ещё висит у него на
    экране, поэтому распознаём подписи на всех языках сразу.
    """
    _MENU_INDEX.clear()
    for lang in SUPPORTED:
        for key in MENU_KEYS:
            _MENU_INDEX[i18n.get(lang, key)] = key


class MenuText(Filter):
    """Совпадение текста сообщения с кнопкой нижней клавиатуры по ключу локали."""

    def __init__(self, key: str) -> None:
        self.key = key

    async def __call__(self, message: Message) -> bool:
        return _MENU_INDEX.get((message.text or "").strip()) == self.key


def fmt_money(settings: Settings, amount: int) -> str:
    """Сумма в валюте меню. Используется там, где важна компактность: кнопки и строки."""
    return money(amount, settings.currency_symbol, settings.currency_minor)


def fmt_dual(settings: Settings, rates: RateProvider | None, amount: int) -> str:
    """Сумма в двух валютах. Используется для цен и итогов, на которые смотрят.

    Курс берётся из памяти и никогда не тянется из сети по ходу отрисовки, поэтому
    вызывать можно свободно.
    """
    return money_service.dual(settings, amount, money_service.live_rate(settings, rates))


async def replace(
    message: Message,
    text: str,
    *,
    reply_markup=None,
    photo: str | None = None,
) -> Message:
    """Заменяет сообщение новым, возможно другого типа.

    Карточка товара приходит с фотографией, а список категорий — текстом; ``edit_text``
    между ними невозможен, поэтому старое сообщение удаляется. Так навигация не оставляет
    за собой хвост из устаревших экранов.
    """
    # Сообщение старше 48 часов или уже удалено — не повод ронять хендлер.
    with suppress(TelegramBadRequest):
        await message.delete()
    if photo:
        return await message.answer_photo(photo, caption=text, reply_markup=reply_markup)
    return await message.answer(text, reply_markup=reply_markup)
