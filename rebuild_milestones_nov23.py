#!/usr/bin/env python3
"""Rebuild sent_milestones.json from tracked_calls.json (Nov 23 2026).

Problem: after the badge-cache restart, OLD X alerts re-fired and
spammed @WizardScan + the KOL channels where the bot is admin.
Cause: sent_milestones.json on disk was STALE — it was missing the
seals for milestones that already fired. On restart the bot loaded
the stale file, thought those milestones never fired, and re-posted
them. (The dupx patch saves seals going forward, but the file was
already stale from the many Nov 22 restarts.)

Fix: rebuild sent_milestones.json from the live record. For every
tracked call, mark all milestones at or below its best X as already
sent, plus every milestone that has a post in milestone_posts.
A milestone ABOVE the call's best X is left alone, so genuine NEW
alerts still fire. Existing entries are kept and only added to.

Run ONCE from /opt/bot while the bot is STOPPED:
    python3 rebuild_milestones_nov23.py
Then restart:
    systemctl restart bot.service
VPS-only one-time script. Backs up sent_milestones.json first.
Safe: never deletes data, only ADDS seals for milestones the call
already reached. Idempotent — running it twice changes nothing.
"""

import json, os, shutil, sys

DATA = os.environ.get("DATA_DIR", "data")
MILESTONES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 18, 20, 22, 25, 28,
              30, 32, 34, 35, 38, 40, 45, 50, 55, 60, 65, 75, 80, 90,
              100, 150, 200, 250, 300, 500, 600, 700, 800, 900, 1000,
              2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000,
              11000, 12000, 13000, 14000, 15000, 20000, 25000, 30000,
              40000, 50000, 60000, 70000, 80000, 90000, 100000]


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print("FAIL: cannot read %s: %s" % (path, e))
        return None


def best_x_of(call):
    try:
        bx = call.get("best_x")
        if bx is not None and float(bx) > 1:
            return float(bx)
    except Exception:
        pass
    try:
        peak = float(call.get("peak_mc") or 0)
        entry = float(call.get("entry_mc") or 0)
        if peak > 0 and entry > 0:
            return peak / entry
    except Exception:
        pass
    return 0.0


def main():
    tracked_path = os.path.join(DATA, "tracked_calls.json")
    ms_path = os.path.join(DATA, "sent_milestones.json")
    tracked = load(tracked_path)
    if tracked is None:
        return 1
    if not isinstance(tracked, dict) or not tracked:
        print("FAIL: %s is empty or not a dict — aborting, nothing changed." % tracked_path)
        return 1
    sent = load(ms_path)
    if sent is None:
        return 1
    if not isinstance(sent, dict):
        sent = {}

    # Backup the current sent_milestones.json first.
    if os.path.exists(ms_path):
        shutil.copy(ms_path, ms_path + ".bak_rebuild_nov23")
        print("Backup: %s.bak_rebuild_nov23" % ms_path)

    added_calls = 0
    added_ms = 0
    for call_key, call in tracked.items():
        if not isinstance(call, dict):
            continue
        bx = best_x_of(call)
        want = set()
        for m in MILESTONES:
            if m <= bx:
                want.add(m)
        # Any milestone with a recorded post definitely fired.
        mp = call.get("milestone_posts") or {}
        if isinstance(mp, dict):
            for k in mp.keys():
                try:
                    want.add(int(k))
                except Exception:
                    pass
        if not want:
            continue
        cur = sent.get(call_key)
        if isinstance(cur, list):
            cur = set(cur)
        elif isinstance(cur, set):
            pass
        else:
            cur = set()
        new = want - cur
        if new:
            cur |= new
            sent[call_key] = sorted(cur)
            added_calls += 1
            added_ms += len(new)

    with open(ms_path, "w", encoding="utf-8") as f:
        json.dump(sent, f)
    print("DONE. Calls updated: %d, milestones sealed: %d, total calls in file: %d"
          % (added_calls, added_ms, len(sent)))
    print("Now restart the bot: systemctl restart bot.service")
    print("Old alerts will NOT re-fire. New milestones above each call's best X still alert normally.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
