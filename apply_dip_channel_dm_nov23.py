# apply_dip_channel_dm_nov23.py - Dip alerts: channel FIRST, then DM + @channel mention
# Marker: DIP_CHANNEL_DM_NOV23
# User request (Nov 23 21:10 PKT): dip profit post must FIRST go on the main
# channel @WizardScan, THEN to the user's DM. (This reverses the Nov 22
# DM-only decision.) Also the channel name in the post must be @Bigbangcall
# (with @) so tapping it opens the channel, not plain "Bigbangcall".
# Edits (x_alert.py only):
#  E1: build_dip_caption - channel name becomes @Channel (clickable mention).
#  E2: _dip_plain_caption_dm - same @Channel change in the plain DM caption.
#  E3: send_dip_alert - remove the DM-only early return (no more DM-only).
#  E4: send_dip_alert - after a successful channel post, send the DM too
#      (best-effort: a DM failure never un-posts the channel alert).
# Usage: python3 apply_dip_channel_dm_nov23.py x_alert.py
import sys

MARKER = "DIP_CHANNEL_DM_NOV23"

EDITS = [
    # E1: rich dip caption - @Channel
    (
        '        f"{_html.escape(ch)} picked ${_html.escape(symbol)} at the dip. "',
        '        f"@{_html.escape(ch)} picked ${_html.escape(symbol)} at the dip. "',
    ),
    # E2: plain DM caption - @Channel
    (
        '             f"{ch} picked ${symbol} at the dip. Now up {pct_s}% from the low.",',
        '             f"@{ch} picked ${symbol} at the dip. Now up {pct_s}% from the low.",',
    ),
    # E3: remove the DM-only early return so the channel post always runs
    (
        '    fid, ftype = media["file_id"], media.get("type", "video")\n'
        '    if dip_dm_only():\n'
        '        ok = await _dip_send_dm(bot, call_key, call, x_val, cur_mc,\n'
        '                                fid, ftype, caption, promo_separate)\n'
        '        if ok:\n'
        '            _dip_clear_pending(call_key, x_val)\n'
        '            logger.info(f"Dip alert DM-sent: {x_val}x {call_key}")\n'
        '            return True\n'
        '        _dip_add_pending(call_key, x_val, cur_mc)\n'
        '        return False\n'
        '    # DIP_USERBOT_FIRST_NOV22: userbot rich send FIRST, Bot API as fallback.',
        '    fid, ftype = media["file_id"], media.get("type", "video")\n'
        '    # DIP_CHANNEL_DM_NOV23: channel FIRST, then DM (reverses Nov 22 DM-only).\n'
        '    # DIP_USERBOT_FIRST_NOV22: userbot rich send FIRST, Bot API as fallback.',
    ),
    # E4: DM after a successful channel post (best-effort)
    (
        '    if posted:\n'
        '        _dip_clear_pending(call_key, x_val)\n'
        '        if promo_separate:\n'
        '            await _dip_send_promo_followup(bot, dip_promo_html())\n'
        '        logger.info(f"Dip alert posted: {x_val}x {call_key}")\n'
        '        return True\n',
        '    if posted:\n'
        '        _dip_clear_pending(call_key, x_val)\n'
        '        if promo_separate:\n'
        '            await _dip_send_promo_followup(bot, dip_promo_html())\n'
        '        logger.info(f"Dip alert posted: {x_val}x {call_key}")\n'
        '        # DIP_CHANNEL_DM_NOV23: DM after the channel post (best-effort).\n'
        '        try:\n'
        '            await _dip_send_dm(bot, call_key, call, x_val, cur_mc,\n'
        '                               fid, ftype, caption, promo_separate)\n'
        '        except Exception as e:\n'
        '            logger.warning(f"Dip DM after channel post failed {x_val}x {call_key}: {e}")\n'
        '        return True\n',
    ),
]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "x_alert.py"
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if MARKER in src:
        print("already has %s, skipping" % MARKER)
        return
    orig = src
    for i, (old, new) in enumerate(EDITS, 1):
        n = src.count(old)
        if n != 1:
            print("FAIL: edit E%d anchor count=%d (want 1)" % (i, n))
            return
        src = src.replace(old, new, 1)
        print("E%d OK" % i)
    with open(path + ".bak_dip_chdm_nov23", "w", encoding="utf-8") as f:
        f.write(orig)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("DONE. Backup: x_alert.py.bak_dip_chdm_nov23")
    print("Now restart the wizu bot (systemctl restart bot.service).")

if __name__ == "__main__":
    main()
