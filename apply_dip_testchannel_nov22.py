#!/usr/bin/env python3
# apply_dip_testchannel_nov22.py - /testdip posts the preview to the MAIN
# channel instead of the owner DM (wizu bot).
# VPS-ONLY one-time script. Run it ONCE on the Contabo VPS as root:
#   cd /opt/bot && python3 apply_dip_testchannel_nov22.py
# It ONLY replaces the testdip block in commands.py (the helpers + cmd_testdip
# + _cmd_testdip_inner that the DIP_TESTFIX_NOV22 patch put there). Nothing
# else is touched.
# Why: the owner wants the test alert on the main channel, exactly like a
# real dip alert (same channel the bot posts real dip alerts to, TARGET_CHANNEL
# i.e. @WizardScan), so he can see it the way channel members will. The owner
# DM only gets a short plain-text confirmation.
# What changes (send target only):
#   - the preview (media + caption, or the text caption when no media is set)
#     goes to TARGET_CHANNEL, userbot-first then Bot API fallback, rich
#     caption first with a plain-text fallback if Telegram rejects it.
#   - the owner DM gets a short plain-text confirmation that the preview was
#     posted to the channel (plus the "media missing" note when no media).
#   - any failure still replies the error in plain text to the owner DM.
# Logging (new requirement): when the rich caption is rejected, the helpers
# log logger.warning("testdip rich rejected: ...") BEFORE the plain fallback,
# so the exact Telegram error lands in the journal and can be read with
# journalctl -u bot.service --since "10 minutes ago" --no-pager | grep -i "testdip rich".
# Also fixed here: the testfix plain caption joined lines with a literal
# backslash-n instead of a real newline (that is the literal backslash-n the
# user saw in the /testdip 90 output). The plain caption now joins with
# chr(10), and the short DM messages are single-line, so no newline escape is
# needed anywhere in the new code.
# Idempotent: commands.py already containing DIP_TESTCHANNEL_NOV22 is skipped.
# Fail-safe: every anchor is checked BEFORE anything is written; if any
# anchor is missing, the script aborts with a clear message and writes
# NOTHING. The edited file is backed up to commands.py.bak_testchannel_nov22.
import os
import sys
import shutil

MARKER = "DIP_TESTCHANNEL_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BACKUP_SUFFIX = ".bak_testchannel_nov22"


class AnchorError(Exception):
    pass


