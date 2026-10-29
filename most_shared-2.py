# most_shared.py — "MOST SHARED TOKENS — Last 24H" feature (bot.py piece, shared namespace).
#
# Flow:
#   every 24h (or /postmostshared) -> collect last-24h calls -> rank top 10 tokens by number of
#   distinct caller channels -> 8s video (most_shared_video.py) + post in @WizardScan with a
#   "Check Record" button -> video file deleted right after posting.
#   Button = deep link  t.me/<bot>?start=msr_<id>  -> bot replies with 2 record messages
#   (Top 1-5, Top 6-10) built from the snapshot saved at post time.
#
# Owner commands:  /postmostshared  (post to channel now)   /mostsharedtest  (preview in owner DM only)
# Auto posting: every day at 00:00 Turkey time (UTC+3), starting after the first successful /postmostshared
# (set MOST_SHARED_AUTO=0 in .env to switch it off).
import re as _ms_re
import time as _ms_time

MS_STATE_FILE      = _dp("most_shared_state.json")
MS_WINDOW_HOURS    = 24
MS_ROWS_PER_TOKEN  = 5
MS_CAPTION_LIMIT   = 1024

MS_EMO_HEADER = 5888670372093502546   # 🔮 MOST SHARED TOKENS (channel post + record header)
MS_EMO_TEER1  = 5820960526204675320   # rank 1-5 separator
MS_EMO_TEER2  = 5818848205453927129   # rank 6-10 separator
MS_EMO_BTN    = 6044166381690166762   # "Check Record" button icon
MS_EMO_FOOT   = 5846193940105012285   # replaces 🔎 in the record footer line

MS_CHAIN_1_5 = {"SOL": 5821384894743324105, "TON": 5821137045065572054, "BNB": 5821408568603058588,
                "ETH": 5821051253093834925, "RH": 5821306460050562617, "BASE": 5821088567769701396,
                "ARC": 5861917123885932251}
MS_CHAIN_6_10 = {"TON": 5866181502424850828, "BNB": 5866260216290483682, "ETH": 5865974768469026405,
                 "SOL": 5865982877367279051, "RH": 5866254272055747007, "BASE": 5866335262254047661,
                 "ARC": 5866195366579281407}
MS_CHAIN_ALIAS = {"BSC": "BNB", "SOLANA": "SOL", "ETHEREUM": "ETH"}

_ms_lock = None
import concurrent.futures as _ms_cf
_ms_pool = _ms_cf.ThreadPoolExecutor(max_workers=6, thread_name_prefix="most_shared")


async def _ms_run(fn, *args, timeout=60):
    """Run blocking work in OUR OWN thread pool (the bot's shared pool can be saturated by the scanners)."""
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(loop.run_in_executor(_ms_pool, lambda: fn(*args)), timeout=timeout)


# ───────────────────────── small helpers ─────────────────────────
def _ms_chain(chain):
    c = str(chain or "SOL").upper()
    return MS_CHAIN_ALIAS.get(c, c)


def _ms_chain_emoji(chain, rank):
    table = MS_CHAIN_1_5 if rank <= 5 else MS_CHAIN_6_10
    return table.get(_ms_chain(chain)) or table["SOL"]


def _ms_sym(s):
    s = str(s or "TOKEN").strip().lstrip("$").upper()
    return (s or "TOKEN")[:16]


def _ms_handle(ch):
    ch = str(ch or "").lstrip("@").strip()
    return "@" + (ch[:1].upper() + ch[1:] if ch else "Channel")


