# apply_dm_alert_settings_nov25.py - DM Alert Settings (user GO Nov 25 ~03:39 PKT)
# Marker: DM_ALERT_SETTINGS_NOV25
# User spec: ~/workspace/goals/wizardscan-bot-issue-fixes/files/dm-alert-settings-spec-nov25.md
# Edits (commands.py + x_alert.py + runtime.py):
#  E1 commands.py: /start button "Command" -> "All Commands".
#  E2 commands.py: DM settings texts/keyboards/show fns + /setdmmedia + /cleardmmedia
#      (inserted after DM_ALERTS_TEXT; DM_ALERTS_TEXT itself is kept, /subscribe
#      still uses it).
#  E3 commands.py: "dm_alerts" button opens the new settings screen; new
#      callback branches dmset_main / dmset_milestone / dmset_dip / dmset_x_*.
#  E4 x_alert.py: per-user X-alert prefs helpers (data/dm_alert_prefs.json).
#  E5 x_alert.py: _forward_alert_recipients respects each DM recipient's
#      saved level choice (default all; channel forwards untouched).
#  E6 runtime.py: register /setdmmedia + /cleardmmedia.
# DIP screen is INTENTIONALLY EMPTY (placeholder toast only) - user sends the
# DIP details later. No dip options, no dip tick/cross, no dip enforcement yet.
# Media: settings replies use config["command_media"]["dm_settings"] (set via
# /setdmmedia). If empty, replies are text-only, nothing breaks.
# Usage: python3 apply_dm_alert_settings_nov25.py [/opt/bot | x_alert.py | ...]
#        (accepts a directory OR any one of the three files; the other two are
#        resolved from the same directory)
import os
import sys

MARKER = "DM_ALERT_SETTINGS_NOV25"


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
    with open(path + ".bak_dm_alert_settings_nov25", "w", encoding="utf-8") as f:
        f.write(orig)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("DONE %s. Backup: %s.bak_dm_alert_settings_nov25" % (os.path.basename(path), path))
    return True


