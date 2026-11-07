"""Конфигурация из .env. Всё валидируется на старте, а не падает в рантайме."""

from __future__ import annotations

from datetime import datetime, time
from functools import cached_property, lru_cache
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Символ и число минорных единиц в одной основной для каждой поддерживаемой валюты.
CURRENCIES: dict[str, tuple[str, int]] = {
    "TRY": ("₺", 100),
    "USD": ("$", 100),
}


class DeliveryTier(BaseModel):
    """Тариф доставки: до max_km километров по прямой — fee минорных единиц."""

    max_km: float = Field(gt=0)
    fee: int = Field(ge=0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Telegram
    bot_token: str
    admin_group_id: int
    admin_ids: list[int] = Field(default_factory=list)

    # Хранилища
    db_url: str = "sqlite+aiosqlite:///./shawarma.db"
    redis_url: str = ""

    # Локаль и деньги
    default_lang: str = "ar"
    currency: str = "TRY"
    tz: str = "Asia/Damascus"
    working_hours: str = "11:00-02:00"
    #: До этого момента заказы принимаются круглосуточно, независимо от WORKING_HOURS.
    #: Нужен для проверки бота в нерабочее время. Пустое значение — режим выключен.
    #: Момент в прошлом тоже безопасен: режим просто перестаёт действовать сам.
    hours_override_until: datetime | None = None

    # Вторая валюта: показывается рядом с основной по живому курсу.
    # Пустая строка полностью выключает конвертер.
    secondary_currency: str = ""
    rate_url: str = "https://sp-today.com/en"
    #: Город, чьи котировки берём: damascus (общесирийские) или alhasakah.
    rate_city: str = "damascus"
    #: sell — курс продажи, buy — покупки, mid — среднее между ними.
    rate_mode: str = "sell"
    #: Как часто обновлять курс в фоне.
    rate_ttl_min: int = 60
    #: Старше этого возраста курс не показываем: лучше одна цена, чем неверные две.
    rate_max_age_hours: int = 48

    # Оплата
    shamcash_wallet: str = ""
    shamcash_holder: str = ""
    payment_timeout_min: int = 30

    # Доставка
    delivery_tiers: list[DeliveryTier] = Field(default_factory=list)
    free_delivery_from: int = 0
    min_order_total: int = 0

    # Vercel (webhook вместо polling)
    #: Секрет вебхука Telegram: бот отвечает только на запросы с этим заголовком.
    webhook_secret: str = ""
    #: Секрет для cron-задач: Vercel присылает его в заголовке Authorization.
    cron_secret: str = ""
    #: Vercel сам выставляет VERCEL=1 в окружении функций.
    vercel: bool = False

    # Прочее
    support_contact: str = ""
    log_level: str = "INFO"

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, v: str) -> str:
        v = v.upper()
        if v not in CURRENCIES:
            raise ValueError(f"CURRENCY={v}: поддерживаются {', '.join(CURRENCIES)}")
        return v

    @field_validator("secondary_currency")
    @classmethod
    def _known_secondary(cls, v: str) -> str:
        v = v.upper().strip()
        if v and v not in CURRENCIES:
            raise ValueError(
                f"SECONDARY_CURRENCY={v}: поддерживаются {', '.join(CURRENCIES)} "
                "(пустое значение выключает вторую цену)"
            )
        return v

    @field_validator("rate_mode")
    @classmethod
    def _known_rate_mode(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("sell", "buy", "mid"):
            raise ValueError("RATE_MODE: допустимы sell, buy или mid")
        return v

    @field_validator("default_lang")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        v = v.lower()
        if v not in ("ar", "ru"):
            raise ValueError("DEFAULT_LANG: допустимы ar или ru")
        return v

    @field_validator("admin_group_id")
    @classmethod
    def _group_looks_like_group(cls, v: int) -> int:
        if v >= 0:
            raise ValueError(
                "ADMIN_GROUP_ID должен быть отрицательным (id группы, например -1001234567890)"
            )
        return v

    @field_validator("delivery_tiers")
    @classmethod
    def _tiers_sorted(cls, v: list[DeliveryTier]) -> list[DeliveryTier]:
        if not v:
            raise ValueError("DELIVERY_TIERS пуст — доставка не будет работать ни для кого")
        return sorted(v, key=lambda t: t.max_km)

    @field_validator("working_hours")
    @classmethod
    def _hours_parsable(cls, v: str) -> str:
        _parse_hours(v)  # бросит ValueError с внятным текстом
        return v

    @cached_property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @cached_property
    def hours(self) -> tuple[time, time]:
        return _parse_hours(self.working_hours)

    @cached_property
    def currency_symbol(self) -> str:
        return CURRENCIES[self.currency][0]

    @cached_property
    def currency_minor(self) -> int:
        return CURRENCIES[self.currency][1]

    @property
    def max_delivery_km(self) -> float:
        return self.delivery_tiers[-1].max_km

    @property
    def dual_prices(self) -> bool:
        """Показывать ли вторую цену. Совпадающие валюты — то же самое, что выключено."""
        return bool(self.secondary_currency) and self.secondary_currency != self.currency

    @cached_property
    def secondary_symbol(self) -> str:
        return CURRENCIES[self.secondary_currency][0] if self.secondary_currency else ""

    @cached_property
    def secondary_minor(self) -> int:
        return CURRENCIES[self.secondary_currency][1] if self.secondary_currency else 100


def _parse_hours(raw: str) -> tuple[time, time]:
    try:
        start_raw, end_raw = raw.split("-")
        sh, sm = (int(p) for p in start_raw.strip().split(":"))
        eh, em = (int(p) for p in end_raw.strip().split(":"))
        return time(sh, sm), time(eh, em)
    except Exception as exc:  # noqa: BLE001 — хотим одну понятную ошибку на старте
        raise ValueError(
            f"WORKING_HOURS={raw!r}: ожидается формат HH:MM-HH:MM, например 11:00-02:00"
        ) from exc





@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ленивая загрузка: импорт модуля не должен падать без .env (например, в тестах)."""
    return Settings()  # type: ignore[call-arg]
