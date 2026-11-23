#!/usr/bin/env python3
"""POINTS15_NOV23 - 15-day auto-zero for channels whose points stay at/above 100.

User design (Nov 23, confirmed):
  - Some channels pile up very high points (e.g. 300) and NEVER drop
    below 100. Their points auto-zero after 15 days.
  - Champion KOLs: after 10 days channels are removed from the Champions
    list and must re-enter rank with a NEW call / NEW X.
  - Leaderboard: auto-reset after 3 days.
  (Leaderboard 3 days + champions 10 days are in the separate
  apply_reset_rules_nov23.py patch. This patch is the 15-day rule.)

Why the champion reset must skip 100+ channels:
  _auto_champions_reset used to zero ALL points, so a 100+ channel's
  points would already be gone at day 10 and a 15-day rule could never
  fire. After this patch the champion reset only zeroes points for
  channels BELOW 100. A 100+ channel keeps its points — but it still
  leaves the Champions LIST at day 10, because champion qualification
  needs BOTH pts>=100 AND best_x>=2, and best_x is computed from
  milestones ABOVE the reset snapshot (old calls stop counting). So the
  channel must earn a NEW call with NEW X to get best_x>=2 and come
  back onto the list. Its old points persist until the 15-day expiry.

Changes:
  1) leaderboard.py _auto_champions_reset: keep channels with >=100
     points (preserve their whole entry dict, incl. points_100_since);
     zero only channels below 100.
  2) leaderboard.py NEW async def _expire_100plus_points(now): runs from
     champions_job every tick (cheap: only saves when something changed).
     - 100+ pts + no timestamp -> stamp it now (legacy channels get a
       full 15 days from deploy, never retroactively zeroed).
     - 100+ pts + timestamp 15+ days old -> points = 0, timestamp cleared.
     - below 100 + stale timestamp -> timestamp cleared.
  3) leaderboard.py champions_job: call _expire_100plus_points(now) after
     the auto-reset check.
  4) core.py award_points_for_milestone: when a channel's points cross
     from below 100 to >=100, stamp entry["points_100_since"] = now.
     (The expiry job also self-heals a missing timestamp, so no other
     award/deduct path needs hooking.)

Not touched: leaderboard 3-day / champion 10-day intervals (separate
patch), the snapshot/exclusion mechanism, points values, the dip
feature, or any other feature. Works whether or not
apply_reset_rules_nov23.py was applied first (anchors avoid the
7-day/10-day wording).

VPS-only one-time script. Idempotent (marker POINTS15_NOV23).
Backups: leaderboard.py.bak_points15_nov23, core.py.bak_points15_nov23.
Fail-safe: validates ALL anchors before writing anything; aborts
without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_points15_nov23.py
"""

import os
import sys

MARKER = "POINTS15_NOV23"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_points15_nov23"

POINTS15_DAYS = 15

# --- leaderboard.py edits -------------------------------------------------
_LB_OLD_RESET = (
    "    async with _points_lock:\n"
    "        save_channel_points({})\n"
)
_LB_NEW_RESET = (
    "    async with _points_lock:\n"
    "        # POINTS15_NOV23: keep channels at/above 100 points — their points\n"
    "        # auto-zero after 15 days (see _expire_100plus_points), not here.\n"
    "        # Only channels below 100 lose their points at the champion reset.\n"
    "        # (They still leave the Champions LIST at day 10: champion status\n"
    "        # needs best_x>=2 from milestones ABOVE the reset snapshot, so old\n"
    "        # calls stop counting and a NEW call / NEW X is required to return.)\n"
    "        _pts = load_channel_points()\n"
    "        _kept = {}\n"
    "        for _k, _v in _pts.items():\n"
    "            _p = _v.get(\"points\", 0) if isinstance(_v, dict) else _v\n"
    "            if isinstance(_p, (int, float)) and _p >= POINTS_FOR_CHAMPION:\n"
    "                _kept[_k] = _v\n"
    "        save_channel_points(_kept)\n"
)

_LB_EXPIRE_FN = '''
async def _expire_100plus_points(now):
    """POINTS15_NOV23: auto-zero points for channels that stay at/above 100.

    A channel whose points never drop below 100 (e.g. 300 pts) keeps them
    for 15 days from when it first reached 100+ (points_100_since), then
    its points auto-zero. Channels below 100 are untouched here (the
    champion reset handles them). Only saves when something changed.
    """
    try:
        async with _points_lock:
            pts_data = load_channel_points()
            changed = False
            for _k, _entry in list(pts_data.items()):
                if not isinstance(_entry, dict):
                    continue
                _pts = _entry.get("points", 0)
                _since = _entry.get("points_100_since", "")
                if _pts >= POINTS_FOR_CHAMPION:
                    if not _since:
                        # Legacy / pre-patch channel: start the 15-day clock now.
                        _entry["points_100_since"] = now.isoformat()
                        changed = True
                    else:
                        try:
                            _since_dt = datetime.fromisoformat(_since)
                        except Exception:
                            _entry["points_100_since"] = now.isoformat()
                            changed = True
                            continue
                        if (now - _since_dt) >= timedelta(days=15):
                            _entry["points"] = 0
                            _entry.pop("points_100_since", None)
                            changed = True
                            logger.info(f"⏳ Points 15-day auto-zero: {_k} had {_pts} pts since {_since}")
                else:
                    if _since:
                        _entry.pop("points_100_since", None)
                        changed = True
            if changed:
                save_channel_points(pts_data)
    except Exception as e:
        logger.error(f"100+ points expiry check failed: {e}")


'''

