# bot.py — entry point. Loads the pieces below, in order, into ONE shared namespace.
# (Same behaviour as the old single file; "global" variables keep working.)
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_PIECES = ["core", "launchpad", "dropped_call", "x_alert", "leaderboard", "commands", "runtime"]
for _name in _PIECES:
    _path = _os.path.join(_HERE, _name + ".py")
    with open(_path, encoding="utf-8") as _f:
        exec(compile(_f.read(), _path, "exec"), globals())


# ═══════════════════════════════════════════════════════════════════════════
# MOST SHARED TOKENS — har 24 ghante baad TARGET_CHANNEL me video post:
# pichle 24h me sabse zyada alag-alag channels ne jo token call kiya (top 10).
# Renderer: most_shared.py. Sab kuch yahin (bot.py) me hai, baqi files ko haath nahi lagaya.
# Env: MOST_SHARED_ENABLED=1, MOST_SHARED_INTERVAL_HOURS=24, MOST_SHARED_MIN_CHANNELS=2,
#      MOST_SHARED_MODE=video|image
# Owner commands: /mostshared (preview DM me) · /mostshared post (abhi channel me) ·
#                 /mostshared on|off
# ═══════════════════════════════════════════════════════════════════════════
import asyncio as _ms_asyncio

_MS_LOGO_CACHE = {}
_MS_GT_NET = {"SOL": "solana", "ETH": "eth", "EVM": "eth", "BNB": "bsc", "BSC": "bsc", "BASE": "base",
              "TRX": "tron", "TON": "ton", "ARB": "arbitrum", "AVAX": "avax", "POLY": "polygon_pos"}


def _ms_collect_rows(hours=24, min_channels=2, limit=10):
    now = datetime.utcnow()
    groups = {}
    for _k, c in list(tracked_calls.items()):
        try:
            if not isinstance(c, dict) or not _ex_valid(c):
                continue
            ts = _ex_ts(c)
            if ts is None or now - ts > timedelta(hours=hours):
                continue
            ca = str(c.get("ca") or "").strip()
            if not ca:
                continue
            groups.setdefault(ca.lower(), []).append((ts, c))
        except Exception:
            continue
    rows = []
    for _ca, lst in groups.items():
        lst.sort(key=lambda x: x[0])
        chans = {_ex_norm_channel(c.get("channel")) for _t, c in lst}
        chans.discard("")
        if len(chans) < max(1, min_channels):
            continue
        first = lst[0][1]
        from_mc = float(first.get("entry_mc") or 0)
        ath = 0.0
        for _t, c in lst:
            try:
                pm = float(c.get("peak_mc") or 0)
                if pm <= 0:
                    pm = float(c.get("entry_mc") or 0) * float(c.get("peak_ratio") or 1)
                ath = max(ath, pm)
            except Exception:
                pass
        ath = max(ath, from_mc)
        sym = next((str(c.get("symbol")).strip() for _t, c in lst if str(c.get("symbol") or "").strip()), "")
        chain = next((str(c.get("chain")) for _t, c in lst if str(c.get("chain") or "").upper() not in ("", "EVM")),
                     str(first.get("chain") or "SOL"))
        order = []
        for _t, c in lst:
            n = _ex_norm_channel(c.get("channel"))
            if n and n not in order:
                order.append(n)
        rows.append({"symbol": sym or first.get("ca", "")[:5], "chain": chain, "channels": len(chans),
                     "chans": order, "first_chan": order[0] if order else "",
                     "ath_mc": ath, "from_mc": from_mc, "mult": (ath / from_mc) if from_mc > 0 else 1.0,
                     "ca": first.get("ca"), "first_ts": lst[0][0].isoformat()})
    rows.sort(key=lambda r: (-r["channels"], -r["mult"], -r["ath_mc"]))
    return rows[:limit]


def _ms_fetch_logo_sync(ca, chain):
    """Token ki photo: DexScreener info.imageUrl, phir GeckoTerminal. bytes ya None."""
    if not ca:
        return None
    if ca in _MS_LOGO_CACHE:
        return _MS_LOGO_CACHE[ca]
    urls = []
    try:
        d = _dex_get(f"https://api.dexscreener.com/latest/dex/tokens/{ca}", timeout=6, lane="single")
        if isinstance(d, dict):
            pairs = [p for p in (d.get("pairs") or []) if isinstance(p, dict)]
            pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), reverse=True)
            for p in pairs:
                bt = str((p.get("baseToken") or {}).get("address") or "").lower()
                u = (p.get("info") or {}).get("imageUrl")
                if u and bt == ca.lower():
                    urls.append(u)
                    break
    except Exception:
        pass
    try:
        net = _MS_GT_NET.get(str(chain).upper(), "solana" if not ca.startswith("0x") else "eth")
        r = requests.get(f"https://api.geckoterminal.com/api/v2/networks/{net}/tokens/{ca}", timeout=6,
                         headers={"accept": "application/json"})
        if r.status_code == 200:
            u = (((r.json() or {}).get("data") or {}).get("attributes") or {}).get("image_url")
            if u and "missing" not in u:
                urls.append(u)
    except Exception:
        pass
    for u in urls:
        try:
            r = requests.get(u, timeout=8)
            if r.status_code == 200 and 200 < len(r.content) < 3_000_000:
                if len(_MS_LOGO_CACHE) > 300:
                    _MS_LOGO_CACHE.clear()
                _MS_LOGO_CACHE[ca] = r.content
                return r.content
        except Exception:
            continue
    return None