NEW_CMDS = r'''def _dip_fmt_plain(v):
    # DIP_TESTFIX_NOV22: plain MC format, no helpers, cannot raise on numbers.
    try:
        v = float(v or 0)
    except Exception:
        return "N/A"
    if v >= 1000000:
        s = f"{v / 1000000:.2f}"
        return s.rstrip("0").rstrip(".") + "M"
    if v >= 1000:
        s = f"{v / 1000:.1f}"
        return s.rstrip("0").rstrip(".") + "K"
    return f"{v:.0f}"


def _dip_plain_caption(call, x_val, cur_mc):
    # DIP_TESTFIX_NOV22: plain-text dip caption. No HTML, no custom emoji,
    # no pe()/fmt_mc()/link helpers, so Telegram can never reject it.
    # DIP_TESTCHANNEL_NOV22: joins with chr(10) (a real newline). The old
    # version joined with a literal backslash-n, which showed up as text.
    try:
        channel = str(call.get("channel") or "TestChannel")
        ch = (channel[:1].upper() + channel[1:]) if channel else channel
        symbol = str(call.get("symbol") or "TEST").upper()
        chain = str(call.get("chain") or "SOL").upper().replace("BSC", "BNB")
        entry_mc = float(call.get("entry_mc") or 0)
        dip_low = float(call.get("dip_low") or 0)
        cur_mc = float(cur_mc or 0)
        x = int(x_val)
    except Exception:
        return "Dip preview"
    try:
        title = dip_title_for_x(x)
    except Exception:
        title = f"DIP TO PROFIT: {x}X"
    pct = ((cur_mc / dip_low) - 1.0) * 100.0 if dip_low > 0 and cur_mc > 0 else 0.0
    pct_s = f"{pct:.1f}"
    if pct_s.endswith(".0"):
        pct_s = pct_s[:-2]
    ch_at = channel.lstrip("@").strip()
    msg_id = call.get("msg_id")
    if ch_at and msg_id:
        post_url = f"https://t.me/{ch_at}/{msg_id}"
    elif ch_at:
        post_url = f"https://t.me/{ch_at}"
    else:
        post_url = ""
    dexpath = {"SOL": "solana", "ETH": "ethereum", "BNB": "bsc", "BASE": "base",
               "ARC": "arc", "TON": "ton", "RH": "robinhood"}
    ca = str(call.get("ca") or "")
    dex_url = f"https://dexscreener.com/{dexpath.get(chain, 'solana')}/{ca}" if ca else ""
    lines = [title, "",
             f"{ch} picked ${symbol} at the dip. Now up {pct_s}% from the low.",
             "",
             f"{_dip_fmt_plain(entry_mc)} to {_dip_fmt_plain(cur_mc)}", ""]
    if post_url:
        lines.append(f"Post Link: {post_url}")
    if dex_url:
        lines.append(f"Dexscreener: {dex_url}")
    return chr(10).join(lines)


async def _testdip_send_text(bot, rich_text, plain_text):
    # DIP_TESTCHANNEL_NOV22: text preview to TARGET_CHANNEL, userbot-first,
    # Bot API fallback; rich first, plain on rejection. Returns True if posted.
    # A rich rejection is logged before the plain fallback, so the exact
    # Telegram error is in the journal (grep "testdip rich").
    import asyncio
    err = None
    try:
        if userbot_client:
            try:
                await asyncio.wait_for(
                    _userbot_send_with_premium_emoji(TARGET_CHANNEL, rich_text),
                    timeout=USERBOT_SEND_TIMEOUT_SECONDS)
                return True
            except Exception as e:
                err = e
        await bot.send_message(chat_id=TARGET_CHANNEL, text=rich_text,
                               parse_mode="HTML", disable_web_page_preview=True)
        return True
    except Exception as e:
        err = e
    try:
        logger.warning("testdip rich rejected: %s", err)
    except Exception:
        pass
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


async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids):
    # DIP_TESTCHANNEL_NOV22: media + caption to TARGET_CHANNEL, userbot-first
    # (with the dip emoji ids, same as real dip alerts), Bot API fallback;
    # plain caption on rejection. Returns True if posted.
    # A rich rejection is logged before the plain fallback, so the exact
    # Telegram error is in the journal (grep "testdip rich").
    import asyncio
    err = None
    if userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               rich_caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
            if msg is not None:
                return True
            err = Exception("userbot send returned None")
        except Exception as e:
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
    try:
        logger.warning("testdip rich rejected: %s", err)
    except Exception:
        pass
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
async def cmd_testdip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # DIP_TESTCHANNEL_NOV22: test preview posts to TARGET_CHANNEL now.
    # Never silent: any failure replies in plain text to the owner DM.
    try:
        await _cmd_testdip_inner(update, context)
    except Exception as e:
        try:
            logger.exception("testdip failed: %s", e)
        except Exception:
            pass
        try:
            await update.message.reply_text(
                f"Testdip error: {e}. Preview nahi ban saka. /showdipset se setting check karo.")
        except Exception:
            pass


async def _cmd_testdip_inner(update, context):
    try:
        xv = int(context.args[0]) if context.args else 5
    except (ValueError, IndexError):
        xv = 5
    if xv < 2:
        await update.message.reply_text("X kam se kam 2 hona chahiye. Example: /testdip 5")
        return
    args = list(context.args[1:] if len(context.args) > 1 else [])
    channel = args[0].lstrip("@") if args else "TestChannel"
    token = args[1].upper() if len(args) > 1 else "TEST"
    entry_mc = 74900.0
    cur_mc = 264700.0
    dip_low = cur_mc / xv if xv > 0 else cur_mc
    fake_call = {"channel": channel, "symbol": token, "chain": "SOL",
                 "entry_mc": entry_mc, "dip_low": dip_low,
                 "ca": "TestCA123", "msg_id": 1}
    try:
        caption = build_dip_caption(fake_call, xv, cur_mc, include_promo=True)
    except Exception:
        caption = None
    plain = _dip_plain_caption(fake_call, xv, cur_mc)
    media = dip_media_for(xv)
    bot = context.bot
    if not media:
        # No media: the text caption itself is the preview on the channel;
        # the admin "media missing" note stays in the DM only.
        rich = caption if caption else plain
        ok = await _testdip_send_text(bot, rich, plain)
        if ok:
            await update.message.reply_text(
                f"Dip preview {xv}X channel par post kar diya hai ({TARGET_CHANNEL}). "
                f"Media missing: {xv}X ka dip media set nahi hai (/setdipmedia {xv} se set karo). "
                f"Sirf preview, kuch record nahi hua.")
        else:
            await update.message.reply_text(
                "Testdip error: channel par post nahi ho saka. /showdipset se setting check karo.")
        return
    fid, ftype = media["file_id"], media.get("type", "video")
    chain = str(fake_call.get("chain") or "SOL").upper().replace("BSC", "BNB")
    emoji_ids = [DIP_CHAIN_EMOJIS.get(chain, DIP_CHAIN_EMOJIS["SOL"]),
                 DIP_CRYSTAL_EMOJI_ID, DIP_TEER_EMOJI_ID,
                 DIP_POSTLINK_EMOJI_ID, DIP_DEX_EMOJI_ID]
    rich_cap = caption if caption else plain
    ok = await _testdip_send_media(bot, ftype, fid, rich_cap, plain, emoji_ids)
    if ok:
        await update.message.reply_text(
            f"Dip preview {xv}X channel par post kar diya hai ({TARGET_CHANNEL}). "
            f"Sirf preview, kuch record nahi hua.")
    else:
        await update.message.reply_text(
            "Testdip error: channel par post nahi ho saka. /showdipset se setting check karo.")
'''


