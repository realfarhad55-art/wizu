# DM Alert Settings — Deploy Note (DM_ALERT_SETTINGS_NOV25)

User said GO Nov 25 ~03:39 PKT. Spec: `dm-alert-settings-spec-nov25.md`.

## What was built

Patch: `apply_dm_alert_settings_nov25.py` (one file, idempotent, marker
`DM_ALERT_SETTINGS_NOV25`, `.bak_dm_alert_settings_nov25` backups, fail-safe
on anchor mismatch). Touches 3 files: `commands.py` (E1-E3), `x_alert.py`
(E4-E5), `runtime.py` (E6).

1. **/start button rename** — "🔮 Command 🔮" -> "🔮 All Commands 🔮"
   (same `command_menu` callback).
2. **DM ALERT Settings screen** — tapping the D.M Alert button now opens the
   spec screen (bold header with premium emoji 5888670372093502546, intro
   paragraph, "Milestone Alerts" + "DIP Profit Alerts" sections with emoji
   5260426225599405269). Buttons: [Milestone Alerts] [DIP Alerts] [Back].
   First 2 buttons carry ONE premium emoji each (5888670372093502546).
   The OLD subscribe/unsubscribe text (`DM_ALERTS_TEXT`) is KEPT — the
   `/subscribe` command still uses it.
3. **Milestone Alerts screen** — "Customize Your X Alert Preferences" with
   the 4 options from the spec (All X Alerts / Standard Milestones / Major
   Milestones / Disable X Alerts) and their paragraphs. Buttons 2 per line:
   [All X Alerts][Standard Milestones] / [Major Milestones][Disable X Alerts]
   / [DIP ALERT Setting][BACK]. The 4 option buttons show TICK
   (4958610528588008305) on the active choice and CROSS (5314430517314075350)
   on the others. Tapping an option SAVES the choice per user in
   `data/dm_alert_prefs.json` (`{"<uid>": {"x": "all|standard|major|disable"}}`)
   and refreshes the tick/cross. BACK returns to the DM ALERT Settings screen.
4. **DIP buttons are EMPTY on purpose** — "DIP Alerts" (main screen) and
   "DIP ALERT Setting" (milestone screen) exist but only show a toast:
   "DIP Alert settings coming soon." No dip options, no dip text, no dip
   tick/cross. The user is making the DIP details himself and will send them
   later. Do NOT invent dip options when deploying.
5. **Enforcement (X alerts only)** — `_forward_alert_recipients` now filters
   DM recipients (owner + subscribers, int chat IDs) by their saved choice:
   All = every milestone; Standard = 2,5,10,15,20,25,30,35,40,45,50,55,60,
   65,70,75,80,85,90,95,100,150,200,250,300,500,600,700,800,900,1000; Major =
   2,10,20,50,100,200,300,500,1000; Disable = none. Default (no choice
   saved) = All, so users who never open settings keep today's behaviour.
   Linked-channel forwards (string targets) and the KOL own-channel
   auto-forward pass through unchanged. Dip enforcement is NOT built yet
   (no dip choices exist to enforce) — it comes with the DIP details.
6. **Media on every settings reply** — settings screens are sent via
   `_send_screen(..., media_cmd="dm_settings")`, which reads
   `config["command_media"]["dm_settings"]`. If empty, replies are text-only
   and nothing breaks. Owner commands (registered in runtime.py):
   - `/setdmmedia` — reply to a photo/video with it to set the media.
   - `/cleardmmedia` — clear it again.
   The user must run `/setdmmedia` once for media to appear.

## Deploy (wizu repo, then /opt/bot)

Upload `apply_dm_alert_settings_nov25.py` to the **wizu** repo, then run
(one line):

```
cd /opt/bot && wget -O apply_dm_alert_settings_nov25.py "https://raw.githubusercontent.com/realfarhad55-art/wizu/main/apply_dm_alert_settings_nov25.py" && python3 apply_dm_alert_settings_nov25.py /opt/bot && systemctl restart bot.service
```

