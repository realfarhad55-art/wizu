# skipcall.py — Skipped Call + Late Track fix (owner only)
# Naya top button: ownerhelp se "Call Fix" khulta hai, andar 2 buttons:
#   1) Skipped Call  2) Late Track
# Dono flows button-driven hain, har step par Back hota hai, aur har step
# ki purani post delete ho kar nayi aati hai (gand nahi hota).
#
# Flow Skipped Call:
#   channel -> CA -> auto chain/symbol (DexScreener) -> correct buttons
#   -> call MC -> ATH (ya "chart abhi call MC par hi hai" = 1x)
#   -> X auto-calc -> manual X option -> post link (+ preview)
#   -> dropped call post -> X alert post (champion ho to video + template)
# Flow Late Track:
#   post link -> scan (CA nikaalo) -> confirm/fix -> call MC -> ATH -> X
#   -> purani call ka data har jagah se delete -> dropped + X alert dobara
#
# Register: bot.py _PIECES me "skipcall" add karo, runtime.py main() me
# register_skipcall(app) call karo (register_most_shared ke paas).
# handle_message me skipcall state check ke liye runtime patch alag file me
# hai: skipcall_runtime_patch.txt

import re, html, asyncio, logging
from datetime import datetime

logger = logging.getLogger(__name__)

# --- imports (bot ke shared namespace se; _PIECES exec order me core,
# dropped_call, x_alert, leaderboard, commands se pehle/ baad me bhi chalega
# kyunki ye functions call time par resolve hote hain) ---
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
except Exception:
    InlineKeyboardButton = InlineKeyboardMarkup = None
    CallbackQueryHandler = MessageHandler = filters = None

# Ye names bot ke shared namespace me hote hain (core/dropped/x_alert/
# leaderboard/commands). Agar koi na mile to fallback niche hai.
_G = globals()

def _need(name, default=None):
    return _G.get(name, default)

# ---------------------------------------------------------------- helpers

def _parse_mc(text):
    """MC jese bhi likho le lo: 100k, 100.5k, 100K, 1.2M, 100000, 100,000,
    70k, 2.5m, 500. Points/decimals dono chalte hain."""
    if text is None:
        return 0.0
    t = str(text).strip().lower().replace(",", "").replace("$", "").replace("mc", "").strip()
    if not t:
        return 0.0
    mult = 1.0
    if t.endswith("k"):
        mult = 1_000.0; t = t[:-1]
    elif t.endswith("m"):
        mult = 1_000_000.0; t = t[:-1]
    elif t.endswith("b"):
        mult = 1_000_000_000.0; t = t[:-1]
    try:
        return float(t) * mult
    except Exception:
        return 0.0

def _parse_x(text):
    t = str(text or "").strip().lower().rstrip("x").strip()
    try:
        return float(t)
    except Exception:
        return 0.0

_CA_RE = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44}|0x[a-fA-F0-9]{40})\b")

def _extract_ca(text):
    if not text:
        return ""
    m = _CA_RE.search(text)
    return m.group(1) if m else ""

def _detect_chain_from_ca(addr):
    if addr.startswith("0x") and len(addr) in (42, 66):
        return "ETH"
    if re.match(r"^(EQ|UQ)[A-Za-z0-9_-]{46}$", addr or ""):
        return "TON"
    return "SOL"

def _fmt_mc(v):
    f = _need("fmt_mc")
    if f:
        try:
            return f(v)
        except Exception:
            pass
    try:
        v = float(v)
    except Exception:
        return "N/A"
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M MC".replace(".0M", "M")
    if v >= 1_000:
        return f"{v/1_000:.1f}K MC".replace(".0K", "K")
    return f"{v:.0f} MC"

def _fmt_x(v):
    f = _need("fmt_x")
    if f:
        try:
            return f(v)
        except Exception:
            pass
    try:
        return f"{float(v):g}x"
    except Exception:
        return "1x"

# ---------------------------------------------------------------- state

def _sc(user_data):
    d = user_data.setdefault("skipcall", {})
    return d

def _reset(user_data):
    user_data.pop("skipcall", None)

def _kb(rows):
    if InlineKeyboardMarkup is None:
        return None
    return InlineKeyboardMarkup(rows)

def _btn(text, cb):
    return InlineKeyboardButton(text, callback_data=cb)

async def _say(msg, text, kb=None, edit=False):
    """Ek step ki post: purani step post delete karo, nayi bhejo."""
    ud = msg  # placeholder (actual impl neeche _send_step me hai)
    return None

