"""Зона доставки и её стоимость.

Расстояние считается по прямой от филиала — без геокодера и внешних сервисов. Для города
это достаточная аппроксимация, а главное — работает офлайн и не зависит от чужого API.

Если однажды понадобится точная зона по улицам, меняется только тело
:func:`resolve_delivery`: сигнатура остаётся, вызывающий код не трогаем.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from bot.config import DeliveryTier

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние по большому кругу между двумя точками, км."""
    p1, p2 = radians(lat1), radians(lat2)
    dphi = p2 - p1
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


@dataclass(frozen=True, slots=True)
class DeliveryQuote:
    distance_km: float
    fee: int


def quote_for_distance(distance_km: float, tiers: list[DeliveryTier]) -> DeliveryQuote | None:
    """Первый тариф, чей радиус покрывает расстояние. None — адрес вне зоны.

    Границы включительные: ровно 2.0 км при тарифе ``max_km=2`` попадает в зону.
    """
    for tier in tiers:  # tiers отсортированы по max_km в конфиге
        if distance_km <= tier.max_km:
            return DeliveryQuote(distance_km=distance_km, fee=tier.fee)
    return None


def resolve_delivery(
    lat: float,
    lon: float,
    *,
    branch_lat: float,
    branch_lon: float,
    tiers: list[DeliveryTier],
) -> DeliveryQuote | None:
    """Стоимость доставки по координатам клиента либо None, если адрес вне зоны."""
    distance = haversine_km(branch_lat, branch_lon, lat, lon)
    return quote_for_distance(distance, tiers)
