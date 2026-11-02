"""All user-facing texts and keyboards in one place (HTML parse mode)."""
from aiogram.types import InlineKeyboardMarkup as Kb
from buttons import Btn

from config import Config
from services.settings_service import CUSTOM_ACTIONS, MESSAGES, SettingsService, plain_text

LINE = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
FOOTER = "✨ <i>VideoShare • Fast • Unique • Simple</i>"
LABEL = {"new": "New", "old": "Old"}
ICON = {"new": "🆕", "old": "📦"}


def other(category: str) -> str:
    return "old" if category == "new" else "new"


def fmt_duration(seconds: int) -> str:
    if seconds % 60 == 0:
        m = seconds // 60
        return f"{m} minute" + ("" if m == 1 else "s")
    return f"{seconds} seconds"


def videos_word(n: int) -> str:
    return "video" if n == 1 else "videos"


# ---------------------------------------------------------------- texts
def _fill(text: str, cfg: Config, **extra) -> str:
    """Placeholders an admin may use in custom texts."""
    text = (text.replace("{auto_delete}", fmt_duration(cfg.auto_delete_seconds))
                .replace("{max}", str(cfg.max_videos_per_request)))
    for key, value in extra.items():
        text = text.replace("{" + key + "}", str(value))
    return text


# The admin's custom texts for the messages listed in MESSAGES. Bound once at startup so the
# text helpers below keep their simple signatures; without it (tests) the defaults are used.
_settings: SettingsService | None = None
_cfg: Config | None = None


def bind(settings: SettingsService, cfg: Config) -> None:
    global _settings, _cfg
    _settings, _cfg = settings, cfg


def custom_message(key: str, value: str | None = None) -> str:
    """The admin's custom text for `key` ("" = use the built-in text)."""
    if value is not None:
        return value
    return _settings.get(key) if _settings is not None else ""


def alert_text(text: str) -> str:
    """Pop-up alerts are plain text, max 200 characters."""
    return plain_text(text).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")[:190]


def message(key: str, default: str, *, value: str | None = None, **extra) -> str:
    """Custom text (placeholders filled) if the admin set one, else `default`."""
    custom = custom_message(key, value)
    if not custom:
        return default
    cfg = _cfg
    return _fill(custom, cfg, **extra) if cfg is not None else custom


# Sample values used when the admin previews a text.
SAMPLE = {"count": 5, "collection": "New"}


def default_message(key: str, cfg: Config) -> str:
    """The built-in text of every message in MESSAGES (placeholders already filled)."""
    return {
        "main_menu_message": DEFAULT_MAIN_MENU,
        "choose_message": DEFAULT_CHOOSE,
        "invalid_message": default_invalid(cfg),
        "preparing_message": default_preparing(5),
        "delivered_message": default_delivered(cfg, 5),
        "exhausted_message": default_exhausted("new", False),
        "empty_message": DEFAULT_EMPTY,
        "busy_message": DEFAULT_BUSY,
        "rate_message": DEFAULT_RATE,
        "expired_message": DEFAULT_EXPIRED,
        "unavailable_message": DEFAULT_UNAVAILABLE,
        "failed_message": DEFAULT_FAILED,
        "error_message": DEFAULT_ERROR,
        "botoff_message": DEFAULT_BOT_OFF,
        "banned_message": DEFAULT_BANNED,
    }[key]


def preview_message(key: str, cfg: Config, value: str | None = None) -> str:
    """What a user sees for `key`, optionally with a not-yet-saved `value`."""
    default = default_message(key, cfg)
    custom = custom_message(key, value)
    text = _fill(custom, cfg, **SAMPLE) if custom else default
    return alert_text(text) if MESSAGES[key][4] else text


def default_welcome(cfg: Config, name: str | None = None) -> str:
    hello = f"👋 Hey <b>{name}</b>, welcome back!\n\n" if name else ""
    return (
        "🎬 <b>VIDEOSHARE</b>\n"
        "<i>Instant delivery • Fresh drops • Zero repeats</i>\n\n"
        f"{LINE}\n\n"
        f"{hello}"
        "🆕 <b>New</b>  ›  the latest videos\n"
        "📦 <b>Old</b>  ›  the classic collection\n"
        f"⏱ Auto-removed after <b>{fmt_duration(cfg.auto_delete_seconds)}</b>\n\n"
        f"{LINE}\n\n"
        "👇 <b>Choose an option below</b>"
    )


