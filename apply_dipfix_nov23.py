"""apply_dipfix_nov23.py - fix dip MC line + old X alert re-post (user order).

Three edits, all in x_alert.py:

E1 - DIP MC LINE (post 121334). build_dip_caption showed ENTRY first,
current second: "57.6K teer 12.9K". The story must be: token dipped to
the low, then pumped from the low. Fix: show DIP LOW first, current
second: "12.9K teer 57.6K".

E2 - DIP HELD ALERT STALE MC. pending_dip_media_job released held dip
alerts with the STALE mc stored in dip_pending_mc (the value from when
the alert was held, e.g. 12.9K at the low). Fix: fetch the LIVE MC
before releasing (best-effort, 4s timeout); fall back to dip_low x top
(the milestone MC) if the fetch fails. The stale stored value is never
used again.

E3 - OLD X ALERT RE-POST (post 121333, $DCTY 2X). pending_media_job
posted a held level even when that milestone was already sealed in
sent_milestones (already posted). Fix: drop any ready level that is
already in sent_milestones for that call before posting. A held entry
for an already-posted milestone must never post again.

Idempotent. Backs up x_alert.py to x_alert.py.bak_dipfix_nov23.
Run: python3 apply_dipfix_nov23.py x_alert.py
Then: systemctl restart bot.service
"""

import sys, shutil

MARKER = "DIPFIX_NOV23"

# --- E1: dip MC line shows dip low first, current second ---
OLD1 = '''    entry_fmt = _mc_no_label(fmt_mc(entry_mc)) if entry_mc > 0 else "N/A"
    cur_fmt = _mc_no_label(fmt_mc(cur_mc)) if cur_mc > 0 else "N/A"'''

NEW1 = '''    entry_fmt = _mc_no_label(fmt_mc(entry_mc)) if entry_mc > 0 else "N/A"
    low_fmt = _mc_no_label(fmt_mc(dip_low)) if dip_low > 0 else "N/A"  # DIPFIX_NOV23: MC line shows the dip low first
    cur_fmt = _mc_no_label(fmt_mc(cur_mc)) if cur_mc > 0 else "N/A"'''

OLD1B = '''        f"{crystal_e} {entry_fmt}  {teer_e}  {cur_fmt}",'''

NEW1B = '''        f"{crystal_e} {low_fmt}  {teer_e}  {cur_fmt}",'''

# --- E2: pending dip job fetches live MC, never uses stale stored value ---
OLD2 = '''            top = max(ready)
            mc_map = call.get("dip_pending_mc") or {}
            try:
                mc = float(mc_map.get(str(top)) or 0)
            except (TypeError, ValueError):
                mc = 0.0
            if mc <= 0:
                try:
                    dip_low = float(call.get("dip_low") or 0)
                except (TypeError, ValueError):
                    dip_low = 0.0
                mc = dip_low * top if dip_low > 0 else 0.0'''

NEW2 = '''            top = max(ready)
            # DIPFIX_NOV23: never use the stale dip_pending_mc (value from
            # when the alert was held). Fetch the live MC so the released
            # alert shows the current price; fall back to dip_low x top.
            mc = 0.0
            try:
                _dex = await asyncio.wait_for(
                    fetch_dexscreener(call.get("ca", ""), allow_alt=False, retries=1, min_liquidity=0),
                    timeout=4)
                mc = float((_dex or {}).get("mcap") or 0)
            except Exception:
                mc = 0.0
            if mc <= 0:
                try:
                    dip_low = float(call.get("dip_low") or 0)
                except (TypeError, ValueError):
                    dip_low = 0.0
                mc = dip_low * top if dip_low > 0 else 0.0'''

# --- E3: held X alert already sealed (posted) must never post again ---
OLD3 = '''            ready = [x for x in levels if milestone_has_media(x)]
            if not ready:
                continue
            top = max(ready)'''

NEW3 = '''            ready = [x for x in levels if milestone_has_media(x)]
            # DIPFIX_NOV23: drop levels already sealed (posted) in
            # sent_milestones — a held entry for an already-posted
            # milestone must never post again (old $DCTY 2X alert).
            try:
                _sealed = sent_milestones.get(call_key, set()) or set()
            except Exception:
                _sealed = set()
            if _sealed:
                _dup = [x for x in ready if x in _sealed]
                if _dup:
                    _keep = {x for x in levels if x not in _sealed}
                    if _keep:
                        pending_media_alerts[call_key] = _keep
                    else:
                        pending_media_alerts.pop(call_key, None)
                    changed = True
                    logger.info(f"DIPFIX_NOV23: held alert already posted, dropped: {_dup} {call_key}")
                    ready = [x for x in ready if x not in _sealed]
            if not ready:
                continue
            top = max(ready)'''


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
    for _tag, _old in (("E1", OLD1), ("E1b", OLD1B), ("E2", OLD2), ("E3", OLD3)):
        if src.count(_old) != 1:
            print("FAIL: %s anchor missing/dup in %s (found %dx) -- NOT writing "
                  "anything." % (_tag, path, src.count(_old)))
            return False
    shutil.copy2(path, path + ".bak_dipfix_nov23")
    src = src.replace(OLD1, NEW1, 1)
    src = src.replace(OLD1B, NEW1B, 1)
    src = src.replace(OLD2, NEW2, 1)
    src = src.replace(OLD3, NEW3, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("E1 OK (dip MC line: low first, current second)")
    print("E2 OK (held dip alert uses live MC, not stale stored value)")
    print("E3 OK (held X alert already posted is dropped, never re-posts)")
    print("DONE. Backup: %s.bak_dipfix_nov23" % path)
    print("Now restart the wizu bot (systemctl restart bot.service).")
    return True


if __name__ == "__main__":
    ok = patch_file(sys.argv[1] if len(sys.argv) > 1 else "x_alert.py")
    sys.exit(0 if ok else 1)
