#!/usr/bin/env python3
# apply_dip_emoji_nov22.py - DIP EMOJI fix for wizu (WizardScan bot).
# VPS-ONLY one-time script. Run it ONCE on the Contabo VPS as root:
#   cd /opt/bot && python3 apply_dip_emoji_nov22.py
# It edits commands.py and x_alert.py in /opt/bot
# (pass another dir as argv[1] to target a copy instead).
# Idempotent: files already containing DIP_EMOJI_NOV22 are skipped.
# Fail-safe: every anchor is checked BEFORE anything is written; if any
# anchor is missing (live code drifted from the Nov 22 local copies), the
# script aborts with a clear message and writes NOTHING.
# Each edited file is backed up to <file>.bak_emoji_nov22 first.
# After the patch: systemctl restart bot.service (and verify one process).
#
# What it fixes (user report 2026-11-22): in the dip test (/testdip) NO emoji
# appears at all, neither premium (custom) nor non-premium (standard). The
# /testdip 5 output on the channel was the plain fallback caption with zero
# emojis. The rich caption itself builds fine (verified: build_dip_caption
# with the real pe()/fmt_mc()/link helpers produces 5 valid <tg-emoji>
# entities), but Telegram rejects it on BOTH the userbot path and the Bot API
# path, so the plain fallback is what gets sent. The plain fallback had NO
# emojis at all, so the output showed none of any kind.
# This patch:
#  1) Puts STANDARD Unicode emojis into BOTH plain fallback captions, so the
#     output always shows emojis even when the premium custom ones fail:
#     diamond 💠 before the title, crystal ball 🔮 before the entry MC,
#     green arrow ➡️ as the teer, megaphone 📣 before Post Link, link 🔗
#     before Dexscreener. Matches the user's desired-output image.
#  2) Fixes the logging so a rich-caption rejection IS captured in the
#     journal. The old logger.warning("testdip rich rejected") never showed
#     up in journalctl (the shared `logger` name is not guaranteed to resolve
#     in every module, and the call was wrapped in a silent try/except).
#     The new helper uses logging.getLogger("dip").error(...) directly at
#     ERROR level, which always reaches the journal. Grep: "dip rich rejected".
#     It logs in every place a rich send is attempted and falls back,
#     including the userbot failure branch (which previously set err silently).
#  3) Does NOT change the emoji IDs (the user's confirmed IDs), the titles,
#     the template structure, the DM-only setting, /testdip's channel target,
#     or any other feature. No public command.
import os
import re
import shutil
import sys

MARKER = "DIP_EMOJI_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BACKUP_SUFFIX = ".bak_emoji_nov22"


class AnchorError(Exception):
    pass


# ─── Shared helper (identical body in both files; the modules share one
# namespace, so the second definition just rebinds the same function) ───────
LOG_HELPER = r'''def _dip_log_rich_rejected(err, where, extra=""):
    # DIP_EMOJI_NOV22: robust error log for a rejected rich (premium-emoji)
    # caption. Uses logging.getLogger("dip") directly at ERROR level, so the
    # exact Telegram error always reaches the journal (grep "dip rich rejected"),
    # even if the shared `logger` name does not resolve in this module.
    try:
        import logging
        msg = "dip rich rejected [%s]: %s" % (where, err)
        if extra:
            msg = msg + " | " + str(extra)
        logging.getLogger("dip").error(msg)
    except Exception:
        pass


'''

# ─── commands.py: plain fallback caption with standard emojis ───────────────
# (replaces the 4 lines of the lines-list in _dip_plain_caption; each is a
# single-line replacement anchored on a unique substring)
CMDS_PLAIN_TITLE_OLD = '    lines = [title, "",'
CMDS_PLAIN_TITLE_NEW = '    lines = [f"💠 {title}", "",'
CMDS_PLAIN_MC_OLD = '             f"{_dip_fmt_plain(entry_mc)} to {_dip_fmt_plain(cur_mc)}", ""'
CMDS_PLAIN_MC_NEW = '             f"🔮 {_dip_fmt_plain(entry_mc)} ➡️ {_dip_fmt_plain(cur_mc)}", ""]'
CMDS_PLAIN_POST_OLD = '        lines.append(f"Post Link: {post_url}")'
CMDS_PLAIN_POST_NEW = '        lines.append(f"📣 Post Link: {post_url}")'
CMDS_PLAIN_DEX_OLD = '        lines.append(f"Dexscreener: {dex_url}")'
CMDS_PLAIN_DEX_NEW = '        lines.append(f"🔗 Dexscreener: {dex_url}")'

