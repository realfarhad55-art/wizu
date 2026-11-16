# binance_trending.py - "BINANCE HOT TOKENS" pinned post for @WizardScan.
#
# What it does:
#   Fetches Binance spot 24h tickers (public API, no key), ranks tokens by
#   quote volume + price change, groups them by native chain, and posts a
#   pinned message in the channel:
#       5 BNB  +  5 ETH  +  5 SOL  +  5 RH  +  5 BASE
#   Tokens first seen on Binance in the last BN_NEW_DAYS days get the NEW
#   marker next to their name.
#
# Post format (HTML parse mode):
#   Title banner = 10 custom-emoji tiles joined with NO spaces (same pattern
#   as the Hot Streak banner in x_alert.py _hs_banner_html), then the LIVE
#   emoji immediately after it, also with no space. Chain header = chain
#   icon emoji + chain banner emoji (bold text fallback until the owner
#   fills the chain banner IDs). Each $SYMBOL links to its Binance trade
#   page. Token rows use the number emojis, the teer arrow and the NEW badge.
#
# Owner commands:  /binancetrend      (post / update the pinned post now)
#                  /binancetrendtest  (preview in owner DM only)
#                  /bnadd             (manual listing wizard: chain, rank,
#                                      chart link, Vol link, Vol emojis,
#                                      bold line, duration 12/24/48/72h)
#                  /bnremove          (remove a manual listing early)
#                  /bnreset <chain>   (reset ONE chain list: old tokens go
#                                      away, next tokens come in)
#                  /bnlist            (show all manual listings)
# Auto posting: every BN_INTERVAL_H hours (default 6). The bot edits the
#   existing pinned message when it can, otherwise posts a new one and pins
#   it (old one unpinned). Pinned post is message 137 in @WizardScan.
#
# Data: Binance public REST, no API key needed.
#   GET https://api.binance.com/api/v3/ticker/24hr  (all USDT pairs)
# Chain for a symbol comes from BN_CHAIN_MAP (map only, no slow lookup).
# Stablecoins, fiat tokens and Binance tokenised stocks are excluded.
# NEW detection: first-seen timestamp per symbol, kept in the state file.
#   A symbol first seen within BN_NEW_DAYS is NEW.
# Manual listings live in the state file under "manual" (per chain) and
#   expire automatically; they never affect NEW detection.
import time as _bn_time
import json as _bn_json
import html as _bn_html

BN_STATE_FILE = _dp("binance_trend_state.json")
BN_INTERVAL_H = 6
BN_NEW_DAYS = 14
BN_PER_CHAIN = 5
BN_CHAINS = ["BNB", "ETH", "SOL", "RH", "BASE"]
# Pinned post this feature updates: https://t.me/WizardScan/137
BN_PINNED_MSG_ID = 137

# Title banner: 10 custom-emoji tiles, IN ORDER, joined with NO spaces.
# Same pattern as the Hot Streak banner (x_alert.py _hs_banner_html).
BN_TITLE_TILES = [
    6041693326636229690, 6041733716508680297, 6044064333267215756,
    6044245353253839411, 6043977690891951425, 6041579372563932615,
    6042097805181329194, 6042000171984756697, 6041706495005957818,
    6041777671203987750,
]
# LIVE emoji, right after the title banner, NO space.
BN_EMO_LIVE = 5260291556899831755
# NEW badge, next to a newly launched token. 0 = plain fallback.
BN_EMO_NEW = 5458526506886124915
BN_NEW_FB = "🆕"
# Teer (arrow) in token rows.
BN_EMO_TEER = 5807952487604297661
# Rank number emojis 1-5.
BN_EMO_NUM = {
    1: 6044341663600484131,
    2: 6044229702393011956,
    3: 6044037223433642494,
    4: 6041954155705147950,
    5: 6043998469943730784,
}
# Chain icons: small logo before each chain banner.
BN_EMO_CHAIN_ICON = {
    "BNB": 6041973392863667743,
    "ETH": 6041954121345410837,
    "SOL": 6044309494295443603,
    "RH": 6041746128964166642,
    "BASE": 6041769042614690440,
}
# Chain banner emojis are NOT used: the chain header is just the chain icon
# above plus bold "BNB CHAIN" text (owner confirmed Nov 17, no banner per
# chain). Values stay 0; _bn_chain_header falls back to bold text.
BN_EMO_CHAIN = {"BNB": 0, "ETH": 0, "SOL": 0, "RH": 0, "BASE": 0}
BN_CHAIN_FB = {"BNB": "🟡", "ETH": "🔵", "SOL": "🟣", "RH": "🔴", "BASE": "🔷"}

BN_DESC = ("Discover popular tokens across five chains, selected from "
           "projects listed on Binance with solid trading activity. "
           "Not financial advice. DYOR.")
BN_CTA = "Boost your project with a listing here. DM us."

