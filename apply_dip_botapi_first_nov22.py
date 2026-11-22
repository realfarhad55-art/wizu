#!/usr/bin/env python3
"""DIP_BOTAPI_FIRST_NOV22 - Bot API first for dip sends.

Problem: /testdip 5 posts with NO error (the rich caption is not
rejected) but the premium custom emojis do not render, and the chain
emoji shows where the crystal ball should be. /testdipemoji proved
all 5 dip custom emoji ids are VALID via the Bot API (all 5 OK), and
the userbot entity-mapping code is correct (harness-proved: all 5
markers get the right ids). The remaining cause: the userbot send
returns a message while Telegram's server drops the custom emoji
entities for that userbot session (@yowziuh's access to the DIP pack
is not effective there), so the post renders non-premium. Because the
userbot is tried FIRST and "succeeds", the Bot API fallback is skipped
and the broken userbot post is what the channel shows.

Fix: for dip sends only, try the Bot API rich send FIRST and the
userbot as fallback. The Bot API provably renders these 5 ids.
This patch swaps the send order in three functions:
  - _testdip_send_text (commands.py, /testdip text preview)
  - _testdip_send_media (commands.py, /testdip media preview)
  - send_dip_alert (x_alert.py, real dip alerts, channel path only)
_dip_send_dm (x_alert.py, DM delivery for real dip alerts) already
uses the Bot API only and is NOT touched.

Behaviour kept exactly: rich first, plain fallback only when BOTH
rich attempts fail (testdip helpers); the DM-error notify still fires
only when both rich attempts fail; send_dip_alert still holds the
alert in pending (no plain post) when both rich attempts fail, per
the media-hold rule; the _BOT_CHANNEL_FORBIDDEN flag still skips the
Bot API attempt; the log tags stay the same ("testdip-text",
"testdip-media", "dip-alert-botapi", "dip-alert-userbot") so the
existing greps keep working, and the log extra now names the Bot API
error first.

VPS-only one-time script. Idempotent (marker DIP_BOTAPI_FIRST_NOV22).
Backups: <file>.bak_botapifirst_nov22. Fail-safe: validates ALL
anchors before writing anything; aborts without touching files on
mismatch.
Usage: cd /opt/bot && python3 apply_dip_botapi_first_nov22.py
"""

import os
import sys

MARKER = "DIP_BOTAPI_FIRST_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_botapifirst_nov22"


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

OLD_TESTDIP_TEXT = r'''async def _testdip_send_text(bot, rich_text, plain_text, notify_chat_id=None):
    # DIP_TESTCHANNEL_NOV22: text preview to TARGET_CHANNEL, userbot-first,
    # Bot API fallback; rich first, plain on rejection. Returns True if posted.
    # DIP_EMOJI_NOV22: every rich rejection is logged with logger.error
    # (tag "dip rich rejected") so the exact Telegram error is in the journal.
    import asyncio
    err = None
    ub_err = None
    try:
        if userbot_client:
            try:
                await asyncio.wait_for(
                    _userbot_send_with_premium_emoji(TARGET_CHANNEL, rich_text),
                    timeout=USERBOT_SEND_TIMEOUT_SECONDS)
                return True
            except Exception as e:
                ub_err = e
                err = e
        await bot.send_message(chat_id=TARGET_CHANNEL, text=rich_text,
                               parse_mode="HTML", disable_web_page_preview=True)
        return True
    except Exception as e:
        err = e
    _dip_log_rich_rejected(err, "testdip-text",
                           ("userbot: %s" % ub_err) if ub_err is not None else "")'''

NEW_TESTDIP_TEXT = r'''async def _testdip_send_text(bot, rich_text, plain_text, notify_chat_id=None):
    # DIP_TESTCHANNEL_NOV22: text preview to TARGET_CHANNEL; rich first,
    # plain on rejection. Returns True if posted.
    # DIP_BOTAPI_FIRST_NOV22: Bot API rich send FIRST, userbot as fallback.
    # The Bot API provably renders these dip custom emojis (/testdipemoji:
    # all 5 OK), while the userbot send returns a message but Telegram
    # drops the custom emoji entities for that session, so userbot-first
    # posts render non-premium and the Bot API fallback never runs.
    # DIP_EMOJI_NOV22: every rich rejection is logged with logger.error
    # (tag "dip rich rejected") so the exact Telegram error is in the journal.
    import asyncio
    err = None
    ub_err = None
    api_err = None
    try:
        await bot.send_message(chat_id=TARGET_CHANNEL, text=rich_text,
                               parse_mode="HTML", disable_web_page_preview=True)
        return True
    except Exception as e:
        api_err = e
        err = e
    if userbot_client:
        try:
            await asyncio.wait_for(
                _userbot_send_with_premium_emoji(TARGET_CHANNEL, rich_text),
                timeout=USERBOT_SEND_TIMEOUT_SECONDS)
            return True
        except Exception as e:
            ub_err = e
            err = e
    _dip_log_rich_rejected(err, "testdip-text",
                           ("botapi: %s | userbot: %s" % (api_err, ub_err)) if ub_err is not None else ("botapi: %s" % api_err))'''