_LB_OLD_JOB = (
    "    except Exception as e:\n"
    "        logger.error(f\"Champions auto-reset check failed: {e}\")\n"
)
_LB_NEW_JOB = (
    "    except Exception as e:\n"
    "        logger.error(f\"Champions auto-reset check failed: {e}\")\n"
    "\n"
    "    # ── 15-day auto-zero for 100+ channels (POINTS15_NOV23) ────────────────\n"
    "    try:\n"
    "        await _expire_100plus_points(now)\n"
    "    except Exception as e:\n"
    "        logger.error(f\"100+ points expiry call failed: {e}\")\n"
)

# --- core.py edits ---------------------------------------------------------
_CORE_OLD_AWARD = (
    '        entry["points"] = max(0, entry.get("points", 0) + new_pts)\n'
    "        call_awarded.append(tier_threshold)\n"
)
_CORE_NEW_AWARD = (
    '        entry["points"] = max(0, entry.get("points", 0) + new_pts)\n'
    "        # POINTS15_NOV23: stamp the moment this channel first reaches 100+.\n"
    "        # The 15-day auto-zero clock runs from here.\n"
    "        if entry[\"points\"] >= POINTS_FOR_CHAMPION and not entry.get(\"points_100_since\"):\n"
    "            entry[\"points_100_since\"] = datetime.utcnow().isoformat()\n"
    "        call_awarded.append(tier_threshold)\n"
)

REPLACES = [
    # leaderboard.py
    ("leaderboard.py", _LB_OLD_RESET, _LB_NEW_RESET,
     "champion reset keeps 100+ channels"),
    ("leaderboard.py", _LB_OLD_JOB, _LB_NEW_JOB,
     "champions_job calls 15-day expiry"),
    # core.py
    ("core.py", _CORE_OLD_AWARD, _CORE_NEW_AWARD,
     "stamp points_100_since on crossing 100"),
]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    print(f"{MARKER} patch - target dir: {BOT_DIR}")
    replaces = REPLACES
    # Insert the new _expire_100plus_points function right before
    # _auto_champions_reset in leaderboard.py.
    lb_path = os.path.join(BOT_DIR, "leaderboard.py")
    if not os.path.isfile(lb_path):
        print(f"ABORT: {lb_path} not found. Run this script in /opt/bot.")
        sys.exit(1)
    lb_text = _read(lb_path)
    fn_anchor = "async def _auto_champions_reset(now):"
    if _LB_EXPIRE_FN.strip().splitlines()[1].strip() in lb_text:
        print("NOTE: _expire_100plus_points already present in leaderboard.py (skip insert).")
        fn_done = True
    elif lb_text.count(fn_anchor) != 1:
        print(f"ABORT: _auto_champions_reset anchor found {lb_text.count(fn_anchor)}x (expected 1).")
        print("Nothing was written.")
        sys.exit(1)
    else:
        fn_done = False

    # ---- Phase 1: validate ALL anchors before writing anything ----
    texts = {}
    for fname, old, new, label in replaces:
        path = os.path.join(BOT_DIR, fname)
        if fname not in texts:
            if not os.path.isfile(path):
                print(f"ABORT: {path} not found. Run this script in /opt/bot.")
                sys.exit(1)
            texts[fname] = _read(path)
        text = texts[fname]
        n_old = text.count(old)
        n_new = text.count(new)
        if n_new >= 1:
            continue
        if n_old != 1:
            print(f"ABORT: {label}: anchor found {n_old}x (expected 1).")
            print("Nothing was written. Check the live file and re-run after fixing.")
            sys.exit(1)

    # ---- Phase 2: apply ----
    changed = []
    for fname, old, new, label in replaces:
        text = texts[fname]
        if text.count(old) == 1 and text.count(new) == 0:
            texts[fname] = text.replace(old, new, 1)
            changed.append(label)
    if not fn_done:
        texts["leaderboard.py"] = texts["leaderboard.py"].replace(
            fn_anchor, _LB_EXPIRE_FN.lstrip("\n") + fn_anchor, 1)
        changed.append("add _expire_100plus_points function")
    if not changed:
        print("SKIP: files already patched (POINTS15_NOV23 present).")
        print("DONE. No change needed - just restart if you have not since.")
        return
    for fname, text in texts.items():
        path = os.path.join(BOT_DIR, fname)
        bak = path + BAK_SUFFIX
        _write(bak, _read(path))
        print(f"Backup: {bak}")
        _write(path, text)
        print(f"Patched: {fname}")
    print(f"Patched ({', '.join(changed)})")
    print("DONE. Now restart the bot: systemctl restart bot.service")
    print("Then verify: a 100+ channel keeps its points past the next")
    print("10-day champion reset, and its points auto-zero 15 days after")
    print("it first reached 100 (check the entry's points_100_since).")


if __name__ == "__main__":
    main()
