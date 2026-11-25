#!/usr/bin/env python3
"""
Move the Fast Track button above the DM Alerts button (Nov 25 2026).

User order (Nov 25 ~11:14 PKT): Fast Track button DM Alerts button ke
UPAR hona chahiye. This reverses the Nov 18 swap (BTN_SWAP_NOV18), which
put DM Alerts above Fast Track.

Change (core.py, build_command_keyboard, one edit):
  Before: dm_alerts, channel_alerts (KOL Alert), fast_track
  After:  fast_track, dm_alerts, channel_alerts (KOL Alert)
  The KOL Alert button stays right after DM Alerts.

Marker: FASTTRACK_TOP_NOV25. Idempotent, .bak backup, fail-safe on
anchor mismatch. Repo: wizu. Run on /opt/bot AFTER patches 1-4 and the
KOL broadcast patch, then restart bot.service.
"""
import os
import sys

MARKER = "FASTTRACK_TOP_NOV25"

EDITS = [
    ("core.py", [
        # E1: move fast_track above dm_alerts (KOL Alert stays after DM Alerts).
        (
            '        [_pkb(lbl("dm_alerts",    "🔮 DM Alerts 🔮"),         callback_data="dm_alerts")],  # BTN_SWAP_NOV18: DM Alerts Fast Track se upar\n'
            '        [_pkb(lbl("channel_alerts", "🔮 KOL Alert 🔮"), callback_data="channel_alerts")],  # KOL_BROADCAST_NOV25: renamed from "Channel Alerts" by owner order\n'
            '        [_pkb(lbl("fast_track",   "🔮 Fast Track 🔮"),        callback_data="fast_track")],',
            '        [_pkb(lbl("fast_track",   "🔮 Fast Track 🔮"),        callback_data="fast_track")],\n'
            '        [_pkb(lbl("dm_alerts",    "🔮 DM Alerts 🔮"),         callback_data="dm_alerts")],  # FASTTRACK_TOP_NOV25: Fast Track DM Alerts se upar (owner order, reverses BTN_SWAP_NOV18)\n'
            '        [_pkb(lbl("channel_alerts", "🔮 KOL Alert 🔮"), callback_data="channel_alerts")],  # KOL_BROADCAST_NOV25: renamed from "Channel Alerts" by owner order',
        ),
    ]),
]


def apply_one(path, old, new):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if new in text:
        return "SKIP"
    if old not in text:
        return "FAIL"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.replace(old, new, 1))
    return "OK"


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
    all_ok = True
    for fname, edits in EDITS:
        path = os.path.join(base, fname)
        bak = path + ".bak_" + MARKER
        if not os.path.exists(path):
            print("FAIL (%s): file not found" % fname)
            all_ok = False
            continue
        if not os.path.exists(bak):
            with open(path, "rb") as f:
                data = f.read()
            with open(bak, "wb") as f:
                f.write(data)
        for i, (old, new) in enumerate(edits, 1):
            res = apply_one(path, old, new)
            print("E%d %s (%s)" % (i, res, fname))
            if res == "FAIL":
                all_ok = False
        print("DONE %s. Backup: %s" % (fname, bak))
    print("ALL OK" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
