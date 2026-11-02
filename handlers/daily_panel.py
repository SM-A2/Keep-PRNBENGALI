"""⏰ Daily Message - a section of the Admin Panel (mixin for handlers.admin_panel.Panel).

Pages     adm:daily            dashboard (status, time, text, photo, button, last run)
          adm:daily:time       time picker (presets + custom)
          adm:daily:now        "send now" confirmation
Actions   adm:daily:tgl | wiz | text | photo | btn | time | st:<HHMM> | tc | prev | now | nowok
          adm:daily:rmphoto | rmbtn | skip
Input     kinds dmtext -> dmphoto -> dmbtnname -> dmbtnlink (wizard) and dmtime
          /skip (or the Skip button) keeps the current value and moves on.
"""
from __future__ import annotations

import asyncio
import logging
import re

from aiogram.types import CallbackQuery, InlineKeyboardMarkup as Kb, Message

import ui
from buttons import Btn as B
from services.daily_service import (BODY_MAX, DailyService, next_send, parse_label, parse_link,
                                    parse_time, pretty_time)
from services.settings_service import ValidationError, sanitize_html

log = logging.getLogger("daily_panel")
LINE = ui.LINE
esc = ui.html_escape
PRESETS = ("08:00", "10:00", "12:00", "15:00", "18:00", "20:00", "21:00", "22:00")
WIZARD = ("dmtext", "dmphoto", "dmbtnname", "dmbtnlink")


def _nav(back: str = "adm:daily") -> list[B]:
    return [B(text="⬅️ Back", callback_data=back), B(text="🏠 Dashboard", callback_data="adm:home")]


def _short(text: str, size: int = 90) -> str:
    one = " ".join(re.sub(r"<[^>]+>", "", text).split())
    return esc(one[:size] + ("…" if len(one) > size else ""))


