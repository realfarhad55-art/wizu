# apply_dm_alert_settings3_nov25.py - DM Alert Settings: Channel Picker (user Nov 25 ~04:18 PKT)
# Markers:
#   DM_ALERT_SETTINGS3_NOV25        - commands.py (picker, channel-scoped screens/callbacks)
#                                     + x_alert.py (per-user-per-channel prefs + enforcement)
#                                     + runtime.py (Add Channel text capture)
#   DM_ALERT_SETTINGS3_DIPFWD_NOV25 - x_alert.py dip-forward gate only
# User spec: ~/workspace/goals/wizardscan-bot-issue-fixes/files/dm-alert-settings-spec-nov25.md
# Section 13 (Channel picker). Base: patch 1 (DM_ALERT_SETTINGS_NOV25) +
# patch 2 (DM_ALERT_SETTINGS2_NOV25) already deployed live; anchors below
# match that applied state. Deploy ONLY after patch 2 is deployed.
#
# FLOW: D.M Alert -> Channel Picker (subscribed channels + Add Channel) ->
# pick a channel -> DM ALERT Settings for THAT channel (Channel: @Name line)
# -> Milestone / DIP screens for that channel. Choices are saved PER USER
# PER CHANNEL in data/dm_alert_prefs.json:
# {"<uid>": {"<channel>": {"x": ..., "dip": ...}}}.
# MIGRATION: an old-shape record {"<uid>": {"x": ..., "dip": ...}} is read as
# the default for EVERY channel of that user until they set a per-channel
# choice. Legacy buttons without a channel keep working (old-shape read/write).
#
# Add Channel: tap -> bot asks for the channel username -> the user's next
# private text message is taken as the name and subscribed with the SAME
# /subscribe logic (cmd_subscribe is called, not re-implemented), then the
# picker reopens with the new channel listed. Invalid / untracked channel ->
# "I couldn't find that channel. Check the username and try again."
# English ONLY in all new user-facing text. No new code files: everything
# goes into existing commands.py / x_alert.py / runtime.py.
# Usage: python3 apply_dm_alert_settings3_nov25.py [/opt/bot | commands.py | ...]
#        (accepts a directory OR any one of the files; the others are resolved
#        from the same directory)
import os
import sys

MARKER = "DM_ALERT_SETTINGS3_NOV25"
MARKER_DIPFWD = "DM_ALERT_SETTINGS3_DIPFWD_NOV25"


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


