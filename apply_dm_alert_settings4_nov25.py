# apply_dm_alert_settings4_nov25.py - DM Alert Settings: Channel Alerts (user GO Nov 25 ~06:07 PKT)
# Markers:
#   DM_ALERT_SETTINGS4_NOV25        - commands.py (Channel-line removal, Channel Alerts
#                                     screens, /linkme + /linksmart removal) + x_alert.py
#                                     (channel prefs + enforcement) + core.py (button)
#                                     + runtime.py (registrations + Add Channel hook)
#   DM_ALERT_SETTINGS4_OH_NOV25     - commands.py OwnerHelp entries only
#   DM_ALERT_SETTINGS4_DIPFWD_NOV25 - x_alert.py dip-forward gate only
# User spec: ~/workspace/goals/wizardscan-bot-issue-fixes/files/dm-alert-settings-spec-nov25.md
# Section 14. Base: patches 1+2+3 already deployed live; anchors match that state.
#
# WHAT IT DOES:
#  1. Removes the "Channel: @Name" line from the DM Alert Settings, Milestone
#     and DIP screens (owner: it did not look right on the page). The Channel
#     Picker stays; callbacks still carry the channel.
#  2. Removes /linkme and /linksmart ENTIRELY (handlers, runtime registration,
#     BotCommand menu entries, OwnerHelp entries, public-command lists).
#     Existing linked channels STOP getting forwards through the old link
#     system - their owners must re-set levels via the new Channel Alerts
#     button. /linkinfo and the DEFAULT_LINKME_INFO text are left alone
#     (they do not call the removed handlers).
#  3. Adds a "Channel Alerts" button in All Commands (core.py
#     build_command_keyboard, right after DM Alerts). It opens the SAME
#     settings as DM Alert (Channel Picker first, then Milestone / DIP
#     screens, same tick/cross, same English), but the choices govern
#     CHANNEL forwards (posts forwarded TO a channel), not DM forwards.
#  4. Channel prefs are per-CHANNEL (not per user), stored in the same
#     data/dm_alert_prefs.json under the top-level "channel" key:
#     {"channel": {"<channel>": {"x": ..., "dip": ...}}}.
#     Enforcement: linked-channel forwards (str targets) and the auto-forward
#     to the KOL's own channel are gated by that channel's X choice
#     (default all). /linksmart's "smart" tier gate is RETIRED - the channel
#     choice is now the single source of truth. The dip owner forward is
#     gated by BOTH the owner's DM dip choice (patch 3) AND the channel's
#     dip choice (this patch); dip alerts are never forwarded to a KOL
#     channel, so the channel dip setting gates the only dip forward that
#     exists for the channel. Default all everywhere, so nothing changes
#     until a channel owner sets a choice.
#  5. Media power for Channel Alerts: /setchannelmedia + /clearchannelmedia
#     (owner-only, reply to a photo/video), stored in
#     config["command_media"]["channel_alerts"], used by the Channel Alerts
#     screens. Listed in OwnerHelp with NEW marking.
# English ONLY in all new user-facing text. No new code files: everything
# goes into existing commands.py / x_alert.py / core.py / runtime.py.
# Usage: python3 apply_dm_alert_settings4_nov25.py [/opt/bot | commands.py | ...]
#        (accepts a directory OR any one of the files; the others are resolved
#        from the same directory)
import os
import sys

MARKER = "DM_ALERT_SETTINGS4_NOV25"
MARKER_OH = "DM_ALERT_SETTINGS4_OH_NOV25"
MARKER_DIPFWD = "DM_ALERT_SETTINGS4_DIPFWD_NOV25"


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


def remove_link_cmds(path, backup_path):
    """Delete cmd_linkme + cmd_linksmart function definitions from commands.py.
    cmd_linkme runs up to cmd_linksmart; cmd_linksmart runs up to the Lookup
    section header. Returns True on success. Idempotent: if both defs are
    already gone, returns True at once. On failure restores `path` from
    `backup_path` (the patch_one backup) and returns False, so the file is
    left exactly as patch_one left it.
    """
    with open(path, encoding="utf-8") as f:
        src = f.read()
    i1 = src.find("\nasync def cmd_linkme(")
    i2 = src.find("\nasync def cmd_linksmart(")
    if i1 < 0 and i2 < 0:
        print("OK (commands.py): cmd_linkme + cmd_linksmart already removed")
        return True
    if i1 < 0 or i2 < 0:
        print("FAIL: only one of cmd_linkme/cmd_linksmart present (i1=%d i2=%d)" % (i1, i2))
        return False
    try:
        i3 = src.find("\n# ─── Lookup ───", i2 + 1) if i2 >= 0 else -1
        if i3 < 0:
            print("FAIL: Lookup header not found after cmd_linksmart")
            raise ValueError("lookup header not found")
        if src.count("\nasync def cmd_linkme(") != 1 or src.count("\nasync def cmd_linksmart(") != 1:
            print("FAIL: linkme/linksmart def count != 1")
            raise ValueError("link def count")
        span_me = src[i1 + 1:i2]
        span_smart = src[i2 + 1:i3]
        if "DEFAULT_LINKME_INFO" not in span_me or "load_linked_channels()" not in span_me:
            print("FAIL: cmd_linkme span does not look like linkme")
            raise ValueError("linkme span")
        if "SMART_LINK_MILESTONES" not in span_smart or "load_linked_channels()" not in span_smart:
            print("FAIL: cmd_linksmart span does not look like linksmart")
            raise ValueError("linksmart span")
        prefix = src[:i1 + 1].rstrip("\n")
        suffix = src[i3:].lstrip("\n")
        new_src = prefix + "\n\n\n" + suffix
        if "cmd_linkme" in new_src or "cmd_linksmart" in new_src:
            print("FAIL: linkme/linksmart references remain after removal")
            raise ValueError("refs remain")
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_src)
        print("OK (commands.py): cmd_linkme + cmd_linksmart removed")
        return True
    except Exception as e:
        print("FAIL: remove_link_cmds: %s - restoring backup" % e)
        with open(backup_path, encoding="utf-8") as f:
            orig = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(orig)
        return False