class DailyPanelMixin:
    daily: DailyService | None = None

    # ------------------------------------------------------------------ pages
    async def p_daily(self, a: list[str]) -> tuple[str, Kb]:
        svc = self.daily
        if svc is None:
            return "⚠️ Daily Message is not available.", Kb(inline_keyboard=[_nav("adm:home")])
        sub = a[0] if a else ""
        if sub == "time":
            return self._p_daily_time()
        if sub == "now":
            return await self._p_daily_now()
        return self._p_daily_home()

    def _p_daily_home(self) -> tuple[str, Kb]:
        c = self.daily.c
        state = "🟢 <b>ON</b>" if c.enabled else "🔴 <b>OFF</b>"
        body = _short(c.body) if c.body else "❌ not set"
        photo = "✅ attached" if c.photo_file_id else "— none"
        button = (f"✅ <b>{esc(c.btn_label)}</b> → {esc(c.btn_url)}" if c.has_button else "— none")
        last = "never"
        if c.last_run_at:
            last = (f"{self.when(c.last_run_at)}\n    ✅ {c.last_sent} sent · 🚫 {c.last_blocked} blocked"
                    f" · ⚠️ {c.last_failed} failed")
        nxt = next_send(c) if c.enabled and c.has_content else "—"
        text = (f"⏰ <b>DAILY AUTO MESSAGE</b>\n\n{LINE}\n\n"
                f"Status: {state}\n"
                f"🕒 Time: <b>{pretty_time(c.send_time)}</b> every day\n"
                f"📅 Next: <b>{nxt}</b>\n\n"
                f"📝 Text: {body}\n"
                f"🖼 Photo: {photo}\n"
                f"🔘 Button: {button}\n\n"
                f"📊 Last send: {last}\n\n{LINE}\n"
                "Sent to every active user once a day. Photo and button are optional.")
        rows = [
            [B(text="🔴 Turn OFF" if c.enabled else "🟢 Turn ON", callback_data="adm:daily:tgl")],
            [B(text="🧙 Setup Wizard (Text → Photo → Button)", callback_data="adm:daily:wiz")],
            [B(text="📝 Text", callback_data="adm:daily:text"),
             B(text="🖼 Photo", callback_data="adm:daily:photo")],
            [B(text="🔘 Button", callback_data="adm:daily:btn"),
             B(text="🕒 Set Time", callback_data="adm:daily:time")],
            [B(text="👁 Preview", callback_data="adm:daily:prev"),
             B(text="🚀 Send Now", callback_data="adm:daily:now")],
        ]
        remove = []
        if c.photo_file_id:
            remove.append(B(text="🗑 Remove Photo", callback_data="adm:daily:rmphoto"))
        if c.has_button:
            remove.append(B(text="🗑 Remove Button", callback_data="adm:daily:rmbtn"))
        if remove:
            rows.append(remove)
        rows.append([B(text="🔙 Back to Admin Panel", callback_data="adm:home")])
        return text, Kb(inline_keyboard=rows)

    def _p_daily_time(self) -> tuple[str, Kb]:
        c = self.daily.c
        text = (f"🕒 <b>SEND TIME</b>\n\n{LINE}\n\nCurrent: <b>{pretty_time(c.send_time)}</b> "
                f"(India time)\n\nPick a time or press <b>✏️ Custom time</b>.\n\n{LINE}")
        btns = [B(text=("✅ " if p == c.send_time else "") + pretty_time(p).replace(" IST", ""),
                  callback_data=f"adm:daily:st:{p.replace(':', '')}") for p in PRESETS]
        rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
        rows.append([B(text="✏️ Custom time", callback_data="adm:daily:tc")])
        rows.append(_nav())
        return text, Kb(inline_keyboard=rows)

    async def _p_daily_now(self) -> tuple[str, Kb]:
        n = len(await self.daily.audience())
        text = (f"🚀 <b>SEND NOW</b>\n\n{LINE}\n\nSend the daily message right now to "
                f"<b>{n}</b> users?\n\nThis does not change the daily schedule.\n\n{LINE}")
        return text, Kb(inline_keyboard=[
            [B(text="✅ Yes, send now", callback_data="adm:daily:nowok")],
            [B(text="❌ Cancel", callback_data="adm:daily")]])

    def when(self, dt) -> str:
        from handlers.admin_panel import when
        return when(dt)

    # ------------------------------------------------------------------ callbacks
    async def _r_daily(self, cb: CallbackQuery, a: list[str]) -> None:
        svc = self.daily
        sub = a[0] if a else ""
        uid = cb.from_user.id
        if svc is None:
            await cb.answer("Daily Message is not available.", show_alert=True)
            return
        c = svc.c

        if sub == "tgl":
            if not c.enabled and not c.has_content:
                await cb.answer("Set the message text or a photo first.", show_alert=True)
                return
            await svc.update(enabled=not c.enabled)
            if svc.c.enabled:
                await svc.skip_today_if_past()
            await self._log(uid, f"daily message {'ON' if svc.c.enabled else 'OFF'}")
            await cb.answer("🟢 Daily message ON" if svc.c.enabled else "🔴 Daily message OFF")
            await self._show(cb, *self._p_daily_home())
            return
        if sub == "wiz":
            await self._dm_prompt_cb(cb, "dmtext", wiz=True)
            return
        if sub in ("text", "photo"):
            await self._dm_prompt_cb(cb, "dmtext" if sub == "text" else "dmphoto", wiz=False)
            return
        if sub == "btn":
            await self._dm_prompt_cb(cb, "dmbtnname", wiz=True)
            return
        if sub == "tc":
            await self._dm_prompt_cb(cb, "dmtime", wiz=False)
            return
        if sub == "st" and len(a) > 1 and a[1].isdigit() and len(a[1]) == 4:
            try:
                value = parse_time(f"{a[1][:2]}:{a[1][2:]}")
            except ValidationError:
                await cb.answer()
                return
            await self._dm_set_time(value, uid)
            await cb.answer("🕒 Time saved")
            await self._show(cb, *self._p_daily_home())
            return
        if sub == "rmphoto":
            await svc.update(photo_file_id=None)
            await self._log(uid, "daily message photo removed")
            await cb.answer("🗑 Photo removed")
            await self._show(cb, *self._p_daily_home())
            return
        if sub == "rmbtn":
            await svc.update(btn_label=None, btn_url=None)
            await self._log(uid, "daily message button removed")
            await cb.answer("🗑 Button removed")
            await self._show(cb, *self._p_daily_home())
            return
        if sub == "prev":
            if not c.has_content:
                await cb.answer("Nothing to preview yet — set the text or a photo.", show_alert=True)
                return
            await cb.answer("👁 Preview sent below")
            await svc.preview(cb.message.chat.id)
            return
        if sub == "nowok":
            if not c.has_content:
                await cb.answer("Set the text or a photo first.", show_alert=True)
                return
            if svc.running:
                await cb.answer("A daily send is already running.", show_alert=True)
                return
            await cb.answer("🚀 Sending…")
            await self._show(cb, "🚀 <b>Sending the daily message…</b>\n\nYou will get a report "
                                 "here when it is finished.", Kb(inline_keyboard=[_nav()]))
            await self._log(uid, "daily message sent manually")
            task = asyncio.create_task(svc.run_send(trigger="manual", notify=uid))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return
        if sub == "skip":
            state, data = await self.users.get_state(uid)
            if state == "admin_input" and str(data.get("kind", "")).startswith("dm"):
                await cb.answer("⏭ Skipped")
                await self._dm_advance(cb.message, uid, data, saved=False)
            else:
                await cb.answer()
            return
        await self._view(cb)

    async def _dm_set_time(self, value: str, uid: int) -> None:
        await self.daily.update(send_time=value)
        await self.daily.skip_today_if_past()
        await self._log(uid, f"daily message time set to {value}")

    # ------------------------------------------------------------------ prompts
    _PROMPTS = {
        "dmtext": ("📝 <b>Message text</b>",
                   "Send the text users will receive.\nFormatting: <code>&lt;b&gt;bold&lt;/b&gt;</code>, "
                   "<code>&lt;i&gt;italic&lt;/i&gt;</code>, <code>&lt;u&gt;</code>, <code>&lt;code&gt;</code> "
                   f"(max {BODY_MAX} characters).", False),
        "dmphoto": ("🖼 <b>Photo</b>",
                    "Send the photo now (as a normal photo, not a file).\n"
                    "Send /skip to keep it as it is.", True),
        "dmbtnname": ("🔘 <b>Button name</b>",
                      "Send the button label, e.g. <code>🎬 Watch Now</code> (max 32 characters).\n"
                      "Send /skip for no change.", True),
        "dmbtnlink": ("🔗 <b>Button link or username</b>",
                      "Send a link <code>https://…</code> or a Telegram username "
                      "<code>@YourChannel</code>.\nSend /skip to leave the button unchanged.", True),
        "dmtime": ("🕒 <b>Custom time</b>",
                   "Send the time in India time, e.g. <code>21:30</code> or <code>9:30 PM</code>.", False),
    }

    def _dm_prompt_text(self, kind: str, wiz: bool) -> tuple[str, Kb]:
        title, hint, skippable = self._PROMPTS[kind]
        step = ""
        if wiz:
            step = {"dmtext": " — step 1/3", "dmphoto": " — step 2/3",
                    "dmbtnname": " — step 3/3", "dmbtnlink": " — step 3/3"}.get(kind, "")
        rows = []
        if skippable:
            rows.append(B(text="⏭ Skip", callback_data="adm:daily:skip"))
        rows.append(B(text="❌ Cancel", callback_data="adm:cancel"))
        return f"{title}{step}\n\n{hint}", Kb(inline_keyboard=[rows])

    async def _dm_prompt_cb(self, cb: CallbackQuery, kind: str, wiz: bool) -> None:
        ok = await self.users.set_state(cb.from_user.id, "admin_input",
                                        {"kind": kind, "back": "adm:daily", "arg": "", "wiz": wiz})
        if not ok:
            await cb.answer("One of your video requests is still running. Try again shortly.",
                            show_alert=True)
            return
        await cb.answer()
        text, markup = self._dm_prompt_text(kind, wiz)
        await self._show(cb, text, markup)

    async def _dm_prompt_msg(self, message: Message, uid: int, kind: str, wiz: bool) -> None:
        await self.users.set_state(uid, "admin_input",
                                   {"kind": kind, "back": "adm:daily", "arg": "", "wiz": wiz})
        text, markup = self._dm_prompt_text(kind, wiz)
        await self._send(message, text, markup)

    async def _dm_done(self, message: Message, uid: int, note: str = "✅ <b>Saved.</b>\n\n") -> None:
        await self.users.clear_state(uid)
        text, markup = self._p_daily_home()
        await self._send(message, note + text, markup)

    async def _dm_advance(self, message: Message, uid: int, data: dict, saved: bool = True) -> None:
        """Go to the next wizard step (or finish). Used after a value was saved or skipped."""
        kind, wiz = data.get("kind", ""), bool(data.get("wiz"))
        note = "✅ <b>Saved.</b>\n\n" if saved else ""
        nxt = {"dmtext": "dmphoto", "dmphoto": "dmbtnname"}.get(kind) if wiz else None
        if nxt is None:
            await self._dm_done(message, uid, note)
            return
        await self._dm_prompt_msg(message, uid, nxt, True)

    # ------------------------------------------------------------------ input handlers
    async def _i_dmtext(self, message: Message, data: dict, text: str) -> None:
        uid = message.from_user.id
        try:
            body = sanitize_html(text, max_len=BODY_MAX)
        except ValidationError as e:
            await self._retry(message, str(e))
            return
        await self.daily.update(body=body)
        await self._log(uid, "daily message text updated")
        await self._dm_advance(message, uid, data)

    async def _i_dmphoto(self, message: Message, data: dict, text: str) -> None:
        await self._retry(message, "Please send a photo (not text), or /skip.")

    async def on_input_photo(self, message: Message) -> None:
        uid = message.from_user.id
        state, data = await self.users.get_state(uid)
        if state != "admin_input" or data.get("kind") != "dmphoto":
            return
        await self.daily.update(photo_file_id=message.photo[-1].file_id)
        await self._log(uid, "daily message photo updated")
        await self._dm_advance(message, uid, data)

    async def _i_dmbtnname(self, message: Message, data: dict, text: str) -> None:
        try:
            label = parse_label(text)
        except ValidationError as e:
            await self._retry(message, str(e))
            return
        data = {**data, "label": label}
        ok = await self.users.set_state(message.from_user.id, "admin_input",
                                        {**data, "kind": "dmbtnlink"})
        if not ok:
            await self._retry(message, "Try again in a moment.")
            return
        text_, markup = self._dm_prompt_text("dmbtnlink", True)
        await self._send(message, text_, markup)

    async def _i_dmbtnlink(self, message: Message, data: dict, text: str) -> None:
        uid = message.from_user.id
        try:
            url = parse_link(text)
        except ValidationError as e:
            await self._retry(message, str(e))
            return
        label = data.get("label") or self.daily.c.btn_label
        if not label:
            await self._dm_prompt_msg(message, uid, "dmbtnname", True)
            return
        await self.daily.update(btn_label=label, btn_url=url)
        await self._log(uid, "daily message button updated")
        await self._dm_done(message, uid)

    async def _i_dmtime(self, message: Message, data: dict, text: str) -> None:
        try:
            value = parse_time(text)
        except ValidationError as e:
            await self._retry(message, str(e))
            return
        await self._dm_set_time(value, message.from_user.id)
        await self._dm_done(message, message.from_user.id, f"✅ <b>Time set to {pretty_time(value)}.</b>\n\n")

    async def on_skip(self, message: Message) -> None:
        uid = message.from_user.id
        state, data = await self.users.get_state(uid)
        if state != "admin_input" or not str(data.get("kind", "")).startswith("dm"):
            return
        await self._dm_advance(message, uid, data, saved=False)