def welcome_text(cfg: Config, s: SettingsService | None = None, name: str | None = None) -> str:
    """`name` must already be HTML-escaped. Only the built-in welcome greets by name."""
    custom = s.get("welcome_message") if s else ""
    return _fill(custom, cfg) if custom else default_welcome(cfg, name)


DEFAULT_MAIN_MENU = f"🏠 <b>MAIN MENU</b>\n{LINE}\n\nWhat would you like to do?"


def main_menu_text() -> str:
    return message("main_menu_message", DEFAULT_MAIN_MENU)


ASK_KEYS = {"new": "ask_new_message", "old": "ask_old_message", None: "ask_any_message"}


def custom_ask_text(s: SettingsService | None, category: str | None) -> str:
    """The admin's prompt for this entry point. New/Old fall back to the Request text when
    they have no text of their own, so editing the Request text changes every prompt."""
    if not s:
        return ""
    return s.get(ASK_KEYS[category]) or s.get(ASK_KEYS[None])


def default_ask_count(cfg: Config, category: str | None = None) -> str:
    what = f"{LABEL[category]} videos" if category else "videos"
    return (f"How many {what} would you like?\n\n"
            f"Send a number from <code>1</code> to <code>{cfg.max_videos_per_request}</code>, "
            "for example <code>5</code>, <code>10</code> or <code>20</code>.")


# Shown ONLY to users whose Save / Forward is OFF (the default for everybody).
SAVE_CONTACT = "@DarkSMBot"
_FOOTER_LINE = "━━━━━━━━━━━━━━━━━━━━"


def protected_footer() -> str:
    return (f"{_FOOTER_LINE}\n\n🔒 <b>Want to Save or Forward Videos?</b>\n"
            f"🧑‍💻 Contact Owner: {SAVE_CONTACT}")


def with_protection_footer(text: str, protected: bool) -> str:
    """Add the contact footer for protected users. If an admin already typed the footer into a
    custom text (it contains the contact name) nothing is added twice."""
    if not protected or SAVE_CONTACT.lower() in text.lower():
        return text
    return f"{text}\n\n{protected_footer()}"


def ask_count_text(cfg: Config, category: str | None = None, fresh: bool = False,
                   s: SettingsService | None = None, protected: bool = False) -> str:
    head = "🔄 <b>New request</b>\n\n" if fresh else ""
    custom = custom_ask_text(s, category)
    body = head + (_fill(custom, cfg) if custom else default_ask_count(cfg, category))
    return with_protection_footer(body, protected)


def default_invalid(cfg: Config) -> str:
    return ("⚠️ <b>Invalid request</b>\n\n"
            f"Please enter a number between <code>1</code> and "
            f"<code>{cfg.max_videos_per_request}</code>.")


def invalid_text(cfg: Config) -> str:
    return message("invalid_message", default_invalid(cfg))


DEFAULT_CHOOSE = ("🎬 <b>Choose your collection</b>\n\n"
                  "🆕 <b>New Videos</b>\nLatest unique videos\n\n"
                  "📦 <b>Old Videos</b>\nOlder unique videos")


def choose_collection_text() -> str:
    return message("choose_message", DEFAULT_CHOOSE)


def default_help(cfg: Config) -> str:
    return (
        "ℹ️ <b>HOW VIDEOSHARE WORKS</b>\n\n"
        "1️⃣ Enter the number of videos you want.\n\n"
        "2️⃣ Choose New or Old.\n\n"
        "3️⃣ Videos are delivered directly to you.\n\n"
        "4️⃣ Use More New / More Old to continue.\n\n"
        "5️⃣ Previously delivered videos are not repeated.\n\n"
        f"⏱️ Videos automatically disappear after {fmt_duration(cfg.auto_delete_seconds)}."
    )


def help_text(cfg: Config, s: SettingsService | None = None) -> str:
    custom = s.get("help_message") if s else ""
    return _fill(custom, cfg) if custom else default_help(cfg)


def default_delete_notice(cfg: Config) -> str:
    return ("⏱️ <b>Auto-delete enabled</b>\n\n"
            f"Videos sent by this bot are automatically removed after "
            f"<b>{fmt_duration(cfg.auto_delete_seconds)}</b>.")


def delete_notice_text(cfg: Config, s: SettingsService | None = None) -> str:
    custom = s.get("delete_notice") if s else ""
    return _fill(custom, cfg) if custom else default_delete_notice(cfg)