# ── commands.py: channel-scoped settings screens ─────────────────────────────
COMMANDS_EDITS = [
    # E1: main settings keyboard - channel-aware, Back goes to the picker
    (
        r"""def _dmset_main_kb():
    return InlineKeyboardMarkup([
        [_icon_kb("Milestone Alerts", DMSET_EMOJI_MAIN, callback_data="dmset_milestone")],
        [_icon_kb("DIP Alerts", DMSET_EMOJI_MAIN, callback_data="dmset_dip")],
        [_back_btn()],
    ])""",
        r"""def _dmset_main_kb(channel=None):
    suffix = ("_" + channel) if channel else ""
    return InlineKeyboardMarkup([
        [_icon_kb("Milestone Alerts", DMSET_EMOJI_MAIN, callback_data="dmset_milestone" + suffix)],
        [_icon_kb("DIP Alerts", DMSET_EMOJI_MAIN, callback_data="dmset_dip" + suffix)],
        [InlineKeyboardButton("Back", callback_data="dmset_pick")],
    ])""",
    ),
    # E2: main settings screen - show the channel name under the title
    (
        r"""async def _dmset_show_main(query):
    await _send_screen(query, "dm_settings", DMSET_MAIN_TEXT, _dmset_main_kb(),
                       media_cmd="dm_settings")""",
        r"""async def _dmset_show_main(query, channel=None):
    text = DMSET_MAIN_TEXT
    if channel:
        text = text.replace("<b>DM ALERT Settings</b>\n\n",
                            "<b>DM ALERT Settings</b>\nChannel: @" + _display_handle(channel) + "\n\n", 1)
    await _send_screen(query, "dm_settings", text, _dmset_main_kb(channel),
                       media_cmd="dm_settings")""",
    ),
    # E3: milestone keyboard - channel-aware (choice callbacks carry @channel)
    (
        r"""def _dmset_milestone_kb(uid):
    cur = dm_alert_x_choice(uid)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        return _icon_kb(label, icon, callback_data="dmset_x_" + choice)
    return InlineKeyboardMarkup([
        [_opt("All X Alerts", "all"), _opt("Standard Milestones", "standard")],
        [_opt("Major Milestones", "major"), _opt("Disable X Alerts", "disable")],
        [InlineKeyboardButton("DIP ALERT Setting", callback_data="dmset_dip"),
         InlineKeyboardButton("BACK", callback_data="dmset_main")],
    ])""",
        r"""def _dmset_milestone_kb(uid, channel=None):
    cur = dm_alert_x_choice(uid, channel)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        cb = "dmset_x_" + choice + ("@" + channel if channel else "")
        return _icon_kb(label, icon, callback_data=cb)
    suffix = ("_" + channel) if channel else ""
    return InlineKeyboardMarkup([
        [_opt("All X Alerts", "all"), _opt("Standard Milestones", "standard")],
        [_opt("Major Milestones", "major"), _opt("Disable X Alerts", "disable")],
        [InlineKeyboardButton("DIP ALERT Setting", callback_data="dmset_dip" + suffix),
         InlineKeyboardButton("BACK", callback_data="dmset_main" + suffix)],
    ])""",
    ),
    # E4: milestone screen - channel-aware + Channel line under the title
    (
        r"""async def _dmset_show_milestone(query):
    await _send_screen(query, "dm_settings", DMSET_MILESTONE_TEXT,
                       _dmset_milestone_kb(query.from_user.id),
                       media_cmd="dm_settings")""",
        r"""async def _dmset_show_milestone(query, channel=None):
    text = DMSET_MILESTONE_TEXT
    if channel:
        text = text.replace("<b>Customize Your X Alert Preferences</b>\n\n",
                            "<b>Customize Your X Alert Preferences</b>\nChannel: @" + _display_handle(channel) + "\n\n", 1)
    await _send_screen(query, "dm_settings", text,
                       _dmset_milestone_kb(query.from_user.id, channel),
                       media_cmd="dm_settings")""",
    ),
    # E5: dip keyboard - channel-aware (choice callbacks carry @channel)
    (
        r"""def _dmset_dip_kb(uid):
    cur = dm_alert_dip_choice(uid)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        return _icon_kb(label, icon, callback_data="dmset_dip_" + choice)
    return InlineKeyboardMarkup([
        [_opt("All Dip Alerts", "all"), _opt("Standard Dip Alerts", "standard")],
        [_opt("Major Dip Alerts", "major"), _opt("Disable Dip Alerts", "disable")],
        [InlineKeyboardButton("BACK", callback_data="dmset_main")],
    ])""",
        r"""def _dmset_dip_kb(uid, channel=None):
    cur = dm_alert_dip_choice(uid, channel)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        cb = "dmset_dip_" + choice + ("@" + channel if channel else "")
        return _icon_kb(label, icon, callback_data=cb)
    suffix = ("_" + channel) if channel else ""
    return InlineKeyboardMarkup([
        [_opt("All Dip Alerts", "all"), _opt("Standard Dip Alerts", "standard")],
        [_opt("Major Dip Alerts", "major"), _opt("Disable Dip Alerts", "disable")],
        [InlineKeyboardButton("BACK", callback_data="dmset_main" + suffix)],
    ])""",
    ),
    # E6: dip screen - channel-aware + Channel line under the title
    (
        r"""async def _dmset_show_dip(query):
    await _send_screen(query, "dm_settings", DMSET_DIP_TEXT,
                       _dmset_dip_kb(query.from_user.id),
                       media_cmd="dm_settings")""",
        r"""async def _dmset_show_dip(query, channel=None):
    text = DMSET_DIP_TEXT
    if channel:
        text = text.replace("<b>Customize Your Dip Profit Alert Preferences</b>\n\n",
                            "<b>Customize Your Dip Profit Alert Preferences</b>\nChannel: @" + _display_handle(channel) + "\n\n", 1)
    await _send_screen(query, "dm_settings", text,
                       _dmset_dip_kb(query.from_user.id, channel),
                       media_cmd="dm_settings")""",
    ),
    # E7: Channel Picker + Add Channel flow (inserted before cmd_setdmmedia)
    (
        """@owner_only
async def cmd_setdmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
        r"""# ── Channel Picker (DM_ALERT_SETTINGS3_NOV25) ─────────────────────────────
# D.M Alert opens this FIRST: which channel do you want alerts for? One
# button per channel the user subscribed to (channel_subs.json - the same
# source the X-alert forward uses), plus Add Channel. Level choices are
# saved per user per channel; the settings screens show "Channel: @Name".
DMSET_PICKER_TEXT = (
    f'{PE_CRYSTAL} <b>Which channel do you want alerts for?</b>\n\n'
    'Pick a channel below to set its DM alert preferences. '
    'Tap Add Channel to follow a new one.'
)

DMSET_PICKER_EMPTY_TEXT = (
    f'{PE_CRYSTAL} <b>Which channel do you want alerts for?</b>\n\n'
    "You haven't subscribed to any channel yet. "
    'Use /subscribe @channel to follow a channel, then come back here to set its alerts.'
)

DMSET_ADD_TEXT = (
    f'{PE_CRYSTAL} <b>Add Channel</b>\n\n'
    'Send the channel username, like @Trenchmarkgems.\n\n'
    "I'll subscribe you and bring you back here to set its alerts. "
    'Send /cancel to go back.'
)


def _dmset_user_channels(uid):
    # Channels this user subscribed to (channel_subs.json). Sorted lowercase names.
    try:
        uid_i = int(uid)
    except Exception:
        return []
    subs = load_channel_subs() or {}
    mine = set()
    for ch, uids in subs.items():
        for x in (uids or []):
            try:
                if int(x) == uid_i:
                    mine.add(str(ch).lstrip("@").lower())
                    break
            except Exception:
                continue
    return sorted(mine)


def _dmset_picker_content(uid):
    mine = _dmset_user_channels(uid)
    if mine:
        rows = [[InlineKeyboardButton("@" + _display_handle(ch),
                                      callback_data="dmset_ch_" + ch)]
                for ch in mine]
        kb = InlineKeyboardMarkup(
            rows + [[InlineKeyboardButton("➕ Add Channel", callback_data="dmset_add")],
                    [_back_btn()]])
        return DMSET_PICKER_TEXT, kb
    return DMSET_PICKER_EMPTY_TEXT, InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Channel", callback_data="dmset_add")],
        [_back_btn()],
    ])


