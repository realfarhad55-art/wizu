#!/usr/bin/env python3
# apply_dip_profit_nov22.py - DIP PROFIT feature for wizu (WizardScan bot).
# VPS-ONLY one-time script. Run it ONCE on the Contabo VPS as root:
#   cd /opt/bot && python3 apply_dip_profit_nov22.py
# It edits core.py, x_alert.py, commands.py, runtime.py in /opt/bot
# (pass another dir as argv[1] to target a copy instead).
# Idempotent: files already containing DIP_PROFIT_NOV22 are skipped.
# Fail-safe: every anchor is checked BEFORE anything is written; if any
# anchor is missing (live code drifted from the Nov 18 local copies), the
# script aborts with a clear message and writes NOTHING.
# Each edited file is backed up to <file>.bak_dipprofit_nov22 first.
# After the patch: systemctl restart bot.service (and verify one process).
import os
import re
import shutil
import sys

MARKER = "DIP_PROFIT_NOV22"
BOT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/opt/bot"
BACKUP_SUFFIX = ".bak_dipprofit_nov22"


class AnchorError(Exception):
    pass


# ─── Inserted code blocks (raw strings: backslash-n stays literal) ───────────

CORE_STATES = r'''ST_DIP_MEDIA      = "set_dip_media"    # DIP_PROFIT_NOV22: /setdipmedia - next message is the dip GIF/video
ST_DIP_PROMO      = "set_dip_promo"    # DIP_PROFIT_NOV22: /setdippromo - next message is the dip promo text
'''

