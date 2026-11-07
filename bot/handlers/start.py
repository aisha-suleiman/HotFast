"""Старт, выбор языка, главное меню и контакты."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db.enums import Lang
from bot.db.models import User
from bot.db.repo import Repos
from bot.handlers.common import MenuText
from bot.i18n import I18n, Translator
from bot.keyboards.callbacks import LangCB
from bot.keyboards.client import language_kb, main_menu_kb
from bot.services.schedule import format_hours
from bot.utils.format import rtl

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    user: User,
    i18n: Translator,
    is_new_user: bool = False,
) -> None:
    await state.clear()
    if is_new_user:
        # Первый экран — выбор языка: до него пользователь ещё ничего не понял на чужом.
        await message.answer(i18n("choose-language"), reply_markup=language_kb())
        return
    await _greet(message, i18n)


@router.callback_query(LangCB.filter(), F.message.chat.type == ChatType.PRIVATE)
async def set_language(
    callback: CallbackQuery,
    callback_data: LangCB,
    repos: Repos,
    user: User,
    i18n_hub: I18n,
) -> None:
    await repos.users.set_lang(user, Lang(callback_data.lang))
    i18n = i18n_hub.translator(callback_data.lang)

    await callback.message.edit_text(i18n("language-set"))
    await _greet(callback.message, i18n)
    await callback.answer()


@router.message(MenuText("menu-language"), F.chat.type == ChatType.PRIVATE)
async def change_language(message: Message, i18n: Translator) -> None:
    await message.answer(i18n("choose-language"), reply_markup=language_kb())


@router.message(MenuText("menu-contacts"), F.chat.type == ChatType.PRIVATE)
async def contacts(
    message: Message, repos: Repos, i18n: Translator, settings: Settings
) -> None:
    branch = await repos.menu.default_branch()
    text = i18n(
        "contacts",
        support=settings.support_contact or "—",
        hours=format_hours(*settings.hours),
        address=branch.address(i18n.lang) if branch else "—",
    )
    await message.answer(rtl(text, is_rtl=i18n.is_rtl))


@router.message(Command("chatid"))
async def chat_id(message: Message, i18n: Translator) -> None:
    """Помогает при настройке: показывает id чата, чтобы вписать его в ADMIN_GROUP_ID."""
    await message.answer(i18n("kitchen-chat-id", chat_id=message.chat.id))


@router.callback_query(F.data == "nv:noop")
async def noop(callback: CallbackQuery) -> None:
    """Кнопки-заголовки и счётчики: нажатие не должно оставлять «часики»."""
    await callback.answer()


async def _greet(message: Message, i18n: Translator) -> None:
    await message.answer(
        rtl(i18n("welcome"), is_rtl=i18n.is_rtl), reply_markup=main_menu_kb(i18n)
    )
