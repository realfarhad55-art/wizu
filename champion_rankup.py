# ===== champion_rankup.py — Champion Rank-Up Alerts (top 5 + new champions) =====
# Loaded by bot.py into ONE shared namespace (no imports of sibling pieces),
# same _PIECES exec style as core / x_alert / leaderboard / commands.
#
# What it does: every 20s it compares the current WizardScan Champion top 10
# against the last known champions stored in data/champion_ranks.json.
# When a KOL IMPROVES inside the top 5 (rank number goes down), ENTERS the
# top 5, or NEWLY QUALIFIES as a champion at any rank 1-10 (e.g. the owner
# gives a new channel 120 points and it lands at #7), it posts one alert
# with a freshly generated video to @WizardScan. It NEVER posts on a rank
# drop (e.g. #4 -> #5) or when a rank is unchanged, and a champion moving
# between ranks 6-10 (e.g. #8 -> #7) does NOT post. Ranks 6-10 use the
# generic champion-entry template and the rank-5 purple theme/video.
#
# Ranking reuses leaderboard.py build_champions_text() for post 134 EXACTLY:
# qualify = points >= POINTS_FOR_CHAMPION (100) AND a real 2x+ call
# (champion_total_x >= 2, snapshot/exclusion aware), sort by
# (total champion X desc, points desc). NOTE: the build_champions_text()
# docstring says "Sorted by points descending" but the code sorts by
# (best_x, points) — total-X first, points only as tiebreak. This module
# reuses the CODE order, not the docstring. See _rankup_current_top5().
#
# Video: built per post by champion_rankup_video.build_rankup_video(), then
# deleted from cache after a successful post (same idea as
# _delete_champion_video in x_alert.py). No /setmedia media-hold applies.
#
# Owner DM (Nov 15): after a successful @WizardScan post, the SAME post is
# also delivered to the KOL/channel owner — exactly like the X alerts do
# (x_alert.py _forward_alert_recipients / _forward_alert_post). X alerts do
# NOT re-send a copy or a shorter text: they FORWARD the published
# @WizardScan message with bot.forward_message(chat_id=owner_id,
# from_chat_id=TARGET_CHANNEL, message_id=wizard_post_id), so the DM is
# byte-identical to the channel post (same video + same message, premium
# emojis preserved). Rank-ups do the same — there is NO shorter DM variant.
# Owner lookup is the same too: core.py load_kol_owners() reads
# data/kol_owners.json, {channel.lower(): telegram user_id}, set via
# /setkolowner. No owner ID is ever hardcoded here. A DM failure never
# fails the rank-up (see _rankup_post_rankup); a missing owner just
# skips the DM silently.
#
# Failure rule (deliberate, see DEPLOY.md): if the video build or the send
# fails, the stored rank for that channel is NOT updated, so the next job
# run retries the same rank change. A failed post is never silently dropped.
#
# Deep link: the message links https://t.me/WIZARD_SCAN_BOT?start=rec_<channel>
# (channel lowercased, no @). No such payload existed before: commands.py
# cmd_start needs the small rec_ branch (see DEPLOY.md) which calls
# rankup_handle_start_rec() in this module — it shows the same record as
# typing @channel in the bot DM (via _send_channel_overview).
#
# Standalone note: only stdlib imports at top level. Every bot-shared name
# (logger, _dp, load_json, get_call_history, ...) is looked up via _g() at
# CALL time, so `python3 -c "import champion_rankup"` works with no bot.

import asyncio
import html
import json
import logging
import os
import re
import time

_rankup_log = logging.getLogger("champion_rankup")

# ─── Config ──────────────────────────────────────────────────────────────────

RANKUP_STATE_FILE = "champion_ranks.json"   # data/champion_ranks.json on VPS
RANKUP_TOP_N = 5
RANKUP_CHAMPIONS_N = 10  # Champions post 134 shows the top 10; the state
# file tracks all 10 so a new champion at rank 6-10 is detected too.
RANKUP_JOB_INTERVAL_SECONDS = 20

# Per-rank premium emoji sets. All five sets are in (user sent #5 in the
# original spec; #1, #2, #3 and #4 on Nov 15). Section emojis are
# PER-RANK too: #4 has its own section emojis, ranks 5/1/2/3 share
# 6044166381690166762 for both sections. No rank falls back to another
# rank's set — every rank 1-5 has its own complete entry.
RANKUP_SECTION_EMOJI = 6044166381690166762  # shared section emoji (ranks 5/1/2/3)

RANKUP_EMOJI_SETS = {
    # #5 set — from the original feature spec.
    5: {
        "title": 6037193373436091544,
        "arrow": 6007806331023531511,
        "section_emoji_last5": 6044166381690166762,
        "section_emoji_check": 6044166381690166762,
        "chains": {
            "rh": 6037138397854704130, "arc": 6037488459164164687,
            "base": 6037511201015996211, "ton": 6037419481989390016,
            "sol": 6037570222456577920, "eth": 6037132015533303152,
            "bnb": 6039766892070051674,
        },
    },
    # #4 set — sent by the user Nov 15. Own title/arrow/chains AND own
    # section emojis (different from the shared 6044166381690166762).
    4: {
        "title": 5848220279905460286,
        "arrow": 6005740237005792773,
        "section_emoji_last5": 5846214053436859823,
        "section_emoji_check": 5848234590736490790,
        "chains": {
            "arc": 6037540698851384597, "ton": 6037486178536529387,
            "sol": 6037635312685949492, "eth": 6039834366006272821,
            "base": 6037199953325989452, "bnb": 6037208062224244703,
            "rh": 6037448735011643068,
        },
    },
    # #3 set — sent by the user Nov 15. Title/arrow/chains differ from #5/#2/#1.
    3: {
        "title": 6037621461416418734,
        "arrow": 6008358264385839169,
        "section_emoji_last5": 6044166381690166762,
        "section_emoji_check": 6044166381690166762,
        "chains": {
            "bnb": 6037542756140720771, "arc": 6037525945638724794,
            "rh": 6037202195298918506, "ton": 6037372971788541212,
            "base": 6037499578834492776, "sol": 6037355950833147473,
            "eth": 6037548571526439690,
        },
    },
    # #2 set — sent by the user Nov 15. Title/arrow/chains differ from #5/#1.
    2: {
        "title": 6037086965621335396,
        "arrow": 6008239542899844540,
        "section_emoji_last5": 6044166381690166762,
        "section_emoji_check": 6044166381690166762,
        "chains": {
            "arc": 6039376745830864191, "eth": 6037497774948230444,
            "sol": 6037431443473309063, "base": 6039752130267455401,
            "ton": 6037092652158033923, "rh": 6039573167570166670,
            "bnb": 6037173848514765744,
        },
    },
    # #1 set — sent by the user Nov 15. Different title/arrow/chains from #5.
    1: {
        "title": 6037576755101835442,
        "arrow": 6007814349727473769,
        "section_emoji_last5": 6044166381690166762,
        "section_emoji_check": 6044166381690166762,
        "chains": {
            "bnb": 6037124336131776911, "arc": 6037193644019031688,
            "base": 6037498573812146495, "rh": 6037083241884687506,
            "ton": 6037317699854411201, "sol": 6037164025924557629,
            "eth": 6037294786203887261,
        },
    },
}

RANKUP_CHAMPIONS_URL = "https://t.me/WizardScan/134"

