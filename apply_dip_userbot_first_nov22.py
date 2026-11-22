#!/usr/bin/env python3
"""DIP_USERBOT_FIRST_NOV22 - Revert the dip send order to USERBOT FIRST.

Problem: /testdip 5 after the final_emoji patch posts to the channel but
premium emojis STILL do not render (all crystal balls), and NO "Bot API
rich fail" DM error arrives. That means the Bot API rich send (explicit
entities first, then parse_mode HTML) SUCCEEDS without raising, but
Telegram's server strips the custom emoji entities from the media caption
sent to the channel. The Bot API path definitively does NOT render premium
emojis in the channel media caption, regardless of explicit entities or
HTML parsing. /testdipemoji proves the bot CAN use these ids, but only in
a TEXT message to the DM, not in a media caption to the channel.

The normal X alerts DO show premium emojis in @WizardScan, and they are
sent via the USERBOT (@yowziuh). The userbot is the PROVEN path for
premium emojis in channel posts. The DIP pack (WizardScanDIPEMOJIS) was
installed on @yowziuh at about 10:30 PKT on 2026-11-22, but the
botapi_first patch (deployed about 10:53 PKT) switched the dip to Bot API
first. Since then the Bot API always "succeeds" (stripping entities), so
the USERBOT FALLBACK IS NEVER REACHED. The userbot has never been tried
for the dip media send after the pack was installed on @yowziuh.

This patch only reorders the existing attempts, it adds no new send logic:
  _testdip_send_media (commands.py): (1) userbot rich send, (2) Bot API
    explicit-entities rich send, (3) Bot API parse_mode HTML rich send,
    (4) plain fallback. The Part A immediate "Bot API rich fail" DM and
    the "both failed" DM notify are kept unchanged.
  send_dip_alert channel path (x_alert.py): (1) userbot rich send,
    (2) Bot API explicit-entities, (3) Bot API parse_mode HTML,
    (4) hold in pending (media-hold rule, no plain post). The Part A
    immediate "Bot API rich fail" DM to OWNER_ID is kept unchanged.

Not touched: _testdip_send_text (text messages already work via Bot API),
_dip_send_dm (Bot API only), the emoji ids, titles, template structure,
DM-only setting, /testdip channel target, build_dip_caption, the plain
fallback captions (crystal ball), or any other feature.

VPS-only one-time script. Idempotent (marker DIP_USERBOT_FIRST_NOV22).
Backups: <file>.bak_userbotfirst_nov22. Fail-safe: validates ALL anchors
before writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_dip_userbot_first_nov22.py
"""

import os
import sys

MARKER = "DIP_USERBOT_FIRST_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_userbotfirst_nov22"


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _count(text, sub):
    return text.count(sub)


# ---------------------------------------------------------------------------
# commands.py edits (_testdip_send_media reorder)
# ---------------------------------------------------------------------------

OLD_CMD_HEADER = r'''async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids, notify_chat_id=None):
    # DIP_TESTCHANNEL_NOV22: media + caption to TARGET_CHANNEL; plain
    # caption on rejection. Returns True if posted.
    # DIP_BOTAPI_FIRST_NOV22: Bot API rich send FIRST, userbot as fallback.
    # The Bot API provably renders these dip custom emojis (/testdipemoji:
    # all 5 OK), while the userbot send returns a message but Telegram
    # drops the custom emoji entities for that session, so userbot-first
    # posts render non-premium and the Bot API fallback never runs.
    # DIP_EMOJI_NOV22: every rich rejection is logged with logger.error
    # (tag "dip rich rejected") so the exact Telegram error is in the journal.
    # The emoji ids attempted are logged too, so a bad id can be identified.
    # DIP_FINAL_EMOJI_NOV22: Bot API rich send tries EXPLICIT caption
    # entities first (_html_to_entities converts the rich caption into plain
    # text + a MessageEntity list, so no parse_mode parsing is involved),
    # then the parse_mode="HTML" rich send, then the userbot, then the plain
    # fallback. When a Bot API rich send raises, the exact error is DMed to
    # the owner immediately, because the journal does not receive bot logs
    # and this DM is the only visibility into a failing Bot API path.
    import asyncio
    err = None
    ub_err = None
    api_err = None
    api_dm_sent = False
    # (1) Bot API explicit-entities rich send.'''