XALERT_ENGINE = r'''# ─── DIP PROFIT (DIP_PROFIT_NOV22) ────────────────────────────────────────────
# Dip X alerts: entry ke baad sabse neeche wale MC (dip_low) se measure hota
# hai. Normal X alerts / milestones / points se bilkul alag system hai:
# apna media, apna template, koi points nahi, leaderboard/champions ko
# chhedta nahi.
DIP_CHAIN_EMOJIS = {
    "SOL": 5765106130082603361, "ETH": 5764739133717095374,
    "BNB": 5764915751362240683, "BASE": 5764744949102812568,
    "ARC": 5764807986337817167, "TON": 5764630410914963343,
    "RH": 5764824212724260037,
}
DIP_CRYSTAL_EMOJI_ID = 5764995255501857846
DIP_TEER_EMOJI_ID = 5764885063820910875
DIP_DEX_EMOJI_ID = 5764841255154491926
DIP_POSTLINK_EMOJI_ID = 5764705675921858385
DIP_MILESTONES_BASE = [2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 35, 40, 45, 50,
                       60, 70, 80, 90, 100, 150, 200, 250, 500, 1000, 1500]
DIP_MAX_X = 10000
DIP_DEFAULT_THRESHOLD_PCT = 30.0
DIP_DUST_FLOOR_FRAC = 0.001
DIP_LOW_CONFIRM_TICKS = 2
DIP_RESET_BELOW_FRAC = 0.8


def _dip_cfg():
    try:
        return load_config()
    except Exception:
        return {}


def dip_enabled():
    try:
        return bool(_dip_cfg().get("dip_enabled", True))
    except Exception:
        return True


def dip_threshold_pct():
    try:
        v = float(_dip_cfg().get("dip_threshold_pct", DIP_DEFAULT_THRESHOLD_PCT)
                  or DIP_DEFAULT_THRESHOLD_PCT)
    except (TypeError, ValueError):
        v = DIP_DEFAULT_THRESHOLD_PCT
    return min(max(v, 1.0), 50.0)


def dip_media_for(x_val):
    try:
        m = (_dip_cfg().get("dip_media", {}) or {}).get(str(int(x_val)))
    except Exception:
        m = None
    if isinstance(m, dict) and m.get("file_id"):
        return m
    return None


def dip_promo_html():
    try:
        p = _dip_cfg().get("dip_promo") or {}
    except Exception:
        return ""
    if isinstance(p, dict):
        return (p.get("html") or "").strip()
    return ""


def dip_title_for_x(x_val):
    try:
        x = int(x_val)
    except (TypeError, ValueError):
        x = 0
    if 2 <= x <= 9:
        return f"DIP TO PROFIT: {x}X"
    if 10 <= x <= 15:
        return f"DIP SNIPER STRIKES | {x}X"
    if x == 20:
        return "DIP DEMOLISHED 20x Profit"
    if x in (25, 30):
        return f"DIP HUNTERS WIN {x}X"
    if 31 <= x <= 40:
        return f"DIP ENTRY HITS {x}X"
    if x == 45:
        return "DIP MASTERED, 45X DONE"
    if x == 50:
        return "DIP TURNED GOLD, 50x Profit"
    if x == 60:
        return "RIDING THE DIP TO 60X"
    if x == 70:
        return "DIP GAME STRONG, 70X IN"
    if x == 80:
        return "DIP SNIPE PAYS 80X"
    if x == 90:
        return "DIP BUYERS EAT, 90X SERVED"
    if x == 100:
        return "HISTORIC DIP PROFIT 100X"
    if x == 200:
        return "DIP CAUGHT, 200X UNLOCKED"
    if x in (300, 400):
        return f"DIP BOUGHT, LIFE CHANGED {x}X"
    if x == 500:
        return "DIP TURNED LEGENDARY, 500X"
    if 600 <= x <= 1000:
        return f"DIP TO THE MOON, {x}X"
    return f"DIP TO PROFIT: {x}X"


def dip_milestones_for_ratio(ratio):
    try:
        ratio = float(ratio or 0)
    except (TypeError, ValueError):
        return []
    out = [m for m in DIP_MILESTONES_BASE if ratio >= m]
    m = 2000
    while m <= ratio and m <= DIP_MAX_X:
        out.append(m)
        m += 500
    return out


def _dip_pct_str(pct):
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = 0.0
    s = f"{pct:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _dip_plain_len(caption_html):
    import re as _re
    return len(_re.sub(r"<[^>]+>", "", caption_html or ""))


def build_dip_caption(call, x_val, cur_mc, include_promo=True):
    import html as _html
    channel = str(call.get("channel") or "")
    ch = (channel[:1].upper() + channel[1:]) if channel else channel
    symbol = str(call.get("symbol") or "TOKEN").upper()
    chain = str(call.get("chain") or "SOL").upper().replace("BSC", "BNB")
    try:
        entry_mc = float(call.get("entry_mc") or 0)
    except (TypeError, ValueError):
        entry_mc = 0.0
    try:
        dip_low = float(call.get("dip_low") or 0)
    except (TypeError, ValueError):
        dip_low = 0.0
    try:
        cur_mc = float(cur_mc or 0)
    except (TypeError, ValueError):
        cur_mc = 0.0
    title = dip_title_for_x(x_val)
    chain_e = pe(DIP_CHAIN_EMOJIS.get(chain, DIP_CHAIN_EMOJIS["SOL"]), "🔮")
    crystal_e = pe(DIP_CRYSTAL_EMOJI_ID, "🔮")
    teer_e = pe(DIP_TEER_EMOJI_ID, "🔮")
    post_e = pe(DIP_POSTLINK_EMOJI_ID, "🔮")
    dex_e = pe(DIP_DEX_EMOJI_ID, "🔮")
    entry_fmt = _mc_no_label(fmt_mc(entry_mc)) if entry_mc > 0 else "N/A"
    cur_fmt = _mc_no_label(fmt_mc(cur_mc)) if cur_mc > 0 else "N/A"
    pct = ((cur_mc / dip_low) - 1.0) * 100.0 if dip_low > 0 and cur_mc > 0 else 0.0
    lines = [
        f"<b>{chain_e} {_html.escape(title)}</b>",
        "",
        f"{_html.escape(ch)} picked ${_html.escape(symbol)} at the dip. "
        f"Now up {_dip_pct_str(pct)}% from the low.",
        "",
        f"{crystal_e} {entry_fmt} {teer_e} {cur_fmt}",
        "",
    ]
    post_url = _x_alert_caller_link(channel, call.get("msg_id"))
    dex_url = _x_alert_dex_link(call.get("ca"), chain)
    links = []
    if post_url:
        links.append(f"{post_e} <a href=\"{post_url}\">Post Link</a>")
    if dex_url:
        links.append(f"{dex_e} <a href=\"{dex_url}\">Dexscreener</a>")
    if links:
        lines.append("   ".join(links))
    if include_promo:
        promo = dip_promo_html()
        if promo:
            lines.append("")
            lines.append(promo)
    return "\n".join(lines)


def _dip_sent_levels(call):
    v = call.get("sent_dip_milestones")
    if not isinstance(v, list):
        v = []
        call["sent_dip_milestones"] = v
    return v


def _dip_pending_levels(call):
    v = call.get("pending_dip")
    if not isinstance(v, list):
        v = []
        call["pending_dip"] = v
    return v


def _dip_add_pending(call_key, x_val, cur_mc=0):
    call = tracked_calls.get(call_key)
    if not call:
        return
    lst = _dip_pending_levels(call)
    if int(x_val) not in lst:
        lst.append(int(x_val))
    try:
        mc_map = call.get("dip_pending_mc")
        if not isinstance(mc_map, dict):
            mc_map = {}
            call["dip_pending_mc"] = mc_map
        mc_map[str(int(x_val))] = float(cur_mc or 0)
    except (TypeError, ValueError):
        pass
    _save_tracked()


def _dip_clear_pending(call_key, x_val):
    call = tracked_calls.get(call_key)
    if not call:
        return
    lst = _dip_pending_levels(call)
    if int(x_val) in lst:
        lst.remove(int(x_val))
    try:
        mc_map = call.get("dip_pending_mc")
        if isinstance(mc_map, dict):
            mc_map.pop(str(int(x_val)), None)
    except Exception:
        pass
    _save_tracked()
'''