def developer_text(s: SettingsService, bio: str | None = None) -> str:
    d = s.developer()
    bio = (d["bio"] if bio is None else bio) or "Creator &amp; Developer of VideoShare"
    has_links = any(d[k] for k in ("website", "instagram", "telegram", "github"))
    text = (f"👨‍💻 <b>DEVELOPER</b>\n\n<b>{html_escape(d['name'])}</b>\n\n{bio}\n\n{LINE}")
    if has_links:
        text += "\n\n🔗 Connect with the developer"
    return text


def html_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def video_caption(cfg: Config, video, position: int, source_caption: str | None = None) -> str:
    """Short, clean caption. Only our own label is used unless the admin opted in to keep the
    source caption (channel captions can contain channel names or links)."""
    number = video.video_number or position
    collection = {"new": "🆕 New Collection", "old": "📦 Old Collection"}.get(video.category or "", "")
    text = f"🎬 <b>Video #{number}</b>"
    if collection:
        text += f"\n\n{collection}"
    text += f"\n\n⏱️ Auto-delete: {fmt_duration(cfg.auto_delete_seconds)}"
    if source_caption:
        extra = html_escape(source_caption.strip())[:300]
        if extra:
            text += f"\n\n{extra}"
    return text


def default_preparing(n: int | None = None) -> str:
    if n is None:
        return "⏳ <b>Preparing your videos...</b>"
    return f"⏳ <b>Preparing {n} unique {videos_word(n)}...</b>"


def preparing_text() -> str:
    return message("preparing_message", default_preparing(), count="your")


def preparing_n_text(n: int, category: str, short_of: int | None = None) -> str:
    text = message("preparing_message", default_preparing(n), count=n)
    if short_of is not None:
        text = (f"⚠️ <b>Only {n} {category} {videos_word(n)} are available that you "
                f"haven't received yet.</b>\n\n") + text
    return text


def _short_note(n: int, category: str, short_of: int) -> str:
    return (f"⚠️ Only {n} unseen {LABEL[category]} {videos_word(n)} were left "
            f"(you asked for {short_of}).")


def default_delivered(cfg: Config, n: int, category: str = "new",
                      short_of: int | None = None) -> str:
    text = f"✅ <b>{n} unique {videos_word(n)} delivered.</b>"
    if short_of is not None:
        text += "\n" + _short_note(n, category, short_of)
    text += (f"\n\n⏱️ Videos will automatically disappear after "
             f"{fmt_duration(cfg.auto_delete_seconds)}.")
    return text


def delivered_text(cfg: Config, n: int, category: str, short_of: int | None = None,
                   protected: bool = False) -> str:
    custom = custom_message("delivered_message")
    if not custom:
        text = default_delivered(cfg, n, category, short_of)
    else:
        text = _fill(custom, cfg, count=n, collection=LABEL.get(category, ""))
        if short_of is not None:      # the shortfall warning is always kept
            text += "\n\n" + _short_note(n, category, short_of)
    return with_protection_footer(text, protected)


def default_exhausted(category: str, other_left: bool = False) -> str:
    where = "newest to oldest" if category == "new" else "oldest to newest"
    icon = ICON.get(category, "🎬")
    tail = ("You can still continue with the other collection." if other_left else
            "New videos will show up here as soon as they are added.")
    return (f"{icon} <b>You've reached the end of {LABEL.get(category, '')} Videos.</b>\n\n"
            f"You've already received every available unique video ({where}).\n\n{tail}")


def exhausted_text(category: str, other_left: bool = False) -> str:
    return message("exhausted_message", default_exhausted(category, other_left),
                   collection=LABEL.get(category, ""))


DEFAULT_EMPTY = ("📭 <b>No videos available yet</b>\n\n"
                 "The library is empty right now. Please check back soon.")
EMPTY_TEXT = DEFAULT_EMPTY    # kept for old imports; use empty_text()


def empty_text() -> str:
    return message("empty_message", DEFAULT_EMPTY)


def progress_text(p: dict) -> str:
    """The 'Continue' screen: where each collection stands for this user."""
    def line(mode: str) -> str:
        d = p[mode]
        state = "✅ finished" if d["left"] == 0 and d["received"] else f"{d['left']:,} left"
        return f"{ICON[mode]} <b>{LABEL[mode]}</b>: {d['received']:,} received • {state}"
    return ("🔥 <b>Continue where you stopped</b>\n\n" + line("new") + "\n" + line("old")
            + "\n\nEach collection remembers your place separately.")


