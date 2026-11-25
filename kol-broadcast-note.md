# KOL Owner Broadcast + "KOL Alert" rename + Channel Picker fix

Patch file: `apply_kol_broadcast_nov25.py` (36,175 B, marker `KOL_BROADCAST_NOV25`)
Repo: **wizu** (`realfarhad55-art/wizu`) - same repo as the main bot.
Run on: `/opt/bot`, **AFTER DM Alert Settings patches 1-4** (it anchors on patch 4's button line and help text).

## What this patch does (3 parts)

### 1. NEW: /kolbroadcast - personalised broadcast to KOL channel owners
- Owner-only command. `/kolbroadcast` = every listed (tracked) channel's owner. `/kolbroadcast @ch1 @ch2 ...` = only those channels' owners.
- Owner sends a template (text, photo, or video with caption). `{Username}` and `{Channel}` are replaced **per recipient**: Shahroz gets `@shahroz2` + `@Marvels_calls`, Farhad gets `@farhad` + `@bigbangcall`. Lowercase `{username}` / `{channel}` work too. No placeholders = same text to everyone.
- Owner lookup, in order: (1) linked owner from `/linkme` data (`kol_owners`); (2) channel **creator** via `getChatAdministrators`; (3) skip + list in the report as "owner not found".
- Flow mirrors the existing Broadcast: **preview first** (rendered for the first recipient + recipient count) with **Send / Rewrite / Cancel**. Nothing is sent until Send. About **1 msg/sec**, blocked users are skipped and counted, one failure never stops the rest. One DM per channel an owner owns.
- Recorded in `broadcasts.json`, so `/pinbroadcast`, `/replybroadcast`, `/editbroadcast`, `/deletebroadcast`, `/listbroadcasts` all work on it. No auto-pin (same rule as normal broadcasts). Note: `/editbroadcast` sends ONE text to all - no per-recipient variables on edit.

### 2. RENAME: "Channel Alerts" button -> "KOL Alert"
- All Commands button label only. `callback_data` and the `lbl` key stay `"channel_alerts"`, so `/editbtnlabel` still works. The help-text mention is updated too.
- Screen titles ("CHANNEL ALERT Settings") and OwnerHelp media entries are untouched - they name the screens, not the button.
- If a custom label was set via `/editbtnlabel`, re-run it after deploy.

### 3. PICKER FIX - why ~139 channels were showing (user report Nov 25 ~06:51 PKT)
- **Root cause:** patch 4's `_chalert_user_channels()` had a shortcut: if the user is the bot owner/admin, return **EVERY linked channel**. Real is the bot owner, so his Channel Alert picker listed all ~139 linked KOL channels (@Acid_call, @Apewonecall, @Basedmakedreamcalls, @Bigbangcall, @Bingobangers, ...). That shortcut is now deleted.
- **What changed:** the picker lists ONLY channels the current user **owns**:
  - the user who linked it (`kol_owners` - the `/linkme` / Add Channel record), OR
  - the channel **creator** (checked via `getChatAdministrators`, only for linked channels with NO recorded owner - covers Real's own channels if someone else linked them, and old links made before `kol_owners` existed).
- **What Real will now see:** only his own channels - @BigBangCall, @acid_call, @MiniBangCall, @DaffodilCalls, @WizardScan (and @wizardscantest if linked). The ~139 KOL channels owned by others are gone.
- **What a KOL owner sees:** only THEIR channel (e.g. Shahroz sees only @marvelscalls). A stranger sees none - just the empty state ("You haven't linked any channel yet") + Add Channel.
- **One honest caveat:** @Marvels_calls shows for whoever owns it. If Shahroz created/linked it, it shows for Shahroz, NOT for Real. If Real created it, the creator fallback shows it for him too. Same rule for any channel Farhad linked: it still shows for Real if he is its creator.
- **Unlinked channels** (never linked, no recorded owner) never appear in the picker for anyone. Add Channel links a channel and records the linker as owner, so it shows at once. The Add Channel admin check is unchanged.
- **The DM picker is untouched.** It lists SUBSCRIBED channels, which is correct for DM alert prefs - a subscriber can follow many channels. Only the Channel/KOL Alert picker (owner settings) is ownership-filtered.
- **Performance guard:** the creator check runs only for channels with no recorded owner, max 10 at a time, whole check capped at 15 seconds. If it times out or the bot is not admin somewhere, the picker just falls back to the link-owner list - it never hangs and never shows extra channels.

## Deploy (one step at a time, Termius)

Step 1 - upload `apply_kol_broadcast_nov25.py` to the **wizu** repo (GitHub web UI, same as patches 1-4).

Step 2 - run on the VPS (one 1-click block):

```
cd /opt/bot && wget -O apply_kol_broadcast_nov25.py "https://raw.githubusercontent.com/realfarhad55-art/wizu/main/apply_kol_broadcast_nov25.py" && python3 apply_kol_broadcast_nov25.py /opt/bot && systemctl restart bot.service
```

Expected output: `E1 OK / E2 OK` (core.py), `E1..E10 OK` (commands.py), `E1..E4 OK` (runtime.py), then `ALL OK`. Backups are written next to the files (`*.bak_KOL_BROADCAST_NOV25`). If any edit says FAIL, the patch writes nothing for that file - send the output, do not restart.

## Verify (after restart)

1. **Picker (Real):** open /command, tap **KOL Alert** (new label). The picker must show ONLY his own channels (BigBangCall, acid_call, MiniBangCall, DaffodilCalls, WizardScan, wizardscantest if linked). The ~139 KOL channels must be gone. Tap one and set a level - it must save.
2. **Picker (KOL owner):** Shahroz opens KOL Alert - only @marvelscalls shows.
3. **Broadcast to 1 channel:** `/kolbroadcast @marvels_calls`, send a template with `{Username}` and `{Channel}` (e.g. `Hello {Username}, your channel {Channel} is listed.`). Preview must show the rendered text for Shahroz (`@shahroz2` / `@Marvels_calls`) and recipient count 1. Tap **Cancel** first - nothing must arrive. Then run it again and tap **Send** - Shahroz must get exactly that personalised DM.
4. **Custom list:** `/kolbroadcast @bigbangcall` must send only to Farhad.
5. **Pin:** after a send, `/pinbroadcast <bid>` pins it in the recipient DM (same as normal broadcasts).
6. **Rename:** All Commands shows **KOL Alert**; the old "Channel Alerts" label is gone. DM Alert Settings screens still work (Milestone/DIP choices, Channel Picker FIRST).

## Rollback

The patch backs up the pre-patch files on the VPS. To undo (one 1-click block):

```
cd /opt/bot && cp core.py.bak_KOL_BROADCAST_NOV25 core.py && cp commands.py.bak_KOL_BROADCAST_NOV25 commands.py && cp runtime.py.bak_KOL_BROADCAST_NOV25 runtime.py && systemctl restart bot.service
```

This restores the state with patches 1-4 still live (the backups were taken after patches 1-4). To also remove the patch file itself: `rm /opt/bot/apply_kol_broadcast_nov25.py`.

## Open items / known limits

- **Owner lookup gaps:** a channel whose owner never linked it AND where the bot is not admin cannot be resolved - it is skipped and listed in the send report as "owner not found". Fix is to link it (`/linkme`) or make the bot admin.
- **Rate limits:** ~1 msg/sec by design. A 200-owner broadcast takes ~3-4 minutes. Telegram flood limits can still pause it; the send loop retries once on RetryAfter, then counts the rest as failed and reports them.
- **Preview shows the first recipient only** (sorted by channel). The rest are counted, not previewed one by one.
- **/editbroadcast has no per-recipient variables** (same limitation as normal broadcasts - edit sends one text to all).
- **Creator check on picker open:** bounded at 15s and only for channels with no recorded owner. In the worst case (many unlinked-owner channels) the picker may take a few seconds to open; it falls back to the link-owner list on timeout.
- **Left over from patch 4 (unchanged):** `/linkinfo` + `DEFAULT_LINKME_INFO` still describe `/linkme`; Hot Streak forwards are not gated by Channel Alerts; `SMART_LINK_MILESTONES` is dead code.
- **Not yet decided:** new-user flow for DM Alert Settings (Option A vs B vs both) - still awaiting his pick.

## Testing done (on copies of the Nov 23 base files + patches 1-4 + live dip-forward block, never on live files)

- Patch applies clean: core E1-E2, commands E1-E10, runtime E1-E4, `ALL OK`. All 4 files compile. Re-run is idempotent (all groups skip). Em-dash delta: 0 in every file.
- **KOL broadcast - 31/31 pass:** template rendering per recipient (Shahroz `@shahroz2`/`@Marvels_calls` vs Farhad `@farhad`/`@bigbangcall` produce different texts); lowercase placeholders; no-placeholder text unchanged; username fallback to first name, then "there"; bold/italic entity offsets shift correctly across replacements (incl. photo captions); original entities untouched; forward drafts unchanged; recipient resolution (linked owner first, creator fallback, skip + report, sorted); custom list targets only listed channels; one DM per channel for multi-channel owners; execute counts (sent/failed/blocked), RetryAfter retry, blocked user skipped; `/kolbroadcast` arg parsing (all / custom / unknown / all-unknown aborts with a warning).
- **Picker - 19/19 pass** (fixture: 139 KOL channels + Real's 6 + @marvelscalls + 4 owner-less linked channels): Real sees exactly his 6 linked-owned channels (139 gone; @marvelscalls correctly absent - Shahroz owns it); creator fallback adds only the channel Real created; other owner-less channels stay out (incl. bot-not-admin); Shahroz sees only @marvelscalls (+ his own creator fallback channel); stranger sees none (empty state + Add Channel only); `bot=None` falls back to the link-owner list without crashing; the old `is_admin_or_owner` sees-all branch is gone from `_chalert_user_channels`.