def _ms_mc(v):
    """150000 -> 150K, 5000000 -> 5M, 1340000 -> 1.34M, 950 -> 950"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "N/A"
    if v <= 0:
        return "N/A"
    for lim, suf, dec in ((1e9, "B", 2), (1e6, "M", 2), (1e3, "K", 1)):
        if v >= lim:
            s = f"{v / lim:.{dec}f}".rstrip("0").rstrip(".")
            return s + suf
    return f"{v:.0f}"


def _ms_x(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "1x"
    return f"{int(x)}x" if x >= 2 or abs(x - round(x)) < 1e-9 else f"{x:.1f}x"


def _ms_state():
    d = load_json(MS_STATE_FILE, {})
    return d if isinstance(d, dict) else {}


def _ms_save_state(d):
    save_json(MS_STATE_FILE, d)


# ───────────────────────── text builder (HTML for DMs + entities for the channel) ─────────────────────────
class _MsDoc:
    def __init__(self):
        self.seg = []      # dict(t, b, u, e)  or ("Q", +1/-1)

    def t(self, s, bold=False, url=None):
        if s:
            self.seg.append({"t": s, "b": bold, "u": url, "e": None})
        return self

    def e(self, emoji_id, fb="🔮"):
        self.seg.append({"t": fb, "b": False, "u": None, "e": int(emoji_id)})
        return self

    def q(self, open_=True):
        self.seg.append(("Q", 1 if open_ else -1))
        return self

    def html(self):
        out = []
        for s in self.seg:
            if isinstance(s, tuple):
                out.append("<blockquote>" if s[1] > 0 else "</blockquote>")
                continue
            if s["e"]:
                out.append(f'<tg-emoji emoji-id="{s["e"]}">{s["t"]}</tg-emoji>')
                continue
            x = html.escape(s["t"])
            if s["b"]:
                x = f"<b>{x}</b>"
            if s["u"]:
                x = f'<a href="{html.escape(s["u"], quote=True)}">{x}</a>'
            out.append(x)
        return "".join(out)

    def plain_entities(self):
        from telethon.tl.types import (MessageEntityBold, MessageEntityTextUrl,
                                       MessageEntityCustomEmoji, MessageEntityBlockquote)
        text, ents, off, qstart = [], [], 0, None
        for s in self.seg:
            if isinstance(s, tuple):
                if s[1] > 0:
                    qstart = off
                elif qstart is not None:
                    ents.append(MessageEntityBlockquote(offset=qstart, length=off - qstart))
                    qstart = None
                continue
            n = len(s["t"].encode("utf-16-le")) // 2
            if s["e"]:
                ents.append(MessageEntityCustomEmoji(offset=off, length=n, document_id=s["e"]))
            else:
                if s["b"]:
                    ents.append(MessageEntityBold(offset=off, length=n))
                if s["u"]:
                    ents.append(MessageEntityTextUrl(offset=off, length=n, url=s["u"]))
            text.append(s["t"])
            off += n
        return "".join(text), ents


# ───────────────────────── collect: last 24h -> ranked tokens ─────────────────────────
def _ms_call_stats(ck, call, archived=False):
    try:
        entry = float(call.get("entry_mc") or 0)
    except (TypeError, ValueError):
        entry = 0.0
    if archived:
        try:
            hx = int(call.get("best_x") or 0)
        except (TypeError, ValueError):
            hx = 0
        ratio = float(hx) if hx > 0 else 1.0
    else:
        ms = set(sent_milestones.get(ck, set()) or [])
        try:
            ms |= {int(x) for x in (pending_media_alerts.get(ck, set()) or [])}
        except Exception:
            pass
        hx = max(ms) if ms else 0
        ratio = call_peak_ratio(call)
    ratio = min(max(ratio, 0.0), 1000.0)
    if hx > 0 and ratio > hx * 3:          # phantom ratio from a bad price sample
        ratio = float(hx)
    if hx >= 2:
        x = float(hx)
    elif ratio >= 2:
        x = float(int(ratio))
    else:
        x = round(max(ratio, 1.0), 1)
    mult = max(ratio, float(hx), 1.0)
    try:
        pm = float(call.get("peak_mc") or 0)
    except (TypeError, ValueError):
        pm = 0.0
    if pm >= 1e9 or (entry > 0 and pm > entry * mult * 3):
        pm = 0.0                            # absurd peak -> ignore, derive from the confirmed multiple
    peak = max(pm, entry * mult if entry > 0 else 0.0)
    return {"x": x, "hx": hx, "entry": entry, "peak": peak, "ratio": ratio}


def _ms_alert_link(ck, hx):
    """Link of OUR X-alert post (WizardScan) for this call at its highest milestone."""
    posts = milestone_posts.get(ck) or {}
    if not posts:
        return None
    pid = posts.get(str(hx))
    if not pid:
        try:
            best = max(int(k) for k in posts if str(k).isdigit() and int(k) <= max(hx, 1))
            pid = posts.get(str(best))
        except ValueError:
            pid = None
    if pid:
        return f"https://t.me/{TARGET_CHANNEL.lstrip('@')}/{pid}"
    return None


def _ms_post_link(channel, msg_id):
    ch = str(channel or "").lstrip("@").strip()
    return f"https://t.me/{ch}/{msg_id}" if msg_id else f"https://t.me/{ch}"


def _ms_collect(now=None, top=10):
    """Pure data step (no network). Returns up to `top` token dicts ranked best-first."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=MS_WINDOW_HOURS)
    try:
        banned = load_global_ca_bans()
    except Exception:
        banned = set()
    groups = {}

    def _add(ck, call, archived):
        ca = str(call.get("ca") or "").strip()
        ch = str(call.get("channel") or "").strip()
        if not ca or not ch or ca.lower() in banned:
            return
        ts = _call_time(call)
        if ts is None or ts < cutoff:
            return
        st = _ms_call_stats(ck, call, archived)
        chain = _ms_chain(call.get("chain"))
        gk = ca.lower() if ca.startswith("0x") else ca
        g = groups.setdefault((chain, gk), {"chain": chain, "ca": ca, "symbol": "", "calls": {}})
        if call.get("symbol") and not g["symbol"]:
            g["symbol"] = call.get("symbol")
        row = {"channel": ch, "msg_id": call.get("msg_id") or 0, "ts": ts, "ck": ck,
               "x": st["x"], "hx": st["hx"], "entry": st["entry"], "peak": st["peak"],
               "ratio": st["ratio"], "alert": _ms_alert_link(ck, st["hx"]) if st["hx"] >= 2 else None}
        old = g["calls"].get(ch.lower())
        if old is None or row["x"] > old["x"]:
            g["calls"][ch.lower()] = row       # one call per channel per token

    for ck, call in list(tracked_calls.items()):
        _add(ck, call, False)
    try:
        for ck, arc in load_call_archive().items():
            if ck in tracked_calls:
                continue
            _add(ck, arc, True)
    except Exception as e:
        logger.warning(f"most_shared: archive read failed: {e}")

    toks = []
    for g in groups.values():
        calls = sorted(g["calls"].values(), key=lambda r: (-r["x"], r["ts"]))
        if not calls:
            continue
        best = calls[0]
        toks.append({
            "symbol": _ms_sym(g["symbol"]), "chain": g["chain"], "ca": g["ca"],
            "count": len(calls), "best_x": best["x"],
            "best_link": best["alert"] or _ms_post_link(best["channel"], best["msg_id"]),
            "best_entry": best["entry"], "best_peak": best["peak"],
            "peak": max(c["peak"] for c in calls), "first_ts": min(c["ts"] for c in calls),
            "calls": calls,
        })
    toks.sort(key=lambda t: (-t["count"], -t["best_x"], t["first_ts"]))
    toks = toks[:top]
    for t in toks:
        t["chart"] = _x_alert_dex_link(t["ca"], t["chain"]) or ""
        t["trade"] = _x_alert_trade_link(t["ca"])
        t["current"] = 0.0
        t["logo"] = None
        # fallback current MC from the freshest live call (replaced by a live fetch in _ms_enrich)
        for c in sorted(t["calls"], key=lambda r: r["ts"], reverse=True):
            call = tracked_calls.get(c["ck"])
            if call and c["entry"] > 0:
                try:
                    t["current"] = c["entry"] * float(call.get("last_ratio") or 0)
                except (TypeError, ValueError):
                    pass
                if t["current"] > 0:
                    break
    return toks


