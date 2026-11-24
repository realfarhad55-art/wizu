# DM Alert Settings follow-up (DM_ALERT_SETTINGS2_NOV25) — deploy note

## What this patch does

Follow-up to DM_ALERT_SETTINGS_NOV25 (already live). One patch file,
`apply_dm_alert_settings2_nov25.py`, four independent groups (each idempotent,
each with its own backup, each fail-safe on anchor mismatch):

1. **Spacing (spec section 9)** — one blank line below each section header:
   DM ALERT Settings screen ("Milestone Alerts", "DIP Profit Alerts") and
   Milestone Alerts screen ("All X Alerts", "Standard Milestones",
   "Major Milestones", "Disable X Alerts"). The DIP screen is built with
   the blank lines already in place.
2. **DIP Alerts screen (spec section 8)** — full screen, same pattern as the
   Milestone screen: header "Customize Your Dip Profit Alert Preferences"
   (premium emoji 5888670372093502546), intro paragraph, 4 sections with
   emoji 5260426225599405269 + bold headers ("All Dip Alerts",
   "Standard Dip Alerts", "Major Dip Alerts", "Disable Dip Alerts") each
   followed by a blank line then its paragraph. Buttons 2-per-line:
   [All Dip Alerts][Standard Dip Alerts] / [Major Dip Alerts][Disable Dip
   Alerts] / [BACK]. Tick (4958610528588008305) on the active choice, cross
   (5314430517314075350) on the others. Tapping saves the dip choice per user
   in `data/dm_alert_prefs.json` under key `"dip"` (same file as the X
   choice). "DIP Alerts" (main screen) and "DIP ALERT Setting" (Milestone
   screen) now open this real screen; the placeholder toast is gone.
   Button labels: the user wrote "All X Alerts / Standard / Major / Disable /
   BACK" — built as the Dip versions to match the section headers. Flag if
   that reading is wrong.
   Dip level sets: All = everything; Standard = 2-10, 15-50 step 5, 60-100
   step 10, 150, 200, 250, 500, 1000, 1500, then every +500; Major = 2, 10,
   20, 30, 50, 100, 200, 300, 500, 1000, then every +500; Disable = none.
   Default (no saved dip choice) = All.
3. **Dip enforcement** — the dip forward to the KOL owner DM is now gated
   on the owner's saved dip choice (default All). Recipients and the
   channel-first flow are unchanged; only the level filter is new.
4. **OwnerHelp media commands (spec section 10)** — `/setdmmedia` and
   `/cleardmmedia` added to OwnerHelp with NEW marking in two places:
   the "bot" (Bot Media & Templates) panel, under Public command, as a
   "NEW - DM Alert Settings media" entry; and `OH_CMD_TUTORIALS` 'bot'
   category, next to `/setcommandmedia`. One media slot covers all
   settings screens (no per-screen media commands needed).
5. **English only (spec section 11)** — `/setdmmedia` and `/cleardmmedia`
   owner replies converted from Roman Urdu to plain English. Public
   settings screens were already English; their text is unchanged.
   (OwnerHelp panel text itself stays Roman Urdu like the rest of the
   panel; only the two command replies were converted, per the task.)

## Deploy

Upload the patch to the **wizu** repo, then run on the VPS (one line):

```
cd /opt/bot && wget -O apply_dm_alert_settings2_nov25.py "https://raw.githubusercontent.com/realfarhad55-art/wizu/main/apply_dm_alert_settings2_nov25.py" && python3 apply_dm_alert_settings2_nov25.py /opt/bot && systemctl restart bot.service
```

Expected output: commands.py E1-E15 OK, OH E1-E2 OK, x_alert.py E1 OK
(helpers), x_alert.py E1 OK (dip forward). Backups, one per group:
`*.bak_DM_ALERT_SETTINGS2_NOV25`, `*.bak_DM_ALERT_SETTINGS2_OH_NOV25`,
`*.bak_DM_ALERT_SETTINGS2_DIPFWD_NOV25`.
If any group prints FAIL, that group wrote nothing — report the output,
do not force it. Groups that succeeded stay applied; the patch is
re-runnable.

