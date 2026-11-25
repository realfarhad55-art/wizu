# DM Alert Settings 4 — Channel Alerts (user GO Nov 25 ~06:07 PKT)

Patch: `apply_dm_alert_settings4_nov25.py` — **45,285 bytes**, marker
`DM_ALERT_SETTINGS4_NOV25` (+ `DM_ALERT_SETTINGS4_OH_NOV25` for OwnerHelp,
`DM_ALERT_SETTINGS4_DIPFWD_NOV25` for the dip-forward gate).
Repo: **wizu** (`realfarhad55-art/wizu`). One patch file, no new code files.
Idempotent, `.bak` backups, fail-safe on anchor mismatch (a failed group
leaves its file untouched).

## What it does

1. **Removes the "Channel: @Name" line** from the three DM Alert screens
   (Settings, Milestone, DIP). The Channel Picker stays; callbacks still
   carry the channel. Owner: the line did not look right on the page.
2. **Removes /linkme and /linksmart entirely** — handlers, runtime
   registrations, BotCommand menu entries, public-command lists
   (`PUBLIC_MEDIA_CMDS`, `PUBLIC_TEXT_CMDS`, `_PUB_CMD_LIST`,
   `_PUB_CMD_DESC`), the `/settext` tutorial entry, the `cmd_settext`
   docstring, the public-commands help sentence, and the OwnerHelp
   Bot Media tutorial lines + Public Command Media header.
   **Existing linked channels STOP getting forwards through the old link
   system.** Their owners must re-set levels via the new Channel Alerts
   button (see "Breaking change" below).
3. **Adds a "Channel Alerts" button in All Commands** (`build_command_keyboard`
   in core.py, right after the DM Alerts button). Label
   `🔮 Channel Alerts 🔮`, renamable via `/editbtnlabel channel_alerts <label>`.
   It opens the SAME settings as DM Alert (Channel Picker first, then
   Milestone / DIP screens, same tick/cross, same English), but the choices
   govern **CHANNEL forwards** (posts forwarded TO a channel), not DM forwards.
4. **Channel Alert prefs** — per-CHANNEL (not per user), stored in the same
   `data/dm_alert_prefs.json` under the top-level `"channel"` key:
   `{"channel": {"<channel>": {"x": ..., "dip": ...}}}`.
   Helpers in x_alert.py (`channel_alert_x_choice/dip_choice`,
   `channel_alert_x_set/dip_set`, `channel_alert_x_allows/dip_allows`),
   reusing the DM level sets and the DM prefs load/save
   (`_dm_alert_prefs_load` / `_dm_alert_prefs_save`), so the channel key
   lives in the same file as the DM prefs. Default all.
   Picker lists LINKED channels the user owns (via `kol_owners`); bot
   owners/admins see every linked channel. Add Channel links a new channel
   with the SAME admin check /linkme used (requester must be a channel
   admin; a private channel skips the check and is trusted), then reopens
   the picker. Runtime hook mirrors patch 3's `dmset` hook.
5. **Enforcement** (x_alert.py `_forward_alert_recipients`):
   - Linked-channel destinations (str targets) are filtered by that
     channel's X choice (default all).
   - The auto-forward to the KOL's own channel is gated the same way.
   - /linksmart's "smart" tier gate is RETIRED — the channel choice is now
     the single source of truth. Existing smart links keep working, now
     governed by prefs (default all).
   - Dip: the owner-DM forward is gated by BOTH the owner's DM dip choice
     (patch 3) AND the channel's dip choice (this patch). Dip alerts are
     never forwarded to a KOL channel, so the channel dip setting governs
     the only dip forward tied to the channel. Default all, so nothing
     changes until a channel owner sets a choice.
   - DM recipients keep patch 3 per-user-per-channel filtering (untouched).
6. **Media power for Channel Alerts** — `/setchannelmedia` +
   `/clearchannelmedia` (owner-only, reply to a photo/video), stored in
   `config["command_media"]["channel_alerts"]`, used by the Channel Alerts
   screens via `_send_screen(media_cmd="channel_alerts")`. Registered in
   runtime.py, listed in OwnerHelp with NEW marking (next to the
   /setdmmedia entries from patch 2). English replies.

## Breaking change — read this before deploy

**Existing /linkme + /linksmart links stop working.** The link records
(`data/linked_channels.json`) are NOT deleted, so the destinations loop
still reads them — but they are now filtered by the Channel Alert choice
(default all, so a linked channel still gets everything UNLESS its owner
sets a choice). The /linkme and /linksmart COMMANDS are gone, so owners
can no longer link/unlink that way. Tell channel owners: open All Commands,
tap Channel Alerts, pick your channel, set Milestone / DIP levels.
If a channel was linked via /linksmart (solid tiers only), it now gets ALL
levels by default until its owner sets a choice — that is the intended
retirement of smart mode, not a bug.