def _find_line(lines, sub, fname, desc):
    hits = [i for i, ln in enumerate(lines) if sub in ln]
    if len(hits) != 1:
        raise AnchorError(f"{fname}: anchor {desc} ({sub!r}) found {len(hits)}x, need exactly 1")
    return hits[0]


def _edit_cmds_testdip(lines):
    si = _find_line(lines, "def _dip_fmt_plain(v):", "commands.py", "_dip_fmt_plain def")
    ii = _find_line(lines, "async def _cmd_testdip_inner(update, context):",
                    "commands.py", "_cmd_testdip_inner def")
    if ii <= si:
        raise AnchorError("commands.py: _cmd_testdip_inner must come after _dip_fmt_plain")
    # End: next top-level item after _cmd_testdip_inner (decorator / def / class).
    end = len(lines)
    for k in range(ii + 1, len(lines)):
        ln = lines[k]
        if ln.startswith("@") or ln.startswith("async def ") or ln.startswith("def ") or ln.startswith("class "):
            end = k
            break
    region = "".join(lines[si:end])
    if "DIP_TESTFIX_NOV22" not in region:
        raise AnchorError("commands.py: region does not contain DIP_TESTFIX_NOV22 (not the testfix version?)")
    if "cmd_testdip" not in region:
        raise AnchorError("commands.py: region does not contain cmd_testdip (wrong function?)")
    if "DIP_TESTCHANNEL_NOV22" in region:
        raise AnchorError("commands.py: region already contains DIP_TESTCHANNEL_NOV22 (already patched?)")
    new_block = NEW_CMDS.splitlines(keepends=True)
    return lines[:si] + new_block + lines[end:]


def main():
    print(f"DIP_TESTCHANNEL_NOV22 patch - target dir: {BOT_DIR}")
    path = os.path.join(BOT_DIR, "commands.py")
    if not os.path.exists(path):
        print(f"ABORT: {path} not found. Run this script in /opt/bot.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if MARKER in text:
        print("SKIP commands.py: already patched (DIP_TESTCHANNEL_NOV22 present).")
        return
    lines = text.splitlines(keepends=True)
    try:
        lines = _edit_cmds_testdip(lines)
    except AnchorError as e:
        print(f"ABORT: anchor missing - {e}")
        print("Nothing was written. Check the live file and re-run after fixing.")
        sys.exit(1)
    bak = path + BACKUP_SUFFIX
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"Backup: {bak}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print("Patched: commands.py (cmd_testdip now posts the preview to TARGET_CHANNEL)")
    print("DONE. Now restart the bot: systemctl restart bot.service")
    print("Then verify: /testdip 5 in the bot DM, and check the preview on the main channel.")


if __name__ == "__main__":
    main()
