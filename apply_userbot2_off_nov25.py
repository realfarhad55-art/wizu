"""apply_userbot2_off_nov25.py - Disable userbot 2 (@Wizard_Scan) in the main bot.

PROBLEM: The main bot and the dropbot share the SAME @Wizard_Scan userbot
session (main bot: /opt/bot/data/userbot_session2.txt, dropbot: a copy of
the same file at /opt/dropbot/wizard_scan.session). Telegram allows only
ONE active connection per session, so when the main bot (re)connects
userbot 2 it kicks the dropbot off, and vice versa. This caused:
- dropbot userbot disconnect 18:22 CET Nov 24 (posts 157/158 missed)
- main-bot userbot disconnect 19:18 CET Nov 24 (dip posts 122681/122695
  went out non-premium via Bot API fallback)
- dropbot silent again after the main bot restarted 21:35 CET Nov 24
  for MONBOT_MODE (posts 160/161 missed)
Restarting the dropbot fixes it for a while, but the next main-bot
restart breaks it again.

FIX: Gate userbot 2 OFF behind an env flag DISABLE_USERBOT2=1. With the
flag set, the main bot never connects @Wizard_Scan at all, so the dropbot
owns that session exclusively and the two bots stop disconnecting each
other. The session FILE is NOT deleted and the userbot-2 code is NOT
removed, so this is fully reversible.

WHY THIS IS SAFE NOW: DROPBOT_MODE=1 is live, so the main bot no longer
does realtime monitoring (the dropbot does it). The main bot only needs
a userbot for posting X alerts / dip alerts / etc. and occasional channel
fetches, and @yowziuh alone handled all posting before userbot 2 was
added on Nov 5. Everything that used userbot 2 is already None-safe:
- _userbot_clients() only returns clients that are not None and connected
- _pick_userbot() round-robins over that list (modulo, so 1 client is fine)
- the fetch fallback checks `userbot_client2 is not None` before use
- userbot_watchdog_job only watches the primary and calls init_userbot()

Three edits, two files (run from /opt/bot):

E1 - core.py, init_userbot(): skip the 2nd-userbot block when the flag is
     set. This block is the tail of init_userbot(), so returning here only
     skips the 2nd account; the primary @yowziuh init above is untouched.
     This also covers the watchdog and _kick_userbot_reconnect paths, which
     both re-enter through init_userbot().
E2 - core.py, _start_second_userbot(): early return when the flag is set,
     so the 2nd account is never connected and its NewMessage handler and
     channel-join loop never start.
E3 - runtime.py: do not even spawn the _start_second_userbot task when the
     flag is set (belt and braces; E2 alone would already return at once).

Plus add DISABLE_USERBOT2=1 to /opt/bot/.env, then restart the main bot.
Rollback: remove DISABLE_USERBOT2=1 from .env + restart main bot. The
dropbot is NOT touched by this patch.

Idempotent. Backs up core.py to core.py.bak_userbot2off_nov25
and runtime.py to runtime.py.bak_userbot2off_nov25.
Run: python3 apply_userbot2_off_nov25.py [/opt/bot]
Then: echo DISABLE_USERBOT2=1 >> /opt/bot/.env && systemctl restart bot.service

WARNING: live /opt/bot/core.py and runtime.py have post-Nov-23 patches
(MONBOT_MODE, DROPBOT_MODE, GUARD, FINAL, PERM, DIPFIX, DIP_BOLD, etc.)
that are NOT in the Nov 23 base copies this patch was written against.
If any anchor below FAILS on the live files, do NOT force it - report back
instead. Anchors were verified count==1 against the Nov 23 base copies
(core-fadf8802.py, runtime-c97fc7f1.py).
"""

import os, sys, shutil

MARKER = "USERBOT2_OFF_NOV25"

# --- E1: skip the 2nd-userbot block inside init_userbot() ---
OLD1 = '''    if userbot_client2 and userbot_client2.is_connected():
        return
    session2 = load_userbot_session2() or os.environ.get("SESSION_STRING_2", "").strip()'''