# ── commands.py: Channel-line removal + Channel Alerts + link removal ───────
COMMANDS_EDITS = [
    # E1: remove the "Channel: @Name" line from the DM Alert Settings screen
    # (owner order Nov 25 ~04:34 PKT - it did not look right on the page).
    (
        r"""async def _dmset_show_main(query, channel=None):
    text = DMSET_MAIN_TEXT
    if channel:
        text = text.replace("<b>DM ALERT Settings</b>\n\n",
                            "<b>DM ALERT Settings</b>\nChannel: @" + _display_handle(channel) + "\n\n", 1)
    await _send_screen(query, "dm_settings", text, _dmset_main_kb(channel),
                       media_cmd="dm_settings")""",
        r"""async def _dmset_show_main(query, channel=None):
    # DM_ALERT_SETTINGS4_NOV25: the "Channel: @Name" line was removed by
    # owner order (it did not look right on the page). The picker already
    # tells the user which channel they picked; callbacks still carry it.
    await _send_screen(query, "dm_settings", DMSET_MAIN_TEXT, _dmset_main_kb(channel),
                       media_cmd="dm_settings")""",
    ),
    # E2: remove the "Channel: @Name" line from the Milestone screen
    (
        r"""async def _dmset_show_milestone(query, channel=None):
    text = DMSET_MILESTONE_TEXT
    if channel:
        text = text.replace("<b>Customize Your X Alert Preferences</b>\n\n",
                            "<b>Customize Your X Alert Preferences</b>\nChannel: @" + _display_handle(channel) + "\n\n", 1)
    await _send_screen(query, "dm_settings", text,
                       _dmset_milestone_kb(query.from_user.id, channel),
                       media_cmd="dm_settings")""",
        r"""async def _dmset_show_milestone(query, channel=None):
    # DM_ALERT_SETTINGS4_NOV25: "Channel: @Name" line removed (owner order).
    await _send_screen(query, "dm_settings", DMSET_MILESTONE_TEXT,
                       _dmset_milestone_kb(query.from_user.id, channel),
                       media_cmd="dm_settings")""",
    ),
    # E3: remove the "Channel: @Name" line from the DIP screen
    (
        r"""async def _dmset_show_dip(query, channel=None):
    text = DMSET_DIP_TEXT
    if channel:
        text = text.replace("<b>Customize Your Dip Profit Alert Preferences</b>\n\n",
                            "<b>Customize Your Dip Profit Alert Preferences</b>\nChannel: @" + _display_handle(channel) + "\n\n", 1)
    await _send_screen(query, "dm_settings", text,
                       _dmset_dip_kb(query.from_user.id, channel),
                       media_cmd="dm_settings")""",
        r"""async def _dmset_show_dip(query, channel=None):
    # DM_ALERT_SETTINGS4_NOV25: "Channel: @Name" line removed (owner order).
    await _send_screen(query, "dm_settings", DMSET_DIP_TEXT,
                       _dmset_dip_kb(query.from_user.id, channel),
                       media_cmd="dm_settings")""",
    ),
    # E4: Channel Alerts screens + picker + Add Channel + media commands
    # (inserted before cmd_setdmmedia, same anchor patch 3 used).
    (
        """@owner_only
async def cmd_setdmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
        r"""# ── Channel Alert Settings (DM_ALERT_SETTINGS4_NOV25) ─────────────────────
# Same screens as DM Alert Settings (same text shape, same tick/cross, same
# English), but the choices govern CHANNEL forwards (posts forwarded TO a
# channel), not DM forwards. Replaces /linkme (all levels) and /linksmart
# (solid tiers only), both removed by this patch. The Channel Alerts button
# lives in All Commands (build_command_keyboard, core.py).
# Choices are saved per CHANNEL in data/dm_alert_prefs.json under the
# top-level "channel" key: {"channel": {"<channel>": {"x": ..., "dip": ...}}}
# (helpers in x_alert.py). The picker lists LINKED channels the user owns
# (kol_owners) - bot owners see every linked channel. Add Channel links a
# new channel with the SAME admin check /linkme used, then reopens the
# picker. Media: config["command_media"]["channel_alerts"] via
# /setchannelmedia; text-only if unset.
CHALERT_MAIN_TEXT = (
    f'{PE_CRYSTAL} <b>CHANNEL ALERT Settings</b>\n\n'
    'Choose which alerts WIZARD SCAN forwards directly to your channel, and '
    'customize your notification preferences to stay updated on the milestones '
    'and activity that matter most to your community.\n\n'
    f'{PE_WAND} <b>Milestone Alerts</b>\n\n'
    'To configure your normal X alerts, click the Milestone Alerts button and '
    'set your preferred milestones according to your needs.\n\n'
    f'{PE_WAND} <b>DIP Profit Alerts</b>\n\n'
    "We've added a new Dip Profit feature! You can configure its settings as "
    'well. Simply click the DIP Alerts button to set your preferences.'
)

CHALERT_MILESTONE_TEXT = (
    f'{PE_CRYSTAL} <b>Customize Your X Alert Preferences</b>\n\n'
    'Click the buttons below to select your preferred X alert notifications.\n\n'
    f'{PE_WAND} <b>All X Alerts</b>\n\n'
    'With the All X Alerts button, your channel will receive every X milestone '
    'alert.\n\n'
    f'{PE_WAND} <b>Standard Milestones</b>\n\n'
    'Receive alerts at 2X, 5X, 10X, 15X, 20X, 25X, 30X and every 5X milestone '
    'up to 100X, followed by 200X, 300X and beyond.\n\n'
    f'{PE_WAND} <b>Major Milestones</b>\n\n'
    'Receive fewer notifications at major milestones: 2X, 10X, 20X, 50X, 100X, '
    '200X, 300X and beyond.\n\n'
    f'{PE_WAND} <b>Disable X Alerts</b>\n\n'
    'Stop receiving all X milestone alerts in your channel.'
)

CHALERT_DIP_TEXT = (
    f'{PE_CRYSTAL} <b>Customize Your Dip Profit Alert Preferences</b>\n\n'
    'Choose how WIZARD SCAN forwards Dip Profit milestone alerts directly to '
    'your channel. Select the notification frequency that best suits your preferences.\n\n'
    f'{PE_WAND} <b>All Dip Alerts</b>\n\n'
    'Receive every available Dip Profit milestone alert, including 2X, 3X, 4X, '
    '5X, 6X and all subsequent milestones.\n\n'
    f'{PE_WAND} <b>Standard Dip Alerts</b>\n\n'
    'Receive alerts at 2X, 5X, 10X, 15X, 20X, 25X, 30X and every 5X milestone '
    'up to 100X, followed by 200X, 300X and beyond.\n\n'
    f'{PE_WAND} <b>Major Dip Alerts</b>\n\n'
    'Receive fewer notifications at major milestones: 2X, 10X, 20X, 30X, 50X, '
    '100X, 200X, 300X and beyond.\n\n'
    f'{PE_WAND} <b>Disable Dip Alerts</b>\n\n'
    'Stop receiving all Dip Profit milestone alerts in your channel.'
)

CHALERT_PICKER_TEXT = (
    f'{PE_CRYSTAL} <b>Which channel do you want alerts for?</b>\n\n'
    'Pick a channel below to set its Channel Alert preferences. '
    'Tap Add Channel to link a new one.'
)

CHALERT_PICKER_EMPTY_TEXT = (
    f'{PE_CRYSTAL} <b>Which channel do you want alerts for?</b>\n\n'
    "You haven't linked any channel yet. "
    'Tap Add Channel to link one, then come back here to set its alerts.'
)

CHALERT_ADD_TEXT = (
    f'{PE_CRYSTAL} <b>Add Channel</b>\n\n'
    'Send the channel username, like @Trenchmarkgems.\n\n'
    "I'll link it and bring you back here to set its alerts. "
    'Send /cancel to go back.'
)


def _chalert_main_kb(channel=None):
    suffix = ("_" + channel) if channel else ""
    return InlineKeyboardMarkup([
        [_icon_kb("Milestone Alerts", DMSET_EMOJI_MAIN, callback_data="chalert_milestone" + suffix)],
        [_icon_kb("DIP Alerts", DMSET_EMOJI_MAIN, callback_data="chalert_dip" + suffix)],
        [InlineKeyboardButton("Back", callback_data="chalert_pick")],
    ])


def _chalert_milestone_kb(channel=None):
    cur = channel_alert_x_choice(channel)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        cb = "chalert_x_" + choice + ("@" + channel if channel else "")
        return _icon_kb(label, icon, callback_data=cb)
    suffix = ("_" + channel) if channel else ""
    return InlineKeyboardMarkup([
        [_opt("All X Alerts", "all"), _opt("Standard Milestones", "standard")],
        [_opt("Major Milestones", "major"), _opt("Disable X Alerts", "disable")],
        [InlineKeyboardButton("DIP ALERT Setting", callback_data="chalert_dip" + suffix),
         InlineKeyboardButton("BACK", callback_data="chalert_main" + suffix)],
    ])


def _chalert_dip_kb(channel=None):
    cur = channel_alert_dip_choice(channel)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        cb = "chalert_dip_" + choice + ("@" + channel if channel else "")
        return _icon_kb(label, icon, callback_data=cb)
    suffix = ("_" + channel) if channel else ""
    return InlineKeyboardMarkup([
        [_opt("All Dip Alerts", "all"), _opt("Standard Dip Alerts", "standard")],
        [_opt("Major Dip Alerts", "major"), _opt("Disable Dip Alerts", "disable")],
        [InlineKeyboardButton("BACK", callback_data="chalert_main" + suffix)],
    ])


async def _chalert_show_main(query, channel=None):
    await _send_screen(query, "channel_alerts", CHALERT_MAIN_TEXT, _chalert_main_kb(channel),
                       media_cmd="channel_alerts")


async def _chalert_show_milestone(query, channel=None):
    await _send_screen(query, "channel_alerts", CHALERT_MILESTONE_TEXT,
                       _chalert_milestone_kb(channel),
                       media_cmd="channel_alerts")


async def _chalert_show_dip(query, channel=None):
    await _send_screen(query, "channel_alerts", CHALERT_DIP_TEXT,
                       _chalert_dip_kb(channel),
                       media_cmd="channel_alerts")


def _chalert_user_channels(uid):
    # Linked channels this user can configure: ones they own (kol_owners) -
    # bot owners/admins see every linked channel.
    try:
        uid_i = int(uid)
    except Exception:
        return []
    linked = load_linked_channels() or {}
    if is_admin_or_owner(uid_i):
        return sorted(str(c).lstrip("@").lower() for c in linked.keys())
    owners = load_kol_owners() or {}
    mine = set()
    for ch in linked.keys():
        try:
            if int(owners.get(str(ch).lstrip("@").lower())) == uid_i:
                mine.add(str(ch).lstrip("@").lower())
        except Exception:
            continue
    return sorted(mine)


def _chalert_picker_content(uid):
    mine = _chalert_user_channels(uid)
    if mine:
        rows = [[InlineKeyboardButton("@" + _display_handle(ch),
                                      callback_data="chalert_ch_" + ch)]
                for ch in mine]
        kb = InlineKeyboardMarkup(
            rows + [[InlineKeyboardButton("➕ Add Channel", callback_data="chalert_add")],
                    [_back_btn()]])
        return CHALERT_PICKER_TEXT, kb
    return CHALERT_PICKER_EMPTY_TEXT, InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Channel", callback_data="chalert_add")],
        [_back_btn()],
    ])


