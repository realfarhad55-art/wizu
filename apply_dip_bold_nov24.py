"""apply_dip_bold_nov24.py - Dip X alert MC line BOLD.

User request (Nov 24 2026): dip MC line "🔮 5.3K  🔮  38.8K" BOLD ho.
Live line (x_alert.py:3574, DIPFIX version, dip low first):
    f"{crystal_e} {low_fmt}  {teer_e}  {cur_fmt}",
Becomes:
    f"<b>{crystal_e} {low_fmt}  {teer_e}  {cur_fmt}</b>",
Caption HTML parse mode me jata hai (title pehle se <b> me hai), is liye
<b> tags kaam karenge. Custom emojis (<tg-emoji> via pe()) bold ke andar
bhi render hote hain.

Run: python3 apply_dip_bold_nov24.py [/opt/bot]
Then: systemctl restart bot.service
Idempotent. Backup: x_alert.py.bak_dipbold_nov24
"""

import os, sys, shutil

MARKER = "DIP_BOLD_NOV24"

OLD = '''        f"{crystal_e} {low_fmt}  {teer_e}  {cur_fmt}",'''

NEW = '''        f"<b>{crystal_e} {low_fmt}  {teer_e}  {cur_fmt}</b>",  # DIP_BOLD_NOV24'''


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    path = os.path.join(d, "x_alert.py")
    if not os.path.exists(path):
        print("FAIL: %s not found" % path)
        return 1
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if MARKER in src:
        print("OK: already has DIP_BOLD_NOV24, skipping.")
        return 0
    if src.count(OLD) != 1:
        print("FAIL: anchor missing/dup (found %dx) — NOT writing anything."
              % src.count(OLD))
        return 1
    shutil.copy2(path, path + ".bak_dipbold_nov24")
    src = src.replace(OLD, NEW, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("OK: dip MC line ab BOLD hai.")
    print("Backup: x_alert.py.bak_dipbold_nov24")
    print("Next: systemctl restart bot.service")
    return 0


if __name__ == "__main__":
    sys.exit(main())