# ───────────────────────── network enrich (logo + live MC) ─────────────────────────
def _ms_fetch_logo_sync(ca, chain):
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{ca}", timeout=8)
        pairs = (r.json() or {}).get("pairs") or []
        pairs = [p for p in pairs if (p.get("info") or {}).get("imageUrl")]
        pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), reverse=True)
        urls = [p["info"]["imageUrl"] for p in pairs[:2]]
    except Exception:
        urls = []
    for u in urls:
        try:
            img = requests.get(u, timeout=8)
            if img.ok and len(img.content) > 200:
                return img.content
        except Exception:
            continue
    return None


def _ms_fetch_mc_sync(ca, chain):
    try:
        r = _fetch_entry_sync(ca, chain)
        v = float((r or {}).get("mcap") or 0)
        return v if 0 < v < 1e10 else 0.0
    except Exception:
        return 0.0


async def _ms_enrich(toks):
    async def one(t):
        logo, mc = await asyncio.gather(
            _ms_run(_ms_fetch_logo_sync, t["ca"], t["chain"], timeout=25),
            _ms_run(_ms_fetch_mc_sync, t["ca"], t["chain"], timeout=25),
            return_exceptions=True)
        if isinstance(logo, (bytes, bytearray)):
            t["logo"] = bytes(logo)
        if isinstance(mc, float) and mc > 0:
            t["current"] = mc
        if t["current"] > t["peak"]:          # live MC above recorded peak -> peak is at least that
            t["peak"] = t["current"]
    await asyncio.gather(*[one(t) for t in toks])


