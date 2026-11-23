#!/usr/bin/env python3
"""Split monitoring: bulk lane every 10s, priority lane stays 1s (Nov 23 2026).

Problem: CPU is 96% even after the badge cache. The bulk monitoring
lane scans all ~3339 tracked calls every 2 seconds, which starves
the event loop — dropped calls take 12s instead of 2s. The priority
lane (special/champion channels, 1s) must stay fast, but normal
calls do not need a 2-second check.

Fix (x_alert.py only): in _monitoring_job_body, when prio_mode is
False (bulk lane), run only every 5th tick. The job still fires
every 2s, but 4 out of 5 ticks return immediately, so the bulk lane
effectively runs every 10s. CPU from bulk monitoring drops ~80%.
The priority lane (prio_mode=True, 1s) is untouched — champion and
special-channel X alerts stay fast.

What keeps working: champion/special calls are checked every 1s
(priority lane). Normal calls are checked every 10s — their X
alerts can be up to ~10s late, which is the accepted tradeoff for
the CPU saving. Dropped calls (separate path) get the freed CPU
and should return to ~2s.

Requires: live /opt/bot/x_alert.py. Run once from /opt/bot:
    python3 apply_monsplit_nov23.py x_alert.py
VPS-only one-time script. Idempotent (marker MONSPLIT_NOV23).
Backup: x_alert.py.bak_monsplit_nov23.
Fail-safe: validates the anchor before writing; aborts without
touching any file on mismatch.
"""

import sys, shutil

MARKER = "MONSPLIT_NOV23"

OLD = """async def _monitoring_job_body(context: ContextTypes.DEFAULT_TYPE, prio_mode: bool):
    try:
        bot   = context.bot"""
NEW = """async def _monitoring_job_body(context: ContextTypes.DEFAULT_TYPE, prio_mode: bool):
    # MONSPLIT_NOV23: bulk (non-priority) lane runs every 5th tick (10s)
    # instead of every 2s, so CPU drops ~70%. Priority lane (1s) is
    # untouched — champion/special X alerts stay fast.
    global _BULK_TICK
    if not prio_mode:
        _BULK_TICK = globals().get("_BULK_TICK", 0) + 1
        globals()["_BULK_TICK"] = _BULK_TICK
        if _BULK_TICK % 5 != 0:
            return
    try:
        bot   = context.bot"""


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
    shutil.copy(path, path + ".bak_monsplit_nov23")
    print("Backup: %s.bak_monsplit_nov23" % path)
    src = src.replace(OLD, NEW, 1)
    print("OK: bulk monitoring lane now every 5th tick (10s) (%s)" % path)
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
    print("Bulk monitoring runs every 10s; priority lane stays 1s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
