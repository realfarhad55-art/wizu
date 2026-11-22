#!/usr/bin/env python3
"""DIP_TESTEMOJI_NOV22 - /testdipemoji diagnostic command.

Problem: the dip rich caption (build_dip_caption) is rejected by Telegram
on both the userbot and Bot API paths, so every /testdip preview falls
back to the plain caption and the premium custom emojis never render.
The cause is one or more invalid dip custom emoji document ids, but the
bad id is still unidentified: the journal greps came back empty (most
likely because /testdip was not run inside the grep windows), and the
ids cannot be verified from the pack link (its preview widget never
loads in a browser).

This patch adds an owner-only diagnostic command that tests each of the
5 dip custom emoji ids by elimination, Bot API only (no userbot), so a
failure is unambiguously the id, not the userbot:
  /testdipemoji [chain]   (default SOL; chains: SOL ETH BNB BASE ARC TON RH)
For each id it sends one Bot API message with that single custom emoji.
It then replies to the owner DM with a 5-line summary table
(label | id | OK, or REJECTED: <exact Telegram error>).
It records nothing and changes no config.

It also makes /testdip DM the exact Telegram error to the owner when
the rich caption is rejected, so the error is visible without journalctl.
That is a low-risk addition: an optional notify_chat_id=None parameter
on the two _testdip_send_* helpers (default None keeps old behaviour),
and a guarded send that can never break the fallback.

VPS-only one-time script. Idempotent (marker DIP_TESTEMOJI_NOV22).
Backups: <file>.bak_testemoji_nov22. Fail-safe: validates ALL anchors
before writing anything; aborts without touching files on mismatch.
Usage: cd /opt/bot && python3 apply_dip_testemoji_nov22.py
"""

import os
import sys

MARKER = "DIP_TESTEMOJI_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BAK_SUFFIX = ".bak_testemoji_nov22"


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

TESTEMOJI_FUNC = r"""

@owner_only
async def cmd_testdipemoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # DIP_TESTEMOJI_NOV22: owner-only diagnostic. Tests each of the 5 dip
    # custom emoji ids by elimination, Bot API only (no userbot), so a
    # failure is unambiguously the id, not the userbot. Records nothing,
    # changes no config. Usage: /testdipemoji [chain] (default SOL).
    chain = (context.args[0] if context.args else "SOL").upper().replace("BSC", "BNB")
    if chain not in DIP_CHAIN_EMOJIS:
        await update.message.reply_text(
            "Chain galat hai. Usage: /testdipemoji [chain]" + chr(10) + chr(10)
            + "Chains: " + ", ".join(DIP_CHAIN_EMOJIS.keys()))
        return
    bot = context.bot
    chat_id = update.effective_chat.id if getattr(update, "effective_chat", None) else None
    if chat_id is None:
        await update.message.reply_text("Testdipemoji error: DM chat nahi mila.")
        return
    tests = [
        ("Chain (" + chain + ")", DIP_CHAIN_EMOJIS[chain]),
        ("Crystal ball", DIP_CRYSTAL_EMOJI_ID),
        ("Teer", DIP_TEER_EMOJI_ID),
        ("Post Link", DIP_POSTLINK_EMOJI_ID),
        ("Dexscreener", DIP_DEX_EMOJI_ID),
    ]
    results = []
    for label, eid in tests:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f'<tg-emoji emoji-id="{eid}">🔮</tg-emoji> {label} {eid}',
                parse_mode="HTML")
            results.append(label + ": " + str(eid) + " - OK")
        except Exception as e:
            results.append(label + ": " + str(eid) + " - REJECTED: " + str(e))
    await update.message.reply_text(
        "Dip emoji test (" + chain + "):" + chr(10) + chr(10).join(results))


"""

EDITBUTTON_ANCHOR = r"""@owner_only
async def cmd_editbutton(update: Update, context: ContextTypes.DEFAULT_TYPE):"""

SEND_TEXT_DEF_OLD = r"""async def _testdip_send_text(bot, rich_text, plain_text):"""

SEND_TEXT_DEF_NEW = r"""async def _testdip_send_text(bot, rich_text, plain_text, notify_chat_id=None):"""

SEND_MEDIA_DEF_OLD = r"""async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids):"""

SEND_MEDIA_DEF_NEW = r"""async def _testdip_send_media(bot, ftype, fid, rich_caption, plain_caption, emoji_ids, notify_chat_id=None):"""

LOG_TEXT_OLD = r"""    _dip_log_rich_rejected(err, "testdip-text",
                           ("userbot: %s" % ub_err) if ub_err is not None else "")"""

