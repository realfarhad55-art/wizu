"""apply_perm_nov23.py - PERMANENT fix for the 2 things (user order).

Runs ON TOP of FINAL_NOV23 (already live). Two edits:

E1 - RESET-PROOF, COMPLETE (old data never returns, even after a
restart). FINAL's startup seal skipped corrupted records (peak/entry
missing) — those are exactly the calls the v2 rebuild had to seal to
100x. If sent_milestones.json goes stale, a corrupted call could re-fire
its old milestones after a restart. Fix: the seal now also seals
corrupted calls (entry<=0 or peak<=0) to 100x, same as the v2 rebuild.
After this, NO call — healthy or corrupted — can re-fire an old
milestone after a restart.

E2 - DROPPED CALL 2 SECONDS (permanent). The bulk monitoring lane does
up to 110 checks per tick; when the API is slow its tick overlaps the
next one, the lane wedges, the event loop starves, and the real-time
dropped-call handler runs late (12s). Fix: bulk lane does at most 60
checks per tick, so each tick finishes fast and the loop stays free for
dropped calls. Priority lane UNTOUCHED (130 checks, 1s — champion X
alerts stay fast). Monitoring INTERVAL untouched. No data deleted.
Tradeoff: old/regular calls rotate a bit slower (checked ~every 9 min
instead of ~5 min); fresh/hot calls are always checked first, so new
pumps are still caught instantly.

Idempotent. Backs up x_alert.py to x_alert.py.bak_perm_nov23.
Run: python3 apply_perm_nov23.py x_alert.py
Then: systemctl restart bot.service
"""

import sys, shutil

MARKER = "PERM_NOV23"

# --- E1: seal corrupted calls to 100x in the startup seal ---
OLD1 = '''            if _entry <= 0 or _peak <= 0:
                continue
            _bx = _peak / _entry'''

NEW1 = '''            if _entry <= 0 or _peak <= 0:
                # PERM_NOV23: corrupted record (no peak/entry) — seal to
                # 100x like the v2 rebuild did, so a restart can never
                # re-fire its old milestones.
                _s = sent_milestones.setdefault(_ck, set())
                for _m in _ms_list:
                    if _m <= 100 and _m not in _s:
                        _s.add(int(_m))
                        _n += 1
                continue
            _bx = _peak / _entry'''

# --- E2: bulk lane max checks 110 -> 60 (priority stays 130) ---
OLD2 = '''            "130" if prio_mode else "110") or (130 if prio_mode else 110)))'''

NEW2 = '''            "130" if prio_mode else "60") or (130 if prio_mode else 60)))  # PERM_NOV23: bulk 110->60 so the lane never wedges and dropped calls stay at 2s'''


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
    for _tag, _old in (("E1", OLD1), ("E2", OLD2)):
        if src.count(_old) != 1:
            print("FAIL: %s anchor missing/dup in %s (found %dx) -- NOT writing "
                  "anything." % (_tag, path, src.count(_old)))
            return False
    shutil.copy2(path, path + ".bak_perm_nov23")
    src = src.replace(OLD1, NEW1, 1)
    src = src.replace(OLD2, NEW2, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("E1 OK (startup seal now covers corrupted calls too)")
    print("E2 OK (bulk lane 110 -> 60 checks per tick)")
    print("DONE. Backup: %s.bak_perm_nov23" % path)
    print("Now restart the wizu bot (systemctl restart bot.service).")
    return True


if __name__ == "__main__":
    ok = patch_file(sys.argv[1] if len(sys.argv) > 1 else "x_alert.py")
    sys.exit(0 if ok else 1)
