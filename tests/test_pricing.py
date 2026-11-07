"""Деньги: подытоги, порог бесплатной доставки, минимальный заказ."""

from __future__ import annotations

from dataclasses import dataclass

from bot.services import pricing


@dataclass
class Opt:
    price_delta: int


@dataclass
class Line:
    line_total: int


def test_unit_price_adds_option_deltas():
    assert pricing.unit_price(15000, [Opt(4000), Opt(2500)]) == 21500


def test_unit_price_without_options():
    assert pricing.unit_price(15000, []) == 15000


def test_subtotal_sums_lines():
    assert pricing.subtotal([Line(15000), Line(6000), Line(3000)]) == 24000


def test_delivery_fee_kept_below_threshold():
    result = pricing.totals(items_subtotal=40000, delivery_fee=3000, free_delivery_from=50000)
    assert (result.delivery_fee, result.total, result.delivery_is_free) == (3000, 43000, False)


def test_delivery_becomes_free_exactly_at_threshold():
    result = pricing.totals(items_subtotal=50000, delivery_fee=3000, free_delivery_from=50000)
    assert (result.delivery_fee, result.total, result.delivery_is_free) == (0, 50000, True)


def test_threshold_zero_disables_free_delivery():
    result = pricing.totals(items_subtotal=999_000, delivery_fee=3000, free_delivery_from=0)
    assert result.delivery_fee == 3000
    assert result.delivery_is_free is False


def test_pickup_has_no_delivery_fee_to_waive():
    result = pricing.totals(items_subtotal=90000, delivery_fee=0, free_delivery_from=50000)
    assert result.delivery_is_free is False
    assert result.total == 90000


def test_below_minimum_reports_the_gap():
    assert pricing.below_minimum(12000, 20000) == 8000


def test_minimum_met_exactly():
    assert pricing.below_minimum(20000, 20000) == 0


def test_minimum_disabled():
    assert pricing.below_minimum(1, 0) == 0