## Deploy (one step at a time, wait for his screenshot after each)

1. Upload `apply_dm_alert_settings4_nov25.py` to the **wizu** repo
   (GitHub web UI, same as patches 1-3).
2. On the VPS, in `/opt/bot` (patches 1-3 must already be live):
   `cd /opt/bot && wget -O apply_dm_alert_settings4_nov25.py "https://raw.githubusercontent.com/realfarhad55-art/wizu/main/apply_dm_alert_settings4_nov25.py"`
3. Run it (accepts a directory or a file):
   `cd /opt/bot && python3 apply_dm_alert_settings4_nov25.py /opt/bot`
   Expect `ALL OK` and one `OK (commands.py): cmd_linkme + cmd_linksmart removed`.
   If any group prints FAIL, it leaves that file untouched — paste the
   FAIL line back; do NOT restart.
4. Restart: `systemctl restart bot.service`
5. Confirm: `systemctl status bot.service` shows active, and the log shows
   no traceback on start.

## Verify (after restart)

- Open All Commands (`/command`): a **Channel Alerts** button sits right
  under DM Alerts. Tap it → picker "Which channel do you want alerts for?"
  with your linked channels + Add Channel.
- Open DM Alert Settings: the three screens show NO "Channel:" line.
- `/linksmart` and `/linkme` in a DM: bot replies unknown command
  (no handler, no menu entry).
- Pick a channel in Channel Alerts → set Milestone to **Major** → send a
  test 5x and a 10x for that channel (or wait for real ones): the channel
  gets the 10x forward but NOT the 5x. Set it back to All when done.
- `/setchannelmedia` (reply to a photo/video): "Channel Alert Settings
  media set!" → the Channel Alerts screens now show that media.
  `/clearchannelmedia` removes it.
- DM Alert Settings still work (pick a channel, change a DM level, confirm
  the tick moves) and `/subscribe` flow is unchanged.

## Rollback

Each file has a `.bak_DM_ALERT_SETTINGS4_NOV25` backup (commands.py also
`.bak_DM_ALERT_SETTINGS4_OH_NOV25`, x_alert.py also
`.bak_DM_ALERT_SETTINGS4_DIPFWD_NOV25`) in `/opt/bot`. To roll back one file:
`cd /opt/bot && cp <file>.bak_DM_ALERT_SETTINGS4_NOV25 <file>` then
`systemctl restart bot.service`. To roll back everything, restore all four
backups (commands.py, x_alert.py, core.py, runtime.py) and restart.
Re-running the patch is safe (idempotent — it skips groups already applied).

## Open items / things left alone on purpose

- **/linkinfo + DEFAULT_LINKME_INFO / DEFAULT_LINKSMART_INFO** are left
  alone. /linkinfo still describes the old /linkme flow. If he wants it
  updated, it needs new wording pointing at Channel Alerts (a separate
  small patch).
- **Hot Streak forward is NOT gated** by Channel Alerts. `_hs_forward_and_pin`
  forwards a streak post to the KOL's own channel if the bot is admin.
  There is no Hot Streak toggle in the settings UI, and /linkme's text
  promised Hot Streak forwards. Ask him if he wants a Hot Streak toggle
  or wants it left ungated.
- **SMART_LINK_MILESTONES + _smart_link_milestone_qualifies** (x_alert.py)
  are now dead code (no callers after the smart gate was removed). Left in
  place; harmless. Remove in a cleanup pass if he wants.
- **DIP button labels**: the Channel Alerts DIP buttons say "All Dip Alerts /
  Standard Dip Alerts / Major Dip Alerts / Disable Dip Alerts" (Dip versions
  of the DM labels). The user wrote "All X Alerts / Standard / Major /
  Disable" in his spec — confirm if he wants those exact labels.
- **New-user flow** (patch 3 open item): how a new user discovers Channel
  Alerts. Option A (hint after /subscribe) vs B (line in /start) vs both —
  still awaiting his pick.
- **Media for the screens is NOT set yet** — owner must run `/setdmmedia`
  (DM screens) and `/setchannelmedia` (Channel Alerts screens).

## Testing done (on copies, never live)

Test harness: `/tmp/dmset4_test` = Nov 23 base files + patches 1+2+3 applied
+ the live DIPFWD block inserted + the FORWARD_ON_NOV25 early-return removed
(to match live; the Nov 23 base still has the STOP_FORWARD return).
- Applies clean, **ALL OK**; second run idempotent (**ALL OK**, all groups skip).
- All four files compile (`py_compile`).
- Backups pristine (commands.py / core.py / runtime.py `.bak` byte-identical
  to pre-patch state; x_alert.py `.bak` differs only by the FORWARD_ON line,
  which is a test-setup change, not a patch change).
