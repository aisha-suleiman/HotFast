"""Форматирование денег, телефонов и RTL-маркеров."""

from __future__ import annotations

import pytest

from bot.utils.format import NBSP, RLM, THIN_SPACE, escape_html, money, normalize_phone, rtl


def test_round_amount_hides_decimals():
    assert money(15000, "₺") == f"150{NBSP}₺"


def test_thousands_are_separated():
    assert money(1_250_000, "₺") == f"12{THIN_SPACE}500{NBSP}₺"


def test_fractional_amount_keeps_decimals():
    assert money(15050, "₺") == f"150.50{NBSP}₺"


def test_zero_is_rendered():
    assert money(0, "$") == f"0{NBSP}$"


def test_negative_amount_keeps_sign():
    assert money(-5000, "$").startswith("-50")


# ── телефоны ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0912345678", "+963912345678"),   # местный сирийский формат
        ("+963912345678", "+963912345678"),
        ("00963912345678", "+963912345678"),
        ("963 912 345 678", "+963912345678"),
        ("+90 555 123 45 67", "+905551234567"),
        (" +963-91-234-5678 ", "+963912345678"),
    ],
)
def test_phone_normalisation(raw: str, expected: str):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "не телефон", "12", "+", "12345678901234567890"])
def test_invalid_phones_rejected(raw: str):
    assert normalize_phone(raw) is None


# ── RTL и экранирование ───────────────────────────────────────────────────────


def test_rtl_marks_arabic_string():
    assert rtl("شاورما 150", is_rtl=True).startswith(RLM)


def test_rtl_is_not_applied_twice():
    once = rtl("شاورما", is_rtl=True)
    assert rtl(once, is_rtl=True) == once


def test_rtl_skipped_for_russian():
    assert rtl("Шаурма 150", is_rtl=False) == "Шаурма 150"


def test_rtl_ignores_empty_string():
    assert rtl("", is_rtl=True) == ""


def test_html_is_escaped():
    assert escape_html("<b>Али & Ко</b>") == "&lt;b&gt;Али &amp; Ко&lt;/b&gt;"
