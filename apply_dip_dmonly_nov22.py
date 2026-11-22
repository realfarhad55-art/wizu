#!/usr/bin/env python3
# apply_dip_dmonly_nov22.py - DIP PROFIT DM-only delivery for wizu (WizardScan bot).
# VPS-ONLY one-time script. Run it ONCE on the Contabo VPS as root:
#   cd /opt/bot && python3 apply_dip_dmonly_nov22.py
# It edits x_alert.py, commands.py, runtime.py in /opt/bot
# (pass another dir as argv[1] to target a copy instead).
# Idempotent: files already containing DIP_DM_ONLY_NOV22 are skipped.
# Fail-safe: every anchor is checked BEFORE anything is written; if any
# anchor is missing (live code drifted), the script aborts with a clear
# message and writes NOTHING.
# Each edited file is backed up to <file>.bak_dmonly_nov22 first.
# What it does: real dip X alerts go ONLY to DMs (KOL owner + channel
# subscribers + global subscribers), NEVER posted on the channel.
# Owner-only commands: /dipdmon (DM-only on, default), /dipdmoff
# (channel mode). No public command is added.
# After the patch: systemctl restart bot.service (and verify one process).
import os
import re
import shutil
import sys

MARKER = "DIP_DM_ONLY_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BACKUP_SUFFIX = ".bak_dmonly_nov22"


class AnchorError(Exception):
    pass


# --- Inserted code blocks (raw strings: backslash-n stays literal) ---

XALERT_HELPERS = r'''def dip_dm_only():
    # DIP_DM_ONLY_NOV22: real dip alerts go to DMs only, never the channel.
    try:
        return bool(_dip_cfg().get("dip_dm_only", True))
    except Exception:
        return True


def _dip_dm_recipients(call):
    # DIP_DM_ONLY_NOV22: who gets a dip alert in DM. KOL owner first, then
    # channel-specific subscribers, then legacy global subscribers.
    # Deduplicated (owner counted once). Linked channels and the KOL's own
    # channel are NOT recipients (no channel post, no forward).
    try:
        channel_key = str(call.get("channel") or "").lstrip("@").lower()
        owner_id = None
        try:
            owner_id = load_kol_owners().get(channel_key)
            owner_id = int(owner_id) if owner_id is not None else None
        except (TypeError, ValueError):
            owner_id = None
        try:
            specific = load_channel_subs().get(channel_key, []) or []
        except Exception:
            specific = []
        try:
            global_subs = load_subscriptions() or []
        except Exception:
            global_subs = []
        seen = set()
        out = []
        if owner_id:
            seen.add(owner_id)
            out.append(owner_id)
        for uid in list(specific) + list(global_subs):
            try:
                uid = int(uid)
            except (TypeError, ValueError):
                continue
            if uid in seen:
                continue
            seen.add(uid)
            out.append(uid)
        return out
    except Exception:
        return []


def _dip_fmt_plain_dm(v):
    # DIP_DM_ONLY_NOV22: plain MC format, no helpers, cannot raise.
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


def _dip_plain_caption_dm(call, x_val, cur_mc):
    # DIP_DM_ONLY_NOV22: plain-text dip caption for the DM fallback. No
    # HTML, no custom emoji, no pe()/fmt_mc()/link helpers, so Telegram
    # can never reject it. Joins with chr(10) (a real newline).
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
        return "Dip alert"
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
             f"{_dip_fmt_plain_dm(entry_mc)} to {_dip_fmt_plain_dm(cur_mc)}", ""]
    if post_url:
        lines.append(f"Post Link: {post_url}")
    if dex_url:
        lines.append(f"Dexscreener: {dex_url}")
    return chr(10).join(lines)


async def _dip_send_dm(bot, call_key, call, x_val, cur_mc, fid, ftype,
                       caption, promo_separate):
    # DIP_DM_ONLY_NOV22: send a FRESH copy (media + caption) straight to
    # each DM recipient via the Bot API. Never posts to the channel, never
    # forwards. Rich caption first; on any Telegram rejection, retry with
    # the plain-text caption. One failing recipient never blocks the rest.
    recipients = _dip_dm_recipients(call)
    if not recipients:
        logger.warning(
            f"Dip {x_val}x {call_key}: DM-only on but no DM recipients "
            f"(no KOL owner, no subscribers) - alert skipped, NOT posted "
            f"to the channel")
        return True
    plain_caption = _dip_plain_caption_dm(call, x_val, cur_mc)
    promo_html = dip_promo_html() if promo_separate else ""
    sent_any = False
    for uid in recipients:
        ok = False
        try:
            if ftype == "photo":
                await bot.send_photo(uid, photo=fid, caption=caption,
                                     parse_mode="HTML")
            elif ftype == "gif":
                await bot.send_animation(uid, animation=fid, caption=caption,
                                         parse_mode="HTML")
            else:
                await bot.send_video(uid, video=fid, caption=caption,
                                     parse_mode="HTML")
            ok = True
        except Exception as e:
            logger.warning(f"dip DM rich send failed {x_val}x {call_key} -> {uid}: {e}")
            try:
                if ftype == "photo":
                    await bot.send_photo(uid, photo=fid, caption=plain_caption)
                elif ftype == "gif":
                    await bot.send_animation(uid, animation=fid, caption=plain_caption)
                else:
                    await bot.send_video(uid, video=fid, caption=plain_caption)
                ok = True
            except Exception as e2:
                logger.warning(f"dip DM plain send failed {x_val}x {call_key} -> {uid}: {e2}")
        if ok:
            sent_any = True
            if promo_html:
                try:
                    await bot.send_message(chat_id=uid, text=promo_html,
                                           parse_mode="HTML",
                                           disable_web_page_preview=True)
                except Exception as e:
                    logger.warning(f"dip DM promo failed {x_val}x {call_key} -> {uid}: {e}")
        await asyncio.sleep(0.1)
    if sent_any:
        logger.info(f"Dip alert DM-sent: {x_val}x {call_key} -> {len(recipients)} recipient(s)")
        return True
    logger.warning(f"Dip {x_val}x {call_key}: DM send failed for all recipients - will retry")
    return False


'''