# ───────────────────────── renderers ─────────────────────────
def _ms_channel_doc(toks, record_url):
    d = _MsDoc()
    d.e(MS_EMO_HEADER).t(" ").t("MOST SHARED TOKENS — Last 24H", bold=True).t("\n\n")
    d.t("Details of the most shared projects in the last 24 hours.\n\n")
    for i, t in enumerate(toks, 1):
        d.e(_ms_chain_emoji(t["chain"], i)).t(" ")
        d.t("$" + t["symbol"], bold=True, url=t["chart"] or None).t("  ")
        d.e(MS_EMO_TEER1 if i <= 5 else MS_EMO_TEER2).t(f" {t['count']} CALLS\n")
        d.t("       Highest ").t(_ms_x(t["best_x"]), url=t["best_link"]).t("\n\n")
    d.t("Click the “Check Record” button for more details.")
    return d


def _ms_record_doc(toks, page):
    """page 0 = ranks 1-5, page 1 = ranks 6-10 (toks = full snapshot list)."""
    sub = toks[page * 5:(page + 1) * 5]
    if not sub:
        return None
    lo, hi = page * 5 + 1, page * 5 + len(sub)
    d = _MsDoc()
    d.e(MS_EMO_HEADER).t(" ").t("MOST SHARED TOKENS RECORD", bold=True).t("\n")
    d.t(f"      Top {lo}–{hi} - Last 24H\n\n")
    for j, t in enumerate(sub):
        rank = page * 5 + j + 1
        d.e(_ms_chain_emoji(t["chain"], rank)).t(" ")
        d.t("$" + t["symbol"], bold=True, url=t["chart"] or None)
        d.t(f" - Total {t['count']} Call{'s' if t['count'] != 1 else ''}", bold=True).t("\n\n")
        for c in t["calls"][:MS_ROWS_PER_TOKEN]:
            d.t("• ").t(_ms_handle(c["channel"])).t(" | ")
            d.t("View Post", url=_ms_post_link(c["channel"], c["msg_id"])).t(" | ")
            d.t(_ms_x(c["x"]), url=c["alert"]).t("\n")
            d.t(f"   {_ms_mc(c['entry'])} to {_ms_mc(c['peak'])}\n")
        d.t("\n").e(MS_EMO_FOOT, "🔎").t(f" Current {_ms_mc(t['current'])} | Peak {_ms_mc(t['peak'])} | ")
        d.t("Trade", url=t["trade"]).t("\n\n")
    d.q(True).t("📔 Tracked by @WizardScan").q(False)
    return d


