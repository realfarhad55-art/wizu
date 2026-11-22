#!/usr/bin/env python3
"""DIP_MAX99_NOV23 - Dip range: min 30% / max 99% (user spec, Nov 23).

User (Nov 23 ~03:29 PKT): "99% krain.. max 99% aur min 30% ok?"
Meaning: a dip counts only when MC falls at least 30% below entry
(min, already the threshold), and the dip low may go as deep as 99%
below entry (100K -> 1K, the Kolscope example) but no deeper.
A low below 1% of entry is dust / a glitch read and must not set
dip_low (the $OWED lesson: a dust price locking a $3 entry).

Change (one line, x_alert.py only):
  DIP_DUST_FLOOR_FRAC = 0.001  ->  0.01
  - floor 0.1% meant lows down to 99.9% dip counted.
  - floor 1% means lows must stay >= 1% of entry (max 99% dip).
  - the 30% min is untouched: dip_threshold_pct() default 30,
    live config already 30 (confirmed by /showdipset Nov 23).

Not touched: threshold, milestones, titles, template, emojis, media
hold, DM-only delivery, /testdip, or any other feature.

VPS-only one-time script. Idempotent (marker DIP_MAX99_NOV23).
Backup: x_alert.py.bak_max99_nov23. Fail-safe: validates the anchor
before writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_dip_max99_nov23.py
"""

import os
import sys

MARKER = "DIP_MAX99_NOV23"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_max99_nov23"

OLD_FLOOR = "DIP_DUST_FLOOR_FRAC = 0.001"
NEW_FLOOR = ("DIP_DUST_FLOOR_FRAC = 0.01  # DIP_MAX99_NOV23: max dip 99% "
             "(low must stay >= 1% of entry)")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    print(f"{MARKER} patch - target dir: {BOT_DIR}")
    path = os.path.join(BOT_DIR, "x_alert.py")
    if not os.path.isfile(path):
        print(f"ABORT: {path} not found. Run this script in /opt/bot.")
        sys.exit(1)
    text = _read(path)

    # ---- Phase 1: validate anchor before writing anything ----
    n_old = text.count(OLD_FLOOR)
    n_new = text.count(NEW_FLOOR)
    if n_new >= 1:
        print("SKIP: x_alert.py already patched (DIP_MAX99_NOV23 present).")
        print("DONE. No change needed - just restart if you have not since.")
        return
    if n_old != 1:
        print(f"ABORT: anchor {OLD_FLOOR!r} found {n_old}x (expected 1).")
        print("Nothing was written. Check the live file and re-run after fixing.")
        sys.exit(1)

    # ---- Phase 2: apply ----
    bak = path + BAK_SUFFIX
    _write(bak, text)
    print(f"Backup: {bak}")
    _write(path, text.replace(OLD_FLOOR, NEW_FLOOR, 1))
    print("Patched: x_alert.py (DIP_DUST_FLOOR_FRAC 0.001 -> 0.01)")

    print("DONE. Now restart the bot: systemctl restart bot.service")
    print("Then verify: /showdipset (threshold still 30%) and /testdip 5.")


if __name__ == "__main__":
    main()
