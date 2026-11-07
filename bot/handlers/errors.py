"""Глобальный обработчик ошибок.

Клиент не должен видеть пустой экран после нажатия кнопки: любое необработанное
исключение превращается в понятное сообщение, а полный traceback уходит в лог.
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ErrorEvent

from bot.config import Settings
from bot.i18n import I18n

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent, settings: Settings, i18n_hub: I18n) -> bool:
    exception = event.exception

    if isinstance(exception, TelegramForbiddenError):
        logger.info("Бот заблокирован пользователем: %s", exception)
        return True
    if isinstance(exception, TelegramBadRequest) and "not modified" in str(exception):
        return True

    logger.exception("Необработанная ошибка в апдейте %s", event.update.update_id)

    text = i18n_hub.get(settings.default_lang, "error-generic", support=settings.support_contact)
    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(text, show_alert=True)
        elif update.message is not None:
            await update.message.answer(text)
    except Exception:  # noqa: BLE001 — сообщить об ошибке тоже не удалось
        logger.exception("Не удалось уведомить пользователя об ошибке")
    return True