async def _dmset_show_picker(query):
    text, kb = _dmset_picker_content(query.from_user.id)
    await _send_screen(query, "dm_settings", text, kb, media_cmd="dm_settings")


async def _dmset_show_add(query):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="dmset_pick")]])
    await _send_screen(query, "dm_settings", DMSET_ADD_TEXT, kb, media_cmd="dm_settings")


async def _dmset_reply_picker(msg, uid):
    # Send the Channel Picker as a plain reply (the Add Channel flow ends
    # with a Message, not a callback query, so _send_screen cannot be used).
    text, kb = _dmset_picker_content(uid)
    text, _ents = _stored_text_entities(text, "")
    bm = get_command_media("dm_settings")
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


async def dmset_on_add_channel_text(update, context):
    # User tapped Add Channel and sent a channel username. Subscribe them
    # with the SAME /subscribe logic (cmd_subscribe is called, not
    # re-implemented), then show the Channel Picker with the new channel.
    # Returns True when the message was consumed.
    msg = update.message
    text = (msg.text or "").strip()
    if not text:
        return False
    if text.lower() in ("/cancel", "cancel"):
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_reply_picker(msg, update.effective_user.id)
        return True
    channel = _norm_channel_arg(text)
    tracked = [c.lower() for c in load_channels()]
    if not channel or channel not in tracked:
        await msg.reply_text(
            "I couldn't find that channel. Check the username and try again.",
            parse_mode="HTML")
        return True
    # Same subscribe logic as /subscribe - do not re-implement it.
    context.args = [channel]
    await cmd_subscribe(update, context)
    context.user_data.pop("dmset_add_channel", None)
    await _dmset_reply_picker(msg, update.effective_user.id)
    return True