## Verify

1. Bot restarts clean: `systemctl is-active bot.service` → active.
2. Open D.M Alert: blank line below "Milestone Alerts" and below
   "DIP Profit Alerts".
3. Open Milestone Alerts: blank line below each of the 4 section headers.
4. Tap "DIP Alerts": the "Customize Your Dip Profit Alert Preferences"
   screen opens (no "coming soon" toast). Tap "Standard Dip Alerts":
   it gets the tick, the others get crosses. Tap BACK: returns to the
   DM ALERT Settings screen.
5. Dip enforcement: set a dip choice (e.g. Major) on the owner's account,
   then watch the next dip forward — it forwards only if the level is in
   the chosen set. (Default All = today's behaviour for everyone else.)
6. OwnerHelp: open the Bot Media & Templates panel — the "NEW - DM Alert
   Settings media" entry is there with `/setdmmedia` + `/cleardmmedia`.
7. `/setdmmedia` without replying to media → English reply
   ("Reply to a photo or video with /setdmmedia."). Reply to a photo
   with `/setdmmedia` → English success message.
8. Media: run `/setdmmedia` (reply to a photo/video) if not set yet —
   settings replies are text-only until media is set.

## Rollback

Restore the per-group backup(s) and restart:
`cp /opt/bot/commands.py.bak_DM_ALERT_SETTINGS2_NOV25 /opt/bot/commands.py`
(and the matching OH / x_alert.py backups), then
`systemctl restart bot.service`. Each backup restores the state just
before its group ran.

## Open items / caveats

- **Dip-forward anchor risk (the one live-only anchor):** the enforcement
  edit anchors on the DIP_FWD_DM_NOV23 block, which is live-only (not in
  the Nov 23 GitHub copies). It is isolated in its own group
  (DM_ALERT_SETTINGS2_DIPFWD_NOV25): if Claude's Nov 24 dip patch changed
  that block, only the enforcement edit is skipped — the DIP screen and
  helpers still land. If it prints FAIL, report the output; the DIP screen
  will save choices but dip forwards will ignore them until the anchor is
  fixed to the live text.
- **DIP button labels:** built as Dip versions per the spec note; confirm
  with the user.
- **Media:** still unset until the owner runs `/setdmmedia` (reply to a
  photo/video). One slot (`command_media.dm_settings`) covers all three
  settings screens.
- **No runtime.py change needed:** no new commands were added
  (`/setdmmedia` + `/cleardmmedia` were already registered by patch 1).

## Testing (done on simulated live state)

Simulated live = Nov 23 base copies + patch 1 applied + DIP_FWD_DM E5
block inserted verbatim from `apply_dip_forward_dm_nov23.py`.
- Patch applies clean: commands.py E1-E15 + OH E1-E2, x_alert.py helpers
  E1 + enforcement E1. All three files compile. Idempotent re-run: all
  groups skip, exit 0.
- Functional dip filter, 12/12 pass: default-all allows everything;
  Standard allows 2/3/5/10/100/1500/2000, denies 12/110/2200; Major
  allows 2/10/30/50/100/1000/2000, denies 5/15/1500; Disable denies all;
  invalid stored choice falls back to All; dip set preserves an existing
  "x" choice in the same record; other users default to All.
- Spec text, spacing, DIP wiring, toast removal, English replies (scoped
  check on `cmd_setdmmedia` + `cmd_cleardmmedia` — other commands'
  Roman Urdu replies untouched), OwnerHelp NEW entries, enforcement gate:
  all verified present.
- Em-dash delta: 0 in both files; patch file itself has 0 em-dashes.
  (Two test-harness bugs found and fixed during testing: a shared anchor
  that matched 3 identical media-command lines — fixed by extending the
  anchor with the `dm_settings` lines; and per-group backups overwriting
  each other — fixed by naming backups per marker.)
