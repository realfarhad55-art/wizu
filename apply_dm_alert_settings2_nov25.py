# apply_dm_alert_settings2_nov25.py - DM Alert Settings follow-up (user Nov 25 ~04:12 PKT)
# Markers:
#   DM_ALERT_SETTINGS2_NOV25        - commands.py (spacing, DIP screen, English replies)
#                                     + x_alert.py (dip prefs helpers)
#   DM_ALERT_SETTINGS2_OH_NOV25     - commands.py OwnerHelp entries only
#   DM_ALERT_SETTINGS2_DIPFWD_NOV25 - x_alert.py dip-forward enforcement only
# User spec: ~/workspace/goals/wizardscan-bot-issue-fixes/files/dm-alert-settings-spec-nov25.md
# Sections 8 (DIP screen), 9 (spacing), 10 (OwnerHelp media commands), 11 (English only).
# Base patch DM_ALERT_SETTINGS_NOV25 is already deployed live; anchors below match
# the LIVE code (Nov 23 base copies + patch 1). Dip-forward enforcement anchors
# on the DIP_FWD_DM_NOV23 block (live-only, from apply_dip_forward_dm_nov23.py);
# if that anchor fails live, ONLY the enforcement edit is skipped - the DIP
# screen + helpers still land, and the note flags enforcement as pending.
# No new code files: everything goes into existing commands.py / x_alert.py.
# Prefs stay in data/dm_alert_prefs.json (a DATA file, not code).
# Usage: python3 apply_dm_alert_settings2_nov25.py [/opt/bot | commands.py | ...]
#        (accepts a directory OR any one of the files; the other is resolved
#        from the same directory)
import os
import sys

MARKER = "DM_ALERT_SETTINGS2_NOV25"
MARKER_OH = "DM_ALERT_SETTINGS2_OH_NOV25"
MARKER_DIPFWD = "DM_ALERT_SETTINGS2_DIPFWD_NOV25"


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