XALERT_ENGINE_2 = r'''
async def _dip_send_promo_followup(bot, promo_html):
    if not promo_html:
        return
    try:
        if userbot_client:
            try:
                await asyncio.wait_for(
                    _userbot_send_with_premium_emoji(TARGET_CHANNEL, promo_html),
                    timeout=USERBOT_SEND_TIMEOUT_SECONDS)
                return
            except Exception as e:
                logger.warning(f"dip promo follow-up userbot failed: {e}")
        await bot.send_message(chat_id=TARGET_CHANNEL, text=promo_html,
                               parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"dip promo follow-up failed: {e}")


async def send_dip_alert(bot, call_key, call, x_val, cur_mc):
    media = dip_media_for(x_val)
    if not media:
        _dip_add_pending(call_key, x_val, cur_mc)
        logger.info(f"Dip {x_val}x HELD (no media set): {call_key}")
        return False
    chain = str(call.get("chain") or "SOL").upper().replace("BSC", "BNB")
    emoji_ids = [DIP_CHAIN_EMOJIS.get(chain, DIP_CHAIN_EMOJIS["SOL"]),
                 DIP_CRYSTAL_EMOJI_ID, DIP_TEER_EMOJI_ID,
                 DIP_POSTLINK_EMOJI_ID, DIP_DEX_EMOJI_ID]
    caption = build_dip_caption(call, x_val, cur_mc, include_promo=True)
    promo_separate = False
    if _dip_plain_len(caption) > 1024:
        caption = build_dip_caption(call, x_val, cur_mc, include_promo=False)
        promo_separate = True
    fid, ftype = media["file_id"], media.get("type", "video")
    posted = False
    if userbot_client:
        try:
            msg = await asyncio.wait_for(
                _userbot_send_media_with_emoji(bot, TARGET_CHANNEL, fid, ftype,
                                               caption, emoji_ids),
                timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
            if msg is not None:
                posted = True
        except Exception as e:
            logger.warning(f"dip alert userbot send failed {x_val}x {call_key}: {e}")
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
            logger.warning(f"dip alert bot send failed {x_val}x {call_key}: {e}")
    if posted:
        _dip_clear_pending(call_key, x_val)
        if promo_separate:
            await _dip_send_promo_followup(bot, dip_promo_html())
        logger.info(f"Dip alert posted: {x_val}x {call_key}")
        return True
    _dip_add_pending(call_key, x_val, cur_mc)
    return False


async def _dip_check_tick(bot, call_key, call, cur_mc):
    if not dip_enabled():
        return
    try:
        entry_mc = float(call.get("entry_mc") or 0)
        cur_mc = float(cur_mc or 0)
    except (TypeError, ValueError):
        return
    if entry_mc <= 0 or cur_mc <= 0:
        return
    threshold = dip_threshold_pct()
    dip_low = call.get("dip_low")
    try:
        dip_low = float(dip_low) if dip_low else 0.0
    except (TypeError, ValueError):
        dip_low = 0.0
    # Dip low = ABSOLUTE lowest MC after entry, however deep it goes
    # (Kolscope example: called 100K, dipped to 1K, pumped to 500K -> dip
    # alerts up to 500x from the 1K low). A dip counts once MC falls
    # threshold% below entry; a small wobble must never become a "dip".
    # Two guards before a low is trusted (OWED dust lesson):
    #  1) Dust guard: lows below 0.1% of entry are ignored (likely a glitch
    #     read, e.g. a dust price locking a $3 entry).
    #  2) Confirmation: the low must be seen twice near the same level
    #     (a single-tick read never sets the low). check_one already feeds
    #     this function only verified live MC (FDV guard + spike-glitch
    #     guard + entry gate), and this second sighting rules out a
    #     one-tick bad read.
    if cur_mc <= entry_mc * (1.0 - threshold / 100.0):
        if cur_mc >= entry_mc * DIP_DUST_FLOOR_FRAC:
            cand = call.get("_dip_low_candidate")
            try:
                cand = float(cand) if cand else 0.0
            except (TypeError, ValueError):
                cand = 0.0
            if cand <= 0 or cur_mc < cand:
                call["_dip_low_candidate"] = cur_mc
                call["_dip_low_candidate_ticks"] = 1
            elif cur_mc <= cand * 1.05:
                call["_dip_low_candidate_ticks"] = int(call.get("_dip_low_candidate_ticks") or 0) + 1
            else:
                call["_dip_low_candidate"] = cur_mc
                call["_dip_low_candidate_ticks"] = 1
            if int(call.get("_dip_low_candidate_ticks") or 0) >= DIP_LOW_CONFIRM_TICKS:
                cand = float(call.get("_dip_low_candidate") or 0)
                if cand > 0:
                    dip_low = cand if dip_low <= 0 else min(dip_low, cand)
                    call["dip_low"] = dip_low
                    # Multi-dip cycle: a new low 20%+ below the low the
                    # current sent list belongs to restarts the alert cycle,
                    # so 2x, 3x... can fire again from the deeper low.
                    # A smaller new low does NOT reset (no duplicates).
                    try:
                        cycle_low = float(call.get("dip_low_at_alert") or 0)
                    except (TypeError, ValueError):
                        cycle_low = 0.0
                    if cycle_low <= 0:
                        call["dip_low_at_alert"] = cand
                    elif cand <= cycle_low * DIP_RESET_BELOW_FRAC:
                        call["sent_dip_milestones"] = []
                        call["pending_dip"] = []
                        call.pop("dip_pending_mc", None)
                        call["dip_low_at_alert"] = cand
                        logger.info(f"Dip cycle reset {call_key}: new low "
                                    f"{fmt_mc(cand)} is 20%+ below cycle low "
                                    f"{fmt_mc(cycle_low)} - sent dip milestones cleared")
                call.pop("_dip_low_candidate", None)
                call.pop("_dip_low_candidate_ticks", None)
    if dip_low <= 0:
        return
    dip_ratio = cur_mc / dip_low
    if dip_ratio < 2:
        return
    sent = _dip_sent_levels(call)
    due = [m for m in dip_milestones_for_ratio(dip_ratio) if m not in sent]
    if not due:
        return
    due.sort()
    for ms in due:
        sent.append(int(ms))
        _save_tracked()
        ok = await send_dip_alert(bot, call_key, call, ms, cur_mc)
        if ok:
            logger.info(f"Dip alert posted: {ms}X {call_key} "
                        f"(dip {dip_ratio:.1f}x from {fmt_mc(dip_low)})")
        else:
            logger.info(f"Dip alert held: {ms}X {call_key} "
                        f"(no media or send failed, will retry)")
        if len(due) > 1:
            await asyncio.sleep(0.3)


async def pending_dip_media_job(context):
    try:
        if not dip_enabled():
            return
        for call_key, call in list(tracked_calls.items()):
            pending = sorted(int(x) for x in (call.get("pending_dip") or []))
            if not pending:
                continue
            ready = [x for x in pending if dip_media_for(x)]
            if not ready:
                continue
            top = max(ready)
            mc_map = call.get("dip_pending_mc") or {}
            try:
                mc = float(mc_map.get(str(top)) or 0)
            except (TypeError, ValueError):
                mc = 0.0
            if mc <= 0:
                try:
                    dip_low = float(call.get("dip_low") or 0)
                except (TypeError, ValueError):
                    dip_low = 0.0
                mc = dip_low * top if dip_low > 0 else 0.0
            try:
                ok = await send_dip_alert(context.bot, call_key, call, top, mc)
            except Exception as e:
                logger.error(f"pending_dip_media_job send failed {top}x {call_key}: {e}")
                continue
            if ok:
                logger.info(f"Released held dip alert: {top}X {call_key}")
            await asyncio.sleep(0.3)
    except Exception as e:
        logger.error(f"pending_dip_media_job: {e}")


'''