# ───────────────────────── posting ─────────────────────────
def _ms_video_tokens(toks):
    out = []
    for t in toks:
        out.append({"symbol": t["symbol"], "chain": t["chain"], "count": t["count"],
                    "ath_mc": t["best_peak"], "from_mc": t["best_entry"],
                    "x": t["best_x"], "logo": t["logo"]})
    return out


def _ms_snapshot(toks):
    keep = []
    for t in toks:
        d = {k: v for k, v in t.items() if k not in ("logo", "first_ts", "calls")}
        d["calls"] = [{"channel": c["channel"], "msg_id": c["msg_id"], "x": c["x"],
                       "entry": c["entry"], "peak": c["peak"], "alert": c["alert"]}
                      for c in t["calls"][:MS_ROWS_PER_TOKEN]]
        keep.append(d)
    return keep


async def _ms_make_video(toks):
    import most_shared_video as _msv
    return await _ms_run(_msv.build_most_shared_video, _ms_video_tokens(toks), timeout=240)


def _ms_cleanup(*paths):
    try:
        import most_shared_video as _msv
        _msv.most_shared_cleanup(*paths)
    except Exception:
        for p in paths:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


async def _ms_send_channel(bot, doc, video_path, record_url):
    """Returns the channel message id. Premium emojis via userbot; button icon via Bot API send + userbot edit."""
    plain, ents = doc.plain_entities()
    kb = InlineKeyboardMarkup([[_icon_kb("Check Record", MS_EMO_BTN, url=record_url)]])
    # A) Bot API send (keeps the button icon) then userbot edit adds premium emoji/entities
    if video_path and len(plain) <= MS_CAPTION_LIMIT and not _BOT_CHANNEL_FORBIDDEN["v"]:
        try:
            with open(video_path, "rb") as fh:
                m = await bot.send_video(TARGET_CHANNEL, video=fh, caption=plain, reply_markup=kb,
                                         width=1440, height=626, duration=8, supports_streaming=True)
            if userbot_client:
                try:
                    await _locked_userbot_edit(TARGET_CHANNEL, m.message_id, plain,
                                               formatting_entities=ents, link_preview=False)
                except Exception as e:
                    if "not modified" not in str(e).lower():
                        logger.warning(f"most_shared: emoji edit failed: {e}")
            return m.message_id
        except Exception as e:
            if "not a member" in str(e).lower() or "forbidden" in str(e).lower():
                _BOT_CHANNEL_FORBIDDEN["v"] = True
            logger.warning(f"most_shared: bot send failed, trying userbot: {e}")
    # B) userbot only (no button icon)
    if userbot_client:
        from telethon.tl.types import DocumentAttributeVideo
        btns = _ptb_keyboard_to_tl(InlineKeyboardMarkup([[InlineKeyboardButton("Check Record", url=record_url)]]))
        if video_path:
            sent = await asyncio.wait_for(userbot_client.send_file(
                TARGET_CHANNEL, video_path, caption=plain, formatting_entities=ents, buttons=btns,
                attributes=[DocumentAttributeVideo(duration=8, w=1440, h=626, supports_streaming=True)],
                supports_streaming=True, force_document=False), timeout=USERBOT_MEDIA_TIMEOUT_SECONDS)
        else:
            sent = await userbot_client.send_message(TARGET_CHANNEL, plain, formatting_entities=ents,
                                                     buttons=btns, link_preview=False)
        return sent.id
    raise RuntimeError("no way to post to channel (bot forbidden and userbot offline)")


MS_TZ_OFFSET_H = int(os.environ.get("MOST_SHARED_TZ_OFFSET", "3") or 3)   # Turkey = UTC+3
MS_POST_HOUR   = int(os.environ.get("MOST_SHARED_POST_HOUR", "0") or 0)    # 0 = midnight Turkey time
MS_CATCHUP_H   = 3                                                          # if bot was down, still post within 3h after


def _ms_tr_now():
    return datetime.utcnow() + timedelta(hours=MS_TZ_OFFSET_H)