def activity_text(a: dict) -> str:
    return (
        "📊 <b>YOUR VIDEOSHARE ACTIVITY</b>\n\n"
        f"🎬 Videos received: <b>{a['total']:,}</b>\n"
        f"🆕 New videos: {a['new']:,}\n"
        f"📦 Old videos: {a['old']:,}\n\n"
        f"🔄 Requests: <b>{a['requests']:,}</b>\n\n"
        "✨ <b>Unique videos remaining:</b>\n"
        f"New: {a['left_new']:,}\n"
        f"Old: {a['left_old']:,}\n\n"
        f"{FOOTER}"
    )


DEFAULT_BUSY = "⏳ Your previous request is still being processed."
DEFAULT_RATE = "⏳ Please wait a moment before requesting another batch."
DEFAULT_FAILED = "⚠️ I couldn't send the videos right now. Please try again in a moment."
DEFAULT_ERROR = "⚠️ Something went wrong. Please try again later."
DEFAULT_EXPIRED = "This request has expired. Send a number again."
DEFAULT_UNAVAILABLE = "This option is currently unavailable."
DEFAULT_BOT_OFF = "🔴 VideoShare is temporarily unavailable. Please try again later."
DEFAULT_BANNED = "⛔ You are currently unable to use VideoShare."
BUSY_TEXT, RATE_TEXT, FAILED_TEXT = DEFAULT_BUSY, DEFAULT_RATE, DEFAULT_FAILED
ERROR_TEXT, EXPIRED_TEXT = DEFAULT_ERROR, DEFAULT_EXPIRED   # defaults; see the functions below


def busy_text() -> str:
    return message("busy_message", DEFAULT_BUSY)


def rate_text() -> str:
    return message("rate_message", DEFAULT_RATE)


def failed_text() -> str:
    return message("failed_message", DEFAULT_FAILED)


def error_text() -> str:
    return message("error_message", DEFAULT_ERROR)


def expired_text() -> str:
    return message("expired_message", DEFAULT_EXPIRED)


def unavailable_text() -> str:
    return message("unavailable_message", DEFAULT_UNAVAILABLE)


def bot_off_text() -> str:
    return message("botoff_message", DEFAULT_BOT_OFF)


def banned_base_text() -> str:
    return message("banned_message", DEFAULT_BANNED)


# ---------------------------------------------------------------- keyboards
def custom_button(s: SettingsService) -> tuple[Btn, str] | None:
    """The admin-defined public button (if enabled and valid) and where it goes."""
    c = s.custom_button()
    if not c["enabled"] or not s.custom_ready(c):
        return None
    label = f"{c['emoji']} {c['name']}".strip()
    if c["kind"] == "url":
        return Btn(text=label, url=c["target"]), c["position"]
    return Btn(text=label, callback_data=CUSTOM_ACTIONS[c["target"]][1]), c["position"]


def _public_rows(s: SettingsService, *, with_activity: bool) -> list[list[Btn]]:
    on = s.button_on
    rows: list[list[Btn]] = []
    if on("btn_request"):
        rows.append([Btn(text="🎬 Request Videos", callback_data="menu:request")])
    pair = []
    if on("btn_new"):
        pair.append(Btn(text="🆕 New Videos", callback_data="menu:new"))
    if on("btn_old"):
        pair.append(Btn(text="📦 Old Videos", callback_data="menu:old"))
    if pair:
        rows.append(pair)
    if on("btn_more"):
        rows.append([Btn(text="🔥 More Videos", callback_data="menu:more")])
    if s.flag("ref_enabled"):
        rows.append([Btn(text="🔗 Refer & Earn", callback_data="ref:home")])
    pair = []
    if on("btn_developer"):
        pair.append(Btn(text="👨‍💻 Developer", callback_data="dev"))
    if on("btn_help"):
        pair.append(Btn(text="ℹ️ Help", callback_data="help"))
    if pair:
        rows.append(pair)
    if with_activity:
        rows.append([Btn(text="📊 My Requests", callback_data="activity")])
    custom = custom_button(s)
    if custom:
        btn, position = custom
        rows.insert(0, [btn]) if position == "top" else rows.append([btn])
    return rows


def _admin_row(is_admin: bool) -> list[list[Btn]]:
    return [[Btn(text="🛠️ Admin Panel", callback_data="adm:home")]] if is_admin else []


