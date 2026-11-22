#!/usr/bin/env python3
"""DIP_FINAL_EMOJI_NOV22 - Final fix for the dip premium emoji issue.

Problem: /testdip 5 posts with ZERO premium emojis and NO DM error.
Facts established before this patch:
  - All 5 dip custom emoji ids are VALID via the Bot API
    (/testdipemoji: text message, one tg-emoji, parse_mode HTML - all OK).
  - The rich caption is NOT rejected (no DM error), so the Bot API rich
    send either succeeds while Telegram strips the entities, or it fails
    silently and the userbot posts (stripping entities). We cannot tell
    which, because the bot logs do NOT reach the journal (every journalctl
    grep for testdip / dip rich rejected came back empty), and the DM
    notify only fires when BOTH rich attempts fail.
  - The entity-mapping code is CORRECT (harness-proved: all 5 markers get
    the right ids via prepare_owner_emojis + _build_premium_entities).
  - The plain fallback now shows the crystal ball at all 5 positions
    (crystal_fallback patch), which the user accepts, but the PREMIUM
    emojis must actually render.

This patch does two things (final patch for this issue):
PART A - Immediate Bot API error visibility. When a Bot API rich send
raises, DM the exact error to the owner IMMEDIATELY, before the userbot
fallback, so a failing Bot API path is visible even when the userbot
then succeeds. Guarded, never breaks the fallback. Applied in
_testdip_send_text, _testdip_send_media (commands.py) and the channel
path of send_dip_alert (x_alert.py, DM to OWNER_ID). The existing
"both failed" DM notify is kept as well.
PART B - Explicit caption entities for the Bot API media send. In
_testdip_send_media (commands.py) and the channel path of send_dip_alert
(x_alert.py), the Bot API rich media send now tries EXPLICIT caption
entities first: _html_to_entities (the codebase's own converter, already
used for stored public command texts) turns the rich caption into plain
text + a MessageEntity list (5 custom_emoji with correct UTF-16 offsets,
plus the bold title and the 2 text_link entities), and the media is sent
with caption=plain text and caption_entities=entities and NO parse_mode.
If that raises, it falls back to the current parse_mode="HTML" rich send,
then the userbot, then the plain fallback. _testdip_send_text is NOT
changed to entities (text messages already work via parse_mode HTML,
proven by /testdipemoji); only Part A is added there. _dip_send_dm is
NOT touched.

VPS-only one-time script. Idempotent (marker DIP_FINAL_EMOJI_NOV22).
Backups: <file>.bak_finalemoji_nov22. Fail-safe: validates ALL anchors
before writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_dip_final_emoji_nov22.py
"""

import os
import sys

MARKER = "DIP_FINAL_EMOJI_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_finalemoji_nov22"


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
        err = e'''

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
    # DIP_FINAL_EMOJI_NOV22: when the Bot API rich send raises, DM the exact
    # error to the owner IMMEDIATELY, before the userbot fallback, so a
    # failing Bot API path is visible even when the userbot then succeeds.
    # The journal does not receive bot logs, so this DM is the only visibility.
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
        if notify_chat_id:
            try:
                await bot.send_message(chat_id=notify_chat_id,
                                       text="Bot API rich fail (testdip-text): " + str(e))
            except Exception:
                pass'''