MS_PIN_MINUTES = int(os.environ.get("MOST_SHARED_PIN_MINUTES", "60") or 60)


async def _ms_pin(bot, mid):
    """Pin the channel post (silently) and remember when to unpin it (restart-safe, stored in state)."""
    ok = False
    try:
        await bot.pin_chat_message(TARGET_CHANNEL, mid, disable_notification=True)
        ok = True
    except Exception as e:
        logger.warning(f"most_shared: bot pin failed ({e}) — trying userbot")
    if not ok and userbot_client:
        try:
            await userbot_client.pin_message(TARGET_CHANNEL, mid, notify=False)
            ok = True
        except Exception as e:
            logger.warning(f"most_shared: userbot pin failed: {e}")
    if ok:
        st = _ms_state()
        st["pinned"] = {"id": mid, "unpin_at": _ms_time.time() + MS_PIN_MINUTES * 60}
        _ms_save_state(st)
    return ok


async def _ms_unpin_now(bot, mid):
    try:
        await bot.unpin_chat_message(TARGET_CHANNEL, message_id=mid)
        return True
    except Exception as e:
        logger.warning(f"most_shared: bot unpin failed ({e}) — trying userbot")
    if userbot_client:
        try:
            await userbot_client.unpin_message(TARGET_CHANNEL, mid)
            return True
        except Exception as e:
            logger.warning(f"most_shared: userbot unpin failed: {e}")
    return False


async def most_shared_unpin_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        pin = _ms_state().get("pinned")
        if pin and _ms_time.time() >= float(pin.get("unpin_at") or 0):
            if await _ms_unpin_now(context.bot, pin["id"]):
                st = _ms_state()
                st.pop("pinned", None)
                _ms_save_state(st)
                logger.info(f"most_shared: unpinned msg {pin['id']}")
    except Exception as e:
        logger.error(f"most_shared unpin job error: {type(e).__name__}: {e}")


async def post_most_shared(bot, to_chat=None):
    """Build + post. to_chat=None -> @WizardScan channel; to_chat=<id> -> preview in that chat only.
    Returns (ok, info_text)."""
    global _ms_lock
    if _ms_lock is None:
        _ms_lock = asyncio.Lock()
    if _ms_lock.locked():
        return False, "Already running."
    async with _ms_lock:
        _t0 = _ms_time.time()
        toks = _ms_collect()
        logger.info(f"most_shared: collected {len(toks)} tokens in {_ms_time.time()-_t0:.1f}s")
        if not toks:
            return False, "No calls in the last 24h."
        try:
            await asyncio.wait_for(_ms_enrich(toks), timeout=60)
        except Exception as e:
            logger.warning(f"most_shared: enrich incomplete ({type(e).__name__}) — continuing")
        logger.info(f"most_shared: enriched ({sum(1 for t in toks if t['logo'])} logos) at +{_ms_time.time()-_t0:.1f}s")
        sid = str(int(_ms_time.time()))
        st = _ms_state()
        snaps = st.setdefault("snapshots", {})
        snaps[sid] = _ms_snapshot(toks)
        for old in sorted(snaps)[:-14]:
            snaps.pop(old, None)
        _ms_save_state(st)
        uname = (await bot.get_me()).username
        record_url = f"https://t.me/{uname}?start=msr_{sid}"
        doc = _ms_channel_doc(toks, record_url)
        video_path = None
        try:
            try:
                video_path = await _ms_make_video(toks)
                logger.info(f"most_shared: video ready at +{_ms_time.time()-_t0:.1f}s")
            except Exception as e:
                logger.error(f"most_shared: video build failed: {type(e).__name__}: {e!r}")
            if to_chat is None:
                mid = await _ms_send_channel(bot, doc, video_path, record_url)
                st = _ms_state()
                st["last_post_ts"] = _ms_time.time()
                st["last_post_day"] = _ms_tr_now().strftime("%Y-%m-%d")
                st["last_post_id"] = mid
                _ms_save_state(st)
                pinned = await _ms_pin(bot, mid)
                return True, (f"Posted (msg {mid}, {len(toks)} tokens, video={'yes' if video_path else 'no'}, "
                              f"pinned={'yes, unpins in ' + str(MS_PIN_MINUTES) + ' min' if pinned else 'NO - check bot pin rights'}).")
            kb = InlineKeyboardMarkup([[_icon_kb("Check Record", MS_EMO_BTN, url=record_url)]])
            if video_path:
                with open(video_path, "rb") as fh:
                    await bot.send_video(to_chat, video=fh, caption=doc.html()[:1024], parse_mode="HTML",
                                         reply_markup=kb, width=1440, height=626, duration=8)
            else:
                await bot.send_message(to_chat, doc.html(), parse_mode="HTML", reply_markup=kb,
                                       disable_web_page_preview=True)
            return True, f"Preview sent ({len(toks)} tokens, video={'yes' if video_path else 'no'})."
        finally:
            _ms_cleanup(video_path)


