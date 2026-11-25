#!/usr/bin/env python3
"""
apply_doubletrack_fix2_nov25.py - Corrected double-track guard for
dropbot_import_job. Replaces the DOUBLETRACK_NOV25 patch, which was
ROLLED BACK live (Nov 25 ~13:05 PKT) because it corrupted records.

WHAT WENT WRONG (traced in code, not guessed):
The first patch routed a different-key CA match into the pre-existing
entry-update branch of dropbot_import_job. That branch overwrites the
existing entry upward when the incoming entry is >8% higher and the
old entry_src is live. A re-post / forwarded X alert carries the
CURRENT price as its entry, so the MIHAO 9513 record (real entry
$11K) was overwritten with the duplicate 9558 record's entry
($535.8K) on the first import tick after deploy. The record display
(get_call_history, leaderboard.py) computes peak as entry x current
ratio, so it then showed 535.8K x 60 = 32.15M. The stored peak_mc
was never rewritten (nothing on the main bot writes peak_mc while
MONBOT_MODE=1); 32.15M is a display recompute from the corrupted
entry, not a stored value. The $MIHAO data is still wrong after the
rollback; restore it with restore_mihao_nov25.py (separate script).

THE FIX (one edit, dropped_call.py):
A CA match under a DIFFERENT key is a re-post or forward, never an
entry correction: SKIP it entirely (do not touch the existing record
at all) and log it. Only a SAME-KEY import (same post, genuine entry
revision from the dropbot confirm task) may run the entry-update
branch, under its existing guards (>8% up, live-src only). The
pre-existing branch never updates an entry downward, so a lower
incoming entry is never applied either.

This patch applies ON TOP OF the rolled-back (pre-doubletrack)
dropped_call.py. If DOUBLETRACK_NOV25 is still present, it refuses
with a clear message (roll back first). Idempotent, .bak backup,
fail-safe on anchor mismatch. Repo: wizu. Run on /opt/bot, then
restart bot.service.
"""
import os
import sys

MARKER = "DOUBLETRACK_FIX2_NOV25"
OLD_MARKER = "DOUBLETRACK_NOV25"

EDITS = [
    ("dropped_call.py", [
        # E1: corrected CA guard in dropbot_import_job. Different-key CA
        # match -> SKIP entirely (original entry is the truth). Same-key
        # -> existing entry-update branch, unchanged.
        (
            "    for call_key, c in incoming.items():\n"
            "        try:\n"
            "            if call_key in tracked_calls:\n"
            "                # Entry revise hui ho to main bot ki entry bhi upar karo\n"
            "                # (sirf live-src entries, aur sirf meaningful jump par).\n"
            "                _old = tracked_calls[call_key]",
            "    for call_key, c in incoming.items():\n"
            "        try:\n"
            "            # DOUBLETRACK_FIX2_NOV25: corrected CA guard. Replaces\n"
            "            # DOUBLETRACK_NOV25, which routed a different-key CA\n"
            "            # match into the entry-update branch below. That branch\n"
            "            # overwrites the existing entry upward when the incoming\n"
            "            # entry is >8% higher and the old entry_src is live. A\n"
            "            # re-post / forwarded X alert carries the CURRENT price\n"
            "            # as its entry, so it overwrote the original call entry\n"
            "            # (MIHAO 9513: 11K -> 535.8K) and the record display\n"
            "            # then showed entry x 60x = 32.15M. The original entry\n"
            "            # is the truth. A CA match under a DIFFERENT key is a\n"
            "            # re-post or forward, never an entry correction: SKIP it\n"
            "            # entirely and log it. Only a SAME-KEY import (same\n"
            "            # post, genuine entry revision from the dropbot confirm\n"
            "            # task) may run the entry-update branch, under its\n"
            "            # existing guards. Fail-safe: any error here falls back\n"
            "            # to exact-key behaviour, so a real new call is never\n"
            "            # blocked.\n"
            "            _dt_skip = False\n"
            "            try:\n"
            "                _dt_ca = str(c.get(\"ca\", \"\") or \"\").lower()\n"
            "                _dt_ch = c.get(\"channel\", \"\")\n"
            "                if _dt_ca and _dt_ch:\n"
            "                    for _dt_k, _dt_o in list(tracked_calls.items()):\n"
            "                        try:\n"
            "                            if (_dt_o.get(\"channel\") == _dt_ch\n"
            "                                    and (str(_dt_o.get(\"ca\", \"\")).lower() == _dt_ca\n"
            "                                         or _dt_k.lower() == f\"{_dt_ch}_{_dt_ca}\".lower())):\n"
            "                                if _dt_k != call_key:\n"
            "                                    logger.info(f\"dropbot_import: CA duplicate, same call as {_dt_k} (incoming key {call_key}, incoming msg {c.get('msg_id', '?')} vs existing msg {_dt_o.get('msg_id', '?')}) - skipping, original entry kept\")\n"
            "                                    _dt_skip = True\n"
            "                                break\n"
            "                        except Exception:\n"
            "                            continue\n"
            "            except Exception:\n"
            "                _dt_skip = False\n"
            "            if _dt_skip:\n"
            "                continue\n"
            "            if call_key in tracked_calls:\n"
            "                # Entry revise hui ho to main bot ki entry bhi upar karo\n"
            "                # (sirf live-src entries, aur sirf meaningful jump par).\n"
            "                _old = tracked_calls[call_key]",
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
        with open(path, "r", encoding="utf-8") as f:
            _txt = f.read()
        if MARKER in _txt:
            print("OK: already has DOUBLETRACK_FIX2_NOV25, skipping.")
            continue
        if OLD_MARKER in _txt:
            print("FAIL: DOUBLETRACK_NOV25 is still present in %s." % fname)
            print("Roll it back first: cp %s.bak_DOUBLETRACK_NOV25 %s" % (path, path))
            print("then re-run this patch. Nothing was changed.")
            return 1
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