_MS_PREMIUM_ID = int(os.environ.get("MOST_SHARED_EMOJI_ID", "5888670372093502546") or 5888670372093502546)  # PE_CRYSTAL


def _ms_caption(rows, hours=24, premium=False):
    lines = [f"🔮 <b>MOST SHARED TOKENS — Last {hours}H</b>", "",
             f"Details of the most shared projects in the last {hours} hours.", ""]
    for i, r in enumerate(rows, 1):
        lines.append(f"🔮 <b>${html.escape(str(r['symbol']).upper())}</b>  🔮  {r['channels']} CHANNELS")
        if i == 5 and len(rows) > 5:
            lines.append("")
    lines += ["", "Click the “Check Record” button for more details.", "",
              "📔 Tracked by @WizardScan"]
    txt = "\n".join(lines)
    if premium:
        # har 🔮 ko premium (custom) emoji bana do — userbot path
        return txt.replace("🔮", f'<tg-emoji emoji-id="{_MS_PREMIUM_ID}">🔮</tg-emoji>')
    return txt[:1024]


async def _ms_send_userbot(chat_id, path, cap_html, kb, is_video, duration=0, w=0, h=0):
    """Userbot se premium emoji wali post (baqi alerts ki tarah). Message ya None."""
    if not userbot_client:
        return None
    try:
        from telethon.extensions.html import parse as _tl_parse
        text, explicit = prepare_owner_emojis(cap_html)
        plain, base = _tl_parse(text)
        ents = _build_premium_entities(plain, base, _MS_PREMIUM_ID, explicit=explicit)
        kw = dict(caption=plain, formatting_entities=ents, buttons=_tl_buttons_from_keyboard(kb))
        if is_video:
            from telethon.tl.types import DocumentAttributeVideo
            kw["supports_streaming"] = True
            kw["attributes"] = [DocumentAttributeVideo(duration=int(duration), w=int(w), h=int(h),
                                                       supports_streaming=True)]
        return await userbot_client.send_file(chat_id, path, **kw)
    except Exception as e:
        logger.warning(f"most_shared userbot send failed, Bot API fallback: {e!r}")
        return None


_MS_SNAP_FILE = _dp("most_shared_last.json")
_MS_BOT_USERNAME = {}


async def _ms_keyboard(bot):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    un = _MS_BOT_USERNAME.get("u")
    if not un:
        un = (await bot.get_me()).username
        _MS_BOT_USERNAME["u"] = un
    return InlineKeyboardMarkup([[InlineKeyboardButton("📔 Check Record", url=f"https://t.me/{un}?start=mostshared")]])


def _ms_save_snapshot(rows):
    try:
        snap = [{k: v for k, v in r.items() if k != "logo"} for r in rows]
        save_json(_MS_SNAP_FILE, {"saved_at": datetime.utcnow().isoformat(), "rows": snap})
    except Exception as e:
        logger.warning(f"most_shared snapshot save failed: {e!r}")


def _ms_load_snapshot():
    try:
        d = load_json(_MS_SNAP_FILE, {})
        rows = d.get("rows") or []
        return rows if rows else None
    except Exception:
        return None


def _ms_ago(iso):
    try:
        sec = max(0, (datetime.utcnow() - datetime.fromisoformat(str(iso))).total_seconds())
    except Exception:
        return ""
    if sec >= 3600:
        return f"{int(sec // 3600)}h {int(sec % 3600 // 60)}m ago"
    return f"{max(1, int(sec // 60))}m ago"


_MS_DEX_SLUG = {"SOL": "solana", "ETH": "ethereum", "EVM": "ethereum", "BNB": "bsc", "BSC": "bsc", "BASE": "base",
                "RH": "robinhood", "TON": "ton"}