# ── commands.py: spacing + DIP screen + callbacks + English replies ──────────
COMMANDS_EDITS = [
    # E0: stale comment (DIP screen is no longer empty)
    (
        """# DIP screen is EMPTY for now (placeholder toast) - user sends DIP details
# later. Settings replies use config["command_media"]["dm_settings"]""",
        """# DIP screen built by DM_ALERT_SETTINGS2_NOV25 (same pattern as Milestone).
# Settings replies use config["command_media"]["dm_settings"]""",
    ),
    # E1: spacing - blank line below "Milestone Alerts" header (main screen)
    (
        r"""    f'{PE_WAND} <b>Milestone Alerts</b>\n'""",
        r"""    f'{PE_WAND} <b>Milestone Alerts</b>\n\n'""",
    ),
    # E2: spacing - blank line below "DIP Profit Alerts" header (main screen)
    (
        r"""    f'{PE_WAND} <b>DIP Profit Alerts</b>\n'""",
        r"""    f'{PE_WAND} <b>DIP Profit Alerts</b>\n\n'""",
    ),
    # E3: spacing - blank line below "All X Alerts" header (milestone screen)
    (
        r"""    f'{PE_WAND} <b>All X Alerts</b>\n'""",
        r"""    f'{PE_WAND} <b>All X Alerts</b>\n\n'""",
    ),
    # E4: spacing - blank line below "Standard Milestones" header
    (
        r"""    f'{PE_WAND} <b>Standard Milestones</b>\n'""",
        r"""    f'{PE_WAND} <b>Standard Milestones</b>\n\n'""",
    ),
    # E5: spacing - blank line below "Major Milestones" header
    (
        r"""    f'{PE_WAND} <b>Major Milestones</b>\n'""",
        r"""    f'{PE_WAND} <b>Major Milestones</b>\n\n'""",
    ),
    # E6: spacing - blank line below "Disable X Alerts" header
    (
        r"""    f'{PE_WAND} <b>Disable X Alerts</b>\n'""",
        r"""    f'{PE_WAND} <b>Disable X Alerts</b>\n\n'""",
    ),
    # E7: DIP screen text + keyboard + show fn (inserted after _dmset_show_milestone)
    (
        """async def _dmset_show_milestone(query):
    await _send_screen(query, "dm_settings", DMSET_MILESTONE_TEXT,
                       _dmset_milestone_kb(query.from_user.id),
                       media_cmd="dm_settings")


@owner_only
async def cmd_setdmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
        r"""async def _dmset_show_milestone(query):
    await _send_screen(query, "dm_settings", DMSET_MILESTONE_TEXT,
                       _dmset_milestone_kb(query.from_user.id),
                       media_cmd="dm_settings")


# ── DIP Alert Settings screen (DM_ALERT_SETTINGS2_NOV25) ────────────────────
# Same pattern as the Milestone screen: same emojis (PE_CRYSTAL header,
# PE_WAND sections), same bold headers, same blank line below each header,
# same tick/cross on the 4 option buttons. Choice saved per user in
# data/dm_alert_prefs.json under key "dip" (helpers live in x_alert.py).
DMSET_DIP_TEXT = (
    f'{PE_CRYSTAL} <b>Customize Your Dip Profit Alert Preferences</b>\n\n'
    'Choose how WIZARD SCAN forwards Dip Profit milestone alerts directly to '
    'your DMs. Select the notification frequency that best suits your preferences.\n\n'
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
    'Stop receiving all Dip Profit milestone alerts in your DMs.'
)


def _dmset_dip_kb(uid):
    cur = dm_alert_dip_choice(uid)
    def _opt(label, choice):
        icon = DMSET_TICK_EMOJI_ID if cur == choice else DMSET_CROSS_EMOJI_ID
        return _icon_kb(label, icon, callback_data="dmset_dip_" + choice)
    return InlineKeyboardMarkup([
        [_opt("All Dip Alerts", "all"), _opt("Standard Dip Alerts", "standard")],
        [_opt("Major Dip Alerts", "major"), _opt("Disable Dip Alerts", "disable")],
        [InlineKeyboardButton("BACK", callback_data="dmset_main")],
    ])


async def _dmset_show_dip(query):
    await _send_screen(query, "dm_settings", DMSET_DIP_TEXT,
                       _dmset_dip_kb(query.from_user.id),
                       media_cmd="dm_settings")


@owner_only
async def cmd_setdmmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):""",
    ),
    # E8: dmset_dip opens the real DIP screen (replaces the placeholder toast)
    (
        """    elif data == "dmset_dip":
        # DIP screen is EMPTY for now (DM_ALERT_SETTINGS_NOV25) - user sends
        # the DIP details later. Placeholder toast only, screen stays as-is.
        await query.answer("DIP Alert settings coming soon.")""",
        """    elif data == "dmset_dip":
        await _dmset_show_dip(query)""",
    ),
    # E9: dip choice branch (after the X choice branch)
    (
        """    elif data in ("dmset_x_all", "dmset_x_standard", "dmset_x_major", "dmset_x_disable"):
        dm_alert_x_set(query.from_user.id, data[len("dmset_x_"):])
        await _dmset_show_milestone(query)""",
        """    elif data in ("dmset_x_all", "dmset_x_standard", "dmset_x_major", "dmset_x_disable"):
        dm_alert_x_set(query.from_user.id, data[len("dmset_x_"):])
        await _dmset_show_milestone(query)

    elif data in ("dmset_dip_all", "dmset_dip_standard", "dmset_dip_major", "dmset_dip_disable"):
        dm_alert_dip_set(query.from_user.id, data[len("dmset_dip_"):])
        await _dmset_show_dip(query)""",
    ),
    # E10: English - /setdmmedia with no replied media
    (
        '''            "📸 Photo ya video ko reply karo <code>/setdmmedia</code> se.",''',
        '''            "📸 Reply to a photo or video with <code>/setdmmedia</code>.",''',
    ),
    # E11: English - /setdmmedia replied to non-media
    # (anchor extended: the bare reply line exists 3x in commands.py -
    # /setdmmedia, /setkolacceptmedia, /setsubmitconfirmmedia. The
    # dm_settings lines below make it unique to /setdmmedia.)
    (
        '''    else:
        await msg.reply_text("❌ Sirf photo ya video reply karo.")
        return
    c = load_config()
    cm = c.get("command_media", {})
    cm["dm_settings"] = {"file_id": fid, "type": ftype}''',
        '''    else:
        await msg.reply_text("❌ Please reply to a photo or video only.")
        return
    c = load_config()
    cm = c.get("command_media", {})
    cm["dm_settings"] = {"file_id": fid, "type": ftype}''',
    ),
    # E12: English - /setdmmedia success
    (
        '''        f"✅ <b>DM Alert Settings</b> ka media set ho gaya! ({ftype})\\n\\n"
        "Ab har settings reply pe yeh media dikhegi.",''',
        '''        f"✅ <b>DM Alert Settings</b> media set! ({ftype})\\n\\n"
        "This media will now show on every settings reply.",''',
    ),
    # E13: English - /cleardmmedia removed
    (
        '''        await update.message.reply_text("✅ DM Alert Settings ka media hata diya. Ab text-only reply aayega.")''',
        '''        await update.message.reply_text("✅ DM Alert Settings media removed. Replies will be text-only now.")''',
    ),
    # E14: English - /cleardmmedia nothing set
    (
        '''        await update.message.reply_text("DM Alert Settings ke liye koi media set nahi hai.")''',
        '''        await update.message.reply_text("No media is set for DM Alert Settings.")''',
    ),
]

# ── commands.py: OwnerHelp entries for /setdmmedia + /cleardmmedia ───────────
COMMANDS_OH_EDITS = [
    # E1: "bot" panel (Bot Media & Templates) - NEW entry under Public command
    (
        r"""        "Text dekho: /showtext CMD · default: /cleartext CMD · media hatao: /clearcommandmedia CMD\n\n"
""",
        r"""        "Text dekho: /showtext CMD · default: /cleartext CMD · media hatao: /clearcommandmedia CMD\n\n"
        "🆕 <b>NEW - DM Alert Settings media</b>\n"
        "/setdmmedia - DM Alert Settings screens ki media set karo (photo/video reply karo)\n"
        "/cleardmmedia - media hatao\n\n"
""",
    ),
    # E2: OH_CMD_TUTORIALS 'bot' category - NEW entries next to /setcommandmedia
    (
        r"""        ('clearcommandmedia', 'Public command ki media hata do.\nUsage: /clearcommandmedia <command>'),""",
        r"""        ('clearcommandmedia', 'Public command ki media hata do.\nUsage: /clearcommandmedia <command>'),
        ('setdmmedia', '🆕 NEW: DM Alert Settings screens ki media set karo, photo ya video ko reply karke.\nUsage: /setdmmedia'),
        ('cleardmmedia', '🆕 NEW: DM Alert Settings ki media hata do.\nUsage: /cleardmmedia'),""",
    ),
]

# ── x_alert.py: dip prefs helpers (same file/pattern as the X helpers) ───────
X_ALERT_EDITS = [
    # E1: dip helpers, inserted after _dm_alert_x_allows (before _forward_alert_recipients)
    (
        """    except Exception:
        return True


async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):""",
        r"""    except Exception:
        return True


