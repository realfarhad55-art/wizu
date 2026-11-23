#!/usr/bin/env python3
"""Dropped call in 2 seconds — v2 (Nov 23 2026).

v1 failed safely on the VPS: its E3 anchor (DROP_SETTLE_SECONDS /
DROP_CONFIRM_TIMEOUT_SEC code defaults 0.5 / 1.0) was NOT found in the
live dropped_call.py (found 0x), so v1 wrote NOTHING and the bot
restarted on the old code (no harm). The Nov 19 DROP patches already
changed those two defaults in the live file (and the .env already sets
0.2 / 0.5), so E3 is redundant. v2 drops E3 and keeps the three edits
that matter.

Why it was still slow (verified in the live-equivalent code):
- POST_MIN_SECONDS code default is STILL 5s and POST_MAX_SECONDS is
  STILL 10s (dropped_call.py). The .env sets 1/2, but the code defaults
  are the fallback — and the Oct 11 owner requirement ("post NOT before
  5s, NOT after 10s") is baked into the comment. The user now overrides
  that requirement: 2 seconds.
- The pre-post confirm loop does 2 reads that must agree within 10%,
  spaced by sleeps: first read after 0.5s, then 2.5s between reads.
  That is ~3s of confirm alone, before the queue + send (~0.5-1s).
  The 2.5s gap exists so the two reads are independent — but the cache
  is already invalidated before EVERY read (_invalidate_dex_cache), so
  each read is a fresh API call; a 0.5s gap still gives two independent
  reads. The 2-read agreement rule itself is UNCHANGED (correctness
  kept: dust / wrong-entry protection stays).

Changes (dropped_call.py only):
1. POST_MIN_SECONDS code default 5 -> 1; POST_MAX_SECONDS code default
   10 -> 2. (Matches the .env; overrides the Oct 11 5s/10s requirement
   per the user's Nov 23 instruction. The confirm loop cap is now 2s.)
2. Confirm loop sleeps: first read 0.5s -> 0.2s; between reads
   2.5s -> 0.5s. Two agreeing reads now complete in ~1s instead of ~3s.
3. The post floor sleep also reads POST_MIN_SECONDS — default 5 -> 1.

Effect: detection -> fetch -> 2 agreeing confirm reads (~1s) -> post
lands ~2s after the KOL message (plus network/send, which cannot go
below ~0.5s). Entry-MC correctness is kept: 2-read agreement within
10% + the 48s background confirm + ratio-jump cap still apply, and the
dust guard (ENTRY_DUST_NOV20) is untouched. RH-chain calls are
UNTOUCHED (RH_PRE_POST_MIN 10s / MAX 60s stay — RH needs the long
wait for a real non-FDV MC).

Requires: live /opt/bot/dropped_call.py. Run once from /opt/bot:
    python3 apply_drop2sec_nov23b.py dropped_call.py
VPS-only one-time script. Idempotent (marker DROP2SEC_B_NOV23).
Backup: dropped_call.py.bak_drop2sec_b_nov23.
Fail-safe: validates ALL anchors before writing anything; aborts
without touching any file on mismatch.
"""

import sys, shutil

MARKER = "DROP2SEC_B_NOV23"

# 1. POST_MIN/POST_MAX code defaults 5/10 -> 1/2.
OLD_1 = """                                    # OWNER REQUIREMENT (2026-10-11): non-RH chains must post NOT before
                                    # POST_MIN_SECONDS (default 5s) and NOT after POST_MAX_SECONDS (default 10s) from
                                    # detection, with the MC verified against fresh independent reads in that window.
                                    _nr_min = float(os.environ.get("POST_MIN_SECONDS", "5") or 5)
                                    _nr_max = max(float(os.environ.get("POST_MAX_SECONDS", "10") or 10), _nr_min)"""
NEW_1 = """                                    # OWNER REQUIREMENT (2026-10-11, SUPERSEDED Nov 23 by the user):
                                    # non-RH chains must post NOT before POST_MIN_SECONDS and NOT
                                    # after POST_MAX_SECONDS from detection, with the MC verified
                                    # against fresh independent reads in that window. The user
                                    # now wants the dropped call in 2 SECONDS, so the defaults
                                    # are 1s / 2s (the .env already sets 1/2; this makes the
                                    # code fast even if .env is not loaded).
                                    _nr_min = float(os.environ.get("POST_MIN_SECONDS", "1") or 1)
                                    _nr_max = max(float(os.environ.get("POST_MAX_SECONDS", "2") or 2), _nr_min)"""

# 2. Confirm loop sleeps: first 0.5 -> 0.2, between reads 2.5 -> 0.5.
OLD_2 = """                                        await asyncio.sleep(min(0.5 if _nr_i == 0 else 2.5, max(0.0, _nr_max - 1.0 - _el)))"""
NEW_2 = """                                        # DROP2SEC_B_NOV23: reads are 0.5s apart (was 2.5s). The cache
                                        # is invalidated before every read, so each read is a
                                        # fresh API call; 0.5s still gives two independent reads.
                                        await asyncio.sleep(min(0.2 if _nr_i == 0 else 0.5, max(0.0, _nr_max - 1.0 - _el)))"""

# 3. The post floor sleep also reads POST_MIN_SECONDS — default 5 -> 1.
OLD_3 = """                            _floor_left = float(os.environ.get("POST_MIN_SECONDS", "5") or 5) - (_t.time() - _call_detected_at)"""
NEW_3 = """                            _floor_left = float(os.environ.get("POST_MIN_SECONDS", "1") or 1) - (_t.time() - _call_detected_at)"""

EDITS = [
    ("E1 POST_MIN/MAX defaults 1/2", OLD_1, NEW_1),
    ("E2 confirm loop sleeps 0.2/0.5", OLD_2, NEW_2),
    ("E3 post floor default 1s", OLD_3, NEW_3),
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
    shutil.copy(path, path + ".bak_drop2sec_b_nov23")
    print("Backup: %s.bak_drop2sec_b_nov23" % path)
    for name, old, new in edits:
        src = src.replace(old, new, 1)
        print("OK: %s (%s)" % (name, path))
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
        if not patch_file(path, EDITS):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("Verify on the next KOL call: the dropped call should land ~2s")
    print("after the KOL message (video + premium emojis + correct entry).")
    print("RH-chain calls are unchanged (they still wait 10s+ for a real MC).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