async def _chalert_show_picker(query):
    text, kb = _chalert_picker_content(query.from_user.id)
    await _send_screen(query, "channel_alerts", text, kb, media_cmd="channel_alerts")


async def _chalert_show_add(query):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="chalert_pick")]])
    await _send_screen(query, "channel_alerts", CHALERT_ADD_TEXT, kb, media_cmd="channel_alerts")


async def _chalert_reply_picker(msg, uid):
    # Send the Channel Picker as a plain reply (the Add Channel flow ends
    # with a Message, not a callback query, so _send_screen cannot be used).
    text, kb = _chalert_picker_content(uid)
    text, _ents = _stored_text_entities(text, "")
    bm = get_command_media("channel_alerts")
    if bm and bm.get("file_id"):
        try:
            if bm.get("type") == "photo":
                if _ents:
                    await msg.reply_photo(photo=bm["file_id"], caption=text,
                                          caption_entities=_ents, reply_markup=kb)
                else:
                    await msg.reply_photo(photo=bm["file_id"], caption=text,
                                          parse_mode="HTML", reply_markup=kb)
            else:
                if _ents:
                    await msg.reply_video(video=bm["file_id"], caption=text,
                                          caption_entities=_ents, reply_markup=kb)
                else:
                    await msg.reply_video(video=bm["file_id"], caption=text,
                                          parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    if _ents:
        await msg.reply_text(text, entities=_ents, reply_markup=kb,
                             disable_web_page_preview=True)
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=kb,
                             disable_web_page_preview=True)