XALERT_HOOK = r'''                # -- DIP PROFIT (DIP_PROFIT_NOV22) --
                # Dip low track karo aur due dip milestones fire karo. Normal
                # X milestones se bilkul alag: apna media, apna template,
                # koi points nahi. Entry gate se guzar chuka hai yahan tak.
                try:
                    await _dip_check_tick(bot, call_key, call, cur_mc)
                except Exception as _e_dip:
                    logger.warning(f"dip check skipped {call_key}: {_e_dip}")
'''

CMDS_PANEL = r'''    "dip": ("📉 Dip Setting",
        "📉 <b>DIP SETTING — DIP PROFIT ALERTS</b>\n"
        "(dip ke neeche se upar jaane par X alert)\n\n"
        "🎬 <b>Dip media (har X level ki apni GIF/video)</b>\n"
        "/setdipmedia 5 - us X ka media set (GIF/video bhejo)\n"
        "/cleardipmedia 5 · /listdipmedia\n"
        "ℹ️ Jis X ka media set nahi, uski dip alert HOLD rehti hai - media set karte hi khud post ho jayegi. Text-only post kabhi nahi hoti.\n\n"
        "🔗 <b>Promo link (sirf dip alerts me lagta hai)</b>\n"
        "/setdippromo - promo message bhejo (bold/italic/mono, premium emoji, quote - jaisa bhejoge waisa hi lagega)\n"
        "/showdippromo · /cleardippromo\n\n"
        "⚙️ <b>Setting</b>\n"
        "/setdipthreshold 30 - dip kitna % neeche jaye to count ho (default 30)\n"
        "/dipon · /dipoff - dip alerts on/off (default on)\n"
        "/showdipset - saari dip settings dekho\n\n"
        "🧪 <b>Test</b>\n"
        "/testdip 5 - preview DM me (kuch record nahi hota)",
        [("🎬 Dip media set karo", "oh:tip:setdipmedia"),
         ("🔗 Promo set karo", "oh:tip:setdippromo"),
         ("⚙️ Settings dekho", "oh:tip:showdipset")]),
'''

