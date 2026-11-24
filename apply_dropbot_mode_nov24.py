"""apply_dropbot_mode_nov24.py - Main bot changes for the separate dropbot.

REQUIRED before starting dropbot.service, otherwise duplicate dropped
calls post (main bot + dropbot both) and X alerts stop for dropbot calls.

Three edits, two files (run from /opt/bot):

E1 - dropped_call.py, _process_new_call: if DROPBOT_MODE=1, return False
     right after the launchpad block (before the call detector), so the
     main bot stops posting dropped calls but presale (launchpad) alerts
     keep working.
E2 - dropped_call.py: add dropbot_import_job (reads dropbot's own
     /opt/dropbot/data/dropbot_calls.json, imports entry_locked calls
     into tracked_calls so X alerts / leaderboard / dip keep working).
E3 - runtime.py: register dropbot_import_job (every 10s, first run 20s).

Plus add DROPBOT_MODE=1 to /opt/bot/.env, then restart the main bot.
Rollback: remove DROPBOT_MODE=1 from .env + restart main bot, and
systemctl stop dropbot.service. Never run both dropped-call posters.

Idempotent. Backs up dropped_call.py to dropped_call.py.bak_dropbotmode_nov24
and runtime.py to runtime.py.bak_dropbotmode_nov24.
Run: python3 apply_dropbot_mode_nov24.py [/opt/bot]
Then: echo DROPBOT_MODE=1 >> /opt/bot/.env && systemctl restart bot.service
"""

import os, sys, shutil

MARKER = "DROPBOT_MODE_NOV24"

# --- E1: stop main bot posting dropped calls (launchpad block already ran) ---
OLD1 = '''        # A caller message is accepted when the normal call detector matches OR
        # when a real token CA is present. This keeps tracking alive if a caller
        # changes wording/emoji style while still requiring an actual CA/link.
        result = extract_ca(text) if text else None'''

NEW1 = '''        # DROPBOT_MODE_NOV24: dropped calls are handled by the separate
        # dropbot. This bot only imports them (dropbot_import_job). Launchpad
        # detection above still runs, so presale alerts keep working.
        if os.environ.get("DROPBOT_MODE") == "1":
            return False

        # A caller message is accepted when the normal call detector matches OR
        # when a real token CA is present. This keeps tracking alive if a caller
        # changes wording/emoji style while still requiring an actual CA/link.
        result = extract_ca(text) if text else None'''

# --- E2: import job function (inserted before setup_realtime_monitoring) ---
OLD2 = '''async def setup_realtime_monitoring(bot):'''

NEW2 = '''# DROPBOT_IMPORT_NOV24: dropbot ki posted calls ko import karo.
# Dropbot apna record /opt/dropbot/data/dropbot_calls.json me likhta hai.
# Yeh job use READ karke main bot ke tracked_calls me daalta hai, taake
# X alerts / leaderboard / dip pehle ki tarah chalte rahen.
# Sirf entry_locked calls import hoti hain (dropbot ne entry confirm karke
# alert post kar di hai). Entry revise hone par (48s confirm task) main bot
# ki entry bhi upar update hoti hai.
DROPBOT_CALLS_FILE = "/opt/dropbot/data/dropbot_calls.json"


async def dropbot_import_job(context):
    try:
        with open(DROPBOT_CALLS_FILE, encoding="utf-8") as f:
            incoming = json.load(f) or {}
    except FileNotFoundError:
        return  # dropbot abhi start nahi hua
    except Exception as e:
        logger.warning(f"dropbot_import: read failed: {e}")
        return
    added = 0
    updated = 0
    for call_key, c in incoming.items():
        try:
            if call_key in tracked_calls:
                # Entry revise hui ho to main bot ki entry bhi upar karo
                # (sirf live-src entries, aur sirf meaningful jump par).
                _old = tracked_calls[call_key]
                _new_mc = float(c.get("entry_mc", 0) or 0)
                _old_mc = float(_old.get("entry_mc", 0) or 0)
                if (_new_mc > 0 and _old_mc > 0 and _new_mc > _old_mc * 1.08
                        and _old.get("entry_src") in ("live", "live_fdv", "post_unconfirmed")):
                    _old["entry_mc"] = _new_mc
                    _old["entry_fmt"] = c.get("entry_fmt", _old.get("entry_fmt", "N/A"))
                    _old["entry_price"] = float(c.get("entry_price", 0) or _old.get("entry_price", 0))
                    updated += 1
                continue
            if not c.get("entry_locked"):
                continue  # entry abhi confirm nahi — agle tick par aayegi
            tracked_calls[call_key] = {
                "channel": c.get("channel", ""),
                "msg_id": str(c.get("msg_id", "")),
                "ca": c.get("ca", ""),
                "chain": c.get("chain", "SOL"),
                "entry_mc": float(c.get("entry_mc", 0) or 0),
                "entry_price": float(c.get("entry_price", 0) or 0),
                "entry_fmt": c.get("entry_fmt", "N/A"),
                "entry_locked": True,
                "entry_src": c.get("entry_src", "live"),
                "entry_confirmed": bool(c.get("entry_confirmed", False)),
                "post_mc_hint": float(c.get("post_mc_hint", 0) or 0),
                "symbol": c.get("symbol", ""),
                "tracked_since": c.get("tracked_since", datetime.utcnow().isoformat()),
                "dex_pending": bool(c.get("dex_pending", False)),
                "series": c.get("series", [1.0]),
                "drop_post_id": c.get("drop_post_id"),
                "drop_post_media": bool(c.get("drop_post_media", False)),
            }
            try:
                _hs_register_call(c.get("channel", ""), call_key, c.get("chain", "SOL"))
            except Exception:
                pass
            try:
                # Wahi deterministic sid jo dropbot ne Details link me diya tha
                _register_drop_details(c.get("channel", ""), c.get("ca", ""))
            except Exception:
                pass
            added += 1
        except Exception as e:
            logger.warning(f"dropbot_import: skip {call_key}: {e}")
            continue
    if added or updated:
        _save_tracked()
        logger.info(f"dropbot_import: {added} new, {updated} entry-updated")


async def setup_realtime_monitoring(bot):'''

