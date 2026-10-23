"""Notification copy for CS2 round results, matched to the banner language.

CS2 localises the round-result banner, and the OCR recogniser already reports
which script it saw (``cs2_rounds.classify_round_result`` handles simplified,
traditional and English). Pushing a Chinese toast at a player whose client
renders ``ROUND WIN`` is the wrong way round, so the copy is selected from the
banner rather than from the Windows UI language: what the player read on screen
is what arrives on the phone.

``notification_language = "auto"`` follows the banner. An explicit value pins
one language and ignores detection.
"""

from __future__ import annotations

LANGUAGES = ("auto", "zh-CN", "zh-TW", "en")

# result -> (title, message)
ROUND_NOTICES: dict[str, dict[str, tuple[str, str]]] = {
    "zh-CN": {
        "win": ("CS2 回合胜利", "回合已结束，切回游戏准备下一回合。"),
        "loss": ("CS2 回合失败", "回合已结束，切回游戏准备下一回合。"),
    },
    "zh-TW": {
        "win": ("CS2 回合勝利", "本回合已結束，切回遊戲準備下一回合。"),
        "loss": ("CS2 回合失敗", "本回合已結束，切回遊戲準備下一回合。"),
    },
    "en": {
        "win": ("CS2 round won", "The round is over. Tab back in for the next one."),
        "loss": ("CS2 round lost", "The round is over. Tab back in for the next one."),
    },
}

# Glyphs that only exist in the traditional set. 回合 is shared by both scripts,
# so it cannot be used to tell them apart; 胜/勝 获/獲 败/敗 负/負 输/輸 赢/贏 can.
TRADITIONAL_ONLY = "勝敗獲負輸贏"

_CANONICAL = {
    "auto": "auto",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "en": "en",
}


def coerce(value: object) -> str:
    """Map a config value onto :data:`LANGUAGES`, tolerating locale spellings."""
    text = str(value).strip().lower().replace("_", "-")
    if text in _CANONICAL:
        return _CANONICAL[text]
    # "zh-hans-cn", "zh-hant", "en-us" and friends
    if text.startswith("zh"):
        return "zh-TW" if ("tw" in text or "hant" in text) else "zh-CN"
    if text.startswith("en"):
        return "en"
    return "auto"


def detect_language(text: str | None) -> str | None:
    """Guess the banner language from the OCR reading of the banner area.

    Only called once a result has already been recognised, so any Latin text
    here came from the English client ("ROUND WIN"). Traditional characters win
    over simplified because 回合 is script-neutral and the noise around it is
    not.
    """
    if not text:
        return None
    if any(ch in TRADITIONAL_ONLY for ch in text):
        return "zh-TW"
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return "zh-CN"
    if any(ch.isascii() and ch.isalpha() for ch in text):
        return "en"
    return None


def resolve(configured: str, detected: str | None, fallback: str = "zh-CN") -> str:
    """Pick the language to render: explicit setting, else banner, else fallback."""
    key = coerce(configured)
    if key != "auto":
        return key
    if detected in ROUND_NOTICES:
        return detected
    fallback_key = coerce(fallback)
    return "zh-CN" if fallback_key == "auto" else fallback_key


def round_notice(
    result: str,
    configured: str = "auto",
    detected: str | None = None,
    fallback: str = "zh-CN",
) -> tuple[str, str]:
    """Return ``(title, message)`` for one round result."""
    return ROUND_NOTICES[resolve(configured, detected, fallback)][result]
