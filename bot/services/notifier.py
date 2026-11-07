"""Отправка карточки заказа на кухню и уведомлений клиенту.

Карточка в группе — одно сообщение на заказ: каждый переход статуса её редактирует.
Кухня видит историю в одном месте, а не ищет заказ среди двадцати уведомлений.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.config import Settings
from bot.db.enums import Fulfillment, OrderStatus, PaymentMethod, PaymentStatus
from bot.db.models import Order
from bot.i18n import I18n, Translator
from bot.keyboards.admin import kitchen_kb
from bot.services import money as money_service
from bot.services.orders import STATUS_EMOJI
from bot.utils.format import escape_html, money, rtl, user_mention

logger = logging.getLogger(__name__)

#: Какой ключ показать клиенту при каждом статусе. None — клиента не тревожим.
_CLIENT_STATUS_KEY: dict[OrderStatus, str | None] = {
    OrderStatus.NEW: None,
    OrderStatus.AWAITING_PAYMENT: None,
    OrderStatus.PAYMENT_SUBMITTED: None,
    OrderStatus.PAYMENT_REJECTED: "shamcash-rejected",
    OrderStatus.ACCEPTED: "status-accepted",
    OrderStatus.COOKING: "status-cooking",
    OrderStatus.READY: "status-ready",  # уточняется по способу получения
    OrderStatus.ON_THE_WAY: "status-on_the_way",
    OrderStatus.DELIVERED: "status-delivered",
    OrderStatus.PICKED_UP: "status-picked_up",
    OrderStatus.CANCELLED: "status-cancelled",
}


class Notifier:
    def __init__(self, bot: Bot, settings: Settings, i18n: I18n) -> None:
        self.bot = bot
        self.settings = settings
        self.i18n = i18n
        #: Кухня читает карточку на языке заведения, а не на языке клиента.
        self.kitchen = i18n.translator(settings.default_lang)

    # ── деньги ────────────────────────────────────────────────────────────────

    def money(self, amount: int) -> str:
        return money(amount, self.settings.currency_symbol, self.settings.currency_minor)

    # ── карточка кухни ────────────────────────────────────────────────────────

    def render_card(self, order: Order) -> str:
        t = self.kitchen
        lang = self.settings.default_lang

        items = "\n".join(
            t(
                "kitchen-item-line",
                name=escape_html(item.name(lang)),
                options=f" ({escape_html(item.options_text(lang))})"
                if item.options_text(lang)
                else "",
                qty=item.qty,
                total=self.money(item.line_total),
            )
            for item in order.items
        )

        money_line = t(
            "kitchen-money",
            subtotal=self.money(order.subtotal),
            delivery=self.money(order.delivery_fee),
            # Итог — по курсу, зафиксированному при оформлении: кухня и клиент должны
            # видеть одно и то же число, даже если курс с тех пор уехал.
            total=money_service.dual_for_order(self.settings, order, order.total),
        )

        if order.fulfillment == Fulfillment.DELIVERY:
            fulfillment = t(
                "kitchen-delivery",
                distance=f"{order.distance_km:.1f}" if order.distance_km is not None else "?",
            )
            # Текстовый адрес больше не спрашиваем, но у старых заказов он есть —
            # и появится снова, если однажды понадобится.
            if order.address_text:
                fulfillment += "\n" + t(
                    "kitchen-address", address=escape_html(order.address_text)
                )
        else:
            branch = order.branch
            fulfillment = t(
                "kitchen-pickup",
                branch=escape_html(branch.name(lang) if branch else "—"),
            )

        payment = self._render_payment(order)
        comment = (
            "\n" + t("kitchen-comment", comment=escape_html(order.comment))
            if order.comment
            else ""
        )

        card = t(
            "kitchen-card",
            emoji=STATUS_EMOJI[order.status],
            no=order.public_no,
            time=self._local_time(order),
            status=t(f"status-name-{order.status.value}"),
            items=items,
            money=money_line,
            fulfillment=fulfillment,
            contact=self._render_contact(order),
            client=user_mention(order.user_id, order.user.full_name if order.user else None),
            payment=payment,
            comment=comment,
            log=self._render_log(order),
        )
        return rtl(card, is_rtl=self.kitchen.is_rtl)

    def _render_contact(self, order: Order) -> str:
        """Как кухне связаться с клиентом.

        Порядок неслучаен: телефон, если он есть у старых заказов, потом ``@username``
        ссылкой на чат, и лишь в крайнем случае — общее «писать в Telegram», когда имени
        пользователя нет. Даже тогда кухня не остаётся ни с чем: строкой ниже стоит
        кликабельное имя клиента.
        """
        t = self.kitchen
        if order.phone:
            return t("kitchen-phone", phone=escape_html(order.phone))
        username = order.user.username if order.user else None
        if username:
            return t("kitchen-contact-username", username=escape_html(username))
        return t("kitchen-no-phone")

    def _render_payment(self, order: Order) -> str:
        t = self.kitchen
        if order.payment_method == PaymentMethod.CASH:
            return t("kitchen-payment-cash")

        state_key = {
            PaymentStatus.AWAITING: "kitchen-payment-state-awaiting",
            PaymentStatus.SUBMITTED: "kitchen-payment-state-submitted",
            PaymentStatus.CONFIRMED: "kitchen-payment-state-confirmed",
            PaymentStatus.REJECTED: "kitchen-payment-state-rejected",
        }.get(order.payment_status, "kitchen-payment-state-awaiting")

        line = t("kitchen-payment-shamcash", state=t(state_key))
        if order.payment_ref:
            line += "\n" + t("kitchen-payment-ref", ref=escape_html(order.payment_ref))
        return line

    def _render_log(self, order: Order) -> str:
        t = self.kitchen
        rows = []
        for entry in order.logs:
            actor = entry.actor_name or "—"
            rows.append(
                t(
                    "kitchen-log-line",
                    emoji=STATUS_EMOJI[entry.to_status],
                    status=t(f"status-name-{entry.to_status.value}"),
                    time=entry.at.astimezone(self.settings.timezone).strftime("%H:%M"),
                    actor=escape_html(actor),
                )
            )
        return "\n".join(rows)

    def _local_time(self, order: Order) -> str:
        return order.created_at.astimezone(self.settings.timezone).strftime("%d.%m %H:%M")

    # ── отправка ──────────────────────────────────────────────────────────────

    async def publish(self, order: Order) -> None:
        """Публикует новый заказ в группе кухни и запоминает id карточки."""
        message = await self.bot.send_message(
            self.settings.admin_group_id,
            self.render_card(order),
            reply_markup=kitchen_kb(order, self.kitchen),
        )
        order.group_message_id = message.message_id

        if order.fulfillment == Fulfillment.DELIVERY and order.lat and order.lon:
            # Отдельным сообщением — курьер открывает его в картах одним тапом.
            await self.bot.send_location(
                self.settings.admin_group_id,
                latitude=order.lat,
                longitude=order.lon,
                reply_to_message_id=message.message_id,
            )

    async def refresh(self, order: Order) -> None:
        """Перерисовывает карточку после смены статуса."""
        if order.group_message_id is None:
            await self.publish(order)
            return
        try:
            await self.bot.edit_message_text(
                self.render_card(order),
                chat_id=self.settings.admin_group_id,
                message_id=order.group_message_id,
                reply_markup=kitchen_kb(order, self.kitchen),
            )
        except TelegramBadRequest as exc:
            # "message is not modified" — нормальная ситуация при гонке двух нажатий.
            if "not modified" not in str(exc):
                logger.warning("Не удалось обновить карточку заказа %s: %s", order.id, exc)

    async def send_proof(self, order: Order) -> None:
        """Пересылает на кухню скриншот оплаты, привязав его к карточке заказа."""
        if not order.payment_proof_file_id:
            return
        await self.bot.send_photo(
            self.settings.admin_group_id,
            order.payment_proof_file_id,
            caption=self.kitchen("kitchen-proof-caption", no=order.public_no),
            reply_to_message_id=order.group_message_id,
        )

    # ── уведомления клиенту ───────────────────────────────────────────────────

    def client_translator(self, order: Order) -> Translator:
        return self.i18n.translator(order.lang.value)

    async def notify_client(self, order: Order, *, from_status: OrderStatus) -> None:
        text = self._client_text(order, from_status=from_status)
        if text is None:
            return
        await self.send_to_client(order.user_id, text)

    def _client_text(self, order: Order, *, from_status: OrderStatus) -> str | None:
        t = self.client_translator(order)
        status = order.status

        # Подтверждение оплаты — более важная новость для клиента, чем «принят».
        if status == OrderStatus.ACCEPTED and from_status == OrderStatus.PAYMENT_SUBMITTED:
            return t("shamcash-confirmed", no=order.public_no)

        key = _CLIENT_STATUS_KEY.get(status)
        if key is None:
            return None
        if key == "status-ready":
            key = (
                "status-ready-delivery"
                if order.fulfillment == Fulfillment.DELIVERY
                else "status-ready-pickup"
            )
        return t(key, no=order.public_no, support=self.settings.support_contact)

    async def send_to_client(self, user_id: int, text: str, **kwargs) -> bool:
        """Возвращает False, если клиент заблокировал бота, — это не ошибка приложения."""
        try:
            await self.bot.send_message(user_id, text, **kwargs)
            return True
        except TelegramForbiddenError:
            logger.info("Пользователь %s заблокировал бота — уведомление пропущено", user_id)
            return False
        except TelegramBadRequest as exc:
            logger.warning("Не удалось отправить сообщение %s: %s", user_id, exc)
            return False