# Titles + paragraphs (English, public posts). NO "best call" anywhere.
# Keys are (old_rank, new_rank); old_rank None = fresh entry into the top 5.
# Only the #5 entry and the four climbs were fixed by the spec; direct
# entries at #4/#3/#2/#1 use the generic entry lines below (assumption,
# see DEPLOY.md — user to confirm or replace the wording).
# Nov 15 user revision: the TITLE carries the Champions-post link (the
# channel name, no @, links to post 134) and the paragraph carries NO
# link at all; #1 paras have no "Number one." prefix and "the top spot"
# is plain text. Titles use "{channel}" (no @) — the video title draws
# the same string.
RANKUP_COPY = {
    (None, 5): (
        "{channel} Breaks Into the Top 5",
        "@{channel} broke into the Top 5 with {points} points and became "
        "Champion KOL Rank #5. A new challenger has entered the elite five.",
    ),
    (5, 4): (
        "{channel} Climbs to Rank #4",
        "@{channel} climbed to Champion KOL Rank #4 with {points} points. "
        "The Top 3 is right above, and the climb is not over yet.",
    ),
    (4, 3): (
        "{channel} Hits Rank #3",
        "@{channel} hit Champion KOL Rank #3 with {points} points and entered "
        "the Top 3. The fight for #1 is getting serious now.",
    ),
    (3, 2): (
        "{channel} Moves Up to Rank #2",
        "@{channel} moved up to Champion KOL Rank #2 with {points} points. "
        "At this pace, #1 is not far. This KOL will not take long to reach the top.",
    ),
    (2, 1): (
        "{channel} Takes Rank #1",
        "@{channel} is now Champion KOL Rank #1 on WizardScan with {points} points. "
        "The top spot is theirs now, and every other KOL is chasing them.",
    ),
    # Generic direct entries (not in the spec - see note above).
    (None, 4): (
        "{channel} Joins the Top 5 at #4",
        "@{channel} joined the Top 5 at Champion KOL Rank #4 with {points} points. "
        "The Top 3 is right above, and the climb is not over yet.",
    ),
    (None, 3): (
        "{channel} Enters the Top 3",
        "@{channel} entered the Top 3 at Champion KOL Rank #3 with {points} points. "
        "The fight for #1 is getting serious now.",
    ),
    (None, 2): (
        "{channel} Debuts at Rank #2",
        "@{channel} debuted at Champion KOL Rank #2 with {points} points. "
        "At this pace, #1 is not far. This KOL will not take long to reach the top.",
    ),
    (None, 1): (
        "{channel} Takes Rank #1",
        "@{channel} is now Champion KOL Rank #1 on WizardScan with {points} points. "
        "The top spot is theirs now, and every other KOL is chasing them.",
    ),
    # Generic champion entries at ranks 6-10 (Nov 16): a channel that
    # newly qualifies as a champion (100+ points AND a real 2x+ call)
    # but lands below the top 5 still gets one post. Titles use
    # "{channel}" (no @) like every other title - the channel name
    # links to the Champions post; paragraphs keep "@{channel}".
    (None, 6): (
        "{channel} Becomes a Champion KOL",
        "@{channel} has earned {points} points and became "
        "Champion KOL Rank #6.",
    ),
    (None, 7): (
        "{channel} Becomes a Champion KOL",
        "@{channel} has earned {points} points and became "
        "Champion KOL Rank #7.",
    ),
    (None, 8): (
        "{channel} Becomes a Champion KOL",
        "@{channel} has earned {points} points and became "
        "Champion KOL Rank #8.",
    ),
    (None, 9): (
        "{channel} Becomes a Champion KOL",
        "@{channel} has earned {points} points and became "
        "Champion KOL Rank #9.",
    ),
    (None, 10): (
        "{channel} Becomes a Champion KOL",
        "@{channel} has earned {points} points and became "
        "Champion KOL Rank #10.",
    ),
}

# ─── Shared-namespace helpers ────────────────────────────────────────────────

def _g(name, default=None):
    """Shared-namespace lookup (bot pieces are exec'd into one namespace)."""
    try:
        return globals().get(name, default)
    except Exception:
        return default


def _rankup_display(channel):
    """First letter upper, rest lower (RANKUP_NAMECAP_NOV17: @Channel,
    not @CHANNEL)."""
    raw = str(channel or "").lstrip("@").strip()
    return raw[:1].upper() + raw[1:].lower() if raw else raw


def _rankup_fmt_x(x):
    """10x, 2x, 15x, 12.3x, 77x — trim trailing .0, one decimal when needed.
    (core.fmt_x gives '10.0x' for 10, which does not match the spec sample.)"""
    try:
        v = float(x or 0)
    except (TypeError, ValueError):
        return "1x"
    if v <= 0:
        return "1x"
    if v >= 100:
        return f"{v:.0f}x"
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return f"{s}x"


def _rankup_emoji_set(rank):
    """Return (emoji_set_dict, used_fallback_bool) for a rank.
    Every rank 1-5 has its own complete set — no rank falls back to
    another rank's set. Ranks 6-10 use the rank-5 set (purple theme)
    by design. An out-of-range rank (< 1) raises KeyError (callers
    treat it as a failed post and retry; ranks are always 1-10)."""
    try:
        r = int(rank)
    except (TypeError, ValueError):
        r = RANKUP_TOP_N
    if r < 1:
        raise KeyError(rank)
    if r > RANKUP_TOP_N:
        r = RANKUP_TOP_N
    return RANKUP_EMOJI_SETS[r], False


def _rankup_copy(old_rank, new_rank, channel_display, points):
    """(title, paragraph) for a rank change, with placeholders filled.
    The paragraph is PLAIN text now (Nov 15 user revision): it carries
    NO link — the Champions-post link lives on the channel name in the
    TITLE instead (build_rankup_message wraps it). The channel is
    html-escaped HERE before formatting, so build_rankup_message must
    append the paragraph RAW — escaping it would print visible entities
    if a handle ever carried one. {points}/{old}/{new} are ints.
    (Telegram handles are [A-Za-z0-9_] so the escape is a no-op for real
    channels; it only guards the HTML shape.) Titles use "{channel}"
    (no @); paragraphs keep "@{channel}"."""
    tpl = RANKUP_COPY.get((old_rank, new_rank))
    if tpl is None:  # unknown climb shape — generic improvement line
        tpl = (
            "{channel} Climbs to #{new}",
            "@{channel} moved up to #{new} on the "
            "WizardScan Champion leaderboard with {points} points.",
        )
    title, para = tpl
    kw = {"channel": html.escape(channel_display), "points": points,
          "old": old_rank if old_rank is not None else "",
          "new": new_rank}
    return title.format(**kw), para.format(**kw)


def _rankup_record_url(channel):
    """Deep link that opens the bot and shows this channel's full record.
    Payload rec_<channel> is handled by cmd_start (see DEPLOY.md)."""
    key = str(channel or "").lstrip("@").strip().lower()
    bot_link = _g("BOT_LINK") or "https://t.me/WIZARD_SCAN_BOT"
    return f"{str(bot_link).rstrip('/') }?start=rec_{key}"


def _rankup_tg_emoji(emoji_id, fallback):
    """Bot API <tg-emoji> tag (same shape as core._history_emoji)."""
    return (f'<tg-emoji emoji-id="{emoji_id}">'
            f"{html.escape(str(fallback))}</tg-emoji>")


def _rankup_build_entities(parsed_text, base_entities, emoji_ids):
    """Positional-only premium-emoji entities for rank-up posts.
    (RANKUP_EMOJI_FIX_NOV17) The shared _build_premium_entities has
    special cases that mis-fire on rank-up rows: its MC-separator teer
    lock reads a numeric-looking token symbol ($1.0) followed by an X
    value (2x) as an entry-MC/current-MC pair, so that row's arrow gets
    the red teer emoji and every later emoji shifts by one. Seen live
    Nov 17: yellow rank-1 $1.0 row, purple rank-5 $S07 row. Rank-up
    text has NO MC values and needs NO special cases, so assign
    emoji_ids strictly in placeholder order. Same UTF-16 offset math
    as the shared builder; base (bold/link) entities are kept."""
    try:
        from telethon.tl.types import MessageEntityCustomEmoji
    except Exception:
        return base_entities or []
    ids = []
    try:
        ids = [int(e) for e in (emoji_ids or []) if e]
    except Exception:
        ids = []
    if not ids:
        return base_entities or []
    PH = "\U0001F52E"
    PH_LEN = len(PH)
    emoji_u16 = len(PH.encode("utf-16-le")) // 2
    custom = []
    pos_index = 0
    utf16_off = 0
    i = 0
    text = str(parsed_text or "")
    while i < len(text):
        if text[i:i + PH_LEN] == PH:
            eid = ids[min(pos_index, len(ids) - 1)]
            pos_index += 1
            custom.append(MessageEntityCustomEmoji(
                offset=utf16_off, length=emoji_u16, document_id=int(eid)))
            utf16_off += emoji_u16
            i += PH_LEN
            continue
        utf16_off += len(text[i].encode("utf-16-le")) // 2
        i += 1
    return (base_entities or []) + custom