CMDS_TUTORIALS = r'''    'dip': [
        ('setdipmedia', 'Dip X level ka media set karo. Command ke baad GIF ya video bhejo.\nUsage: /setdipmedia 5'),
        ('listdipmedia', 'Kin dip X levels ka media set hai, list dekho.\nUsage: /listdipmedia'),
        ('cleardipmedia', 'Ek dip X level ka media hatao.\nUsage: /cleardipmedia 5'),
        ('setdippromo', 'Dip alerts ke neeche lagne wala promo message set karo. Bold/italic/mono, premium emoji, quote - jaisa bhejoge waisa hi lagega. Sirf dip alerts me lagta hai.\nUsage: /setdippromo'),
        ('showdippromo', 'Abhi ka dip promo dekho.\nUsage: /showdippromo'),
        ('cleardippromo', 'Dip promo hatao.\nUsage: /cleardippromo'),
        ('setdipthreshold', 'Dip kitna % neeche jaye to count ho. Default 30.\nUsage: /setdipthreshold 30'),
        ('dipon', 'Dip alerts on karo.\nUsage: /dipon'),
        ('dipoff', 'Dip alerts off karo.\nUsage: /dipoff'),
        ('showdipset', 'Saari dip settings dekho - status, threshold, media, promo.\nUsage: /showdipset'),
        ('testdip', 'Dip X alert ka preview DM me bhejo. Kuch record nahi hota. Media set na ho to text preview bhejta hai.\nUsage: /testdip 5 [@channel] [token]'),
    ],
'''