async def chalert_on_add_channel_text(update, context):
    # User tapped Add Channel and sent a channel username. Link it with the
    # SAME admin check /linkme used (requester must be an admin; a private
    # channel skips the check and is trusted), then show the Channel Picker
    # with the new channel. Returns True when the message was consumed.
    msg = update.message
    text = (msg.text or "").strip()
    if not text:
        return False
    if text.lower() in ("/cancel", "cancel"):
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_reply_picker(msg, update.effective_user.id)
        return True
    channel = _norm_channel_arg(text)
    tracked = [c.lower() for c in load_channels()]
    if not channel or channel not in tracked:
        await msg.reply_text(
            "I couldn't find that channel. Check the username and try again.",
            parse_mode="HTML")
        return True
    u = update.effective_user
    is_admin = False
    try:
        member = await context.bot.get_chat_member(f"@{channel}", u.id)
        if member.status in ("administrator", "creator"):
            is_admin = True
    except Exception:
        pass  # Channel may be private - skip admin check, trust the user
    if not is_admin:
        await msg.reply_text(
            f"Only admins of @{channel} can change its Channel Alert settings.\n\n"
            "Please make sure you are an admin of this channel and "
            "@WIZARD_SCAN_BOT is also added as admin with post permission.",
            parse_mode="HTML")
        return True
    linked = load_linked_channels()
    linked[channel] = f"@{channel}"
    save_linked_channels(linked)
    kol_owners = load_kol_owners()
    kol_owners[channel] = u.id
    save_kol_owners(kol_owners)
    context.user_data.pop("chalert_add_channel", None)
    await _chalert_reply_picker(msg, update.effective_user.id)
    return True


@owner_only
async def cmd_setchannelmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reply to a photo/video with /setchannelmedia to set the media shown on
    # every Channel Alert Settings reply. Stored in
    # config["command_media"]["channel_alerts"]. English replies (user rule).
    msg = update.message
    reply = msg.reply_to_message
    if not reply:
        await msg.reply_text(
            "📸 Reply to a photo or video with <code>/setchannelmedia</code>.",
            parse_mode="HTML")
        return
    if reply.video:
        fid = reply.video.file_id; ftype = "video"
    elif reply.photo:
        fid = reply.photo[-1].file_id; ftype = "photo"
    elif reply.document and reply.document.mime_type and reply.document.mime_type.startswith("video"):
        fid = reply.document.file_id; ftype = "video"
    else:
        await msg.reply_text("❌ Please reply to a photo or video only.")
        return
    c = load_config()
    cm = c.get("command_media", {})
    cm["channel_alerts"] = {"file_id": fid, "type": ftype}
    c["command_media"] = cm
    save_config(c)
    await msg.reply_text(
        f"✅ <b>Channel Alert Settings</b> media set! ({ftype})\n\n"
        "This media will now show on every Channel Alert settings reply.",
        parse_mode="HTML")