Expected output: E1/E2/E3 OK (commands.py), E1/E2 OK (x_alert.py), E1 OK
(runtime.py), then DONE. The patch accepts a directory (`/opt/bot`) or any
one of the three files as its argument.

## Verify

1. `/start` in a DM with the bot — button now reads "All Commands".
2. Open the command menu, tap **D.M Alerts** — the "DM ALERT Settings"
   screen appears with the exact spec text and 3 buttons.
3. Tap **Milestone Alerts** — "Customize Your X Alert Preferences" appears;
   "All X Alerts" shows the tick, the other 3 show a cross (default = All).
4. Tap **Standard Milestones** — tick moves to it, others show cross.
5. Tap **DIP Alerts** — toast "DIP Alert settings coming soon.", screen
   stays as-is (empty by design).
6. Enforcement: with a test account set to Standard, a 3x alert must NOT
   forward to that DM while a 5x alert does. (Disable = nothing arrives.)
7. Media: reply to a photo/video with `/setdmmedia` (owner only), then open
   the settings screen again — the media shows. `/cleardmmedia` removes it.

## Rollback

Restore the three backups and restart:
`cp /opt/bot/commands.py.bak_dm_alert_settings_nov25 /opt/bot/commands.py`
(and the same for `x_alert.py` and `runtime.py`), then
`systemctl restart bot.service`. Saved prefs in
`/opt/bot/data/dm_alert_prefs.json` are inert without the patch and can be
left or deleted.

## Test results (on Nov 23 base copies, /tmp/dmset_test)

- Patch applies clean: E1-E3 commands.py, E1-E2 x_alert.py, E1 runtime.py.
- All 3 files compile. Backups byte-identical to base copies.
- Idempotent: 2nd and 3rd runs skip all 3 files, exit 0 (a runtime.py
  duplicate-handler bug found during testing was fixed by adding the marker
  comment to the new handler lines).
- No em-dashes added (delta 0 in all 3 files).
- Functional test of the filter (22 checks, all pass): no-saved gets
  everything; All gets everything; Standard gets 5x/100x/150x/1000x but not
  3x/12x/2000x; Major gets 2x/10x/50x/1000x but not 5x/30x; Disable gets
  nothing; invalid stored choice falls back to All; choices persist.
- Spec text spot-checked in the patched file (all lines present, including
  the Major line, which is split across two adjacent string literals and
  concatenates exactly to the spec sentence).

## Anchors used

- commands.py E1: `kb      = InlineKeyboardMarkup([[_pkb("🔮 Command 🔮", ...`
  (unique, 1 occurrence).
- commands.py E2: end of `DM_ALERTS_TEXT` + `FAST_TRACK_TEXT = (`.
- commands.py E3: the `dm_alerts` branch (3 lines).
- x_alert.py E4: `async def _forward_alert_recipients(bot, channel, x_val, wizard_post_id):`
  (insert helpers before it; the line after it differs live vs base
  because of FORWARD_ON_NOV25, so the anchor deliberately stops at the def line).
- x_alert.py E5: the `asyncio.gather(*[_one(chat_id, label) ...` lines.
- runtime.py E6: the `setcommandmedia` / `clearcommandmedia` handler lines.

## Open items / warnings

- **DIP screen intentionally empty** — waiting on the user's exact DIP text.
  When it arrives: build the DIP screen the same way, add dip choices to
  `dm_alert_prefs.json` (`{"x": ..., "dip": ...}`), and enforce in
  `_dip_dm_recipients` (DM path) + the DIP_FWD_DM owner forward in
  `send_dip_alert` (live-only code, anchor from
  `apply_dip_forward_dm_nov23.py` E5).
- **Media must be set** via `/setdmmedia` or settings replies are text-only.
- **Live-file drift**: the patch was anchored on the Nov 23 base copies. The
  live files carry later patches (MONBOT_MODE, USERBOT2_OFF, FORWARD_ON_NOV25,
  Claude's dip patch). If any anchor fails live, the patch writes NOTHING for
  that file and prints FAIL — report the output, do not force it.
- The patch script accepts a directory argument (this was the IsADirectoryError
  that hit the forward-on patch) — `/opt/bot` works.
