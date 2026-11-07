"""Протухшая кнопка не должна отменять уже сделанную работу.

Из живого случая: кухня нажала «Готов», пока бот лежал. Через час Telegram доставил это
нажатие, статус сменился, карточка перерисовалась — а ответ на саму кнопку Telegram уже не
принял («query is too old»). Исключение долетало до транзакции, та откатывалась, и смена
статуса пропадала: в группе заказ выглядел готовым, в базе — нет.
"""

from __future__ import annotations

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery

from bot.middlewares.stale_callback import StaleCallbackMiddleware, is_stale_callback


def bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=AnswerCallbackQuery(callback_query_id="1"), message=message)


STALE = [
    "Bad Request: query is too old and response timeout expired or query ID is invalid",
    "Bad Request: QUERY ID IS INVALID",
    "query is too old",
]
REAL = [
    "Bad Request: message text is empty",
    "Bad Request: chat not found",
    "Bad Request: message to edit not found",
]


@pytest.mark.parametrize("message", STALE)
def test_recognises_stale_button(message: str):
    assert is_stale_callback(bad_request(message))


@pytest.mark.parametrize("message", REAL)
def test_real_errors_are_not_mistaken_for_stale(message: str):
    assert not is_stale_callback(bad_request(message))


async def test_stale_answer_is_swallowed_so_the_work_commits():
    middleware = StaleCallbackMiddleware()
    done = []

    async def handler(event, data):
        done.append("статус сменён")
        raise bad_request(STALE[0])

    result = await middleware(handler, object(), {})

    assert result is None
    assert done == ["статус сменён"], "работа хендлера должна остаться выполненной"


async def test_real_errors_still_propagate():
    """Гасить всё подряд нельзя: настоящая ошибка обязана дойти до отката и лога."""
    middleware = StaleCallbackMiddleware()

    async def handler(event, data):
        raise bad_request(REAL[0])

    with pytest.raises(TelegramBadRequest):
        await middleware(handler, object(), {})


async def test_successful_handler_passes_through():
    middleware = StaleCallbackMiddleware()

    async def handler(event, data):
        return "ок"

    assert await middleware(handler, object(), {}) == "ок"


async def test_unrelated_exceptions_are_not_touched():
    middleware = StaleCallbackMiddleware()

    async def handler(event, data):
        raise ValueError("ошибка в логике")

    with pytest.raises(ValueError):
        await middleware(handler, object(), {})
