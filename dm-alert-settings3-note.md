# DM Alert Settings 3 — Channel Picker — Deploy Note

Patch: `apply_dm_alert_settings3_nov25.py` (one file, idempotent).
Markers: `DM_ALERT_SETTINGS3_NOV25` (commands.py + x_alert.py + runtime.py),
`DM_ALERT_SETTINGS3_DIPFWD_NOV25` (x_alert.py dip-forward gate only).
Backups: `*.bak_DM_ALERT_SETTINGS3*` (one per group).

## Deploy — AFTER patch 2 is deployed

Upload the patch to the **wizu** repo, then run on the VPS:

```
cd /opt/bot && wget -O apply_dm_alert_settings3_nov25.py "https://raw.githubusercontent.com/realfarhad55-art/wizu/main/apply_dm_alert_settings3_nov25.py" && python3 apply_dm_alert_settings3_nov25.py /opt/bot && systemctl restart bot.service
```

Expected output: commands.py E1-E8 OK, x_alert.py E1-E7 OK, x_alert.py DIPFWD E1 OK,
runtime.py E1 OK, DONE. If any group prints FAIL, nothing was written for that
group: report the output, do NOT force it. (The DIPFWD group is isolated: if its
anchor fails live, only the dip gate is skipped; the picker and helpers still land.)

## What it does

1. **Channel Picker (new first step).** Tapping D.M Alert now shows
   "Which channel do you want alerts for?" (bold, main premium emoji), with one
   button per channel the user subscribed to (from `channel_subs.json`, the same
   source the X-alert forward uses), plus "➕ Add Channel" and Back.
   No subscriptions: "You haven't subscribed to any channel yet. Use /subscribe
   @channel to follow a channel, then come back here to set its alerts."
2. **Add Channel.** Tapping it asks for the channel username
   ("Send the channel username, like @Trenchmarkgems."). The user's next private
   text message is taken as the name and subscribed with the SAME `/subscribe`
   logic (`cmd_subscribe` is called, not re-implemented). Then the picker
   reopens with the new channel listed. Invalid / untracked channel:
   "I couldn't find that channel. Check the username and try again."
   `/cancel` goes back to the picker. The waiting flag is one-shot and cleared
   whenever the user navigates in the settings (same pattern as the skipcall flow).
3. **Per-channel settings.** Picking a channel shows the DM ALERT Settings screen
   for THAT channel, with a "Channel: @Name" line under the title. Milestone and
   DIP screens show the same line. All level choices are saved per user per
   channel in `data/dm_alert_prefs.json`:
   `{"<uid>": {"<channel>": {"x": ..., "dip": ...}}}`.
4. **Migration.** An old-shape record `{"<uid>": {"x": ..., "dip": ...}}` is read
   as the default for EVERY channel of that user until they set a per-channel
   choice. Legacy buttons without a channel keep working (old-shape read/write).
5. **Enforcement.** X forwards and the dip owner forward now filter by
   (user, channel, level). Default (no saved choice) = All, as before.
   Channel forwards (linked channels) still pass through untouched.
6. **Back.** From the settings screens, Back goes to the Channel Picker.
   From the picker, Back goes to the command menu (the existing Back behaviour).
7. **English only** in all new user-facing text. No new code files: everything
   in existing commands.py / x_alert.py / runtime.py.

## Verify

1. `systemctl is-active bot.service` -> active.
2. Tap D.M Alert -> picker lists your subscribed channels + Add Channel.
3. Pick a channel -> settings screen shows "Channel: @Name" under the title.
4. Milestone screen: set Standard for channel A, Disable for channel B.
   Reopen each: tick/cross must differ per channel.
5. Add Channel: tap it, send a tracked channel username -> subscribed + picker
   shows the new channel. Send a bad name -> "I couldn't find that channel."
6. A 5x alert for channel A (Disable) must NOT forward to your DM; a 5x for
   channel B (Standard) must forward.
7. `/subscribe` / `/unsubscribe` still work exactly as before.

## Rollback

Restore the backups and restart:
```
cd /opt/bot && cp commands.py.bak_DM_ALERT_SETTINGS3_NOV25 commands.py && cp x_alert.py.bak_DM_ALERT_SETTINGS3_NOV25 x_alert.py && cp runtime.py.bak_DM_ALERT_SETTINGS3_NOV25 runtime.py && systemctl restart bot.service
```
(The DIPFWD backup `x_alert.py.bak_DM_ALERT_SETTINGS3_DIPFWD_NOV25` holds the
state with the main-group edits applied; restoring the main-group backup above
is enough for a full rollback. `data/dm_alert_prefs.json` is untouched by a
rollback; old-shape records keep working, per-channel records are ignored by
the old code.)

## Open items

- **KOL owners:** the picker lists SUBSCRIBED channels only. A KOL owner who
  is not subscribed to their own channel still gets forwards (default All, or
  their old-shape choice). To change levels for their own channel they must
  `/subscribe` to it first.
- **New-user flow (spec section 13):** still open — Option A (hint after
  /subscribe) vs Option B (line in /start) vs both. Awaiting the user's pick.
- **Add Channel flag:** one-shot + cleared on navigation; no 5-minute timeout
  like the AI chat has. If the user abandons mid-flow, their NEXT private
  message will still be treated as a channel name until they tap a settings
  button or send /cancel.
- **Dip gate anchor:** if the DIPFWD group prints FAIL live (Claude's Nov 24
  dip patch changed the block), dip forwards ignore per-channel dip choices
  until the anchor is fixed to the live text. The picker and X enforcement
  are unaffected.
- **Media:** picker/add screens use the same `dm_settings` media slot
  (`/setdmmedia`); text-only until the owner sets it.
