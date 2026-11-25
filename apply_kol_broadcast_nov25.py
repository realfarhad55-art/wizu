# apply_kol_broadcast_nov25.py - KOL Owner Broadcast + "Channel Alerts" -> "KOL Alert" (user spec Nov 25 ~06:46 PKT)
# Marker: KOL_BROADCAST_NOV25
# User spec: ~/workspace/goals/wizardscan-bot-issue-fixes/files/dm-alert-settings-spec-nov25.md (section 15)
# Base: DM Alert Settings patches 1-4 already deployed live; anchors match that state.
#
# WHAT IT DOES:
#  1. NEW owner-only command /kolbroadcast [@ch1 @ch2 ...]:
#     - No args = every listed (tracked) channel's owner. Args = only those channels.
#     - Owner sends a template (text / photo / video with caption). {Username}
#       and {Channel} are replaced PER RECIPIENT with that owner's username and
#       that channel's name (Shahroz -> @shahroz2 + @Marvels_calls, Farhad ->
#       @farhad + @bigbangcall). Lowercase {username}/{channel} also work.
#     - Owner lookup: linked owner (kol_owners) first, else the channel
#       creator via getChatAdministrators. No owner found -> skipped + listed
#       in the report. One DM per channel an owner owns.
#     - Preview first (rendered for the first recipient + recipient count),
#       then Send / Rewrite / Cancel. About 1 msg/sec, blocked counted, never
#       aborts the rest. Recorded in broadcasts.json, so /pinbroadcast,
#       /replybroadcast, /editbroadcast and /deletebroadcast all work on it
#       (edit sends ONE text to all - no per-recipient variables on edit).
#       No auto-pin (same rule as normal broadcasts).
#  2. RENAME: All Commands button "Channel Alerts" -> "KOL Alert" (label
#     only; callback_data and lbl key stay "channel_alerts"). The help-text
#     mention is updated too. Screen titles ("CHANNEL ALERT Settings") and
#     OwnerHelp media entries are untouched - they name the screens, not
#     the button. If a custom label was set via /editbtnlabel, re-run it.
#  3. PICKER FIX (user report Nov 25 ~06:51 PKT - his picker showed ~139
#     channels): the Channel/KOL Alert picker is for a channel OWNER to set
#     THEIR OWN channel's alert preferences, but patch 4's
#     _chalert_user_channels returned EVERY linked channel for the bot
#     owner/admin. Now it lists ONLY linked channels this user owns
#     (kol_owners), plus linked channels with no recorded owner where the
#     user is the channel creator (getChatAdministrators, best-effort,
#     15s cap). Real now sees only his own channels; a KOL owner sees only
#     theirs; a stranger sees none (empty state + Add Channel). Add Channel
#     already records the linker as owner, so a newly linked channel shows
#     at once. The DM picker is untouched (it lists SUBSCRIBED channels,
#     which is correct for DM prefs).
# English ONLY in all new user-facing text. No new code files: everything
# goes into existing core.py / commands.py / runtime.py.
# Usage: python3 apply_kol_broadcast_nov25.py [/opt/bot | core.py | ...]
#        (accepts a directory OR any one of the files; the others are resolved
#        from the same directory)
import os
import sys

MARKER = "KOL_BROADCAST_NOV25"


def resolve(arg, name):
    if arg and os.path.isdir(arg):
        return os.path.join(arg, name)
    if arg and os.path.isfile(arg):
        return os.path.join(os.path.dirname(arg), name)
    return name


def patch_one(path, edits, marker=MARKER):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if marker in src:
        print("already has %s in %s, skipping" % (marker, os.path.basename(path)))
        return True
    orig = src
    for i, (old, new) in enumerate(edits, 1):
        n = src.count(old)
        if n != 1:
            print("FAIL: %s edit E%d anchor count=%d (want 1)" % (os.path.basename(path), i, n))
            return False
        src = src.replace(old, new, 1)
        print("E%d OK (%s)" % (i, os.path.basename(path)))
    bak = path + ".bak_" + marker
    with open(bak, "w", encoding="utf-8") as f:
        f.write(orig)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("DONE %s. Backup: %s" % (os.path.basename(path), bak))
    return True


