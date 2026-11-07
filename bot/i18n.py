"""Локализация.

Тексты лежат в ``bot/locales/<lang>/txt.ftl`` в плоском Fluent-подобном формате::

    key = значение с подстановкой { $name }

    multiline-key =
        первая строка
        вторая строка

Полноценный Fluent (селекторы, плюрализация) сознательно не подключается: в текстах бота
нет ни одной фразы, где арабские шесть форм множественного числа реально нужны — количество
везде показывается цифрой рядом с названием («شاورما دجاج × 2»). Если такая фраза появится,
этот модуль заменяется на ``fluent.runtime`` без изменений на стороне вызова.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).parent / "locales"
SUPPORTED = ("ar", "ru")

_KEY_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*=\s*(.*)$")
_VAR_RE = re.compile(r"\{\s*\$([a-zA-Z][a-zA-Z0-9_]*)\s*\}")


def _parse(text: str) -> dict[str, str]:
    messages: dict[str, str] = {}
    key: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if key is not None:
            messages[key] = "\n".join(buf).strip("\n")

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            # Пустая строка и комментарий завершают текущее сообщение.
            flush()
            key, buf = None, []
            continue

        match = _KEY_RE.match(raw)
        if match and not raw[0].isspace():
            flush()
            key = match.group(1)
            first = match.group(2)
            buf = [first] if first else []
        elif key is not None:
            buf.append(raw.strip())
        else:
            logger.warning("Строка вне сообщения в файле локали пропущена: %r", raw[:60])

    flush()
    return messages


class I18n:
    """Хранилище переводов для всех языков."""

    def __init__(self, default_lang: str = "ar", locales_dir: Path = LOCALES_DIR) -> None:
        self.default_lang = default_lang
        self.messages: dict[str, dict[str, str]] = {}
        for lang in SUPPORTED:
            path = locales_dir / lang / "txt.ftl"
            self.messages[lang] = _parse(path.read_text(encoding="utf-8")) if path.exists() else {}
            if not self.messages[lang]:
                logger.warning("Локаль %s пуста или не найдена: %s", lang, path)

    def get(self, lang: str, key: str, /, **kwargs: object) -> str:
        lang = lang if lang in self.messages else self.default_lang
        template = self.messages[lang].get(key)
        if template is None:
            template = self.messages[self.default_lang].get(key)
        if template is None:
            logger.error("Нет перевода для ключа %r (язык %s)", key, lang)
            return key

        def sub(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in kwargs:
                logger.error("Ключ %r: не передан параметр %r", key, name)
                return m.group(0)
            return str(kwargs[name])

        return _VAR_RE.sub(sub, template)

    def translator(self, lang: str) -> Translator:
        return Translator(self, lang)

    def missing_keys(self) -> dict[str, set[str]]:
        """Ключи, которых не хватает в каждом языке относительно объединения всех.

        Используется тестом, чтобы непереведённая строка не доехала до продакшена.
        """
        all_keys: set[str] = set()
        for msgs in self.messages.values():
            all_keys |= msgs.keys()
        return {lang: all_keys - msgs.keys() for lang, msgs in self.messages.items()}


class Translator:
    """Переводчик, привязанный к языку пользователя. В хендлеры приходит как ``i18n``."""

    __slots__ = ("_i18n", "lang")

    def __init__(self, i18n: I18n, lang: str) -> None:
        self._i18n = i18n
        self.lang = lang

    def __call__(self, key: str, /, **kwargs: object) -> str:
        return self._i18n.get(self.lang, key, **kwargs)

    @property
    def is_rtl(self) -> bool:
        return self.lang == "ar"