# Well-known Binance symbols -> native chain. Covers the bulk of volume.
# RH is the catch-all bucket for major L1s and chains outside BNB/ETH/SOL.
# Tokens not in this map are skipped (no slow per-token lookup).
BN_CHAIN_MAP = {
    "BNB": "BNB", "CAKE": "BNB", "BAKE": "BNB", "BURGER": "BNB", "TWT": "BNB",
    "XVS": "BNB", "SFP": "BNB", "ALPACA": "BNB", "MBOX": "BNB", "NFP": "BNB",
    "SIGN": "BNB", "ASTER": "BNB", "COCOS": "BNB", "MUB": "BNB", "BABY": "BNB",
    "ETH": "ETH", "LINK": "ETH", "UNI": "ETH", "AAVE": "ETH", "MKR": "ETH",
    "PEPE": "ETH", "SHIB": "ETH", "WLD": "ETH", "ARB": "ETH", "OP": "ETH",
    "LDO": "ETH", "ENS": "ETH", "GRT": "ETH", "SNX": "ETH", "CRV": "ETH",
    "ONDO": "ETH", "PENDLE": "ETH", "MORPHO": "ETH",
    "FET": "ETH", "ENA": "ETH", "ETHFI": "ETH", "NEIRO": "ETH", "GTC": "ETH",
    "DODO": "ETH", "LSK": "ETH", "MEGA": "ETH", "POLY": "ETH", "ZRO": "ETH",
    "HFT": "ETH", "GNS": "ETH", "CYBER": "ETH", "CELO": "ETH", "QNT": "ETH",
    "RSR": "ETH", "HOT": "ETH", "POL": "ETH", "STRK": "ETH", "XAUT": "ETH",
    "PAXG": "ETH", "WBETH": "ETH", "VANRY": "ETH", "MET": "ETH",
    "MITO": "ETH", "ZAMA": "ETH", "BEAMX": "ETH",
    "SOL": "SOL", "BONK": "SOL", "WIF": "SOL", "JUP": "SOL", "PYTH": "SOL",
    "RAY": "SOL", "ORCA": "SOL", "POPCAT": "SOL", "BOME": "SOL", "MEW": "SOL",
    "RENDER": "SOL", "JTO": "SOL", "WEN": "SOL", "PUMP": "SOL", "PENGU": "SOL",
    "TRUMP": "SOL", "ACT": "SOL", "RNDR": "SOL", "HUMA": "SOL",
    "BTC": "RH", "XRP": "RH", "DOGE": "RH", "ADA": "RH", "AVAX": "RH",
    "DOT": "RH", "ATOM": "RH", "NEAR": "RH", "APT": "RH", "SUI": "RH",
    "LTC": "RH", "TRX": "RH", "FIL": "RH", "ICP": "RH", "HBAR": "RH",
    "TON": "RH", "BCH": "RH", "DASH": "RH", "XLM": "RH", "ZEC": "RH",
    "ONE": "RH", "INJ": "RH", "TAO": "RH", "XPL": "RH", "HYPE": "RH",
    "SEI": "RH", "FTM": "RH", "TIA": "RH", "JST": "RH", "SCRT": "RH",
    "ZEN": "RH", "COTI": "RH", "GRAM": "RH", "HMSTR": "RH",
    # BASE native tokens on Binance.
    "AERO": "BASE", "VIRTUAL": "BASE", "BRETT": "BASE", "DEGEN": "BASE",
    "TOSHI": "BASE", "WELL": "BASE", "ZORA": "BASE",
}

# Symbols that are not tradeable crypto tokens for this list: stablecoins,
# fiat-backed tokens and Binance tokenised stocks / ETFs (end in B).
BN_EXCLUDE = {
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "BUSD", "USD1", "RLUSD",
    "RWUSD", "BFUSD", "XUSD", "EUR", "GBP", "USDP", "AEUR", "VAI",
    "NVDAB", "GOOGLB", "MSTRB", "QQQB", "TQQQB", "INTCB", "CRCLB",
    "SPCXB", "KORUB", "SNXXB", "SKHYB", "SOXLB",
}

_bn_lock = None
import concurrent.futures as _bn_cf
_bn_pool = _bn_cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="binance_trend")


async def _bn_run(fn, *args, timeout=60):
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(loop.run_in_executor(_bn_pool, lambda: fn(*args)), timeout=timeout)


def _bn_state():
    try:
        with open(BN_STATE_FILE, "r", encoding="utf-8") as f:
            st = _bn_json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("seen", {})
    st.setdefault("chain_cache", {})
    st.setdefault("manual", {})
    st.setdefault("reset_excluded", {})
    if not st.get("pinned_msg_id"):
        st["pinned_msg_id"] = BN_PINNED_MSG_ID
    return st


def _bn_save_state(st):
    try:
        with open(BN_STATE_FILE, "w", encoding="utf-8") as f:
            _bn_json.dump(st, f)
    except OSError:
        pass


def _bn_prune_manual(st, now=None):
    """Drop expired manual entries. Returns True if anything was removed."""
    now = now if now is not None else _bn_time.time()
    manual = st.get("manual") or {}
    changed = False
    for chain in list(manual.keys()):
        kept = [e for e in (manual.get(chain) or [])
                if float(e.get("expires_at", 0)) > now]
        if len(kept) != len(manual.get(chain) or []):
            changed = True
        if kept:
            manual[chain] = kept
        else:
            manual.pop(chain, None)
    if changed:
        st["manual"] = manual
    return changed


def _bn_fmt_vol(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "N/A"
    if v <= 0:
        return "N/A"
    if v >= 1e9:
        return "$%.2fB" % (v / 1e9)
    if v >= 1e6:
        return "$%.2fM" % (v / 1e6)
    if v >= 1e3:
        return "$%.1fK" % (v / 1e3)
    return "$%.0f" % v


def _bn_chain_for(symbol, st=None):
    """Native chain for a Binance base symbol (e.g. PEPE -> ETH).
    Map only, no network lookup, so ranking stays fast. Returns None if unknown."""
    return BN_CHAIN_MAP.get(str(symbol or "").upper())


def _bn_fetch_tickers():
    """All Binance USDT spot tickers. Returns a list of dicts.
    Tries the public market-data host first (api.binance.com geo-blocks
    some regions with HTTP 451), then binance.com, then binance.us."""
    import requests
    urls = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api.binance.us/api/v3/ticker/24hr",
    ]
    data = None
    last_err = None
    for url in urls:
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            last_err = e
            continue
    if data is None:
        raise RuntimeError("Binance API unreachable: %s" % last_err)
    out = []
    for t in data:
        sym = str(t.get("symbol", ""))
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if base in BN_EXCLUDE:
            continue
        try:
            chg = float(t.get("priceChangePercent", 0))
            vol = float(t.get("quoteVolume", 0))
            price = float(t.get("lastPrice", 0))
        except (TypeError, ValueError):
            continue
        if vol <= 0 or price <= 0:
            continue
        out.append({"base": base, "symbol": sym, "chg": chg, "vol": vol, "price": price})
    return out


