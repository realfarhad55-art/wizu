#!/usr/bin/env python3
"""Rebuild sent_milestones.json v2 (Nov 23 2026) — PROPER fix for the spam.

Problem: v1 rebuild sealed 2641 milestones across 674 calls, but 396
calls got NOTHING sealed because their best_x reads <= 1 (record
corruption from the Nov 17 collapse — peaks lost, best_x None/1,
milestone_posts empty). Those 396 calls are the ones STILL spamming
old X alerts from last week, because the bot sees their current
price at a milestone level and the milestone was never sealed.

Fix v2: for a call whose best_x is corrupted (<= 1), seal ALL
milestones up to 100x. Rationale: an old call with a corrupted
record that is firing alerts has ALREADY pumped (that is why it is
spamming) — sealing everything stops the re-fires. The only cost is
that such a call will not alert again even if it pumps to a new high
later; that is the right trade while the record is broken, and the
owner can still trigger a manual alert if one ever matters.
For a call with a healthy best_x (> 1), seal only milestones <=
best_x, exactly as v1 did (so genuine NEW alerts above best_x still
fire).

Run ONCE from /opt/bot while the bot is STOPPED:
    python3 rebuild_milestones_v2_nov23.py
Then restart:
    systemctl restart bot.service
VPS-only one-time script. Backs up sent_milestones.json first.
Idempotent — running it twice changes nothing.
"""

import json, os, shutil, sys

DATA = os.environ.get("DATA_DIR", "data")
MILESTONES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 18, 20, 22, 25, 28,
              30, 32, 34, 35, 38, 40, 45, 50, 55, 60, 65, 75, 80, 90,
              100, 150, 200, 250, 300, 500, 600, 700, 800, 900, 1000,
              2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000,
              11000, 12000, 13000, 14000, 15000, 20000, 25000, 30000,
              40000, 50000, 60000, 70000, 80000, 90000, 100000]
# Corrupted-record calls get everything sealed up to this level.
CORRUPT_SEAL_MAX = 100


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

    if os.path.exists(ms_path):
        shutil.copy(ms_path, ms_path + ".bak_rebuild2_nov23")
        print("Backup: %s.bak_rebuild2_nov23" % ms_path)

    healthy_calls = 0
    corrupt_calls = 0
    added_ms = 0
    for call_key, call in tracked.items():
        if not isinstance(call, dict):
            continue
        bx = best_x_of(call)
        want = set()
        if bx >= 2:
            for m in MILESTONES:
                if m <= bx:
                    want.add(m)
            healthy_calls += 1
        else:
            # Corrupted record (best_x < 2) — seal everything up to 100x
            # so it can never re-fire an old alert.
            for m in MILESTONES:
                if m <= CORRUPT_SEAL_MAX:
                    want.add(m)
            corrupt_calls += 1
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
            added_ms += len(new)

    with open(ms_path, "w", encoding="utf-8") as f:
        json.dump(sent, f)
    print("DONE. Healthy calls: %d, corrupted calls sealed to 100x: %d, "
          "milestones sealed: %d, total calls in file: %d"
          % (healthy_calls, corrupt_calls, added_ms, len(sent)))
    print("Now restart the bot: systemctl restart bot.service")
    print("Old alerts will NOT re-fire. Healthy calls still alert on NEW milestones above their best X.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
