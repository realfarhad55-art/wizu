"""apply_final_nov23.py - FINAL fix so old posts NEVER come back (user order).

Three guards, one patch. After this, an old X alert cannot post again
through ANY path:

E1 - STALE HELD ALERTS (the $ROCCO 14X post 121311: entry 11.2K, now
1.17M = ~104X, but bot posted the 14X alert). pending_media_job posted a
held milestone with NO freshness check. Fix: before posting a held
milestone, compute current X = peak/entry. If current X >= held level * 2,
the alert is stale: DISCARD it (remove from pending, log, do NOT post).
Fresh alerts (token still near the level) post as before.

E2 - DIP ALERTS LOST (dip never reached the channel). _dip_check_tick
marked a dip milestone as SENT *before* calling send_dip_alert. If the
send failed, the milestone was already in `sent` (never re-fired) AND a
dip cycle reset cleared its pending_dip entry — the alert was lost
forever. Fix: on send failure, UNMARK the milestone from `sent` (and
save), so it retries next tick instead of being lost.

E3 - STARTUP SEAL (the permanent guard). On the first monitoring tick
after a (re)start, seal every milestone <= each call's best_x
(peak/entry) into sent_milestones and save. So even if
sent_milestones.json goes stale or corrupt, a restart can NEVER re-fire
an old milestone. Runs ONCE per process. New milestones (above best_x)
are unaffected and fire normally.

Idempotent. Backs up x_alert.py to x_alert.py.bak_final_nov23.
Run: python3 apply_final_nov23.py x_alert.py
Then: systemctl restart bot.service
"""

import sys, shutil

MARKER = "FINAL_NOV23"

# --- E1: staleness guard in pending_media_job (same as FIX2) ---
OLD1 = '''            _pk_mc = float(call.get("peak_mc", 0) or 0)
            cur_fmt = fmt_mc(_pk_mc) if _pk_mc > 0 else (fmt_mc(entry_mc * top) if entry_mc > 0 else f"{top}X")
            try:
                posted = await send_alert('''

NEW1 = '''            _pk_mc = float(call.get("peak_mc", 0) or 0)
            cur_fmt = fmt_mc(_pk_mc) if _pk_mc > 0 else (fmt_mc(entry_mc * top) if entry_mc > 0 else f"{top}X")
            # FINAL_NOV23: discard stale held alerts. If the token already
            # ran far past the held level (14X held, token now 100X+),
            # posting the old level misleads the channel. Drop it.
            try:
                _cx = (float(_pk_mc) / float(entry_mc)) if _pk_mc > 0 and entry_mc > 0 else 0.0
            except (TypeError, ValueError, ZeroDivisionError):
                _cx = 0.0
            if _cx > 0 and _cx >= top * 2:
                _rest = {x for x in levels if x not in ready}
                if _rest:
                    pending_media_alerts[call_key] = _rest
                else:
                    pending_media_alerts.pop(call_key, None)
                changed = True
                logger.info(f"FINAL_NOV23: stale held alert skipped: {top}X {call_key} (now {_cx:.1f}x)")
                await asyncio.sleep(0.3)
                continue
            try:
                posted = await send_alert('''

# --- E2: dip retry — unmark on failed send (same as FIX2) ---
OLD2 = '''        ok = await send_dip_alert(bot, call_key, call, ms, cur_mc)
        if ok:
            logger.info(f"Dip alert posted: {ms}X {call_key} "
                        f"(dip {dip_ratio:.1f}x from {fmt_mc(dip_low)})")
        else:
            logger.info(f"Dip alert held: {ms}X {call_key} "
                        f"(no media or send failed, will retry)")'''

NEW2 = '''        ok = await send_dip_alert(bot, call_key, call, ms, cur_mc)
        if ok:
            logger.info(f"Dip alert posted: {ms}X {call_key} "
                        f"(dip {dip_ratio:.1f}x from {fmt_mc(dip_low)})")
        else:
            # FINAL_NOV23: send failed — unmark so it retries next tick.
            # (It was marked sent before the call, so a failure lost the
            # alert forever: _dip_check_tick never re-fired it and a cycle
            # reset cleared its pending entry.)
            try:
                sent.remove(int(ms))
            except ValueError:
                pass
            _save_tracked()
            logger.info(f"Dip alert held: {ms}X {call_key} "
                        f"(no media or send failed, will retry)")'''

# --- E3: startup seal, called on first monitoring tick ---
OLD3 = '''async def _monitoring_job_body(context: ContextTypes.DEFAULT_TYPE, prio_mode: bool):
    # MONSPLIT_NOV23: bulk (non-priority) lane runs every 5th tick (10s)'''

NEW3 = '''# FINAL_NOV23: seal every milestone <= each call's best_x once per
# process, on the first monitoring tick. A restart can never re-fire an
# old milestone even if sent_milestones.json went stale or corrupt.
_FINAL_SEALED = False


def _seal_past_milestones_once():
    global _FINAL_SEALED
    if _FINAL_SEALED:
        return
    _FINAL_SEALED = True
    try:
        _ms_list = get_milestones()
    except Exception:
        return
    _n = 0
    try:
        for _ck, _call in list(tracked_calls.items()):
            try:
                _entry = float(_call.get("entry_mc", 0) or 0)
                _peak = float(_call.get("peak_mc", 0) or 0)
            except (TypeError, ValueError):
                continue
            if _entry <= 0 or _peak <= 0:
                continue
            _bx = _peak / _entry
            if _bx < 2:
                continue
            _s = sent_milestones.setdefault(_ck, set())
            for _m in _ms_list:
                if _m <= _bx and _m not in _s:
                    _s.add(int(_m))
                    _n += 1
        if _n:
            _save_milestones()
            logger.info(f"FINAL_NOV23: startup seal: sealed {_n} past milestones")
    except Exception as e:
        logger.error(f"FINAL_NOV23: startup seal failed: {e}")


async def _monitoring_job_body(context: ContextTypes.DEFAULT_TYPE, prio_mode: bool):
    _seal_past_milestones_once()
    # MONSPLIT_NOV23: bulk (non-priority) lane runs every 5th tick (10s)'''


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
    for _tag, _old in (("E1", OLD1), ("E2", OLD2), ("E3", OLD3)):
        if src.count(_old) != 1:
            print("FAIL: %s anchor missing/dup in %s (found %dx) -- NOT writing "
                  "anything." % (_tag, path, src.count(_old)))
            return False
    shutil.copy2(path, path + ".bak_final_nov23")
    src = src.replace(OLD1, NEW1, 1)
    src = src.replace(OLD2, NEW2, 1)
    src = src.replace(OLD3, NEW3, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("E1 OK (stale held X alerts discarded)")
    print("E2 OK (failed dip alerts retry instead of being lost)")
    print("E3 OK (startup seal: old milestones can never re-fire)")
    print("DONE. Backup: %s.bak_final_nov23" % path)
    print("Now restart the wizu bot (systemctl restart bot.service).")
    return True


if __name__ == "__main__":
    ok = patch_file(sys.argv[1] if len(sys.argv) > 1 else "x_alert.py")
    sys.exit(0 if ok else 1)
