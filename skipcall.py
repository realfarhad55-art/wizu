# skipcall.py — Skipped Call + Late Track + Entry MC Fix (owner only)
# Naya top button: ownerhelp se "Call Fix" khulta hai, andar 3 buttons:
#   1) Skipped Call  2) Late Track  3) Entry MC Fix (FIXENTRY_NOV12)
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
    """Top button se khulta hai: Skipped Call + Late Track + Entry MC Fix."""
    ud = context.user_data
    st = _sc(ud)
    st.clear()
    st["flow"] = "menu"
    kb = _kb([
        [_btn("📡 Skipped Call", "sc:skip")],
        [_btn("🔧 Late Track (MC fix)", "sc:late")],
        [_btn("📝 Entry MC Fix Karo", "sc:entryfix")],
        [_btn("⬅️ Back", "sc:close")],
    ])
    await _send_step(update, context,
        "🔧 <b>Call Fix</b>\n\n"
        "Konsa masla hai?\n\n"
        "📡 <b>Skipped Call</b> — bot ne KOL ki call miss kar di, dobara add karni hai.\n"
        "🔧 <b>Late Track</b> — call late track hui, MC galat hai, purana data delete kar ke sahi karni hai.\n"
        "📝 <b>Entry MC Fix</b> - call ki entry MC galat hai, sahi karni hai aur X alert dobara post karni hai.",
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
    """Text input jab skipcall/late/entryfix flow chal raha ho."""
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
    if flow == "entryfix":
        return await _entryfix_text(update, context, st, step, text)
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
    if data == "sc:entryfix":
        await sc_entryfix_start(update, context)
        return
    if data == "sc:ef_confirm":
        await _entryfix_apply(update, context)
        return
    if data == "sc:ef_cancel":
        _reset(ud)
        await context.bot.send_message(update.effective_chat.id,
            "❌ Cancel kar diya - kuch change nahi hua.", parse_mode="HTML")
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


# ---------------------------------------------------------------- entry MC fix flow
# FIXENTRY_NOV12: owner button "Entry MC Fix Karo" (Call Fix menu).
# Post link / forward / CA se call dhoondo, record dikhao, sahi entry MC lo,
# confirm karo, phir entry + X + points theek kar ke latest X alert post karo.
# Koi channel post delete nahi hoti, koi aur call/channel nahi chherta.
# State in-memory hai (skipcall jaisi) - bot restart ho to flow khatam, data
# ko kuch nahi hota kyunki likhai sirf Confirm par hoti hai.

_EF_FILES = ["tracked_calls.json", "sent_milestones.json",
             "milestone_posts.json", "channel_points.json"]

def _ef_tier_points(tiers):
    """Call ke tiers ki total points (highest tier only, live rule).
    tiers=[2,10,50] -> 50. tiers=[2,10] -> 25. tiers=[2] -> 10. tiers=[] -> 0."""
    best = 0
    _tiers = _need("POINT_TIERS") or [(50, 50), (10, 25), (2, 10)]
    try:
        for t, p in _tiers:
            if t in (tiers or []) and int(p) > best:
                best = int(p)
    except Exception:
        pass
    return best

def _ef_parse_link(text):
    m = re.search(r"t\.me/([A-Za-z0-9_]+)/(\d+)", text or "")
    if m:
        return m.group(1), int(m.group(2))
    return None, None

def _ef_find_call_by_msg_id(msg_id):
    """WizardScan X-alert post id se call key dhoondo (milestone_posts)."""
    mp = _need("milestone_posts") or {}
    try:
        mid = int(msg_id)
    except Exception:
        return None
    for ck, levels in (mp or {}).items():
        if not isinstance(levels, dict):
            continue
        for _lvl, pid in levels.items():
            try:
                if int(pid) == mid:
                    return ck
            except Exception:
                continue
    return None

def _ef_find_call_by_ca(ca):
    """CA se call key dhoondo (key = f'{channel}_{ca}')."""
    tc = _need("tracked_calls") or {}
    ca_low = (ca or "").strip().lower()
    if not ca_low:
        return None
    for ck in tc.keys():
        try:
            if str(ck).rsplit("_", 1)[-1].lower() == ca_low:
                return ck
        except Exception:
            continue
    return None

async def _ef_fetch_post_ca(channel, msg_id):
    """Userbot se post ka text le kar CA nikaalo (KOL post ya WizardScan
    dropped-call post). Na mile to ''. Pehle userbot, phir 2nd userbot."""
    if not channel or not msg_id:
        return ""
    for _ub_name in ("userbot_client", "userbot_client2"):
        ub = _need(_ub_name)
        if not ub:
            continue
        try:
            ent = await ub.get_entity(channel)
            msgs = await ub.get_messages(ent, ids=int(msg_id))
            txt = getattr(msgs, "text", "") or ""
            ca = _extract_ca(txt) or ""
            if ca:
                return ca
        except Exception as e:
            logger.warning(f"entryfix post fetch fail {channel}/{msg_id} via {_ub_name}: {e}")
            continue
    return ""

async def _ef_resolve_call(text):
    """Post link / forward / CA se call key nikalo.
    Returns (call_key, reason). reason: ok | ca_not_tracked | post_not_found | no_input."""
    ca = _extract_ca(text)
    if ca:
        ck = _ef_find_call_by_ca(ca)
        if ck:
            return ck, "ok"
        return None, "ca_not_tracked"
    ch, mid = _ef_parse_link(text)
    if ch and mid:
        if ch.lower() == "wizardscan":
            ck = _ef_find_call_by_msg_id(mid)
            if ck:
                return ck, "ok"
        ca2 = await _ef_fetch_post_ca(ch, mid)
        if ca2:
            ck = _ef_find_call_by_ca(ca2)
            if ck:
                return ck, "ok"
            return None, "ca_not_tracked"
        return None, "post_not_found"
    return None, "no_input"

def _ef_fmt_list(vals, cap=25):
    """Milestone list ko compact dikhao: [2, 5, 8] -> '2, 5, 8'."""
    try:
        v = sorted({int(x) for x in (vals or [])})
    except Exception:
        return "koi nahi"
    if not v:
        return "koi nahi"
    if len(v) <= cap:
        return ", ".join(str(x) for x in v)
    return ", ".join(str(x) for x in v[:cap]) + f" ... (+{len(v) - cap} aur)"

async def sc_entryfix_start(update, context):
    st = _sc(context.user_data)
    st.clear()
    st["flow"] = "entryfix"
    st["step"] = "link"
    kb = _back_kb("sc:menu")
    await _send_step(update, context,
        "📝 <b>Entry MC Fix</b>\n\n"
        "Jis call ki entry galat hai, us ki <b>post ka link</b> bhejo.\n"
        "Example: <code>https://t.me/WizardScan/114218</code>\n\n"
        "Ya post <b>forward</b> kar do, ya seedha <b>CA</b> bhej do.\n\n"
        "Bot record dikhayega, phir tum sahi entry MC bata dena.",
        kb)

async def _entryfix_text(update, context, st, step, text):
    if step == "link":
        await _send_step(update, context, "⏳ Post dhoond raha hoon...", _back_kb("sc:menu"))
        ck, reason = await _ef_resolve_call(text)
        if not ck:
            if reason == "ca_not_tracked":
                st["step"] = "ca"
                await _send_step(update, context,
                    "⚠️ Ye CA bot ke record me nahi hai (call track nahi hui).\n\n"
                    "Koi aur <b>CA</b> do, ya sahi post ka link bhejo.",
                    _back_kb("sc:menu"))
            elif reason == "post_not_found":
                st["step"] = "ca"
                await _send_step(update, context,
                    "⚠️ Post se CA nahi mila (post nahi mili ya userbot ne nahi di).\n\n"
                    "Token ka <b>CA</b> seedha bhej do.",
                    _back_kb("sc:menu"))
            else:
                await _send_step(update, context,
                    "⚠️ Samajh nahi aaya. Post ka link, forward, ya CA bhejo.\n"
                    "Example: <code>https://t.me/WizardScan/114218</code>",
                    _back_kb("sc:menu"))
            return True
        await _entryfix_show(update, context, st, ck)
        return True
    if step == "ca":
        ca = _extract_ca(text) or text.strip()
        if len(ca) < 32:
            await _send_step(update, context,
                "⚠️ Ye CA nahi lag raha. Poora CA dobara do.", _back_kb("sc:menu"))
            return True
        ck = _ef_find_call_by_ca(ca)
        if not ck:
            await _send_step(update, context,
                "⚠️ Ye CA bot ke record me nahi hai (call track nahi hui).\n\n"
                "Koi aur <b>CA</b> do.",
                _back_kb("sc:menu"))
            return True
        await _entryfix_show(update, context, st, ck)
        return True
    if step == "entry":
        return await _entryfix_new_entry(update, context, st, text)
    if step == "confirm":
        ct = st.get("confirm_text") or ""
        kb = _kb([
            [_btn("✅ Confirm Karo", "sc:ef_confirm")],
            [_btn("❌ Cancel", "sc:ef_cancel")],
        ])
        await _send_step(update, context,
            (ct + "\n\nConfirm ya Cancel dabao.") if ct else
            "Confirm ya Cancel dabao.",
            kb)
        return True
    return True

async def _entryfix_show(update, context, st, call_key):
    tc = _need("tracked_calls") or {}
    call = tc.get(call_key)
    if not call:
        await _send_step(update, context,
            "⚠️ Call record nahi mila. Dobara shuru karo.", _back_kb("sc:menu"))
        return
    channel = (call.get("channel") or "").lstrip("@")
    ca = call.get("ca") or ""
    chain = (call.get("chain") or "SOL").upper()
    symbol = (call.get("symbol") or "UNKNOWN").upper()
    old_entry = float(call.get("entry_mc") or 0)
    peak_mc = float(call.get("peak_mc") or 0)
    old_peak = float(call.get("peak_ratio") or 0)
    live_mc = 0.0
    fetch = _need("fetch_dexscreener")
    if fetch and ca:
        try:
            dex = await asyncio.wait_for(fetch(ca), timeout=10)
            if dex:
                live_mc = float((dex or {}).get("mcap") or 0)
        except Exception as e:
            logger.warning(f"entryfix live mc fail {ca[:12]}: {e}")
            live_mc = 0.0
    sm = _need("sent_milestones") or {}
    try:
        sent = sorted({int(x) for x in (sm.get(call_key) or [])})
    except Exception:
        sent = []
    pts = 0
    tiers = []
    try:
        _gcp = _need("get_channel_points")
        if _gcp:
            pts = int(_gcp(channel) or 0)
        _lcp = _need("load_channel_points")
        if _lcp:
            _pd = _lcp() or {}
            _ent = _pd.get((channel or "").lower(), {}) or {}
            tiers = list((_ent.get("awarded_tiers") or {}).get(call_key, []))
    except Exception:
        pass
    st["call_key"] = call_key
    st["channel"] = channel
    st["ca"] = ca
    st["chain"] = chain
    st["symbol"] = symbol
    st["old_entry_mc"] = old_entry
    st["old_entry_price"] = float(call.get("entry_price") or 0)
    st["peak_mc"] = peak_mc
    st["old_peak_ratio"] = old_peak
    st["live_mc"] = live_mc
    st["old_tiers"] = tiers
    st["old_points"] = pts
    st["sent_ms"] = sent
    st["step"] = "entry"
    ca_short = (ca[:8] + "..." + ca[-6:]) if len(ca) > 16 else ca
    live_txt = _fmt_mc(live_mc) if live_mc > 0 else "nahi mili"
    await _send_step(update, context,
        f"📝 <b>Entry MC Fix</b> - record mil gaya:\n\n"
        f"🪙 <b>${html.escape(symbol)}</b> · @{html.escape(channel)} ({html.escape(chain)})\n"
        f"CA: <code>{html.escape(ca_short)}</code>\n\n"
        f"📌 Entry MC (tracked): <b>{_fmt_mc(old_entry)}</b> (src: {html.escape(str(call.get('entry_src') or '?'))})\n"
        f"📈 ATH / Peak MC: <b>{_fmt_mc(peak_mc)}</b> = <b>{_fmt_x(old_peak)}</b>\n"
        f"📊 Live MC abhi: <b>{live_txt}</b>\n"
        f"🏅 Sent milestones: <b>{_ef_fmt_list(sent)}</b>\n"
        f"⭐ Channel points: <b>{pts}</b> (is call ke tiers: {tiers if tiers else 'koi nahi'})\n\n"
        "<b>Sahi entry MC kya hai?</b>\n"
        "Sirf number bhejo, jaise <code>5000</code> ya <code>5K</code>.",
        _back_kb("sc:menu"))

async def _entryfix_new_entry(update, context, st, text):
    mc = _parse_mc(text)
    old_entry = float(st.get("old_entry_mc") or 0)
    peak_mc = float(st.get("peak_mc") or 0)
    if mc <= 0:
        await _send_step(update, context,
            "⚠️ MC samajh nahi aayi. Aise likho: <code>5000</code> ya <code>5K</code> ya <code>1.2M</code>",
            _back_kb("sc:menu"))
        return True
    if old_entry > 0 and abs(mc - old_entry) < 1e-9:
        _reset(context.user_data)
        await context.bot.send_message(update.effective_chat.id,
            f"✅ Entry pehle se hi theek hai (<b>{_fmt_mc(old_entry)}</b>). Kuch change nahi kia.",
            parse_mode="HTML")
        return True
    if peak_mc > 0 and mc > peak_mc:
        await _send_step(update, context,
            f"⚠️ Ye entry (<b>{_fmt_mc(mc)}</b>) peak MC (<b>{_fmt_mc(peak_mc)}</b>) se zyada hai - aisa ho nahi sakta.\n\n"
            "Sahi entry dobara do.",
            _back_kb("sc:menu"))
        return True
    new_peak = round((peak_mc / mc), 4) if (peak_mc > 0 and mc > 0) else 0.0
    get_mil = _need("get_milestones")
    milestones = get_mil() if get_mil else [2, 3, 4, 5, 6, 7, 8, 9, 10]
    reached = [m for m in milestones if m <= new_peak]
    postable = list(milestones)
    is_champ = False
    _badge_fn = _need("_get_kol_badge")
    if _badge_fn:
        try:
            _bd = _badge_fn(st.get("channel") or "")
            if _bd and _bd.get("type") == "champions":
                is_champ = True
                _cm = _need("CHAMPION_MILESTONES")
                if _cm:
                    postable = list(_cm)
        except Exception:
            pass
    mp = _need("milestone_posts") or {}
    posted = set()
    for _k in ((mp.get(st.get("call_key"), {}) or {}).keys()):
        try:
            posted.add(int(_k))
        except Exception:
            continue
    unposted = [m for m in reached if m in postable and m not in posted]
    alert_x = max(unposted) if unposted else 0
    _tiers_all = _need("POINT_TIERS") or [(50, 50), (10, 25), (2, 10)]
    new_tiers = sorted([t for t, _p in _tiers_all if t <= new_peak])
    old_tiers = list(st.get("old_tiers") or [])
    old_contrib = _ef_tier_points(old_tiers)
    new_contrib = _ef_tier_points(new_tiers)
    pts_delta = new_contrib - old_contrib
    old_points = int(st.get("old_points") or 0)
    new_points = max(0, old_points + pts_delta)
    old_sent = list(st.get("sent_ms") or [])
    added = [m for m in reached if m not in set(old_sent)]
    removed = [m for m in old_sent if m not in set(reached)]
    st["new_entry_mc"] = mc
    st["new_peak_ratio"] = new_peak
    st["reached"] = reached
    st["alert_x"] = alert_x
    st["new_tiers"] = new_tiers
    st["pts_delta"] = pts_delta
    st["new_points"] = new_points
    st["is_champ"] = is_champ
    st["step"] = "confirm"
    if added and removed:
        ms_txt = f"<b>{len(old_sent)}</b> → <b>{len(reached)}</b> ({len(added)} naye, {len(removed)} hatenge)"
    elif added:
        ms_txt = f"<b>{len(old_sent)}</b> → <b>{len(reached)}</b> ({len(added)} naye add honge)"
    elif removed:
        ms_txt = f"<b>{len(old_sent)}</b> → <b>{len(reached)}</b> ({len(removed)} hatenge)"
    else:
        ms_txt = f"<b>{len(reached)}</b> (koi change nahi)"
    if alert_x and alert_x >= 2:
        alert_txt = f"📣 Alert: <b>{_fmt_x(alert_x)}</b> post hogi (sab se upar wali nayi)."
    elif reached:
        alert_txt = "📣 Alert: koi nayi nahi - jo milestones reach hue wo pehle se post ho chuke hain."
    else:
        alert_txt = "📣 Alert: koi nahi - is call ne 2x kabhi nahi mara."
    if pts_delta > 0:
        pts_txt = f"⭐ Points: <b>{old_points}</b> → <b>{new_points}</b> (+{pts_delta})"
    elif pts_delta < 0:
        pts_txt = f"⭐ Points: <b>{old_points}</b> → <b>{new_points}</b> ({pts_delta})"
    else:
        pts_txt = f"⭐ Points: <b>{old_points}</b> (koi change nahi)"
    summary = (
        "📝 <b>Entry MC Fix</b> - confirm karo:\n\n"
        f"@{html.escape(st.get('channel') or '')} · <b>${html.escape(st.get('symbol') or '')}</b> ({html.escape(st.get('chain') or '')})\n\n"
        f"Entry: <b>{_fmt_mc(old_entry)}</b> → <b>{_fmt_mc(mc)}</b>\n"
        f"Peak: <b>{_fmt_mc(peak_mc)}</b> = <b>{_fmt_x(float(st.get('old_peak_ratio') or 0))}</b> → <b>{_fmt_x(new_peak)}</b>\n"
        f"Milestones: {ms_txt}\n"
        f"{pts_txt}\n"
        f"{alert_txt}\n\n"
        "Confirm karo?"
    )
    st["confirm_text"] = summary
    kb = _kb([
        [_btn("✅ Confirm Karo", "sc:ef_confirm")],
        [_btn("❌ Cancel", "sc:ef_cancel")],
    ])
    await _send_step(update, context, summary, kb)
    return True

async def _entryfix_apply(update, context):
    ud = context.user_data
    st = _sc(ud)
    try:
        _uid = update.effective_user.id if update.effective_user else None
        _is_owner = _need("is_admin_or_owner")
        if _is_owner:
            if not _is_owner(_uid):
                _reset(ud)
                return
        else:
            _oids = _need("OWNER_IDS") or []
            if _uid not in _oids:
                _reset(ud)
                return
    except Exception:
        pass
    call_key = st.get("call_key") or ""
    new_entry = float(st.get("new_entry_mc") or 0)
    if not call_key or new_entry <= 0:
        await _send_step(update, context, "⚠️ Data adhoora hai. Dobara shuru karo.", _back_kb("sc:menu"))
        return
    tc = _need("tracked_calls") or {}
    call = tc.get(call_key)
    if not call:
        _reset(ud)
        await context.bot.send_message(update.effective_chat.id,
            "⚠️ Call record ab nahi mila (delete ho gaya ho ga). Kuch change nahi hua.",
            parse_mode="HTML")
        return
    old_entry = float(call.get("entry_mc") or 0)
    if abs(old_entry - float(st.get("old_entry_mc") or 0)) > 1e-9:
        _reset(ud)
        await context.bot.send_message(update.effective_chat.id,
            "⚠️ Record badal gaya tha (entry ab pehle jaisi nahi). Dobara shuru karo.",
            parse_mode="HTML")
        return
    peak_mc = float(call.get("peak_mc") or 0)
    if peak_mc > 0 and new_entry > peak_mc:
        _reset(ud)
        await context.bot.send_message(update.effective_chat.id,
            "⚠️ Nayi entry peak MC se zyada hai. Kuch change nahi hua.",
            parse_mode="HTML")
        return
    await _send_step(update, context,
        "⏳ Entry theek ho rahi hai - record, points aur alert...", None)
    ok, detail = await _ef_do_fix(context, st, call)
    _reset(ud)
    if ok:
        await context.bot.send_message(update.effective_chat.id, detail, parse_mode="HTML")
    else:
        await context.bot.send_message(update.effective_chat.id,
            f"⚠️ Fix karte waqt masla aaya: {html.escape(str(detail))}\nLog check karo ya dobara try karo.",
            parse_mode="HTML")

def _ef_backup_data_files():
    """4 data files ko *.bak_entryfix par copy karo (pehle se ho to chhoro).
    Pehle flush karo taake disk par fresh state ho. Returns True/False."""
    import shutil as _shutil
    import os as _os
    _flush = _need("flush_all_to_disk")
    if _flush:
        try:
            _flush()
        except Exception:
            pass
    _dp = _need("_dp")
    ok = True
    for _name in _EF_FILES:
        _src = None
        try:
            if _dp:
                _cand = _dp(_name)
                if _cand and _os.path.exists(_cand):
                    _src = _cand
            if not _src:
                for _cand in (os.path.join("data", _name), os.path.join("/opt/bot/data", _name)):
                    if _os.path.exists(_cand):
                        _src = _cand
                        break
        except Exception:
            _src = None
        if not _src:
            continue
        try:
            _bak = _src + ".bak_entryfix"
            if not _os.path.exists(_bak):
                _shutil.copy2(_src, _bak)
        except Exception as _e:
            logger.warning(f"entryfix backup fail {_name}: {_e}")
            ok = False
    return ok

async def _ef_do_fix(context, st, call):
    """Entry + milestones + points theek karo, phir latest X alert post karo.
    Returns (ok, owner_message_html)."""
    call_key = st.get("call_key") or ""
    channel = (st.get("channel") or "").lstrip("@")
    ca = st.get("ca") or ""
    chain = (st.get("chain") or "SOL").upper()
    symbol = (st.get("symbol") or "UNKNOWN").upper()
    old_entry = float(st.get("old_entry_mc") or 0)
    old_price = float(st.get("old_entry_price") or 0)
    peak_mc = float(st.get("peak_mc") or 0)
    new_entry = float(st.get("new_entry_mc") or 0)
    new_peak = float(st.get("new_peak_ratio") or 0)
    reached = list(st.get("reached") or [])
    alert_x = int(st.get("alert_x") or 0)
    new_tiers = list(st.get("new_tiers") or [])
    old_tiers = list(st.get("old_tiers") or [])
    try:
        _ef_backup_data_files()
        new_price = (old_price * (new_entry / old_entry)) if (old_price and old_entry > 0) else 0.0
        call["entry_mc"] = new_entry
        call["entry_price"] = new_price
        call["entry_fmt"] = _fmt_mc(new_entry)
        call["entry_src"] = "owner_fix"
        call["entry_confirmed"] = True
        call["entry_fix_prev_mc"] = old_entry
        call["entry_fix_at"] = datetime.utcnow().isoformat()
        call["peak_ratio"] = round(new_peak, 4)
        if peak_mc > 0:
            call["peak_mc_fmt"] = _fmt_mc(peak_mc)
        try:
            _lr = float(call.get("last_ratio", 0) or 0)
        except Exception:
            _lr = 0.0
        if _lr > new_peak:
            call["last_ratio"] = round(new_peak, 4)
        sm = _need("sent_milestones")
        if sm is not None:
            _old_sent = set()
            try:
                _old_sent = {int(x) for x in (sm.get(call_key) or [])}
            except Exception:
                _old_sent = set()
            _new_sent = {m for m in (_old_sent | set(reached)) if m <= new_peak}
            sm[call_key] = _new_sent
        pts_delta = 0
        _new_set = set(new_tiers)
        _old_set = set(old_tiers)
        if _new_set != _old_set:
            if _new_set >= _old_set:
                _ap = _need("award_points_for_milestone")
                if _ap:
                    for _t in sorted(_new_set - _old_set):
                        try:
                            _got = await _ap(channel, call_key, _t)
                            pts_delta += int(_got or 0)
                        except Exception as _e:
                            logger.warning(f"entryfix award fail tier {_t}: {_e}")
            else:
                pts_delta = _ef_tier_points(new_tiers) - _ef_tier_points(old_tiers)
                _lock = _need("_points_lock")
                _lcp = _need("load_channel_points")
                _scp = _need("save_channel_points")
                if not (_lcp and _scp):
                    return False, "points helpers nahi mile"
                try:
                    if _lock is not None:
                        await _lock.acquire()
                    try:
                        _pd = _lcp() or {}
                        _key = (channel or "").lower()
                        _ent = _pd.get(_key)
                        if _ent is None:
                            _ent = {"points": 0, "awarded_tiers": {}, "deducted_calls": []}
                            _pd[_key] = _ent
                        _aw = _ent.get("awarded_tiers") or {}
                        _aw[call_key] = list(new_tiers)
                        _ent["awarded_tiers"] = _aw
                        _ent["points"] = max(0, int(_ent.get("points", 0) or 0) + pts_delta)
                        _pd[_key] = _ent
                        _scp(_pd)
                    finally:
                        if _lock is not None:
                            try:
                                _lock.release()
                            except Exception:
                                pass
                except Exception as _e:
                    logger.warning(f"entryfix deduct fail: {_e}")
                    return False, "points update fail"
        _gcp = _need("get_channel_points")
        new_total = int(st.get("old_points") or 0) + pts_delta
        if _gcp:
            try:
                new_total = int(_gcp(channel) or 0)
            except Exception:
                pass
        for _fn in ("_save_tracked", "_save_milestones", "_save_milestone_posts"):
            _f = _need(_fn)
            if _f:
                try:
                    _f()
                except Exception:
                    pass
        _flush = _need("flush_all_to_disk")
        if _flush:
            try:
                _flush()
            except Exception:
                pass
        posted_txt = ""
        if alert_x and alert_x >= 2:
            _sa = _need("send_alert")
            if _sa:
                try:
                    _res = await _sa(context.bot, channel, call.get("msg_id", 0), alert_x,
                                     chain, _fmt_mc(new_entry), _fmt_mc(peak_mc), ca, symbol)
                    if _res is True:
                        _mp = _need("milestone_posts") or {}
                        _pid = ((_mp.get(call_key, {}) or {}).get(str(alert_x)))
                        post_link = f"https://t.me/WizardScan/{_pid}" if _pid else ""
                        posted_txt = f"\n\n📣 <b>{_fmt_x(alert_x)} alert post kar di.</b>" + (f"\n{post_link}" if post_link else "")
                    elif _res == "silent":
                        posted_txt = f"\n\nℹ️ {_fmt_x(alert_x)} record-only hai, post nahi gayi."
                    else:
                        posted_txt = f"\n\n⚠️ {_fmt_x(alert_x)} alert post nahi ho saki (media/video ya network). Record theek hai, alert dobara /setmedia se release kar lo."
                except Exception as _e:
                    logger.warning(f"entryfix alert fail: {_e}")
                    posted_txt = f"\n\n⚠️ {_fmt_x(alert_x)} alert post karte waqt masla aaya. Record theek hai."
            else:
                posted_txt = "\n\n⚠️ send_alert nahi mila, alert post nahi hui."
        elif reached:
            posted_txt = "\n\nℹ️ Koi nayi alert nahi - jo milestones reach hue wo pehle se post ho chuke hain."
        else:
            posted_txt = "\n\nℹ️ Koi alert nahi - is call ne 2x kabhi nahi mara."
        _pd_txt = ""
        if pts_delta > 0:
            _pd_txt = f" (+{pts_delta})"
        elif pts_delta < 0:
            _pd_txt = f" ({pts_delta})"
        msg = (
            "✅ <b>Entry theek ho gayi!</b>\n\n"
            f"@{html.escape(channel)} · <b>${html.escape(symbol)}</b> ({html.escape(chain)})\n"
            f"Entry: <b>{_fmt_mc(old_entry)}</b> → <b>{_fmt_mc(new_entry)}</b>\n"
            f"Peak: <b>{_fmt_mc(peak_mc)}</b> = <b>{_fmt_x(new_peak)}</b> (pehle {_fmt_x(float(st.get('old_peak_ratio') or 0))})\n"
            f"⭐ Points: <b>{int(st.get('old_points') or 0)}</b> → <b>{new_total}</b>{_pd_txt}"
            + posted_txt
        )
        return True, msg
    except Exception as e:
        logger.exception(f"entryfix do_fix fail: {e}")
        return False, str(e)


# ---------------------------------------------------------------- register

def register_skipcall(app):
    """runtime.py main() me call karo: register_skipcall(app)"""
    if CallbackQueryHandler is None:
        return
    # group=-1: button_callback (group 0, no pattern) se PEHLE chale,
    # warna wo "sc:menu" pakar kar kuch kiye baghair rok deta hai.
    app.add_handler(CallbackQueryHandler(sc_callback, pattern=r"^sc:"), group=-1)
    app.add_handler(CallbackQueryHandler(sc_callback, pattern=r"^lt:"), group=-1)
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