def welcome_kb(s: SettingsService, is_admin: bool = False) -> Kb:
    rows = _public_rows(s, with_activity=True)
    # welcome only: 🔥 More Videos | 📊 My Requests share one row (2 columns)
    act = next((r for r in rows if r[0].callback_data == "activity"), None)
    more = next((r for r in rows if len(r) == 1 and r[0].callback_data == "menu:more"), None)
    if act and more:
        rows.remove(act)
        more.append(act[0])
    rows = rows + _admin_row(is_admin)
    return Kb(inline_keyboard=rows or [[Btn(text="🏠 Main Menu", callback_data="menu")]])


def main_menu_kb(s: SettingsService, is_admin: bool = False) -> Kb:
    return Kb(inline_keyboard=_public_rows(s, with_activity=True) + _admin_row(is_admin))


def more_kb() -> Kb:
    return Kb(inline_keyboard=[
        [Btn(text="🔥 More New", callback_data="mmore:new"),
         Btn(text="♻️ More Old", callback_data="mmore:old")],
        [Btn(text="⬅️ Back", callback_data="menu")],
    ])


def help_kb(s: SettingsService) -> Kb:
    rows = []
    if s.button_on("btn_request"):
        rows.append([Btn(text="🎬 Request Videos", callback_data="menu:request")])
    elif s.button_on("btn_new") or s.button_on("btn_old"):
        rows.append([b for b in (
            Btn(text="🆕 New Videos", callback_data="menu:new") if s.button_on("btn_new") else None,
            Btn(text="📦 Old Videos", callback_data="menu:old") if s.button_on("btn_old") else None,
        ) if b])
    if s.button_on("btn_developer"):
        rows.append([Btn(text="👨‍💻 Developer", callback_data="dev")])
    rows.append([Btn(text="⬅️ Back", callback_data="menu")])
    return Kb(inline_keyboard=rows)


def developer_kb(s: SettingsService) -> Kb:
    d = s.developer()
    links = [("🌐 Website", d["website"]), ("📸 Instagram", d["instagram"]),
             ("💬 Telegram", d["telegram"]), ("🐙 GitHub", d["github"])]
    buttons = [Btn(text=label, url=url) for label, url in links if url]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Btn(text="⬅️ Back", callback_data="menu")])
    return Kb(inline_keyboard=rows)


def collection_kb() -> Kb:
    return Kb(inline_keyboard=[[
        Btn(text="🆕 New Videos", callback_data="type:new"),
        Btn(text="📦 Old Videos", callback_data="type:old"),
    ]])


def after_delivery_kb(category: str, count: int, s: SettingsService | None = None) -> Kb:
    show_more = s is None or s.button_on("btn_more")
    show_dev = s is None or s.button_on("btn_developer")
    rows: list[list[Btn]] = []
    if show_more:
        rows.append([Btn(text="🔥 More New", callback_data=f"more:new:{count}"),
                     Btn(text="♻️ More Old", callback_data=f"more:old:{count}")])
    rows.append([Btn(text="✨ Fresh Batch", callback_data=f"fresh:{category}:{count}")])
    last = [Btn(text="🔄 New Request", callback_data="again")]
    if show_dev:
        last.append(Btn(text="👨‍💻 Developer", callback_data="dev"))
    rows.append(last)
    rows.append([Btn(text="🏠 Main Menu", callback_data="menu")])
    return Kb(inline_keyboard=rows)


def try_other_kb(category: str, count: int) -> Kb:
    o = other(category)
    label = "📦 Try Old Videos" if o == "old" else "🆕 Try New Videos"
    return Kb(inline_keyboard=[
        [Btn(text=label, callback_data=f"more:{o}:{count}"),
         Btn(text="🔄 Request Again", callback_data="again")],
        [Btn(text="🏠 Main Menu", callback_data="menu")],
    ])


def finished_kb() -> Kb:
    return Kb(inline_keyboard=[
        [Btn(text="🔄 Request Again", callback_data="again"),
         Btn(text="🏠 Main Menu", callback_data="menu")],
    ])


def retry_kb(category: str, count: int) -> Kb:
    return Kb(inline_keyboard=[
        [Btn(text="🔄 Try Again", callback_data=f"more:{category}:{count}"),
         Btn(text="🏠 Main Menu", callback_data="menu")],
    ])


def back_kb(s: SettingsService | None = None) -> Kb:
    rows = []
    if s is None or s.button_on("btn_request"):
        rows.append(Btn(text="🎬 Request Videos", callback_data="menu:request"))
    rows.append(Btn(text="🏠 Main Menu", callback_data="menu"))
    return Kb(inline_keyboard=[rows])
