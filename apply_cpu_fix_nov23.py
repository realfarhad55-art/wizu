#!/usr/bin/env python3
"""CPU fix (Nov 23 2026) — the dropped call is slow because the bot's
CPU is pegged at ~97%, starving the event loop. The dropped-call code
is already fast (patches + variables are correct, bot restarted), but
the bot is too busy to post promptly.

Root cause (verified in code + live `ps` output): champion_prerender_job
runs every 15 SECONDS and, for every tracked call near a video level,
calls _get_kol_badge — which does disk I/O (load_channel_points +
load_config) and full scans over ALL channels AND all 2355 tracked
calls, every single time. That is the CPU hog.

Changes (2 files):
1. runtime.py — champion_prerender_job interval 15 -> 60 seconds.
   A call takes minutes to go from 80% to 100% of a video level, so
   a 60s check still catches it in time. 4x fewer prerender runs.
2. x_alert.py — champion_prerender_job: load the points ONCE per run
   (not per call), and skip the expensive _get_kol_badge entirely for
   channels with < 100 points. Only champion channels (>=100 pts) can
   ever need a champion video base, so everyone else is skipped with a
   cheap dict lookup. If the points load fails, nothing is skipped
   (safe fallback to the old behaviour).

Champion X alerts are NOT delayed: champion channels are still
pre-rendered (checked every 60s, and a call needs minutes to travel
80% -> 100% of a level), and if a base is ever missing the alert
renders it on demand. Non-champion channels never needed a champion
video base at all. The monitoring jobs (X-alert detection) are
UNTOUCHED.

Requires: live /opt/bot/runtime.py + x_alert.py. Run once from /opt/bot:
    python3 apply_cpu_fix_nov23.py runtime.py x_alert.py
VPS-only one-time script. Idempotent (marker CPU_FIX_NOV23).
Backups: runtime.py.bak_cpu_nov23, x_alert.py.bak_cpu_nov23.
Fail-safe: validates ALL anchors before writing anything; aborts
without touching any file on mismatch.
"""

import sys, shutil

MARKER = "CPU_FIX_NOV23"

# 1. runtime.py — prerender interval 15 -> 60.
OLD_RT = """    app.job_queue.run_repeating(champion_prerender_job, interval=15,     first=30)   # pre-render champion video bases for calls near a video level  # CHAMPION_VIDEO_FINAL_NOV10"""
NEW_RT = """    app.job_queue.run_repeating(champion_prerender_job, interval=60,     first=30)   # pre-render champion video bases for calls near a video level  # CHAMPION_VIDEO_FINAL_NOV10  # CPU_FIX_NOV23: 15s -> 60s, a call needs minutes to travel 80% -> 100% of a level"""

# 2a. x_alert.py — load points once per prerender run.
OLD_XA = """    # Find the next video level each champion call is approaching.
    _cands = []
    try:
        _badge_fn = globals().get("_get_kol_badge")"""
NEW_XA = """    # Find the next video level each champion call is approaching.
    _cands = []
    try:
        _badge_fn = globals().get("_get_kol_badge")
        # CPU_FIX_NOV23: load points ONCE per run, so the champion
        # check below is a cheap dict lookup, not disk I/O per call.
        try:
            _cpu_pts = load_channel_points()
        except Exception:
            _cpu_pts = None"""

# 2b. x_alert.py — skip _get_kol_badge for non-champion channels.
OLD_XB = """            if _badge_fn is not None:
                try:
                    _bdg = _badge_fn(_ch)"""
NEW_XB = """            # CPU_FIX_NOV23: only champion channels (>=100 pts) can
            # ever need a champion video base. Skip the expensive
            # _get_kol_badge (disk I/O + full channel/call scans) for
            # everyone else. If points failed to load, do not skip.
            if _cpu_pts is not None and (_cpu_pts.get(_ch.lower(), {}) or {}).get("points", 0) < 100:
                continue
            if _badge_fn is not None:
                try:
                    _bdg = _badge_fn(_ch)"""

EDITS = {
    "runtime.py": [
        ("E1 prerender interval 15 -> 60s", OLD_RT, NEW_RT),
    ],
    "x_alert.py": [
        ("E2 load points once per run", OLD_XA, NEW_XA),
        ("E3 skip badge for non-champions", OLD_XB, NEW_XB),
    ],
}


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
    shutil.copy(path, path + ".bak_cpu_nov23")
    print("Backup: %s.bak_cpu_nov23" % path)
    for name, old, new in edits:
        src = src.replace(old, new, 1)
        print("OK: %s (%s)" % (name, path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    args = sys.argv[1:]
    if not args:
        args = ["runtime.py", "x_alert.py"]
    ok = True
    for path in args:
        base = path.rsplit("/", 1)[-1]
        if base not in EDITS:
            print("FAIL: unknown file %s" % path)
            ok = False
            continue
        if not patch_file(path, EDITS[base]):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("Then check CPU with: ps aux | grep \"venv/bin/python bot.py\" | grep -v grep")
    print("CPU should drop well below 97%. Champion X alerts are NOT delayed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