@owner_only
async def cmd_clearchannelmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = load_config()
    cm = c.get("command_media", {})
    if "channel_alerts" in cm:
        del cm["channel_alerts"]
        c["command_media"] = cm
        save_config(c)
        await update.message.reply_text("✅ Channel Alert Settings media removed. Replies will be text-only now.")
    else:
        await update.message.reply_text("No media is set for Channel Alert Settings.")


@owner_only
async def cmd_setdmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
    ),
    # E5: Channel Alerts callback branches (right after the dmset_x branch).
    (
        """    elif data.startswith("dmset_x_"):
        context.user_data.pop("dmset_add_channel", None)
        rest = data[len("dmset_x_"):]
        if "@" in rest:
            choice, ch = rest.split("@", 1)
            dm_alert_x_set(query.from_user.id, ch.lstrip("@").lower(), choice)
            await _dmset_show_milestone(query, ch.lstrip("@").lower())
        else:
            dm_alert_x_set(query.from_user.id, None, rest)
            await _dmset_show_milestone(query)""",
        """    elif data.startswith("dmset_x_"):
        context.user_data.pop("dmset_add_channel", None)
        rest = data[len("dmset_x_"):]
        if "@" in rest:
            choice, ch = rest.split("@", 1)
            dm_alert_x_set(query.from_user.id, ch.lstrip("@").lower(), choice)
            await _dmset_show_milestone(query, ch.lstrip("@").lower())
        else:
            dm_alert_x_set(query.from_user.id, None, rest)
            await _dmset_show_milestone(query)

    # ── Channel Alerts (DM_ALERT_SETTINGS4_NOV25) ────────────────────────
    elif data == "channel_alerts":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_picker(query)

    elif data == "chalert_pick":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_picker(query)

    elif data == "chalert_add":
        context.user_data["chalert_add_channel"] = True
        await _chalert_show_add(query)

    elif data.startswith("chalert_ch_"):
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_main(query, data[len("chalert_ch_"):].lstrip("@").lower())

    elif data == "chalert_main":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_main(query)

    elif data.startswith("chalert_main_"):
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_main(query, data[len("chalert_main_"):].lstrip("@").lower())

    elif data == "chalert_milestone":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_milestone(query)

    elif data.startswith("chalert_milestone_"):
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_milestone(query, data[len("chalert_milestone_"):].lstrip("@").lower())

    elif data == "chalert_dip":
        context.user_data.pop("chalert_add_channel", None)
        await _chalert_show_dip(query)

    elif data.startswith("chalert_dip_"):
        context.user_data.pop("chalert_add_channel", None)
        rest = data[len("chalert_dip_"):]
        if "@" in rest:
            choice, ch = rest.split("@", 1)
            channel_alert_dip_set(ch.lstrip("@").lower(), choice)
            await _chalert_show_dip(query, ch.lstrip("@").lower())
        elif rest in ("all", "standard", "major", "disable"):
            channel_alert_dip_set(None, rest)
            await _chalert_show_dip(query)
        else:
            await _chalert_show_dip(query, rest.lstrip("@").lower())

    elif data.startswith("chalert_x_"):
        context.user_data.pop("chalert_add_channel", None)
        rest = data[len("chalert_x_"):]
        if "@" in rest:
            choice, ch = rest.split("@", 1)
            channel_alert_x_set(ch.lstrip("@").lower(), choice)
            await _chalert_show_milestone(query, ch.lstrip("@").lower())
        else:
            channel_alert_x_set(None, rest)
            await _chalert_show_milestone(query)""",
    ),
    # E6: /linkme + /linksmart out of PUBLIC_MEDIA_CMDS and PUBLIC_TEXT_CMDS
    (
        """PUBLIC_MEDIA_CMDS = [
    "start", "command", "submit", "subscribe", "linkme", "linksmart", "linkinfo", "history",
]""",
        """PUBLIC_MEDIA_CMDS = [
    "start", "command", "submit", "subscribe", "linkinfo", "history",
]""",
    ),
    (
        """PUBLIC_TEXT_CMDS = ["submit", "subscribe", "linkme", "linksmart", "linkinfo", "history"]""",
        """PUBLIC_TEXT_CMDS = ["submit", "subscribe", "linkinfo", "history"]""",
    ),
    # E7: /linkme + /linksmart out of the public-command list/descriptions
    # (the live list is the "start/command/submit/subscribe/..." one, not
    # the submit-first variant - verified against the patched test file).
    (
        """_PUB_CMD_LIST = ["start", "command", "submit", "subscribe", "linkme", "linksmart",
                 "linkinfo", "history"]
_PUB_CMD_DESC = {
    "start": "/start — bot ka welcome screen.",
    "command": "/command — Command Center menu.",
    "submit": "/submit — KOL request info.",
    "subscribe": "/subscribe — DM alerts info.",
    "linkme": "/linkme — channel link info.",
    "linksmart": "/linksmart — smart link info (sirf solid milestones).",
    "linkinfo": "/linkinfo — /linkme ka tareeqa.",
    "history": "/history — history info (bina @channel ke).",
}""",
        """_PUB_CMD_LIST = ["start", "command", "submit", "subscribe",
                 "linkinfo", "history"]
_PUB_CMD_DESC = {
    "start": "/start — bot ka welcome screen.",
    "command": "/command — Command Center menu.",
    "submit": "/submit — KOL request info.",
    "subscribe": "/subscribe — DM alerts info.",
    "linkinfo": "/linkinfo — /linkme ka tareeqa.",
    "history": "/history — history info (bina @channel ke).",
}""",
    ),
    # E8: /settext tutorial entry - drop "linkme, " from the commands list
    # (raw string: the entry stores literal \n escapes in the source).
    (
        r"""        ('settext', 'Kisi public command ka info text set karo.\nUsage: /settext <command>\nCommands: subscribe, history, linkme, linkinfo, submit.'),""",
        r"""        ('settext', 'Kisi public command ka info text set karo.\nUsage: /settext <command>\nCommands: subscribe, history, linkinfo, submit.'),""",
    ),
    # E9: cmd_settext docstring - drop "linkme|" from the settable list.
    # (Only the docstring content is replaced; the docstring quotes stay.)
    (
        "Set the info text of a public command: /settext subscribe|history|linkme|linkinfo|submit",
        "Set the info text of a public command: /settext subscribe|history|linkinfo|submit",
    ),
    # E10: public-commands help text - the /linkme sentence now points at
    # the Channel Alerts button in All Commands (/linkinfo stays, it is a
    # separate command left alone - see the open items in the note).
    (
        '''    "/unsubscribe @channel - stop DM alerts. /linkme @channel - link your "
    "channel to get its alerts. /linkinfo - how linking works. "''',
        '''    "/unsubscribe @channel - stop DM alerts. Channel Alerts - open /command "
    "and tap Channel Alerts to choose which alerts go to your channel. /linkinfo - how linking works. "''',
    ),
]


