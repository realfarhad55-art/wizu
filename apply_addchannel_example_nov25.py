#!/usr/bin/env python3
"""
Fix the Add Channel example text (Nov 25 2026).

User caught it: the Add Channel prompt used a REAL channel name
(@Trenchmarkgems) as the example. That is wrong, a real channel must
never be the example. Both Add Channel prompts now use the generic
placeholder @channel instead.

Changes (commands.py only):
  E1: DMSET_ADD_TEXT (DM Alert Add Channel)  @Trenchmarkgems -> @channel
  E2: CHALERT_ADD_TEXT (Channel/KOL Alert Add Channel)  @Trenchmarkgems -> @channel

Marker: ADDCHANNEL_EXAMPLE_NOV25. Idempotent, .bak backup, fail-safe
on anchor mismatch. Repo: wizu. Run on /opt/bot, then restart bot.service.
"""
import os
import sys

MARKER = "ADDCHANNEL_EXAMPLE_NOV25"

EDITS = [
    ("commands.py", [
        # E1: DM Alert Add Channel example (patch 3, DMSET_ADD_TEXT).
        (
            "    'Send the channel username, like @Trenchmarkgems.\\n\\n'\n"
            "    \"I'll subscribe you and bring you back here to set its alerts. \"",
            "    'Send the channel username, like @channel.\\n\\n'\n"
            "    \"I'll subscribe you and bring you back here to set its alerts. \"",
        ),
        # E2: Channel/KOL Alert Add Channel example (patch 4, CHALERT_ADD_TEXT).
        (
            "    'Send the channel username, like @Trenchmarkgems.\\n\\n'\n"
            "    \"I'll link it and bring you back here to set its alerts. \"",
            "    'Send the channel username, like @channel.\\n\\n'\n"
            "    \"I'll link it and bring you back here to set its alerts. \"",
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
