#!/usr/bin/env python3
"""
apply_doubletrack_nov25.py - Fix the double-track bug in dropbot_import_job.

User report (Nov 25 ~12:47 PKT): tokens show twice in the record
($MIHAO 1.1x, $ETHCAT 1x in the @Bigbangcall record). Diagnosis in
double-track-note.md: dropbot_import_job (live since Nov 24, in
apply_dropbot_mode_nov24.py) dedupes ONLY on exact call_key. It never
runs the Oct-21 CA guard that _process_new_call has in both bots
(same channel + same CA, checked against both the old key AND the old
record's ca field = same call). The dropbot's guard only sees its own
file, never the main bot's legacy tracked_calls.json. So a token first
tracked by the main bot pre-Nov-24 under one key and re-posted
post-Nov-24 tracked by the dropbot under a different key gets a
SECOND record on import. Dip is NOT the cause (it only writes fields
on the existing call dict).

Fix (one edit, dropped_call.py): port the Oct-21 CA guard into
dropbot_import_job. Before the insert, resolve the effective key: if
any existing tracked_calls entry has the same channel and the same CA
(lowercased, compared against both the old key and the old record's
ca field), the existing entry-update branch runs against THAT record
and no second record is created. Fail-safe: on ANY error in the
guard, fall back to the current exact-key behaviour, so a real new
call is never blocked.

The archive merge in get_call_history has the same exact-key-only
weakness (noted in double-track-note.md); it is NOT changed here,
because the live check has not shown an archive-side duplicate yet.

Files: dropped_call.py only.
Marker: DOUBLETRACK_NOV25. Idempotent, .bak backup, fail-safe on
anchor mismatch. Repo: wizu. Run on /opt/bot, then restart bot.service.
"""
import os
import sys

MARKER = "DOUBLETRACK_NOV25"

EDITS = [
    ("dropped_call.py", [
        # E1: CA guard in dropbot_import_job, before the exact-key check.
        # The guard resolves _dt_key to the EXISTING record when the same
        # channel + same CA is already tracked under a different key, so
        # the entry-update branch below runs against it and no second
        # record is inserted.
        (
            "    for call_key, c in incoming.items():\n"
            "        try:\n"
            "            if call_key in tracked_calls:\n"
            "                # Entry revise hui ho to main bot ki entry bhi upar karo\n"
            "                # (sirf live-src entries, aur sirf meaningful jump par).\n"
            "                _old = tracked_calls[call_key]",
            "    for call_key, c in incoming.items():\n"
            "        try:\n"
            "            # DOUBLETRACK_NOV25: Oct-21 CA guard, ported from\n"
            "            # _process_new_call. The dropbot's own guard only sees\n"
            "            # its file, so a token first tracked by the main bot\n"
            "            # (pre-Nov-24, key built from a pair address) and\n"
            "            # re-posted by the dropbot (different key) slipped past\n"
            "            # the exact-key check and got a SECOND tracked_calls\n"
            "            # entry. Same channel + same CA (checked against the\n"
            "            # old key AND the old record's ca field, lowercased)\n"
            "            # is the same call, whatever the key says. A match\n"
            "            # runs the entry-update branch below against the\n"
            "            # EXISTING record, no second record is made.\n"
            "            # Fail-safe: any error here falls back to exact-key\n"
            "            # behaviour, so a real new call is never blocked.\n"
            "            _dt_key = call_key\n"
            "            try:\n"
            "                _dt_ca = str(c.get(\"ca\", \"\") or \"\").lower()\n"
            "                _dt_ch = c.get(\"channel\", \"\")\n"
            "                if _dt_ca and _dt_ch:\n"
            "                    for _dt_k, _dt_o in list(tracked_calls.items()):\n"
            "                        try:\n"
            "                            if (_dt_o.get(\"channel\") == _dt_ch\n"
            "                                    and (str(_dt_o.get(\"ca\", \"\")).lower() == _dt_ca\n"
            "                                         or _dt_k.lower() == f\"{_dt_ch}_{_dt_ca}\".lower())):\n"
            "                                _dt_key = _dt_k\n"
            "                                if _dt_key != call_key:\n"
            "                                    logger.info(f\"dropbot_import: CA duplicate, same call as {_dt_key} (incoming key {call_key}) - updating existing record\")\n"
            "                                break\n"
            "                        except Exception:\n"
            "                            continue\n"
            "            except Exception:\n"
            "                _dt_key = call_key\n"
            "            if _dt_key in tracked_calls:\n"
            "                # Entry revise hui ho to main bot ki entry bhi upar karo\n"
            "                # (sirf live-src entries, aur sirf meaningful jump par).\n"
            "                _old = tracked_calls[_dt_key]",
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
