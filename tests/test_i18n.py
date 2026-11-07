"""Локали: полнота перевода и наличие ключей, которые код запрашивает по шаблону.

Непереведённая строка не должна доезжать до клиента — а заметить её в арабском тексте
глазами почти невозможно, поэтому проверяем машинно.
"""

from __future__ import annotations

import pytest

from bot.db.enums import OrderStatus
from bot.i18n import SUPPORTED, I18n
from bot.services.orders import ALLOWED, CLIENT_DRIVEN

i18n = I18n()


def test_no_missing_translations():
    missing = {lang: sorted(keys) for lang, keys in i18n.missing_keys().items() if keys}
    assert missing == {}


@pytest.mark.parametrize("lang", SUPPORTED)
def test_locale_is_not_empty(lang: str):
    assert len(i18n.messages[lang]) > 100


@pytest.mark.parametrize("lang", SUPPORTED)
@pytest.mark.parametrize("status", list(OrderStatus))
def test_every_status_has_a_name(lang: str, status: OrderStatus):
    key = f"status-name-{status.value}"
    assert i18n.messages[lang].get(key), f"нет {key} в локали {lang}"


@pytest.mark.parametrize("lang", SUPPORTED)
def test_every_kitchen_button_has_a_label(lang: str):
    """Ключи кнопок строятся из таблицы переходов, а не перечисляются вручную."""
    targets = {t for targets in ALLOWED.values() for t in targets} - set(CLIENT_DRIVEN)
    for status in targets:
        key = f"kitchen-btn-{status.value}"
        assert i18n.messages[lang].get(key), f"нет {key} в локали {lang}"


def test_placeholders_are_substituted():
    text = i18n.get("ru", "cart-min-order", min="200 ₺", left="50 ₺")
    assert "200 ₺" in text and "50 ₺" in text
    assert "{" not in text


def test_multiline_message_keeps_line_breaks():
    assert "\n" in i18n.get("ru", "welcome")


def test_unknown_key_returns_the_key_itself():
    assert i18n.get("ru", "no-such-key") == "no-such-key"


def test_unknown_language_falls_back_to_default():
    assert i18n.get("de", "menu-cart") == i18n.get("ar", "menu-cart")