# ── commands.py ──────────────────────────────────────────────────────────────
COMMANDS_EDITS = [
    # E1: /start button rename
    (
        '    kb      = InlineKeyboardMarkup([[_pkb("🔮 Command 🔮", callback_data="command_menu")]])',
        '    kb      = InlineKeyboardMarkup([[_pkb("🔮 All Commands 🔮", callback_data="command_menu")]])',
    ),
    # E2: DM settings block (inserted after DM_ALERTS_TEXT)
    (
        """    '<b>Send <code>/unsubscribe @channel</code> to unsub.</b>'
)

FAST_TRACK_TEXT = (""",
        r"""    '<b>Send <code>/unsubscribe @channel</code> to unsub.</b>'
)


# ── DM Alert Settings (DM_ALERT_SETTINGS_NOV25) ─────────────────────────────
# Owner spec Nov 25: D.M Alert button opens a settings screen (Milestone
# Alerts / DIP Alerts / Back). Milestone screen offers All / Standard /
# Major / Disable with tick/cross and saves the choice per user in
# data/dm_alert_prefs.json (helpers live in x_alert.py, same namespace).
# DIP screen is EMPTY for now (placeholder toast) - user sends DIP details
# later. Settings replies use config["command_media"]["dm_settings"]
# (set via /setdmmedia); if empty, replies are text-only.
DMSET_EMOJI_MAIN = 5888670372093502546     # header + first 2 buttons
DMSET_EMOJI_SECTION = 5260426225599405269  # section headers
DMSET_TICK_EMOJI_ID = 4958610528588008305
DMSET_CROSS_EMOJI_ID = 5314430517314075350

DMSET_MAIN_TEXT = (
    f'{PE_CRYSTAL} <b>DM ALERT Settings</b>\n\n'
    'Choose which alerts WIZARD SCAN forwards directly to your DMs, and '
    'customize your notification preferences to stay updated on the milestones '
    'and activity that matter most to you.\n\n'
    f'{PE_WAND} <b>Milestone Alerts</b>\n'
    'To configure your normal X alerts, click the Milestone Alerts button and '
    'set your preferred milestones according to your needs.\n\n'
    f'{PE_WAND} <b>DIP Profit Alerts</b>\n'
    "We've added a new Dip Profit feature! You can configure its settings as "
    'well. Simply click the DIP Alerts button to set your preferences.'
)

DMSET_MILESTONE_TEXT = (
    f'{PE_CRYSTAL} <b>Customize Your X Alert Preferences</b>\n\n'
    'Click the buttons below to select your preferred X alert notifications.\n\n'
    f'{PE_WAND} <b>All X Alerts</b>\n'
    "With the All X Alerts button, you'll receive every X milestone alert "
    'directly in your DMs.\n\n'
    f'{PE_WAND} <b>Standard Milestones</b>\n'
    'Receive alerts at 2X, 5X, 10X, 15X, 20X, 25X, 30X and every 5X milestone '
    'up to 100X, followed by 200X, 300X and beyond.\n\n'
    f'{PE_WAND} <b>Major Milestones</b>\n'
    'Receive fewer notifications at major milestones: 2X, 10X, 20X, 50X, 100X, '
    '200X, 300X and beyond.\n\n'
    f'{PE_WAND} <b>Disable X Alerts</b>\n'
    'Stop receiving all X milestone alerts in your DMs.'
)


def _dmset_main_kb():
    return InlineKeyboardMarkup([
        [_icon_kb("Milestone Alerts", DMSET_EMOJI_MAIN, callback_data="dmset_milestone")],
        [_icon_kb("DIP Alerts", DMSET_EMOJI_MAIN, callback_data="dmset_dip")],
        [_back_btn()],
    ])


def _dmset_milestone_kb(uid):
    cur = dm_alert_x_choice(uid)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        return _icon_kb(label, icon, callback_data="dmset_x_" + choice)
    return InlineKeyboardMarkup([
        [_opt("All X Alerts", "all"), _opt("Standard Milestones", "standard")],
        [_opt("Major Milestones", "major"), _opt("Disable X Alerts", "disable")],
        [InlineKeyboardButton("DIP ALERT Setting", callback_data="dmset_dip"),
         InlineKeyboardButton("BACK", callback_data="dmset_main")],
    ])


async def _dmset_show_main(query):
    await _send_screen(query, "dm_settings", DMSET_MAIN_TEXT, _dmset_main_kb(),
                       media_cmd="dm_settings")


async def _dmset_show_milestone(query):
    await _send_screen(query, "dm_settings", DMSET_MILESTONE_TEXT,
                       _dmset_milestone_kb(query.from_user.id),
                       media_cmd="dm_settings")


@owner_only
async def cmd_setdmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reply to a photo/video with /setdmmedia to set the media shown on
    # every DM Alert Settings reply. Stored in config["command_media"]["dm_settings"].
    msg = update.message
    reply = msg.reply_to_message
    if not reply:
        await msg.reply_text(
            "📸 Photo ya video ko reply karo <code>/setdmmedia</code> se.",
            parse_mode="HTML")
        return
    if reply.video:
        fid = reply.video.file_id; ftype = "video"
    elif reply.photo:
        fid = reply.photo[-1].file_id; ftype = "photo"
    elif reply.document and reply.document.mime_type and reply.document.mime_type.startswith("video"):
        fid = reply.document.file_id; ftype = "video"
    else:
        await msg.reply_text("❌ Sirf photo ya video reply karo.")
        return
    c = load_config()
    cm = c.get("command_media", {})
    cm["dm_settings"] = {"file_id": fid, "type": ftype}
    c["command_media"] = cm
    save_config(c)
    await msg.reply_text(
        f"✅ <b>DM Alert Settings</b> ka media set ho gaya! ({ftype})\n\n"
        "Ab har settings reply pe yeh media dikhegi.",
        parse_mode="HTML")


@owner_only
async def cmd_cleardmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = load_config()
    cm = c.get("command_media", {})
    if "dm_settings" in cm:
        del cm["dm_settings"]
        c["command_media"] = cm
        save_config(c)
        await update.message.reply_text("✅ DM Alert Settings ka media hata diya. Ab text-only reply aayega.")
    else:
        await update.message.reply_text("DM Alert Settings ke liye koi media set nahi hai.")


FAST_TRACK_TEXT = (""",
    ),
]

COMMANDS_EDITS.append(
    # E3: dm_alerts branch -> new settings screens + callback branches
    (
        """    elif data == "dm_alerts":
        kb = InlineKeyboardMarkup([[_back_btn()]])
        await _send_screen(query, "dm_alerts", DM_ALERTS_TEXT, kb, media_cmd="subscribe")""",
        r"""    elif data == "dm_alerts":
        await _dmset_show_main(query)

    elif data == "dmset_main":
        await _dmset_show_main(query)

    elif data == "dmset_milestone":
        await _dmset_show_milestone(query)

    elif data == "dmset_dip":
        # DIP screen is EMPTY for now (DM_ALERT_SETTINGS_NOV25) - user sends
        # the DIP details later. Placeholder toast only, screen stays as-is.
        await query.answer("DIP Alert settings coming soon.")

    elif data in ("dmset_x_all", "dmset_x_standard", "dmset_x_major", "dmset_x_disable"):
        dm_alert_x_set(query.from_user.id, data[len("dmset_x_"):])
        await _dmset_show_milestone(query)""",
    ),
)