XALERT_DM_BRANCH = r'''    if dip_dm_only():
        ok = await _dip_send_dm(bot, call_key, call, x_val, cur_mc,
                                fid, ftype, caption, promo_separate)
        if ok:
            _dip_clear_pending(call_key, x_val)
            logger.info(f"Dip alert DM-sent: {x_val}x {call_key}")
            return True
        _dip_add_pending(call_key, x_val, cur_mc)
        return False
'''


CMDS_PANEL_LINE = r'''        "/dipdmon · /dipdmoff - dip alerts DM-only on/off (default DM-only, channel par nahi)\n"
'''

CMDS_TUTORIALS = r'''        ('dipdmon', 'Dip alerts sirf DM me bhejo (DM-only on). Channel par nahi aayengi.\nUsage: /dipdmon'),
        ('dipdmoff', 'Dip alerts channel par post karo (DM-only off).\nUsage: /dipdmoff'),
'''

CMDS_FUNCS = r'''

# DIP_DM_ONLY_NOV22: owner-only /dipdmon and /dipdmoff commands.
@owner_only
async def cmd_dipdmon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg_set("dip_dm_only", True)
    await update.message.reply_text("✅ Dip alerts ab sirf DM me aayengi. Channel par nahi post hongi.")


@owner_only
async def cmd_dipdmoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg_set("dip_dm_only", False)
    await update.message.reply_text("✅ Dip alerts ab channel par post hongi. DM me nahi jayengi.")


'''

CMDS_SHOWDIPSET_CFG = r'''    dm_only = c.get("dip_dm_only", True)
'''

