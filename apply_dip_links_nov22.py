#!/usr/bin/env python3
"""DIP_LINKS_NOV22 - dip alert fallback links as real hyperlinks.

Problem: the /testdip 5 preview shows the links as OPEN URLs in plain
text ("Post Link: https://t.me/..." / "Dexscreener: https://...").
The user wants "Post Link" and "Dexscreener" THEMSELVES to be the
clickable links (URL hidden behind the label), exactly like the normal
X alert and like the rich dip caption.

Root cause: the rich caption (build_dip_caption) already uses
<a href="URL">label</a>, but the two PLAIN fallback captions only
built "label: URL" text and were sent with NO parse_mode, so the URLs
showed openly. This patch:
  1. Changes BOTH plain fallback captions (_dip_plain_caption in
     commands.py, _dip_plain_caption_dm in x_alert.py) so the links are
     real <a href> hyperlinks, joined on one line with three spaces,
     exactly like the rich caption. Standard Unicode emojis kept.
  2. Sends the fallback with parse_mode="HTML" in all three fallback
     sites (_testdip_send_text, _testdip_send_media, _dip_send_dm).
     The userbot paths already parse HTML (tl_html_parse /
     parse_mode="html"), so nothing changes there.
  3. Adds a last-resort no-parse_mode send (stripped "label: URL"
     text via _dip_strip_links) ONLY if the HTML fallback itself is
     rejected, logged with tag "html-fallback" (grep it in the journal).

VPS-only one-time script. Idempotent (marker DIP_LINKS_NOV22).
Backups: <file>.bak_links_nov22. Fail-safe: validates ALL anchors
before writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_dip_links_nov22.py
"""

import os
import sys

MARKER = "DIP_LINKS_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_links_nov22"


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

CMDS_COMMENT_OLD = r"""def _dip_plain_caption(call, x_val, cur_mc):
    # DIP_TESTFIX_NOV22: plain-text dip caption. No HTML, no custom emoji,
    # no pe()/fmt_mc()/link helpers, so Telegram can never reject it."""

CMDS_COMMENT_NEW = r"""def _dip_plain_caption(call, x_val, cur_mc):
    # DIP_TESTFIX_NOV22: dip caption for the fallback. HTML links only
    # (<a href>), no custom emoji, no pe()/fmt_mc()/link helpers, so
    # Telegram can never reject it for a bad custom emoji id.
    # DIP_LINKS_NOV22: links are real <a href> hyperlinks now (URL hidden
    # behind the label, like the normal X alert), sent with parse_mode HTML."""

CMDS_LINKS_OLD = r"""    if post_url:
        lines.append(f"📣 Post Link: {post_url}")
    if dex_url:
        lines.append(f"🔗 Dexscreener: {dex_url}")
    return chr(10).join(lines)"""

CMDS_LINKS_NEW = r"""    links = []
    if post_url:
        links.append(f'📣 <a href="{post_url}">Post Link</a>')
    if dex_url:
        links.append(f'🔗 <a href="{dex_url}">Dexscreener</a>')
    if links:
        lines.append("   ".join(links))
    return chr(10).join(lines)"""

STRIP_HELPER = r"""def _dip_strip_links(text):
    # DIP_LINKS_NOV22: last-resort plain text. Turns <a href="URL">label</a>
    # back into "label: URL" so a no-parse_mode send is still readable.
    try:
        import re
        return re.sub(r'<a href="([^"]+)">([^<]+)</a>', r'\2: \1', text or "")
    except Exception:
        return text or ""


"""

LOG_DEF_ANCHOR = r"""def _dip_log_rich_rejected(err, where, extra=""):"""

CMDS_SEND_TEXT_OLD = r"""    try:
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
        return False"""

CMDS_SEND_TEXT_NEW = r"""    try:
        if userbot_client:
            try:
                await asyncio.wait_for(
                    _userbot_send_with_premium_emoji(TARGET_CHANNEL, plain_text),
                    timeout=USERBOT_SEND_TIMEOUT_SECONDS)
                return True
            except Exception:
                pass
        await bot.send_message(chat_id=TARGET_CHANNEL, text=plain_text,
                               parse_mode="HTML", disable_web_page_preview=True)
        return True
    except Exception as e:
        _dip_log_rich_rejected(e, "html-fallback", "testdip-text")
    try:
        await bot.send_message(chat_id=TARGET_CHANNEL,
                               text=_dip_strip_links(plain_text),
                               disable_web_page_preview=True)
        return True
    except Exception as e:
        _dip_log_rich_rejected(e, "html-fallback", "testdip-text last resort")
        return False"""

CMDS_SEND_MEDIA_OLD = r"""    try:
        if ftype == "photo":
            await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=plain_caption)
        elif ftype == "gif":
            await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=plain_caption)
        else:
            await bot.send_video(TARGET_CHANNEL, video=fid, caption=plain_caption)
        return True
    except Exception:
        return False"""

