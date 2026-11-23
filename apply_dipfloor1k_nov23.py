#!/usr/bin/env python3
"""Dip low floor: fixed 1K MC minimum (Nov 23 2026).

User rule: the lowest dip low is 1K MC, fixed — not 1% of entry.
Before: DIP_DUST_FLOOR_FRAC = 0.01 (low must stay >= 1% of entry,
so a 10K entry could dip to 100 MC, a 1M entry only to 10K).
After: the low must stay >= $1,000 MC, no matter the entry.

Fix (x_alert.py only): replace the dust-floor fraction check with a
fixed 1,000 MC minimum. DIP_DUST_FLOOR_FRAC is left in place (unused
by the check now) so nothing else breaks.

What keeps working: dip threshold 30%, 1-tick low confirm, multi-dip
reset (20% below), milestones, DM-only delivery, media hold — all
unchanged. Only the lowest allowed dip low changes.

Requires: live /opt/bot/x_alert.py. Run once from /opt/bot:
    python3 apply_dipfloor1k_nov23.py x_alert.py
VPS-only one-time script. Idempotent (marker DIPFLOOR1K_NOV23).
Backup: x_alert.py.bak_dipfloor1k_nov23.
Fail-safe: validates the anchor before writing; aborts without
touching any file on mismatch.
"""

import sys, shutil

MARKER = "DIPFLOOR1K_NOV23"

OLD = "        if cur_mc >= entry_mc * DIP_DUST_FLOOR_FRAC:"
NEW = "        if cur_mc >= 1000.0:  # DIPFLOOR1K_NOV23: lowest dip low is 1K MC, fixed"


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
    shutil.copy(path, path + ".bak_dipfloor1k_nov23")
    print("Backup: %s.bak_dipfloor1k_nov23" % path)
    src = src.replace(OLD, NEW, 1)
    print("OK: dip low floor is now fixed 1K MC (%s)" % path)
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
    print("Dip low can never go below 1K MC now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
