#!/usr/bin/env python3
"""
LEAD KOL badge patch for X alerts.

Run inside /opt/bot:   python3 patch_lead_badge.py
- backs up x_alert.py and core.py (…bak_leadbadge)
- moves "🔮 LEAD KOL - Rank # 🔮" to the END of the X alert (2 blank lines after the links)
- leading 🔮 = same tier-coloured crystal ball as the entry MC (🔮 151.3K)
- rank 🔮 = number emoji picked by the alert's x range (2-10, 11-20, 21-30, 31-50, 51-75, 76-99)
- 100x and above keep the old rank emoji
Restores the backups automatically if anything fails to compile.
"""
import os, shutil, py_compile, sys

HERE = os.getcwd()
XA = os.path.join(HERE, "x_alert.py")
CO = os.path.join(HERE, "core.py")
for p in (XA, CO):
    if not os.path.exists(p):
        sys.exit(f"missing {p} - run this from /opt/bot")

xa = open(XA, encoding="utf-8").read()
co = open(CO, encoding="utf-8").read()

if "_lead_rank_emoji_for_x" in xa:
    sys.exit("already patched - nothing to do")

def swap(src, old, new, label):
    n = src.count(old)
    if n != 1:
        sys.exit(f"PATCH STOPPED ({label}): expected 1 match, found {n}. Nothing was changed.")
    return src.replace(old, new, 1)

# ── 1) x_alert.py: LEAD KOL line goes to the end (x_style only) ─────────────
xa = swap(xa,
'''        if badge["type"] == "leaderboard":
            badge_html = f' <b><a href="https://t.me/WizardScan/136">LEAD KOL</a></b> - Rank # 🔮'
''',
'''        if badge["type"] == "leaderboard":
            if x_style:
                # LEAD KOL ab post ke END me alag line par (links ke neeche 2 khali lines)
                _champ_badge_line = f'🔮 <b><a href="https://t.me/WizardScan/136">LEAD KOL</a></b> - Rank # 🔮'
            else:
                badge_html = f' <b><a href="https://t.me/WizardScan/136">LEAD KOL</a></b> - Rank # 🔮'
''', "build_alert leaderboard badge")

xa = swap(xa,
'''        if _champ_badge_line and "CHAMP KOL" not in text:''',
'''        if _champ_badge_line and "CHAMP KOL" not in text and "LEAD KOL" not in text:''',
"end-badge guard")

# ── 2) x_alert.py: tier rank-number emojis + helper (placed before _get_alert_emoji_ids) ──
helper = '''# ── LEAD KOL rank-number premium emojis, tier by the alert's x value ─────────
# Each list is rank 1..10 in order. 100x+ keeps the old LEADERBOARD_PREMIUM_EMOJIS.
LEAD_RANK_TIER_EMOJIS = [
    (2, 10, [6003466361060204218, 6003544855882507005, 6003802382121576201, 6003372958406419088, 6003539444223714524,
             6001139639837007865, 6003814021482946755, 6003640152616869707, 6003461881409314873, 6003415865129706096]),
    (11, 20, [6003712935132668091, 6003823483295902552, 6003319602027700134, 6003709550698437970, 6005864413100253272,
              6003678480905018574, 6003633508302462775, 6003556319150219127, 6003556263315644328, 6003351685433400404]),
    (21, 30, [6003703962945986556, 6003620271213256999, 6003849974654181680, 6003837815601765906, 6005836732036030447,
              6003710379627128033, 6003421603206012387, 6003515285032673025, 6003470870775868095, 6003813256978768360]),
    (31, 50, [6003660871539106191, 6003383322162503610, 6003732004787462339, 6003564831775399193, 6003469878638419892,
              6003483755677752686, 6003504032218358258, 6005661969816755771, 6003479529429935720, 6003568083065643002]),
    (51, 75, [6003682500994408226, 6003375406537779003, 6003787044793359987, 6005716356987624820, 6003303139418054451,
              6003598006102793987, 6003753226220871999, 6003701089612866659, 6003459875659587126, 6003543004751601164]),
    (76, 99, [6003739568224872602, 6003573456069729832, 6006078358306169726, 6003664797139213731, 6003343443391159673,
              6003470853595996353, 6003303998411513679, 6003507150364614091, 6005815519192554646, 6003631820380315667]),
]

def _lead_rank_emoji_for_x(x_val, rank):
    """Rank-number premium emoji for the LEAD KOL badge, chosen by x tier."""
    try:
        xv = int(x_val)
        r = int(rank)
    except Exception:
        xv, r = 0, 1
    for lo, hi, ids in LEAD_RANK_TIER_EMOJIS:
        if lo <= xv <= hi and 1 <= r <= len(ids):
            return ids[r - 1]
    return LEADERBOARD_PREMIUM_EMOJIS.get(r, LEADERBOARD_PREMIUM_EMOJIS[1])

'''
xa = swap(xa, "def _get_alert_emoji_ids(x_val, chain, pack=None):",
          helper + "def _get_alert_emoji_ids(x_val, chain, pack=None):", "helper insert")

# ── 3) x_alert.py: send path now appends [crystal, rank] for leaderboard ───────
xa = swap(xa,
'''            rank_emoji_id = LEADERBOARD_PREMIUM_EMOJIS.get(badge["rank"], LEADERBOARD_PREMIUM_EMOJIS[1])
            emoji_id += [rank_emoji_id]
''',
'''            rank_emoji_id = _lead_rank_emoji_for_x(x_val, badge["rank"])
            emoji_id += [_pack_crystal(pack), rank_emoji_id]
''', "send path emoji ids")

# ── 4) core.py: LEAD KOL line (new format) reserves 2 badge emojis ───────────
co = swap(co,
'''    badge_count = (2 if _badge_type == 'champion' else 1) if _badge_type else 0
''',
'''    # New X-alert format: "🔮 LEAD KOL - Rank # 🔮" on its own line -> 2 badge emojis
    # (leading crystal + rank number), same as the champion badge.
    _lead_new = bool(re.search(r'(?m)^🔮 LEAD KOL - Rank #', plain_text))
    badge_count = (2 if (_badge_type == 'champion' or _lead_new) else 1) if _badge_type else 0
''', "core badge_count")

co = swap(co,
'''            elif badge_ids and plain_text[:i].endswith('Rank # '):''',
'''            elif (_lead_new and len(badge_ids) >= 2
                  and rest.lstrip(' ').startswith('LEAD KOL')):
                # "🔮 LEAD KOL - Rank # 🔮" -> leading crystal ball
                eid = badge_ids[0]

            elif badge_ids and plain_text[:i].endswith('Rank # '):''',
"core leading crystal")

# ── write (with backups) and compile-check ────────────────────────────────────
shutil.copy2(XA, XA + ".bak_leadbadge")
shutil.copy2(CO, CO + ".bak_leadbadge")
open(XA, "w", encoding="utf-8").write(xa)
open(CO, "w", encoding="utf-8").write(co)
try:
    py_compile.compile(XA, doraise=True)
    py_compile.compile(CO, doraise=True)
except Exception as e:
    shutil.copy2(XA + ".bak_leadbadge", XA)
    shutil.copy2(CO + ".bak_leadbadge", CO)
    sys.exit(f"compile failed, backups restored: {e}")
print("PATCHED OK. Now: systemctl restart bot.service")
print("Undo any time: cp x_alert.py.bak_leadbadge x_alert.py && cp core.py.bak_leadbadge core.py && systemctl restart bot.service")