CMDS_FUNCS = r'''
# DIP PROFIT commands (DIP_PROFIT_NOV22) - /setdipmedia, /listdipmedia,
# /cleardipmedia, /setdippromo, /showdippromo, /cleardippromo,
# /setdipthreshold, /dipon, /dipoff, /showdipset, /testdip
@owner_only
async def cmd_setdipmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setdipmedia <X>\nExample: /setdipmedia 5"); return
    try:
        x = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ X number hona chahiye, jaise /setdipmedia 5"); return
    if x < 2:
        await update.message.reply_text("❌ X kam se kam 2 hona chahiye."); return
    owner_edit_state[update.effective_user.id] = {"state": ST_DIP_MEDIA, "level": x}
    await update.message.reply_text(f"🎬 {x}X dip alert ke liye GIF ya video bhejo:")


@owner_only
async def cmd_listdipmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    media = cfg_get("dip_media", {}) or {}
    if not media:
        await update.message.reply_text("Koi dip media set nahi. /setdipmedia <X> se set karo."); return
    def _k(v):
        try:
            return int(v[0])
        except Exception:
            return 0
    lines = [f"✅ <b>{k}X</b> — {v.get('type', 'video')}" for k, v in sorted(media.items(), key=_k)]
    await update.message.reply_text("🎬 <b>Dip Media:</b>\n\n" + "\n".join(lines), parse_mode="HTML")


@owner_only
async def cmd_cleardipmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /cleardipmedia <X>"); return
    x = str(context.args[0])
    c = load_config()
    media = c.get("dip_media", {}) or {}
    if x in media:
        del media[x]
        c["dip_media"] = media
        save_config(c)
        await update.message.reply_text(f"✅ {x}X ka dip media hata diya.")
    else:
        await update.message.reply_text(f"{x}X ka koi dip media set nahi tha.")


@owner_only
async def cmd_setdippromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_edit_state[update.effective_user.id] = {"state": ST_DIP_PROMO}
    await update.message.reply_text(
        "🔗 <b>Dip promo link set karo</b>\n\n"
        "Ab promo message bhejo - bold, italic, mono, premium emoji, quote, sab chalega. "
        "Jaisa bhejoge, dip X alerts me waisa hi lagega (sirf dip alerts me).\n\n"
        "(/cancel se rok sakte ho)", parse_mode="HTML")


@owner_only
async def cmd_showdippromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = load_config().get("dip_promo") or {}
    html_text = (p.get("html") or "").strip() if isinstance(p, dict) else ""
    if not html_text:
        await update.message.reply_text("Koi dip promo set nahi. /setdippromo se set karo."); return
    await update.message.reply_text("🔗 <b>Dip promo (abhi ka):</b>\n\n" + html_text, parse_mode="HTML")


@owner_only
async def cmd_cleardippromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = load_config()
    if c.get("dip_promo"):
        c["dip_promo"] = {}
        save_config(c)
        await update.message.reply_text("✅ Dip promo hata diya.")
    else:
        await update.message.reply_text("Dip promo pehle se set nahi tha.")


@owner_only
async def cmd_setdipthreshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setdipthreshold <pct>\nExample: /setdipthreshold 30"); return
    try:
        v = float(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Number bhejo, jaise /setdipthreshold 30"); return
    if not (1 <= v <= 50):
        await update.message.reply_text("❌ Threshold 1 se 50 % ke darmiyan hona chahiye."); return
    cfg_set("dip_threshold_pct", v)
    await update.message.reply_text(
        f"✅ Dip threshold set: <b>{v:g}%</b> - MC entry se itna % neeche jaye to dip count hoga.",
        parse_mode="HTML")


@owner_only
async def cmd_dipon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg_set("dip_enabled", True)
    await update.message.reply_text("✅ Dip alerts ON ho gayi.")


@owner_only
async def cmd_dipoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg_set("dip_enabled", False)
    await update.message.reply_text("⏸️ Dip alerts OFF ho gayi. (Pehle se park hui alerts bhi ruk jayengi.)")


@owner_only
async def cmd_showdipset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = load_config()
    media = c.get("dip_media", {}) or {}
    promo = c.get("dip_promo") or {}
    promo_txt = (promo.get("html", "") or "").strip() if isinstance(promo, dict) else ""
    thr = c.get("dip_threshold_pct", 30)
    enabled = c.get("dip_enabled", True)
    levels = sorted(media.keys(), key=lambda k: int(k) if str(k).isdigit() else 0)
    media_txt = ", ".join(f"{k}X" for k in levels) if levels else "koi nahi"
    await update.message.reply_text(
        "📉 <b>Dip Setting</b>\n\n"
        f"Status: <b>{'ON' if enabled else 'OFF'}</b>\n"
        f"Dip threshold: <b>{thr}%</b>\n"
        f"Media: <b>{media_txt}</b>\n"
        f"Promo link: <b>{'set hai' if promo_txt else 'set nahi'}</b>\n\n"
        "Media: /setdipmedia X · /listdipmedia · /cleardipmedia X\n"
        "Promo: /setdippromo · /showdippromo · /cleardippromo\n"
        "Threshold: /setdipthreshold PCT · On/Off: /dipon · /dipoff\n"
        "Test: /testdip X [@channel] [token]",
        parse_mode="HTML")


@owner_only
async def cmd_testdip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        xv = int(context.args[0]) if context.args else 5
    except (ValueError, IndexError):
        xv = 5
    if xv < 2:
        await update.message.reply_text("❌ X kam se kam 2 hona chahiye.\nExample: /testdip 5"); return
    args = list(context.args[1:] if len(context.args) > 1 else [])
    channel = args[0].lstrip("@") if args else "TestChannel"
    token = args[1].upper() if len(args) > 1 else "TEST"
    entry_mc = 74900.0
    cur_mc = 264700.0
    dip_low = cur_mc / xv if xv > 0 else cur_mc
    fake_call = {"channel": channel, "symbol": token, "chain": "SOL",
                 "entry_mc": entry_mc, "dip_low": dip_low,
                 "ca": "TestCA123", "msg_id": 1}
    caption = build_dip_caption(fake_call, xv, cur_mc, include_promo=True)
    media = dip_media_for(xv)
    await update.message.reply_text(
        f"👀 <b>Dip preview {xv}X</b> - @{html.escape(channel)} ${html.escape(token)}\n"
        f"(sirf preview, kuch record nahi hua)", parse_mode="HTML")
    if not media:
        await update.message.reply_text(
            f"⚠️ <b>Media missing:</b> {xv}X ka dip media set nahi hai "
            f"(/setdipmedia {xv} se set karo). Text preview:\n\n{caption}",
            parse_mode="HTML")
        return
    fid, ftype = media["file_id"], media.get("type", "video")
    try:
        if ftype == "photo":
            await update.message.reply_photo(photo=fid, caption=caption, parse_mode="HTML")
        elif ftype == "gif":
            await update.message.reply_animation(animation=fid, caption=caption, parse_mode="HTML")
        else:
            await update.message.reply_video(video=fid, caption=caption, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Media send fail ho gaya ({html.escape(str(e))}). Text preview:\n\n{caption}",
            parse_mode="HTML")
'''

