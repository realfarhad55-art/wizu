#!/usr/bin/env python3
"""Stop re-processing old posts as new calls (Nov 23 2026).

Problem: after every restart the bot re-scans the channel history and
treats old posts as brand-new dropped calls — one by one, including
rug projects — and then fires X alerts for them (even millions of X
when the entry was dust). The seen list is empty after a redeploy,
so nothing is deduplicated, and the catch-up window (30 min normal,
6h special) lets hours of old posts through as "new".

Fix (dropped_call.py only): force the catch-up window to ZERO for
both normal and special channels. After this, the bot only processes
a post if it arrived AFTER the bot started (BOT_START_TS). Any post
older than the startup time is marked seen and skipped, no matter
what the .env says. This is the permanent end of the re-process
spam — a restart can never again flood the feed with old posts.

What keeps working: genuinely NEW calls posted after the bot starts
are processed normally. Dropped calls, X alerts, points, leaderboard
— all normal for new posts.

Requires: live /opt/bot/dropped_call.py. Run once from /opt/bot:
    python3 apply_nocatchup_nov23.py dropped_call.py
VPS-only one-time script. Idempotent (marker NOCATCHUP_NOV23).
Backup: dropped_call.py.bak_nocatchup_nov23.
Fail-safe: validates the anchor before writing; aborts without
touching any file on mismatch.
"""

import sys, shutil

MARKER = "NOCATCHUP_NOV23"

OLD = """                lookback_minutes = (float(os.environ.get("SPECIAL_CATCHUP_MINUTES", "360") or 360)
                                    if is_special_channel else
                                    float(os.environ.get("CALL_CATCHUP_MINUTES", "30") or 30))"""
NEW = """                # NOCATCHUP_NOV23: catch-up window forced to 0. After a restart
                # the bot must NEVER re-process old posts as new calls — that
                # is what floods the feed with duplicate drops + fake X
                # alerts (incl. millions-of-X on rugs). Only posts that
                # arrived after this boot are processed.
                lookback_minutes = 0.0"""


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
    shutil.copy(path, path + ".bak_nocatchup_nov23")
    print("Backup: %s.bak_nocatchup_nov23" % path)
    src = src.replace(OLD, NEW, 1)
    print("OK: catch-up window forced to 0 (%s)" % path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    args = sys.argv[1:]
    if not args:
        args = ["dropped_call.py"]
    ok = True
    for path in args:
        if not path.endswith("dropped_call.py"):
            print("FAIL: unknown file %s (expected dropped_call.py)" % path)
            ok = False
            continue
        if not patch_file(path):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("Old posts will NEVER be re-processed as new calls again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