@owner_only
async def cmd_setdmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
    ),
    # E8: callback branches - picker first, channel-aware screens and choices.
    # Legacy buttons without a channel keep working (old-shape read/write).
    (
        r"""    elif data == "dm_alerts":
        await _dmset_show_main(query)

    elif data == "dmset_main":
        await _dmset_show_main(query)

    elif data == "dmset_milestone":
        await _dmset_show_milestone(query)

    elif data == "dmset_dip":
        await _dmset_show_dip(query)

    elif data in ("dmset_x_all", "dmset_x_standard", "dmset_x_major", "dmset_x_disable"):
        dm_alert_x_set(query.from_user.id, data[len("dmset_x_"):])
        await _dmset_show_milestone(query)

    elif data in ("dmset_dip_all", "dmset_dip_standard", "dmset_dip_major", "dmset_dip_disable"):
        dm_alert_dip_set(query.from_user.id, data[len("dmset_dip_"):])
        await _dmset_show_dip(query)""",
        r"""    elif data == "dm_alerts":
        await _dmset_show_picker(query)

    elif data == "dmset_pick":
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_show_picker(query)

    elif data == "dmset_add":
        context.user_data["dmset_add_channel"] = True
        await _dmset_show_add(query)

    elif data.startswith("dmset_ch_"):
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_show_main(query, data[len("dmset_ch_"):].lstrip("@").lower())

    elif data == "dmset_main":
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_show_main(query)

    elif data.startswith("dmset_main_"):
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_show_main(query, data[len("dmset_main_"):].lstrip("@").lower())

    elif data == "dmset_milestone":
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_show_milestone(query)

    elif data.startswith("dmset_milestone_"):
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_show_milestone(query, data[len("dmset_milestone_"):].lstrip("@").lower())

    elif data == "dmset_dip":
        context.user_data.pop("dmset_add_channel", None)
        await _dmset_show_dip(query)

    elif data.startswith("dmset_dip_"):
        context.user_data.pop("dmset_add_channel", None)
        rest = data[len("dmset_dip_"):]
        if "@" in rest:
            choice, ch = rest.split("@", 1)
            dm_alert_dip_set(query.from_user.id, ch.lstrip("@").lower(), choice)
            await _dmset_show_dip(query, ch.lstrip("@").lower())
        elif rest in ("all", "standard", "major", "disable"):
            dm_alert_dip_set(query.from_user.id, None, rest)
            await _dmset_show_dip(query)
        else:
            await _dmset_show_dip(query, rest.lstrip("@").lower())

    elif data.startswith("dmset_x_"):
        context.user_data.pop("dmset_add_channel", None)
        rest = data[len("dmset_x_"):]
        if "@" in rest:
            choice, ch = rest.split("@", 1)
            dm_alert_x_set(query.from_user.id, ch.lstrip("@").lower(), choice)
            await _dmset_show_milestone(query, ch.lstrip("@").lower())
        else:
            dm_alert_x_set(query.from_user.id, None, rest)
            await _dmset_show_milestone(query)""",
    ),
]


