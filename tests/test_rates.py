"""Курс валют: разбор страницы, кросс-курс, пересчёт сумм и поведение при сбоях.

Сети здесь нет: страница берётся из фикстуры, снятой с sp-today.com. Так тест ловит
изменение формата данных, но не падает от того, что чужой сайт лежит.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bot.config import Settings
from bot.services import money as money_service
from bot.services.rates import (
    RATE_SCALE,
    Rate,
    RateProvider,
    RateUnavailable,
    build_rate,
    convert,
    cross_rate_micro,
    parse_quotes,
    pick_quote,
)
from tests.test_order_flow import make_settings

FIXTURE = (Path(__file__).parent / "fixtures" / "sp_today.html").read_text(encoding="utf-8")


def rate_settings(**overrides) -> Settings:
    base = dict(secondary_currency="USD", rate_mode="sell", rate_city="damascus")
    base.update(overrides)
    return make_settings(**base)


# ── разбор страницы ───────────────────────────────────────────────────────────


def test_parses_all_currencies():
    quotes = parse_quotes(FIXTURE)
    assert quotes["USD"] == (13150, 13200)
    assert quotes["TRY"] == (270, 273)
    assert quotes["EUR"] == (15170, 15350)


def test_city_selects_its_own_quotes():
    """У Хасаке свои котировки — не должны перепутаться с дамасскими."""
    assert parse_quotes(FIXTURE, "alhasakah")["USD"] == (13125, 13175)


def test_parses_unescaped_json_too():
    """Если сайт перестанет экранировать кавычки, парсер не должен ослепнуть."""
    quotes = parse_quotes(FIXTURE.replace('\\"', '"'))
    assert quotes["TRY"] == (270, 273)


def test_garbage_page_yields_nothing():
    assert parse_quotes("<html><body>сайт лёг</body></html>") == {}


def test_first_occurrence_wins():
    """Каждая валюта встречается в payload дважды — берём одну, а не удваиваем."""
    doubled = FIXTURE + FIXTURE.replace('"sell":273', '"sell":999')
    assert parse_quotes(doubled)["TRY"] == (270, 273)


# ── выбор котировки ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("sell", 13200), ("buy", 13150), ("mid", 13175)],
)
def test_pick_quote(mode: str, expected: int):
    assert pick_quote(13150, 13200, mode) == expected


def test_mid_rounds_up_in_favour_of_the_shop():
    assert pick_quote(270, 273, "mid") == 272


# ── кросс-курс ────────────────────────────────────────────────────────────────


def test_cross_rate_through_syrian_pound():
    """1 ₺ = 2.73 фунта, 1 $ = 132.00 фунта, значит 1 ₺ = 0.020682 $."""
    micro = cross_rate_micro(273, 13200)
    assert micro == 20682
    assert micro / RATE_SCALE == pytest.approx(0.020682, abs=1e-6)


def test_reverse_direction_is_consistent():
    """Обратный курс: доллар должен стоить около 48 лир."""
    micro = cross_rate_micro(13200, 273)
    assert micro / RATE_SCALE == pytest.approx(48.35, abs=0.01)


def test_same_currency_gives_one():
    assert cross_rate_micro(13200, 13200) == RATE_SCALE


def test_zero_quote_is_rejected():
    with pytest.raises(RateUnavailable):
        cross_rate_micro(273, 0)


def test_build_rate_from_page():
    rate = build_rate(parse_quotes(FIXTURE), base="TRY", quote="USD", mode="sell")
    assert (rate.base, rate.quote, rate.micro) == ("TRY", "USD", 20682)


def test_missing_currency_is_reported():
    with pytest.raises(RateUnavailable, match="RUB"):
        build_rate(parse_quotes(FIXTURE), base="TRY", quote="RUB", mode="sell")


# ── пересчёт сумм ─────────────────────────────────────────────────────────────


TRY_USD = Rate("TRY", "USD", 20682, datetime.now(UTC))


@pytest.mark.parametrize(
    ("kurus", "cents"),
    [
        (15000, 310),    # шаурма 150 ₺ -> 3.10 $
        (22000, 455),    # микс 220 ₺   -> 4.55 $
        (46000, 951),    # заказ 460 ₺  -> 9.51 $
        (0, 0),
    ],
)
def test_conversion(kurus: int, cents: int):
    assert convert(kurus, TRY_USD) == cents


def test_conversion_rounds_to_nearest_cent():
    """Курс 0.5 цента за единицу: 1 -> 1 цент, а не 0 от отбрасывания дроби."""
    half = Rate("TRY", "USD", RATE_SCALE // 2, datetime.now(UTC))
    assert convert(1, half) == 1
    assert convert(3, half) == 2


def test_conversion_stays_integer():
    assert isinstance(convert(12345, TRY_USD), int)


# ── провайдер: свежесть и запасной вариант ────────────────────────────────────


def make_provider(**overrides) -> RateProvider:
    return RateProvider(rate_settings(**overrides))


def aged(hours: float) -> Rate:
    return Rate("TRY", "USD", 20682, datetime.now(UTC) - timedelta(hours=hours))


def test_no_rate_at_all():
    assert make_provider().current is None


def test_fresh_rate_is_served():
    provider = make_provider()
    provider.prime(aged(0.5))
    assert provider.current is not None


def test_rate_older_than_limit_is_hidden():
    """Лучше одна верная цена, чем вторая, посчитанная по позапрошлонедельному курсу."""
    provider = make_provider(rate_max_age_hours=48)
    provider.prime(aged(72))
    assert provider.current is None


def test_stale_but_usable_rate_survives_site_outage():
    provider = make_provider(rate_ttl_min=60, rate_max_age_hours=48)
    provider.prime(aged(5))
    assert provider.is_stale is True       # пора обновить
    assert provider.current is not None    # но показывать пока можно


def test_prime_does_not_overwrite_fresher_memory():
    provider = make_provider()
    fresh = aged(0)
    provider.prime(fresh)
    provider.prime(aged(24))
    assert provider.current is fresh


def test_disabled_when_no_secondary_currency():
    assert RateProvider(make_settings(secondary_currency="")).enabled is False


def test_disabled_when_secondary_equals_base():
    assert RateProvider(make_settings(currency="USD", secondary_currency="USD")).enabled is False


async def test_refresh_parses_fetched_page(monkeypatch):
    provider = make_provider()

    async def fake_fetch(url: str) -> str:
        return FIXTURE

    monkeypatch.setattr(provider, "_fetch", fake_fetch)
    rate = await provider.refresh()
    assert rate.micro == 20682
    assert provider.current is not None


async def test_refresh_on_broken_page_keeps_old_rate(monkeypatch):
    provider = make_provider()
    provider.prime(aged(1))

    async def broken(url: str) -> str:
        return "<html>редизайн</html>"

    monkeypatch.setattr(provider, "_fetch", broken)
    with pytest.raises(RateUnavailable):
        await provider.refresh()
    assert provider.current is not None, "старый курс не должен пропадать при сбое"


# ── форматирование двух цен ───────────────────────────────────────────────────


def test_dual_price_shows_both():
    text = money_service.dual(rate_settings(), 15000, TRY_USD)
    assert "150" in text and "3.10" in text
    assert money_service.APPROX in text


def test_without_rate_only_base_price():
    text = money_service.dual(rate_settings(), 15000, None)
    assert "150" in text
    assert money_service.APPROX not in text


def test_unknown_quote_currency_is_ignored():
    weird = Rate("TRY", "XYZ", 20682, datetime.now(UTC))
    assert money_service.APPROX not in money_service.dual(rate_settings(), 15000, weird)


def test_live_rate_none_when_converter_disabled():
    provider = make_provider()
    provider.prime(aged(0))
    disabled = make_settings(secondary_currency="")
    assert money_service.live_rate(disabled, provider) is None
