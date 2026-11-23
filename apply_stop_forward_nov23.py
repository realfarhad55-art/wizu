#!/usr/bin/env python3
"""Stop DM alerts + channel forwards (Nov 23 2026).

Owner order: stop ALL DM alerts and channel forwarding first, then
move forward. The old X alerts are spamming DMs and KOL channels.

What this does (x_alert.py only): _forward_alert_recipients is the
single function that sends an X alert to EVERYONE except the main
@WizardScan post — KOL owner DM, channel subscribers DM, linked
channels, and the KOL's own channel. This patch makes it return
immediately, so nothing is forwarded or DM'd.

What keeps working: the main @WizardScan post itself still goes out
normally (it is sent before the forward step). Only the DM alerts
and the channel forwards are paused.

How to re-enable later: remove the one `return` line this patch
adds (marker STOP_FORWARD_NOV23), then restart the bot.

Requires: live /opt/bot/x_alert.py. Run once from /opt/bot:
    python3 apply_stop_forward_nov23.py x_alert.py
VPS-only one-time script. Idempotent (marker STOP_FORWARD_NOV23).
Backup: x_alert.py.bak_stopforward_nov23.
Fail-safe: validates the anchor before writing; aborts without
touching any file on mismatch.
"""

import sys, shutil

MARKER = "STOP_FORWARD_NOV23"

OLD = """async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    \"\"\"Forward the already-published WizardScan post without rebuilding it."""
NEW = """async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    return  # STOP_FORWARD_NOV23: DM alerts + channel forwards paused by owner
    \"\"\"Forward the already-published WizardScan post without rebuilding it."""


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
              "anything. Send the live file so the patch can be rebuilt."
              % (path, src.count(OLD)))
        return False
    shutil.copy(path, path + ".bak_stopforward_nov23")
    print("Backup: %s.bak_stopforward_nov23" % path)
    src = src.replace(OLD, NEW, 1)
    print("OK: _forward_alert_recipients now returns immediately (%s)" % path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    args = sys.argv[1:]
    if not args:
        args = ["x_alert.py"]
    ok = True
    for path in args:
        if not path.endswith("x_alert.py"):
            print("FAIL: unknown file %s (expected x_alert.py)" % path)
            ok = False
            continue
        if not patch_file(path):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("DM alerts + channel forwards are now OFF. Main @WizardScan posts still go out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