# ── DM Alert Settings dip prefs (DM_ALERT_SETTINGS2_NOV25) ─────────────────
# Per-user Dip-alert level choice, saved in the SAME data/dm_alert_prefs.json:
# {"<uid>": {"x": ..., "dip": "all"|"standard"|"major"|"disable"}}.
# Default (no saved dip choice) is "all", so users who never open settings
# keep today's behaviour. Standard = dip milestones 2-10, 15-50 step 5,
# 60-100 step 10, 150, 200, 250, 500, 1000, 1500, then every +500.
# Major = 2, 10, 20, 30, 50, 100, 200, 300, 500, 1000, then every +500.
DM_ALERT_DIP_STANDARD_LEVELS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30,
                                35, 40, 45, 50, 60, 70, 80, 90, 100, 150,
                                200, 250, 500, 1000, 1500]
DM_ALERT_DIP_MAJOR_LEVELS = [2, 10, 20, 30, 50, 100, 200, 300, 500, 1000]


def dm_alert_dip_choice(uid):
    try:
        c = _dm_alert_prefs_load().get(str(int(uid)), {}) or {}
        v = str(c.get("dip") or "all").lower()
        return v if v in ("all", "standard", "major", "disable") else "all"
    except Exception:
        return "all"


def dm_alert_dip_set(uid, choice):
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
    return choice