# ── commands.py: OwnerHelp entries (separate marker, patch 2 pattern) ──────
COMMANDS_OH_EDITS = [
    # OH E1: Bot Media tutorial - drop the /linkme + /linksmart text/media
    # lines (raw string: the lines store literal \n escapes in the source).
    (
        r"""        "/linkme ka text: /settext linkme\n"
        "/linkme ki media: /setcommandmedia linkme\n"
        "/linksmart ka text: /settext linksmart\n"
        "/linksmart ki media: /setcommandmedia linksmart\n"
""",
        "",
    ),
    # OH E2: Bot Media tutorial - add the Channel Alerts media section
    # (NEW) right after the DM Alert Settings media section.
    (
        r"""        "🆕 <b>NEW - DM Alert Settings media</b>\n"
        "/setdmmedia - DM Alert Settings screens ki media set karo (photo/video reply karo)\n"
        "/cleardmmedia - media hatao\n\n"
""",
        r"""        "🆕 <b>NEW - DM Alert Settings media</b>\n"
        "/setdmmedia - DM Alert Settings screens ki media set karo (photo/video reply karo)\n"
        "/cleardmmedia - media hatao\n\n"
        # DM_ALERT_SETTINGS4_OH_NOV25: Channel Alerts media section (NEW)
        "🆕 <b>NEW - Channel Alert Settings media</b>\n"
        "/setchannelmedia - Channel Alert Settings screens ki media set karo (photo/video reply karo)\n"
        "/clearchannelmedia - media hatao\n\n"
""",
    ),
    # OH E3: OH_CMD_TUTORIALS - add /setchannelmedia + /clearchannelmedia
    # (NEW) right after the /setdmmedia + /cleardmmedia entries.
    (
        r"""        ('setdmmedia', '🆕 NEW: DM Alert Settings screens ki media set karo, photo ya video ko reply karke.\nUsage: /setdmmedia'),
        ('cleardmmedia', '🆕 NEW: DM Alert Settings ki media hata do.\nUsage: /cleardmmedia'),""",
        r"""        ('setdmmedia', '🆕 NEW: DM Alert Settings screens ki media set karo, photo ya video ko reply karke.\nUsage: /setdmmedia'),
        ('cleardmmedia', '🆕 NEW: DM Alert Settings ki media hata do.\nUsage: /cleardmmedia'),
        ('setchannelmedia', '🆕 NEW: Channel Alert Settings screens ki media set karo, photo ya video ko reply karke.\nUsage: /setchannelmedia'),
        ('clearchannelmedia', '🆕 NEW: Channel Alert Settings ki media hata do.\nUsage: /clearchannelmedia'),""",
    ),
    # OH E4a: Public Command Media header - drop /linkme.
    # (triple single quotes: the line ends in a double quote.)
    (
        r'''        "🌐 <b>Public Command Media (/submit /subscribe /linkme)</b>\n"''',
        r'''        "🌐 <b>Public Command Media (/submit /subscribe)</b>\n"''',
    ),
    # OH E4b: Public Command Media command list - drop linkme.
    (
        r'''        "  Commands: <code>submit</code>, <code>subscribe</code>, <code>linkme</code>\n"''',
        r'''        "  Commands: <code>submit</code>, <code>subscribe</code>\n"''',
    ),
]

