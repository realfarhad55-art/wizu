#!/usr/bin/env python3
"""Dip low confirm 2 -> 1 tick (Nov 23 2026).

Problem: real dip alerts NEVER fire even though calls dip 30%+ and
pump 2x+ from the low. Root cause: DIP_LOW_CONFIRM_TICKS = 2 means
the low must be seen TWICE near the same level before it counts.
A fast V-shape dip (price dips to the low on one tick, pumps on the
next) is only seen ONCE, so dip_low is never set, so no dip X can
ever be measured, so no dip alert fires.

Fix (x_alert.py only): DIP_LOW_CONFIRM_TICKS 2 -> 1. The low is
trusted on first sight. The dust guard (low must stay >= 1% of
entry, DIP_DUST_FLOOR_FRAC) and check_one's verified-live-MC guards
(FDV guard + spike-glitch guard + entry gate) already rule out the
bad reads the 2-tick rule was added for (the $OWED dust lesson).

What keeps working: dip threshold 30%, dust floor 1%, multi-dip
reset (20% below), milestones, DM-only delivery, media hold — all
unchanged. Only the low-confirmation count changes.

Requires: live /opt/bot/x_alert.py. Run once from /opt/bot:
    python3 apply_dipconfirm1_nov23.py x_alert.py
VPS-only one-time script. Idempotent (marker DIPCONFIRM1_NOV23).
Backup: x_alert.py.bak_dipconfirm1_nov23.
Fail-safe: validates the anchor before writing; aborts without
touching any file on mismatch.
"""

import sys, shutil

MARKER = "DIPCONFIRM1_NOV23"

OLD = "DIP_LOW_CONFIRM_TICKS = 2"
NEW = "DIP_LOW_CONFIRM_TICKS = 1  # DIPCONFIRM1_NOV23: V-shape lows confirm on first sight"


def patch_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print("FAIL: %s not found" % path)
        return False
    if MARKER in src:
        print("OK: %s already has %s, skipping." % (path, MARKER))
        return True
    if src.count(OLD) != 1:
        print("FAIL: anchor missing/dup in %s (found %dx) -- NOT writing "
              "anything. Send the live file so the patch can be rebuilt."
              % (path, src.count(OLD)))
        return False
    shutil.copy(path, path + ".bak_dipconfirm1_nov23")
    print("Backup: %s.bak_dipconfirm1_nov23" % path)
    src = src.replace(OLD, NEW, 1)
    print("OK: dip low now confirms on first sight (%s)" % path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    args = sys.argv[1:]
    if not args:
        args = ["x_alert.py"]
    ok = True
    for path in args:
        if not path.endswith("x_alert.py"):
            print("FAIL: unknown file %s (expected x_alert.py)" % path)
            ok = False
            continue
        if not patch_file(path):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("V-shape dips will now confirm on first sight; dip alerts fire.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