def _bn_rank(tickers, st):
    """Group tickers by chain, rank each chain by volume, top N per chain.
    Returns {chain: [ticker, ...]}. Updates first-seen timestamps.
    Chain is only resolved for the top 120 tickers by volume, so unmapped
    tokens never trigger a slow CoinGecko lookup for the long tail."""
    now = _bn_time.time()
    seen = st.get("seen", {})
    # First ever run: we have no history, so treat every symbol we see now
    # as already known (backdate them past the NEW window). Only symbols
    # that appear for the first time AFTER this run count as NEW.
    first_run = len(seen) == 0
    base_ts = now - (BN_NEW_DAYS + 1) * 86400 if first_run else now
    changed = False
    for t in tickers:
        base = t["base"]
        if base not in seen:
            seen[base] = base_ts
            changed = True
    if changed:
        st["seen"] = seen
        _bn_save_state(st)
    cands = sorted(tickers, key=lambda x: x["vol"], reverse=True)[:120]
    grouped = {c: [] for c in BN_CHAINS}
    for t in cands:
        chain = _bn_chain_for(t["base"], st)
        if chain in grouped:
            t["is_new"] = (now - float(seen.get(t["base"], now))) < BN_NEW_DAYS * 86400
            grouped[chain].append(t)
    for c in grouped:
        grouped[c].sort(key=lambda x: x["vol"], reverse=True)
        grouped[c] = grouped[c][:BN_PER_CHAIN]
    return grouped


# ── Emoji HTML helpers (parse_mode="HTML") ──────────────────────────────────

def _bn_emo(cid, placeholder="🔮"):
    """One custom emoji as a tg-emoji tag. Empty string when no id set."""
    if not cid:
        return ""
    return '<tg-emoji emoji-id="%s">%s</tg-emoji>' % (cid, placeholder)


def _bn_title_html():
    """Title banner: 10 tiles joined with NO spaces, then LIVE, no space."""
    tiles = "".join(_bn_emo(cid) for cid in BN_TITLE_TILES)
    live = _bn_emo(BN_EMO_LIVE, "🔴") if BN_EMO_LIVE else ""
    return tiles + live


def _bn_chain_header(chain):
    """Chain header: [chain icon][chain banner, or bold text fallback]."""
    icon_id = BN_EMO_CHAIN_ICON.get(chain)
    if icon_id:
        icon = _bn_emo(icon_id)
    else:
        icon = BN_CHAIN_FB.get(chain, "")
    banner_id = BN_EMO_CHAIN.get(chain) or 0
    if banner_id:
        banner = _bn_emo(banner_id)
    else:
        banner = "<b>%s CHAIN</b>" % chain
    return icon + banner


# ── Manual listings: merge with the auto top-5 ──────────────────────────────

def _bn_merge_chain(chain, auto_rows, tickers_by_base, st, now):
    """Final rows for one chain (rank order). Manual entries take their rank
    slots; auto top-5 fills the rest in volume order. A manual token pushes
    the lowest auto token out; only the top 5 are shown. Each row is a dict
    {rank, base, chg, vol, is_new, manual} where manual is the entry dict
    or None."""
    manual = [e for e in (st.get("manual") or {}).get(chain, [])
              if float(e.get("expires_at", 0)) > now]
    manual = sorted(manual, key=lambda e: int(e.get("rank", BN_PER_CHAIN)))
    by_rank = {}
    seen_sym = set()
    for e in manual:
        try:
            r = int(e.get("rank", BN_PER_CHAIN))
        except (TypeError, ValueError):
            continue
        s = str(e.get("symbol", "")).upper()
        if r < 1 or r > BN_PER_CHAIN or not s:
            continue
        if r in by_rank or s in seen_sym:
            continue
        by_rank[r] = e
        seen_sym.add(s)
    excluded = set((st.get("reset_excluded") or {}).get(chain, []) or [])
    auto = []
    for t in (auto_rows or []):
        if t["base"] in seen_sym:
            continue
        if t["base"] in excluded:
            continue
        auto.append(t)
    rows = []
    ai = 0
    for rank in range(1, BN_PER_CHAIN + 1):
        if rank in by_rank:
            e = by_rank[rank]
            base = str(e.get("symbol", "")).upper()
            tk = (tickers_by_base or {}).get(base)
            if tk:
                chg = float(tk.get("chg", 0))
                vol = float(tk.get("vol", 0))
                is_new = bool(tk.get("is_new", False))
            else:
                chg = 0.0
                vol = 0.0
                is_new = False
            rows.append({"rank": rank, "base": base, "chg": chg, "vol": vol,
                         "is_new": is_new, "manual": e})
        elif ai < len(auto):
            t = auto[ai]
            ai += 1
            rows.append({"rank": rank, "base": t["base"],
                         "chg": float(t.get("chg", 0)),
                         "vol": float(t.get("vol", 0)),
                         "is_new": bool(t.get("is_new", False)),
                         "manual": None})
    return rows


def _bn_row_html(row):
    """One token row: [number] [linked $SYMBOL] [+x%] [teer] Vol $X
    [vol emojis] [NEW]. Bold wraps the whole line when the manual entry
    asks for it."""
    rank = int(row.get("rank", 1))
    manual = row.get("manual") or {}
    num_id = BN_EMO_NUM.get(rank)
    num = _bn_emo(num_id, str(rank)) if num_id else str(rank)
    base = str(row.get("base", "")).upper()
    chart_url = manual.get("chart_url") or ("https://www.binance.com/en/trade/%s_USDT" % base)
    sym = '<a href="%s">$%s</a>' % (_bn_html.escape(str(chart_url), quote=True), base)
    chg = float(row.get("chg", 0))
    sign = "+" if chg >= 0 else ""
    chg_s = "%s%.1f%%" % (sign, chg)
    teer = _bn_emo(BN_EMO_TEER, "➤") if BN_EMO_TEER else "➤"
    vol_s = _bn_fmt_vol(row.get("vol", 0))
    vol_url = manual.get("vol_url")
    if vol_url:
        vol_html = '<a href="%s">Vol %s</a>' % (_bn_html.escape(str(vol_url), quote=True), vol_s)
    else:
        vol_html = "Vol %s" % vol_s
    parts = [num, sym, chg_s, teer, vol_html]
    for cid in (manual.get("vol_emoji_ids") or [])[:2]:
        parts.append(_bn_emo(cid))
    if row.get("is_new"):
        if BN_EMO_NEW:
            parts.append(_bn_emo(BN_EMO_NEW, BN_NEW_FB))
        else:
            parts.append(BN_NEW_FB)
    line = " ".join(parts)
    if manual.get("bold"):
        line = "<b>%s</b>" % line
    return line


