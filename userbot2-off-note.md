# Userbot 2 OFF - solid fix for the dropbot disconnects

## Problem (why restarts keep breaking it)

The main bot and the dropbot share the SAME @Wizard_Scan userbot session
(main bot: `/opt/bot/data/userbot_session2.txt`, dropbot: a copy of the
same file at `/opt/dropbot/wizard_scan.session`). Telegram allows only ONE
active connection per session. So every time the main bot (re)connects
userbot 2, it kicks the dropbot off, and vice versa. That is why:
- dropbot userbot disconnected 18:22 CET Nov 24, posts 157/158 missed
- main-bot userbot disconnected 19:18 CET Nov 24, dip posts 122681 and
  122695 went out non-premium (Bot API fallback, no premium emojis)
- dropbot silent again after the main bot restarted 21:35 CET Nov 24
  for MONBOT_MODE, posts 160/161 missed
- restarting the dropbot fixes it for a while, then the next main-bot
  restart breaks it again

Restarting is NOT a fix. This patch is.

## What the patch changes

File: `apply_userbot2_off_nov25.py` (7,821 B, marker `USERBOT2_OFF_NOV25`).
It adds an env flag `DISABLE_USERBOT2=1`. When the flag is set, the main
bot never connects @Wizard_Scan at all, so the dropbot owns that session
exclusively and the two bots stop disconnecting each other.

Three edits, two files:
- E1 `core.py`, `init_userbot()`: skips the 2nd-userbot block when the
  flag is set. This block is the tail of the function, so returning there
  only skips the 2nd account; the primary @yowziuh init above is untouched.
  This also covers the watchdog and `_kick_userbot_reconnect` paths, which
  both re-enter through `init_userbot()`.
- E2 `core.py`, `_start_second_userbot()`: early return when the flag is
  set. No connect, no NewMessage handler, no channel-join loop.
- E3 `runtime.py`: does not even spawn the `_start_second_userbot` task
  when the flag is set (belt and braces; E2 alone would already return).

What it does NOT do:
- It does NOT delete `userbot_session2.txt` and does NOT remove the
  userbot-2 code. Fully reversible.
- It does NOT touch the dropbot or the monbot.
- It does NOT change posting: `_userbot_clients()` only returns clients
  that are not None and connected, `_pick_userbot()` round-robins over
  that list, and the fetch fallback checks `userbot_client2 is not None`
  first. @yowziuh alone handled all posting before userbot 2 was added
  on Nov 5, and DROPBOT_MODE=1 is live, so the main bot no longer needs
  a 2nd account for realtime monitoring.

## Deploy (one step at a time, single 1-click command per step)

Step 1 - upload to the wizu repo (GitHub `realfarhad55-art/wizu`):
`apply_userbot2_off_nov25.py`

Step 2 - run the patch on the main bot (one line):
```
cd /opt/bot && wget -O apply_userbot2_off_nov25.py "https://raw.githubusercontent.com/realfarhad55-art/wizu/main/apply_userbot2_off_nov25.py" && python3 apply_userbot2_off_nov25.py /opt/bot
```
Expected output: `E1 OK`, `E2 OK`, `E3 OK`, `DONE. Backups:
core.py.bak_userbot2off_nov25, runtime.py.bak_userbot2off_nov25`.
If any anchor FAILS, do NOT force it. Send the output back instead.

Step 3 - set the flag + restart the main bot (one line):
```
echo DISABLE_USERBOT2=1 >> /opt/bot/.env && systemctl restart bot.service
```

Step 4 - restart the dropbot once, so it takes the @Wizard_Scan session
cleanly with no competitor (one line):
```
systemctl restart dropbot.service && sleep 10 && journalctl -u dropbot.service --since "1 minute ago" --no-pager | grep -a -iE "Userbot connected" | cut -c1-180 | tail -3
```
Expected: `Userbot connected: @Wizard_Scan (id=2134051116)`.

## Verify (the solid proof)

1. Main bot logs show ONLY @yowziuh, never @Wizard_Scan:
```
journalctl -u bot.service --since "5 minutes ago" --no-pager | grep -a -iE "Userbot2|2nd userbot" | cut -c1-180 | tail -5
```
Expected: `Userbot2 OFF (DISABLE_USERBOT2=1) - @Wizard_Scan left to dropbot.`
(and/or `2nd userbot OFF (DISABLE_USERBOT2=1) - @Wizard_Scan left to dropbot.`).
And NO `Userbot2: @Wizard_Scan` / `2nd userbot connected` line.

2. Dropbot STAYS connected across a main-bot restart. After any later
`systemctl restart bot.service`, check:
```
journalctl -u dropbot.service --since "10 minutes ago" --no-pager | grep -a -iE "Disconnecting from|Dropped call posted" | cut -c1-180 | tail -5
```
Expected: dropped calls keep posting, NO `Disconnecting from` line.
Then post a test CA on @wizardscantest and confirm the dropped call
arrives in ~1s.

3. Main-bot posting still works: the next X alert / dip alert should
post with premium emojis via @yowziuh as before.

## Rollback (if anything goes wrong)

Remove the flag and restart the main bot (one line):
```
sed -i '/^DISABLE_USERBOT2=1$/d' /opt/bot/.env && systemctl restart bot.service
```
The main bot will connect userbot 2 again on startup, exactly as before.
The `.bak_userbot2off_nov25` files are pristine pre-patch copies if the
code itself ever needs restoring. Note: rolling back re-introduces the
shared-session disconnects, so only roll back if the patch itself causes
a problem, not because the dropbot disconnected (that is what the patch
fixes).

## Test results (on Nov 23 base copies, before delivery)

- Patch applies clean: E1 OK, E2 OK, E3 OK.
- Both patched files compile (`py_compile` OK).
- Idempotent: second run prints `OK: already has USERBOT2_OFF_NOV25, skipping.`
- Backups byte-identical to the base copies (pristine).
- AST check: in `init_userbot` the guard (line 2867) sits before
  `load_userbot_session2` (2872) and `TelegramClient` (2880); in
  `_start_second_userbot` the guard (6139) sits before all calls.
- Every remaining `userbot_client2.<attr>` use in the patched files is a
  guarded `is_connected()` check (3 sites, all None-checked first).
- No em-dashes added (patch file has 0; target files unchanged at 238/157).
- Anchors verified count==1 against core-fadf8802.py and runtime-c97fc7f1.py.
  Live /opt/bot files have post-Nov-23 patches (MONBOT_MODE, DROPBOT_MODE,
  GUARD, FINAL, PERM, DIPFIX, DIP_BOLD); the patch is fail-safe and writes
  nothing if an anchor fails live.