# ── x_alert.py ───────────────────────────────────────────────────────────────
X_ALERT_EDITS = [
    # E4: per-user X-alert prefs helpers (inserted before _forward_alert_recipients)
    (
        "async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):",
        r"""# ── DM Alert Settings prefs (DM_ALERT_SETTINGS_NOV25) ───────────────────────
# Per-user X-alert level choice, saved in data/dm_alert_prefs.json:
# {"<uid>": {"x": "all"|"standard"|"major"|"disable"}}. Default (no saved
# choice) is "all", so users who never open settings keep today's behaviour.
DM_ALERT_PREFS_FILE = _dp("dm_alert_prefs.json")
DM_ALERT_X_STANDARD_LEVELS = [2, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55,
                              60, 65, 70, 75, 80, 85, 90, 95, 100, 150, 200,
                              250, 300, 500, 600, 700, 800, 900, 1000]
DM_ALERT_X_MAJOR_LEVELS = [2, 10, 20, 50, 100, 200, 300, 500, 1000]


def _dm_alert_prefs_load():
    try:
        d = load_json(DM_ALERT_PREFS_FILE, {})
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _dm_alert_prefs_save(prefs):
    try:
        save_json(DM_ALERT_PREFS_FILE, prefs)
    except Exception as e:
        logger.error(f"dm_alert_prefs save failed: {e}")


def dm_alert_x_choice(uid):
    try:
        c = _dm_alert_prefs_load().get(str(int(uid)), {}) or {}
        v = str(c.get("x") or "all").lower()
        return v if v in ("all", "standard", "major", "disable") else "all"
    except Exception:
        return "all"


def dm_alert_x_set(uid, choice):
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
    return choice


def _dm_alert_x_allows(uid, x_val):
    try:
        choice = dm_alert_x_choice(uid)
        if choice == "all":
            return True
        if choice == "disable":
            return False
        x = int(x_val)
        if choice == "standard":
            return x in DM_ALERT_X_STANDARD_LEVELS
        if choice == "major":
            return x in DM_ALERT_X_MAJOR_LEVELS
        return True
    except Exception:
        return True


async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):""",
    ),
    # E5: filter DM recipients by their saved level choice (channel forwards pass through)
    (
        """        await asyncio.gather(*[_one(chat_id, label) for chat_id, label in destinations],
                             return_exceptions=True)""",
        r"""        # DM_ALERT_SETTINGS_NOV25: each DM recipient only gets the X levels
        # they chose (default all). Channel forwards (str targets) pass through.
        destinations = [(c, l) for (c, l) in destinations
                        if not isinstance(c, int) or _dm_alert_x_allows(c, x_val)]

        await asyncio.gather(*[_one(chat_id, label) for chat_id, label in destinations],
                             return_exceptions=True)""",
    ),
]


# ── runtime.py ───────────────────────────────────────────────────────────────
RUNTIME_EDITS = [
    # E6: register /setdmmedia + /cleardmmedia
    (
        """    app.add_handler(CommandHandler("setcommandmedia",    cmd_setcommandmedia))
    app.add_handler(CommandHandler("clearcommandmedia",  cmd_clearcommandmedia))""",
        """    app.add_handler(CommandHandler("setcommandmedia",    cmd_setcommandmedia))
    app.add_handler(CommandHandler("clearcommandmedia",  cmd_clearcommandmedia))
    app.add_handler(CommandHandler("setdmmedia",         cmd_setdmmedia))   # DM_ALERT_SETTINGS_NOV25
    app.add_handler(CommandHandler("cleardmmedia",       cmd_cleardmmedia))  # DM_ALERT_SETTINGS_NOV25""",
    ),
]


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    ok = True
    ok = patch_one(resolve(arg, "commands.py"), COMMANDS_EDITS) and ok
    ok = patch_one(resolve(arg, "x_alert.py"), X_ALERT_EDITS) and ok
    ok = patch_one(resolve(arg, "runtime.py"), RUNTIME_EDITS) and ok
    if not ok:
        print("FAILED - nothing was written for the failed file(s); fix the anchor and re-run.")
        sys.exit(1)
    print("DONE. Backups: *.bak_dm_alert_settings_nov25")
    print("Now restart the wizu bot (systemctl restart bot.service).")


if __name__ == "__main__":
    main()
