"""Минимум служебных команд для владельца.

Полноценной админки нет по решению из плана — меню правится в ``seed/menu.yaml``. Но две
вещи из файла сделать нельзя: приложить фотографию (у Telegram она существует только как
``file_id``) и быстро убрать блюдо из продажи в час пик. Эти две команды закрывают обе
дыры, не превращаясь в отдельный интерфейс.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from bot.config import Settings
from bot.db.models import Product
from bot.db.repo import Repos

router = Router(name="admin")


def _is_admin(message: Message, settings: Settings) -> bool:
    return message.from_user is not None and message.from_user.id in settings.admin_ids


@router.message(Command("photo"), F.reply_to_message)
async def set_photo(
    message: Message, command: CommandObject, repos: Repos, settings: Settings
) -> None:
    """``/photo <slug>`` в ответ на фотографию — привязывает картинку к товару."""
    if not _is_admin(message, settings):
        return
    if not command.args or not message.reply_to_message.photo:
        await message.reply("Ответьте на фото командой: /photo shawarma-chicken")
        return

    slug = command.args.strip()
    product = await repos.session.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        await message.reply(f"Товар со slug «{slug}» не найден.")
        return

    product.photo_file_id = message.reply_to_message.photo[-1].file_id
    await repos.session.flush()
    await message.reply(f"Фото для «{product.name_ru}» сохранено.")


@router.message(Command("stop"))
async def toggle_stop_list(
    message: Message, command: CommandObject, repos: Repos, settings: Settings
) -> None:
    """``/stop <slug>`` — переключает товар в стоп-листе и обратно."""
    if not _is_admin(message, settings):
        return
    if not command.args:
        await message.reply("Использование: /stop shawarma-beef")
        return

    slug = command.args.strip()
    product = await repos.session.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        await message.reply(f"Товар со slug «{slug}» не найден.")
        return

    product.is_active = not product.is_active
    await repos.session.flush()
    state = "в продаже" if product.is_active else "в стоп-листе"
    await message.reply(f"«{product.name_ru}» теперь {state}.")


@router.message(Command("stats"))
async def stats(message: Message, repos: Repos, settings: Settings) -> None:
    if not _is_admin(message, settings):
        return
    users = await repos.users.count()
    await message.reply(f"Пользователей: {users}")
