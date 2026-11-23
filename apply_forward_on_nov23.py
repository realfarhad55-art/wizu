# apply_forward_on_nov23.py - DM alerts + channel forwards wapas ON (FORWARD_ON_NOV23)
# Reverses apply_stop_forward_nov23.py: removes the single early `return` line
# it added at the top of _forward_alert_recipients. All later patches
# (monsplit, dipconfirm1, dipfloor1k, dip5099, badge cache) stay intact.
# Do NOT restore from x_alert.py.bak_stopforward_nov23 - that backup predates
# those patches and would revert them.
# Usage: python3 apply_forward_on_nov23.py x_alert.py
import sys, shutil

MARKER = "FORWARD_ON_NOV23"
STOP_MARKER = "STOP_FORWARD_NOV23"

OLD = """async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    return  # STOP_FORWARD_NOV23: DM alerts + channel forwards paused by owner
    \"\"\"Forward the already-published WizardScan post without rebuilding it."""
NEW = """async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    # FORWARD_ON_NOV23: DM alerts + channel forwards re-enabled by owner
    \"\"\"Forward the already-published WizardScan post without rebuilding it."""


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "x_alert.py"
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if STOP_MARKER not in src:
        print("already ON (no STOP_FORWARD line found), skipping")
        return
    if src.count(OLD) != 1:
        print("FAIL: anchor not unique/found:", src.count(OLD))
        return
    orig = src
    src = src.replace(OLD, NEW, 1)
    with open(path + ".bak_forward_on_nov23", "w", encoding="utf-8") as f:
        f.write(orig)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("OK: DM alerts + channel forwards are ON again (x_alert.py)")
    print("Backup: x_alert.py.bak_forward_on_nov23")
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")

if __name__ == "__main__":
    main()