NEW_CMD_HEADER = r'''async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids, notify_chat_id=None):
    # DIP_TESTCHANNEL_NOV22: media + caption to TARGET_CHANNEL; plain
    # caption on rejection. Returns True if posted.
    # DIP_USERBOT_FIRST_NOV22: userbot rich send FIRST, Bot API as fallback.
    # The Bot API rich send succeeds but Telegram strips the custom emoji
    # entities from the media caption to the channel, so Bot-API-first posts
    # render non-premium (proven by /testdip 5 after the final_emoji patch:
    # post happens, no DM error, all crystal balls). The userbot is the
    # proven path for premium emojis in channel posts (normal X alerts),
    # and the DIP pack was installed on @yowziuh after the botapi_first
    # switch, so the userbot was never tried for dip media since then.
    # DIP_EMOJI_NOV22: every rich rejection is logged with logger.error
    # (tag "dip rich rejected") so the exact Telegram error is in the journal.
    # The emoji ids attempted are logged too, so a bad id can be identified.
    # DIP_FINAL_EMOJI_NOV22: Bot API rich send tries EXPLICIT caption
    # entities first (_html_to_entities converts the rich caption into plain
    # text + a MessageEntity list, so no parse_mode parsing is involved),
    # then the parse_mode="HTML" rich send. When a Bot API rich send raises,
    # the exact error is DMed to the owner immediately, because the journal
    # does not receive bot logs and this DM is the only visibility into a
    # failing Bot API path.
    import asyncio
    err = None
    ub_err = None
    api_err = None
    api_dm_sent = False
    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.
    if userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               rich_caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
            if msg is not None:
                return True
            ub_err = Exception("userbot send returned None")
            err = ub_err
        except Exception as e:
            ub_err = e
            err = e
    # (2) Bot API explicit-entities rich send.'''

OLD_CMD_PARSEMODE = r'''                api_dm_sent = True
    # (2) Bot API parse_mode="HTML" rich send.
    try:'''

NEW_CMD_PARSEMODE = r'''                api_dm_sent = True
    # (3) Bot API parse_mode="HTML" rich send.
    try:'''

OLD_CMD_UBOLD = r'''    if userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               rich_caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
            if msg is not None:
                return True
            ub_err = Exception("userbot send returned None")
            err = ub_err
        except Exception as e:
            ub_err = e
            err = e
    _dip_log_rich_rejected(err, "testdip-media",'''

NEW_CMD_UBOLD = r'''    # DIP_USERBOT_FIRST_NOV22: userbot attempt moved to the top of this function.
    _dip_log_rich_rejected(err, "testdip-media",'''

# ---------------------------------------------------------------------------
# x_alert.py edits (send_dip_alert channel path reorder)
# ---------------------------------------------------------------------------

OLD_ALERT_HEADER = r'''    # DIP_BOTAPI_FIRST_NOV22: Bot API rich send FIRST, userbot as fallback.
    # The Bot API provably renders these dip custom emojis (/testdipemoji:
    # all 5 OK), while the userbot send returns a message but Telegram
    # drops the custom emoji entities for that session, so userbot-first
    # posts render non-premium and the Bot API fallback never runs.
    # DIP_FINAL_EMOJI_NOV22: Bot API rich send tries EXPLICIT caption
    # entities first (_html_to_entities converts the rich caption into plain
    # text + a MessageEntity list, so no parse_mode parsing is involved),
    # then the parse_mode="HTML" rich send, then the userbot. When a Bot API
    # rich send raises, the exact error is DMed to the owner immediately,
    # because the journal does not receive bot logs and this DM is the only
    # visibility into a failing Bot API path. _html_to_entities lives in
    # commands.py (shared namespace); if it is unavailable the explicit
    # attempt is skipped and the parse_mode send runs as before.
    posted = False
    _api_dm_sent = False
    if not _BOT_CHANNEL_FORBIDDEN["v"]:
        # (1) Bot API explicit-entities rich send.'''