# ── x_alert.py: channel prefs + enforcement ────────────────────────────────
X_ALERT_EDITS = [
    # E1: channel-level Channel Alert prefs (helpers, before
    # _forward_alert_recipients). Same file as the DM prefs
    # (data/dm_alert_prefs.json), top-level "channel" key:
    # {"channel": {"<channel>": {"x": ..., "dip": ...}}}.
    # Channel-level, NOT per user: the channel's own setting. Default all.
    # The "channel" key never collides with uid keys (numeric strings).
    (
        """async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):""",
        """# ── Channel Alert prefs (DM_ALERT_SETTINGS4_NOV25) ─────────────────────
# Same file as the DM prefs (data/dm_alert_prefs.json), top-level
# "channel" key: {"channel": {"<channel>": {"x": ..., "dip": ...}}}.
# Channel-level, NOT per user: the channel's own setting, set by whoever
# opens Channel Alerts for it. Default all, so nothing changes until a
# channel owner sets a choice. Reuses the DM level sets
# (DM_ALERT_X_STANDARD_LEVELS / DM_ALERT_X_MAJOR_LEVELS and the DIP sets)
# and the DM prefs load/save (_dm_alert_prefs_load/_dm_alert_prefs_save),
# so the channel key lives in the same file as the DM prefs.
def channel_alert_x_choice(channel):
    if not channel:
        return "all"
    try:
        prefs = (_dm_alert_prefs_load() or {}).get("channel", {})
        return str((prefs.get(str(channel).lstrip("@").lower()) or {}).get("x", "all")).lower()
    except Exception:
        return "all"


def channel_alert_dip_choice(channel):
    if not channel:
        return "all"
    try:
        prefs = (_dm_alert_prefs_load() or {}).get("channel", {})
        return str((prefs.get(str(channel).lstrip("@").lower()) or {}).get("dip", "all")).lower()
    except Exception:
        return "all"


def channel_alert_x_set(channel, choice):
    if not channel:
        return
    prefs = _dm_alert_prefs_load() or {}
    ch = prefs.setdefault("channel", {})
    ent = ch.setdefault(str(channel).lstrip("@").lower(), {})
    ent["x"] = choice
    _dm_alert_prefs_save(prefs)


def channel_alert_dip_set(channel, choice):
    if not channel:
        return
    prefs = _dm_alert_prefs_load() or {}
    ch = prefs.setdefault("channel", {})
    ent = ch.setdefault(str(channel).lstrip("@").lower(), {})
    ent["dip"] = choice
    _dm_alert_prefs_save(prefs)


def channel_alert_x_allows(channel, x_val):
    ch = channel_alert_x_choice(channel)
    if ch == "all":
        return True
    if ch == "disable":
        return False
    try:
        xv = float(x_val)
    except Exception:
        return True
    if ch == "standard":
        return xv in DM_ALERT_X_STANDARD_LEVELS
    if ch == "major":
        return xv in DM_ALERT_X_MAJOR_LEVELS
    return True


def channel_alert_dip_allows(channel, x_val):
    ch = channel_alert_dip_choice(channel)
    if ch == "all":
        return True
    if ch == "disable":
        return False
    try:
        xv = float(x_val)
    except Exception:
        return True
    if ch == "standard":
        return xv in DM_ALERT_DIP_STANDARD_LEVELS
    if ch == "major":
        return xv in DM_ALERT_DIP_MAJOR_LEVELS
    return True


async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):""",
    ),
    # E2: linked-channel destinations - retire the /linksmart "smart" tier
    # gate, gate by the channel's Channel Alert X choice instead (default
    # all). Both /linkme (plain "@channel") and /linksmart (dict) links are
    # read the same way now; the channel choice is the single source of truth.
    (
        """            # /linksmart stores {"target": "@channel", "mode": "smart"} so
            # only the milestones in SMART_LINK_MILESTONES get forwarded.
            if isinstance(link_val, dict):
                target = link_val.get("target")
                mode   = link_val.get("mode", "full")
            else:
                target = link_val
                mode   = "full"
            if not target:
                continue
            if mode == "smart" and not _smart_link_milestone_qualifies(x_val):
                continue
            destinations.append((target, f"({x_val}X linked)"))""",
        """            # DM_ALERT_SETTINGS4_NOV25: /linksmart's "smart" tier gate is
            # retired (the channel's Channel Alert choice is now the single
            # source of truth). /linkme stores a plain "@channel" string,
            # /linksmart stores {"target": "@channel", "mode": "smart"} -
            # both are read the same way now.
            if isinstance(link_val, dict):
                target = link_val.get("target")
            else:
                target = link_val
            if not target:
                continue
            if not channel_alert_x_allows(str(target).lstrip("@").lower(), x_val):
                continue
            destinations.append((target, f"({x_val}X linked)"))""",
    ),
    # E3: auto-forward to the KOL's own channel - gate by the channel's
    # Channel Alert X choice (default all, so nothing changes until set).
    (
        """        # Auto-forward to the KOL's own channel, if bot has admin rights.
        try:
            await _auto_forward_to_own_channel(
                bot, channel_key, wizard_post_id,
                already_linked={
                    str(k).lstrip("@").lower() for k in linked.keys()
                })
        except Exception as e:
            logger.warning(f"auto self-forward failed @{channel_key}: {e}")""",
        """        # Auto-forward to the KOL's own channel, if bot has admin rights.
        # DM_ALERT_SETTINGS4_NOV25: gated by the channel's Channel Alert
        # choice (default all, so nothing changes until a choice is set).
        if channel_alert_x_allows(channel_key, x_val):
            try:
                await _auto_forward_to_own_channel(
                    bot, channel_key, wizard_post_id,
                    already_linked={
                        str(k).lstrip("@").lower() for k in linked.keys()
                    })
            except Exception as e:
                logger.warning(f"auto self-forward failed @{channel_key}: {e}")""",
    ),
]

