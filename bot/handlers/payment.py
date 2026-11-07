"""Приём подтверждения оплаты ShamCash: скриншот перевода и номер транзакции.

Шаг сознательно сделан без FSM. Состояние живёт в самом заказе, поэтому клиент может
прислать чек через час, после перезапуска бота или после отказа кухни — и это сработает.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.db.enums import OrderStatus
from bot.db.models import User
from bot.db.repo import Repos
from bot.i18n import Translator
from bot.services.notifier import Notifier
from bot.services.orders import InvalidTransition, apply_transition
from bot.utils.format import has_digits

router = Router(name="payment")
# Оплату присылают только в личку — в группе кухни свои обработчики.
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(F.photo)
async def got_proof_photo(
    message: Message,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
) -> None:
    if await state.get_state() is not None:
        return  # идёт оформление заказа — фото сейчас не про оплату

    order = await repos.orders.awaiting_payment_for_user(user.tg_id)
    if order is None:
        return

    # Берём самый крупный размер: мелкий скриншот на кухне не прочитать.
    order.payment_proof_file_id = message.photo[-1].file_id
    await repos.session.flush()
    await message.answer(i18n("shamcash-need-ref"))


@router.message(F.text)
async def got_proof_ref(
    message: Message,
    state: FSMContext,
    repos: Repos,
    i18n: Translator,
    user: User,
    notifier: Notifier,
) -> None:
    if await state.get_state() is not None:
        return

    order = await repos.orders.awaiting_payment_for_user(user.tg_id)
    if order is None:
        return

    if not order.payment_proof_file_id:
        await message.answer(i18n("shamcash-need-photo"))
        return

    ref = message.text.strip()
    if not has_digits(ref):
        await message.answer(i18n("shamcash-ref-invalid"))
        return

    order.payment_ref = ref[:64]
    try:
        previous = apply_transition(order, OrderStatus.PAYMENT_SUBMITTED)
    except InvalidTransition:
        # Заказ уехал дальше, пока клиент печатал, — сообщать об ошибке незачем.
        return
    await repos.orders.log_transition(
        order,
        from_status=previous,
        to_status=OrderStatus.PAYMENT_SUBMITTED,
        actor_tg_id=user.tg_id,
        actor_name=user.full_name,
    )
    await repos.session.refresh(order, ["logs"])

    await notifier.refresh(order)
    await notifier.send_proof(order)
    await message.answer(i18n("shamcash-received"))