def _rankup_strip_tg_emoji(text):
    """Drop <tg-emoji> tags, keep their fallback glyph (plain retry path)."""
    return re.sub(r"<tg-emoji[^>]*>(.*?)</tg-emoji>", r"\1",
                  str(text or ""), flags=re.DOTALL)

# ─── Alpha calls (Last 5 section) ────────────────────────────────────────────

def _rankup_call_peak(call):
    """Peak X of one get_call_history() row (same source as _call_peak_x)."""
    fn = _g("_call_peak_x")
    if callable(fn):
        try:
            return float(fn(call) or 0)
        except Exception:
            pass
    try:
        cx = float(call.get("current_x", 0) or 0)
    except (TypeError, ValueError):
        cx = 0.0
    try:
        hx = float(call.get("highest_x", 0) or 0)
    except (TypeError, ValueError):
        hx = 0.0
    return max(cx, hx)


def _rankup_call_time_key(call):
    """Sort key for 'most recent first' (tracked_since ISO string sorts)."""
    fn = _g("_call_time")
    if callable(fn):
        try:
            dt = fn(call)
            return dt.isoformat() if dt is not None else ""
        except Exception:
            pass
    return str(call.get("tracked_since", "") or "")


def _rankup_normalize_alpha_call(call):
    """One history row -> {symbol, chain, x, msg_id} or None if not >= 2x.
    STRICT 2x filter (verified Nov 15): the X used is the call's PEAK /
    final X — max of every X signal on the row ("x" when a caller passed
    one, else/also _rankup_call_peak = max(current_x, highest_x), where
    get_call_history's current_x is already peak-aware, floored at the
    highest confirmed milestone). A call that peaked at 1.9x, 1.5x or
    1.2x does NOT qualify even if it is recent; exactly 2.0x DOES.
    The comparison is `x < 2 -> None`, i.e. >= 2.0 passes — never > 1.0
    or >= 1.5. This one function gates BOTH consumers: the message list
    (build_rankup_message re-normalizes) and the video renderer calls
    (_rankup_video_kwargs normalizes too), so no sub-2x call can reach
    either output even if a caller passes unfiltered rows."""
    try:
        xs = []
        try:
            xs.append(float(call.get("x") or 0))
        except (TypeError, ValueError):
            pass
        try:
            xs.append(float(_rankup_call_peak(call) or 0))
        except Exception:
            pass
        x = max(xs) if xs else 0.0
    except (TypeError, ValueError):
        return None
    if x < 2:
        return None
    return {
        "symbol": str(call.get("symbol", "TOKEN") or "TOKEN"),
        "chain": str(call.get("chain", "") or ""),
        "x": x,
        "msg_id": call.get("msg_id", 0),
    }


def _rankup_alpha_calls(channel, limit=5):
    """Most recent alpha calls (peak X >= 2), most recent first, max 5.
    Uses get_call_history() (already tracked_since-desc) and re-sorts by
    call time defensively. Returns [] when the bot namespace is absent."""
    fn = _g("get_call_history")
    if not callable(fn):
        return []
    try:
        calls = fn(channel) or []
    except Exception as e:
        _rankup_log.warning(f"🏆 Rank-up: get_call_history @{channel} failed: {e}")
        return []
    norm = []
    for c in calls:
        try:
            n = _rankup_normalize_alpha_call(c)
        except Exception:
            continue
        if n is None:
            continue
        n["_t"] = _rankup_call_time_key(c)
        norm.append(n)
    norm.sort(key=lambda d: d.get("_t", ""), reverse=True)
    out = []
    for n in norm[:limit]:
        n.pop("_t", None)
        out.append(n)
    return out


# ─── Message builder ─────────────────────────────────────────────────────────
# Builds TWO versions in one pass so the placeholder order can never drift:
#   plain: 🔮 placeholders + ordered emoji_ids  (userbot / _build_premium_entities)
#   html:  <tg-emoji> tags inline                (Bot API fallback)
# Both carry the same visible text. Fallback glyphs: 🔮 everywhere, ➤ arrow.

def build_rankup_message(channel, rank, points, alpha_calls=None, old_rank=None):
    """Return {html, plain, emoji_ids, title, para, record_url, rank, points,
    channel_display}. alpha_calls may be passed in (tests / preview) or
    fetched live via get_call_history() when None."""
    ch_disp = _rankup_display(channel)
    ch_key = str(channel or "").lstrip("@").strip().lower()
    title, para = _rankup_copy(old_rank, rank, ch_disp, points)
    emoji_set, _fb = _rankup_emoji_set(rank)
    chains = emoji_set.get("chains", {})
    arrow_id = emoji_set.get("arrow")
    # Section emojis are PER-RANK (#4 has its own; 5/1/2/3 share the
    # 6044166381690166762 set). Fall back to the shared constant only if
    # a set entry somehow lacks the field.
    section_last5_id = emoji_set.get("section_emoji_last5",
                                     RANKUP_SECTION_EMOJI)
    section_check_id = emoji_set.get("section_emoji_check",
                                     RANKUP_SECTION_EMOJI)
    record_url = _rankup_record_url(channel)

    if alpha_calls is None:
        alpha_calls = _rankup_alpha_calls(channel)
    calls = []
    for c in (alpha_calls or []):
        n = _rankup_normalize_alpha_call(c)
        if n is not None:
            calls.append(n)
    calls = calls[:5]

    plain_lines, html_lines, emoji_ids = [], [], []

    def _em(emoji_id, fallback):
        emoji_ids.append(int(emoji_id))
        return "🔮", _rankup_tg_emoji(emoji_id, fallback)

    # Line 1: title emoji + bold title. The channel name (no @) links to
    # the Champions post (Nov 15 user revision); the rest of the title
    # follows as plain bold text. The title from _rankup_copy always
    # starts with the channel display name.
    title_rest = title[len(ch_disp):]
    title_link = (f'<a href="{RANKUP_CHAMPIONS_URL}">'
                  f'{html.escape(ch_disp)}</a>')
    title_html = f"<b>{title_link}{html.escape(title_rest)}</b>"
    _p, _h = _em(emoji_set["title"], "🔮")
    plain_lines.append(f"{_p} {title_html}")
    html_lines.append(f"{_h} {title_html}")
    plain_lines.append("")
    html_lines.append("")
    # Paragraph — appended RAW, not html.escape()d: it is plain text
    # (no link since the Nov 15 revision), and escaping here would only
    # risk printing entities if a handle ever carried one.
    plain_lines.append(para)
    html_lines.append(para)

    # Last N Alpha Calls — hidden entirely when there are zero 2x+ calls.
    # The header carries the ACTUAL count (Nov 16 fix): a channel with
    # only 3 qualifying calls shows "Last 3 Alpha Calls", not "Last 5".
    if calls:
        plain_lines.append("")
        html_lines.append("")
        _p, _h = _em(section_last5_id, "🔮")
        last_header = f"Last {len(calls)} Alpha Calls"
        plain_lines.append(f"{_p} <b>{last_header}</b>")
        html_lines.append(f"{_h} <b>{last_header}</b>")
        # One blank line between the header and the first call.
        plain_lines.append("")
        html_lines.append("")
        for c in calls:
            chain_key = str(c.get("chain", "") or "").lower()
            chain_id = chains.get(chain_key, chains.get("sol"))
            _pc, _hc = _em(chain_id, "🔮")
            _pa, _ha = _em(arrow_id, "➤")
            mid = c.get("msg_id")
            # msg_id 0 / missing -> channel link (same rule as build_alert).
            link = (f"https://t.me/{ch_key}/{mid}"
                    if mid else f"https://t.me/{ch_key}")
            sym = html.escape(str(c.get("symbol", "TOKEN")).upper())
            x_str = _rankup_fmt_x(c.get("x"))
            plain_lines.append(
                f'{_pc} <a href="{link}">${sym}</a> {_pa} {x_str}')
            html_lines.append(
                f'{_hc} <a href="{link}">${sym}</a> {_ha} {x_str}')

    # Check KOL Performance — the header text ITSELF is the deep link
    # into the bot DM record (Nov 15 user revision). No separate
    # "See @Channel full record" line below it, no extra message.
    plain_lines.append("")
    html_lines.append("")
    _p, _h = _em(section_check_id, "🔮")
    check_link = (f'<a href="{html.escape(record_url, quote=True)}">'
                  "<b>Check KOL Performance</b></a>")
    plain_lines.append(f"{_p} {check_link}")
    html_lines.append(f"{_h} {check_link}")

    return {
        "html": "\n".join(html_lines),
        "plain": "\n".join(plain_lines),
        "emoji_ids": emoji_ids,
        "title": title,
        "para": para,
        "record_url": record_url,
        "rank": rank,
        "points": points,
        "channel_display": ch_disp,
    }