def _bn_build_text(grouped, st, tickers_by_base=None):
    """English pinned-post HTML. No em-dashes."""
    now = _bn_time.time()
    lines = []
    lines.append(_bn_title_html())
    lines.append("")
    lines.append(BN_DESC)
    lines.append("")
    for chain in BN_CHAINS:
        rows = _bn_merge_chain(chain, grouped.get(chain, []) or [],
                               tickers_by_base or {}, st, now)
        lines.append(_bn_chain_header(chain))
        if not rows:
            lines.append("No trending tokens right now.")
        for row in rows:
            lines.append(_bn_row_html(row))
        lines.append("")
    lines.append("Updated every 6 hours.")
    lines.append(BN_CTA)
    return "\n".join(lines).strip()


def _bn_build_plain(grouped, st, tickers_by_base=None):
    """Plain-text fallback for the userbot send path only (no emojis,
    no links). Same layout and same merged rows as the HTML post."""
    now = _bn_time.time()
    lines = []
    lines.append("BINANCE HOT TOKENS")
    lines.append("")
    lines.append(BN_DESC)
    lines.append("")
    for chain in BN_CHAINS:
        rows = _bn_merge_chain(chain, grouped.get(chain, []) or [],
                               tickers_by_base or {}, st, now)
        lines.append("%s %s CHAIN" % (BN_CHAIN_FB.get(chain, ""), chain))
        if not rows:
            lines.append("No trending tokens right now.")
        for row in rows:
            base = str(row.get("base", "")).upper()
            chg = float(row.get("chg", 0))
            sign = "+" if chg >= 0 else ""
            new = " 🆕" if row.get("is_new") else ""
            lines.append("%d. $%s %s%.1f%%  |  Vol %s%s" % (
                int(row.get("rank", 1)), base, sign, chg,
                _bn_fmt_vol(row.get("vol", 0)), new))
        lines.append("")
    lines.append("Updated every 6 hours.")
    lines.append(BN_CTA)
    return "\n".join(lines).strip()


async def _bn_post(bot, to_chat=None, preview=False):
    """Fetch, build and post (or preview) the Binance trending post.
    Returns (ok, message_id or error text). Edits the pinned post 137
    when it exists, otherwise posts fresh and pins it."""
    chat = to_chat or TARGET_CHANNEL
    try:
        tickers = await _bn_run(_bn_fetch_tickers)
    except Exception as e:
        return False, "Binance API error: %s" % e
    st = _bn_state()
    try:
        grouped = await _bn_run(_bn_rank, tickers, st)
    except Exception as e:
        return False, "Ranking error: %s" % e
    tickers_by_base = {t["base"]: t for t in tickers}
    if _bn_prune_manual(st):
        _bn_save_state(st)
    text = _bn_build_text(grouped, st, tickers_by_base)
    if preview:
        return True, text
    st = _bn_state()
    mid = None
    # Try editing the existing pinned message first.
    old_id = st.get("pinned_msg_id") or BN_PINNED_MSG_ID
    if old_id:
        try:
            await bot.edit_message_text(text, chat_id=chat, message_id=old_id,
                                        parse_mode="HTML")
            return True, old_id
        except Exception:
            pass
    # Post fresh, pin it, unpin the old one.
    try:
        sent = await bot.send_message(chat, text, parse_mode="HTML")
        mid = sent.message_id
    except Exception:
        try:
            plain = _bn_build_plain(grouped, st, tickers_by_base)
            sent = await userbot_client.send_message(chat, plain)
            mid = sent.id
        except Exception as e:
            return False, "Send failed: %s" % e
    try:
        await bot.pin_chat_message(chat, mid, disable_notification=True)
    except Exception:
        try:
            await userbot_client.pin_message(chat, mid, notify=False)
        except Exception:
            pass
    if old_id and old_id != mid:
        try:
            await bot.unpin_chat_message(chat, message_id=old_id)
        except Exception:
            pass
    st["pinned_msg_id"] = mid
    _bn_save_state(st)
    return True, mid


async def binance_trend_job(context):
    """Scheduled job: refresh the pinned Binance trending post."""
    try:
        bot = context.bot
    except AttributeError:
        bot = None
    if bot is None:
        return
    try:
        ok, res = await _bn_post(bot)
        if not ok:
            print("[binance_trend] job failed: %s" % res)
    except Exception as e:
        print("[binance_trend] job error: %s" % e)


async def cmd_binancetrend(update, context):
    if not _is_owner(update):
        return
    m = update.effective_message
    try:
        await m.reply_text("Fetching Binance trending tokens...")
    except Exception:
        pass
    ok, res = await _bn_post(context.bot)
    try:
        if ok:
            await m.reply_text("Binance trending post updated and pinned. Message id: %s" % res)
        else:
            await m.reply_text("Binance trending failed: %s" % res)
    except Exception:
        pass


async def cmd_binancetrendtest(update, context):
    if not _is_owner(update):
        return
    m = update.effective_message
    ok, res = await _bn_post(context.bot, to_chat=update.effective_chat.id, preview=True)
    try:
        if ok:
            await m.reply_text(res, parse_mode="HTML")
        else:
            await m.reply_text("Binance trending failed: %s" % res)
    except Exception:
        pass


# ── Manual listings ─────────────────────────────────────────────────────────
# Flow states live in owner_edit_state[uid] = {"state": "BN_ADD_...", "bn": {...}}.
# Text input is routed by _bn_flow_message (group -1, runs before the central
# handle_message) and blocked there, so the central dispatcher never sees it.
# Buttons are handled by _bn_callback (pattern ^bn:, group -1).

BN_DURATIONS = [12, 24, 48, 72]


