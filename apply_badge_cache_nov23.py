#!/usr/bin/env python3
"""Badge cache fix (Nov 23 2026) — get the bot posting again.

Problem: commands work but NO posts are happening. CPU is ~85% even
after the prerender fix, and the event loop is starved, so the
monitoring / posting jobs cannot run on time.

Root cause: _get_kol_badge() is called for EVERY X alert, and it does
disk I/O (load_channel_points + load_config) plus full scans over ALL
channels and all tracked calls, every single time. The leaderboard
scores themselves are already cached (Nov 18 fix, live), but
_get_kol_badge does a lot of its OWN work on top of the scores, and
that work is never cached. During an active market, many X alerts
fire, so _get_kol_badge runs over and over, burning CPU and blocking
the event loop — posts stall.

Fix (x_alert.py only): a 60-second per-channel cache for the badge.
A channel's champion / leaderboard rank does not change in 60s, so a
60s-old badge is fine for an X alert. The cache is a small dict
(channel -> (timestamp, badge)); entries older than 5 minutes are
dropped so it never grows. If anything fails, it falls back to
calling _get_kol_badge directly (old behaviour).

Changes:
1. Module-level _BADGE_CACHE dict + _cached_badge(channel) helper.
2. The two _get_kol_badge call sites in the X-alert send path now
   call _cached_badge instead.

Safety: X alerts are NOT delayed (the badge is only a label — the
alert itself still fires immediately when a milestone is hit). The
rankings are NOT changed (the cache only reuses a 60s-old badge for
display). NO data is deleted. The monitoring jobs are UNTOUCHED.

Requires: live /opt/bot/x_alert.py. Run once from /opt/bot:
    python3 apply_badge_cache_nov23.py x_alert.py
VPS-only one-time script. Idempotent (marker BADGE_CACHE_NOV23).
Backup: x_alert.py.bak_badge_nov23.
Fail-safe: validates ALL anchors before writing anything; aborts
without touching any file on mismatch.
"""

import sys, shutil

MARKER = "BADGE_CACHE_NOV23"

# 1. Cache dict + helper, inserted after the file header.
OLD_1 = """# ===== x_alert.py — X alerts (milestones), templates, send_alert, true-X, monitoring, Hot Streak =====
# Loaded by bot.py into ONE shared namespace (no imports needed between pieces)."""
NEW_1 = """# ===== x_alert.py — X alerts (milestones), templates, send_alert, true-X, monitoring, Hot Streak =====
# Loaded by bot.py into ONE shared namespace (no imports needed between pieces).

# BADGE_CACHE_NOV23: 60s per-channel cache for _get_kol_badge.
# _get_kol_badge does disk I/O + full channel/call scans on every call,
# and it runs for every X alert. A 60s-old badge is fine — a channel's
# champion/leaderboard rank does not change in 60s.
_BADGE_CACHE = {}


def _cached_badge(channel):
    try:
        import time as _t
        _now = _t.time()
        _key = (channel or "").lower()
        _ent = _BADGE_CACHE.get(_key)
        if _ent is not None and (_now - _ent[0]) < 60:
            return _ent[1]
        _bdg = _get_kol_badge(channel)
        _BADGE_CACHE[_key] = (_now, _bdg)
        for _k in [k for k, v in _BADGE_CACHE.items() if (_now - v[0]) > 300]:
            _BADGE_CACHE.pop(_k, None)
        return _bdg
    except Exception:
        try:
            return _get_kol_badge(channel)
        except Exception:
            return None"""

# 2. First call site (badge resolved up-front in the alert builder).
OLD_2 = """    if badge is None:
        badge = _get_kol_badge(channel)"""
NEW_2 = """    if badge is None:
        badge = _cached_badge(channel)"""

# 3. Second call site (badge computed once for build_alert + emoji list).
OLD_3 = """    badge    = _get_kol_badge(channel)"""
NEW_3 = """    badge    = _cached_badge(channel)"""

EDITS = [
    ("E1 badge cache dict + helper", OLD_1, NEW_1),
    ("E2 cached badge (alert builder)", OLD_2, NEW_2),
    ("E3 cached badge (build_alert path)", OLD_3, NEW_3),
]


def patch_file(path, edits):
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print("FAIL: %s not found" % path)
        return False
    if MARKER in src:
        print("OK: %s already has %s, skipping." % (path, MARKER))
        return True
    for name, old, new in edits:
        if src.count(old) != 1:
            print("FAIL: anchor missing/dup in %s for %s (found %dx) -- NOT writing "
                  "anything. Send the live file so the patch can be rebuilt."
                  % (path, name, src.count(old)))
            return False
    shutil.copy(path, path + ".bak_badge_nov23")
    print("Backup: %s.bak_badge_nov23" % path)
    for name, old, new in edits:
        src = src.replace(old, new, 1)
        print("OK: %s (%s)" % (name, path))
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
        if not patch_file(path, EDITS):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("Posts should resume — the badge cache frees the event loop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
