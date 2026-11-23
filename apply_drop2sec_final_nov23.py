#!/usr/bin/env python3
"""Dropped call in 2 seconds — FINAL (Nov 23 2026).

User (Nov 23): v2 deployed but still not working, "sara din is pr nai
waste krna, 100% final work krain" — do not waste the whole day, do a
100% final fix.

Why v2 was still not 2s (verified in the code): v2 shortened the
pre-post confirm loop, but the loop still runs on EVERY call — two
confirm reads, each a network round-trip, before the post. Fetch
(~0.5-1s) + confirm loop (~1-1.5s) + queue/send (~0.5-1s) = ~2.5-3.5s
even with v2. The confirm loop is the remaining serial delay, and no
timeout cut can remove it — it has to be SKIPPED for solid data.

The fix (this patch): when the first fetch already returned complete,
solid data, SKIP the pre-post confirm loop entirely and post now.
Solid = real (non-FDV) MC >= $100 + symbol present. A dust MC
(<$100, the $OWED case) or FDV-only / missing symbol still runs the
full confirm loop, so dust protection is kept.

Safety (why this does not break entries): the codebase already
accepts this tradeoff — the comment above the loop says a slightly-off
entry "can no longer cascade into a fake milestone burst" because two
backstops exist independently of this step: the 48s background
_confirm_entry_mc task, and the universal ratio-jump cap in
_verified_live_ratio() (rejects any milestone tick implying a >20x
jump over the last confirmed peak). So a slightly-off entry is
corrected in the record and cannot fake X alerts. The posted message
uses the fetch MC, which for solid data is the real MC.

Changes (dropped_call.py only, ONE edit):
- Right after _nr_max is computed, if the fetch data is solid, set
  _nr_max = 0.0. The loop's first check is `if _el >= _nr_max - 1.0:
  break` — with _nr_max = 0.0 that is `if _el >= -1.0`, always true,
  so the loop exits immediately with zero reads and the post goes out.
  The `if _nr_reads:` block after the loop is already guarded, so an
  empty _nr_reads is safe (entry MC stays the fetch value).

Effect: solid call = fetch (~0.5-1s) + floor (<=1s, only if the fetch
was fast) + send (~0.5-1s) = ~2s after the KOL message. Suspicious
call (dust / FDV / no symbol) = full confirm loop as before.
RH-chain calls are UNTOUCHED (RH_PRE_POST_MIN 10s / MAX 60s stay).

Requires: live /opt/bot/dropped_call.py WITH v2 (DROP2SEC_B_NOV23)
already applied. Run once from /opt/bot:
    python3 apply_drop2sec_final_nov23.py dropped_call.py
VPS-only one-time script. Idempotent (marker DROP2SEC_FINAL_NOV23).
Backup: dropped_call.py.bak_drop2sec_final_nov23.
Fail-safe: validates the anchor before writing anything; aborts
without touching any file on mismatch.
"""

import sys, shutil

MARKER = "DROP2SEC_FINAL_NOV23"

OLD = """                                    _nr_min = float(os.environ.get("POST_MIN_SECONDS", "1") or 1)
                                    _nr_max = max(float(os.environ.get("POST_MAX_SECONDS", "2") or 2), _nr_min)"""
NEW = """                                    _nr_min = float(os.environ.get("POST_MIN_SECONDS", "1") or 1)
                                    _nr_max = max(float(os.environ.get("POST_MAX_SECONDS", "2") or 2), _nr_min)
                                    # DROP2SEC_FINAL_NOV23: fetch already returned complete,
                                    # solid data — SKIP the pre-post confirm loop entirely.
                                    # Solid = real (non-FDV) MC >= $100 + symbol present.
                                    # Dust (<$100, the $OWED case) or FDV-only / missing
                                    # symbol still runs the full confirm loop. The 48s
                                    # background confirm + ratio-jump cap correct a
                                    # slightly-off entry, so this cannot fake X alerts.
                                    if (dex.get("mcap", 0) or 0) >= 100 and dex.get("symbol") and not dex.get("_mc_is_fdv"):
                                        _nr_max = 0.0"""


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
              "anything. This patch needs v2 (DROP2SEC_B_NOV23) applied "
              "first. Send the live file so the patch can be rebuilt."
              % (path, src.count(OLD)))
        return False
    shutil.copy(path, path + ".bak_drop2sec_final_nov23")
    print("Backup: %s.bak_drop2sec_final_nov23" % path)
    src = src.replace(OLD, NEW, 1)
    print("OK: solid-data fast path — skip pre-post confirm loop (%s)" % path)
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
    print("Verify on the next KOL call: the dropped call should land ~2s")
    print("after the KOL message (video + premium emojis + correct entry).")
    print("RH-chain calls are unchanged (they still wait 10s+ for a real MC).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
