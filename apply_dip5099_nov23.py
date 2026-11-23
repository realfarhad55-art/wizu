# apply_dip5099_nov23.py - dip range min 50% max 99% (DIP5099_NOV23)
# Min dip 50%: DIP_DEFAULT_THRESHOLD_PCT 30 -> 50 (threshold clamp max 50, so 50 is allowed).
# Max dip 99%: dip low floor = max(1000.0, entry * 0.01) so the low never goes
# below 1K MC (user rule) and never below 1% of entry (max 99% dip).
# NOTE: run /setdipthreshold 50 after deploy so the stored config also becomes 50.
# Usage: python3 apply_dip5099_nov23.py x_alert.py
import sys

MARKER = "DIP5099_NOV23"

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "x_alert.py"
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if MARKER in src:
        print("already applied, skipping")
        return
    orig = src

    old1 = "DIP_DEFAULT_THRESHOLD_PCT = 30.0"
    new1 = "DIP_DEFAULT_THRESHOLD_PCT = 50.0  # DIP5099_NOV23: min dip 50%"
    if src.count(old1) != 1:
        print("FAIL: threshold anchor not unique/found:", src.count(old1))
        return
    src = src.replace(old1, new1)

    old2 = "    if cur_mc <= entry_mc * (1.0 - threshold / 100.0):\n        if cur_mc >= 1000.0:"
    new2 = "    if cur_mc <= entry_mc * (1.0 - threshold / 100.0):\n        if cur_mc >= max(1000.0, entry_mc * DIP_DUST_FLOOR_FRAC):  # DIP5099_NOV23: 1K floor + max 99% dip"
    if src.count(old2) != 1:
        print("FAIL: floor anchor not unique/found:", src.count(old2))
        return
    src = src.replace(old2, new2)

    with open(path + ".bak_dip5099_nov23", "w", encoding="utf-8") as f:
        f.write(orig)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("OK: min dip 50%, max dip 99% (x_alert.py)")
    print("Backup: x_alert.py.bak_dip5099_nov23")
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("Then run /setdipthreshold 50 so the stored config is 50 too.")

if __name__ == "__main__":
    main()