def _dm_alert_dip_allows(uid, x_val):
    try:
        choice = dm_alert_dip_choice(uid)
        if choice == "all":
            return True
        if choice == "disable":
            return False
        x = int(x_val)
        if choice == "standard":
            return x in DM_ALERT_DIP_STANDARD_LEVELS or (x > 1500 and (x - 1500) % 500 == 0)
        if choice == "major":
            return x in DM_ALERT_DIP_MAJOR_LEVELS or (x > 1500 and (x - 1500) % 500 == 0)
        return True
    except Exception:
        return True


async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):""",
    ),
]

# ── x_alert.py: dip-forward enforcement (live-only DIP_FWD_DM_NOV23 block) ───
# Anchored on the E5 block from apply_dip_forward_dm_nov23.py (deployed live
# Nov 23 ~21:12 PKT). If this anchor fails live (e.g. Claude's Nov 24 dip
# patch changed the block), ONLY this edit is skipped - helpers still land.
X_ALERT_DIPFWD_EDITS = [
    # E1: gate the owner forward on the owner's saved dip choice
    (
        """                if _owner_id:
                    try:
                        await bot.forward_message(chat_id=_owner_id,
                                                  from_chat_id=TARGET_CHANNEL,
                                                  message_id=channel_post_id)
                    except Exception as _fe:
                        logger.warning(f"Dip forward to owner {_owner_id} failed {x_val}x {call_key}: {_fe}")""",
        """                if _owner_id:
                    # DM_ALERT_SETTINGS2_DIPFWD_NOV25: only forward dip levels
                    # the owner chose in DM Alert Settings (default all).
                    if not _dm_alert_dip_allows(_owner_id, x_val):
                        logger.info(f"Dip forward skipped {x_val}x {call_key}: owner {_owner_id} disabled this level")
                    else:
                        try:
                            await bot.forward_message(chat_id=_owner_id,
                                                      from_chat_id=TARGET_CHANNEL,
                                                      message_id=channel_post_id)
                        except Exception as _fe:
                            logger.warning(f"Dip forward to owner {_owner_id} failed {x_val}x {call_key}: {_fe}")""",
    ),
]


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    ok = True
    ok = patch_one(resolve(arg, "commands.py"), COMMANDS_EDITS, MARKER) and ok
    ok = patch_one(resolve(arg, "commands.py"), COMMANDS_OH_EDITS, MARKER_OH) and ok
    ok = patch_one(resolve(arg, "x_alert.py"), X_ALERT_EDITS, MARKER) and ok
    ok = patch_one(resolve(arg, "x_alert.py"), X_ALERT_DIPFWD_EDITS, MARKER_DIPFWD) and ok
    if not ok:
        print("FAILED - nothing was written for the failed group(s); fix the anchor and re-run.")
        print("Groups that succeeded before the failure stay applied (re-runnable).")
        sys.exit(1)
    print("DONE. Backups: *.bak_DM_ALERT_SETTINGS2* (one per group)")
    print("Now restart the wizu bot (systemctl restart bot.service).")


if __name__ == "__main__":
    main()
