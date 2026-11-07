"""Веб-слой для Vercel: защита эндпоинтов, передача апдейтов диспетчеру, cron-задачи."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aiogram import Bot
from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

from bot import web
from bot.db.session import make_engine
from bot.services.rates import Rate, RateProvider
from tests.test_order_flow import make_settings

WEBHOOK_SECRET = "hook-secret"
CRON_SECRET = "cron-secret"


class StubDispatcher(dict):
    """Настоящий Dispatcher привязывает роутеры-синглтоны, второй раз его не собрать."""

    def __init__(self) -> None:
        super().__init__(sessionmaker=object(), notifier=object())
        self.updates: list = []
        self.fail = False

    async def feed_update(self, bot, update) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.updates.append(update)


@pytest.fixture
def dp() -> StubDispatcher:
    dispatcher = StubDispatcher()
    dispatcher["rates"] = RateProvider(make_settings(secondary_currency="USD"))
    return dispatcher


@pytest.fixture
def client(dp, monkeypatch):
    settings = make_settings(webhook_secret=WEBHOOK_SECRET, cron_secret=CRON_SECRET)
    monkeypatch.setattr(web, "_runtime", web.Runtime(Bot("123:test"), dp, settings))

    async def no_db(provider, sessionmaker):
        return None

    monkeypatch.setattr(web, "adopt_stored", no_db)
    with TestClient(web.app) as c:
        yield c


def _hook(client, secret: str | None, update_id: int = 7):
    headers = {} if secret is None else {"X-Telegram-Bot-Api-Secret-Token": secret}
    return client.post("/webhook", json={"update_id": update_id}, headers=headers)


def test_webhook_feeds_update_to_dispatcher(client, dp):
    response = _hook(client, WEBHOOK_SECRET)

    assert response.status_code == 200
    assert [u.update_id for u in dp.updates] == [7]


@pytest.mark.parametrize("secret", [None, "", "wrong"])
def test_webhook_rejects_bad_secret(client, dp, secret):
    assert _hook(client, secret).status_code == 403
    assert dp.updates == []


def test_webhook_closed_when_secret_not_configured(dp, monkeypatch):
    settings = make_settings(webhook_secret="")
    monkeypatch.setattr(web, "_runtime", web.Runtime(Bot("123:test"), dp, settings))
    with TestClient(web.app) as c:
        assert _hook(c, "").status_code == 503
    assert dp.updates == []


def test_webhook_answers_200_even_when_handler_fails(client, dp):
    """Не-200 заставил бы Telegram слать тот же апдейт снова и снова."""
    dp.fail = True
    assert _hook(client, WEBHOOK_SECRET).status_code == 200


def test_cron_requires_bearer_secret(client):
    assert client.get("/cron/expire").status_code == 403
    assert client.get("/cron/expire", headers={"Authorization": "Bearer nope"}).status_code == 403
    assert client.get("/cron/rates").status_code == 403


def test_cron_closed_when_secret_not_configured(dp, monkeypatch):
    settings = make_settings(cron_secret="")
    monkeypatch.setattr(web, "_runtime", web.Runtime(Bot("123:test"), dp, settings))
    with TestClient(web.app) as c:
        assert c.get("/cron/expire", headers={"Authorization": "Bearer "}).status_code == 503


def test_cron_expire_reports_cancelled_count(client, monkeypatch):
    async def fake_expire(sessionmaker, notifier, settings):
        return 3

    monkeypatch.setattr(web, "expire_unpaid_once", fake_expire)
    response = client.get("/cron/expire", headers={"Authorization": f"Bearer {CRON_SECRET}"})

    assert response.status_code == 200
    assert response.json() == {"cancelled": 3}


def test_cron_rates_refreshes_rate(client, monkeypatch):
    async def fake_sync(provider, sessionmaker):
        return True

    monkeypatch.setattr(web, "sync_once", fake_sync)
    response = client.get("/cron/rates", headers={"Authorization": f"Bearer {CRON_SECRET}"})

    assert response.json() == {"updated": True}


def test_cron_rates_noop_when_converter_disabled(dp, monkeypatch):
    dp["rates"] = RateProvider(make_settings(secondary_currency=""))
    settings = make_settings(cron_secret=CRON_SECRET)
    monkeypatch.setattr(web, "_runtime", web.Runtime(Bot("123:test"), dp, settings))
    with TestClient(web.app) as c:
        response = c.get("/cron/rates", headers={"Authorization": f"Bearer {CRON_SECRET}"})
    assert response.json()["updated"] is False


# ── курс между инстансами ─────────────────────────────────────────────────────


def _rate(age_hours: int) -> Rate:
    return Rate("TRY", "USD", 20_000, datetime.now(UTC) - timedelta(hours=age_hours))


def test_adopt_takes_newer_rate_and_ignores_older():
    provider = RateProvider(make_settings(secondary_currency="USD"))
    provider.adopt(_rate(5))
    assert provider.current is not None

    newer = _rate(1)
    provider.adopt(newer)
    assert provider.current is newer

    provider.adopt(_rate(10))
    assert provider.current is newer


def test_adopt_ignores_missing_rate():
    provider = RateProvider(make_settings(secondary_currency="USD"))
    provider.adopt(None)
    assert provider.current is None


# ── движок ────────────────────────────────────────────────────────────────────


def test_serverless_engine_has_no_pool():
    engine = make_engine("sqlite+aiosqlite:///:memory:", serverless=True)
    assert isinstance(engine.pool, NullPool)