def _ms_details(rows):
    """-> (list of HTML messages, InlineKeyboardMarkup of chart buttons)"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    blocks = []
    for i, r in enumerate(rows, 1):
        sym = html.escape(str(r.get("symbol") or "?").upper())
        chans = [html.escape(c) for c in (r.get("chans") or [])]
        shown = ", ".join("@" + c for c in chans[:4]) + (f" +{len(chans) - 4} more" if len(chans) > 4 else "")
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"#{i}")
        blk = [f"{medal} <b>${sym}</b>  ·  {html.escape(str(r.get('chain') or ''))}",
               f"📣 <b>{r.get('channels', 0)}</b> channels called it",
               f"🚀 {_ms_fmt_mc(r.get('from_mc'))} → ATH <b>{_ms_fmt_mc(r.get('ath_mc'))}</b>  ·  <b>{float(r.get('mult') or 1):.1f}x</b>"]
        if r.get("first_chan"):
            blk.append(f"⏱ First call: @{html.escape(r['first_chan'])} · {_ms_ago(r.get('first_ts'))}")
        if shown:
            blk.append(f"👥 {shown}")
        if r.get("ca"):
            blk.append(f"📋 <code>{html.escape(str(r['ca']))}</code>")
        blocks.append("\n".join(blk))
    head = "🔮 <b>MOST SHARED TOKENS — Record</b>\n<i>Last 24H · channels, ATH & first calls</i>"
    foot = "📔 Tracked by @WizardScan"
    sep = "\n\n〰️〰️〰️〰️〰️〰️\n\n"
    msgs, cur = [], head + "\n\n"
    for b in blocks:
        if len(cur) + len(b) + len(sep) > 3800:
            msgs.append(cur.rstrip("〰️\n "))
            cur = ""
        cur += b + sep
    msgs.append(cur.rstrip("〰️\n ") + "\n\n" + foot)
    btns = []
    for r in rows:
        if r.get("ca"):
            slug = _MS_DEX_SLUG.get(str(r.get("chain")).upper())
            url = f"https://dexscreener.com/{slug}/{r['ca']}" if slug else f"https://dexscreener.com/search?q={r['ca']}"
            btns.append(InlineKeyboardButton(f"📈 ${str(r.get('symbol') or '?').upper()}"[:24], url=url))
    kb = InlineKeyboardMarkup([btns[i:i + 2] for i in range(0, len(btns), 2)]) if btns else None
    return msgs, kb


async def _ms_start(update, context):
    """/start mostshared  (Check Record button) — baaki /start payloads ko haath nahi lagata."""
    if not context.args or str(context.args[0]).lower() != "mostshared":
        return
    from telegram.ext import ApplicationHandlerStop
    try:
        user = update.effective_user
        add_user(user.id, user.username, user.first_name)
    except Exception:
        pass
    rows = _ms_load_snapshot()
    if not rows:
        min_ch = int(os.environ.get("MOST_SHARED_MIN_CHANNELS", "2") or 2)
        rows = await _ms_asyncio.to_thread(_ms_collect_rows, 24, min_ch, 10)
    if not rows:
        await update.message.reply_text("Abhi record available nahi hai. Thodi der baad try karo.")
    else:
        msgs, kb = _ms_details(rows)
        for i, m in enumerate(msgs):
            await update.message.reply_text(m, parse_mode="HTML", disable_web_page_preview=True,
                                            reply_markup=(kb if i == len(msgs) - 1 else None))
    raise ApplicationHandlerStop


def _ms_fmt_mc(v):
    v = float(v or 0)
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.2f}M"
    if v >= 1e3: return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


async def _ms_build_and_send(bot, chat_id, mode="video", preview=False):
    """Returns (ok, info_text)."""
    import most_shared as _msr
    min_ch = int(os.environ.get("MOST_SHARED_MIN_CHANNELS", "2") or 2)
    rows = await _ms_asyncio.to_thread(_ms_collect_rows, 24, min_ch, 10)
    if not rows:
        return False, "Pichle 24h me koi token 2+ channels ne call nahi kiya."
    logos = await _ms_asyncio.gather(*[_ms_asyncio.to_thread(_ms_fetch_logo_sync, r.get("ca"), r.get("chain"))
                                       for r in rows], return_exceptions=True)
    for r, lg in zip(rows, logos):
        r["logo"] = lg if isinstance(lg, (bytes, bytearray)) else None
    cap = _ms_caption(rows)
    cap_prem = _ms_caption(rows, premium=True)
    use_userbot = (not preview) and str(chat_id) == str(TARGET_CHANNEL) and userbot_client is not None
    if not preview:
        _ms_save_snapshot(rows)
    try:
        kb = await _ms_keyboard(bot)
    except Exception:
        kb = None
    sent = False
    if mode == "video":
        path = await _msr.build_video_async(rows, timeout=150)
        if path and use_userbot:
            dur = int(round(_msr.PAGE_S * (2 if len(rows) > 5 else 1)))
            if await _ms_send_userbot(chat_id, path, cap_prem, kb, True, dur, _msr.VW, _msr.VH) is not None:
                sent = True
        if path and not sent:
            with open(path, "rb") as fh:
                await bot.send_video(chat_id, video=fh, caption=cap, parse_mode="HTML",
                                     width=_msr.VW, height=_msr.VH, duration=int(round(
                                         _msr.PAGE_S * (2 if len(rows) > 5 else 1))),
                                     supports_streaming=True, read_timeout=120, write_timeout=120,
                                     reply_markup=kb)
            sent = True
    if not sent:
        path = await _msr.build_image_async(rows, timeout=60)
        if path and use_userbot:
            if await _ms_send_userbot(chat_id, path, cap_prem, kb, False) is not None:
                sent = True
        if path and not sent:
            with open(path, "rb") as fh:
                await bot.send_photo(chat_id, photo=fh, caption=cap, parse_mode="HTML",
                                     read_timeout=60, write_timeout=60, reply_markup=kb)
            sent = True
    if not sent:
        await bot.send_message(chat_id, cap, parse_mode="HTML", reply_markup=kb)
    if preview:
        # preview me poster image bhi bhejo (design check)
        try:
            ip = await _msr.build_image_async(rows, timeout=60)
            if ip:
                with open(ip, "rb") as fh:
                    await bot.send_document(chat_id, document=fh, filename="most_shared.png")
        except Exception:
            pass
    return True, f"{len(rows)} tokens"


async def _ms_job(context):
    try:
        cfg = load_config()
        if not cfg.get("most_shared_enabled", os.environ.get("MOST_SHARED_ENABLED", "1") not in ("0", "false", "off")):
            return
        hrs = float(os.environ.get("MOST_SHARED_INTERVAL_HOURS", "24") or 24)
        last = cfg.get("last_most_shared_post")
        now = datetime.utcnow()
        if not last:
            cfg["last_most_shared_post"] = now.isoformat()      # pehli post 24h baad
            save_config(cfg)
            return
        try:
            last_dt = datetime.fromisoformat(str(last))
        except Exception:
            last_dt = now
        if now - last_dt < timedelta(hours=hrs):
            return
        # pehle time aage badhao (loop/duplicate se bachne ke liye); fail ho to 30 min me retry
        cfg["last_most_shared_post"] = (now - timedelta(hours=hrs) + timedelta(minutes=30)).isoformat()
        save_config(cfg)
        mode = os.environ.get("MOST_SHARED_MODE", "video").lower()
        ok, info = await _ms_build_and_send(context.bot, TARGET_CHANNEL, mode=mode)
        if ok:
            cfg = load_config()
            cfg["last_most_shared_post"] = datetime.utcnow().isoformat()
            save_config(cfg)
            logger.info(f"✅ Most Shared Tokens posted ({info})")
        else:
            cfg = load_config()
            cfg["last_most_shared_post"] = datetime.utcnow().isoformat()   # data nahi — agle 24h me dobara
            save_config(cfg)
            logger.info(f"Most Shared Tokens skipped: {info}")
    except Exception as e:
        logger.error(f"most_shared job failed: {e!r}")


@owner_only
async def cmd_mostshared(update, context):
    arg = (context.args[0].lower() if context.args else "")
    if arg in ("on", "off"):
        cfg = load_config()
        cfg["most_shared_enabled"] = (arg == "on")
        save_config(cfg)
        await update.message.reply_text(f"Most Shared auto-post: {arg.upper()}")
        return
    target = TARGET_CHANNEL if arg == "post" else update.effective_chat.id
    await update.message.reply_text("⏳ Bana raha hun (30-60s)…")
    try:
        ok, info = await _ms_build_and_send(context.bot, target, mode=os.environ.get("MOST_SHARED_MODE", "video").lower(),
                                            preview=(arg != "post"))
        if arg == "post" and ok:
            cfg = load_config()
            cfg["last_most_shared_post"] = datetime.utcnow().isoformat()
            save_config(cfg)
        await update.message.reply_text(("✅ " if ok else "⚠️ ") + info)
    except Exception as e:
        logger.error(f"cmd_mostshared failed: {e!r}")
        await update.message.reply_text(f"❌ Fail: {e!r}"[:300])


_ms_orig_post_init = post_init
_ms_installed = False


async def post_init(application):          # main() ye naam runtime pe dhoondta hai
    global _ms_installed
    try:
        await _ms_orig_post_init(application)
    finally:
        if not _ms_installed:
            _ms_installed = True
            try:
                from telegram.ext import CommandHandler as _MsCH
                application.add_handler(_MsCH("mostshared", cmd_mostshared), group=-1)
                application.add_handler(_MsCH("start", _ms_start), group=-1)
                application.job_queue.run_repeating(_ms_job, interval=60, first=120)
                logger.info("✅ Most Shared Tokens feature loaded (/mostshared)")
            except Exception as e:
                logger.error(f"most_shared install failed: {e!r}")


if __name__ == "__main__":
    main()