# ── core.py: state constants + button rename ───────────────────────────────
CORE_EDITS = [
    # E1: new states for the KOL broadcast flow (after the reply-broadcast state).
    (
        'ST_REPLY_BROADCAST_MSG = "reply_broadcast_msg"  # /replybroadcast - next message is the update, sent as a reply to the old broadcast',
        '''ST_REPLY_BROADCAST_MSG = "reply_broadcast_msg"  # /replybroadcast - next message is the update, sent as a reply to the old broadcast
# KOL_BROADCAST_NOV25 - KOL owner broadcast: personalised template per channel owner
ST_KOLBROADCAST_MSG     = "kolbroadcast_msg"      # /kolbroadcast - next message is the template
ST_KOLBROADCAST_PREVIEW = "kolbroadcast_preview"  # KOL broadcast preview - owner confirms before send''',
    ),
    # E2: "Channel Alerts" button -> "KOL Alert" (label only; the lbl key and
    # callback_data stay "channel_alerts", so /editbtnlabel still works).
    (
        '        [_pkb(lbl("channel_alerts", "🔮 Channel Alerts 🔮"), callback_data="channel_alerts")],',
        '        [_pkb(lbl("channel_alerts", "🔮 KOL Alert 🔮"), callback_data="channel_alerts")],  # KOL_BROADCAST_NOV25: renamed from "Channel Alerts" by owner order',
    ),
]


