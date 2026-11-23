#!/usr/bin/env python3
"""NOV23_ALERT - The three pending Nov 23 WizardScan fixes in ONE file.

This single file replaces 3 separate patch files:
  apply_reset_rules_nov23.py       (leaderboard 24h->72h, champions 7d->10d)
  apply_dupx_nov23.py              (duplicate X alerts: persist seals to disk)
  apply_mostshared_nobutton_nov23.py (Most Shared post: drop Check Record button)

max99 + points15 are NOT in here - both are already deployed live,
so delete their patch files from GitHub too. After this file, the
Nov 23 patch set is just: dip.alert.py + nov23.alert.py.

Verified: applying this file to clean bases produces byte-identical
files to applying the 3 patches in order (checked by the builder).
It also applies cleanly on a live-like bot (dip + max99 + points15
already in), because none of these anchors overlap those changes.

VPS-only one-time script. Idempotent (marker NOV23_ALERT).
Backup: <file>.bak_nov23_alert. Fail-safe: validates ALL anchors
before writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 nov23.alert.py
"""

import os
import sys

MARKER = "NOV23_ALERT"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_nov23_alert"

EDITS = {
    'leaderboard.py': [
        ('LEADERBOARD_RESET_HOURS = 24\n',
         'LEADERBOARD_RESET_HOURS = 72  # RESET_RULES_NOV23: leaderboard resets every 3 days\n',
         'leaderboard.py replace base lines 1976-1976 (1 -> 1 lines)'),
        ('    time is actually left until the next 24h auto-reset."""\n    return "Auto-resets every 24 hours."\n',
         '    time is actually left until the next 3-day auto-reset."""\n    return "Auto-resets every 3 days."\n',
         'leaderboard.py replace base lines 1981-1982 (2 -> 2 lines)'),
        ('    """Update post 136 (leaderboard) every 1-2 minutes. Auto-resets scores every 24 hours."""\n',
         '    """Update post 136 (leaderboard) every 1-2 minutes. Auto-resets scores every 3 days."""\n',
         'leaderboard.py replace base lines 1985-1985 (1 -> 1 lines)'),
        ('    # ── automatic 24-hour reset ──────────────────────────────────────────────\n',
         '    # ── automatic 3-day reset ──────────────────────────────────────────────\n',
         'leaderboard.py replace base lines 1989-1989 (1 -> 1 lines)'),
        ('CHAMPIONS_RESET_DAYS = 7   # Champion KOLs list + points auto-reset every 7 days\n',
         'CHAMPIONS_RESET_DAYS = 10  # RESET_RULES_NOV23: Champion KOLs list + points auto-reset every 10 days\n',
         'leaderboard.py replace base lines 2123-2123 (1 -> 1 lines)'),
        ('    zero ALL channel points, start a fresh 7-day cycle. Leaderboard (post 136) is NOT touched."""\n',
         '    zero ALL channel points, start a fresh 10-day cycle. Leaderboard (post 136) is NOT touched."""\n',
         'leaderboard.py replace base lines 2127-2127 (1 -> 1 lines)'),
        ('    """Update post 134 (champions) every 1-2 minutes. Resets all points every 7 days."""\n',
         '    """Update post 134 (champions) every 1-2 minutes. Resets all points every 10 days."""\n',
         'leaderboard.py replace base lines 2144-2144 (1 -> 1 lines)'),
        ('    # ── automatic 7-day reset (Champions only) ────────────────────────────────\n',
         '    # ── automatic 10-day reset (Champions only) ────────────────────────────────\n',
         'leaderboard.py replace base lines 2148-2148 (1 -> 1 lines)'),
    ],
    'x_alert.py': [
        ('                return []\n            except Exception as e:\n',
         '                _save_milestones()  # DUPX_NOV23: persist the seal NOW so a restart cannot re-fire it\n                return []\n            except Exception as e:\n',
         'x_alert.py insert base lines 5380-5379 (0 -> 1 lines)'),
        ('        # NOTE: alerts are already dispatched in real time by the FIFO worker\n',
         '        _save_milestones()  # DUPX_NOV23: persist any seals from this tick\n        # NOTE: alerts are already dispatched in real time by the FIFO worker\n',
         'x_alert.py insert base lines 5395-5394 (0 -> 1 lines)'),
    ],
    'most_shared.py': [
        ('    1) Bot API send with HTML caption  -> links + bold + button icon + (premium emojis if the bot may use them)\n',
         '    1) Bot API send with HTML caption  -> links + bold + (premium emojis if the bot may use them)\n',
         'most_shared.py replace base lines 436-436 (1 -> 1 lines)'),
        ('    kb = InlineKeyboardMarkup([[_icon_kb("Check Record", MS_EMO_BTN, url=record_url)]])\n    _MS_EDIT["v"] = "n/a"\n',
         '    _MS_EDIT["v"] = "n/a"  # MOSTSHARED_NOBUTTON_NOV23: no button on the channel post\n',
         'most_shared.py replace base lines 440-441 (2 -> 1 lines)'),
        ('            btns = _ptb_keyboard_to_tl(InlineKeyboardMarkup([[InlineKeyboardButton("Check Record", url=record_url)]]))\n',
         '            # MOSTSHARED_NOBUTTON_NOV23: no buttons on the channel post\n',
         'most_shared.py replace base lines 447-447 (1 -> 1 lines)'),
        ('                    TARGET_CHANNEL, video_path, caption=plain, formatting_entities=ents, buttons=btns,\n',
         '                    TARGET_CHANNEL, video_path, caption=plain, formatting_entities=ents,\n',
         'most_shared.py replace base lines 450-450 (1 -> 1 lines)'),
        ('                                                         buttons=btns, link_preview=False)\n',
         '                                                         link_preview=False)\n',
         'most_shared.py replace base lines 455-455 (1 -> 1 lines)'),
        ('    # FALLBACK: Bot API (video+button post fine, but NO premium emojis for user-pack in channels)\n',
         '    # FALLBACK: Bot API (video post fine, but NO premium emojis for user-pack in channels)\n',
         'most_shared.py replace base lines 460-460 (1 -> 1 lines)'),
        ('                                         reply_markup=kb, width=1440, height=626, duration=8,\n',
         '                                         width=1440, height=626, duration=8,\n',
         'most_shared.py replace base lines 465-465 (1 -> 1 lines)'),
    ],
}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    print(f"{MARKER} patch - target dir: {BOT_DIR}")
    new_contents = {}
    skipped = []
    for fname, replaces in EDITS.items():
        path = os.path.join(BOT_DIR, fname)
        if not os.path.isfile(path):
            print(f"ABORT: {path} not found. Run this script in /opt/bot.")
            sys.exit(1)
        text = _read(path)
        for old, new, label in replaces:
            n_old = text.count(old)
            n_new = text.count(new)
            if n_new >= 1:
                skipped.append(label)
                continue
            if n_old != 1:
                print(f"ABORT: {label}: anchor found {n_old}x (expected 1).")
                print("Nothing was written. Check the live file and re-run after fixing.")
                sys.exit(1)
            text = text.replace(old, new, 1)
        new_contents[fname] = text
    if skipped and len(skipped) == sum(len(v) for v in EDITS.values()):
        print("SKIP: all files already patched (NOV23_ALERT present).")
        print("DONE. No change needed - just restart if you have not since.")
        return
    for fname, text in new_contents.items():
        path = os.path.join(BOT_DIR, fname)
        bak = path + BAK_SUFFIX
        _write(bak, _read(path))
        print(f"Backup: {bak}")
        _write(path, text)
        print(f"Patched: {fname}")
    print("DONE. Now restart the bot: systemctl restart bot.service")
    print("Then verify: leaderboard resets every 3 days, champions every 10 days;")
    print("no duplicate X alert after the next restart; tomorrow's Most Shared")
    print("post (02:00 PKT) carries premium emojis.")


if __name__ == "__main__":
    main()
