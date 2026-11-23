"""apply_guard_nov23.py - FINAL guard: an X alert posts ONLY when the
token is AT or ABOVE that level right now (user order).

Problem: old X alerts kept posting for tokens that pumped days ago and
have since DROPPED below the level (e.g. $DCTY 2X while the token sits
at 1.2x). The earlier guards only caught tokens that ran FAR PAST the
level (peak >= level x 2). A token that pumped to the level and then
dropped back below it slipped through.

Two edits, both in x_alert.py:

E1 - HELD X ALERTS (pending_media_job). Before posting a held level,
fetch the LIVE current MC. If live_ratio (live/entry) < top, the token
has dropped below the level — DISCARD the held level(s) above the live
ratio, do NOT post. If the live fetch fails, fall back to the existing
guards (never block on a fetch failure).

E2 - ATH BACKFILL (ath_backfill_job). The backfill fires milestones from
the PEAK (candle ATH), even when the token's live price has dropped
below the level. Fix: only fire a level if the latest live ratio
(last_ratio) is at/above it — or if there is no live data at all
(last_ratio <= 0, let the seal handle it).

Idempotent. Backs up x_alert.py to x_alert.py.bak_guard_nov23.
Run: python3 apply_guard_nov23.py x_alert.py
Then: systemctl restart bot.service
"""

import sys, shutil

MARKER = "GUARD_NOV23"

# --- E1: held X alert only posts if token is at/above the level now ---
OLD1 = '''                logger.info(f"FINAL_NOV23: stale held alert skipped: {top}X {call_key} (now {_cx:.1f}x)")
                await asyncio.sleep(0.3)
                continue
            try:
                posted = await send_alert('''

NEW1 = '''                logger.info(f"FINAL_NOV23: stale held alert skipped: {top}X {call_key} (now {_cx:.1f}x)")
                await asyncio.sleep(0.3)
                continue
            # GUARD_NOV23: an X alert posts ONLY if the token is AT or
            # ABOVE the level right now. If it pumped days ago and has
            # since dropped below the level, the held alert is stale.
            try:
                _g_dex = await asyncio.wait_for(
                    fetch_dexscreener(call.get("ca", ""), allow_alt=False, retries=1, min_liquidity=0),
                    timeout=4)
                _g_live = float((_g_dex or {}).get("mcap") or 0)
            except Exception:
                _g_live = 0.0
            if _g_live > 0 and entry_mc > 0:
                try:
                    _g_ratio = _g_live / float(entry_mc)
                except (TypeError, ValueError, ZeroDivisionError):
                    _g_ratio = 0.0
                if _g_ratio > 0 and _g_ratio < top:
                    _keep = {x for x in levels if x <= _g_ratio}
                    if _keep:
                        pending_media_alerts[call_key] = _keep
                    else:
                        pending_media_alerts.pop(call_key, None)
                    changed = True
                    logger.info(f"GUARD_NOV23: held {top}X dropped, token below level (live {_g_ratio:.2f}x) {call_key}")
                    await asyncio.sleep(0.3)
                    continue
            try:
                posted = await send_alert('''

# --- E2: backfill only fires a level the live price is at/above ---
OLD2 = '''                new_ms = [ms for ms in get_milestones()
                          if ms <= MAX_MILESTONE and ratio >= ms
                          and ms not in sent_milestones[call_key]]'''

NEW2 = '''                # GUARD_NOV23: only fire a level the LIVE price is
                # at/above. A peak from days ago must not post when the
                # token has dropped below the level since.
                _lr = float(call.get("last_ratio", 0) or 0)
                new_ms = [ms for ms in get_milestones()
                          if ms <= MAX_MILESTONE and ratio >= ms
                          and ms not in sent_milestones[call_key]
                          and (_lr <= 0 or _lr >= ms)]'''


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
    shutil.copy2(path, path + ".bak_guard_nov23")
    src = src.replace(OLD1, NEW1, 1)
    src = src.replace(OLD2, NEW2, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("E1 OK (held X alert only posts if token is at/above the level)")
    print("E2 OK (backfill only fires levels the live price is at/above)")
    print("DONE. Backup: %s.bak_guard_nov23" % path)
    print("Now restart the wizu bot (systemctl restart bot.service).")
    return True


if __name__ == "__main__":
    ok = patch_file(sys.argv[1] if len(sys.argv) > 1 else "x_alert.py")
    sys.exit(0 if ok else 1)
