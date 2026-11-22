#!/usr/bin/env python3
"""DIP_CRYSTAL_FALLBACK_NOV22 - Crystal ball emoji in all plain fallback positions.

Problem: the dip PLAIN fallback captions (used when the rich premium-emoji
caption is rejected) use distinct standard Unicode emojis: diamond before
the title, green arrow as the teer, megaphone before Post Link, link before
Dexscreener (only the entry-MC crystal ball already matches). The user set
the crystal ball as the fallback behind the premium emojis in his pack, so
the non-premium/plain version should show the crystal ball at every emoji
position, for consistency with the rich caption (whose pe() fallback is the
crystal ball everywhere).

Fix: change the plain fallback captions in both files so all 5 emoji
positions use the crystal ball:
  - _dip_plain_caption (commands.py, /testdip fallback)
  - _dip_plain_caption_dm (x_alert.py, real dip DM fallback)
Title line becomes crystal ball + bold title (like the rich caption), MC
line becomes crystal ball entry, crystal ball current, links line becomes
crystal ball Post Link and crystal ball Dexscreener (HTML hyperlinks kept,
URLs hidden behind the labels).

Behaviour kept exactly: real newlines (chr(10) joins), HTML hyperlinks,
bold title, paragraph unchanged, rich caption untouched, emoji ids
untouched, DM-only setting untouched, Bot-API-first send order untouched,
DM-error notify untouched.

VPS-only one-time script. Idempotent (marker DIP_CRYSTAL_FALLBACK_NOV22).
Backups: <file>.bak_crystal_nov22. Fail-safe: validates ALL anchors before
writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_dip_crystal_fallback_nov22.py
"""

import os
import sys

MARKER = "DIP_CRYSTAL_FALLBACK_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_crystal_nov22"


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

CMDS_COMMENT_OLD = r'''def _dip_plain_caption(call, x_val, cur_mc):
    # DIP_TESTFIX_NOV22: dip caption for the fallback. HTML links only
    # (<a href>), no custom emoji, no pe()/fmt_mc()/link helpers, so
    # Telegram can never reject it for a bad custom emoji id.
    # DIP_LINKS_NOV22: links are real <a href> hyperlinks now (URL hidden
    # behind the label, like the normal X alert), sent with parse_mode HTML.'''

CMDS_COMMENT_NEW = r'''def _dip_plain_caption(call, x_val, cur_mc):
    # DIP_TESTFIX_NOV22: dip caption for the fallback. HTML links only
    # (<a href>), no custom emoji, no pe()/fmt_mc()/link helpers, so
    # Telegram can never reject it for a bad custom emoji id.
    # DIP_LINKS_NOV22: links are real <a href> hyperlinks now (URL hidden
    # behind the label, like the normal X alert), sent with parse_mode HTML.
    # DIP_CRYSTAL_FALLBACK_NOV22: all 5 emoji positions use the crystal
    # ball, matching the pe() fallback the user set behind the premium
    # emojis, so the plain version looks the same as the rich one.'''

CMDS_TITLE_OLD = r'''    lines = [f"💠 {title}", "",'''

CMDS_TITLE_NEW = r'''    lines = [f"🔮 <b>{title}</b>", "",'''

CMDS_MC_OLD = r'''             f"🔮 {_dip_fmt_plain(entry_mc)} ➡️ {_dip_fmt_plain(cur_mc)}", ""]'''

CMDS_MC_NEW = r'''             f"🔮 {_dip_fmt_plain(entry_mc)} 🔮 {_dip_fmt_plain(cur_mc)}", ""]'''

CMDS_POST_OLD = r'''        links.append(f'📣 <a href="{post_url}">Post Link</a>')'''

CMDS_POST_NEW = r'''        links.append(f'🔮 <a href="{post_url}">Post Link</a>')'''

CMDS_DEX_OLD = r'''        links.append(f'🔗 <a href="{dex_url}">Dexscreener</a>')'''

CMDS_DEX_NEW = r'''        links.append(f'🔮 <a href="{dex_url}">Dexscreener</a>')'''


# ---------------------------------------------------------------------------
# x_alert.py edits
# ---------------------------------------------------------------------------

XA_COMMENT_OLD = r'''def _dip_plain_caption_dm(call, x_val, cur_mc):
    # DIP_DM_ONLY_NOV22: dip caption for the DM fallback. HTML links only
    # (<a href>), no custom emoji, no pe()/fmt_mc()/link helpers, so
    # Telegram can never reject it for a bad custom emoji id.
    # DIP_LINKS_NOV22: links are real <a href> hyperlinks now (URL hidden
    # behind the label, like the normal X alert), sent with parse_mode HTML.'''

XA_COMMENT_NEW = r'''def _dip_plain_caption_dm(call, x_val, cur_mc):
    # DIP_DM_ONLY_NOV22: dip caption for the DM fallback. HTML links only
    # (<a href>), no custom emoji, no pe()/fmt_mc()/link helpers, so
    # Telegram can never reject it for a bad custom emoji id.
    # DIP_LINKS_NOV22: links are real <a href> hyperlinks now (URL hidden
    # behind the label, like the normal X alert), sent with parse_mode HTML.
    # DIP_CRYSTAL_FALLBACK_NOV22: all 5 emoji positions use the crystal
    # ball, matching the pe() fallback the user set behind the premium
    # emojis, so the plain version looks the same as the rich one.'''

XA_TITLE_OLD = CMDS_TITLE_OLD
XA_TITLE_NEW = CMDS_TITLE_NEW

XA_MC_OLD = r'''             f"🔮 {_dip_fmt_plain_dm(entry_mc)} ➡️ {_dip_fmt_plain_dm(cur_mc)}", ""]'''

XA_MC_NEW = r'''             f"🔮 {_dip_fmt_plain_dm(entry_mc)} 🔮 {_dip_fmt_plain_dm(cur_mc)}", ""]'''

XA_POST_OLD = CMDS_POST_OLD
XA_POST_NEW = CMDS_POST_NEW

XA_DEX_OLD = CMDS_DEX_OLD
XA_DEX_NEW = CMDS_DEX_NEW


EDITS = {
    "commands.py": {
        "replaces": [
            (CMDS_COMMENT_OLD, CMDS_COMMENT_NEW, "plain caption comment"),
            (CMDS_TITLE_OLD, CMDS_TITLE_NEW, "plain caption title line"),
            (CMDS_MC_OLD, CMDS_MC_NEW, "plain caption MC line"),
            (CMDS_POST_OLD, CMDS_POST_NEW, "plain caption Post Link line"),
            (CMDS_DEX_OLD, CMDS_DEX_NEW, "plain caption Dexscreener line"),
        ],
        "inserts": [],
    },
    "x_alert.py": {
        "replaces": [
            (XA_COMMENT_OLD, XA_COMMENT_NEW, "DM plain caption comment"),
            (XA_TITLE_OLD, XA_TITLE_NEW, "DM plain caption title line"),
            (XA_MC_OLD, XA_MC_NEW, "DM plain caption MC line"),
            (XA_POST_OLD, XA_POST_NEW, "DM plain caption Post Link line"),
            (XA_DEX_OLD, XA_DEX_NEW, "DM plain caption Dexscreener line"),
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
    print("channel post shows the crystal ball at all 5 emoji positions")
    print("(title, entry MC, teer, Post Link, Dexscreener).")


if __name__ == "__main__":
    main()