# ── x_alert.py: per-user-per-channel prefs ───────────────────────────────────
X_ALERT_EDITS = [
    # E1: X choice - channel-aware with old-shape migration
    (
        """def dm_alert_x_choice(uid):
    try:
        c = _dm_alert_prefs_load().get(str(int(uid)), {}) or {}
        v = str(c.get("x") or "all").lower()
        return v if v in ("all", "standard", "major", "disable") else "all"
    except Exception:
        return "all\"""",
        r"""def _dm_alert_choice(rec, key, channel):
    # Read one level choice ('x' or 'dip') from a user's prefs record.
    # New shape: {"<channel>": {"x": ..., "dip": ...}}. Old shape {"x": ...,
    # "dip": ...} (no channel key) is the default for every channel, so
    # choices saved before channel selection keep working everywhere.
    try:
        if not isinstance(rec, dict):
            return "all"
        if channel:
            ch = str(channel).lstrip("@").lower()
            c = rec.get(ch)
            if isinstance(c, dict) and c.get(key):
                v = str(c.get(key)).lower()
                if v in ("all", "standard", "major", "disable"):
                    return v
        v = str(rec.get(key) or "all").lower()
        return v if v in ("all", "standard", "major", "disable") else "all"
    except Exception:
        return "all"


def dm_alert_x_choice(uid, channel=None):
    try:
        rec = _dm_alert_prefs_load().get(str(int(uid)), {}) or {}
        return _dm_alert_choice(rec, "x", channel)
    except Exception:
        return 'all'""",
    ),
    # E2: X set - channel-aware (shared writer for x and dip)
    (
        """def dm_alert_x_set(uid, choice):
    choice = str(choice or "all").lower()
    if choice not in ("all", "standard", "major", "disable"):
        choice = "all"
    prefs = _dm_alert_prefs_load()
    try:
        rec = prefs.get(str(int(uid))) or {}
    except Exception:
        rec = {}
    if not isinstance(rec, dict):
        rec = {}
    rec["x"] = choice
    prefs[str(int(uid))] = rec
    _dm_alert_prefs_save(prefs)
    return choice""",
        r"""def _dm_alert_set_key(uid, channel, key, choice):
    # Save one level choice, per user per channel. channel=None keeps the
    # old per-user shape (used by legacy buttons without a channel).
    choice = str(choice or "all").lower()
    if choice not in ("all", "standard", "major", "disable"):
        choice = "all"
    prefs = _dm_alert_prefs_load()
    try:
        rec = prefs.get(str(int(uid))) or {}
    except Exception:
        rec = {}
    if not isinstance(rec, dict):
        rec = {}
    if channel:
        ch = str(channel).lstrip("@").lower()
        c = rec.get(ch)
        if not isinstance(c, dict):
            c = {}
        c[key] = choice
        rec[ch] = c
    else:
        rec[key] = choice
    prefs[str(int(uid))] = rec
    _dm_alert_prefs_save(prefs)
    return choice


def dm_alert_x_set(uid, channel, choice):
    return _dm_alert_set_key(uid, channel, "x", choice)""",
    ),
    # E3: X allows - pass the alert's channel through
    (
        """def _dm_alert_x_allows(uid, x_val):
    try:
        choice = dm_alert_x_choice(uid)""",
        r"""def _dm_alert_x_allows(uid, channel, x_val):
    try:
        choice = dm_alert_x_choice(uid, channel)""",
    ),
    # E4: dip choice - channel-aware with old-shape migration
    (
        """def dm_alert_dip_choice(uid):
    try:
        c = _dm_alert_prefs_load().get(str(int(uid)), {}) or {}
        v = str(c.get("dip") or "all").lower()
        return v if v in ("all", "standard", "major", "disable") else "all"
    except Exception:
        return "all\"""",
        r"""def dm_alert_dip_choice(uid, channel=None):
    try:
        rec = _dm_alert_prefs_load().get(str(int(uid)), {}) or {}
        return _dm_alert_choice(rec, "dip", channel)
    except Exception:
        return 'all'""",
    ),
    # E5: dip set - channel-aware (shared writer)
    (
        """def dm_alert_dip_set(uid, choice):
    choice = str(choice or "all").lower()
    if choice not in ("all", "standard", "major", "disable"):
        choice = "all"
    prefs = _dm_alert_prefs_load()
    try:
        rec = prefs.get(str(int(uid))) or {}
    except Exception:
        rec = {}
    if not isinstance(rec, dict):
        rec = {}
    rec["dip"] = choice
    prefs[str(int(uid))] = rec
    _dm_alert_prefs_save(prefs)
    return choice""",
        r"""def dm_alert_dip_set(uid, channel, choice):
    return _dm_alert_set_key(uid, channel, "dip", choice)""",
    ),
    # E6: dip allows - pass the alert's channel through
    (
        """def _dm_alert_dip_allows(uid, x_val):
    try:
        choice = dm_alert_dip_choice(uid)""",
        r"""def _dm_alert_dip_allows(uid, channel, x_val):
    try:
        choice = dm_alert_dip_choice(uid, channel)""",
    ),
    # E7: X enforcement - filter by (user, channel, level)
    (
        r"""        # DM_ALERT_SETTINGS_NOV25: each DM recipient only gets the X levels
        # they chose (default all). Channel forwards (str targets) pass through.
        destinations = [(c, l) for (c, l) in destinations
                        if not isinstance(c, int) or _dm_alert_x_allows(c, x_val)]""",
        r"""        # DM_ALERT_SETTINGS3_NOV25: each DM recipient only gets the X levels
        # they chose for THIS channel (default all). Channel forwards
        # (str targets) pass through.
        destinations = [(c, l) for (c, l) in destinations
                        if not isinstance(c, int) or _dm_alert_x_allows(c, channel_key, x_val)]""",
    ),
]