# ─── Persisted state ─────────────────────────────────────────────────────────

def _rankup_state_path():
    dp = _g("_dp")
    if callable(dp):
        try:
            return dp(RANKUP_STATE_FILE)
        except Exception:
            pass
    data_dir = _g("DATA_DIR") or "."
    return os.path.join(str(data_dir), RANKUP_STATE_FILE)


def _rankup_load_ranks():
    """Return (ranks_dict, file_existed). Keys are lowercased channels,
    values are last known champion ranks (1-10: the top 5 plus ranks
    6-10, so a new champion outside the top 5 is detected too). A
    corrupt file -> ({}, False) so the next run records fresh instead
    of crashing the job. Old top-5-only files still parse fine."""
    path = _rankup_state_path()
    existed = os.path.exists(path)
    if not existed:
        return {}, False
    load = _g("load_json")
    try:
        if callable(load):
            data = load(path, {})
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
    except Exception as e:
        _rankup_log.warning(f"🏆 Rank-up: state file unreadable, starting fresh: {e}")
        return {}, False
    out = {}
    try:
        for k, v in dict(data or {}).items():
            r = int(v)
            if 1 <= r <= RANKUP_CHAMPIONS_N:
                out[str(k).lower()] = r
    except Exception:
        return {}, False
    return out, True