def _bn_capture_emojis(msg):
    """Custom emoji IDs from a message (same idea as _capture_custom_emojis).
    Returns a list of id strings, in order, deduped."""
    out = []
    try:
        ents = list(getattr(msg, "entities", None) or []) + \
            list(getattr(msg, "caption_entities", None) or [])
        for e in ents:
            if getattr(e, "type", "") == "custom_emoji" and getattr(e, "custom_emoji_id", None):
                out.append(str(e.custom_emoji_id))
    except Exception:
        pass
    seen = set()
    uniq = []
    for cid in out:
        if cid not in seen:
            seen.add(cid)
            uniq.append(cid)
    return uniq


def _bn_is_url(s):
    s = (s or "").strip()
    return s.startswith("http://") or s.startswith("https://")


def _bn_kb(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows])


def _bn_flow_get(uid):
    try:
        si = owner_edit_state.get(uid) or {}
    except Exception:
        si = {}
    return si


def _bn_flow_clear(uid):
    try:
        owner_edit_state[uid] = {"state": None}
    except Exception:
        pass


async def cmd_bnadd(update, context):
    if not _is_owner(update):
        return
    uid = update.effective_user.id
    owner_edit_state[uid] = {"state": "BN_ADD_SYMBOL", "bn": {}}
    await update.message.reply_text(
        "📈 <b>Binance manual listing</b>\n\n"
        "Token ka symbol bhejo (jaise <code>BRETT</code>).\n\n"
        "(/cancel se kabhi bhi rok sakte ho)",
        parse_mode="HTML")


async def cmd_bnlist(update, context):
    if not _is_owner(update):
        return
    st = _bn_state()
    if _bn_prune_manual(st):
        _bn_save_state(st)
    manual = st.get("manual") or {}
    now = _bn_time.time()
    lines = ["📈 <b>Manual listings</b>\n"]
    total = 0
    for chain in BN_CHAINS:
        for e in (manual.get(chain) or []):
            total += 1
            left_h = max(0.0, (float(e.get("expires_at", 0)) - now) / 3600.0)
            bold = "bold" if e.get("bold") else "normal"
            chart = "chart link" if e.get("chart_url") else "Binance link"
            vol = "Vol link" if e.get("vol_url") else "no Vol link"
            nemo = len(e.get("vol_emoji_ids") or [])
            lines.append("• $%s  %s #%d  (%.1fh left, %s, %s, %s, %d emoji)" % (
                str(e.get("symbol", "")).upper(), chain, int(e.get("rank", 0)),
                left_h, bold, chart, vol, nemo))
    if total == 0:
        lines.append("Koi manual listing nahi hai.")
    lines.append("\nRemove karne ke liye: /bnremove")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_bnremove(update, context):
    if not _is_owner(update):
        return
    st = _bn_state()
    if _bn_prune_manual(st):
        _bn_save_state(st)
    manual = st.get("manual") or {}
    args = (context.args or [])
    if len(args) >= 2:
        chain = str(args[0]).upper()
        sym = str(args[1]).upper().lstrip("$")
        if chain in BN_CHAINS:
            lst = list(manual.get(chain) or [])
            kept = [e for e in lst if str(e.get("symbol", "")).upper() != sym]
            if len(kept) != len(lst):
                if kept:
                    manual[chain] = kept
                else:
                    manual.pop(chain, None)
                st["manual"] = manual
                _bn_save_state(st)
                await update.message.reply_text(
                    "✅ $%s (%s) hata diya, post refresh ho rahi hai..." % (sym, chain))
                ok, res = await _bn_post(context.bot)
                if not ok:
                    await update.message.reply_text(
                        "⚠️ Post refresh nahi hui: %s (agli auto update me aa jayega)" % res)
                return
        await update.message.reply_text(
            "⚠️ $%s (%s) manual list me nahi mila.\nUsage: /bnremove <chain> <symbol>" % (sym, chain))
        return
    rows = []
    for chain in BN_CHAINS:
        for e in (manual.get(chain) or []):
            sym = str(e.get("symbol", "")).upper()
            rows.append([("❌ $%s (%s #%d)" % (sym, chain, int(e.get("rank", 0))),
                          "bn:rm:%s:%s" % (chain, sym))])
    if not rows:
        await update.message.reply_text(
            "📈 Koi manual listing nahi hai.\nAdd karne ke liye: /bnadd")
        return
    await update.message.reply_text(
        "📈 <b>Manual listing hatao</b>\n\n"
        "Kis token ko hatana hai? Button dabao, wo foran hat jayega "
        "aur post refresh ho jayegi.",
        parse_mode="HTML", reply_markup=_bn_kb(rows))


async def cmd_bnreset(update, context):
    if not _is_owner(update):
        return
    args = (context.args or [])
    if args:
        chain = str(args[0]).upper()
        if chain not in BN_CHAINS:
            await update.message.reply_text(
                "⚠️ Chain galat hai. Chains: %s\nUsage: /bnreset <chain>" % ", ".join(BN_CHAINS))
            return
        kb = _bn_kb([
            [("✅ Reset karo", "bn:rsok:%s" % chain),
             ("❌ Cancel", "bn:rsno:%s" % chain)],
        ])
        await update.message.reply_text(
            "⚠️ <b>%s</b> chain ki list reset hogi:\n\n"
            "• Is chain ki manual listings hat jayengi\n"
            "• Abhi dikh rahe purane top tokens hat jayenge, agle tokens aa jayenge\n"
            "• Baaki chains ko kuch nahi hoga\n\n"
            "Pakka reset karna hai?" % chain,
            parse_mode="HTML", reply_markup=kb)
        return
    rows = [[("%s reset" % c, "bn:rspick:%s" % c)] for c in BN_CHAINS]
    await update.message.reply_text(
        "📈 <b>Chain list reset</b>\n\nKis chain ki list reset karni hai?",
        parse_mode="HTML", reply_markup=_bn_kb(rows))