NEW1 = '''    # USERBOT2_OFF_NOV25: skip userbot 2 entirely when disabled, so the
    # dropbot owns the @Wizard_Scan session alone (one session, one
    # connection). init_userbot() ends right after this block, so returning
    # here only skips the 2nd account; the primary @yowziuh init above is
    # untouched. This also covers the watchdog and _kick_userbot_reconnect
    # paths, which both re-enter through init_userbot().
    if os.environ.get("DISABLE_USERBOT2", "").strip() == "1":
        logger.info("Userbot2 OFF (DISABLE_USERBOT2=1) - @Wizard_Scan left to dropbot.")
        return
    if userbot_client2 and userbot_client2.is_connected():
        return
    session2 = load_userbot_session2() or os.environ.get("SESSION_STRING_2", "").strip()'''

# --- E2: early return in _start_second_userbot() ---
OLD2 = '''    global userbot_client2
    try:
        api_id = int(os.environ.get("USERBOT_API_ID_2", "") or 0) or OWNER_API_ID'''

NEW2 = '''    global userbot_client2
    # USERBOT2_OFF_NOV25: skip userbot 2 entirely when disabled, so the
    # dropbot owns the @Wizard_Scan session alone (one session, one
    # connection). No connect, no NewMessage handler, no channel-join loop.
    if os.environ.get("DISABLE_USERBOT2", "").strip() == "1":
        logger.info("2nd userbot OFF (DISABLE_USERBOT2=1) - @Wizard_Scan left to dropbot.")
        return
    try:
        api_id = int(os.environ.get("USERBOT_API_ID_2", "") or 0) or OWNER_API_ID'''

# --- E3: do not spawn the _start_second_userbot task in runtime.py ---
OLD3 = '''        asyncio.create_task(_prewarm_media_cache(app_ref.bot))
        asyncio.create_task(_start_second_userbot(app_ref.bot))'''

NEW3 = '''        asyncio.create_task(_prewarm_media_cache(app_ref.bot))
        # USERBOT2_OFF_NOV25: do not start userbot 2 when disabled (dropbot owns it).
        import os as _os_ub2off
        if _os_ub2off.environ.get("DISABLE_USERBOT2", "").strip() != "1":
            asyncio.create_task(_start_second_userbot(app_ref.bot))'''


def patch_one(path, old, new, tag):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if src.count(old) != 1:
        print("FAIL: %s anchor missing/dup in %s (found %dx) -- NOT writing "
              "anything." % (tag, path, src.count(old)))
        return False
    bak = path + ".bak_userbot2off_nov25"
    if not os.path.exists(bak):
        # First edit only: keep a PRISTINE pre-patch backup (later edits
        # must not overwrite it, or rollback would restore a half-patched file).
        shutil.copy2(path, bak)
    src = src.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    co = os.path.join(d, "core.py")
    rt = os.path.join(d, "runtime.py")
    for p in (co, rt):
        if not os.path.exists(p):
            print("FAIL: %s not found" % p)
            return 1
    with open(co, encoding="utf-8") as f:
        cosrc = f.read()
    with open(rt, encoding="utf-8") as f:
        rtsrc = f.read()
    if MARKER in cosrc and MARKER in rtsrc:
        print("OK: already has USERBOT2_OFF_NOV25, skipping.")
        return 0
    if MARKER in cosrc or MARKER in rtsrc:
        print("FAIL: partial state (marker in one file only) -- inspect "
              "core.py / runtime.py before re-running.")
        return 1
    if not patch_one(co, OLD1, NEW1, "E1"):
        return 1
    print("E1 OK (init_userbot skips userbot 2 when DISABLE_USERBOT2=1)")
    if not patch_one(co, OLD2, NEW2, "E2"):
        return 1
    print("E2 OK (_start_second_userbot returns early when DISABLE_USERBOT2=1)")
    if not patch_one(rt, OLD3, NEW3, "E3"):
        return 1
    print("E3 OK (_start_second_userbot task not spawned when DISABLE_USERBOT2=1)")
    print("DONE. Backups: core.py.bak_userbot2off_nov25, runtime.py.bak_userbot2off_nov25")
    print("Next: echo DISABLE_USERBOT2=1 >> /opt/bot/.env && systemctl restart bot.service")
    print("Note: restart the dropbot once too, so it takes the @Wizard_Scan session cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