# ── commands.py: /kolbroadcast + help-text rename ──────────────────────────
COMMANDS_EDITS = [
    # E1: /kolbroadcast command (inserted before /broadcast, same area).
    (
        """@owner_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
        r"""@owner_only
async def cmd_kolbroadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # KOL_BROADCAST_NOV25: personalised broadcast to KOL channel owners.
    # Usage: /kolbroadcast [@ch1 @ch2 ...] - no args = every listed channel.
    # The owner then sends the template; {Username} and {Channel} are
    # replaced per recipient. Preview first - nothing is sent until Send.
    args = context.args or []
    parts = []
    for a in args:
        parts.extend([p.strip().lstrip("@") for p in a.replace(",", " ").split() if p.strip()])
    tracked_set = {str(c).lstrip("@").lower() for c in load_channels()}
    wanted = []
    unknown = []
    for p in parts:
        key = p.lower()
        if key in tracked_set:
            if key not in wanted:
                wanted.append(key)
        elif key not in unknown:
            unknown.append(key)
    if parts and not wanted:
        await update.message.reply_text(
            "⚠️ None of those channels are tracked.\n\n"
            "Unknown: " + ", ".join("@" + _display_handle(u) for u in unknown) +
            "\n\nCheck the channel names and try again: <code>/kolbroadcast @channel1 @channel2</code>",
            parse_mode="HTML")
        return
    uid = update.effective_user.id
    owner_edit_state[uid] = {"state": ST_KOLBROADCAST_MSG,
                             "kol_channels": wanted if wanted else None,
                             "kol_custom": bool(wanted),
                             "kol_unknown": unknown}
    scope = (f"to the owners of <b>{len(wanted)} channel(s)</b>" if wanted
             else "to <b>all KOL owners</b> (every listed channel)")
    warn = ""
    if unknown:
        warn = ("\n\n⚠️ Skipped (not tracked): " +
                ", ".join("@" + _display_handle(u) for u in unknown))
    await update.message.reply_text(
        f"📢 <b>KOL Broadcast</b> {scope}\n\n"
        f"Now send the template message (text, photo, or video with caption).\n\n"
        f"Use <code>{{Username}}</code> for the owner's username and "
        f"<code>{{Channel}}</code> for the channel name - each owner gets "
        f"their own values. Example: <code>Hello {{Username}}, your channel "
        f"{{Channel}} ...</code>\n\n"
        f"I'll show a preview first - nothing is sent until you tap Send."
        f"{warn}\n\n"
        f"Cancel with /cancel.",
        parse_mode="HTML")


@owner_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
    ),
    # E2: help text - the button mention "Channel Alerts" -> "KOL Alert".
    (
        '''    "/unsubscribe @channel - stop DM alerts. Channel Alerts - open /command "
    "and tap Channel Alerts to choose which alerts go to your channel. /linkinfo - how linking works. "''',
        '''    "/unsubscribe @channel - stop DM alerts. KOL Alert - open /command "
    "and tap KOL Alert to choose which alerts go to your channel. /linkinfo - how linking works. "''',
    ),
    # ── PICKER FIX (KOL_BROADCAST_NOV25) ──────────────────────────────────
    # E3: _chalert_user_channels - drop the admin/owner sees-all branch.
    # The picker is for a channel OWNER to set THEIR OWN channel's prefs,
    # so it lists ONLY linked channels this user owns (kol_owners).
    (
        '''def _chalert_user_channels(uid):
    # Linked channels this user can configure: ones they own (kol_owners) -
    # bot owners/admins see every linked channel.
    try:
        uid_i = int(uid)
    except Exception:
        return []
    linked = load_linked_channels() or {}
    if is_admin_or_owner(uid_i):
        return sorted(str(c).lstrip("@").lower() for c in linked.keys())
    owners = load_kol_owners() or {}''',
        '''def _chalert_user_channels(uid):
    # KOL_BROADCAST_NOV25: the Channel/KOL Alert picker is for a channel
    # OWNER to set THEIR OWN channel's alert preferences. It lists ONLY
    # linked channels this user owns (kol_owners). The old code returned
    # EVERY linked channel for the bot owner/admin - that is why ~139 KOL
    # channels showed in Real's picker. Owners never see other owners'
    # channels here; a channel with no recorded owner shows for nobody
    # (Add Channel links it and records the linker as owner).
    try:
        uid_i = int(uid)
    except Exception:
        return []
    linked = load_linked_channels() or {}
    owners = load_kol_owners() or {}''',
    ),
    # E4: async owner list (link owner + creator fallback) + picker_content
    # accepts a precomputed list.
    (
        '''    return sorted(mine)


def _chalert_picker_content(uid):
    mine = _chalert_user_channels(uid)''',
        '''    return sorted(mine)


async def _chalert_user_channels_async(bot, uid):
    # KOL_BROADCAST_NOV25: link-owner list PLUS the creator fallback.
    # A linked channel with NO recorded owner still shows for the user who
    # created the channel (checked via getChatAdministrators). This covers
    # Real's own channels if someone else linked them, and old links made
    # before kol_owners existed. Best-effort and bounded: a failed lookup
    # just leaves the channel out, and the whole check times out in 15s
    # so a slow network cannot hang the picker.
    mine = set(_chalert_user_channels(uid))
    if bot is None:
        return sorted(mine)
    try:
        uid_i = int(uid)
    except Exception:
        return sorted(mine)
    linked = load_linked_channels() or {}
    owners = load_kol_owners() or {}
    unknown = [str(c).lstrip("@").lower() for c in linked.keys()
               if str(c).lstrip("@").lower() not in owners]
    if not unknown:
        return sorted(mine)

    _sem = asyncio.Semaphore(10)

    async def _is_creator(ch):
        async with _sem:
            try:
                admins = await bot.get_chat_administrators(f"@{ch}")
                for m in admins or []:
                    u = getattr(m, "user", None)
                    if (getattr(m, "status", "") == "creator" and u is not None
                            and int(getattr(u, "id", -1)) == uid_i):
                        return ch
            except Exception:
                pass
            return None

    try:
        found = await asyncio.wait_for(
            asyncio.gather(*[_is_creator(c) for c in unknown]),
            timeout=15)
    except Exception:
        found = []
    for ch in found:
        if ch:
            mine.add(ch)
    return sorted(mine)


def _chalert_picker_content(uid, mine=None):
    # KOL_BROADCAST_NOV25: mine can be passed in (async owner list).
    if mine is None:
        mine = _chalert_user_channels(uid)''',
    ),
    # E5: show_picker uses the async owner list (bot from arg or query).
    (
        '''async def _chalert_show_picker(query):
    text, kb = _chalert_picker_content(query.from_user.id)
    await _send_screen(query, "channel_alerts", text, kb, media_cmd="channel_alerts")''',
        '''async def _chalert_show_picker(query, bot=None):
    # KOL_BROADCAST_NOV25: owner-only list (link owner + creator fallback).
    bot = bot or getattr(query, "bot", None)
    mine = await _chalert_user_channels_async(bot, query.from_user.id)
    text, kb = _chalert_picker_content(query.from_user.id, mine)
    await _send_screen(query, "channel_alerts", text, kb, media_cmd="channel_alerts")''',
    ),
    # E6: reply_picker uses the async owner list (bot from arg or message).
    (
        '''async def _chalert_reply_picker(msg, uid):
    # Send the Channel Picker as a plain reply (the Add Channel flow ends
    # with a Message, not a callback query, so _send_screen cannot be used).
    text, kb = _chalert_picker_content(uid)''',
        '''async def _chalert_reply_picker(msg, uid, bot=None):
    # Send the Channel Picker as a plain reply (the Add Channel flow ends
    # with a Message, not a callback query, so _send_screen cannot be used).
    # KOL_BROADCAST_NOV25: owner-only list (link owner + creator fallback).
    bot = bot or getattr(msg, "bot", None)
    mine = await _chalert_user_channels_async(bot, uid)
    text, kb = _chalert_picker_content(uid, mine)''',
    ),
    # E7: button_callback "channel_alerts" site passes context.bot.
    (
        '''    elif data == "channel_alerts":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_picker(query)''',
        '''    elif data == "channel_alerts":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_picker(query, context.bot)''',
    ),
    # E8: button_callback "chalert_pick" site passes context.bot.
    (
        '''    elif data == "chalert_pick":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_picker(query)''',
        '''    elif data == "chalert_pick":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_picker(query, context.bot)''',
    ),
    # E9: Add Channel /cancel site passes context.bot.
    (
        '''    if text.lower() in ("/cancel", "cancel"):
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_reply_picker(msg, update.effective_user.id)''',
        '''    if text.lower() in ("/cancel", "cancel"):
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_reply_picker(msg, update.effective_user.id, context.bot)''',
    ),
    # E10: Add Channel success site passes context.bot.
    (
        '''    kol_owners[channel] = u.id
    save_kol_owners(kol_owners)
    context.user_data.pop("chalert_add_channel", None)
    await _chalert_reply_picker(msg, update.effective_user.id)''',
        '''    kol_owners[channel] = u.id
    save_kol_owners(kol_owners)
    context.user_data.pop("chalert_add_channel", None)
    await _chalert_reply_picker(msg, update.effective_user.id, context.bot)''',
    ),
]