LOG_TEXT_NEW = r"""    _dip_log_rich_rejected(err, "testdip-text",
                           ("userbot: %s" % ub_err) if ub_err is not None else "")
    # DIP_TESTEMOJI_NOV22: DM the exact Telegram error to the owner too, so
    # it is visible without journalctl. Guarded, never breaks the fallback.
    if notify_chat_id:
        try:
            await bot.send_message(chat_id=notify_chat_id,
                                   text="Dip rich caption reject ho gaya: " + str(err))
        except Exception:
            pass"""

LOG_MEDIA_OLD = r"""    _dip_log_rich_rejected(err, "testdip-media",
                           ("userbot: %s | emoji_ids: %s" % (ub_err, emoji_ids)) if ub_err is not None else ("emoji_ids: %s" % (emoji_ids,)))"""

LOG_MEDIA_NEW = r"""    _dip_log_rich_rejected(err, "testdip-media",
                           ("userbot: %s | emoji_ids: %s" % (ub_err, emoji_ids)) if ub_err is not None else ("emoji_ids: %s" % (emoji_ids,)))
    # DIP_TESTEMOJI_NOV22: DM the exact Telegram error to the owner too, so
    # it is visible without journalctl. Guarded, never breaks the fallback.
    if notify_chat_id:
        try:
            await bot.send_message(chat_id=notify_chat_id,
                                   text="Dip rich caption reject ho gaya: " + str(err))
        except Exception:
            pass"""

DM_CHAT_OLD = r"""    media = dip_media_for(xv)
    bot = context.bot
    if not media:"""

DM_CHAT_NEW = r"""    media = dip_media_for(xv)
    bot = context.bot
    # DIP_TESTEMOJI_NOV22: owner DM chat id, so a rejected rich caption can
    # be reported to the owner without journalctl.
    dm_chat_id = update.effective_chat.id if getattr(update, "effective_chat", None) else None
    if not media:"""

CALL_TEXT_OLD = r"""        ok = await _testdip_send_text(bot, rich, plain)"""

CALL_TEXT_NEW = r"""        ok = await _testdip_send_text(bot, rich, plain, notify_chat_id=dm_chat_id)"""

CALL_MEDIA_OLD = r"""    ok = await _testdip_send_media(bot, ftype, fid, rich_cap, plain, emoji_ids)"""

CALL_MEDIA_NEW = r"""    ok = await _testdip_send_media(bot, ftype, fid, rich_cap, plain, emoji_ids, notify_chat_id=dm_chat_id)"""

# ---------------------------------------------------------------------------
# runtime.py edits
# ---------------------------------------------------------------------------

TESTDIP_HANDLER_OLD = r"""    app.add_handler(CommandHandler("testdip",        cmd_testdip))"""

TESTDIP_HANDLER_NEW = r"""    app.add_handler(CommandHandler("testdip",        cmd_testdip))
    # DIP_TESTEMOJI_NOV22: owner-only /testdipemoji diagnostic.
    app.add_handler(CommandHandler("testdipemoji",   cmd_testdipemoji))"""

# (fname, [(old, new, label), ...], inserts=[(anchor, text, label)])
EDITS = {
    "commands.py": {
        "replaces": [
            (SEND_TEXT_DEF_OLD, SEND_TEXT_DEF_NEW, "_testdip_send_text signature"),
            (SEND_MEDIA_DEF_OLD, SEND_MEDIA_DEF_NEW, "_testdip_send_media signature"),
            (LOG_TEXT_OLD, LOG_TEXT_NEW, "_testdip_send_text rich notify"),
            (LOG_MEDIA_OLD, LOG_MEDIA_NEW, "_testdip_send_media rich notify"),
            (DM_CHAT_OLD, DM_CHAT_NEW, "dm_chat_id in _cmd_testdip_inner"),
            (CALL_TEXT_OLD, CALL_TEXT_NEW, "_testdip_send_text call site"),
            (CALL_MEDIA_OLD, CALL_MEDIA_NEW, "_testdip_send_media call site"),
        ],
        "inserts": [
            (EDITBUTTON_ANCHOR, TESTEMOJI_FUNC, "cmd_testdipemoji"),
        ],
    },
    "runtime.py": {
        "replaces": [
            (TESTDIP_HANDLER_OLD, TESTDIP_HANDLER_NEW, "testdipemoji handler"),
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
    print("Then verify: run /testdipemoji in the bot DM and read the")
    print("5-line summary. The REJECTED line names the bad emoji id.")
    print("Also: /testdip 5 now DMs the exact Telegram error to the owner")
    print("when the rich caption is rejected (no journalctl needed).")


if __name__ == "__main__":
    main()
