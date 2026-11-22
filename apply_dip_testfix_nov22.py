#!/usr/bin/env python3
# apply_dip_testfix_nov22.py - fix for /testdip giving NO reply (wizu bot).
# VPS-ONLY one-time script. Run it ONCE on the Contabo VPS as root:
#   cd /opt/bot && python3 apply_dip_testfix_nov22.py
# It ONLY replaces cmd_testdip in commands.py (plus 4 small helpers placed
# right before it). Nothing else is touched.
# Why: the original cmd_testdip built the rich caption BEFORE the first
# reply, with no try/except around it, and its media-missing / media-fail
# fallback replies also sent the same rich caption with parse_mode="HTML"
# and no guard. So (a) any exception while building the caption meant
# ZERO replies (exactly the reported symptom), and (b) if Telegram rejects
# the caption (e.g. an invalid custom emoji ID), the fallback itself raises
# and the preview never arrives. This fix wraps everything, sends the
# header as plain text, and retries any rejected rich caption as plain
# text, so /testdip always replies.
# Idempotent: commands.py already containing DIP_TESTFIX_NOV22 is skipped.
# Fail-safe: every anchor is checked BEFORE anything is written; if any
# anchor is missing, the script aborts with a clear message and writes
# NOTHING. The edited file is backed up to commands.py.bak_testfix_nov22.
import os
import sys
import shutil

MARKER = "DIP_TESTFIX_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BACKUP_SUFFIX = ".bak_testfix_nov22"


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
    return "\\n".join(lines)


async def _testdip_reply_text(update, rich_text, plain_text):
    # DIP_TESTFIX_NOV22: rich HTML first; if Telegram rejects it, plain text.
    try:
        await update.message.reply_text(rich_text, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(plain_text)


async def _testdip_reply_media(update, ftype, fid, rich_caption, plain_caption):
    # DIP_TESTFIX_NOV22: media with rich caption first; on rejection, plain caption.
    async def _send(cap, pm):
        if ftype == "photo":
            await update.message.reply_photo(photo=fid, caption=cap, parse_mode=pm)
        elif ftype == "gif":
            await update.message.reply_animation(animation=fid, caption=cap, parse_mode=pm)
        else:
            await update.message.reply_video(video=fid, caption=cap, parse_mode=pm)
    try:
        await _send(rich_caption, "HTML")
    except Exception:
        await _send(plain_caption, None)


@owner_only
async def cmd_testdip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # DIP_TESTFIX_NOV22: robust testdip. Never silent: any failure replies
    # in plain text, and a rejected rich caption falls back to plain text.
    try:
        await _cmd_testdip_inner(update, context)
    except Exception as e:
        try:
            logger.exception("testdip failed: %s", e)
        except Exception:
            pass
        try:
            await update.message.reply_text(
                f"Testdip error: {e}\\n\\nPreview nahi ban saka. /showdipset se setting check karo.")
        except Exception:
            pass


async def _cmd_testdip_inner(update, context):
    try:
        xv = int(context.args[0]) if context.args else 5
    except (ValueError, IndexError):
        xv = 5
    if xv < 2:
        await update.message.reply_text("X kam se kam 2 hona chahiye.\\nExample: /testdip 5")
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
    # Header: plain text, no parse_mode (cannot fail on HTML).
    await update.message.reply_text(
        f"Dip preview {xv}X - @{channel} ${token} (sirf preview, kuch record nahi hua)")
    if not media:
        rich = None
        if caption:
            rich = (f"<b>Media missing:</b> {xv}X ka dip media set nahi hai "
                    f"(/setdipmedia {xv} se set karo). Text preview:\\n\\n{caption}")
        plain_t = (f"Media missing: {xv}X ka dip media set nahi hai "
                   f"(/setdipmedia {xv} se set karo). Text preview:\\n\\n{plain}")
        if rich:
            await _testdip_reply_text(update, rich, plain_t)
        else:
            await update.message.reply_text(plain_t)
        return
    fid, ftype = media["file_id"], media.get("type", "video")
    try:
        if caption:
            await _testdip_reply_media(update, ftype, fid, caption, plain)
        else:
            await _testdip_reply_media(update, ftype, fid, plain, plain)
    except Exception as e:
        rich = None
        if caption:
            rich = f"Media send fail ho gaya ({e}). Text preview:\\n\\n{caption}"
        plain_t = f"Media send fail ho gaya ({e}). Text preview:\\n\\n{plain}"
        if rich:
            await _testdip_reply_text(update, rich, plain_t)
        else:
            await update.message.reply_text(plain_t)
'''


def _find_line(lines, sub, fname, desc):
    hits = [i for i, ln in enumerate(lines) if sub in ln]
    if len(hits) != 1:
        raise AnchorError(f"{fname}: anchor {desc} ({sub!r}) found {len(hits)}x, need exactly 1")
    return hits[0]


def _edit_cmds_testdip(lines):
    di = _find_line(
        lines,
        "async def cmd_testdip(update: Update, context: ContextTypes.DEFAULT_TYPE):",
        "commands.py", "cmd_testdip def")
    # The @owner_only decorator sits directly above the def; replace from there.
    if lines[di - 1].strip() != "@owner_only":
        raise AnchorError("commands.py: expected '@owner_only' directly above cmd_testdip def")
    start = di - 1
    # End: next top-level item (decorator / def / class at column 0).
    end = None
    for k in range(di + 1, len(lines)):
        ln = lines[k]
        if ln.startswith("@") or ln.startswith("async def ") or ln.startswith("def ") or ln.startswith("class "):
            end = k
            break
    if end is None:
        raise AnchorError("commands.py: no top-level item found after cmd_testdip (cannot bound the function)")
    region = "".join(lines[start:end])
    if "Dip preview" not in region:
        raise AnchorError("commands.py: region after cmd_testdip def does not contain 'Dip preview' (wrong function?)")
    new_block = NEW_CMDS.splitlines(keepends=True)
    return lines[:start] + new_block + lines[end:]


def main():
    print(f"DIP_TESTFIX_NOV22 patch - target dir: {BOT_DIR}")
    path = os.path.join(BOT_DIR, "commands.py")
    if not os.path.exists(path):
        print(f"ABORT: {path} not found. Run this script in /opt/bot.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if MARKER in text:
        print("SKIP commands.py: already patched (DIP_TESTFIX_NOV22 present).")
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
    print("Patched: commands.py (cmd_testdip replaced with robust version)")
    print("DONE. Now restart the bot: systemctl restart bot.service")
    print("Then verify: /testdip 5 in the bot DM (preview must arrive).")


if __name__ == "__main__":
    main()