# ─── commands.py: new _testdip_send_text (robust logging) ───────────────────
CMDS_SEND_TEXT = r'''async def _testdip_send_text(bot, rich_text, plain_text):
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
                           ("userbot: %s" % ub_err) if ub_err is not None else "")
    try:
        if userbot_client:
            try:
                await asyncio.wait_for(
                    _userbot_send_with_premium_emoji(TARGET_CHANNEL, plain_text),
                    timeout=USERBOT_SEND_TIMEOUT_SECONDS)
                return True
            except Exception:
                pass
        await bot.send_message(chat_id=TARGET_CHANNEL, text=plain_text,
                               disable_web_page_preview=True)
        return True
    except Exception:
        return False


'''

# ─── commands.py: new _testdip_send_media (robust logging + emoji ids) ──────
CMDS_SEND_MEDIA = r'''async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids):
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
                           ("userbot: %s | emoji_ids: %s" % (ub_err, emoji_ids)) if ub_err is not None else ("emoji_ids: %s" % (emoji_ids,)))
    try:
        if ftype == "photo":
            await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=plain_caption)
        elif ftype == "gif":
            await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=plain_caption)
        else:
            await bot.send_video(TARGET_CHANNEL, video=fid, caption=plain_caption)
        return True
    except Exception:
        return False


@owner_only
'''

# ─── x_alert.py: plain fallback caption (DM) with standard emojis ───────────
XA_PLAIN_TITLE_OLD = '    lines = [title, "",'
XA_PLAIN_TITLE_NEW = '    lines = [f"💠 {title}", "",'
XA_PLAIN_MC_OLD = '             f"{_dip_fmt_plain_dm(entry_mc)} to {_dip_fmt_plain_dm(cur_mc)}", ""'
XA_PLAIN_MC_NEW = '             f"🔮 {_dip_fmt_plain_dm(entry_mc)} ➡️ {_dip_fmt_plain_dm(cur_mc)}", ""]'
XA_PLAIN_POST_OLD = '        lines.append(f"Post Link: {post_url}")'
XA_PLAIN_POST_NEW = '        lines.append(f"📣 Post Link: {post_url}")'
XA_PLAIN_DEX_OLD = '        lines.append(f"Dexscreener: {dex_url}")'
XA_PLAIN_DEX_NEW = '        lines.append(f"🔗 Dexscreener: {dex_url}")'

# ─── x_alert.py: logging replacements (single lines) ─────────────────────────
XA_DM_LOG_OLD = '            logger.warning(f"dip DM rich send failed {x_val}x {call_key} -> {uid}: {e}")'
XA_DM_LOG_NEW = '            _dip_log_rich_rejected(e, "dip-dm", f"{x_val}x {call_key} -> {uid}")'
XA_UB_LOG_OLD = '            logger.warning(f"dip alert userbot send failed {x_val}x {call_key}: {e}")'
XA_UB_LOG_NEW = '            _dip_log_rich_rejected(e, "dip-alert-userbot", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")'
XA_BOT_LOG_OLD = '            logger.warning(f"dip alert bot send failed {x_val}x {call_key}: {e}")'
XA_BOT_LOG_NEW = '            _dip_log_rich_rejected(e, "dip-alert-botapi", f"{x_val}x {call_key} | emoji_ids: {emoji_ids}")'


# ─── Edit application ─────────────────────────────────────────────────────────
def _find_line(lines, sub, fname, desc):
    hits = [i for i, ln in enumerate(lines) if sub in ln]
    if len(hits) != 1:
        raise AnchorError(f"{fname}: anchor {desc} ({sub!r}) found {len(hits)}x, need exactly 1")
    return hits[0]


def _insert_after(lines, idx, block):
    return lines[:idx + 1] + block.splitlines(keepends=True) + lines[idx + 1:]


def _insert_before(lines, idx, block):
    return lines[:idx] + block.splitlines(keepends=True) + lines[idx:]


def _replace_line(lines, sub, new_text, fname, desc):
    i = _find_line(lines, sub, fname, desc)
    nl = "\n" if lines[i].endswith("\n") else ""
    lines = list(lines)
    lines[i] = new_text + nl
    return lines


def _replace_block(lines, start_sub, end_sub, new_block, fname, desc):
    # Replace lines[start:end] (end line NOT included) with new_block.
    s_hits = [i for i, ln in enumerate(lines) if start_sub in ln]
    if len(s_hits) != 1:
        raise AnchorError(f"{fname}: start anchor {desc} ({start_sub!r}) found {len(s_hits)}x, need exactly 1")
    s = s_hits[0]
    e_hits = [i for i, ln in enumerate(lines) if i > s and end_sub in ln]
    if len(e_hits) != 1:
        raise AnchorError(f"{fname}: end anchor {desc} ({end_sub!r}) found {len(e_hits)}x after start, need exactly 1")
    e = e_hits[0]
    return lines[:s] + new_block.splitlines(keepends=True) + lines[e:]