async def _send_step(update, context, text, kb=None):
    """Purani step wali post delete kar ke nayi post bhejo (gand nahi)."""
    ud = context.user_data
    st = _sc(ud)
    chat_id = update.effective_chat.id
    old_id = st.get("step_msg_id")
    if old_id:
        try:
            await context.bot.delete_message(chat_id, old_id)
        except Exception:
            pass
    # callback se aaye to edit karo, warna nayi post
    sent = None
    if update.callback_query:
        try:
            sent = await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            sent = await context.bot.send_message(
                chat_id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    else:
        sent = await context.bot.send_message(
            chat_id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    if sent is not None:
        try:
            st["step_msg_id"] = sent.message_id
        except Exception:
            pass
    return sent

def _back_kb(back_cb, extra=None):
    rows = []
    if extra:
        rows.extend(extra)
    rows.append([_btn("⬅️ Back", back_cb)])
    return _kb(rows)

# ---------------------------------------------------------------- menu

async def sc_menu(update, context):
    """Top button se khulta hai: Skipped Call + Late Track."""
    ud = context.user_data
    st = _sc(ud)
    st.clear()
    st["flow"] = "menu"
    kb = _kb([
        [_btn("📡 Skipped Call", "sc:skip")],
        [_btn("🔧 Late Track (MC fix)", "sc:late")],
        [_btn("⬅️ Back", "sc:close")],
    ])
    await _send_step(update, context,
        "🔧 <b>Call Fix</b>\n\n"
        "Konsa masla hai?\n\n"
        "📡 <b>Skipped Call</b> — bot ne KOL ki call miss kar di, dobara add karni hai.\n"
        "🔧 <b>Late Track</b> — call late track hui, MC galat hai, purana data delete kar ke sahi karni hai.",
        kb)

# ---------------------------------------------------------------- skipped call flow

async def sc_skip_start(update, context):
    st = _sc(context.user_data)
    st.clear()
    st["flow"] = "skip"
    st["step"] = "ch"
    kb = _back_kb("sc:menu")
    await _send_step(update, context,
        "📡 <b>Skipped Call</b>\n\n"
        "Channel ka username do.\n"
        "Example: <code>@pumpwatch1</code>",
        kb)

async def sc_on_text(update, context):
    """Text input jab skipcall/late flow chal raha ho."""
    ud = context.user_data
    st = _sc(ud)
    if not st or not st.get("flow"):
        return False
    text = (update.message.text or "").strip()
    flow = st.get("flow")
    step = st.get("step")
    if flow == "skip":
        return await _skip_text(update, context, st, step, text)
    if flow == "late":
        return await _late_text(update, context, st, step, text)
    return False

async def _skip_text(update, context, st, step, text):
    if step == "ch":
        ch = text.lstrip("@").strip()
        if not ch:
            await _send_step(update, context, "⚠️ Username khaali hai. Dobara do.", _back_kb("sc:menu"))
            return True
        st["channel"] = ch
        st["step"] = "ca"
        await _send_step(update, context,
            f"Channel: <b>@{html.escape(ch)}</b>\n\n"
            "Ab token ka <b>CA</b> do.",
            _back_kb("sc:skip"))
        return True
    if step == "ca":
        ca = _extract_ca(text) or text.strip()
        if len(ca) < 32:
            await _send_step(update, context, "⚠️ Ye CA nahi lag raha. Poora CA dobara do.", _back_kb("sc:skip"))
            return True
        st["ca"] = ca
        await _send_step(update, context, "⏳ DexScreener se token ka data nikaal raha hoon...", _back_kb("sc:skip"))
        # DexScreener fetch
        dex = None
        fetch = _need("fetch_dexscreener")
        if fetch:
            try:
                dex = await fetch(ca)
            except Exception as e:
                logger.warning(f"skipcall dex fetch fail {ca[:12]}: {e}")
        sym = ""
        chain = ""
        if dex:
            sym = (dex.get("symbol") or "").upper()
            chain = (dex.get("chain") or "").upper()
        if not chain:
            chain = _detect_chain_from_ca(ca)
        if not sym:
            sym = "UNKNOWN"
        st["symbol"] = sym
        st["chain"] = chain
        st["step"] = "confirm"
        kb = _kb([
            [_btn("✅ Data theek hai", "sc:ok")],
            [_btn("⛓️ Chain galat hai", "sc:chain")],
            [_btn("🔤 Symbol galat hai", "sc:sym")],
            [_btn("⬅️ Back", "sc:skip")],
        ])
        await _send_step(update, context,
            f"Token mil gaya:\n\n"
            f"🪙 Symbol: <b>${html.escape(sym)}</b>\n"
            f"⛓️ Chain: <b>{html.escape(chain)}</b>\n"
            f"CA: <code>{html.escape(ca)}</code>\n\n"
            "Agar chain ya symbol galat hai to theek kar lo, warna aage barho.",
            kb)
        return True
    if step == "chain":
        ch = text.strip().upper()
        valid = {"SOL", "ETH", "BNB", "BSC", "BASE", "RH", "TON", "EVM"}
        if ch not in valid:
            await _send_step(update, context,
                "⚠️ Chain in me se ek do: <code>SOL ETH BNB BASE RH TON</code>",
                _back_kb("sc:confirm"))
            return True
        st["chain"] = ch
        st["step"] = "confirm"
        kb = _kb([
            [_btn("✅ Data theek hai", "sc:ok")],
            [_btn("⛓️ Chain galat hai", "sc:chain")],
            [_btn("🔤 Symbol galat hai", "sc:sym")],
            [_btn("⬅️ Back", "sc:skip")],
        ])
        await _send_step(update, context,
            f"Chain theek kar di: <b>{html.escape(ch)}</b>\n\n"
            f"🪙 Symbol: <b>${html.escape(st.get('symbol',''))}</b>\n"
            f"⛓️ Chain: <b>{html.escape(ch)}</b>",
            kb)
        return True
    if step == "sym":
        sym = text.strip().upper().lstrip("$")
        if not sym:
            await _send_step(update, context, "⚠️ Symbol khaali hai.", _back_kb("sc:confirm"))
            return True
        st["symbol"] = sym
        st["step"] = "confirm"
        kb = _kb([
            [_btn("✅ Data theek hai", "sc:ok")],
            [_btn("⛓️ Chain galat hai", "sc:chain")],
            [_btn("🔤 Symbol galat hai", "sc:sym")],
            [_btn("⬅️ Back", "sc:skip")],
        ])
        await _send_step(update, context,
            f"Symbol theek kar diya: <b>${html.escape(sym)}</b>\n\n"
            f"🪙 Symbol: <b>${html.escape(sym)}</b>\n"
            f"⛓️ Chain: <b>{html.escape(st.get('chain',''))}</b>",
            kb)
        return True
    if step == "entry":
        mc = _parse_mc(text)
        if mc <= 0:
            await _send_step(update, context,
                "⚠️ MC samajh nahi aayi. Aise likho: <code>100k</code> ya <code>100000</code> ya <code>1.2M</code>",
                _back_kb("sc:confirm"))
            return True
        st["entry_mc"] = mc
        st["step"] = "ath"
        kb = _kb([
            [_btn("📊 Chart abhi call MC par hi hai (1x)", "sc:ath_same")],
            [_btn("⬅️ Back", "sc:confirm")],
        ])
        await _send_step(update, context,
            f"Call MC: <b>{_fmt_mc(mc)}</b>\n\n"
            "Ab <b>ATH MC</b> batao — call ke baad token kitna upar gaya?\n"
            "Aise likho: <code>250k</code> ya <code>250000</code>\n\n"
            "Agar chart abhi call MC par hi hai to neeche wala button dabao.",
            kb)
        return True
    if step == "ath":
        mc = _parse_mc(text)
        if mc <= 0:
            await _send_step(update, context,
                "⚠️ ATH MC samajh nahi aayi. Aise likho: <code>250k</code>",
                _back_kb("sc:entry"))
            return True
        st["ath_mc"] = mc
        entry = st.get("entry_mc") or 0
        x = (mc / entry) if entry > 0 else 1.0
        st["x"] = round(x, 4)
        st["step"] = "x"
        kb = _kb([
            [_btn(f"✅ {_fmt_x(x)} theek hai", "sc:x_ok")],
            [_btn("✏️ X khud batao", "sc:x_manual")],
            [_btn("⬅️ Back", "sc:entry")],
        ])
        await _send_step(update, context,
            f"Call MC: <b>{_fmt_mc(entry)}</b> → ATH: <b>{_fmt_mc(mc)}</b>\n\n"
            f"📈 X ban raha hai: <b>{_fmt_x(x)}</b>\n\n"
            "Agar X galat lag raha hai to khud bata do.",
            kb)
        return True
    if step == "x_manual":
        x = _parse_x(text)
        if x <= 0:
            await _send_step(update, context, "⚠️ X number me do, jaise <code>2.5</code>", _back_kb("sc:ath"))
            return True
        st["x"] = round(x, 4)
        # ATH ko X ke hisaab se adjust karo (record ke liye)
        entry = st.get("entry_mc") or 0
        st["ath_mc"] = entry * x
        st["step"] = "link"
        await _send_step(update, context,
            f"X set kar diya: <b>{_fmt_x(x)}</b>\n\n"
            "Ab KOL ki <b>post ka link</b> do.\n"
            "Example: <code>https://t.me/pumpwatch1/14579</code>",
            _back_kb("sc:ath"))
        return True
    if step == "link":
        link = text.strip()
        st["link"] = link
        st["step"] = "preview"
        kb = _kb([
            [_btn("✅ Yehi post hai", "sc:post_ok")],
            [_btn("🔗 Apna link do", "sc:link_own")],
            [_btn("⬅️ Back", "sc:x")],
        ])
        await _send_step(update, context,
            f"Post ka link:\n{html.escape(link)}\n\n"
            "Ye wali post hai? Agar galat hai to apna link de do.",
            kb)
        return True
    if step == "link_own":
        link = text.strip()
        st["link"] = link
        st["step"] = "preview"
        kb = _kb([
            [_btn("✅ Yehi post hai", "sc:post_ok")],
            [_btn("🔗 Apna link do", "sc:link_own")],
            [_btn("⬅️ Back", "sc:x")],
        ])
        await _send_step(update, context,
            f"Post ka link:\n{html.escape(link)}\n\n"
            "Ye wali post hai?",
            kb)
        return True
    return True

# ---------------------------------------------------------------- callbacks

async def sc_callback(update, context):
    query = update.callback_query
    data = query.data or ""
    ud = context.user_data
    st = _sc(ud)
    try:
        await query.answer()
    except Exception:
        pass
    if data == "sc:menu":
        await sc_menu(update, context)
        return
    if data == "sc:close":
        _reset(ud)
        try:
            await query.message.delete()
        except Exception:
            pass
        return
    if data == "sc:skip":
        await sc_skip_start(update, context)
        return
    if data == "sc:late":
        await sc_late_start(update, context)
        return
    # --- skip flow buttons ---
    if data == "sc:chain":
        st["step"] = "chain"
        await _send_step(update, context,
            "Sahi <b>chain</b> do.\nSOL / ETH / BNB / BASE / RH / TON",
            _back_kb("sc:confirm"))
        return
    if data == "sc:sym":
        st["step"] = "sym"
        await _send_step(update, context,
            "Sahi <b>symbol</b> do. Example: <code>DOPE</code>",
            _back_kb("sc:confirm"))
        return
    if data == "sc:ok":
        st["step"] = "entry"
        await _send_step(update, context,
            f"🪙 <b>${html.escape(st.get('symbol',''))}</b> · {html.escape(st.get('chain',''))}\n\n"
            "<b>Call MC</b> batao — jis MC par KOL ne call di thi.\n"
            "Aise likho: <code>100k</code> ya <code>100000</code> ya <code>70.5k</code>",
            _back_kb("sc:confirm"))
        return
    if data == "sc:ath_same":
        # Chart abhi call MC par hi hai = 1x, X waghera nahi poochna
        st["ath_mc"] = st.get("entry_mc") or 0
        st["x"] = 1.0
        st["step"] = "link"
        await _send_step(update, context,
            "✅ Samajh gaya — chart abhi <b>1x</b> par hi hai.\n\n"
            "Ab KOL ki <b>post ka link</b> do.\n"
            "Example: <code>https://t.me/pumpwatch1/14579</code>",
            _back_kb("sc:entry"))
        return
    if data == "sc:x_ok":
        st["step"] = "link"
        await _send_step(update, context,
            f"X: <b>{_fmt_x(st.get('x', 1))}</b>\n\n"
            "Ab KOL ki <b>post ka link</b> do.\n"
            "Example: <code>https://t.me/pumpwatch1/14579</code>",
            _back_kb("sc:ath"))
        return
    if data == "sc:x_manual":
        st["step"] = "x_manual"
        await _send_step(update, context,
            "Apna <b>X</b> batao. Example: <code>2.5</code>",
            _back_kb("sc:ath"))
        return
    if data == "sc:link_own":
        st["step"] = "link_own"
        await _send_step(update, context,
            "Apna <b>post link</b> do.",
            _back_kb("sc:x"))
        return
    if data == "sc:post_ok":
        await _skip_finish(update, context)
        return
    # --- late flow buttons ---
    if data == "lt:ok":
        st["step"] = "entry"
        await _send_step(update, context,
            f"🪙 <b>${html.escape(st.get('symbol',''))}</b> · {html.escape(st.get('chain',''))}\n\n"
            "<b>Call MC</b> batao — asal call kis MC par hui thi?\n"
            "Example: bot ne 100k par track kia, asal 70k thi to <code>70k</code> likho.",
            _back_kb("lt:confirm"))
        return
    if data == "lt:chain":
        st["step"] = "chain"
        await _send_step(update, context,
            "Sahi <b>chain</b> do.\nSOL / ETH / BNB / BASE / RH / TON",
            _back_kb("lt:confirm"))
        return
    if data == "lt:sym":
        st["step"] = "sym"
        await _send_step(update, context,
            "Sahi <b>symbol</b> do. Example: <code>DOPE</code>",
            _back_kb("lt:confirm"))
        return
    if data == "lt:ath_same":
        st["ath_mc"] = st.get("entry_mc") or 0
        st["x"] = 1.0
        await _late_finish(update, context)
        return
    if data == "lt:x_ok":
        await _late_finish(update, context)
        return
    if data == "lt:x_manual":
        st["step"] = "x_manual"
        await _send_step(update, context,
            "Apna <b>X</b> batao. Example: <code>2.5</code>",
            _back_kb("lt:ath"))
        return
    # back shortcuts
    if data == "sc:confirm":
        st["step"] = "confirm"
        kb = _kb([
            [_btn("✅ Data theek hai", "sc:ok")],
            [_btn("⛓️ Chain galat hai", "sc:chain")],
            [_btn("🔤 Symbol galat hai", "sc:sym")],
            [_btn("⬅️ Back", "sc:skip")],
        ])
        await _send_step(update, context,
            f"🪙 Symbol: <b>${html.escape(st.get('symbol',''))}</b>\n"
            f"⛓️ Chain: <b>{html.escape(st.get('chain',''))}</b>",
            kb)
        return
    if data == "sc:entry":
        st["step"] = "entry"
        await _send_step(update, context,
            "<b>Call MC</b> batao.\nAise likho: <code>100k</code> ya <code>100000</code>",
            _back_kb("sc:confirm"))
        return
    if data == "sc:ath":
        st["step"] = "ath"
        kb = _kb([
            [_btn("📊 Chart abhi call MC par hi hai (1x)", "sc:ath_same")],
            [_btn("⬅️ Back", "sc:entry")],
        ])
        await _send_step(update, context,
            "<b>ATH MC</b> batao — call ke baad token kitna upar gaya?",
            kb)
        return
    if data == "sc:x":
        st["step"] = "x"
        kb = _kb([
            [_btn(f"✅ {_fmt_x(st.get('x', 1))} theek hai", "sc:x_ok")],
            [_btn("✏️ X khud batao", "sc:x_manual")],
            [_btn("⬅️ Back", "sc:entry")],
        ])
        await _send_step(update, context,
            f"📈 X ban raha hai: <b>{_fmt_x(st.get('x', 1))}</b>",
            kb)
        return
    if data == "lt:confirm":
        st["step"] = "confirm"
        kb = _kb([
            [_btn("✅ Data theek hai", "lt:ok")],
            [_btn("⛓️ Chain galat hai", "lt:chain")],
            [_btn("🔤 Symbol galat hai", "lt:sym")],
            [_btn("⬅️ Back", "sc:menu")],
        ])
        await _send_step(update, context,
            f"🪙 Symbol: <b>${html.escape(st.get('symbol',''))}</b>\n"
            f"⛓️ Chain: <b>{html.escape(st.get('chain',''))}</b>",
            kb)
        return
    if data == "lt:ath":
        st["step"] = "ath"
        kb = _kb([
            [_btn("📊 Chart abhi call MC par hi hai (1x)", "lt:ath_same")],
            [_btn("⬅️ Back", "lt:entry")],
        ])
        await _send_step(update, context,
            "<b>ATH MC</b> batao — call ke baad token kitna upar gaya?",
            kb)
        return
    if data == "lt:entry":
        st["step"] = "entry"
        await _send_step(update, context,
            "<b>Call MC</b> batao — asal call kis MC par hui thi?",
            _back_kb("lt:confirm"))
        return

# ---------------------------------------------------------------- finish: skipped call

async def _skip_finish(update, context):
    st = _sc(context.user_data)
    channel = (st.get("channel") or "").lstrip("@")
    ca = st.get("ca") or ""
    chain = (st.get("chain") or "SOL").upper()
    symbol = (st.get("symbol") or "UNKNOWN").upper()
    entry_mc = float(st.get("entry_mc") or 0)
    ath_mc = float(st.get("ath_mc") or entry_mc)
    x = float(st.get("x") or 1.0)
    link = st.get("link") or ""
    if not channel or not ca or entry_mc <= 0:
        await _send_step(update, context, "⚠️ Data adhoora hai. Dobara shuru karo.", _back_kb("sc:menu"))
        return
    await _send_step(update, context, "⏳ Call add ho rahi hai — pehle dropped post, phir X alert...", None)
    ok = await _apply_fix(context, channel, ca, chain, symbol, entry_mc, ath_mc, x, link, delete_old=False)
    _reset(context.user_data)
    if ok:
        await context.bot.send_message(update.effective_chat.id,
            f"✅ <b>Skipped call fix ho gayi!</b>\n\n"
            f"@{html.escape(channel)} · <b>${html.escape(symbol)}</b> ({html.escape(chain)})\n"
            f"{_fmt_mc(entry_mc)} → {_fmt_mc(ath_mc)} = <b>{_fmt_x(x)}</b>\n\n"
            "Pehle dropped call post gayi, phir X alert. Champion KOL hua to video + champion template bhi gaya.",
            parse_mode="HTML")
    else:
        await context.bot.send_message(update.effective_chat.id,
            "⚠️ Fix karte waqt masla aaya. Log check karo ya dobara try karo.",
            parse_mode="HTML")

async def _apply_fix(context, channel, ca, chain, symbol, entry_mc, ath_mc, x, link, delete_old):
    """Call record karo, milestones mark karo, dropped post phir X alert.
    delete_old=True (late track) par purani call ka data har jagah se hatao."""
    try:
        tracked_calls = _need("tracked_calls")
        sent_milestones = _need("sent_milestones")
        milestone_posts = _need("milestone_posts")
        call_archive = _need("call_archive")
        if tracked_calls is None:
            return False
        call_key = f"{channel}_{ca}"
        # --- late track: purani call ka data delete ---
        if delete_old and call_key in tracked_calls:
            tracked_calls.pop(call_key, None)
            if sent_milestones is not None:
                sent_milestones.pop(call_key, None)
            if milestone_posts is not None:
                milestone_posts.pop(call_key, None)
            if call_archive is not None:
                call_archive.pop(call_key, None)
            _save = _need("_save_tracked")
            if _save:
                try:
                    _save()
                except Exception:
                    pass
            for fn in ("_save_milestones", "_save_milestone_posts", "save_call_archive"):
                f = _need(fn)
                if f:
                    try:
                        f()
                    except Exception:
                        pass
        # --- call record ---
        entry_fmt = _fmt_mc(entry_mc)
        if call_key not in tracked_calls:
            tracked_calls[call_key] = {
                "channel": channel, "msg_id": 0, "ca": ca,
                "chain": chain, "entry_mc": entry_mc,
                "entry_price": 0, "entry_fmt": entry_fmt,
                "entry_src": "owner", "entry_locked": True,
                "symbol": symbol,
                "tracked_since": datetime.utcnow().isoformat(),
                **({"kol_tg_link": link} if link else {}),
            }
        ref = tracked_calls[call_key]
        ref["chain"] = chain
        ref["symbol"] = symbol
        ref["entry_mc"] = entry_mc
        ref["entry_fmt"] = entry_fmt
        ref["entry_src"] = "owner"
        ref["entry_locked"] = True
        if link:
            ref["kol_tg_link"] = link
        ref["last_ratio"] = round(x, 4)
        ref["owner_reported_x"] = round(x, 4)
        ref["owner_reported_ath_mc"] = float(ath_mc)
        _upd = _need("_update_peak")
        if _upd:
            try:
                _upd(ref, x, float(ath_mc))
            except Exception:
                pass
        _save = _need("_save_tracked")
        if _save:
            try:
                _save()
            except Exception:
                pass
        # --- milestones mark (sirf top alert bhejta hai; 100x ho to sirf 100x) ---
        get_mil = _need("get_milestones")
        milestones = get_mil() if get_mil else [2, 3, 4, 5, 6, 7, 8, 9, 10]
        hit = [m for m in milestones if m <= x]
        alert_x = max(hit) if hit else 0
        if sent_milestones is not None:
            s = sent_milestones.setdefault(call_key, set())
            for ms in hit:
                if ms not in s:
                    s.add(ms)
                    ap = _need("award_points_for_milestone")
                    if ap:
                        try:
                            await ap(channel, call_key, ms)
                        except Exception:
                            pass
            _sm = _need("_save_milestones")
            if _sm:
                try:
                    _sm()
                except Exception:
                    pass
        # --- pehle dropped call post, phir X alert ---
        bot = context.bot
        sda = _need("send_dropped_alert")
        if sda:
            try:
                await sda(bot, channel, ref.get("msg_id", 0), ca, chain, entry_fmt, symbol, respect_skip=False)
            except Exception as e:
                logger.warning(f"skipcall dropped post fail: {e}")
        if alert_x >= 2:
            sa = _need("send_alert")
            if sa:
                try:
                    # Champion ho to send_alert khud video + champion template lagata hai.
                    await sa(bot, channel, ref.get("msg_id", 0), alert_x, chain,
                             entry_fmt, _fmt_mc(ath_mc), ca, symbol)
                except Exception as e:
                    logger.warning(f"skipcall x alert fail: {e}")
        return True
    except Exception as e:
        logger.exception(f"skipcall _apply_fix fail: {e}")
        return False

# ---------------------------------------------------------------- late track flow

async def sc_late_start(update, context):
    st = _sc(context.user_data)
    st.clear()
    st["flow"] = "late"
    st["step"] = "link"
    kb = _back_kb("sc:menu")
    await _send_step(update, context,
        "🔧 <b>Late Track Fix</b>\n\n"
        "Channel ki <b>post ka link</b> do jis call ko late track kia gaya.\n"
        "Example: <code>https://t.me/pumpwatch1/14579</code>\n\n"
        "Bot khud scan kar ke token ka naam aur chain batayega.",
        kb)

async def _late_text(update, context, st, step, text):
    if step == "link":
        link = text.strip()
        st["link"] = link
        # link se channel nikaalo
        m = re.search(r"t\.me/([A-Za-z0-9_]+)/(\d+)", link)
        if m:
            st["channel"] = m.group(1)
        # CA: pehle link wali post se nikaalne ki koshish (userbot), warna user se mango
        ca = ""
        ub = _need("userbot_client")
        if ub and m:
            try:
                ent = await ub.get_entity(m.group(1))
                msgs = await ub.get_messages(ent, ids=int(m.group(2)))
                txt = getattr(msgs, "text", "") or ""
                ca = _extract_ca(txt)
            except Exception as e:
                logger.warning(f"late scan fail: {e}")
        if ca:
            st["ca"] = ca
            await _late_after_ca(update, context, st)
        else:
            st["step"] = "ca"
            await _send_step(update, context,
                "Post se CA nahi mila. Token ka <b>CA</b> do.",
                _back_kb("sc:menu"))
        return True
    if step == "ca":
        ca = _extract_ca(text) or text.strip()
        if len(ca) < 32:
            await _send_step(update, context, "⚠️ Ye CA nahi lag raha. Poora CA dobara do.", _back_kb("sc:menu"))
            return True
        st["ca"] = ca
        await _late_after_ca(update, context, st)
        return True
    if step == "chain":
        ch = text.strip().upper()
        valid = {"SOL", "ETH", "BNB", "BSC", "BASE", "RH", "TON", "EVM"}
        if ch not in valid:
            await _send_step(update, context, "⚠️ Chain in me se ek do: <code>SOL ETH BNB BASE RH TON</code>", _back_kb("lt:confirm"))
            return True
        st["chain"] = ch
        st["step"] = "confirm"
        kb = _kb([
            [_btn("✅ Data theek hai", "lt:ok")],
            [_btn("⛓️ Chain galat hai", "lt:chain")],
            [_btn("🔤 Symbol galat hai", "lt:sym")],
            [_btn("⬅️ Back", "sc:menu")],
        ])
        await _send_step(update, context,
            f"Chain: <b>{html.escape(ch)}</b>\n🪙 Symbol: <b>${html.escape(st.get('symbol',''))}</b>",
            kb)
        return True
    if step == "sym":
        sym = text.strip().upper().lstrip("$")
        if not sym:
            await _send_step(update, context, "⚠️ Symbol khaali hai.", _back_kb("lt:confirm"))
            return True
        st["symbol"] = sym
        st["step"] = "confirm"
        kb = _kb([
            [_btn("✅ Data theek hai", "lt:ok")],
            [_btn("⛓️ Chain galat hai", "lt:chain")],
            [_btn("🔤 Symbol galat hai", "lt:sym")],
            [_btn("⬅️ Back", "sc:menu")],
        ])
        await _send_step(update, context,
            f"Symbol: <b>${html.escape(sym)}</b>\n⛓️ Chain: <b>{html.escape(st.get('chain',''))}</b>",
            kb)
        return True
    if step == "entry":
        mc = _parse_mc(text)
        if mc <= 0:
            await _send_step(update, context, "⚠️ MC samajh nahi aayi. Aise likho: <code>70k</code>", _back_kb("lt:confirm"))
            return True
        st["entry_mc"] = mc
        st["step"] = "ath"
        kb = _kb([
            [_btn("📊 Chart abhi call MC par hi hai (1x)", "lt:ath_same")],
            [_btn("⬅️ Back", "lt:confirm")],
        ])
        await _send_step(update, context,
            f"Call MC: <b>{_fmt_mc(mc)}</b>\n\n"
            "Ab <b>ATH MC</b> batao — call ke baad token kitna upar gaya?",
            kb)
        return True
    if step == "ath":
        mc = _parse_mc(text)
        if mc <= 0:
            await _send_step(update, context, "⚠️ ATH MC samajh nahi aayi.", _back_kb("lt:entry"))
            return True
        st["ath_mc"] = mc
        entry = st.get("entry_mc") or 0
        x = (mc / entry) if entry > 0 else 1.0
        st["x"] = round(x, 4)
        st["step"] = "x"
        kb = _kb([
            [_btn(f"✅ {_fmt_x(x)} theek hai", "lt:x_ok")],
            [_btn("✏️ X khud batao", "lt:x_manual")],
            [_btn("⬅️ Back", "lt:entry")],
        ])
        await _send_step(update, context,
            f"Call MC: <b>{_fmt_mc(entry)}</b> → ATH: <b>{_fmt_mc(mc)}</b>\n\n"
            f"📈 X ban raha hai: <b>{_fmt_x(x)}</b>",
            kb)
        return True
    if step == "x_manual":
        x = _parse_x(text)
        if x <= 0:
            await _send_step(update, context, "⚠️ X number me do, jaise <code>2.5</code>", _back_kb("lt:ath"))
            return True
        st["x"] = round(x, 4)
        entry = st.get("entry_mc") or 0
        st["ath_mc"] = entry * x
        await _late_finish(update, context)
        return True
    return True

async def _late_after_ca(update, context, st):
    ca = st.get("ca") or ""
    dex = None
    fetch = _need("fetch_dexscreener")
    if fetch:
        try:
            dex = await fetch(ca)
        except Exception:
            pass
    sym = ""
    chain = ""
    if dex:
        sym = (dex.get("symbol") or "").upper()
        chain = (dex.get("chain") or "").upper()
    if not chain:
        chain = _detect_chain_from_ca(ca)
    if not sym:
        sym = "UNKNOWN"
    st["symbol"] = sym
    st["chain"] = chain
    # channel link se nahi mila to tracked call se lo
    if not st.get("channel"):
        tc = _need("tracked_calls") or {}
        for k, v in tc.items():
            if ca in k:
                st["channel"] = v.get("channel") or ""
                break
    st["step"] = "confirm"
    kb = _kb([
        [_btn("✅ Data theek hai", "lt:ok")],
        [_btn("⛓️ Chain galat hai", "lt:chain")],
        [_btn("🔤 Symbol galat hai", "lt:sym")],
        [_btn("⬅️ Back", "sc:menu")],
    ])
    await _send_step(update, context,
        f"Post scan ho gayi:\n\n"
        f"🪙 Symbol: <b>${html.escape(sym)}</b>\n"
        f"⛓️ Chain: <b>{html.escape(chain)}</b>\n"
        f"CA: <code>{html.escape(ca)}</code>\n\n"
        "Agar chain ya symbol galat hai to theek kar lo.",
        kb)

async def _late_finish(update, context):
    st = _sc(context.user_data)
    channel = (st.get("channel") or "").lstrip("@")
    ca = st.get("ca") or ""
    chain = (st.get("chain") or "SOL").upper()
    symbol = (st.get("symbol") or "UNKNOWN").upper()
    entry_mc = float(st.get("entry_mc") or 0)
    ath_mc = float(st.get("ath_mc") or entry_mc)
    x = float(st.get("x") or 1.0)
    link = st.get("link") or ""
    if not channel or not ca or entry_mc <= 0:
        await _send_step(update, context, "⚠️ Data adhoora hai (channel/CA/MC). Dobara shuru karo.", _back_kb("sc:menu"))
        return
    await _send_step(update, context, "⏳ Purani call delete ho rahi hai, phir sahi wali post ho gi...", None)
    ok = await _apply_fix(context, channel, ca, chain, symbol, entry_mc, ath_mc, x, link, delete_old=True)
    _reset(context.user_data)
    if ok:
        await context.bot.send_message(update.effective_chat.id,
            f"✅ <b>Late track fix ho gayi!</b>\n\n"
            f"@{html.escape(channel)} · <b>${html.escape(symbol)}</b> ({html.escape(chain)})\n"
            f"{_fmt_mc(entry_mc)} → {_fmt_mc(ath_mc)} = <b>{_fmt_x(x)}</b>\n\n"
            "Purani call ka data delete kar diya, phir dropped call post aur X alert dobara bhej di.",
            parse_mode="HTML")
    else:
        await context.bot.send_message(update.effective_chat.id,
            "⚠️ Fix karte waqt masla aaya. Log check karo ya dobara try karo.",
            parse_mode="HTML")

# ---------------------------------------------------------------- register

def register_skipcall(app):
    """runtime.py main() me call karo: register_skipcall(app)"""
    if CallbackQueryHandler is None:
        return
    app.add_handler(CallbackQueryHandler(sc_callback, pattern=r"^sc:"))
    app.add_handler(CallbackQueryHandler(sc_callback, pattern=r"^lt:"))
    # Text input: sirf tab jab skipcall flow chal raha ho (sc_on_text khud check karta hai)
    async def _text_entry(update, context):
        try:
            handled = await sc_on_text(update, context)
        except Exception as e:
            logger.exception(f"skipcall text fail: {e}")
            handled = False
        # handled na ho to baaqi handlers (handle_message) ko jaane do
        return handled
    # NOTE: runtime.py handle_message me ye check add karna hai (patch file dekho):
    #   if context.user_data.get("skipcall", {}).get("flow"):
    #       if await sc_on_text(update, context): return
    # Is liye yahan MessageHandler register nahi kar rahe — handle_message se route hoga.
    return _text_entry
