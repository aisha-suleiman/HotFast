"""Зона доставки: расстояние и подбор тарифа, включая границы."""

from __future__ import annotations

import pytest

from bot.config import DeliveryTier
from bot.services import geo

TIERS = [
    DeliveryTier(max_km=2, fee=1500),
    DeliveryTier(max_km=5, fee=3000),
    DeliveryTier(max_km=8, fee=5000),
]

# Центр Дамаска — точка отсчёта в seed/menu.yaml.
BRANCH = (33.5138, 36.2765)


def test_distance_to_itself_is_zero():
    assert geo.haversine_km(*BRANCH, *BRANCH) == pytest.approx(0, abs=1e-9)


def test_distance_matches_known_pair():
    # Дамаск — Хомс: около 141 км по прямой (по дороге заметно больше — это не то же самое).
    assert geo.haversine_km(33.5138, 36.2765, 34.7324, 36.7137) == pytest.approx(141, abs=2)


def test_nearest_tier_wins():
    quote = geo.quote_for_distance(1.2, TIERS)
    assert quote is not None and quote.fee == 1500


def test_tier_boundary_is_inclusive():
    """Ровно 2.0 км при тарифе max_km=2 — ещё внутри зоны, а не за ней."""
    quote = geo.quote_for_distance(2.0, TIERS)
    assert quote is not None and quote.fee == 1500


def test_just_past_boundary_falls_to_next_tier():
    quote = geo.quote_for_distance(2.0001, TIERS)
    assert quote is not None and quote.fee == 3000


def test_outside_last_tier_is_rejected():
    assert geo.quote_for_distance(8.1, TIERS) is None


def test_resolve_delivery_returns_distance_and_fee():
    quote = geo.resolve_delivery(
        33.5200, 36.2800, branch_lat=BRANCH[0], branch_lon=BRANCH[1], tiers=TIERS
    )
    assert quote is not None
    assert quote.distance_km < 2
    assert quote.fee == 1500


def test_resolve_delivery_far_away_is_none():
    quote = geo.resolve_delivery(
        34.7324, 36.7137, branch_lat=BRANCH[0], branch_lon=BRANCH[1], tiers=TIERS
    )
    assert quote is None
