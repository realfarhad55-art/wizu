#!/usr/bin/env python3
"""DIP_EMOJI_FIX_NOV22 - Fix the dip emoji positions 3, 4, 5 in the userbot path.

Root cause (proven by running the real functions in a harness):
  /testdip 5 after the userbot_first patch renders premium emojis, but
  positions 3, 4, 5 are WRONG: pos 3 shows the BLUE pack teer, pos 4
  shows the DIP teer, pos 5 shows the BLUE pack dexscreener. Positions 1
  (chain SOL) and 2 (crystal) are correct.
  The local code path (prepare_owner_emojis -> _build_premium_entities
  with the explicit map {0: SOL, 1: CRYSTAL, 2: TEER, 3: POSTLINK,
  4: DEX}) produces all 5 correct DIP ids. But running the same real
  _build_premium_entities with an EMPTY explicit map reproduces the live
  post EXACTLY: pos 1 SOL, pos 2 CRYSTAL (positional coincidence), pos 3
  blue teer 5818848205453927129 (MC-separator lock, blue pack), pos 4 DIP
  teer 5764885063820910875 (positional list, off by one because the MC
  lock does not advance pos_index), pos 5 blue dex 5863945855983166730
  (DEX label lock, blue pack). So in the LIVE userbot path the explicit
  map is empty / not applied, and the fallthrough positional + label-lock
  logic takes over (live code drift: the live core.py differs from the
  local Nov 18 copy in prepare_owner_emojis / _build_premium_entities).
  The fix does NOT depend on the explicit map: it passes a forced_pack
  carrying the DIP ids to the userbot send, so the MC-separator, Post
  and DEX locks all resolve to the DIP ids. When the explicit map IS
  present it wins anyway, so this is harmless there (harness-proved).

Also applies the user-specified MC-line spacing: two spaces after the
entry MC and two spaces after the teer, so the line reads
"crystal 74.9K  teer  264.7K". Applied to build_dip_caption (rich) and
both plain fallback captions (_dip_plain_caption, _dip_plain_caption_dm).

Changes (reorder-free, no new send logic):
  commands.py _testdip_send_media: userbot call passes
    forced_pack=_dip_pack (DIP ids for teer/dex/post/crystal).
  commands.py _dip_plain_caption: MC line gets the 2-space spacing.
  x_alert.py send_dip_alert channel path: userbot call passes
    forced_pack=_dip_pack (same DIP pack).
  x_alert.py build_dip_caption: MC line gets the 2-space spacing.
  x_alert.py _dip_plain_caption_dm: MC line gets the 2-space spacing.

Not touched: positions 1 and 2 (already correct), the emoji ids
themselves, titles, template structure, DM-only setting, /testdip
channel target, the send order (userbot first), _dip_send_dm,
_testdip_send_text, the X-alert or dropped-call emoji mappings, or any
other feature. No core.py change: the fix lives at the dip call sites.

VPS-only one-time script. Idempotent (marker DIP_EMOJI_FIX_NOV22).
Backups: <file>.bak_emojifix_nov22. Fail-safe: validates ALL anchors
before writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_dip_emoji_fix_nov22.py
"""

import os
import sys

MARKER = "DIP_EMOJI_FIX_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_emojifix_nov22"


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _count(text, sub):
    return text.count(sub)


# ---------------------------------------------------------------------------
# commands.py edits
# ---------------------------------------------------------------------------

OLD_CMD_USERBOT = r'''    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.
    if userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               rich_caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)'''

NEW_CMD_USERBOT = r'''    # DIP_EMOJI_FIX_NOV22: force the DIP emoji pack for the userbot
    # send. _build_premium_entities falls back to positional + label
    # locks when its explicit map is empty (live behaviour, proven by
    # the /testdip 5 post: blue teer at pos 3, DIP teer at pos 4, blue
    # dex at pos 5), and those locks resolve teer/dex/post from the
    # current X-alert pack. Forcing the DIP pack makes the MC-separator,
    # Post and DEX locks all resolve to the DIP ids. When the explicit
    # map IS present it wins anyway, so this is harmless there.
    _dip_pack = {"name": "dip", "teer": DIP_TEER_EMOJI_ID,
                 "dex": DIP_DEX_EMOJI_ID, "post": DIP_POSTLINK_EMOJI_ID,
                 "crystal": DIP_CRYSTAL_EMOJI_ID}
    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.
    if userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               rich_caption, emoji_ids,
                                               forced_pack=_dip_pack),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)'''

OLD_CMD_PLAIN_MC = r'''             f"🔮 {_dip_fmt_plain(entry_mc)} 🔮 {_dip_fmt_plain(cur_mc)}", ""]'''

NEW_CMD_PLAIN_MC = r'''             f"🔮 {_dip_fmt_plain(entry_mc)}  🔮  {_dip_fmt_plain(cur_mc)}", ""]'''