CMDS_SEND_MEDIA_NEW = r"""    try:
        if ftype == "photo":
            await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=plain_caption,
                                 parse_mode="HTML")
        elif ftype == "gif":
            await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=plain_caption,
                                     parse_mode="HTML")
        else:
            await bot.send_video(TARGET_CHANNEL, video=fid, caption=plain_caption,
                                 parse_mode="HTML")
        return True
    except Exception as e:
        _dip_log_rich_rejected(e, "html-fallback", "testdip-media")
    try:
        _stripped = _dip_strip_links(plain_caption)
        if ftype == "photo":
            await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=_stripped)
        elif ftype == "gif":
            await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=_stripped)
        else:
            await bot.send_video(TARGET_CHANNEL, video=fid, caption=_stripped)
        return True
    except Exception as e:
        _dip_log_rich_rejected(e, "html-fallback", "testdip-media last resort")
        return False"""

# ---------------------------------------------------------------------------
# x_alert.py edits
# ---------------------------------------------------------------------------

XA_COMMENT_OLD = r"""def _dip_plain_caption_dm(call, x_val, cur_mc):
    # DIP_DM_ONLY_NOV22: plain-text dip caption for the DM fallback. No
    # HTML, no custom emoji, no pe()/fmt_mc()/link helpers, so Telegram
    # can never reject it. Joins with chr(10) (a real newline)."""

XA_COMMENT_NEW = r"""def _dip_plain_caption_dm(call, x_val, cur_mc):
    # DIP_DM_ONLY_NOV22: dip caption for the DM fallback. HTML links only
    # (<a href>), no custom emoji, no pe()/fmt_mc()/link helpers, so
    # Telegram can never reject it for a bad custom emoji id.
    # DIP_LINKS_NOV22: links are real <a href> hyperlinks now (URL hidden
    # behind the label, like the normal X alert), sent with parse_mode HTML.
    # Joins with chr(10) (a real newline)."""

XA_LINKS_OLD = CMDS_LINKS_OLD
XA_LINKS_NEW = CMDS_LINKS_NEW

XA_SEND_DM_OLD = r"""        except Exception as e:
            _dip_log_rich_rejected(e, "dip-dm", f"{x_val}x {call_key} -> {uid}")
            try:
                if ftype == "photo":
                    await bot.send_photo(uid, photo=fid, caption=plain_caption)
                elif ftype == "gif":
                    await bot.send_animation(uid, animation=fid, caption=plain_caption)
                else:
                    await bot.send_video(uid, video=fid, caption=plain_caption)
                ok = True
            except Exception as e2:
                logger.warning(f"dip DM plain send failed {x_val}x {call_key} -> {uid}: {e2}")"""

XA_SEND_DM_NEW = r"""        except Exception as e:
            _dip_log_rich_rejected(e, "dip-dm", f"{x_val}x {call_key} -> {uid}")
            try:
                if ftype == "photo":
                    await bot.send_photo(uid, photo=fid, caption=plain_caption,
                                         parse_mode="HTML")
                elif ftype == "gif":
                    await bot.send_animation(uid, animation=fid, caption=plain_caption,
                                             parse_mode="HTML")
                else:
                    await bot.send_video(uid, video=fid, caption=plain_caption,
                                         parse_mode="HTML")
                ok = True
            except Exception as e2:
                _dip_log_rich_rejected(e2, "html-fallback", f"dip-dm {x_val}x {call_key} -> {uid}")
                try:
                    _stripped = _dip_strip_links(plain_caption)
                    if ftype == "photo":
                        await bot.send_photo(uid, photo=fid, caption=_stripped)
                    elif ftype == "gif":
                        await bot.send_animation(uid, animation=fid, caption=_stripped)
                    else:
                        await bot.send_video(uid, video=fid, caption=_stripped)
                    ok = True
                except Exception as e3:
                    logger.warning(f"dip DM plain send failed {x_val}x {call_key} -> {uid}: {e3}")"""

# (fname, [(old, new, label), ...], inserts=[(anchor, text, label)])
EDITS = {
    "commands.py": {
        "replaces": [
            (CMDS_COMMENT_OLD, CMDS_COMMENT_NEW, "plain caption comment"),
            (CMDS_LINKS_OLD, CMDS_LINKS_NEW, "plain caption links"),
            (CMDS_SEND_TEXT_OLD, CMDS_SEND_TEXT_NEW, "_testdip_send_text fallback"),
            (CMDS_SEND_MEDIA_OLD, CMDS_SEND_MEDIA_NEW, "_testdip_send_media fallback"),
        ],
        "inserts": [
            (LOG_DEF_ANCHOR, STRIP_HELPER, "_dip_strip_links helper"),
        ],
    },
    "x_alert.py": {
        "replaces": [
            (XA_COMMENT_OLD, XA_COMMENT_NEW, "DM plain caption comment"),
            (XA_LINKS_OLD, XA_LINKS_NEW, "DM plain caption links"),
            (XA_SEND_DM_OLD, XA_SEND_DM_NEW, "_dip_send_dm fallback"),
        ],
        "inserts": [
            (LOG_DEF_ANCHOR, STRIP_HELPER, "_dip_strip_links helper"),
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
            if n_old == 1:
                continue
            if n_old == 0 and n_new >= 1:
                print(f"  SKIP {fname}: {label} already applied.")
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
            if _count(text, old) == 1:
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
    print("Then verify: /testdip 5 in the bot DM - the channel preview must")
    print("show 'Post Link' and 'Dexscreener' as clickable labels, NO open URLs.")
    print("If the HTML fallback itself is rejected, check the journal:")
    print('journalctl -u bot.service --since "10 minutes ago" --no-pager | grep -i "html-fallback"')


if __name__ == "__main__":
    main()
