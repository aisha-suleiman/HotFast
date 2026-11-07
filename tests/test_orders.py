"""Машина состояний заказа: разрешённые и запрещённые переходы, статус оплаты."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from bot.db.enums import (
    TERMINAL_STATUSES,
    Fulfillment,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from bot.services import orders as svc

S = OrderStatus


@dataclass
class FakeOrder:
    status: OrderStatus = S.NEW
    fulfillment: Fulfillment = Fulfillment.DELIVERY
    payment_method: PaymentMethod = PaymentMethod.CASH
    payment_status: PaymentStatus = PaymentStatus.NOT_REQUIRED
    logs: list = field(default_factory=list)


# ── начальное состояние ───────────────────────────────────────────────────────


def test_cash_order_waits_for_the_kitchen():
    assert svc.initial_status(PaymentMethod.CASH) == S.NEW
    assert svc.initial_payment_status(PaymentMethod.CASH) == PaymentStatus.NOT_REQUIRED


def test_shamcash_order_waits_for_payment():
    assert svc.initial_status(PaymentMethod.SHAMCASH) == S.AWAITING_PAYMENT
    assert svc.initial_payment_status(PaymentMethod.SHAMCASH) == PaymentStatus.AWAITING


# ── таблица переходов ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source", "target"),
    [(source, target) for source, targets in svc.ALLOWED.items() for target in targets],
)
def test_every_allowed_transition_applies(source: OrderStatus, target: OrderStatus):
    order = FakeOrder(status=source)
    assert svc.apply_transition(order, target) == source
    assert order.status == target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source in svc.ALLOWED
        for target in OrderStatus
        if target not in svc.ALLOWED[source]
    ],
)
def test_every_forbidden_transition_raises(source: OrderStatus, target: OrderStatus):
    order = FakeOrder(status=source)
    with pytest.raises(svc.InvalidTransition):
        svc.apply_transition(order, target)
    assert order.status == source, "запрещённый переход не должен менять заказ"


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
def test_terminal_statuses_have_no_exit(status: OrderStatus):
    assert svc.ALLOWED[status] == frozenset()
    assert svc.is_terminal(status)


def test_pressing_the_same_button_twice_is_rejected():
    """Гонка двух поваров: второй клик должен упереться, а не откатить статус."""
    order = FakeOrder(status=S.ACCEPTED)
    svc.apply_transition(order, S.COOKING)
    with pytest.raises(svc.InvalidTransition):
        svc.apply_transition(order, S.COOKING)


# ── кнопки кухни ──────────────────────────────────────────────────────────────


def test_ready_delivery_offers_only_on_the_way():
    buttons = svc.kitchen_buttons(S.READY, Fulfillment.DELIVERY)
    assert S.ON_THE_WAY in buttons
    assert S.PICKED_UP not in buttons


def test_ready_pickup_offers_only_picked_up():
    buttons = svc.kitchen_buttons(S.READY, Fulfillment.PICKUP)
    assert S.PICKED_UP in buttons
    assert S.ON_THE_WAY not in buttons


def test_kitchen_never_gets_client_driven_buttons():
    for status in svc.ALLOWED:
        for fulfillment in Fulfillment:
            assert S.PAYMENT_SUBMITTED not in svc.kitchen_buttons(status, fulfillment)


def test_cancel_is_the_last_button():
    buttons = svc.kitchen_buttons(S.ACCEPTED, Fulfillment.DELIVERY)
    assert buttons[-1] == S.CANCELLED


def test_terminal_order_has_no_buttons():
    assert svc.kitchen_buttons(S.DELIVERED, Fulfillment.DELIVERY) == []


# ── статус оплаты ─────────────────────────────────────────────────────────────


def test_accepting_after_proof_marks_payment_confirmed():
    order = FakeOrder(
        status=S.PAYMENT_SUBMITTED,
        payment_method=PaymentMethod.SHAMCASH,
        payment_status=PaymentStatus.SUBMITTED,
    )
    svc.apply_transition(order, S.ACCEPTED)
    assert order.payment_status == PaymentStatus.CONFIRMED


def test_rejecting_marks_payment_rejected():
    order = FakeOrder(
        status=S.PAYMENT_SUBMITTED,
        payment_method=PaymentMethod.SHAMCASH,
        payment_status=PaymentStatus.SUBMITTED,
    )
    svc.apply_transition(order, S.PAYMENT_REJECTED)
    assert order.payment_status == PaymentStatus.REJECTED


def test_client_can_resend_proof_after_rejection():
    order = FakeOrder(
        status=S.PAYMENT_REJECTED,
        payment_method=PaymentMethod.SHAMCASH,
        payment_status=PaymentStatus.REJECTED,
    )
    svc.apply_transition(order, S.PAYMENT_SUBMITTED)
    assert order.payment_status == PaymentStatus.SUBMITTED


def test_cash_order_payment_status_never_moves():
    order = FakeOrder(status=S.NEW, payment_method=PaymentMethod.CASH)
    svc.apply_transition(order, S.ACCEPTED)
    assert order.payment_status == PaymentStatus.NOT_REQUIRED


def test_every_status_has_an_emoji():
    assert set(svc.STATUS_EMOJI) == set(OrderStatus)