# ── x_alert.py: dip-forward gate (own marker, patch 2/3 pattern) ───────────
X_ALERT_DIPFWD_EDITS = [
    # E1: gate the dip owner forward by the channel's Channel Alert dip
    # choice as well (in addition to the owner's DM dip choice from
    # patch 3). Dip alerts are never forwarded to a KOL channel, so the
    # channel dip setting governs this owner forward - the only dip
    # forward tied to the channel. Default all, so no behaviour change
    # until a channel owner sets a choice.
    (
        """                    # DM_ALERT_SETTINGS3_DIPFWD_NOV25: only forward dip levels
                    # the owner chose for THIS channel (default all).
                    if not _dm_alert_dip_allows(_owner_id, _ck, x_val):
                        logger.info(f"Dip forward skipped {x_val}x {call_key}: owner {_owner_id} disabled this level")""",
        """                    # DM_ALERT_SETTINGS3_DIPFWD_NOV25: only forward dip levels
                    # the owner chose for THIS channel (default all).
                    # DM_ALERT_SETTINGS4_DIPFWD_NOV25: also only forward dip
                    # levels the channel chose in Channel Alerts (default
                    # all). Dip alerts are never forwarded to a KOL channel,
                    # so the channel dip setting governs this owner forward.
                    if not _dm_alert_dip_allows(_owner_id, _ck, x_val) or not channel_alert_dip_allows(_ck, x_val):
                        logger.info(f"Dip forward skipped {x_val}x {call_key}: level disabled for owner {_owner_id} or channel {_ck}")""",
    ),
]

# ── core.py: "Channel Alerts" button in All Commands ───────────────────────
CORE_EDITS = [
    # E1: add the Channel Alerts button right after the DM Alerts button in
    # build_command_keyboard (the All Commands menu). It opens the same
    # settings as DM Alert, but for channel forwards.
    (
        """        [_pkb(lbl("dm_alerts",    "🔮 DM Alerts 🔮"),         callback_data="dm_alerts")],  # BTN_SWAP_NOV18: DM Alerts Fast Track se upar""",
        """        [_pkb(lbl("dm_alerts",    "🔮 DM Alerts 🔮"),         callback_data="dm_alerts")],  # BTN_SWAP_NOV18: DM Alerts Fast Track se upar
        # DM_ALERT_SETTINGS4_NOV25: Channel Alerts button - same settings
        # as DM Alert, but the choices govern channel forwards.
        [_pkb(lbl("channel_alerts", "🔮 Channel Alerts 🔮"), callback_data="channel_alerts")],""",
    ),
]

# ── runtime.py: registrations + Add Channel hook ───────────────────────────
RUNTIME_EDITS = [
    # E1: Channel Alerts Add Channel text hook (right after the DM Alert
    # Add Channel hook in handle_message).
    (
        """    # The user tapped "Add Channel" in the DM Alert picker; their next
    # message is the channel username (same pattern as the skipcall flow).
    if context.user_data.get("dmset_add_channel"):
        if msg.text and await dmset_on_add_channel_text(update, context):
            return""",
        """    # The user tapped "Add Channel" in the DM Alert picker; their next
    # message is the channel username (same pattern as the skipcall flow).
    if context.user_data.get("dmset_add_channel"):
        if msg.text and await dmset_on_add_channel_text(update, context):
            return
    # DM_ALERT_SETTINGS4_NOV25: same hook for the Channel Alerts picker.
    if context.user_data.get("chalert_add_channel"):
        if msg.text and await chalert_on_add_channel_text(update, context):
            return""",
    ),
    # E2: remove /linkme + /linksmart registrations, register
    # /setchannelmedia + /clearchannelmedia in their place.
    (
        """    app.add_handler(CommandHandler("linkme",    cmd_linkme))
    app.add_handler(CommandHandler("linksmart", cmd_linksmart))""",
        """    # DM_ALERT_SETTINGS4_NOV25: /linkme + /linksmart removed - replaced by
    # the Channel Alerts button in All Commands.
    app.add_handler(CommandHandler("setchannelmedia", cmd_setchannelmedia))
    app.add_handler(CommandHandler("clearchannelmedia", cmd_clearchannelmedia))""",
    ),
    # E3: remove /linkme + /linksmart from the BotCommand menu.
    (
        """        BotCommand("linkme",    "Link your channel for alerts"),
        BotCommand("linksmart", "Link your channel for solid alerts only"),""",
        """        # DM_ALERT_SETTINGS4_NOV25: /linkme + /linksmart removed - replaced
        # by the Channel Alerts button in All Commands.""",
    ),
]


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    cmds = resolve(base, "commands.py")
    xal = resolve(base, "x_alert.py")
    core = resolve(base, "core.py")
    rt = resolve(base, "runtime.py")
    ok = True
    # commands.py: exact edits first (sets MARKER + backup), then the
    # function-def removal (restores the backup if it fails).
    if patch_one(cmds, COMMANDS_EDITS, MARKER):
        if not remove_link_cmds(cmds, cmds + ".bak_" + MARKER):
            print("FAIL: commands.py link-cmd removal failed - restored to pre-patch-4 state")
            ok = False
    else:
        ok = False
    if not patch_one(cmds, COMMANDS_OH_EDITS, MARKER_OH):
        ok = False
    if not patch_one(xal, X_ALERT_EDITS, MARKER):
        ok = False
    if not patch_one(xal, X_ALERT_DIPFWD_EDITS, MARKER_DIPFWD):
        ok = False
    if not patch_one(core, CORE_EDITS, MARKER):
        ok = False
    if not patch_one(rt, RUNTIME_EDITS, MARKER):
        ok = False
    print("ALL OK" if ok else "SOME FAILED - check the FAIL lines above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
