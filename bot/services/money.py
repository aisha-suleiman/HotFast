"""Форматирование сумм с учётом второй валюты.

Основная цена — всегда точная, в валюте меню. Вторая идёт после «≈»: она получена по
курсу с внешнего сайта, меняется в течение дня и служит ориентиром, а не обязательством.
"""

from __future__ import annotations

from bot.config import CURRENCIES, Settings
from bot.services.rates import Rate, convert
from bot.utils.format import money

#: Отделяет справочную цену от точной. Знак «примерно» здесь важен: клиент не должен
#: воспринимать пересчёт как вторую цену, по которой у него обязаны принять оплату.
APPROX = "≈"


def amount(settings: Settings, value: int) -> str:
    """Сумма в основной валюте: 15000 -> ``150 ₺``."""
    return money(value, settings.currency_symbol, settings.currency_minor)


def dual(settings: Settings, value: int, rate: Rate | None) -> str:
    """Сумма в двух валютах: ``150 ₺ ≈ 3.10 $``.

    Без курса возвращает только основную цену — показать одну верную цену лучше, чем две,
    из которых вторая выдумана.
    """
    primary = amount(settings, value)
    if rate is None or rate.quote not in CURRENCIES:
        return primary

    quote_symbol, quote_minor = CURRENCIES[rate.quote]
    converted = convert(
        value, rate, base_minor=settings.currency_minor, quote_minor=quote_minor
    )
    return f"{primary} {APPROX} {money(converted, quote_symbol, quote_minor)}"


def live_rate(settings: Settings, rates) -> Rate | None:
    """Текущий курс, если вторая цена включена и курс не устарел."""
    if not settings.dual_prices or rates is None:
        return None
    return rates.current


def order_rate(order) -> Rate | None:
    """Курс, зафиксированный в заказе при оформлении.

    История и карточка кухни считаются по нему, а не по текущему: сумма, которую клиент
    видел при подтверждении, не должна меняться задним числом.
    """
    if not order.rate_micro or not order.secondary_currency:
        return None
    return Rate(
        base=order.currency,
        quote=order.secondary_currency,
        micro=order.rate_micro,
        fetched_at=order.created_at,
    )


def dual_for_order(settings: Settings, order, value: int) -> str:
    """Сумма заказа в двух валютах по зафиксированному в нём курсу."""
    return dual(settings, value, order_rate(order))