# --- E3: register the import job in runtime.py (after userbot_watchdog_job) ---
OLD3 = '''    app.job_queue.run_repeating(userbot_watchdog_job, interval=45,        first=45)   # har 45s: userbot alive check + auto-reconnect (backstop for the immediate _kick_userbot_reconnect)'''

NEW3 = '''    app.job_queue.run_repeating(userbot_watchdog_job, interval=45,        first=45)   # har 45s: userbot alive check + auto-reconnect (backstop for the immediate _kick_userbot_reconnect)
    app.job_queue.run_repeating(dropbot_import_job, interval=10, first=20)  # DROPBOT_MODE_NOV24: dropbot ki calls import karo (X alerts ke liye)'''


def patch_one(path, old, new, tag):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if src.count(old) != 1:
        print("FAIL: %s anchor missing/dup in %s (found %dx) -- NOT writing "
              "anything." % (tag, path, src.count(old)))
        return False
    shutil.copy2(path, path + ".bak_dropbotmode_nov24")
    src = src.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    dc = os.path.join(d, "dropped_call.py")
    rt = os.path.join(d, "runtime.py")
    for p in (dc, rt):
        if not os.path.exists(p):
            print("FAIL: %s not found" % p)
            return 1
    with open(dc, encoding="utf-8") as f:
        dcsrc = f.read()
    with open(rt, encoding="utf-8") as f:
        rtsrc = f.read()
    if MARKER in dcsrc and "dropbot_import_job" in dcsrc and MARKER in rtsrc:
        print("OK: already has DROPBOT_MODE_NOV24, skipping.")
        return 0
    if MARKER in dcsrc or "dropbot_import_job" in dcsrc or MARKER in rtsrc:
        print("FAIL: partial state (marker in one file only) — inspect "
              "dropped_call.py / runtime.py before re-running.")
        return 1
    if not patch_one(dc, OLD1, NEW1, "E1"):
        return 1
    print("E1 OK (main bot dropped-call posting OFF when DROPBOT_MODE=1)")
    if not patch_one(dc, OLD2, NEW2, "E2"):
        return 1
    print("E2 OK (dropbot_import_job added to dropped_call.py)")
    if not patch_one(rt, OLD3, NEW3, "E3"):
        return 1
    print("E3 OK (dropbot_import_job registered in runtime.py, every 10s)")
    print("DONE. Backups: dropped_call.py.bak_dropbotmode_nov24, runtime.py.bak_dropbotmode_nov24")
    print("Next: echo DROPBOT_MODE=1 >> /opt/bot/.env && systemctl restart bot.service")
    print("Then: systemctl start dropbot.service")
    return 0


if __name__ == "__main__":
    sys.exit(main())