# ── runtime.py: KOL broadcast helpers + callback (before handle_message) ───
RT_HELPERS = r'''
# KOL_BROADCAST_NOV25 - personalised broadcast to KOL channel owners.
# /kolbroadcast: owner sends a template with {Username} / {Channel}; each
# listed channel's owner gets a DM with THEIR OWN username and channel
# name. Mirrors the normal Broadcast flow (preview -> Send / Rewrite /
# Cancel, recorded in broadcasts.json so /pinbroadcast, /replybroadcast,
# /editbroadcast and /deletebroadcast all work on it), but the text is
# rendered per recipient. No auto-pin (same rule as normal broadcasts).

_KOL_PLACEHOLDER_RE = re.compile(r"\{(username|channel)\}", re.IGNORECASE)


def _kol_html_escape(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _kol_display_name(username, first_name):
    # What {Username} becomes: @username, else first name, else "there".
    if username:
        return "@" + str(username).lstrip("@")
    if first_name:
        return str(first_name)
    return "there"


async def _kol_resolve_recipients(context, wanted):
    # Resolve one recipient per channel: {uid, username, first_name, channel}.
    # wanted: list of channel keys, or None for every tracked channel.
    # Owner lookup order: linked owner (kol_owners) first, then the channel
    # creator via getChatAdministrators. Returns (recipients, no_owner).
    # no_owner: channel keys with no owner found (bot not admin / API failed).
    # Recipients are sorted by channel name so the order is stable.
    if wanted:
        channels = [str(c).lstrip("@").lower() for c in wanted]
    else:
        channels = [str(c).lstrip("@").lower() for c in load_channels()]
    owners = load_kol_owners() or {}
    users = load_users_dict() or {}
    recipients = []
    no_owner = []
    for key in channels:
        uid = None
        username = None
        first_name = None
        try:
            raw = owners.get(key)
            uid = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            uid = None
        if uid is None:
            try:
                admins = await context.bot.get_chat_administrators(f"@{key}")
            except Exception as e:
                admins = None
                logger.warning(f"kolbroadcast: getChatAdministrators failed @{key}: {e}")
            if admins:
                for adm in admins:
                    if getattr(adm, "status", "") == "creator":
                        u = getattr(adm, "user", None)
                        if u is not None:
                            uid = getattr(u, "id", None)
                            username = getattr(u, "username", None)
                            first_name = getattr(u, "first_name", None)
                        break
        if uid is None:
            no_owner.append(key)
            continue
        if not username:
            rec = users.get(str(uid)) or {}
            username = rec.get("username") or username
            first_name = first_name or rec.get("name")
        if not username and not first_name:
            try:
                u = await context.bot.get_chat(uid)
                username = getattr(u, "username", None)
                first_name = getattr(u, "first_name", None)
            except Exception:
                pass
        recipients.append({"uid": int(uid), "username": username,
                           "first_name": first_name, "channel": key})
    recipients.sort(key=lambda r: r["channel"])
    return recipients, no_owner


def _kol_render_text_entities(text, entities, username, first_name, channel):
    # Render {Username}/{Channel} in text and shift entity offsets so
    # bold/italic/links/premium emoji still land on the right characters.
    # Returns (new_text, new_entities_or_None). Entities are copied, never
    # mutated in place, so the stored draft stays pristine for the next
    # recipient.
    import copy as _copy
    uname = _kol_display_name(username, first_name)
    chname = "@" + _display_handle(channel)
    matches = [(m.start(), m.end(),
                uname if m.group(1).lower() == "username" else chname)
               for m in _KOL_PLACEHOLDER_RE.finditer(text or "")]
    if not matches:
        return text, list(entities) if entities else None
    ents = [_copy.copy(e) for e in (entities or [])]
    out = text
    shift = 0
    for s, e, repl in matches:
        s2, e2 = s + shift, e + shift
        delta = len(repl) - (e - s)
        out = out[:s2] + repl + out[e2:]
        for ent in ents:
            o = getattr(ent, "offset", 0)
            l = getattr(ent, "length", 0)
            if o + l <= s2:
                continue
            if o >= e2:
                ent.offset = o + delta
            else:
                # Entity overlaps the replaced span: keep its start, stretch it.
                if o > s2:
                    ent.offset = s2
                ent.length = l + delta
        shift += delta
    return out, ents or None


def _kol_render_draft(draft, username, first_name, channel):
    # Return a copy of a stored broadcast draft with {Username}/{Channel}
    # replaced for one recipient (text + entities adjusted). Forward drafts
    # cannot be personalised - returned unchanged.
    kind = (draft or {}).get("kind")
    if kind == "text":
        txt, ents = _kol_render_text_entities(draft.get("text") or "",
                                              draft.get("entities"),
                                              username, first_name, channel)
        return {"kind": "text", "text": txt, "entities": ents}
    if kind in ("photo", "video"):
        cap, ents = _kol_render_text_entities(draft.get("caption") or "",
                                              draft.get("caption_entities"),
                                              username, first_name, channel)
        return {"kind": kind, "file_id": draft.get("file_id"),
                "caption": cap, "caption_entities": ents}
    return dict(draft or {})


def _kolbroadcast_preview_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Send", callback_data="kbc:send"),
        InlineKeyboardButton("✏️ Rewrite", callback_data="kbc:rewrite"),
    ], [
        InlineKeyboardButton("❌ Cancel", callback_data="kbc:cancel"),
    ]])


async def _kolbroadcast_show_preview(context, uid, draft, recipients, no_owner):
    # Show the template rendered for the FIRST recipient (so the owner sees
    # real values), plus the recipient count. Nothing is sent to owners here.
    first = recipients[0]
    shown = _kol_render_draft(draft, first.get("username"), first.get("first_name"), first.get("channel"))
    pv_ok = True
    try:
        if shown.get("kind") == "photo":
            await context.bot.send_photo(uid, photo=shown["file_id"], caption=shown.get("caption") or "", caption_entities=shown.get("caption_entities") or None)
        elif shown.get("kind") == "video":
            await context.bot.send_video(uid, video=shown["file_id"], caption=shown.get("caption") or "", caption_entities=shown.get("caption_entities") or None)
        elif shown.get("kind") == "text":
            await context.bot.send_message(uid, shown.get("text") or "", entities=shown.get("entities") or None)
        else:
            await context.bot.forward_message(uid, from_chat_id=shown["from_chat_id"], message_id=shown["message_id"])
    except Exception as e:
        pv_ok = False
        logger.warning(f"KOL broadcast preview send failed: {e}")
    head = "👀 <b>KOL Broadcast Preview</b>\n\n"
    if not pv_ok:
        head += "⚠️ Preview copy could not be sent (check the draft) - you can still Send or Cancel.\n\n"
    head += (f"This is how it looks for the first recipient "
             f"(<code>{_kol_html_escape(_kol_display_name(first.get('username'), first.get('first_name')))}</code> / "
             f"<code>@{_display_handle(first.get('channel'))}</code>). "
             f"<code>{{Username}}</code> and <code>{{Channel}}</code> change for each owner.\n\n")
    if shown.get("kind") == "forward":
        head += "ℹ️ Forwarded messages cannot be personalised - everyone gets the same forward.\n\n"
    head += (f"📩 <b>{len(recipients)} KOL owner(s)</b> will get this DM.\n")
    if no_owner:
        shown_no = ", ".join("@" + _display_handle(c) for c in no_owner[:10])
        more = f" and {len(no_owner) - 10} more" if len(no_owner) > 10 else ""
        head += (f"⚠️ No owner found for: {shown_no}{more} - they will be skipped.\n")
    head += "\nCheck everything, then tap <b>Send</b> - or <b>Rewrite</b> / <b>Cancel</b>."
    try:
        await context.bot.send_message(uid, head, parse_mode="HTML", reply_markup=_kolbroadcast_preview_kb())
    except Exception as e:
        logger.warning(f"KOL broadcast preview buttons failed: {e}")


async def _kolbroadcast_execute(context, draft, recipients, status_msg=None):
    # Send a personalised draft to every recipient (about 1 msg/sec).
    # Same resilience as the normal broadcast: RetryAfter -> sleep + retry
    # once; BadRequest parse/entities -> one plain-text retry; blocked ->
    # counted, never aborts the rest. Returns (ok, fail, blocked, sent_messages).
    ok = fail = blocked = 0
    sent_messages = []
    for i, r in enumerate(recipients):
        tid = r["uid"]
        shown = _kol_render_draft(draft, r.get("username"), r.get("first_name"), r.get("channel"))
        sent = None
        try:
            try:
                sent = await _broadcast_send_one(context, shown, tid)
            except RetryAfter as e_flood:
                wait_s = float(getattr(e_flood, "retry_after", 3)) + 1
                logger.warning(f"KOL broadcast flood-wait: sleeping {wait_s}s (tid={tid})")
                await asyncio.sleep(wait_s)
                sent = await _broadcast_send_one(context, shown, tid)
            except BadRequest as e_bad:
                err_str = str(e_bad).lower()
                if "parse" in err_str or "entities" in err_str:
                    sent = await _broadcast_send_one(context, shown, tid, plain=True)
                else:
                    raise
            ok += 1
            if sent is not None:
                sent_messages.append({"chat_id": tid, "message_id": sent.message_id})
        except Exception as e:
            err_str = str(e).lower()
            if isinstance(e, Forbidden) or any(x in err_str for x in ("deactivated", "deleted", "blocked", "bot was kicked", "user not found", "chat not found", "forbidden")):
                blocked += 1
            else:
                fail += 1
                logger.error(f"KOL broadcast send failed for {tid}: {e}")
        if i + 1 < len(recipients):
            await asyncio.sleep(1)
        if status_msg is not None and (i + 1) % 25 == 0:
            try:
                await status_msg.edit_text(f"⏳ Progress: {i+1}/{len(recipients)} owners done...")
            except Exception:
                pass
    return ok, fail, blocked, sent_messages


async def _kbc_confirm_send(query, context):
    # "Send" on a KOL broadcast preview: send the personalised draft to
    # every recipient, record it (so /pinbroadcast, /replybroadcast,
    # /editbroadcast and /deletebroadcast all work), and replace the
    # preview with the Done summary + Pin button.
    uid = query.from_user.id
    si = owner_edit_state.get(uid, {}) or {}
    if si.get("state") != ST_KOLBROADCAST_PREVIEW:
        try: await query.edit_message_text("⚠️ Preview expired - run /kolbroadcast again.")
        except Exception: pass
        return
    draft = si.get("draft") or {}
    recipients = si.get("recipients", []) or []
    no_owner = si.get("no_owner", []) or []
    is_media = bool(si.get("is_media"))
    if not draft or not recipients:
        owner_edit_state[uid] = {"state": None}
        try: await query.edit_message_text("⚠️ Draft not found - run /kolbroadcast again.")
        except Exception: pass
        return
    owner_edit_state[uid] = {"state": None}
    try:
        await query.edit_message_text(f"⏳ Sending to {len(recipients)} KOL owners...")
    except Exception:
        pass
    ok, fail, blocked, sent_messages = await _kolbroadcast_execute(
        context, draft, recipients, status_msg=query.message)
    bid = record_broadcast(sent_messages, is_media=is_media)
    no_owner_note = ""
    if no_owner:
        shown_no = ", ".join("@" + _display_handle(c) for c in no_owner[:10])
        more = f" and {len(no_owner) - 10} more" if len(no_owner) > 10 else ""
        no_owner_note = f"\n⚠️ No owner found (skipped): {shown_no}{more}"
    summary = (
        f"📢 <b>KOL Broadcast Done</b> (ID: <code>{bid}</code>)\n"
        f"✅ Sent: {ok} | 🚫 Blocked / never started the bot: {blocked} | ❌ Failed: {fail}"
        f"{no_owner_note}\n\n"
        f"If something is wrong:\n"
        f"<code>/editbroadcast {bid}</code> - edit in every DM (same text for all)\n"
        f"<code>/deletebroadcast {bid}</code> - delete from every DM\n"
        f"<code>/pinbroadcast {bid}</code> - pin in every DM\n"
        f"(You can also run these without an ID - the latest broadcast is used.)"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📌 Pin", callback_data=f"kbc:pin:{bid}")]])
    try:
        await query.edit_message_text(summary, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await context.bot.send_message(uid, summary, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning(f"KOL broadcast done summary failed: {e}")


async def cb_kolbroadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # KOL broadcast preview / pin callbacks (callback_data "kbc:...").
    # Owner-only. kbc:send / kbc:rewrite / kbc:cancel / kbc:pin:<bid>.
    query = update.callback_query
    uid = query.from_user.id if query.from_user else None
    data = query.data or ""
    if uid not in OWNER_IDS:
        try: await query.answer("Owner only.", show_alert=True)
        except Exception: pass
        return
    try: await query.answer()
    except Exception: pass
    if data == "kbc:send":
        await _kbc_confirm_send(query, context)
        return
    if data == "kbc:rewrite":
        si = owner_edit_state.get(uid, {}) or {}
        if si.get("state") != ST_KOLBROADCAST_PREVIEW:
            try: await query.edit_message_text("⚠️ Preview expired - run /kolbroadcast again.")
            except Exception: pass
            return
        owner_edit_state[uid] = {"state": ST_KOLBROADCAST_MSG,
                                 "kol_channels": si.get("kol_channels"),
                                 "kol_custom": si.get("kol_custom"),
                                 "kol_unknown": si.get("kol_unknown", [])}
        try:
            await query.edit_message_text(
                "✏️ <b>Rewrite</b>\n\nSend the new template message (text, photo, or video with caption).\n\n"
                "Use <code>{Username}</code> for the owner's username and "
                "<code>{Channel}</code> for the channel name.",
                parse_mode="HTML")
        except Exception:
            pass
        return
    if data == "kbc:cancel":
        owner_edit_state[uid] = {"state": None}
        try: await query.edit_message_text("❌ Cancelled - nothing was sent.")
        except Exception: pass
        return
    if data.startswith("kbc:pin:"):
        bid = data.split(":", 2)[2].strip()
        ok, fail, total = await _broadcast_pin_all(context, bid)
        if total < 0:
            try: await query.edit_message_text(f"⚠️ Broadcast {bid} not found - check /listbroadcasts.")
            except Exception: pass
            return
        try:
            await query.edit_message_text(
                f"📌 <b>Broadcast {bid} Pinned</b>\n"
                f"✅ Pinned: {ok} | ⚠️ Could not pin (deleted/blocked): {fail}",
                parse_mode="HTML")
        except Exception:
            pass
        return
'''


