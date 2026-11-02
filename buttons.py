"""Colored inline buttons.

Telegram's Bot API (9.4+) lets an inline button carry a `style`: "primary" (blue),
"success" (green) or "danger" (red). `Btn` is a drop-in replacement for InlineKeyboardButton
that picks the colour AUTOMATICALLY from what the button does, so every menu in the bot gets
a consistent, modern look without touching each button. Navigation buttons (Back, Menu,
Dashboard) stay neutral. Pass `style=` explicitly to override; set BUTTON_COLORS=off to
disable colours globally. Clients/servers that do not know `style` simply ignore it.
"""
import os

from aiogram.types import InlineKeyboardButton

ENABLED = (os.getenv("BUTTON_COLORS", "on").strip().lower() not in ("0", "off", "false", "no")
           and "style" in InlineKeyboardButton.model_fields)

_NAV = ("back", "dashboard", "main menu", "🏠", "⬅️", "🔙", "◀️")
_DANGER = ("🗑", "🚫", "⛔", "❌", "🛑", "remove", "delete", "stop", "turn off", "block", "ban",
           "cancel")
_SUCCESS = ("✅", "➕", "💾", "🚀", "🟢", "save", "confirm", "send", "start", "turn on",
            "request again", "new request", "fresh", "more new", "more old", "try again")
_PRIMARY = ("🎬", "🆕", "📦", "🔗 refer", "🛠", "📢", "🔥", "preview", "setup", "wizard")

_DANGER_CB = (":rm", "rmok", "del", "ban", "scn:stop", "stop", ":off", "cancel")
_SUCCESS_CB = ("more:", "fresh:", "again", "mmore:", "save", ":on", "ok", ":add", ":nowok")


def style_for(text: str, callback_data: str | None = None, url: str | None = None) -> str | None:
    if url:
        return None
    t = (text or "").lower()
    cb = (callback_data or "").lower()
    if any(k in t for k in _NAV) or cb in ("menu", "adm:home") or cb.endswith(":home"):
        return None
    if any(k in t for k in _DANGER) or any(k in cb for k in _DANGER_CB):
        return "danger"
    if any(k in t for k in _SUCCESS) or any(cb.startswith(k) or k in cb for k in _SUCCESS_CB):
        return "success"
    if any(k in t for k in _PRIMARY) or cb.startswith(("menu:", "type:")):
        return "primary"
    return None


class Btn(InlineKeyboardButton):
    def __init__(self, **data):
        if ENABLED and data.get("style") is None:
            style = style_for(data.get("text", ""), data.get("callback_data"), data.get("url"))
            if style:
                data["style"] = style
        super().__init__(**data)