def _rankup_save_ranks(ranks):
    """Atomic when the bot's save_json is available (same fix as core.py)."""
    path = _rankup_state_path()
    clean = {str(k).lower(): int(v) for k, v in dict(ranks or {}).items()
             if 1 <= int(v) <= RANKUP_CHAMPIONS_N}
    save = _g("save_json")
    try:
        if callable(save):
            save(path, clean)
        else:
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(clean, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
    except Exception as e:
        _rankup_log.warning(f"🏆 Rank-up: state save failed {path}: {e}")


# --- Per-stint rank-up dedup (RANKUP_DEDUP_NOV20) ---
# Rule (user, 2026-11-20): ranks 2-5 alert ONCE per champion stint. Once a
# rank's alert has fired, it never fires again in the same stint, even if
# the channel drops and climbs back to that rank. Rank 1 alerts EVERY time
# it is reached (no dedup). When a channel leaves the top 10 (points fall
# below 100), its record is wiped, so a fresh stint alerts at 5/4/3/2
# again, once each. Ranks 6-10 new-champion entries are untouched.
# State file: data/rankup_alerted.json, {channel_lower: [ranks]}.
# Only successful posts are marked (a failed post retries next run, same
# as the stored-rank failure rule). A skipped event still advances the
# stored rank (via _rankup_next_state) so the job does not re-detect it
# every 20s.

RANKUP_ALERTED_FILE = "rankup_alerted.json"  # data/rankup_alerted.json on VPS


def _rankup_alerted_path():
    dp = _g("_dp")
    if callable(dp):
        try:
            return dp(RANKUP_ALERTED_FILE)
        except Exception:
            pass
    data_dir = _g("DATA_DIR") or "."
    return os.path.join(str(data_dir), RANKUP_ALERTED_FILE)


def _rankup_load_alerted():
    """Return {channel_lower: [ranks alerted in the current stint]}.
    Only ranks 2-5 are ever stored (rank 1 is never deduped). A missing
    or corrupt file returns {} (fresh stint for everyone)."""
    path = _rankup_alerted_path()
    if not os.path.exists(path):
        return {}
    load = _g("load_json")
    try:
        if callable(load):
            data = load(path, {})
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
    except Exception as e:
        _rankup_log.warning(f"Rank-up: alerted file unreadable, starting fresh: {e}")
        return {}
    out = {}
    try:
        for k, v in dict(data or {}).items():
            ranks = sorted({int(r) for r in (v or []) if 2 <= int(r) <= 5})
            if ranks:
                out[str(k).lower()] = ranks
    except Exception:
        return {}
    return out


def _rankup_save_alerted(alerted):
    """Atomic when the bot's save_json is available (same fix as core.py)."""
    path = _rankup_alerted_path()
    clean = {}
    for k, v in dict(alerted or {}).items():
        ranks = sorted({int(r) for r in (v or []) if 2 <= int(r) <= 5})
        if ranks:
            clean[str(k).lower()] = ranks
    save = _g("save_json")
    try:
        if callable(save):
            save(path, clean)
        else:
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(clean, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
    except Exception as e:
        _rankup_log.warning(f"Rank-up: alerted save failed {path}: {e}")


def _rankup_filter_events(events, alerted):
    """Dedup top-5 rank-up events per champion stint (pure, unit-tested).
    Rank 1 always passes (alerts every time). Ranks 2-5 pass only if
    that rank has not alerted yet in this stint. Rank 6-10 events (new
    champions) pass untouched. Returns (kept, skipped)."""
    kept, skipped = [], []
    for ev in (events or []):
        try:
            nr = int(ev.get("new_rank"))
        except (TypeError, ValueError):
            kept.append(ev)
            continue
        if nr == 1:
            kept.append(ev)
        elif 2 <= nr <= 5:
            key = str(ev.get("channel", "")).lstrip("@").strip().lower()
            if nr in (alerted or {}).get(key, []):
                skipped.append(ev)
            else:
                kept.append(ev)
        else:
            kept.append(ev)
    return kept, skipped


def _rankup_mark_alerted(alerted, ok_events):
    """Record ranks 2-5 that just posted successfully. Rank 1 is never
    recorded (it always alerts). Returns the updated dict."""
    out = {str(k).lower(): sorted({int(r) for r in (v or []) if 2 <= int(r) <= 5})
           for k, v in dict(alerted or {}).items()}
    for ev in (ok_events or []):
        try:
            nr = int(ev.get("new_rank"))
        except (TypeError, ValueError):
            continue
        if 2 <= nr <= 5:
            key = str(ev.get("channel", "")).lstrip("@").strip().lower()
            ranks = set(out.get(key, []))
            ranks.add(nr)
            out[key] = sorted(ranks)
    return out


def _rankup_prune_alerted(alerted, current_top10):
    """Drop alerted records for channels no longer in the top 10 (they
    left Champions, so the next stint starts fresh). Also sanitizes
    stored ranks to 2-5 and drops empty lists. Returns
    (pruned_dict, removed_keys)."""
    keep = {str(c or "").lstrip("@").strip().lower()
            for c in (current_top10 or [])}
    pruned = {}
    removed = []
    for k, v in dict(alerted or {}).items():
        key = str(k).lower()
        if key in keep:
            ranks = sorted({int(r) for r in (v or []) if 2 <= int(r) <= 5})
            if ranks:
                pruned[key] = ranks
        else:
            removed.append(key)
    return pruned, removed


# ─── Detection (pure — unit-tested without the bot) ───────────────────────────

def _rankup_detect_changes(old_ranks, current_top5):
    """Compare stored ranks vs current top 5 (list of channel names, rank
    order = list order). Returns events in new-rank order:
    [{channel, new_rank, old_rank}] where old_rank None = fresh entry.
    Only improvements / entries. Drops, unchanged and leavers: no event."""
    old = {str(k).lower(): int(v) for k, v in dict(old_ranks or {}).items()}
    events = []
    seen = {}
    for i, ch in enumerate(list(current_top5 or [])[:RANKUP_TOP_N]):
        key = str(ch or "").lstrip("@").strip().lower()
        if not key or key in seen:
            continue
        seen[key] = str(ch).lstrip("@").strip()
        new_rank = i + 1
        old_rank = old.get(key)
        if old_rank is None:
            events.append({"channel": seen[key], "new_rank": new_rank,
                           "old_rank": None})
        elif new_rank < old_rank:
            events.append({"channel": seen[key], "new_rank": new_rank,
                           "old_rank": old_rank})
    return events


def _rankup_detect_new_champions(old_ranks, current_top10):
    """New champions at ranks 6-10 (outside the top 5). Returns events
    in new-rank order: [{channel, new_rank, old_rank: None}] for
    channels in the current top 10 at rank 6-10 that were NOT
    champions before (absent from the stored state entirely). Ranks
    1-5 are handled by _rankup_detect_changes, so they are skipped
    here; a channel already in state — even at a worse rank — is NOT
    a new champion, so a move like #8 -> #7 produces no event."""
    old = {str(k).lower(): int(v) for k, v in dict(old_ranks or {}).items()}
    events = []
    seen = {}
    for i, ch in enumerate(list(current_top10 or [])[:RANKUP_CHAMPIONS_N]):
        key = str(ch or "").lstrip("@").strip().lower()
        if not key or key in seen:
            continue
        seen[key] = str(ch).lstrip("@").strip()
        new_rank = i + 1
        if new_rank <= RANKUP_TOP_N:
            continue  # top 5: _rankup_detect_changes owns it
        if key in old:
            continue  # already a champion — no new-entry post
        events.append({"channel": seen[key], "new_rank": new_rank,
                       "old_rank": None})
    return events


def _rankup_next_state(old_ranks, current_top10, ok_events):
    """State to store after a job run. Channels still in the top 10 keep
    their new rank — EXCEPT events whose post FAILED: those keep their OLD
    rank (or stay absent), so the next run retries them. Leavers are
    removed. ok_events = the events from _rankup_detect_changes +
    _rankup_detect_new_champions that actually posted. current_top10
    is the full champion list in rank order (1-10); passing a top-5
    list behaves exactly like the old top-5-only version."""
    old = {str(k).lower(): int(v) for k, v in dict(old_ranks or {}).items()}
    ok = {}
    for ev in (ok_events or []):
        ok[str(ev.get("channel", "")).lstrip("@").strip().lower()] = int(
            ev.get("new_rank"))
    top10 = list(current_top10 or [])[:RANKUP_CHAMPIONS_N]
    events = {str(ev.get("channel", "")).lstrip("@").strip().lower()
              for ev in (_rankup_detect_changes(old, top10[:RANKUP_TOP_N])
                         + _rankup_detect_new_champions(old, top10))}
    new_state = {}
    for i, ch in enumerate(top10):
        key = str(ch or "").lstrip("@").strip().lower()
        if not key or key in new_state:
            continue
        new_rank = i + 1
        if key in events and key not in ok:
            # Post failed (or was skipped): keep the old rank so the next
            # run retries this exact change. A fresh entrant stays absent.
            if key in old:
                new_state[key] = old[key]
        else:
            new_state[key] = new_rank
    return new_state


# ─── Current top 5 (same qualification + sort as post 134) ───────────────────

def _rankup_current_champions(limit):
    """Return [(channel, points, total_x)] for the current top `limit`
    champions, using the exact build_champions_text() rule: qualify
    pts >= 100 AND real 2x+ (champion_total_x >= 2, snapshot/exclusion
    aware), sort by (total champion X desc, points desc). Falls back
    to a points-only order (with a live 2x+ check) only if the
    leaderboard helpers are missing from the namespace — that fallback
    is logged, never silent."""
    ranking_fn = _g("_ranking_channels")
    load_pts = _g("load_channel_points")
    load_cfg = _g("load_config")
    total_fn = _g("champion_total_x")
    champ_pts = _g("POINTS_FOR_CHAMPION", 100)
    if callable(ranking_fn) and callable(load_pts) and callable(total_fn):
        try:
            pts_data = load_pts() or {}
            cfg = load_cfg() if callable(load_cfg) else {}
            excluded = set((cfg or {}).get("champion_excluded_call_keys", []))
            snap = (cfg or {}).get("champion_milestone_snapshot", {})
            out = []
            for ch in ranking_fn():
                pts = (pts_data.get(str(ch).lower(), {}) or {}).get("points", 0)
                try:
                    best_x, _ = total_fn(ch, snap, excluded)
                except Exception:
                    continue
                if pts >= champ_pts and (best_x or 0) >= 2:
                    out.append((str(ch), int(pts), best_x))
            # EXACT sort from build_champions_text(): (best_x, pts) desc.
            out.sort(key=lambda t: (t[2], t[1]), reverse=True)
            return out[:int(limit)]
        except Exception as e:
            _rankup_log.warning(f"🏆 Rank-up: champion list build failed: {e}")
    # Fallback (helpers missing): points desc + live 2x+ check via history.
    _rankup_log.warning("🏆 Rank-up: leaderboard helpers missing — "
                        "using points-only fallback order")
    get_pts = _g("get_channel_points")
    load_ch = _g("load_channels")
    chans = []
    if callable(load_ch):
        try:
            chans = list(load_ch() or [])
        except Exception:
            chans = []
    out = []
    for ch in chans:
        try:
            pts = int(get_pts(ch)) if callable(get_pts) else 0
        except Exception:
            pts = 0
        if pts < champ_pts:
            continue
        if not any(_rankup_call_peak(c) >= 2
                   for c in (_g("get_call_history")(ch) or [])):
            continue
        out.append((str(ch), pts, 0))
    out.sort(key=lambda t: t[1], reverse=True)
    return out[:int(limit)]


def _rankup_current_top5():
    """Top 5 champions — same qualification + sort as post 134.
    Kept for the rank-improvement logic and callers that only need
    the top 5; the job itself uses _rankup_current_top10()."""
    return _rankup_current_champions(RANKUP_TOP_N)


def _rankup_current_top10():
    """Top 10 champions — the full Champions list (post 134). Used
    by the job so a channel that newly qualifies at rank 6-10 is
    detected and posted as a new champion entry."""
    return _rankup_current_champions(RANKUP_CHAMPIONS_N)

# ─── Video build + send ──────────────────────────────────────────────────────

def _rankup_avatar_path(channel):
    """avatars/<channel-lower>.jpg when it exists, else None (same pattern
    as _champion_video_try_send in x_alert.py)."""
    dp = _g("_dp")
    if not callable(dp):
        return None
    try:
        cand = dp(os.path.join("avatars",
                               f"{str(channel).lstrip('@').lower()}.jpg"))
    except Exception:
        return None
    return cand if cand and os.path.exists(cand) else None


def _rankup_video_kwargs(channel, rank, points, alpha_calls, title,
                         avatar_path=None, out_path=None):
    """Exact kwargs for champion_rankup_video.build_rankup_video().
    calls = [{symbol, x}] — the renderer only needs symbol + X."""
    if out_path is None:
        out_dir = os.environ.get("CHAMP_VIDEO_DIR", "/tmp")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            out_dir = "/tmp"
        stamp = int(time.time() * 1000) % 100000
        out_path = os.path.join(
            out_dir,
            f"champ-rankup-{int(rank)}x-"
            f"{str(channel).lstrip('@').lower()}-{stamp}.mp4")
    calls = []
    for c in (alpha_calls or []):
        # STRICT 2x filter, same gate as the message list: re-normalize
        # here instead of trusting the caller, so a sub-2x row (1.9x /
        # 1.5x / 1.2x) can never reach the renderer even if it was
        # passed in unfiltered. _rankup_normalize_alpha_call returns
        # None below 2.0 peak X and the peak X otherwise.
        n = _rankup_normalize_alpha_call(c)
        if n is None:
            continue
        calls.append({"symbol": str(n.get("symbol", "TOKEN")),
                      "x": n.get("x")})
    return {
        "channel": str(channel).lstrip("@"),
        "rank": int(rank),
        "points": int(points),
        "calls": calls,
        "title": title,
        "avatar_path": avatar_path,
        "out_path": out_path,
        "crf": 12,
        "preset": "veryfast",
    }


async def _rankup_build_video(channel, rank, points, alpha_calls, title):
    """Build the per-post video via the parallel renderer module.
    Returns the file path, or None on any failure (caller: no post)."""
    try:
        import champion_rankup_video
        kw = _rankup_video_kwargs(
            channel, rank, points, alpha_calls, title,
            avatar_path=_rankup_avatar_path(channel))
        path = await asyncio.to_thread(
            champion_rankup_video.build_rankup_video, **kw)
    except Exception as e:
        _rankup_log.warning(
            f"🏆 Rank-up video build failed @{channel} rank #{rank}: "
            f"{type(e).__name__}: {e}")
        return None
    if not path or not os.path.exists(path):
        _rankup_log.warning(
            f"🏆 Rank-up video missing @{channel} rank #{rank}: {path}")
        return None
    return path


def _rankup_delete_video(path):
    """Delete a generated video from cache after posting (same idea as
    _delete_champion_video in x_alert.py)."""
    fn = _g("_delete_champion_video")
    if callable(fn):
        try:
            fn(path)
            return
        except Exception:
            pass
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as e:
        _rankup_log.warning(f"🏆 Rank-up video delete failed {path}: {e}")


def _rankup_owner_id(channel):
    """The KOL/channel owner's Telegram user ID, or None.
    Same lookup the X alerts use (x_alert.py _forward_alert_recipients):
    core.py load_kol_owners() -> data/kol_owners.json, keyed by
    channel.lower(), values set via /setkolowner. String IDs are cast
    to int (old JSON files stored some as strings); anything invalid
    or missing -> None (caller skips the DM silently, never crashes)."""
    try:
        load = _g("load_kol_owners")
        if not callable(load):
            return None
        owners = load() or {}
        raw = owners.get(str(channel or "").lstrip("@").strip().lower())
        if raw is None:
            return None
        return int(raw)
    except (TypeError, ValueError):
        return None
    except Exception as e:
        _rankup_log.warning(f"🏆 Rank-up owner lookup failed @{channel}: {e}")
        return None


async def _rankup_forward_to_owner(bot, channel, wizard_post_id):
    """Forward the just-posted @WizardScan rank-up post to the channel
    owner's DM. Same path as the X alerts: the published message is
    FORWARDED (bot.forward_message from TARGET_CHANNEL), never rebuilt
    or re-sent, so the DM carries the identical video + message with
    premium emojis intact. Returns True if the forward went out,
    False otherwise (no owner / no bot / forward failed). Never raises.
    Prefers the shared x_alert.py _forward_alert_post helper when the
    bot namespace has it (3 retries + bot-access fail-fast); falls back
    to one direct bot.forward_message call when it does not (e.g. in
    standalone tests)."""
    if not wizard_post_id:
        return False
    owner_id = _rankup_owner_id(channel)
    if not owner_id:
        _rankup_log.info(
            f"🏆 Rank-up: no owner mapped for @{channel} "
            "(kol_owners.json) — owner DM skipped, channel post stands")
        return False
    if bot is None:
        _rankup_log.warning(
            f"🏆 Rank-up: no bot to forward post {wizard_post_id} "
            f"to owner {owner_id} @{channel}")
        return False
    label = f"(KOL owner @{str(channel).lstrip('@').lower()} rank-up)"
    try:
        forward_fn = _g("_forward_alert_post")
        if callable(forward_fn):
            ok = await forward_fn(bot, owner_id, wizard_post_id, label=label)
            if ok:
                _rankup_log.info(
                    f"🏆 Rank-up post {wizard_post_id} forwarded to owner "
                    f"{owner_id} @{channel}")
            else:
                _rankup_log.warning(
                    f"🏆 Rank-up owner DM failed @{channel} "
                    f"(owner {owner_id}, post {wizard_post_id}) — "
                    "channel post stands, rank already stored")
            return bool(ok)
        target = _g("TARGET_CHANNEL") or "@WizardScan"
        await bot.forward_message(chat_id=owner_id,
                                  from_chat_id=target,
                                  message_id=int(wizard_post_id))
        _rankup_log.info(
            f"🏆 Rank-up post {wizard_post_id} forwarded to owner "
            f"{owner_id} @{channel}")
        return True
    except Exception as e:
        _rankup_log.warning(
            f"🏆 Rank-up owner DM failed @{channel} (owner {owner_id}, "
            f"post {wizard_post_id}): {type(e).__name__}: {e} — "
            "channel post stands, rank already stored")
        return False


async def _rankup_forward_linked(bot, channel, wizard_post_id):
    """Forward the rank-up post to the KOL's linked channels and its own
    channel - same distribution as the X alerts, because a rank-up is an
    important post. (RANKUP_FORWARD_NOV17)
    - Linked channels: BOTH /linkme (full) and /linksmart (smart) targets
      get the post. The smart X-milestone filter does NOT apply here: a
      rank-up is not an X alert, so there is no X value to filter on.
    - Own channel: auto-forward via _auto_forward_to_own_channel when
      the bot is admin there. Skipped only when a linked target IS the
      own channel (the link loop already sent it there - no duplicate).
    - The owner DM is NOT done here (_rankup_forward_to_owner does it).
    Best-effort, never raises, never fails the rank-up."""
    if not wizard_post_id:
        return
    ch_key = str(channel or "").lstrip("@").strip().lower()
    if not ch_key:
        return
    target = _g("TARGET_CHANNEL") or "@WizardScan"
    forward_fn = _g("_forward_alert_post")
    try:
        load_linked = _g("load_linked_channels")
        linked = dict(load_linked()) if callable(load_linked) else {}
    except Exception:
        linked = {}
    own_linked = False
    for kol_ch, link_val in (linked or {}).items():
        if str(kol_ch).lstrip("@").lower() != ch_key:
            continue
        if isinstance(link_val, dict):
            tgt = link_val.get("target")
        else:
            tgt = link_val
        if not tgt:
            continue
        if str(tgt).lstrip("@").strip().lower() == ch_key:
            own_linked = True
        label = f"(KOL @{ch_key} rank-up)"
        try:
            if callable(forward_fn):
                ok = await forward_fn(bot, tgt, wizard_post_id, label=label)
            else:
                await bot.forward_message(
                    chat_id=tgt, from_chat_id=target,
                    message_id=int(wizard_post_id))
                ok = True
            if ok:
                _rankup_log.info(
                    f"🏆 Rank-up post {wizard_post_id} forwarded to "
                    f"linked {tgt} @{channel}")
        except Exception as e:
            _rankup_log.warning(
                f"🏆 Rank-up linked forward failed @{channel} -> {tgt}: "
                f"{type(e).__name__}: {e}")
    try:
        auto_fn = _g("_auto_forward_to_own_channel")
        if callable(auto_fn):
            await auto_fn(bot, ch_key, wizard_post_id,
                          already_linked={ch_key} if own_linked else set())
    except Exception as e:
        _rankup_log.warning(
            f"🏆 Rank-up own-channel forward failed @{channel}: "
            f"{type(e).__name__}: {e}")


async def _rankup_send_video_post(bot, channel, rank, msg, video_path,
                                  target=None):
    """Send the rank-up video post. Userbot first (premium emojis, no edit
    pencil — _champion_video_try_send pattern), Bot API fallback.
    Returns the published message ID on success, None on failure.
    Never raises. No text-only fallback: a failed send returns None and
    the rank change is retried on the next job run (see _rankup_next_state).
    target: chat to send to; None means the @WizardScan channel
    (TARGET_CHANNEL). The /testrankup preview passes the owner's DM chat
    id so the preview never touches the channel.
    NOTE: this function does NOT delete the video. The caller
    (_rankup_post_rankup) deletes it only after BOTH sends have been
    attempted — the channel post here AND the owner-DM forward there —
    so the cached file is never removed while a send still needs it."""
    if target is None:
        target = _g("TARGET_CHANNEL") or "@WizardScan"
    plain = msg["plain"]
    html_text = msg["html"]
    emoji_ids = list(msg["emoji_ids"])

    # Caption limit is on the PARSED text (Telegram counts visible chars).
    if len(plain) > 1024:
        _rankup_log.warning(
            f"🏆 Rank-up caption too long @{channel} rank #{rank} "
            f"({len(plain)} chars) — skipping, will retry next run")
        return None

    # 1) Userbot: video + premium emojis in one send (no edit pencil).
    clients_fn = _g("_userbot_clients")
    try:
        clients = list(clients_fn()) if callable(clients_fn) else []
    except Exception:
        clients = []
    if clients:
        try:
            from telethon.extensions.html import parse as tl_html_parse
            prepare = _g("prepare_owner_emojis")
            txt, explicit = ("", {})
            if callable(prepare):
                try:
                    txt, explicit = prepare(plain)
                except Exception:
                    txt, explicit = plain, {}
            else:
                txt = plain
            parsed_text, base_ents = tl_html_parse(txt)
            if len(parsed_text) <= 1024:
                # RANKUP_EMOJI_FIX_NOV17: positional-only entities (see
                # _rankup_build_entities) - the shared builder's teer lock
                # mis-fires on rank-up rows and shifts later emojis.
                all_ents = _rankup_build_entities(parsed_text, base_ents,
                                                  emoji_ids)
                pick = _g("_pick_userbot")
                first = pick() if callable(pick) else (clients[0] if clients else None)
                ordered = ([first] if first else []) + [
                    c for c in clients if c is not first]
                timeout = float(_g("USERBOT_MEDIA_TIMEOUT_SECONDS", 30) or 30)
                sent = None
                for ub in ordered:
                    try:
                        sent = await asyncio.wait_for(
                            ub.send_file(
                                target, video_path, caption=parsed_text,
                                formatting_entities=all_ents,
                                supports_streaming=True, force_document=False),
                            timeout=timeout)
                        break
                    except Exception as se:
                        _rankup_log.warning(
                            "🏆 Rank-up userbot send failed on one client: "
                            f"{se}")
                        continue
                if sent is not None:
                    post_id = getattr(sent, "id", None)
                    _rankup_log.info(
                        f"🏆 Rank-up video sent by userbot: @{channel} "
                        f"rank #{rank} msg_id={post_id}")
                    return post_id
        except Exception as e:
            _rankup_log.warning(
                f"🏆 Rank-up userbot send failed @{channel}: "
                f"{type(e).__name__}: {e} — trying Bot API")

    # 2) Bot API fallback (plain HTML caption with <tg-emoji> tags).
    forbidden = _g("_BOT_CHANNEL_FORBIDDEN") or {}
    try:
        is_forbidden = bool(forbidden.get("v")) if isinstance(forbidden, dict) else False
    except Exception:
        is_forbidden = False
    if not is_forbidden and bot is not None:
        for caption, label in ((html_text, "emoji"),
                               (_rankup_strip_tg_emoji(html_text), "plain")):
            try:
                with open(video_path, "rb") as fh:
                    m = await bot.send_video(
                        target, video=fh, caption=caption, parse_mode="HTML",
                        supports_streaming=True)
                post_id = getattr(m, "message_id", None)
                _rankup_log.info(
                    f"🏆 Rank-up video sent by bot ({label}): @{channel} "
                    f"rank #{rank} msg_id={post_id}")
                return post_id
            except Exception as e:
                if "not a member" in str(e).lower() or "forbidden" in str(e).lower():
                    try:
                        forbidden["v"] = True
                    except Exception:
                        pass
                _rankup_log.warning(
                    f"🏆 Rank-up bot send ({label}) failed @{channel}: {e}")
                if label == "plain":
                    break
                continue
    # All sends failed — report failure (caller deletes the generated
    # video; it is re-built on retry) so the stored rank is NOT updated.
    return None


async def _rankup_post_rankup(bot, channel, new_rank, old_rank):
    """One rank-change post: points -> alpha calls -> message -> video ->
    channel post -> owner-DM + linked/own-channel forwards. Returns True
    only if the @WizardScan channel post went out. Never raises.
    Failure rule (deliberate, see DEPLOY.md):
    - Channel post fails -> False, stored rank NOT updated, next run
      retries the same change (existing behaviour, unchanged).
    - Channel post succeeds but the owner DM fails (or no owner is
      mapped) -> still True. The rank IS stored as new and the channel
      post is NOT re-sent: re-posting would duplicate the public post
      for a private-DM problem. The DM failure is only logged.
    - The video is deleted from cache only after BOTH sends have been
      attempted (channel post + owner DM), in the finally below — the
      forward itself needs no file (it forwards the published message),
      but the ordering guarantees no send ever runs after cleanup."""
    video_path = None
    try:
        get_pts = _g("get_channel_points")
        points = int(get_pts(channel)) if callable(get_pts) else 0
        alpha = _rankup_alpha_calls(channel)
        msg = build_rankup_message(channel, new_rank, points,
                                   alpha_calls=alpha, old_rank=old_rank)
        video_path = await _rankup_build_video(
            channel, new_rank, points, alpha, msg["title"])
        if not video_path:
            return False
        post_id = await _rankup_send_video_post(
            bot, channel, new_rank, msg, video_path)
        if not post_id:
            return False
        # Channel post is out. Owner DM is best-effort: it must never
        # fail the rank-up or re-trigger the channel post. Unlike the X
        # alerts (which fire the forward via asyncio.create_task after
        # the post), this is awaited inline so the video cleanup below
        # provably happens after both sends were attempted.
        try:
            await _rankup_forward_to_owner(bot, channel, post_id)
        except Exception as e:  # defensive: _rankup_forward_to_owner never raises
            _rankup_log.warning(
                f"🏆 Rank-up owner DM failed @{channel} -> #{new_rank}: "
                f"{type(e).__name__}: {e} — channel post stands")
        # Rank-up is an important post: also forward to the KOL's linked
        # channels (/linkme + /linksmart) and its own channel.
        # Best-effort like the owner DM - a forward failure never fails
        # the rank-up or re-triggers the channel post.
        try:
            await _rankup_forward_linked(bot, channel, post_id)
        except Exception as e:  # defensive: _rankup_forward_linked never raises
            _rankup_log.warning(
                f"🏆 Rank-up linked forward failed @{channel} -> "
                f"#{new_rank}: {type(e).__name__}: {e} — channel post stands")
        return True
    except Exception as e:
        _rankup_log.warning(
            f"🏆 Rank-up post failed @{channel} -> #{new_rank}: "
            f"{type(e).__name__}: {e}")
        return False
    finally:
        if video_path:
            _rankup_delete_video(video_path)


# ─── Job (registered in runtime.py main(), see DEPLOY.md) ────────────────────

async def champion_rankup_job(context):
    """Every 20s: compare current top 10 champions vs stored ranks,
    post top-5 improvements / entries AND new-champion entries at
    ranks 6-10, update state. Never raises into the scheduler.
    FIRST RUN (no state file): record the current champions WITHOUT
    posting. A champion moving between ranks 6-10 (e.g. #8 -> #7)
    does NOT post — the move is only logged, so the journal shows
    why no post fired for a channel that sits outside the top 5."""
    try:
        bot = getattr(context, "bot", None)
        current = _rankup_current_top10()
        top5 = current[:RANKUP_TOP_N]
        names = [c for c, _, _ in top5]
        names10 = [c for c, _, _ in current]
        old, existed = _rankup_load_ranks()
        if not existed:
            _rankup_save_ranks(
                {c.lower(): i + 1 for i, (c, _, _) in enumerate(current)})
            _rankup_log.info(
                "🏆 Rank-up first run: recorded current champions, "
                f"no posts ({[c for c, _, _ in current]})")
            return
        events = _rankup_detect_changes(old, names)
        events += _rankup_detect_new_champions(old, names10)
        # RANKUP_DEDUP_NOV20: per-stint dedup for top-5 ranks. Rank 1
        # always posts; ranks 2-5 post once per stint; ranks 6-10
        # new-champion entries are never filtered. Leavers reset.
        alerted = _rankup_load_alerted()
        alerted, _removed = _rankup_prune_alerted(alerted, names10)
        for _key in _removed:
            _rankup_log.info(
                f"Rank-up: @{_key} left Champions, alerted record reset")
        events, skipped = _rankup_filter_events(events, alerted)
        for _ev in skipped:
            _rankup_log.info(
                f"Rank-up: @{_ev['channel']} -> #{_ev['new_rank']} already "
                "alerted this stint, skipping")
        # Diagnostic: a champion sitting outside the top 5 whose rank
        # moved (or dropped out of the top 5) gets no post — log it so
        # the journal shows why. New champions at 6-10 DO post (the
        # event above), so they are not logged here; unchanged ranks
        # are not logged either (would spam every 20s).
        for i, (c, _, _) in enumerate(current):
            rank = i + 1
            if rank <= RANKUP_TOP_N:
                continue
            key = str(c).lstrip("@").strip().lower()
            old_rank = old.get(key)
            if old_rank is not None and old_rank != rank:
                _rankup_log.info(
                    f"🏆 Rank-up: @{c} is a champion at rank #{rank} "
                    "(outside top 5) — no post")
        if not events:
            # Still persist: ranks may have worsened / leavers dropped.
            # Skipped events count as done for state (no re-detect spam).
            _rankup_save_ranks(_rankup_next_state(old, names10, skipped))
            _rankup_save_alerted(alerted)
            return
        ok_events = []
        for ev in events:
            try:
                ok = await _rankup_post_rankup(
                    bot, ev["channel"], ev["new_rank"], ev["old_rank"])
            except Exception as e:
                _rankup_log.warning(
                    f"🏆 Rank-up trigger failed @{ev['channel']}: {e}")
                ok = False
            if ok:
                ok_events.append(ev)
            else:
                _rankup_log.warning(
                    f"🏆 Rank-up: post failed @{ev['channel']} -> "
                    f"#{ev['new_rank']}, rank NOT updated — retry next run")
        # Skipped events count as done for state (no re-detect spam);
        # only actually-posted ranks 2-5 are marked as alerted.
        _rankup_save_ranks(_rankup_next_state(old, names10,
                                              ok_events + skipped))
        alerted = _rankup_mark_alerted(alerted, ok_events)
        _rankup_save_alerted(alerted)
    except Exception as e:
        _rankup_log.error(f"🏆 Rank-up job error (continuing): {e}")


# ─── Deep-link handler (called from commands.py cmd_start, see DEPLOY.md) ───

def rankup_parse_rec_payload(arg):
    """'rec_<channel>' -> channel (lowercased, no @) or None."""
    if not arg or not str(arg).startswith("rec_"):
        return None
    ch = str(arg)[len("rec_"):].strip().lstrip("@").lower()
    return ch or None


async def rankup_handle_start_rec(update, context, channel):
    """Same record as typing @channel in the bot DM (handle_lookup path).
    Called from cmd_start when the /start payload is rec_<channel>."""
    msg = update.message
    ch = str(channel or "").lstrip("@").strip().lower()
    if not ch:
        await msg.reply_text("⚠️ This record link is not valid.")
        return
    load_ch = _g("load_channels")
    tracked = []
    if callable(load_ch):
        try:
            tracked = [str(c).lower() for c in (load_ch() or [])]
        except Exception:
            tracked = []
    if tracked and ch not in tracked:
        await msg.reply_text(
            f"<b>🔮 @{html.escape(_rankup_display(ch))}</b>\n\n"
            "❌ This channel is not tracked by Wizard Scan.\n\n"
            "To request tracking, contact our team for priority review.",
            parse_mode="HTML")
        return
    overview = _g("_send_channel_overview")
    if callable(overview):
        try:
            await overview(msg, ch)
            return
        except Exception as e:
            _rankup_log.warning(f"🏆 Rank-up rec_ overview failed @{ch}: {e}")
    await msg.reply_text(
        f"⚠️ Could not display the record for @{html.escape(_rankup_display(ch))}. "
        "Please try again in a moment.")


# ─── Owner preview command: /testrankup [@channel] [rank] ────────────────────
# Safe by design: preview goes to the OWNER's DM only, never to the channel,
# and it never touches champion_ranks.json.

async def cmd_testrankup(update, context):
    """Owner-only preview: build the rank-up message + video for a channel
    and send it to this chat (the owner's DM). No state change, no channel
    post. Usage: /testrankup @channel [rank]  (rank defaults to the
    channel's current rank, or 5)."""
    owner_ids = _g("OWNER_IDS") or []
    try:
        uid = update.effective_user.id if update.effective_user else None
    except Exception:
        uid = None
    if owner_ids and uid not in owner_ids:
        return
    args = list(getattr(context, "args", None) or [])
    if not args:
        await update.message.reply_text(
            "Usage: /testrankup @channel [rank]\n"
            "Example: /testrankup @flokiarmywhale 1\n"
            "Preview is sent here (owner DM only) — nothing is posted to "
            "the channel and no rank state is changed.")
        return
    channel = str(args[0]).lstrip("@").strip()
    try:
        rank = int(args[1]) if len(args) > 1 else RANKUP_TOP_N
    except (TypeError, ValueError):
        rank = RANKUP_TOP_N
    rank = min(max(rank, 1), RANKUP_TOP_N)
    try:
        get_pts = _g("get_channel_points")
        points = int(get_pts(channel)) if callable(get_pts) else 0
        alpha = _rankup_alpha_calls(channel)
        msg = build_rankup_message(channel, rank, points,
                                   alpha_calls=alpha, old_rank=None)
        await update.message.reply_text(
            f"⏳ Building rank #{rank} preview for @{_rankup_display(channel)}…")
        video_path = await _rankup_build_video(
            channel, rank, points, alpha, msg["title"])
        if not video_path:
            await update.message.reply_text(
                "⚠️ Video build failed (renderer missing/failed). "
                "Text preview:\n\n" + msg["html"], parse_mode="HTML",
                disable_web_page_preview=True)
            return
        # Preview via the SAME send path as live posts: userbot first
        # (premium emojis, parsed text), Bot API fallback. The old code
        # sent msg["html"] (1383 raw chars, user-pack <tg-emoji> tags)
        # straight through context.bot.send_video, which always failed
        # on the 1024-char caption limit / unusable emoji ids. target is
        # this DM only — never @WizardScan — and no rank state is touched.
        try:
            try:
                post_id = await _rankup_send_video_post(
                    context.bot, channel, rank, msg, video_path,
                    target=update.effective_chat.id)
            except Exception as e:
                _rankup_log.warning(f"🏆 /testrankup send failed: {e}")
                post_id = None
            if post_id is not None:
                await update.message.reply_text(
                    f"✅ Preview sent for rank #{rank} (owner DM only, "
                    "no channel post, no state change).")
            else:
                # Video send failed entirely: text fallback, RENDERED.
                # msg["plain"] keeps <b>/<a> tags with literal fallback
                # emoji chars (no <tg-emoji> tags), so it renders correctly
                # under parse_mode="HTML". Never send HTML-tagged text
                # without parse_mode — that is what showed literal tags.
                _rankup_log.warning(
                    "🏆 /testrankup video send failed — text fallback")
                await update.message.reply_text(
                    msg["plain"], parse_mode="HTML",
                    disable_web_page_preview=True)
        finally:
            _rankup_delete_video(video_path)
    except Exception as e:
        _rankup_log.warning(f"🏆 /testrankup failed: {e}")
        await update.message.reply_text(
            "⚠️ Preview failed — check the logs and try again.")
# RANKUP_COPY_NOV17