- **34/34 functional checks pass** (`func_test.py`): channel prefs save/read
  (Major/Standard/Disable/default all); Major allows 10x but NOT 5x;
  Standard allows 5x but NOT 12x; Disable blocks; dip Major allows 10x/30x
  but NOT 5x; DM prefs per-user-per-channel still work and are stored
  separately (uid key + "channel" key coexist in one prefs file, no collision).
- **10/10 picker checks pass** (`picker_test.py`): owner sees all linked
  channels, non-owner sees only channels they own, stranger sees none;
  picker shows channel buttons + Add Channel; empty state shows empty text
  + Add Channel, no channel buttons.
- (a) "Channel:" line absent from all three DM screens (grep 0).
- (b) /linksmart + /linkme handlers gone (0 defs, 0 runtime registrations,
  0 BotCommand entries; only comments + the left-alone /linkinfo and
  DEFAULT_* constants remain).
- (c) Channel Alerts button (core.py) → callback `channel_alerts` →
  `_chalert_show_picker` (71 `chalert_` references; all keyboard callbacks
  have a matching branch).
- (e) Enforcement wiring confirmed in code: destinations loop gated by
  `channel_alert_x_allows`, auto-forward wrapped in the same gate, DIPFWD
  gate is the combined `not _dm_alert_dip_allows(...) or not
  channel_alert_dip_allows(...)` condition. DM branches intact.
- (f) DM prefs untouched (func_test DM checks + DM callback branches present).
- No em-dashes in any new user-facing text. (The 14 em-dashes in the patch
  file are verbatim pre-existing `_PUB_CMD_DESC` descriptions carried over
  unchanged, not new copy.)

## Anchor notes (for the next patch)

The summary's line numbers were stale in several places; the anchors below
are the VERIFIED live forms (from the patched test files):
- `_forward_alert_recipients` signature is **4 params**:
  `(bot, channel, x_val, wizard_post_id)` — NOT the 6-param form.
- `PUBLIC_TEXT_CMDS` is a **single line**:
  `["submit", "subscribe", "linkme", "linksmart", "linkinfo", "history"]`.
- `_PUB_CMD_LIST` is the `["start", "command", "submit", "subscribe",
  "linkme", "linksmart", "linkinfo", "history"]` list (no "pnl"/"scan").
- The `/settext` tutorial is an `OH_CMD_TUTORIALS` tuple, not a
  `/settext command <text>` block. `cmd_settext` docstring is
  `Set the info text of a public command: /settext subscribe|history|linkme|linkinfo|submit`.
- The help-text /linkme sentence is at the end of the public-commands help
  string (`/unsubscribe @channel - stop DM alerts. /linkme @channel - link
  your channel to get its alerts. /linkinfo - how linking works.`).
- core.py All Commands uses `_pkb(...)` rows (not `InlineKeyboardButton`),
  and the dm_alerts row carries a `# BTN_SWAP_NOV18` comment.
- runtime.py Add Channel hook is `if msg.text and await
  dmset_on_add_channel_text(...)` (with the `msg.text and` guard).
- runtime.py registrations are aligned (`CommandHandler("linkme",    cmd_linkme)`);
  BotCommand descriptions are "Link your channel for alerts" /
  "Link your channel for solid alerts only".
- The DIPFWD gate is an if/else (`if not _dm_alert_dip_allows(...):
  logger.info(...) else: try: forward`), NOT a `return True` form, and its
  marker is `DM_ALERT_SETTINGS3_DIPFWD_NOV25`.
- The DM prefs use `_dm_alert_prefs_load()` / `_dm_alert_prefs_save()` with
  `DM_ALERT_PREFS_FILE`. There is NO `DM_ALERT_PREFS_PATH` and NO
  `load_json_file` / `save_json_file` in the codebase — the first draft of
  this patch used those names and was caught + fixed in testing.
- OH anchors that store literal `\n` escapes in the source must be written
  as raw strings (`r"""..."""`); a string ending in `"` must use triple
  single quotes (`r'''...'''`), otherwise the trailing `\"` adds a stray
  backslash and the anchor never matches.
- Idempotency: EVERY group's new text must contain its marker string,
  otherwise `patch_one` cannot detect it already applied and will re-apply
  (core.py duplicated the button row on the first re-run; fixed by adding
  a marker comment). `remove_link_cmds` is idempotent (returns True at once
  if both defs are already gone).
