"""ASGI-приложение для Vercel: вебхук Telegram и суточные cron-задачи.

Вместо long polling и бесконечных циклов (``bot/__main__.py``) функция просыпается на
каждый запрос: Telegram присылает апдейт на ``/webhook``, а Vercel раз в сутки дёргает
``/cron/expire`` (отмена неоплаченных заказов) и ``/cron/rates`` (обновление курса).
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import sys
import time
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request

from bot.__main__ import build_dispatcher
from bot.config import Settings, get_settings
from bot.handlers.common import build_menu_index
from bot.i18n import I18n
from bot.services.expire import expire_unpaid_once
from bot.services.rate_sync import adopt_stored, sync_once

logger = logging.getLogger(__name__)

#: Как часто инстанс сверяется с базой: курс мог обновить cron на другом инстансе.
RATE_RELOAD_SEC = 300


@dataclass
class Runtime:
    bot: Bot
    dp: Dispatcher
    settings: Settings
    rates_checked_at: float = float("-inf")


_runtime: Runtime | None = None
_init_lock = asyncio.Lock()


async def get_runtime() -> Runtime:
    """Собирает бота один раз на инстанс, дальше переиспользует между запросами."""
    global _runtime
    if _runtime is None:
        async with _init_lock:
            if _runtime is None:
                settings = get_settings()
                logging.basicConfig(
                    level=settings.log_level.upper(),
                    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                    stream=sys.stdout,
                )
                if not settings.redis_url:
                    logger.warning(
                        "REDIS_URL не задан: на serverless состояние оформления "
                        "теряется между запросами"
                    )
                i18n = I18n(default_lang=settings.default_lang)
                build_menu_index(i18n)
                bot = Bot(
                    settings.bot_token,
                    default=DefaultBotProperties(
                        parse_mode=ParseMode.HTML, link_preview_is_disabled=True
                    ),
                )
                _runtime = Runtime(bot, build_dispatcher(bot, settings, i18n), settings)
    return _runtime


def _require_secret(expected: str, given: str, name: str) -> None:
    # Пустой секрет — не «без защиты», а ошибка настройки: эндпоинт закрыт наглухо.
    if not expected:
        raise HTTPException(503, f"{name} не задан")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(403, "Forbidden")


def _require_cron(rt: Runtime, authorization: str) -> None:
    # Vercel присылает «Authorization: Bearer <CRON_SECRET>», если переменная задана.
    secret = rt.settings.cron_secret
    _require_secret(f"Bearer {secret}" if secret else "", authorization, "CRON_SECRET")


async def _adopt_rate_if_due(rt: Runtime) -> None:
    now = time.monotonic()
    if now - rt.rates_checked_at < RATE_RELOAD_SEC:
        return
    rt.rates_checked_at = now
    try:
        await adopt_stored(rt.dp["rates"], rt.dp["sessionmaker"])
    except Exception:  # noqa: BLE001 — курс не должен ронять обработку заказа
        logger.exception("Не удалось подхватить курс из базы")


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    rt = await get_runtime()
    _require_secret(rt.settings.webhook_secret, x_telegram_bot_api_secret_token, "WEBHOOK_SECRET")

    update = Update.model_validate(await request.json(), context={"bot": rt.bot})
    await _adopt_rate_if_due(rt)
    try:
        await rt.dp.feed_update(rt.bot, update)
    except Exception:  # noqa: BLE001
        # Не-200 заставил бы Telegram слать тот же апдейт снова и снова.
        logger.exception("Ошибка обработки апдейта %s", update.update_id)
    return {"ok": True}


@app.get("/cron/expire")
async def cron_expire(authorization: str = Header(default="")) -> dict:
    rt = await get_runtime()
    _require_cron(rt, authorization)

    cancelled = await expire_unpaid_once(rt.dp["sessionmaker"], rt.dp["notifier"], rt.settings)
    logger.info("Отменено по таймауту оплаты: %d", cancelled)
    return {"cancelled": cancelled}


@app.get("/cron/rates")
async def cron_rates(authorization: str = Header(default="")) -> dict:
    rt = await get_runtime()
    _require_cron(rt, authorization)

    provider = rt.dp["rates"]
    if not provider.enabled:
        return {"updated": False, "reason": "second currency disabled"}
    return {"updated": await sync_once(provider, rt.dp["sessionmaker"])}
