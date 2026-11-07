"""Регистрирует вебхук Telegram на адрес развёрнутого проекта.

Запуск (один раз после деплоя и при смене адреса или WEBHOOK_SECRET)::

    python -m scripts.set_webhook https://hotfast.vercel.app
"""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.__main__ import build_dispatcher
from bot.config import get_settings
from bot.i18n import I18n


async def main(base_url: str) -> None:
    settings = get_settings()
    if not settings.webhook_secret:
        sys.exit("WEBHOOK_SECRET не задан в .env — вебхук без секрета не регистрируем")

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(bot, settings, I18n(default_lang=settings.default_lang))
    try:
        await bot.set_webhook(
            url=f"{base_url.rstrip('/')}/webhook",
            secret_token=settings.webhook_secret,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        await bot.set_my_commands([BotCommand(command="start", description="Menu / القائمة")])
        info = await bot.get_webhook_info()
        print(f"Вебхук: {info.url}")
        print(f"Ожидают отправки: {info.pending_update_count}")
        if info.last_error_message:
            print(f"Последняя ошибка Telegram: {info.last_error_message}")
    finally:
        await dp["engine"].dispose()
        await bot.session.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Использование: python -m scripts.set_webhook https://<проект>.vercel.app")
    asyncio.run(main(sys.argv[1]))
