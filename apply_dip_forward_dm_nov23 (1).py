# apply_dip_forward_dm_nov23.py - Dip DM = forward to KOL owner only (min dip stays 50%)
# Marker: DIP_FWD_DM_NOV23
# User request (Nov 23 21:15 + 21:21 PKT, corrected):
#  (1) Dip alert DM must be a FORWARD of the channel post, exactly like X
#      alerts are forwarded to DMs (not a fresh copy). Tapping it opens the
#      @WizardScan post. Forward goes ONLY to the KOL owner's DM - NOT to
#      the KOL's own channel, NOT to subscribers.
#  (2) Dip filter: min dip 50%, max dip 99% (NO CHANGE - already live via
#      DIP5099 + /setdipthreshold 50). User first said 1%, then 30%, then
#      corrected: he meant 50% min dip. The 1% is the floor: dip low must
#      stay >= 1% of entry = max 99% dip. No /setdipthreshold run needed.
# Edits (x_alert.py only):
#  E1: DIP_DEFAULT_THRESHOLD_PCT -> 50.0 (keeps live value; regex matches 30.0 or 50.0).
#  E2: capture channel_post_id from the userbot send (msg.id).
#  E3: capture channel_post_id from the Bot API explicit-entities send.
#  E4: capture channel_post_id from the Bot API HTML send.
#  E5: after a successful channel post, FORWARD it to the KOL owner DM only
#      (replaces the fresh-copy _dip_send_dm call added by DIP_CHANNEL_DM_NOV23).
# Usage: python3 apply_dip_forward_dm_nov23.py x_alert.py
import re
import sys

