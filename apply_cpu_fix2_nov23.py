#!/usr/bin/env python3
"""CPU fix part 2 — leaderboard scores cache (Nov 23 2026).

CPU dropped 97.7% -> 87.9% after part 1 (prerender 60s + skip
non-champions), but it is still far too high. The remaining hog:
_calc_leaderboard_scores() is recalculated from scratch on EVERY call
— disk I/O (load_channel_points + load_config) + full scans over ALL
channels and all 2355 tracked calls — and it is called for every X
alert badge, every prerender candidate, and every leaderboard /
champion post build. There is NO cache in the live-equivalent code
(the Nov 18 LEADERBOARD_CACHE_NOV23 fix is not present there).

This patch adds a 60-second cache. A 60s-old ranking is fine for
every use (badge rank, leaderboard post, champion post) — none of
them need sub-minute freshness, and the scores only change when a
call hits a new milestone.

Changes (leaderboard.py only):
1. Module-level cache dict _LB_SCORES_CACHE = {"ts": 0.0, "data": None}.
2. At the start of _calc_leaderboard_scores(): if the cache is fresh
   (< 60s old), return a copy of it immediately — no disk I/O, no scans.
3. Before the return: store the fresh result in the cache.

Safety: the cache is only a performance shortcut. If it is ever
stale or empty, the function computes normally. The returned list is
a copy, so callers cannot mutate the cached data. If time import
fails, the cache is bypassed and the function computes normally.

Requires: live /opt/bot/leaderboard.py. Run once from /opt/bot:
    python3 apply_cpu_fix2_nov23.py leaderboard.py
VPS-only one-time script. Idempotent (marker CPU_FIX2_NOV23).
Backup: leaderboard.py.bak_cpu2_nov23.
Fail-safe: validates ALL anchors before writing anything; aborts
without touching any file on mismatch.
"""

import sys, shutil

MARKER = "CPU_FIX2_NOV23"

# 1. Cache dict before the function.
OLD_1 = """def _calc_leaderboard_scores():
    \"\"\"Calculate top 10 leaderboard channels.
    Channels already in Champions list (>=100 points, top-10) are excluded
    so they don't appear in both lists.
    Returns list of (ch, best_x, wizard_post_id).\"\"\""""
NEW_1 = """# CPU_FIX2_NOV23: 60s cache for leaderboard scores (see below).
_LB_SCORES_CACHE = {"ts": 0.0, "data": None}


def _calc_leaderboard_scores():
    \"\"\"Calculate top 10 leaderboard channels.
    Channels already in Champions list (>=100 points, top-10) are excluded
    so they don't appear in both lists.
    Returns list of (ch, best_x, wizard_post_id).\"\"\"
    # CPU_FIX2_NOV23: return the cached ranking when it is fresh (< 60s).
    # Scores only change on a new milestone, so a 60s-old ranking is fine
    # for badges, leaderboard posts and champion posts alike.
    try:
        import time as _t
        _c = _LB_SCORES_CACHE
        if _c.get("data") is not None and (_t.time() - float(_c.get("ts", 0) or 0)) < 60:
            return list(_c["data"])
    except Exception:
        pass"""

# 2. Store the fresh result in the cache before returning.
OLD_2 = """    lb_scores = [(ch, x, wpost) for ch, (x, wpost) in all_scores.items()]
    lb_scores.sort(key=lambda t: t[1], reverse=True)
    return lb_scores[:10]"""
NEW_2 = """    lb_scores = [(ch, x, wpost) for ch, (x, wpost) in all_scores.items()]
    lb_scores.sort(key=lambda t: t[1], reverse=True)
    # CPU_FIX2_NOV23: store the fresh ranking in the 60s cache.
    try:
        import time as _t2
        _LB_SCORES_CACHE["ts"] = _t2.time()
        _LB_SCORES_CACHE["data"] = list(lb_scores[:10])
    except Exception:
        pass
    return lb_scores[:10]"""

EDITS = [
    ("E1 cache dict + fresh-check", OLD_1, NEW_1),
    ("E2 store result in cache", OLD_2, NEW_2),
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
    shutil.copy(path, path + ".bak_cpu2_nov23")
    print("Backup: %s.bak_cpu2_nov23" % path)
    for name, old, new in edits:
        src = src.replace(old, new, 1)
        print("OK: %s (%s)" % (name, path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    args = sys.argv[1:]
    if not args:
        args = ["leaderboard.py"]
    ok = True
    for path in args:
        if not path.endswith("leaderboard.py"):
            print("FAIL: unknown file %s (expected leaderboard.py)" % path)
            ok = False
            continue
        if not patch_file(path, EDITS):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("Then check CPU with: ps aux | grep \"venv/bin/python bot.py\" | grep -v grep")
    print("CPU should drop a lot further. Dropped call should then land ~2s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