def _edit_cmds_plain(lines):
    lines = _replace_line(lines, CMDS_PLAIN_TITLE_OLD, CMDS_PLAIN_TITLE_NEW,
                          "commands.py", "_dip_plain_caption title line")
    lines = _replace_line(lines, CMDS_PLAIN_MC_OLD, CMDS_PLAIN_MC_NEW,
                          "commands.py", "_dip_plain_caption MC line")
    lines = _replace_line(lines, CMDS_PLAIN_POST_OLD, CMDS_PLAIN_POST_NEW,
                          "commands.py", "_dip_plain_caption Post Link line")
    lines = _replace_line(lines, CMDS_PLAIN_DEX_OLD, CMDS_PLAIN_DEX_NEW,
                          "commands.py", "_dip_plain_caption Dexscreener line")
    return lines


def _edit_cmds_log_helper(lines):
    i = _find_line(lines, "async def _testdip_send_text(", "commands.py",
                   "_testdip_send_text def")
    return _insert_before(lines, i, LOG_HELPER)


def _edit_cmds_send_text(lines):
    return _replace_block(lines, "async def _testdip_send_text(",
                          "async def _testdip_send_media(", CMDS_SEND_TEXT,
                          "commands.py", "_testdip_send_text block")


def _edit_cmds_send_media(lines):
    # End anchor is the cmd_testdip def; the new block re-adds the
    # @owner_only decorator line it replaces, so the decorator survives.
    return _replace_block(lines, "async def _testdip_send_media(",
                          "async def cmd_testdip(", CMDS_SEND_MEDIA,
                          "commands.py", "_testdip_send_media block")


def _edit_xa_plain(lines):
    lines = _replace_line(lines, XA_PLAIN_TITLE_OLD, XA_PLAIN_TITLE_NEW,
                          "x_alert.py", "_dip_plain_caption_dm title line")
    lines = _replace_line(lines, XA_PLAIN_MC_OLD, XA_PLAIN_MC_NEW,
                          "x_alert.py", "_dip_plain_caption_dm MC line")
    lines = _replace_line(lines, XA_PLAIN_POST_OLD, XA_PLAIN_POST_NEW,
                          "x_alert.py", "_dip_plain_caption_dm Post Link line")
    lines = _replace_line(lines, XA_PLAIN_DEX_OLD, XA_PLAIN_DEX_NEW,
                          "x_alert.py", "_dip_plain_caption_dm Dexscreener line")
    return lines


def _edit_xa_log_helper(lines):
    i = _find_line(lines, "def _dip_plain_caption_dm(", "x_alert.py",
                   "_dip_plain_caption_dm def")
    return _insert_before(lines, i, LOG_HELPER)


def _edit_xa_dm_log(lines):
    return _replace_line(lines, XA_DM_LOG_OLD, XA_DM_LOG_NEW,
                         "x_alert.py", "_dip_send_dm rich-fail log")


def _edit_xa_alert_logs(lines):
    lines = _replace_line(lines, XA_UB_LOG_OLD, XA_UB_LOG_NEW,
                          "x_alert.py", "send_dip_alert userbot-fail log")
    lines = _replace_line(lines, XA_BOT_LOG_OLD, XA_BOT_LOG_NEW,
                          "x_alert.py", "send_dip_alert bot-fail log")
    return lines


EDITS = {
    "commands.py": [_edit_cmds_plain, _edit_cmds_log_helper,
                    _edit_cmds_send_text, _edit_cmds_send_media],
    "x_alert.py": [_edit_xa_plain, _edit_xa_log_helper,
                   _edit_xa_dm_log, _edit_xa_alert_logs],
}


def main():
    print(f"DIP_EMOJI_NOV22 patch - target dir: {BOT_DIR}")

    # Phase 1: validate every anchor on in-memory copies (write nothing yet).
    new_contents = {}
    skipped = []

    for fname, fns in EDITS.items():
        path = os.path.join(BOT_DIR, fname)
        if not os.path.exists(path):
            print(f"ABORT: {path} not found. Run this script in /opt/bot.")
            sys.exit(1)

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        if MARKER in text:
            print(f"SKIP {fname}: already patched ({MARKER} present).")
            skipped.append(fname)
            continue

        lines = text.splitlines(keepends=True)
        try:
            for fn in fns:
                lines = fn(lines)
        except AnchorError as e:
            print(f"ABORT: anchor missing - {e}")
            print("Nothing was written. Check the live file and re-run after fixing.")
            sys.exit(1)

        new_contents[fname] = "".join(lines)

    # Phase 2: backup + write.
    for fname, text in new_contents.items():
        path = os.path.join(BOT_DIR, fname)
        bak = path + BACKUP_SUFFIX
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
            print(f"Backup: {bak}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Patched: {fname}")

    print("DONE. Now restart the bot: systemctl restart bot.service")
    print("Then verify: /testdip 5 in the bot DM, and check the main channel")
    print("for emojis. If the preview is still plain, read the exact error:")
    print('journalctl -u bot.service --since "10 minutes ago" --no-pager | grep -i "dip rich rejected"')
    if skipped:
        print(f"Skipped (already patched): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
