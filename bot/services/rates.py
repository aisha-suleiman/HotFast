"""Курс валют с sp-today.com.

Сайт не отдаёт публичного JSON (их API платный и по заявке), но страница построена на
Next.js и несёт данные структурированным payload прямо в HTML::

    {"code":"USD",...,"cities":{"damascus":{"buy":13150,"sell":13200,...}}}

Парсим именно его, а не разметку: имена полей меняются куда реже, чем вёрстка и CSS-классы.
Значения приходят умноженными на 100 — ``13200`` это 132.00 фунта за доллар.

Все котировки даны к сирийскому фунту, поэтому курс «лира → доллар» получается кросс-курсом
через фунт: 1 ₺ = 2.73 SYP, 1 $ = 132.00 SYP, значит 1 ₺ = 2.73 / 132.00 $.

Курс нигде не запрашивается по ходу отрисовки цен: фоновая задача обновляет его раз в
``RATE_TTL_MIN`` минут, а хендлеры читают уже готовое значение из памяти. Поэтому медленный
или упавший сайт не может задержать ответ клиенту.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiohttp

from bot.config import Settings

logger = logging.getLogger(__name__)

#: Курс хранится целым числом: единиц второй валюты за 1 единицу первой, ×1 000 000.
#: Дробей в деньгах не держим нигде, включая курс.
RATE_SCALE = 1_000_000

_TIMEOUT = aiohttp.ClientTimeout(total=15)
_HEADERS = {
    # Без узнаваемого User-Agent сайт отвечает заглушкой.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en",
}


class RateUnavailable(RuntimeError):
    """Курс получить не удалось: сайт недоступен или изменил формат данных."""


@dataclass(frozen=True, slots=True)
class Rate:
    """Сколько единиц ``quote`` дают за одну единицу ``base``."""

    base: str
    quote: str
    micro: int
    fetched_at: datetime

    def age(self, now: datetime | None = None) -> timedelta:
        return (now or datetime.now(UTC)) - self.fetched_at

    @property
    def as_float(self) -> float:
        """Только для логов и текста «1 ₺ = 0.0207 $»; в расчётах используется micro."""
        return self.micro / RATE_SCALE


# ── разбор страницы ───────────────────────────────────────────────────────────


def _rate_pattern(city: str) -> re.Pattern[str]:
    return re.compile(
        r'"code":"(?P<code>[A-Z]{3})".{0,400}?'
        r'"' + re.escape(city) + r'":\{"buy":(?P<buy>\d+),"sell":(?P<sell>\d+)',
        re.DOTALL,
    )


def parse_quotes(html: str, city: str = "damascus") -> dict[str, tuple[int, int]]:
    """Достаёт из страницы котировки к сирийскому фунту: код -> (buy, sell), ×100.

    В payload каждая валюта встречается дважды (блок ``rates`` и ``allCurrencies``) —
    берём первое вхождение, значения там одинаковые.
    """
    # В HTML кавычки экранированы (\"), нормализуем — дальше regex проще и надёжнее.
    text = html.replace('\\"', '"')
    quotes: dict[str, tuple[int, int]] = {}
    for match in _rate_pattern(city).finditer(text):
        code = match.group("code")
        if code not in quotes:
            quotes[code] = (int(match.group("buy")), int(match.group("sell")))
    return quotes


def pick_quote(buy: int, sell: int, mode: str) -> int:
    """Какое из двух чисел считать курсом. ``mid`` округляем вверх, в пользу заведения."""
    if mode == "buy":
        return buy
    if mode == "mid":
        return (buy + sell + 1) // 2
    return sell


def cross_rate_micro(base_in_syp: int, quote_in_syp: int) -> int:
    """Кросс-курс через фунт: сколько ``quote`` за одну ``base``, в micro.

    Обе котировки одинаково умножены на 100, поэтому множитель сокращается сам и
    приводить значения к «настоящим» фунтам не нужно.
    """
    if base_in_syp <= 0 or quote_in_syp <= 0:
        raise RateUnavailable("нулевая котировка — считать кросс-курс не от чего")
    return _div_round(base_in_syp * RATE_SCALE, quote_in_syp)


def build_rate(
    quotes: dict[str, tuple[int, int]], *, base: str, quote: str, mode: str
) -> Rate:
    for code in (base, quote):
        if code not in quotes:
            raise RateUnavailable(f"на странице нет котировки {code}")

    base_syp = pick_quote(*quotes[base], mode)
    quote_syp = pick_quote(*quotes[quote], mode)
    return Rate(
        base=base,
        quote=quote,
        micro=cross_rate_micro(base_syp, quote_syp),
        fetched_at=datetime.now(UTC),
    )


# ── пересчёт сумм ─────────────────────────────────────────────────────────────


def convert(
    amount_minor: int, rate: Rate, *, base_minor: int = 100, quote_minor: int = 100
) -> int:
    """Пересчитывает сумму из минорных единиц базовой валюты в минорные единицы второй.

    Целочисленно, с округлением к ближайшему: 15000 курушей при курсе 0.020682 дают
    310 центов, то есть 150 ₺ ≈ 3.10 $.
    """
    return _div_round(amount_minor * rate.micro * quote_minor, RATE_SCALE * base_minor)


def _div_round(numerator: int, denominator: int) -> int:
    """Деление с округлением к ближайшему целому (половина — вверх)."""
    return (numerator + denominator // 2) // denominator


# ── поставщик курса ───────────────────────────────────────────────────────────


class RateProvider:
    """Держит актуальный курс в памяти и умеет его обновлять.

    Чтение (:attr:`current`) синхронное и никогда не ходит в сеть — цены отрисовываются
    без ожидания. Обновление делает фоновая задача; если сайт недоступен, остаётся
    последний известный курс, а когда и он устареет сверх ``rate_max_age_hours`` —
    вторая цена просто перестаёт показываться.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._rate: Rate | None = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.settings.dual_prices

    @property
    def current(self) -> Rate | None:
        """Свежий курс либо None, если его нет или он слишком стар."""
        if self._rate is None:
            return None
        max_age = timedelta(hours=self.settings.rate_max_age_hours)
        if self._rate.age() > max_age:
            return None
        return self._rate

    @property
    def is_stale(self) -> bool:
        """Курс есть, но пора обновить."""
        if self._rate is None:
            return True
        return self._rate.age() > timedelta(minutes=self.settings.rate_ttl_min)

    def prime(self, rate: Rate | None) -> None:
        """Подставить курс, сохранённый в базе с прошлого запуска."""
        if rate is not None and self._rate is None:
            self._rate = rate

    def adopt(self, rate: Rate | None) -> None:
        """Взять курс из базы, если он новее текущего (его мог обновить другой инстанс)."""
        if rate is not None and (self._rate is None or rate.fetched_at > self._rate.fetched_at):
            self._rate = rate

    async def refresh(self) -> Rate:
        """Скачивает страницу и пересчитывает курс. Бросает :class:`RateUnavailable`."""
        async with self._lock:
            html = await self._fetch(self.settings.rate_url)
            quotes = parse_quotes(html, self.settings.rate_city)
            if not quotes:
                raise RateUnavailable(
                    "не нашли ни одной котировки — вероятно, изменился формат страницы"
                )
            rate = build_rate(
                quotes,
                base=self.settings.currency,
                quote=self.settings.secondary_currency,
                mode=self.settings.rate_mode,
            )
            self._rate = rate
            logger.info(
                "Курс обновлён: 1 %s = %.6f %s (%s, %s)",
                rate.base,
                rate.as_float,
                rate.quote,
                self.settings.rate_mode,
                self.settings.rate_city,
            )
            return rate

    async def _fetch(self, url: str) -> str:
        try:
            async with (
                aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session,
                session.get(url) as response,
            ):
                response.raise_for_status()
                return await response.text()
        except aiohttp.ClientError as exc:
            raise RateUnavailable(f"сайт курса недоступен: {exc}") from exc
        except TimeoutError as exc:
            raise RateUnavailable("сайт курса не ответил вовремя") from exc