async def _bn_do_reset(bot, chain):
    """Reset ONE chain only. Drops its manual listings, excludes its current
    top-5 symbols (so the old tokens go away and the next ones come in),
    then refreshes the post. Other chains are untouched. Returns (ok, res,
    excluded_list)."""
    st = _bn_state()
    cur = []
    try:
        tickers = await _bn_run(_bn_fetch_tickers)
        grouped = await _bn_run(_bn_rank, tickers, st)
        cur = [t["base"] for t in (grouped.get(chain) or [])]
    except Exception:
        cur = []
    manual = st.get("manual") or {}
    manual.pop(chain, None)
    st["manual"] = manual
    seen = st.get("seen") or {}
    for sym in list(seen.keys()):
        if _bn_chain_for(sym) == chain:
            seen.pop(sym, None)
    st["seen"] = seen
    ex = st.get("reset_excluded") or {}
    lst = list(ex.get(chain) or [])
    for s in cur:
        if s not in lst:
            lst.append(s)
    ex[chain] = lst
    st["reset_excluded"] = ex
    _bn_save_state(st)
    ok, res = await _bn_post(bot)
    return ok, res, cur


def _bn_confirm_text(d):
    left = ""
    sym = str(d.get("symbol", "")).upper()
    chain = str(d.get("chain", ""))
    chart = d.get("chart_url") or "Binance trade link (default)"
    vol = d.get("vol_url") or "koi link nahi"
    nemo = len(d.get("vol_emoji_ids") or [])
    bold = "HAAN (poori line bold)" if d.get("bold") else "NAHI"
    hours = int(d.get("hours", 24))
    return (
        "📈 <b>Confirm karo</b>\n\n"
        "• Token: <b>$%s</b>\n"
        "• Chain: <b>%s</b>\n"
        "• Rank: <b>#%d</b>\n"
        "• Chart link: %s\n"
        "• Vol link: %s\n"
        "• Vol ke baad emojis: %d\n"
        "• Bold line: %s\n"
        "• Duration: <b>%d hours</b>\n\n"
        "Save kar dun?" % (sym, chain, int(d.get("rank", 0)), chart, vol,
                            nemo, bold, hours))


async def _bn_save_manual(bot, uid, d):
    """Write the manual entry (replacing any entry at the same rank or with
    the same symbol in that chain), then refresh the post."""
    st = _bn_state()
    _bn_prune_manual(st)
    manual = st.get("manual") or {}
    chain = str(d.get("chain", ""))
    rank = int(d.get("rank", 5))
    sym = str(d.get("symbol", "")).upper()
    lst = [e for e in (manual.get(chain) or [])
           if int(e.get("rank", 0)) != rank
           and str(e.get("symbol", "")).upper() != sym]
    entry = {
        "symbol": sym,
        "chain": chain,
        "rank": rank,
        "chart_url": d.get("chart_url"),
        "vol_url": d.get("vol_url"),
        "vol_emoji_ids": list(d.get("vol_emoji_ids") or [])[:2],
        "bold": bool(d.get("bold")),
        "expires_at": _bn_time.time() + int(d.get("hours", 24)) * 3600,
    }
    lst.append(entry)
    manual[chain] = lst
    st["manual"] = manual
    _bn_save_state(st)
    return await _bn_post(bot)