# ── runtime.py: state branches (inserted before ST_EDIT_BROADCAST_MSG) ─────
RT_BRANCHES = r'''
        elif state == ST_KOLBROADCAST_MSG:
            # KOL_BROADCAST_NOV25: owner sent the template - resolve the
            # channel owners first (linked owner, else channel creator),
            # then show a preview rendered for the first recipient.
            # Nothing is sent to owners until "Send" is tapped.
            draft = _broadcast_draft_from_msg(msg)
            status = None
            try:
                status = await msg.reply_text("⏳ Resolving channel owners...")
            except Exception:
                pass
            recipients, no_owner = await _kol_resolve_recipients(context, si.get("kol_channels"))
            if status is not None:
                try: await status.delete()
                except Exception: pass
            if not recipients:
                owner_edit_state[uid] = {"state": None}
                no_txt = ""
                if no_owner:
                    no_txt = "\n\nNo owner found for: " + ", ".join("@" + _display_handle(c) for c in no_owner[:10])
                await msg.reply_text(
                    "⚠️ No channel owners found - nothing to send." + no_txt +
                    "\n\nCheck that the channels are tracked and the bot is admin in them, then try again.",
                    parse_mode="HTML")
                return
            owner_edit_state[uid] = {"state": ST_KOLBROADCAST_PREVIEW,
                                     "draft": draft,
                                     "recipients": recipients,
                                     "no_owner": no_owner,
                                     "is_media": bool(msg.photo or msg.video),
                                     "kol_channels": si.get("kol_channels"),
                                     "kol_custom": si.get("kol_custom"),
                                     "kol_unknown": si.get("kol_unknown", [])}
            await _kolbroadcast_show_preview(context, uid, draft, recipients, no_owner)
            return

        elif state == ST_KOLBROADCAST_PREVIEW:
            # Preview is open - nothing is sent from a message; use the buttons.
            await msg.reply_text(
                "👀 Preview is open - nothing has been sent yet.\n\n"
                "Use the buttons below:\n"
                "✅ <b>Send</b> - send to all KOL owners\n"
                "✏️ <b>Rewrite</b> - write a new template\n"
                "❌ <b>Cancel</b> - send nothing",
                parse_mode="HTML"); return

'''