async def ms_send_record(bot, chat_id, sid):
    """Deep link handler: /start msr_<sid> -> 2 reply messages."""
    toks = (_ms_state().get("snapshots") or {}).get(str(sid))
    if not toks:
        await bot.send_message(chat_id, "⚠️ This record is no longer available.")
        return
    for page in (0, 1):
        doc = _ms_record_doc(toks, page)
        if doc:
            await bot.send_message(chat_id, doc.html(), parse_mode="HTML", disable_web_page_preview=True)


# ───────────────────────── commands + auto job ─────────────────────────
async def cmd_postmostshared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        return
    await update.message.reply_text("⏳ Building Most Shared post…")
    ok, info = await post_most_shared(context.bot)
    await update.message.reply_text(("✅ " if ok else "⚠️ ") + info)


async def cmd_mostsharedtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        return
    await update.message.reply_text("⏳ Building preview (nothing is posted to the channel)…")
    ok, info = await post_most_shared(context.bot, to_chat=update.effective_chat.id)
    await update.message.reply_text(("✅ " if ok else "⚠️ ") + info)
    if ok:
        sid = max((_ms_state().get("snapshots") or {"0": 0}), key=int)
        await ms_send_record(context.bot, update.effective_chat.id, sid)


async def most_shared_auto_job(context: ContextTypes.DEFAULT_TYPE):
    """Posts once a day at MS_POST_HOUR:00 Turkey time (default 00:00). Runs only after the owner has made
    one successful /postmostshared, so nothing untested ever goes out by itself."""
    try:
        st = _ms_state()
        if not st.get("last_post_ts"):
            return
        now = _ms_tr_now()
        today = now.strftime("%Y-%m-%d")
        if st.get("last_post_day") == today or _ms_time.time() < float(st.get("retry_after") or 0):
            return
        mins_since = (now.hour - MS_POST_HOUR) * 60 + now.minute
        if mins_since < 0 or mins_since > MS_CATCHUP_H * 60:
            return
        ok, info = await post_most_shared(context.bot)
        logger.info(f"most_shared auto ({now.strftime('%H:%M')} TR): {info}")
        if not ok:      # don't retry in a tight loop; try again in a few minutes
            st = _ms_state()
            st["retry_after"] = _ms_time.time() + 300
            _ms_save_state(st)
    except Exception as e:
        logger.error(f"most_shared auto job error: {type(e).__name__}: {e}")


def register_most_shared(app):
    app.add_handler(CommandHandler("postmostshared", cmd_postmostshared))
    app.add_handler(CommandHandler("mostsharedtest", cmd_mostsharedtest))
    app.job_queue.run_repeating(most_shared_unpin_job, interval=60, first=60)   # unpin after MOST_SHARED_PIN_MINUTES
    if os.environ.get("MOST_SHARED_AUTO", "1") != "0":
        app.job_queue.run_repeating(most_shared_auto_job, interval=30, first=120)
        logger.info(f"most_shared: auto posting ON daily at {MS_POST_HOUR:02d}:00 Turkey time (UTC+{MS_TZ_OFFSET_H})")
