"""Состояния оформления заказа."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Checkout(StatesGroup):
    fulfillment = State()
    #: Геолокация — единственный «адрес» доставки: улиц и номеров домов в Сирии
    #: часто просто нет, а точка на карте однозначна. Ориентир клиент при желании
    #: пишет в комментарии к заказу.
    location = State()
    branch = State()
    #: Подтверждение контакта: телефон не спрашиваем, связь идёт через Telegram.
    contact = State()
    payment = State()
    comment = State()
    confirm = State()