OLD_TESTDIP_MEDIA = r'''async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids, notify_chat_id=None):
    # DIP_TESTCHANNEL_NOV22: media + caption to TARGET_CHANNEL, userbot-first
    # (with the dip emoji ids, same as real dip alerts), Bot API fallback;
    # plain caption on rejection. Returns True if posted.
    # DIP_EMOJI_NOV22: every rich rejection is logged with logger.error
    # (tag "dip rich rejected") so the exact Telegram error is in the journal.
    # The emoji ids attempted are logged too, so a bad id can be identified.
    import asyncio
    err = None
    ub_err = None
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
    try:
        if ftype == "photo":
            await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=rich_caption, parse_mode="HTML")
        elif ftype == "gif":
            await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=rich_caption, parse_mode="HTML")
        else:
            await bot.send_video(TARGET_CHANNEL, video=fid, caption=rich_caption, parse_mode="HTML")
        return True
    except Exception as e:
        err = e
    _dip_log_rich_rejected(err, "testdip-media",
                           ("userbot: %s | emoji_ids: %s" % (ub_err, emoji_ids)) if ub_err is not None else ("emoji_ids: %s" % (emoji_ids,)))'''

NEW_TESTDIP_MEDIA = r'''async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids, notify_chat_id=None):
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
    import asyncio
    err = None
    ub_err = None
    api_err = None
    try:
        if ftype == "photo":
            await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=rich_caption, parse_mode="HTML")
        elif ftype == "gif":
            await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=rich_caption, parse_mode="HTML")
        else:
            await bot.send_video(TARGET_CHANNEL, video=fid, caption=rich_caption, parse_mode="HTML")
        return True
    except Exception as e:
        api_err = e
        err = e
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
    _dip_log_rich_rejected(err, "testdip-media",
                           ("botapi: %s | userbot: %s | emoji_ids: %s" % (api_err, ub_err, emoji_ids)) if ub_err is not None else ("botapi: %s | emoji_ids: %s" % (api_err, emoji_ids)))'''

# ---------------------------------------------------------------------------
# x_alert.py edits
# ---------------------------------------------------------------------------

OLD_ALERT_CHANNEL = r'''    posted = False
    if userbot_client:
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
        try:
            if ftype == "photo":
                await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=caption,
                                     parse_mode="HTML")
            elif ftype == "gif":
                await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=caption,
                                         parse_mode="HTML")
            else:
                await bot.send_video(TARGET_CHANNEL, video=fid, caption=caption,
                                     parse_mode="HTML")
            posted = True
        except Exception as e:
            if "not a member" in str(e).lower() or "forbidden" in str(e).lower():
                _BOT_CHANNEL_FORBIDDEN["v"] = True
            _dip_log_rich_rejected(e, "dip-alert-botapi", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")'''

NEW_ALERT_CHANNEL = r'''    # DIP_BOTAPI_FIRST_NOV22: Bot API rich send FIRST, userbot as fallback.
    # The Bot API provably renders these dip custom emojis (/testdipemoji:
    # all 5 OK), while the userbot send returns a message but Telegram
    # drops the custom emoji entities for that session, so userbot-first
    # posts render non-premium and the Bot API fallback never runs.
    posted = False
    if not _BOT_CHANNEL_FORBIDDEN["v"]:
        try:
            if ftype == "photo":
                await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=caption,
                                     parse_mode="HTML")
            elif ftype == "gif":
                await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=caption,
                                         parse_mode="HTML")
            else:
                await bot.send_video(TARGET_CHANNEL, video=fid, caption=caption,
                                     parse_mode="HTML")
            posted = True
        except Exception as e:
            if "not a member" in str(e).lower() or "forbidden" in str(e).lower():
                _BOT_CHANNEL_FORBIDDEN["v"] = True
            _dip_log_rich_rejected(e, "dip-alert-botapi", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")
    if not posted and userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
            if msg is not None:
                posted = True
        except Exception as e:
            _dip_log_rich_rejected(e, "dip-alert-userbot", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")'''

EDITS = {
    "commands.py": {
        "replaces": [
            (OLD_TESTDIP_TEXT, NEW_TESTDIP_TEXT, "_testdip_send_text botapi first"),
            (OLD_TESTDIP_MEDIA, NEW_TESTDIP_MEDIA, "_testdip_send_media botapi first"),
        ],
        "inserts": [],
    },
    "x_alert.py": {
        "replaces": [
            (OLD_ALERT_CHANNEL, NEW_ALERT_CHANNEL, "send_dip_alert channel botapi first"),
        ],
        "inserts": [],
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
    print("channel post shows the premium emojis (chain, crystal ball,")
    print("teer, Post Link, Dexscreener), not the plain fallbacks.")


if __name__ == "__main__":
    main()
