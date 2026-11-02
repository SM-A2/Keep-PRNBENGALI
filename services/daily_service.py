"""Daily auto message: text + optional photo + optional button, sent to every active user once
a day at a time the admin chooses (IST), with an ON/OFF switch. State lives in PostgreSQL
(table `daily_message`), so restarts never lose the setup and never double-send.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.types import InlineKeyboardMarkup as Kb

from buttons import Btn
from config import Config
from database import Database
from logging_setup import log_event
from services.settings_service import ValidationError, validate_url
from services.user_service import UserService

log = logging.getLogger("daily")
IST = timezone(timedelta(hours=5, minutes=30), "IST")
SEND_DELAY = 0.05          # ~20 messages / second (Telegram allows 30)
CATCH_UP_MINUTES = 360     # bot was down at send time: still send if at most this late
CAPTION_MAX = 1024
BODY_MAX = 3500
LABEL_MAX = 32


# ------------------------------------------------------------------ parsing helpers
def parse_time(raw: str) -> str:
    """'21:30', '9:30 pm', '9 PM', '0930' -> 'HH:MM' (24h)."""
    m = re.fullmatch(r"\s*(\d{1,2})(?:[:.]?(\d{2}))?\s*([ap]\.?m\.?)?\s*", raw.lower())
    if not m:
        raise ValidationError("Send a time like 09:30, 21:00 or 9:30 PM (India time).")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm:
        if not 1 <= hour <= 12:
            raise ValidationError("With AM/PM the hour must be 1–12.")
        hour = hour % 12 + (12 if ampm.startswith("p") else 0)
    if hour > 23 or minute > 59:
        raise ValidationError("That is not a valid time.")
    return f"{hour:02d}:{minute:02d}"


def pretty_time(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:])
    return f"{(h % 12) or 12:02d}:{m:02d} {'AM' if h < 12 else 'PM'} IST"


def parse_link(raw: str) -> str:
    """@username / username / t.me/... / https://... -> a safe https URL."""
    v = raw.strip()
    m = re.fullmatch(r"@?([A-Za-z][A-Za-z0-9_]{3,31})", v)
    if m:
        return f"https://t.me/{m.group(1)}"
    if re.match(r"(?i)(t|telegram)\.me/", v):
        v = "https://" + v
    return validate_url(v)


def parse_label(raw: str) -> str:
    v = raw.strip()
    if not v or len(v) > LABEL_MAX or "\n" in v:
        raise ValidationError(f"The button name must be 1–{LABEL_MAX} characters on one line.")
    return v


# ------------------------------------------------------------------ model
@dataclass
class DailyConfig:
    enabled: bool = False
    send_time: str = "09:00"
    body: str = ""
    photo_file_id: str | None = None
    btn_label: str | None = None
    btn_url: str | None = None
    last_sent_on: date | None = None
    last_run_at: datetime | None = None
    last_total: int = 0
    last_sent: int = 0
    last_blocked: int = 0
    last_failed: int = 0

    @property
    def has_content(self) -> bool:
        return bool(self.body.strip() or self.photo_file_id)

    @property
    def has_button(self) -> bool:
        return bool(self.btn_label and self.btn_url)


@dataclass
class DailyResult:
    total: int = 0
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    seconds: float = 0.0


def next_send(c: DailyConfig, now: datetime | None = None) -> str:
    now = now or datetime.now(IST)
    hh, mm = int(c.send_time[:2]), int(c.send_time[3:])
    slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if c.last_sent_on == now.date() or now >= slot + timedelta(minutes=CATCH_UP_MINUTES):
        slot += timedelta(days=1)
    elif now >= slot:
        return "any moment now"
    day = "today" if slot.date() == now.date() else "tomorrow"
    return f"{day} at {pretty_time(c.send_time)}"