# ── x_alert.py: dip-forward gate - pass the call's channel ───────────────────
# Isolated group (like patch 2): if this anchor fails live (Claude's Nov 24
# dip patch changed the block), only the dip gate is skipped - everything
# else still lands.
X_ALERT_DIPFWD_EDITS = [
    # E1: gate the owner dip forward on the owner's choice for THIS channel
    (
        r"""                    # DM_ALERT_SETTINGS2_DIPFWD_NOV25: only forward dip levels
                    # the owner chose in DM Alert Settings (default all).
                    if not _dm_alert_dip_allows(_owner_id, x_val):""",
        r"""                    # DM_ALERT_SETTINGS3_DIPFWD_NOV25: only forward dip levels
                    # the owner chose for THIS channel (default all).
                    if not _dm_alert_dip_allows(_owner_id, _ck, x_val):""",
    ),
]


# ── runtime.py: Add Channel text capture in handle_message ───────────────────
RUNTIME_EDITS = [
    # E1: after the DM-only check, consume the next text message when the
    # user is in the Add Channel flow (same pattern as the skipcall flow).
    (
        """    # Bot is DM-only — ignore groups/lounges entirely (custom commands ke ilawa)
    if not _is_private_update(update): return""",
        """    # Bot is DM-only — ignore groups/lounges entirely (custom commands ke ilawa)
    if not _is_private_update(update): return

    # ── DM Alert Settings: Add Channel flow (DM_ALERT_SETTINGS3_NOV25) ─────
    # The user tapped "Add Channel" in the DM Alert picker; their next
    # message is the channel username (same pattern as the skipcall flow).
    if context.user_data.get("dmset_add_channel"):
        if msg.text and await dmset_on_add_channel_text(update, context):
            return""",
    ),
]


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    ok = True
    ok = patch_one(resolve(arg, "commands.py"), COMMANDS_EDITS, MARKER) and ok
    ok = patch_one(resolve(arg, "x_alert.py"), X_ALERT_EDITS, MARKER) and ok
    ok = patch_one(resolve(arg, "x_alert.py"), X_ALERT_DIPFWD_EDITS, MARKER_DIPFWD) and ok
    ok = patch_one(resolve(arg, "runtime.py"), RUNTIME_EDITS, MARKER) and ok
    if not ok:
        print("FAILED - nothing was written for the failed group(s); fix the anchor and re-run.")
        print("Groups that succeeded before the failure stay applied (re-runnable).")
        sys.exit(1)
    print("DONE. Backups: *.bak_DM_ALERT_SETTINGS3* (one per group)")
    print("Now restart the wizu bot (systemctl restart bot.service).")


if __name__ == "__main__":
    main()
