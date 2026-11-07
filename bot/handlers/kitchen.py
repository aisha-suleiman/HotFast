"""Обработка кнопок статусов в группе кухни."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.config import Settings
from bot.db.enums import OrderStatus
from bot.db.repo import Repos
from bot.i18n import Translator
from bot.keyboards.callbacks import KitchenCB
from bot.services.notifier import Notifier
from bot.services.orders import InvalidTransition, apply_transition

logger = logging.getLogger(__name__)
router = Router(name="kitchen")


@router.callback_query(KitchenCB.filter())
async def change_status(
    callback: CallbackQuery,
    callback_data: KitchenCB,
    repos: Repos,
    i18n: Translator,
    settings: Settings,
    notifier: Notifier,
) -> None:
    if callback.message is None or callback.message.chat.id != settings.admin_group_id:
        # Карточку могли переслать — за пределами группы кнопки не работают.
        await callback.answer(i18n("kitchen-not-allowed"), show_alert=True)
        return

    order = await repos.orders.get(callback_data.order_id)
    if order is None:
        await callback.answer(i18n("error-stale-button"), show_alert=True)
        return

    to_status = OrderStatus(callback_data.to_status)
    try:
        previous = apply_transition(order, to_status)
    except InvalidTransition:
        # Двое нажали почти одновременно: показываем актуальное состояние и перерисовываем.
        await callback.answer(
            i18n("kitchen-stale", status=i18n(f"status-name-{order.status.value}")),
            show_alert=True,
        )
        await notifier.refresh(order)
        return

    await repos.orders.log_transition(
        order,
        from_status=previous,
        to_status=to_status,
        actor_tg_id=callback.from_user.id,
        actor_name=callback.from_user.username or callback.from_user.full_name,
    )
    await repos.session.refresh(order, ["logs"])

    await notifier.refresh(order)
    await notifier.notify_client(order, from_status=previous)
    await callback.answer(i18n(f"status-name-{to_status.value}"))