CMDS_SHOWDIPSET_LINE = r'''        f"DM delivery: <b>{'DM only' if dm_only else 'Channel'}</b> (/dipdmon · /dipdmoff)\n"
'''

RUNTIME_HANDLERS = r'''    # DIP_DM_ONLY_NOV22: owner-only /dipdmon and /dipdmoff handlers.
    app.add_handler(CommandHandler("dipdmon",        cmd_dipdmon))
    app.add_handler(CommandHandler("dipdmoff",       cmd_dipdmoff))
'''


# --- Edit application ---

def _find_line(lines, sub, fname, desc):
    hits = [i for i, ln in enumerate(lines) if sub in ln]
    if len(hits) != 1:
        raise AnchorError(f"{fname}: anchor {desc} ({sub!r}) found {len(hits)}x, need exactly 1")
    return hits[0]


def _insert_after(lines, idx, block):
    return lines[:idx + 1] + block.splitlines(keepends=True) + lines[idx + 1:]


def _insert_before(lines, idx, block):
    return lines[:idx] + block.splitlines(keepends=True) + lines[idx:]


def _edit_xalert_helpers(lines):
    i = _find_line(lines, "async def send_dip_alert(bot, call_key, call, x_val, cur_mc):",
                   "x_alert.py", "send_dip_alert def")
    return _insert_before(lines, i, XALERT_HELPERS)


def _edit_xalert_branch(lines):
    i = _find_line(lines, '    fid, ftype = media["file_id"], media.get("type", "video")',
                   "x_alert.py", "fid/ftype line in send_dip_alert")
    return _insert_after(lines, i, XALERT_DM_BRANCH)


def _edit_cmds_panel(lines):
    i = _find_line(lines, "/dipon · /dipoff - dip alerts on/off (default on)",
                   "commands.py", "dipon/dipoff panel line")
    return _insert_after(lines, i, CMDS_PANEL_LINE)


def _edit_cmds_tutorials(lines):
    i = _find_line(lines, "('dipoff', 'Dip alerts off karo",
                   "commands.py", "dipoff tutorial entry")
    return _insert_after(lines, i, CMDS_TUTORIALS)


def _edit_cmds_showdipset_cfg(lines):
    i = _find_line(lines, '    enabled = c.get("dip_enabled", True)',
                   "commands.py", "enabled line in cmd_showdipset")
    return _insert_after(lines, i, CMDS_SHOWDIPSET_CFG)


def _edit_cmds_showdipset_line(lines):
    i = _find_line(lines, "Promo link: <b>{'set hai' if promo_txt else 'set nahi'}</b>",
                   "commands.py", "Promo link line in cmd_showdipset")
    return _insert_after(lines, i, CMDS_SHOWDIPSET_LINE)


def _edit_cmds_funcs(lines):
    i = _find_line(lines, "async def cmd_showdipset",
                   "commands.py", "cmd_showdipset def")
    j = i
    while j > 0 and (lines[j - 1].strip() == "" or lines[j - 1].lstrip().startswith("@")):
        j -= 1
    return _insert_before(lines, j, CMDS_FUNCS)


def _edit_runtime_handlers(lines):
    i = _find_line(lines, 'CommandHandler("dipoff",',
                   "runtime.py", "dipoff handler")
    return _insert_after(lines, i, RUNTIME_HANDLERS)


EDITS = {
    "x_alert.py": [_edit_xalert_helpers, _edit_xalert_branch],
    "commands.py": [_edit_cmds_panel, _edit_cmds_tutorials,
                    _edit_cmds_showdipset_cfg, _edit_cmds_showdipset_line,
                    _edit_cmds_funcs],
    "runtime.py": [_edit_runtime_handlers],
}


def main():
    print(f"DIP_DM_ONLY_NOV22 patch - target dir: {BOT_DIR}")

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
    print("Then verify: /showdipset in the bot DM (DM delivery: DM only).")
    if skipped:
        print(f"Skipped (already patched): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
