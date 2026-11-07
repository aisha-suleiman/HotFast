"""Точка входа: сборка Dispatcher и запуск long polling."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, User

from bot.config import Settings, get_settings
from bot.db.session import make_engine, make_sessionmaker
from bot.handlers import (
    admin,
    cart,
    catalog,
    checkout,
    errors,
    kitchen,
    payment,
    profile,
    start,
)
from bot.handlers.common import build_menu_index
from bot.i18n import I18n
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.stale_callback import StaleCallbackMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user import UserMiddleware
from bot.services.expire import expire_unpaid_loop
from bot.services.notifier import Notifier
from bot.services.rate_sync import rates_loop, warm_up
from bot.services.rates import RateProvider
from bot.services.watchdog import session_watchdog

logger = logging.getLogger(__name__)


def make_storage(settings: Settings) -> BaseStorage:
    """Redis в проде, память в разработке.

    Без Redis состояние оформления теряется при перезапуске: клиент, дошедший до выбора
    оплаты, окажется в пустоте. Для боевого запуска REDIS_URL обязателен.
    """
    if not settings.redis_url:
        logger.warning("REDIS_URL не задан: состояние оформления не переживёт рестарт")
        return MemoryStorage()

    from aiogram.fsm.storage.redis import RedisStorage

    return RedisStorage.from_url(settings.redis_url)


def build_dispatcher(bot: Bot, settings: Settings, i18n: I18n) -> Dispatcher:
    engine = make_engine(settings.db_url, serverless=settings.vercel)
    sessionmaker = make_sessionmaker(engine)
    notifier = Notifier(bot, settings, i18n)

    dp = Dispatcher(storage=make_storage(settings))
    dp["settings"] = settings
    dp["i18n_hub"] = i18n
    dp["notifier"] = notifier
    dp["rates"] = RateProvider(settings)
    dp["sessionmaker"] = sessionmaker
    dp["engine"] = engine

    # Порядок важен: UserMiddleware берёт репозитории, созданные DbSessionMiddleware.
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.update.outer_middleware(
        UserMiddleware(i18n, settings.default_lang, settings.admin_group_id)
    )
    dp.callback_query.middleware(ThrottlingMiddleware())
    # Внутри транзакции: протухшая кнопка не должна откатывать сделанную работу.
    dp.callback_query.middleware(StaleCallbackMiddleware())

    dp.include_router(errors.router)
    dp.include_router(kitchen.router)
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(checkout.router)
    dp.include_router(profile.router)
    # Приём чека ловит свободный текст и фото, поэтому подключается последним.
    dp.include_router(payment.router)

    return dp


def use_system_certificates() -> None:
    """Проверять TLS по хранилищу сертификатов операционной системы.

    На Windows связка Python + certifi часто не может достроить цепочку до
    api.telegram.org: промежуточный сертификат подтягивается системой на лету, а Python
    так не умеет и падает с ``CERTIFICATE_VERIFY_FAILED``. То же бывает при антивирусе,
    который подменяет сертификаты своим корневым.

    ``truststore`` отдаёт проверку системе — она умеет и то, и другое. Проверка остаётся
    полной: это не отключение TLS, а смена источника доверенных корней.
    """
    try:
        import truststore
    except ModuleNotFoundError:
        logger.debug("truststore не установлен — проверка TLS по certifi")
        return
    truststore.inject_into_ssl()


#: Сколько раз пробуем достучаться до Telegram на старте и с какой паузой.
#: Первое соединение через VPN или мобильный интернет часто не успевает установиться,
#: а следующее проходит мгновенно — падать из-за этого нельзя.
CONNECT_ATTEMPTS = 5
CONNECT_DELAY_SEC = 3


async def connect(bot: Bot) -> User | None:
    """Дожидается ответа Telegram. None — связи нет, но это не приговор.

    Неверный токен пробрасывается наружу: сколько ни повторяй, он не станет верным.
    """
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            return await bot.get_me()
        except TelegramUnauthorizedError:
            raise
        except (TelegramNetworkError, TimeoutError) as exc:
            logger.warning(
                "Telegram не ответил (попытка %d из %d): %s", attempt, CONNECT_ATTEMPTS, exc
            )
            if attempt < CONNECT_ATTEMPTS:
                await asyncio.sleep(CONNECT_DELAY_SEC)
    return None


async def on_startup(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands([BotCommand(command="start", description="Menu / القائمة")])
    try:
        chat = await bot.get_chat(settings.admin_group_id)
        logger.info("Группа кухни: %s (%s)", chat.title, chat.id)
        if chat.type == ChatType.GROUP:
            # Обычная группа превращается в супергруппу при первой же смене настроек —
            # и её id при этом меняется. Заказы начнут уходить в никуда, а понять почему
            # без этой подсказки трудно.
            logger.warning(
                "Это обычная группа, а не супергруппа: Telegram сменит её id при первом "
                "изменении настроек. Сделайте бота администратором, снова отправьте "
                "/chatid и впишите новый ADMIN_GROUP_ID."
            )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Бот не видит группу кухни ADMIN_GROUP_ID=%s (%s). "
            "Добавьте бота в группу и дайте право писать сообщения.",
            settings.admin_group_id,
            exc,
        )


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    use_system_certificates()

    i18n = I18n(default_lang=settings.default_lang)
    build_menu_index(i18n)

    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML, link_preview_is_disabled=True
        ),
    )
    dp = build_dispatcher(bot, settings, i18n)

    try:
        me = await connect(bot)
    except TelegramUnauthorizedError:
        # Единственная ошибка, при которой продолжать бессмысленно.
        logger.error(
            "Telegram отклонил BOT_TOKEN. Проверьте значение в .env — токен выдаёт "
            "@BotFather командой /mybots -> API Token."
        )
        await bot.session.close()
        return

    if me is None:
        logger.warning(
            "Связаться с Telegram пока не удалось. Бот продолжит попытки сам — "
            "проверьте интернет или VPN, перезапускать не нужно."
        )
    else:
        logger.info("Бот @%s подключён", me.username)
        await on_startup(bot, settings)

    # Курс поднимаем до старта опроса: первый же клиент должен увидеть вторую цену.
    await warm_up(dp["rates"], dp["sessionmaker"])

    tasks = [
        # Сторож чинит зависшее после обрыва сети соединение: без него бот молчит,
        # даже когда интернет вернулся.
        asyncio.create_task(session_watchdog(bot)),
        asyncio.create_task(expire_unpaid_loop(dp["sessionmaker"], dp["notifier"], settings)),
        asyncio.create_task(rates_loop(dp["rates"], dp["sessionmaker"])),
    ]
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        for task in tasks:
            task.cancel()
        await dp["engine"].dispose()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановлено")