OLD_TESTDIP_MEDIA = r'''async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids, notify_chat_id=None):
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
        err = e'''

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
    # (1) Bot API explicit-entities rich send.
    _ent_plain = None
    _ent_list = None
    try:
        _ent_plain, _ent_list, _ = _html_to_entities(rich_caption)
        _n_custom = 0
        _ok_ent = False
        if _ent_plain and _ent_list:
            _u16_total = len(_ent_plain.encode("utf-16-le")) // 2
            _ok_ent = True
            for _e in _ent_list:
                if getattr(_e, "type", "") == "custom_emoji":
                    _n_custom += 1
                _eo = int(getattr(_e, "offset", 0))
                _el = int(getattr(_e, "length", 0))
                if _eo < 0 or _el <= 0 or _eo + _el > _u16_total:
                    _ok_ent = False
                    break
            if _n_custom < 1:
                _ok_ent = False
        if not _ok_ent:
            _ent_plain = None
            _ent_list = None
    except Exception:
        _ent_plain = None
        _ent_list = None
    if _ent_list:
        try:
            if ftype == "photo":
                await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=_ent_plain, caption_entities=_ent_list)
            elif ftype == "gif":
                await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=_ent_plain, caption_entities=_ent_list)
            else:
                await bot.send_video(TARGET_CHANNEL, video=fid, caption=_ent_plain, caption_entities=_ent_list)
            return True
        except Exception as e:
            api_err = e
            err = e
            if notify_chat_id:
                try:
                    await bot.send_message(chat_id=notify_chat_id,
                                           text="Bot API rich fail (testdip-media): " + str(e))
                except Exception:
                    pass
                api_dm_sent = True
    # (2) Bot API parse_mode="HTML" rich send.
    try:
        if ftype == "photo":
            await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=rich_caption, parse_mode="HTML")
        elif ftype == "gif":
            await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=rich_caption, parse_mode="HTML")
        else:
            await bot.send_video(TARGET_CHANNEL, video=fid, caption=rich_caption, parse_mode="HTML")
        return True
    except Exception as e:
        if api_err is None:
            api_err = e
        err = e
        if notify_chat_id and not api_dm_sent:
            try:
                await bot.send_message(chat_id=notify_chat_id,
                                       text="Bot API rich fail (testdip-media): " + str(e))
            except Exception:
                pass
            api_dm_sent = True'''

# ---------------------------------------------------------------------------
# x_alert.py edits
# ---------------------------------------------------------------------------

OLD_ALERT_CHANNEL = r'''    # DIP_BOTAPI_FIRST_NOV22: Bot API rich send FIRST, userbot as fallback.
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
            _dip_log_rich_rejected(e, "dip-alert-botapi", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")'''

NEW_ALERT_CHANNEL = r'''    # DIP_BOTAPI_FIRST_NOV22: Bot API rich send FIRST, userbot as fallback.
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
        # (1) Bot API explicit-entities rich send.
        _ent_plain = None
        _ent_list = None
        try:
            _ent_plain, _ent_list, _ = _html_to_entities(caption)
            _n_custom = 0
            _ok_ent = False
            if _ent_plain and _ent_list:
                _u16_total = len(_ent_plain.encode("utf-16-le")) // 2
                _ok_ent = True
                for _e in _ent_list:
                    if getattr(_e, "type", "") == "custom_emoji":
                        _n_custom += 1
                    _eo = int(getattr(_e, "offset", 0))
                    _el = int(getattr(_e, "length", 0))
                    if _eo < 0 or _el <= 0 or _eo + _el > _u16_total:
                        _ok_ent = False
                        break
                if _n_custom < 1:
                    _ok_ent = False
            if not _ok_ent:
                _ent_plain = None
                _ent_list = None
        except Exception:
            _ent_plain = None
            _ent_list = None
        if _ent_list:
            try:
                if ftype == "photo":
                    await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=_ent_plain,
                                         caption_entities=_ent_list)
                elif ftype == "gif":
                    await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=_ent_plain,
                                             caption_entities=_ent_list)
                else:
                    await bot.send_video(TARGET_CHANNEL, video=fid, caption=_ent_plain,
                                         caption_entities=_ent_list)
                posted = True
            except Exception as e:
                if "not a member" in str(e).lower() or "forbidden" in str(e).lower():
                    _BOT_CHANNEL_FORBIDDEN["v"] = True
                _dip_log_rich_rejected(e, "dip-alert-botapi", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")
                if OWNER_ID:
                    try:
                        await bot.send_message(chat_id=OWNER_ID,
                                               text="Bot API rich fail (dip-alert): " + str(e))
                    except Exception:
                        pass
                    _api_dm_sent = True
        # (2) Bot API parse_mode="HTML" rich send.
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
                _dip_log_rich_rejected(e, "dip-alert-botapi", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")
                if OWNER_ID and not _api_dm_sent:
                    try:
                        await bot.send_message(chat_id=OWNER_ID,
                                               text="Bot API rich fail (dip-alert): " + str(e))
                    except Exception:
                        pass
                    _api_dm_sent = True'''

EDITS = {
    "commands.py": {
        "replaces": [
            (OLD_TESTDIP_TEXT, NEW_TESTDIP_TEXT, "_testdip_send_text Bot API fail DM"),
            (OLD_TESTDIP_MEDIA, NEW_TESTDIP_MEDIA, "_testdip_send_media explicit entities + Bot API fail DM"),
        ],
        "inserts": [],
        "requires": [
            ("def _html_to_entities(text):", "_html_to_entities converter present"),
        ],
    },
    "x_alert.py": {
        "replaces": [
            (OLD_ALERT_CHANNEL, NEW_ALERT_CHANNEL, "send_dip_alert channel explicit entities + Bot API fail DM"),
        ],
        "inserts": [],
        "requires": [],
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
    print("Then verify: run /testdip 5 in the bot DM and check (a) the")
    print("channel post for premium emojis and (b) the owner DM for any")
    print("immediate 'Bot API rich fail' message with the exact error.")


if __name__ == "__main__":
    main()
