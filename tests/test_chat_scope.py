"""Клиентские сценарии не должны срабатывать в группе кухни.

Живая поломка: повар нажал «🥙 Меню» в группе — и бот упал с
``AttributeError: 'NoneType' object has no attribute 'lang'``. В группе «клиента» нет,
UserMiddleware намеренно кладёт ``user=None``, а хендлеры каталога этого не ожидали.
Здесь проверяется, что такие апдейты до хендлеров попросту не доходят.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from aiogram.enums import ChatType

from bot.handlers import cart, catalog, checkout, profile, start

#: Роутеры, живущие только в личке.
CLIENT_ROUTERS = [catalog.router, cart.router, checkout.router, profile.router]


@dataclass
class FakeChat:
    type: str


@dataclass
class FakeMessage:
    chat: FakeChat
    text: str | None = None


@dataclass
class FakeCallback:
    message: FakeMessage


async def passes(observer, event) -> bool:
    """Пропускают ли корневые фильтры роутера такой апдейт."""
    result, _ = await observer.check_root_filters(event)
    return bool(result)


@pytest.mark.parametrize("router", CLIENT_ROUTERS, ids=lambda r: r.name)
async def test_group_messages_never_reach_client_routers(router):
    for chat_type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        event = FakeMessage(chat=FakeChat(chat_type), text="🥙 Меню")
        assert not await passes(router.message, event), (
            f"{router.name}: сообщение из {chat_type} не должно доходить до хендлера"
        )


@pytest.mark.parametrize("router", CLIENT_ROUTERS, ids=lambda r: r.name)
async def test_private_messages_do_reach_client_routers(router):
    event = FakeMessage(chat=FakeChat(ChatType.PRIVATE), text="🥙 Меню")
    assert await passes(router.message, event)


@pytest.mark.parametrize("router", CLIENT_ROUTERS, ids=lambda r: r.name)
async def test_group_callbacks_never_reach_client_routers(router):
    event = FakeCallback(message=FakeMessage(chat=FakeChat(ChatType.SUPERGROUP)))
    assert not await passes(router.callback_query, event)


@pytest.mark.parametrize("router", CLIENT_ROUTERS, ids=lambda r: r.name)
async def test_private_callbacks_do_reach_client_routers(router):
    event = FakeCallback(message=FakeMessage(chat=FakeChat(ChatType.PRIVATE)))
    assert await passes(router.callback_query, event)


async def test_setup_commands_still_work_in_a_group():
    """/chatid нужен именно в группе — им узнают ADMIN_GROUP_ID."""
    event = FakeMessage(chat=FakeChat(ChatType.SUPERGROUP), text="/chatid")
    assert await passes(start.router.message, event), (
        "роутер старта не должен быть закрыт для групп целиком"
    )
