"""Форматирование денег, телефонов и RTL-безопасных строк."""

from __future__ import annotations

import re

#: Right-to-Left Mark. Без него Telegram переставляет числа и латиницу внутри арабской
#: строки — «120 ₺» превращается в «₺ 120» и хуже.
RLM = "‏"
#: Неразрывный пробел между суммой и символом валюты.
NBSP = " "
#: Узкий неразрывный пробел-разделитель разрядов: «12 500», а не «12500».
THIN_SPACE = " "

_DIGITS_RE = re.compile(r"\d")
_PHONE_CLEAN_RE = re.compile(r"[^\d+]")


def money(amount_minor: int, symbol: str, minor: int = 100) -> str:
    """Сумма из минорных единиц в читаемую строку: 1250000 -> ``12 500 ₺``.

    Дробная часть показывается, только если она ненулевая — цены на шаурму обычно круглые,
    и «150.00 ₺» в списке из восьми позиций читается хуже, чем «150 ₺».
    """
    whole, frac = divmod(abs(amount_minor), minor)
    sign = "-" if amount_minor < 0 else ""
    grouped = f"{whole:,}".replace(",", THIN_SPACE)
    body = grouped if frac == 0 else f"{grouped}.{frac:0{len(str(minor)) - 1}d}"
    return f"{sign}{body}{NBSP}{symbol}"


def rtl(text: str, *, is_rtl: bool) -> str:
    """Ставит RLM в начало строки, если интерфейс арабский.

    Нужно везде, где арабский текст соседствует с цифрами, латиницей или эмодзи.
    """
    if not is_rtl or not text:
        return text
    return text if text.startswith(RLM) else RLM + text


def normalize_phone(raw: str) -> str | None:
    """Приводит телефон к ``+<цифры>`` или возвращает None, если это не похоже на номер.

    Сирийские номера часто вводят как ``09XXXXXXXX`` — такой формат разворачивается в
    международный ``+9639XXXXXXXX``, иначе курьер не дозвонится из другой сети.
    """
    cleaned = _PHONE_CLEAN_RE.sub("", raw.strip())
    if not cleaned:
        return None

    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 10:
        cleaned = "+963" + cleaned[1:]
    elif not cleaned.startswith("+"):
        cleaned = "+" + cleaned

    digits = cleaned[1:]
    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        return None
    return cleaned


def escape_html(text: str) -> str:
    """Экранирование для parse_mode=HTML: имена и комментарии приходят от пользователя."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def user_mention(tg_id: int, name: str | None) -> str:
    """Кликабельная ссылка на клиента для карточки в группе кухни."""
    label = escape_html(name or str(tg_id))
    return f'<a href="tg://user?id={tg_id}">{label}</a>'


def shorten(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def has_digits(text: str) -> bool:
    return bool(_DIGITS_RE.search(text))