async def _bn_callback(update, context):
    q = update.callback_query
    if not q or not (q.data or "").startswith("bn:"):
        return
    try:
        await q.answer()
    except Exception:
        pass
    uid = update.effective_user.id
    try:
        if uid not in OWNER_IDS:
            return
    except Exception:
        return
    data = q.data or ""
    parts = data.split(":")
    kind = parts[1] if len(parts) > 1 else ""

    # Manual listing flow buttons.
    if kind in ("ch", "rk", "bd", "du", "save", "cancel"):
        si = _bn_flow_get(uid)
        d = si.get("bn") or {}
        state = si.get("state") or ""
        if kind == "cancel":
            _bn_flow_clear(uid)
            try:
                await q.edit_message_text("❌ Cancelled.")
            except Exception:
                pass
            return
        if kind == "ch" and len(parts) > 2:
            chain = parts[2].upper()
            if chain not in BN_CHAINS:
                return
            d["chain"] = chain
            owner_edit_state[uid] = {"state": "BN_ADD_RANK", "bn": d}
            kb = _bn_kb([[(str(i), "bn:rk:%d" % i) for i in (1, 2, 3, 4, 5)],
                         [("❌ Cancel", "bn:cancel")]])
            try:
                await q.edit_message_text(
                    "📈 <b>Rank choose karo</b>\n\n"
                    "$%s (%s) kis number pe dikhe?\n1 = sabse upar" % (
                        str(d.get("symbol", "")).upper(), chain),
                    parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
            return
        if kind == "rk" and len(parts) > 2:
            try:
                rank = int(parts[2])
            except ValueError:
                return
            if rank < 1 or rank > BN_PER_CHAIN:
                return
            d["rank"] = rank
            owner_edit_state[uid] = {"state": "BN_ADD_CHART", "bn": d}
            try:
                await q.edit_message_text(
                    "📈 <b>Chart link</b>\n\n"
                    "$%s ke symbol pe kaunsa chart link lagana hai?\n"
                    "Link bhejo, ya default Binance trade link ke liye /skip likho." % (
                        str(d.get("symbol", "")).upper()),
                    parse_mode="HTML")
            except Exception:
                pass
            return
        if kind == "bd" and len(parts) > 2:
            d["bold"] = (parts[2] == "1")
            owner_edit_state[uid] = {"state": "BN_ADD_DUR", "bn": d}
            kb = _bn_kb([[(("%d hours" % h), "bn:du:%d" % h) for h in BN_DURATIONS],
                         [("❌ Cancel", "bn:cancel")]])
            try:
                await q.edit_message_text(
                    "📈 <b>Duration</b>\n\n"
                    "$%s kitni der ke liye list rahe?" % str(d.get("symbol", "")).upper(),
                    parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
            return
        if kind == "du" and len(parts) > 2:
            try:
                hours = int(parts[2])
            except ValueError:
                return
            if hours not in BN_DURATIONS:
                return
            d["hours"] = hours
            owner_edit_state[uid] = {"state": "BN_ADD_CONFIRM", "bn": d}
            kb = _bn_kb([[("✅ Save karo", "bn:save"),
                          ("❌ Cancel", "bn:cancel")]])
            try:
                await q.edit_message_text(_bn_confirm_text(d),
                                          parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
            return
        if kind == "save":
            if state != "BN_ADD_CONFIRM" or not d.get("symbol"):
                try:
                    await q.edit_message_text(
                        "⚠️ Session khatam ho gaya, /bnadd dobara chalao.")
                except Exception:
                    pass
                _bn_flow_clear(uid)
                return
            _bn_flow_clear(uid)
            try:
                await q.edit_message_text("⏳ Save ho raha hai, post refresh ho rahi hai...")
            except Exception:
                pass
            ok, res = await _bn_save_manual(context.bot, uid, d)
            try:
                if ok:
                    await q.edit_message_text(
                        "✅ <b>$%s</b> list ho gaya (%s #%d, %d hours).\nPost update ho gayi." % (
                            str(d.get("symbol", "")).upper(), d.get("chain"),
                            int(d.get("rank", 0)), int(d.get("hours", 24))),
                        parse_mode="HTML")
                else:
                    await q.edit_message_text(
                        "✅ Listing save ho gayi, lekin post refresh nahi hui: %s\n"
                        "Agli auto update me aa jayega." % res)
            except Exception:
                pass
            return
        return

    # Remove one manual listing (early remove).
    if kind == "rm" and len(parts) > 3:
        chain = parts[2].upper()
        sym = parts[3].upper()
        st = _bn_state()
        manual = st.get("manual") or {}
        lst = list(manual.get(chain) or [])
        kept = [e for e in lst if str(e.get("symbol", "")).upper() != sym]
        if len(kept) == len(lst):
            try:
                await q.edit_message_text("⚠️ $%s (%s) list me nahi mila." % (sym, chain))
            except Exception:
                pass
            return
        if kept:
            manual[chain] = kept
        else:
            manual.pop(chain, None)
        st["manual"] = manual
        _bn_save_state(st)
        ok, res = await _bn_post(context.bot)
        try:
            if ok:
                await q.edit_message_text("✅ $%s (%s) hata diya, post refresh ho gayi." % (sym, chain))
            else:
                await q.edit_message_text(
                    "✅ $%s hata diya, lekin post refresh nahi hui: %s" % (sym, res))
        except Exception:
            pass
        return

    # Reset flow: pick a chain, then confirm.
    if kind == "rspick" and len(parts) > 2:
        chain = parts[2].upper()
        if chain not in BN_CHAINS:
            return
        kb = _bn_kb([
            [("✅ Reset karo", "bn:rsok:%s" % chain),
             ("❌ Cancel", "bn:rsno:%s" % chain)],
        ])
        try:
            await q.edit_message_text(
                "⚠️ <b>%s</b> chain ki list reset hogi:\n\n"
                "• Is chain ki manual listings hat jayengi\n"
                "• Abhi dikh rahe purane top tokens hat jayenge, agle tokens aa jayenge\n"
                "• Baaki chains ko kuch nahi hoga\n\n"
                "Pakka reset karna hai?" % chain,
                parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return
    if kind == "rsok" and len(parts) > 2:
        chain = parts[2].upper()
        if chain not in BN_CHAINS:
            return
        try:
            await q.edit_message_text("⏳ %s reset ho raha hai, post refresh ho rahi hai..." % chain)
        except Exception:
            pass
        ok, res, cur = await _bn_do_reset(context.bot, chain)
        try:
            if ok:
                await q.edit_message_text(
                    "✅ <b>%s</b> reset ho gaya. Hataye gaye tokens: %s\nPost update ho gayi." % (
                        chain, ", ".join("$%s" % s for s in cur) or "koi nahi"),
                    parse_mode="HTML")
            else:
                await q.edit_message_text("⚠️ Reset save ho gaya, lekin post refresh nahi hui: %s" % res)
        except Exception:
            pass
        return
    if kind == "rsno":
        try:
            await q.edit_message_text("❌ Cancelled, kuch reset nahi hua.")
        except Exception:
            pass
        return


async def _bn_flow_message(update, context):
    """Group -1 text handler for the /bnadd wizard. Only acts when the
    owner has an active BN_* state; otherwise passes through untouched.
    Raises ApplicationHandlerStop when it handles a message, so the central
    handle_message never sees wizard input."""
    msg = update.effective_message
    if msg is None:
        return
    try:
        uid = update.effective_user.id
    except Exception:
        return
    try:
        if uid not in OWNER_IDS:
            return
    except Exception:
        return
    si = _bn_flow_get(uid)
    state = str(si.get("state") or "")
    if not state.startswith("BN_"):
        return
    d = si.get("bn") or {}
    text = (msg.text or msg.caption or "").strip()

    async def _ask(html_text, kb=None):
        try:
            await msg.reply_text(html_text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    # Any other command exits the wizard silently and lets it run.
    if text.startswith("/") and text.split()[0].lstrip("/").lower() not in ("cancel", "skip"):
        _bn_flow_clear(uid)
        return
    # Cancel.
    if text.lower() in ("/cancel", "cancel"):
        _bn_flow_clear(uid)
        await _ask("❌ Cancelled.")
        raise ApplicationHandlerStop

    if state == "BN_ADD_SYMBOL":
        sym = text.upper().lstrip("$").replace(" ", "")
        if not sym or len(sym) > 12 or not sym.isalnum():
            await _ask("⚠️ Sahi symbol bhejo (sirf letters/numbers, jaise <code>BRETT</code>).")
            raise ApplicationHandlerStop
        d["symbol"] = sym
        owner_edit_state[uid] = {"state": "BN_ADD_CHAIN", "bn": d}
        kb = _bn_kb([[(c, "bn:ch:%s" % c) for c in ("BNB", "ETH", "SOL")],
                     [(c, "bn:ch:%s" % c) for c in ("RH", "BASE")],
                     [("❌ Cancel", "bn:cancel")]])
        await _ask("📈 <b>Chain choose karo</b>\n\n$%s kis chain ka hai?" % sym,
                   kb)
        raise ApplicationHandlerStop

    if state == "BN_ADD_CHAIN":
        chain = text.upper()
        if chain not in BN_CHAINS:
            await _ask("⚠️ Chain galat hai. BNB, ETH, SOL, RH ya BASE likho, ya button dabao.")
            raise ApplicationHandlerStop
        d["chain"] = chain
        owner_edit_state[uid] = {"state": "BN_ADD_RANK", "bn": d}
        kb = _bn_kb([[(str(i), "bn:rk:%d" % i) for i in (1, 2, 3, 4, 5)],
                     [("❌ Cancel", "bn:cancel")]])
        await _ask("📈 <b>Rank choose karo</b>\n\n$%s (%s) kis number pe dikhe?\n1 = sabse upar" % (
            str(d.get("symbol", "")).upper(), chain), kb)
        raise ApplicationHandlerStop

    if state == "BN_ADD_RANK":
        try:
            rank = int(text)
        except ValueError:
            rank = 0
        if rank < 1 or rank > BN_PER_CHAIN:
            await _ask("⚠️ Rank 1 se 5 ke beech me likho.")
            raise ApplicationHandlerStop
        d["rank"] = rank
        owner_edit_state[uid] = {"state": "BN_ADD_CHART", "bn": d}
        await _ask("📈 <b>Chart link</b>\n\n$%s ke symbol pe kaunsa chart link lagana hai?\n"
                   "Link bhejo, ya default Binance trade link ke liye /skip likho." % (
                       str(d.get("symbol", "")).upper()))
        raise ApplicationHandlerStop

    if state == "BN_ADD_CHART":
        if text.lower() in ("/skip", "skip"):
            d["chart_url"] = None
        elif _bn_is_url(text):
            d["chart_url"] = text
        else:
            await _ask("⚠️ Sahi link bhejo (https:// se shuru ho), ya /skip likho.")
            raise ApplicationHandlerStop
        owner_edit_state[uid] = {"state": "BN_ADD_VOLURL", "bn": d}
        await _ask("📈 <b>Vol link</b>\n\nVol wali line (jaise Vol $64.51M) pe link lagana hai?\n"
                   "Link bhejo, ya /skip likho.")
        raise ApplicationHandlerStop

    if state == "BN_ADD_VOLURL":
        if text.lower() in ("/skip", "skip"):
            d["vol_url"] = None
        elif _bn_is_url(text):
            d["vol_url"] = text
        else:
            await _ask("⚠️ Sahi link bhejo (https:// se shuru ho), ya /skip likho.")
            raise ApplicationHandlerStop
        owner_edit_state[uid] = {"state": "BN_ADD_VOLEMO", "bn": d}
        await _ask("📈 <b>Vol emojis</b>\n\nVol ke baad 1 ya 2 premium emojis lagane hain?\n"
                   "Emojis bhejo (1 ya 2), ya /skip likho.")
        raise ApplicationHandlerStop

    if state == "BN_ADD_VOLEMO":
        if text.lower() in ("/skip", "skip"):
            d["vol_emoji_ids"] = []
        else:
            ids = _bn_capture_emojis(msg)
            if not ids:
                await _ask("⚠️ Koi premium emoji nahi mila. 1 ya 2 custom emojis bhejo, ya /skip likho.")
                raise ApplicationHandlerStop
            d["vol_emoji_ids"] = ids[:2]
        owner_edit_state[uid] = {"state": "BN_ADD_BOLD", "bn": d}
        kb = _bn_kb([[("✅ HAAN, bold karo", "bn:bd:1"),
                      ("❌ NAHI", "bn:bd:0")],
                     [("❌ Cancel", "bn:cancel")]])
        await _ask("📈 <b>Bold line?</b>\n\n$%s ki poori line bold karni hai?" % (
            str(d.get("symbol", "")).upper()), kb)
        raise ApplicationHandlerStop

    if state == "BN_ADD_BOLD":
        low = text.lower()
        if low in ("haan", "han", "yes", "1"):
            d["bold"] = True
        elif low in ("nahi", "no", "0"):
            d["bold"] = False
        else:
            await _ask("⚠️ HAAN ya NAHI likho, ya button dabao.")
            raise ApplicationHandlerStop
        owner_edit_state[uid] = {"state": "BN_ADD_DUR", "bn": d}
        kb = _bn_kb([[(("%d hours" % h), "bn:du:%d" % h) for h in BN_DURATIONS],
                     [("❌ Cancel", "bn:cancel")]])
        await _ask("📈 <b>Duration</b>\n\n$%s kitni der ke liye list rahe?" % (
            str(d.get("symbol", "")).upper()), kb)
        raise ApplicationHandlerStop

    if state == "BN_ADD_DUR":
        try:
            hours = int(text)
        except ValueError:
            hours = 0
        if hours not in BN_DURATIONS:
            await _ask("⚠️ Duration 12, 24, 48 ya 72 hours me se likho.")
            raise ApplicationHandlerStop
        d["hours"] = hours
        owner_edit_state[uid] = {"state": "BN_ADD_CONFIRM", "bn": d}
        kb = _bn_kb([[("✅ Save karo", "bn:save"),
                      ("❌ Cancel", "bn:cancel")]])
        await _ask(_bn_confirm_text(d), kb)
        raise ApplicationHandlerStop

    if state == "BN_ADD_CONFIRM":
        await _ask("ℹ️ Save karne ke liye ✅ button dabao, ya /cancel likho.")
        raise ApplicationHandlerStop


def register_binance_trending(app):
    app.add_handler(CommandHandler("binancetrend", cmd_binancetrend))
    app.add_handler(CommandHandler("binancetrendtest", cmd_binancetrendtest))
    app.add_handler(CommandHandler("bnadd", cmd_bnadd))
    app.add_handler(CommandHandler("bnremove", cmd_bnremove))
    app.add_handler(CommandHandler("bnreset", cmd_bnreset))
    app.add_handler(CommandHandler("bnlist", cmd_bnlist))
    app.add_handler(CallbackQueryHandler(_bn_callback, pattern=r"^bn:"), group=-1)
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT, _bn_flow_message), group=-1)
    try:
        app.job_queue.run_repeating(
            binance_trend_job,
            interval=BN_INTERVAL_H * 3600,
            first=BN_INTERVAL_H * 3600,
            name="binance_trend_job",
        )
    except Exception as e:
        print("[binance_trend] job schedule failed: %s" % e)