# ---------------------------------------------------------------------------
# x_alert.py edits
# ---------------------------------------------------------------------------

OLD_X_USERBOT = r'''    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.
    if not posted and userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)'''

NEW_X_USERBOT = r'''    # DIP_EMOJI_FIX_NOV22: force the DIP emoji pack for the userbot
    # send (same reason as in _testdip_send_media: the live userbot path
    # runs _build_premium_entities with an empty explicit map, so the
    # MC-separator, Post and DEX locks would otherwise resolve teer/dex
    # from the current X-alert pack instead of the DIP ids).
    _dip_pack = {"name": "dip", "teer": DIP_TEER_EMOJI_ID,
                 "dex": DIP_DEX_EMOJI_ID, "post": DIP_POSTLINK_EMOJI_ID,
                 "crystal": DIP_CRYSTAL_EMOJI_ID}
    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.
    if not posted and userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               caption, emoji_ids,
                                               forced_pack=_dip_pack),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)'''

OLD_X_RICH_MC = r'''        f"{crystal_e} {entry_fmt} {teer_e} {cur_fmt}",'''

NEW_X_RICH_MC = r'''        f"{crystal_e} {entry_fmt}  {teer_e}  {cur_fmt}",'''

OLD_X_DM_MC = r'''             f"🔮 {_dip_fmt_plain_dm(entry_mc)} 🔮 {_dip_fmt_plain_dm(cur_mc)}", ""]'''

NEW_X_DM_MC = r'''             f"🔮 {_dip_fmt_plain_dm(entry_mc)}  🔮  {_dip_fmt_plain_dm(cur_mc)}", ""]'''

EDITS = {
    "commands.py": {
        "replaces": [
            (OLD_CMD_USERBOT, NEW_CMD_USERBOT, "userbot forced DIP pack"),
            (OLD_CMD_PLAIN_MC, NEW_CMD_PLAIN_MC, "plain caption MC spacing"),
        ],
        "requires": [
            ("DIP_USERBOT_FIRST_NOV22", "userbot-first patch present"),
            ("DIP_FINAL_EMOJI_NOV22", "final-emoji patch present"),
        ],
    },
    "x_alert.py": {
        "replaces": [
            (OLD_X_USERBOT, NEW_X_USERBOT, "userbot forced DIP pack"),
            (OLD_X_RICH_MC, NEW_X_RICH_MC, "rich caption MC spacing"),
            (OLD_X_DM_MC, NEW_X_DM_MC, "DM plain caption MC spacing"),
        ],
        "requires": [
            ("DIP_USERBOT_FIRST_NOV22", "userbot-first patch present"),
            ("DIP_FINAL_EMOJI_NOV22", "final-emoji patch present"),
        ],
    },
}


def main():
    print(f"{MARKER} patch - target dir: {BOT_DIR}")
    texts = {}
    for fname in EDITS:
        path = os.path.join(BOT_DIR, fname)
        if not os.path.isfile(path):
            print(f"ABORT: {path} not found. Run this script in /opt/bot.")
            sys.exit(1)
        texts[fname] = _read(path)

    # ---- Phase 1: validate ALL anchors before writing anything ----
    for fname, spec in EDITS.items():
        text = texts[fname]
        for old, new, label in spec["replaces"]:
            n_old = _count(text, old)
            n_new = _count(text, new)
            if n_new >= 1:
                print(f"  SKIP {fname}: {label} already applied.")
                continue
            if n_old == 1:
                continue
            print(f"ABORT: {fname} {label}: old block found {n_old}x "
                  f"(expected 1), new found {n_new}x.")
            sys.exit(1)
        for req, label in spec.get("requires", []):
            if _count(text, req) < 1:
                print(f"ABORT: {fname} {label}: required text not found.")
                sys.exit(1)

    # ---- Phase 2: apply ----
    for fname, spec in EDITS.items():
        path = os.path.join(BOT_DIR, fname)
        text = texts[fname]
        changed = []
        for old, new, label in spec["replaces"]:
            if _count(text, old) == 1 and _count(text, new) == 0:
                text = text.replace(old, new, 1)
                changed.append(label)
        if not changed:
            print(f"SKIP: {fname} already patched.")
            continue
        bak = path + BAK_SUFFIX
        _write(bak, texts[fname])
        print(f"Backup: {bak}")
        _write(path, text)
        print(f"Patched: {fname} ({', '.join(changed)})")

    print("DONE. Now restart the bot: systemctl restart bot.service")
    print("Then verify: run /testdip 5 in the bot DM and check all 5")
    print("emoji positions on the channel post (chain, crystal, teer,")
    print("Post Link, Dexscreener) plus the MC-line spacing.")


if __name__ == "__main__":
    main()
