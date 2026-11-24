"""apply_forward_on_nov25.py - X-alert DM alerts + channel forwards wapas ON.

Reverses apply_stop_forward2_nov23.py (STOP_FORWARD_NOV23, Nov 23 ~21:44
PKT): removes the single early `return` line it added at the top of
_forward_alert_recipients in x_alert.py. All later patches (FINAL, PERM,
DIPFIX, GUARD, DIP_BOLD, DROPBOT_MODE, MONBOT_MODE, USERBOT2_OFF) stay
intact. Only that one return line is removed; recipients, dip forwarding
(a separate function) and everything else are untouched.

Idempotent. Backs up x_alert.py to x_alert.py.bak_forward_on_nov25.
Run: python3 apply_forward_on_nov25.py /opt/bot
Then: systemctl restart bot.service
"""

import sys, shutil

MARKER = "FORWARD_ON_NOV25"
STOP_MARKER = "STOP_FORWARD_NOV23"

OLD = '''async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    return  # STOP_FORWARD_NOV23: DM alerts + channel forwards paused by owner
    """Forward the already-published WizardScan post without rebuilding it.'''

NEW = '''async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    # FORWARD_ON_NOV25: DM alerts + channel forwards re-enabled by owner
    """Forward the already-published WizardScan post without rebuilding it.'''


def patch_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print("FAIL: %s not found" % path)
        return False
    if MARKER in src:
        print("OK: %s already has FORWARD_ON_NOV25, skipping." % path)
        return True
    if STOP_MARKER not in src:
        print("OK: %s has no STOP_FORWARD line, forwards already ON, skipping."
              % path)
        return True
    if src.count(OLD) != 1:
        print("FAIL: anchor not unique/found in %s (%dx) -- NOT writing "
              "anything." % (path, src.count(OLD)))
        print("Live file may differ from the Nov 23 base copy. Report the "
              "output, do not force it.")
        return False
    shutil.copy2(path, path + ".bak_forward_on_nov25")
    src = src.replace(OLD, NEW, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("E1 OK (forward ON again, STOP_FORWARD return removed)")
    print("DONE. Backup: %s.bak_forward_on_nov25" % path)
    print("Now restart the wizu bot (systemctl restart bot.service).")
    return True


if __name__ == "__main__":
    ok = patch_file(sys.argv[1] if len(sys.argv) > 1 else "x_alert.py")
    sys.exit(0 if ok else 1)
