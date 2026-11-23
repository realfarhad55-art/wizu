"""apply_stop_forward2_nov23.py - Stop X-alert DMs + channel forwards (v2).

Rebuilt for the LIVE x_alert.py, whose _forward_alert_recipients has a
FORWARD_ON_NOV23 comment line between the def and the docstring (that is
why the v1 stop-forward patch failed with "anchor missing, found 0x").

Effect: _forward_alert_recipients returns immediately, so no DM alerts and
no channel forwards go out. Main @WizardScan posts are NOT affected.

Idempotent. Backs up x_alert.py to x_alert.py.bak_stopforward2_nov23.
Run: python3 apply_stop_forward2_nov23.py x_alert.py
Then: systemctl restart bot.service
"""

import sys, shutil

MARKER = "STOP_FORWARD_NOV23"

# Live state (after FORWARD_ON_NOV23): def + FORWARD_ON comment + docstring.
OLD = '''async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    # FORWARD_ON_NOV23: DM alerts + channel forwards re-enabled by owner
    """Forward the already-published WizardScan post without rebuilding it.'''

NEW = '''async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    return  # STOP_FORWARD_NOV23: DM alerts + channel forwards paused by owner
    """Forward the already-published WizardScan post without rebuilding it.'''

# Fallback: plain def + docstring (no FORWARD_ON comment), for other copies.
OLD2 = '''async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    """Forward the already-published WizardScan post without rebuilding it.'''

NEW2 = '''async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    return  # STOP_FORWARD_NOV23: DM alerts + channel forwards paused by owner
    """Forward the already-published WizardScan post without rebuilding it.'''


def patch_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print("FAIL: %s not found" % path)
        return False
    if "return  # STOP_FORWARD_NOV23" in src:
        print("OK: %s already has STOP_FORWARD_NOV23, skipping." % path)
        return True
    if src.count(OLD) == 1:
        shutil.copy2(path, path + ".bak_stopforward2_nov23")
        src = src.replace(OLD, NEW, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print("E1 OK (forward stopped, FORWARD_ON comment removed)")
        print("DONE. Backup: %s.bak_stopforward2_nov23" % path)
        print("Now restart the wizu bot (systemctl restart bot.service).")
        return True
    if src.count(OLD2) == 1:
        shutil.copy2(path, path + ".bak_stopforward2_nov23")
        src = src.replace(OLD2, NEW2, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print("E1 OK (forward stopped, plain def)")
        print("DONE. Backup: %s.bak_stopforward2_nov23" % path)
        print("Now restart the wizu bot (systemctl restart bot.service).")
        return True
    print("FAIL: anchor missing/dup in %s (OLD %dx, OLD2 %dx) -- NOT writing "
          "anything." % (path, src.count(OLD), src.count(OLD2)))
    return False


if __name__ == "__main__":
    ok = patch_file(sys.argv[1] if len(sys.argv) > 1 else "x_alert.py")
    sys.exit(0 if ok else 1)
