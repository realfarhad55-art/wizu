# Forwards ON again - apply_forward_on_nov25.py (FORWARD_ON_NOV25)

## Kya hai yeh

Ek chhota patch jo X-alert forwards wapas ON karta hai. User ne Nov 25
~02:17 PKT order diya ("forword wala option on krna ha").

## Background

- Nov 23 ~21:44 PKT user ne forwards OFF karne ko kaha tha ("phly forword
  wala roko"). STOP_FORWARD2_NOV23 patch ne `_forward_alert_recipients`
  (x_alert.py) ke top par ek early `return` laga diya tha, jis se na DM
  alerts gaye na channel forwards.
- Ye patch sirf wohi ek `return` line hatata hai. Recipients kaun hain,
  dip forwarding (alag function), aur baaki sab kuch untouched rehta hai.

## Kya change hota hai (sirf 1 line, x_alert.py)

Pehle (OFF):
```python
async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    return  # STOP_FORWARD_NOV23: DM alerts + channel forwards paused by owner
```

Baad me (ON):
```python
async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):
    # FORWARD_ON_NOV25: DM alerts + channel forwards re-enabled by owner
```

## Deploy

1. Patch ko wizu repo (`realfarhad55-art/wizu`) me upload karo.
2. VPS par ek line me chalao:

```
cd /opt/bot && wget -O apply_forward_on_nov25.py "https://raw.githubusercontent.com/realfarhad55-art/wizu/main/apply_forward_on_nov25.py" && python3 apply_forward_on_nov25.py /opt/bot && systemctl restart bot.service
```

3. Output me "E1 OK (forward ON again, STOP_FORWARD return removed)" aana
   chahiye. Backup banta hai: `x_alert.py.bak_forward_on_nov25`.

## Verify

- Agle X alert ke baad: linked channels / KOL owner ko forward jana chahiye
  (pehle jaisa). Logs me check karo:

```
journalctl -u bot.service --since "10 minutes ago" --no-pager | grep -a "_forward_alert_recipients\|forward" | cut -c1-200 | tail -10
```

- Forward na aaye to pehle check karo ke patch apply hua: `grep FORWARD_ON_NOV25 /opt/bot/x_alert.py` (1 hit hona chahiye) aur `grep STOP_FORWARD_NOV23 /opt/bot/x_alert.py` (0 hits).

## Agar anchor fail ho

Patch fail-safe hai: agar live file ka text base copy se alag hua to patch
kuch bhi write nahi karta, sirf "FAIL: anchor not unique/found" print karta
hai. Aisa ho to output bhej do, force mat karo. (Live file me Nov 23 ke
baad ke patches hain: FINAL, PERM, DIPFIX, GUARD, DIP_BOLD, DROPBOT_MODE,
MONBOT_MODE, USERBOT2_OFF. Anchor `_forward_alert_recipients` ke def par
hai, jo un patches se nahi badla, is liye fail hone ka chance kam hai.)

## Rollback (forwards phir OFF karne hon to)

- Dobara stop-forward patch chalao (`apply_stop_forward2_nov23.py`, wizu
  repo me hai), phir `systemctl restart bot.service`. Ya: `.env` ya code
  me kuch aur badalne ki zaroorat nahi, sirf wohi patch wapas lagana hai.
- Is patch ka backup (`x_alert.py.bak_forward_on_nov25`) restore mat karo,
  wo sirf emergency ke liye hai.

## Test results (base copy x_alert-3aa26821.py par, Nov 25)

- Apply: E1 OK, exit 0. File compiles (COMPILE_OK).
- FORWARD_ON_NOV25 count 1, STOP_FORWARD_NOV23 count 0.
- Function body intact (try block, owner_id, linked channels, destinations).
- Dobara run: idempotent skip ("already has FORWARD_ON_NOV25").
- Backup byte-identical to base copy (319,678 B).
- Patch me koi em-dash nahi; patched file me em-dash count base jaisa (230).
