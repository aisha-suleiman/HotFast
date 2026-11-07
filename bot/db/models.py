"""ORM-модели.

Пользовательские тексты хранятся парой колонок ``*_ar`` / ``*_ru`` — языка всего два,
отдельная таблица переводов была бы лишним слоем.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base, TimestampMixin
from bot.db.enums import Fulfillment, Lang, OrderStatus, PaymentMethod, PaymentStatus


def _enum(enum_cls, name: str):
    """Строковый enum: native_enum=False, чтобы SQLite и Postgres вели себя одинаково."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda e: [i.value for i in e],
    )


class Localized:
    """Миксин для сущностей с названием на двух языках."""

    name_ar: Mapped[str] = mapped_column(String(128))
    name_ru: Mapped[str] = mapped_column(String(128))

    def name(self, lang: str) -> str:
        return self.name_ru if lang == Lang.RU else self.name_ar


class User(Base, TimestampMixin):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    lang: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), default=Lang.AR)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class Branch(Base, Localized):
    """Точка выдачи. Она же центр отсчёта зоны доставки."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    address_ar: Mapped[str] = mapped_column(String(255))
    address_ru: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    def address(self, lang: str) -> str:
        return self.address_ru if lang == Lang.RU else self.address_ar


class Category(Base, Localized):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    emoji: Mapped[str | None] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    products: Mapped[list[Product]] = relationship(
        back_populates="category", order_by="Product.sort"
    )


class Product(Base, Localized):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    desc_ar: Mapped[str | None] = mapped_column(Text)
    desc_ru: Mapped[str | None] = mapped_column(Text)
    #: Цена в минорных единицах валюты (куруши / центы).
    price: Mapped[int] = mapped_column(Integer)
    photo_file_id: Mapped[str | None] = mapped_column(String(255))
    #: False — товар в стоп-листе: не показывается и не даёт оформить заказ.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship(back_populates="products")
    option_groups: Mapped[list[OptionGroup]] = relationship(
        back_populates="product",
        order_by="OptionGroup.sort",
        cascade="all, delete-orphan",
    )

    def desc(self, lang: str) -> str | None:
        return self.desc_ru if lang == Lang.RU else self.desc_ar


class OptionGroup(Base, Localized):
    """Группа модификаторов: размер, соус, добавки."""

    __tablename__ = "option_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    #: min_select=1, max_select=1 — обязательный выбор ровно одного (размер).
    #: min_select=0, max_select=N — необязательные добавки.
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="option_groups")
    options: Mapped[list[Option]] = relationship(
        back_populates="group", order_by="Option.sort", cascade="all, delete-orphan"
    )


class Option(Base, Localized):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("option_groups.id", ondelete="CASCADE"))
    #: Прибавка к цене товара в минорных единицах, может быть 0.
    price_delta: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    group: Mapped[OptionGroup] = relationship(back_populates="options")


class CartItem(Base, TimestampMixin):
    __tablename__ = "cart_items"
    __table_args__ = (Index("ix_cart_items_user", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    qty: Mapped[int] = mapped_column(Integer, default=1)
    #: Список id выбранных опций.
    option_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    #: Снимок цены товара вместе с опциями на момент добавления.
    unit_price: Mapped[int] = mapped_column(Integer)

    product: Mapped[Product] = relationship(lazy="joined")

    @property
    def line_total(self) -> int:
        return self.unit_price * self.qty


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Короткий номер для клиента и кухни, вида 0907-014.
    public_no: Mapped[str] = mapped_column(String(16), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id"))

    status: Mapped[OrderStatus] = mapped_column(
        _enum(OrderStatus, "order_status"), default=OrderStatus.NEW, index=True
    )
    fulfillment: Mapped[Fulfillment] = mapped_column(_enum(Fulfillment, "fulfillment"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))

    # Доставка
    address_text: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    distance_km: Mapped[float | None] = mapped_column(Float)

    #: Необязателен: клиент может не оставлять номер, тогда связь идёт в Telegram.
    phone: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), default=Lang.AR)

    # Оплата
    payment_method: Mapped[PaymentMethod] = mapped_column(_enum(PaymentMethod, "payment_method"))
    payment_status: Mapped[PaymentStatus] = mapped_column(
        _enum(PaymentStatus, "payment_status"), default=PaymentStatus.NOT_REQUIRED
    )
    payment_proof_file_id: Mapped[str | None] = mapped_column(String(255))
    payment_ref: Mapped[str | None] = mapped_column(String(64))

    # Деньги, всё в минорных единицах
    subtotal: Mapped[int] = mapped_column(Integer)
    delivery_fee: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    #: Снимок курса на момент оформления: вторая цена в истории и на кухне не должна
    #: меняться от того, что курс уехал, пока заказ везли.
    secondary_currency: Mapped[str | None] = mapped_column(String(3))
    rate_micro: Mapped[int | None] = mapped_column(BigInteger)

    #: id карточки в группе кухни, чтобы редактировать её, а не слать новые сообщения.
    group_message_id: Mapped[int | None] = mapped_column(BigInteger)

    user: Mapped[User] = relationship(lazy="joined")
    branch: Mapped[Branch | None] = relationship(lazy="joined")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    logs: Mapped[list[OrderStatusLog]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusLog.at",
        lazy="selectin",
    )


class OrderItem(Base):
    """Снимок позиции на момент заказа: цены в меню меняются, история — нет."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    name_ar: Mapped[str] = mapped_column(String(128))
    name_ru: Mapped[str] = mapped_column(String(128))
    options_text_ar: Mapped[str | None] = mapped_column(String(255))
    options_text_ru: Mapped[str | None] = mapped_column(String(255))
    #: Идентификаторы выбранных опций — нужны, чтобы «повторить заказ» собрал то же самое.
    option_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    unit_price: Mapped[int] = mapped_column(Integer)
    qty: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")

    def name(self, lang: str) -> str:
        return self.name_ru if lang == Lang.RU else self.name_ar

    def options_text(self, lang: str) -> str | None:
        return self.options_text_ru if lang == Lang.RU else self.options_text_ar


class OrderStatusLog(Base):
    __tablename__ = "order_status_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    from_status: Mapped[OrderStatus | None] = mapped_column(_enum(OrderStatus, "order_status"))
    to_status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus, "order_status"))
    actor_tg_id: Mapped[int | None] = mapped_column(BigInteger)
    actor_name: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="logs")


class ExchangeRate(Base):
    """Последний известный курс. Переживает перезапуск: после рестарта вторая цена
    показывается сразу, не дожидаясь первого удачного похода на сайт."""

    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("base", "quote", name="uq_exchange_rates_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(String(3))
    quote: Mapped[str] = mapped_column(String(3))
    #: Единиц quote за одну base, умноженные на RATE_SCALE.
    micro: Mapped[int] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