class DailyService:
    def __init__(self, bot: Bot, db: Database, users: UserService, cfg: Config) -> None:
        self.bot, self.db, self.users, self.cfg = bot, db, users, cfg
        self.c = DailyConfig()
        self.running = False

    # ----- storage -----
    async def load(self) -> None:
        row = await self.db.pool.fetchrow("SELECT * FROM daily_message WHERE id = 1")
        if row:
            self.c = DailyConfig(**{k: row[k] for k in DailyConfig.__dataclass_fields__})

    async def update(self, **fields) -> None:
        cols = [k for k in fields if k in DailyConfig.__dataclass_fields__]
        if not cols:
            return
        sets = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(cols))
        await self.db.pool.execute(
            f"UPDATE daily_message SET {sets}, updated_at = now() WHERE id = 1",
            *[fields[k] for k in cols])
        await self.load()

    async def skip_today_if_past(self) -> None:
        """After turning ON or changing the time: if today's slot already passed, the first
        automatic send is tomorrow (nothing fires immediately by surprise)."""
        now = datetime.now(IST)
        if now.strftime("%H:%M") >= self.c.send_time:
            await self.update(last_sent_on=now.date())
        else:
            await self.update(last_sent_on=None)

    # ----- message -----
    def keyboard(self) -> Kb | None:
        if not self.c.has_button:
            return None
        return Kb(inline_keyboard=[[Btn(text=self.c.btn_label, url=self.c.btn_url,
                                        style="primary")]])

    async def send_one(self, chat_id: int) -> str:
        """'sent' | 'blocked' | 'failed'"""
        c, markup = self.c, self.keyboard()
        for _ in range(3):
            try:
                if c.photo_file_id:
                    if c.body and len(c.body) > CAPTION_MAX:
                        await self.bot.send_photo(chat_id, c.photo_file_id)
                        await self.bot.send_message(chat_id, c.body, parse_mode="HTML",
                                                    reply_markup=markup)
                    else:
                        await self.bot.send_photo(chat_id, c.photo_file_id, caption=c.body or None,
                                                  parse_mode="HTML", reply_markup=markup)
                else:
                    await self.bot.send_message(chat_id, c.body, parse_mode="HTML",
                                                reply_markup=markup)
                return "sent"
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                await self.users.mark_blocked(chat_id)
                return "blocked"
            except TelegramBadRequest as e:
                reason = str(e).lower()
                if "chat not found" in reason or "deactivated" in reason:
                    await self.users.mark_blocked(chat_id)
                    return "blocked"
                log_event(log, logging.WARNING, "daily_bad_request", error=str(e)[:120])
                return "failed"
            except TelegramAPIError:
                return "failed"
        return "failed"

    async def preview(self, chat_id: int) -> str:
        return await self.send_one(chat_id)

    async def audience(self) -> list[int]:
        rows = await self.db.pool.fetch(
            "SELECT user_id FROM users WHERE NOT is_banned AND NOT is_blocked ORDER BY user_id")
        return [r["user_id"] for r in rows]

    async def run_send(self, *, trigger: str, notify: int | None = None) -> DailyResult | None:
        """Send to everybody. Returns None if a send is already running."""
        if self.running:
            return None
        self.running = True
        started = asyncio.get_running_loop().time()
        res = DailyResult()
        try:
            ids = await self.audience()
            res.total = len(ids)
            for uid in ids:
                outcome = await self.send_one(uid)
                setattr(res, outcome, getattr(res, outcome) + 1)
                await asyncio.sleep(SEND_DELAY)
        finally:
            res.seconds = asyncio.get_running_loop().time() - started
            self.running = False
        await self.update(last_run_at=datetime.now(timezone.utc), last_total=res.total,
                          last_sent=res.sent, last_blocked=res.blocked, last_failed=res.failed)
        log_event(log, logging.INFO, "daily_sent", trigger=trigger, total=res.total,
                  sent=res.sent, blocked=res.blocked, failed=res.failed)
        report = (f"⏰ <b>Daily message {'sent' if trigger != 'auto' else 'sent automatically'}</b>\n\n"
                  f"👥 Audience: <b>{res.total}</b>\n✅ Delivered: <b>{res.sent}</b>\n"
                  f"🚫 Blocked the bot: <b>{res.blocked}</b>\n⚠️ Failed: <b>{res.failed}</b>\n"
                  f"⏱ {res.seconds:.0f}s")
        for admin in ([notify] if notify else list(self.cfg.admin_ids)):
            try:
                await self.bot.send_message(admin, report, parse_mode="HTML")
            except TelegramAPIError:
                pass
        return res

    # ----- scheduler -----
    async def _tick(self) -> None:
        c = self.c
        if not c.enabled or not c.has_content or self.running:
            return
        now = datetime.now(IST)
        hh, mm = int(c.send_time[:2]), int(c.send_time[3:])
        slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if now < slot or c.last_sent_on == now.date():
            return
        # atomic claim: only one instance / one tick can win today's send
        claimed = await self.db.pool.fetchval(
            "UPDATE daily_message SET last_sent_on = $1 WHERE id = 1 AND enabled "
            "AND last_sent_on IS DISTINCT FROM $1 RETURNING 1", now.date())
        if not claimed:
            await self.load()
            return
        await self.load()
        if now - slot > timedelta(minutes=CATCH_UP_MINUTES):
            log_event(log, logging.INFO, "daily_skipped_too_late")
            return
        await self.run_send(trigger="auto")

    async def background_loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:   # noqa: BLE001 - the loop must never die
                log.exception("daily_tick_failed")
            await asyncio.sleep(20)
