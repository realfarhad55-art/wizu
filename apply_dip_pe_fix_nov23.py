# apply_dip_pe_fix_nov23.py - Fix NameError: name 'pe' is not defined (DIP_PE_FIX_NOV23)
# Root cause (found Nov 23 20:58 PKT from live logs): pending_dip_media_job
# fails every 15s for held dip alerts with "name 'pe' is not defined".
# build_dip_caption() calls pe(emoji_id, fallback) to build <tg-emoji> tags,
# but pe() is a BigBang helper - it is NOT defined anywhere in the wizu bot
# (core/x_alert/runtime/commands/dropped_call/leaderboard/most_shared).
# Normal X alerts never call pe(), only the dip caption does, so this bug
# only breaks dip alerts: no held dip alert can ever be released.
# Fix: define pe() right before build_dip_caption in x_alert.py.
# Safe if pe() already exists elsewhere (same implementation, redefinition
# is a no-op in Python).
# Usage: python3 apply_dip_pe_fix_nov23.py x_alert.py
import sys

MARKER = "DIP_PE_FIX_NOV23"

OLD = "def build_dip_caption(call, x_val, cur_mc, include_promo=True):"
NEW = """def pe(emoji_id, fallback):  # DIP_PE_FIX_NOV23: <tg-emoji> helper (was missing in wizu)
    try:
        return '<tg-emoji emoji-id="%s">%s</tg-emoji>' % (int(emoji_id), fallback)
    except (TypeError, ValueError):
        return fallback


def build_dip_caption(call, x_val, cur_mc, include_promo=True):"""


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "x_alert.py"
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if MARKER in src:
        print("already has %s, skipping" % MARKER)
        return
    if src.count(OLD) != 1:
        print("FAIL: anchor not unique/found:", src.count(OLD))
        return
    orig = src
    src = src.replace(OLD, NEW, 1)
    with open(path + ".bak_dip_pe_fix_nov23", "w", encoding="utf-8") as f:
        f.write(orig)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("OK: pe() defined before build_dip_caption (x_alert.py)")
    print("Backup: x_alert.py.bak_dip_pe_fix_nov23")
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")

if __name__ == "__main__":
    main()