NEW_ALERT_HEADER = r'''    # DIP_USERBOT_FIRST_NOV22: userbot rich send FIRST, Bot API as fallback.
    # The Bot API rich send succeeds but Telegram strips the custom emoji
    # entities from the media caption to the channel, so Bot-API-first posts
    # render non-premium (proven by /testdip 5 after the final_emoji patch:
    # post happens, no DM error, all crystal balls). The userbot is the
    # proven path for premium emojis in channel posts (normal X alerts),
    # and the DIP pack was installed on @yowziuh after the botapi_first
    # switch, so the userbot was never tried for dip media since then.
    # DIP_FINAL_EMOJI_NOV22: Bot API rich send tries EXPLICIT caption
    # entities first (_html_to_entities converts the rich caption into plain
    # text + a MessageEntity list, so no parse_mode parsing is involved),
    # then the parse_mode="HTML" rich send. When a Bot API rich send raises,
    # the exact error is DMed to the owner immediately, because the journal
    # does not receive bot logs and this DM is the only visibility into a
    # failing Bot API path. _html_to_entities lives in commands.py (shared
    # namespace); if it is unavailable the explicit attempt is skipped and
    # the parse_mode send runs as before.
    posted = False
    _api_dm_sent = False
    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.
    if not posted and userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
            if msg is not None:
                posted = True
        except Exception as e:
            _dip_log_rich_rejected(e, "dip-alert-userbot", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")
    if not posted and not _BOT_CHANNEL_FORBIDDEN["v"]:
        # (2) Bot API explicit-entities rich send.'''

OLD_ALERT_PARSEMODE = r'''        # (2) Bot API parse_mode="HTML" rich send.
        if not posted and not _BOT_CHANNEL_FORBIDDEN["v"]:'''

NEW_ALERT_PARSEMODE = r'''        # (3) Bot API parse_mode="HTML" rich send.
        if not posted and not _BOT_CHANNEL_FORBIDDEN["v"]:'''

OLD_ALERT_UBOLD = r'''    if not posted and userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
            if msg is not None:
                posted = True
        except Exception as e:
            _dip_log_rich_rejected(e, "dip-alert-userbot", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")
    if posted:'''

NEW_ALERT_UBOLD = r'''    # DIP_USERBOT_FIRST_NOV22: userbot attempt moved to the top of the channel path.
    if posted:'''

EDITS = {
    "commands.py": {
        "replaces": [
            (OLD_CMD_HEADER, NEW_CMD_HEADER, "_testdip_send_media userbot first"),
            (OLD_CMD_PARSEMODE, NEW_CMD_PARSEMODE, "_testdip_send_media renumber parse_mode to (3)"),
            (OLD_CMD_UBOLD, NEW_CMD_UBOLD, "_testdip_send_media remove old userbot block"),
        ],
        "inserts": [],
        "requires": [
            ("DIP_FINAL_EMOJI_NOV22", "final_emoji patch applied"),
        ],
    },
    "x_alert.py": {
        "replaces": [
            (OLD_ALERT_HEADER, NEW_ALERT_HEADER, "send_dip_alert userbot first"),
            (OLD_ALERT_PARSEMODE, NEW_ALERT_PARSEMODE, "send_dip_alert renumber parse_mode to (3)"),
            (OLD_ALERT_UBOLD, NEW_ALERT_UBOLD, "send_dip_alert remove old userbot block"),
        ],
        "inserts": [],
        "requires": [
            ("DIP_FINAL_EMOJI_NOV22", "final_emoji patch applied"),
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
        for anchor, ins, label in spec["inserts"]:
            n_anchor = _count(text, anchor)
            n_ins = _count(text, ins)
            if n_anchor == 1 and n_ins == 0:
                continue
            if n_ins >= 1:
                print(f"  SKIP {fname}: {label} already applied.")
                continue
            print(f"ABORT: {fname} {label}: anchor found {n_anchor}x "
                  f"(expected 1), insert found {n_ins}x.")
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
        for anchor, ins, label in spec["inserts"]:
            if _count(text, ins) == 0 and _count(text, anchor) == 1:
                text = text.replace(anchor, ins + anchor, 1)
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
    print("Then verify: run /testdip 5 in the bot DM and check the")
    print("channel post for premium emojis.")


if __name__ == "__main__":
    main()