RUNTIME_STATES = r'''        elif state == ST_DIP_MEDIA:
            x = si.get("level")
            if msg.animation: fid, ftype = msg.animation.file_id, "gif"
            elif msg.video: fid, ftype = msg.video.file_id, "video"
            elif msg.photo: fid, ftype = msg.photo[-1].file_id, "photo"
            else: await msg.reply_text("⚠️ GIF ya video bhejo."); return
            c = load_config(); media = c.get("dip_media", {}) or {}
            media[str(x)] = {"type": ftype, "file_id": fid}
            c["dip_media"] = media; save_config(c)
            owner_edit_state[uid] = {"state": None}
            await msg.reply_text(f"✅ {ftype.capitalize()} saved for {x}X dip alert! "
                                 f"Ab {x}X dip level par yehi media post hogi."); return

        elif state == ST_DIP_PROMO:
            text_val = msg.text or msg.caption
            if not text_val:
                await msg.reply_text("⚠️ Promo message bhejo (text)."); return
            html_text = msg.text_html if msg.text else (msg.caption_html or "")
            c = load_config()
            c["dip_promo"] = {"html": html_text, "text": text_val}
            save_config(c)
            owner_edit_state[uid] = {"state": None}
            await msg.reply_text("✅ Dip promo save ho gaya! Ab har dip X alert ke neeche yehi promo lagega, "
                                 "jaisa tumne bheja tha waisa hi.", parse_mode="HTML"); return

'''