# ── runtime.py: registrations ───────────────────────────────────────────────
RUNTIME_EDITS = [
    # E1: helpers + callback, inserted before handle_message (same spot the
    # Nov 12 broadcast patch used).
    (
        "async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):",
        RT_HELPERS + "\nasync def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):",
    ),
    # E2: state branches, inserted before the ST_EDIT_BROADCAST_MSG branch.
    (
        "        elif state == ST_EDIT_BROADCAST_MSG:",
        RT_BRANCHES + "        elif state == ST_EDIT_BROADCAST_MSG:",
    ),
    # E3: register the kbc: callback right after the bc: callback.
    (
        '    app.add_handler(CallbackQueryHandler(cb_broadcast, pattern=r"^bc:"))',
        '    app.add_handler(CallbackQueryHandler(cb_broadcast, pattern=r"^bc:"))\n    app.add_handler(CallbackQueryHandler(cb_kolbroadcast, pattern=r"^kbc:"))  # KOL_BROADCAST_NOV25',
    ),
    # E4: register /kolbroadcast right after /broadcast.
    (
        '    app.add_handler(CommandHandler("broadcast",      cmd_broadcast))',
        '    app.add_handler(CommandHandler("broadcast",      cmd_broadcast))\n    app.add_handler(CommandHandler("kolbroadcast",   cmd_kolbroadcast))  # KOL_BROADCAST_NOV25',
    ),
]


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    core = resolve(base, "core.py")
    cmds = resolve(base, "commands.py")
    rt = resolve(base, "runtime.py")
    ok = True
    if not patch_one(core, CORE_EDITS):
        ok = False
    if not patch_one(cmds, COMMANDS_EDITS):
        ok = False
    if not patch_one(rt, RUNTIME_EDITS):
        ok = False
    print("ALL OK" if ok else "SOME FAILED - check the FAIL lines above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