MARKER = "DIP_FWD_DM_NOV23"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "x_alert.py"
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if MARKER in src:
        print("already has %s, skipping" % MARKER)
        return
    orig = src

    # E1: threshold -> 50.0 (live value is 50.0 after DIP5099; older copies 30.0)
    new_src, n1 = re.subn(
        r"DIP_DEFAULT_THRESHOLD_PCT = [0-9.]+",
        "DIP_DEFAULT_THRESHOLD_PCT = 50.0  # DIP_FWD_DM_NOV23: min dip 50% (unchanged)",
        src, count=1)
    if n1 != 1:
        print("FAIL: E1 threshold anchor not found")
        return
    src = new_src
    print("E1 OK (threshold -> 50.0)")

    edits = [
        # E2: userbot send - capture msg.id
        (
            "    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.\n"
            "    if not posted and userbot_client:\n"
            "        try:\n"
            "            msg = await asyncio.wait_for(\n"
            "                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,\n"
            "                                               caption, emoji_ids,\n"
            "                                               forced_pack=_dip_pack),\n"
            "                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)\n"
            "            if msg is not None:\n"
            "                posted = True\n",
            "    # DIP_USERBOT_FIRST_NOV22: (1) userbot rich send FIRST.\n"
            "    channel_post_id = None  # DIP_FWD_DM_NOV23: id of the channel post to forward\n"
            "    if not posted and userbot_client:\n"
            "        try:\n"
            "            msg = await asyncio.wait_for(\n"
            "                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,\n"
            "                                               caption, emoji_ids,\n"
            "                                               forced_pack=_dip_pack),\n"
            "                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)\n"
            "            if msg is not None:\n"
            "                posted = True\n"
            "                channel_post_id = getattr(msg, \"id\", None)\n",
        ),
        # E3: Bot API explicit-entities send - capture message_id
        (
            "        if _ent_list:\n"
            "            try:\n"
            "                if ftype == \"photo\":\n"
            "                    await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=_ent_plain,\n"
            "                                         caption_entities=_ent_list)\n"
            "                elif ftype == \"gif\":\n"
            "                    await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=_ent_plain,\n"
            "                                             caption_entities=_ent_list)\n"
            "                else:\n"
            "                    await bot.send_video(TARGET_CHANNEL, video=fid, caption=_ent_plain,\n"
            "                                         caption_entities=_ent_list)\n"
            "                posted = True\n",
            "        if _ent_list:\n"
            "            try:\n"
            "                _sent = None\n"
            "                if ftype == \"photo\":\n"
            "                    _sent = await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=_ent_plain,\n"
            "                                                 caption_entities=_ent_list)\n"
            "                elif ftype == \"gif\":\n"
            "                    _sent = await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=_ent_plain,\n"
            "                                                     caption_entities=_ent_list)\n"
            "                else:\n"
            "                    _sent = await bot.send_video(TARGET_CHANNEL, video=fid, caption=_ent_plain,\n"
            "                                                 caption_entities=_ent_list)\n"
            "                posted = True\n"
            "                channel_post_id = getattr(_sent, \"message_id\", None)\n",
        ),
        # E4: Bot API HTML send - capture message_id
        (
            "        if not posted and not _BOT_CHANNEL_FORBIDDEN[\"v\"]:\n"
            "            try:\n"
            "                if ftype == \"photo\":\n"
            "                    await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=caption,\n"
            "                                         parse_mode=\"HTML\")\n"
            "                elif ftype == \"gif\":\n"
            "                    await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=caption,\n"
            "                                             parse_mode=\"HTML\")\n"
            "                else:\n"
            "                    await bot.send_video(TARGET_CHANNEL, video=fid, caption=caption,\n"
            "                                         parse_mode=\"HTML\")\n"
            "                posted = True\n",
            "        if not posted and not _BOT_CHANNEL_FORBIDDEN[\"v\"]:\n"
            "            try:\n"
            "                _sent = None\n"
            "                if ftype == \"photo\":\n"
            "                    _sent = await bot.send_photo(TARGET_CHANNEL, photo=fid, caption=caption,\n"
            "                                                 parse_mode=\"HTML\")\n"
            "                elif ftype == \"gif\":\n"
            "                    _sent = await bot.send_animation(TARGET_CHANNEL, animation=fid, caption=caption,\n"
            "                                                     parse_mode=\"HTML\")\n"
            "                else:\n"
            "                    _sent = await bot.send_video(TARGET_CHANNEL, video=fid, caption=caption,\n"
            "                                                 parse_mode=\"HTML\")\n"
            "                posted = True\n"
            "                channel_post_id = getattr(_sent, \"message_id\", None)\n",
        ),
        # E5: forward the channel post to the KOL owner DM ONLY (no subscribers,
        # no KOL channel). Replaces the fresh-copy _dip_send_dm call.
        (
            "        # DIP_CHANNEL_DM_NOV23: DM after the channel post (best-effort).\n"
            "        try:\n"
            "            await _dip_send_dm(bot, call_key, call, x_val, cur_mc,\n"
            "                               fid, ftype, caption, promo_separate)\n"
            "        except Exception as e:\n"
            "            logger.warning(f\"Dip DM after channel post failed {x_val}x {call_key}: {e}\")\n"
            "        return True\n",
            "        # DIP_FWD_DM_NOV23: forward the channel post to the KOL owner DM\n"
            "        # ONLY (like X alerts). No forward to the KOL channel, no subscribers.\n"
            "        try:\n"
            "            if channel_post_id:\n"
            "                _owner_id = None\n"
            "                try:\n"
            "                    _ck = str(call.get(\"channel\") or \"\").lstrip(\"@\").lower()\n"
            "                    _owner_id = load_kol_owners().get(_ck)\n"
            "                    _owner_id = int(_owner_id) if _owner_id is not None else None\n"
            "                except (TypeError, ValueError):\n"
            "                    _owner_id = None\n"
            "                if _owner_id:\n"
            "                    try:\n"
            "                        await bot.forward_message(chat_id=_owner_id,\n"
            "                                                  from_chat_id=TARGET_CHANNEL,\n"
            "                                                  message_id=channel_post_id)\n"
            "                    except Exception as _fe:\n"
            "                        logger.warning(f\"Dip forward to owner {_owner_id} failed {x_val}x {call_key}: {_fe}\")\n"
            "                else:\n"
            "                    logger.warning(f\"Dip forward skipped {x_val}x {call_key}: no KOL owner set\")\n"
            "            else:\n"
            "                logger.warning(f\"Dip forward skipped {x_val}x {call_key}: no channel post id\")\n"
            "        except Exception as e:\n"
            "            logger.warning(f\"Dip DM forward failed {x_val}x {call_key}: {e}\")\n"
            "        return True\n",
        ),
    ]
    for i, (old, new) in enumerate(edits, 2):
        n = src.count(old)
        if n != 1:
            print("FAIL: edit E%d anchor count=%d (want 1)" % (i, n))
            return
        src = src.replace(old, new, 1)
        print("E%d OK" % i)
    with open(path + ".bak_dip_fwd_nov23", "w", encoding="utf-8") as f:
        f.write(orig)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("DONE. Backup: x_alert.py.bak_dip_fwd_nov23")
    print("Now restart the wizu bot (systemctl restart bot.service).")
    print("No /setdipthreshold run needed (already 50).")

if __name__ == "__main__":
    main()