RUNTIME_JOB = r'''    app.job_queue.run_repeating(pending_dip_media_job, interval=15,        first=25)   # DIP_PROFIT_NOV22: release held dip alerts once media is uploaded
'''

RUNTIME_HANDLERS = r'''    app.add_handler(CommandHandler("setdipmedia",    cmd_setdipmedia))
    app.add_handler(CommandHandler("listdipmedia",   cmd_listdipmedia))
    app.add_handler(CommandHandler("cleardipmedia",  cmd_cleardipmedia))
    app.add_handler(CommandHandler("setdippromo",    cmd_setdippromo))
    app.add_handler(CommandHandler("showdippromo",   cmd_showdippromo))
    app.add_handler(CommandHandler("cleardippromo",  cmd_cleardippromo))
    app.add_handler(CommandHandler("setdipthreshold", cmd_setdipthreshold))
    app.add_handler(CommandHandler("dipon",          cmd_dipon))
    app.add_handler(CommandHandler("dipoff",         cmd_dipoff))
    app.add_handler(CommandHandler("showdipset",     cmd_showdipset))
    app.add_handler(CommandHandler("testdip",        cmd_testdip))
'''


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


def _edit_core(lines):
    i = _find_line(lines, "ST_SET_HS_MEDIA", "core.py", "ST_SET_HS_MEDIA definition")
    return _insert_after(lines, i, CORE_STATES)


def _edit_xalert_engine(lines):
    i = _find_line(lines, "def call_peak_ratio(call):", "x_alert.py", "call_peak_ratio def")
    return _insert_before(lines, i, XALERT_ENGINE + XALERT_ENGINE_2)


def _edit_xalert_hook(lines):
    i = _find_line(lines, "Which milestones fire on this tick?", "x_alert.py",
                   "milestone section in check_one")
    return _insert_before(lines, i, XALERT_HOOK)


def _edit_cmds_panel(lines):
    i = _find_line(lines, '"oh:tip:ask"', "commands.py", "ai panel ask button")
    return _insert_after(lines, i, CMDS_PANEL)


def _edit_cmds_tutorials(lines):
    i = _find_line(lines, "AI intro text wapas default par kar do", "commands.py",
                   "ai tutorials last entry")
    j = None
    for k in range(i + 1, len(lines)):
        if lines[k].rstrip("\n") == "    ],":
            j = k
            break
    if j is None:
        raise AnchorError("commands.py: closing '    ],' after ai tutorials not found")
    return _insert_after(lines, j, CMDS_TUTORIALS)


def _edit_cmds_funcs(lines):
    i = _find_line(lines, "async def cmd_editbutton", "commands.py", "cmd_editbutton def")
    j = i
    while j > 0 and (lines[j - 1].strip() == "" or lines[j - 1].lstrip().startswith("@")):
        j -= 1
    return _insert_before(lines, j, CMDS_FUNCS)


def _edit_runtime_states(lines):
    i = _find_line(lines, "elif state == ST_SET_HS_MEDIA:", "runtime.py",
                   "ST_SET_HS_MEDIA branch")
    return _insert_before(lines, i, RUNTIME_STATES)


def _edit_runtime_job(lines):
    i = _find_line(lines, "run_repeating(pending_media_job,", "runtime.py",
                   "pending_media_job schedule")
    return _insert_after(lines, i, RUNTIME_JOB)


def _edit_runtime_handlers(lines):
    i = _find_line(lines, 'CommandHandler("setmedia"', "runtime.py", "setmedia handler")
    return _insert_after(lines, i, RUNTIME_HANDLERS)


EDITS = {
    "core.py": [_edit_core],
    "x_alert.py": [_edit_xalert_engine, _edit_xalert_hook],
    "commands.py": [_edit_cmds_panel, _edit_cmds_tutorials, _edit_cmds_funcs],
    "runtime.py": [_edit_runtime_states, _edit_runtime_job, _edit_runtime_handlers],
}


def main():
    print(f"DIP_PROFIT_NOV22 patch - target dir: {BOT_DIR}")
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
    print("Then verify: systemctl status bot.service --no-pager | head -5")
    if skipped:
        print(f"Skipped (already patched): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
