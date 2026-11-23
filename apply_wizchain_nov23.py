#!/usr/bin/env python3
"""WizardScan chain fix: pair-link chain preserved + Details chain hint (Nov 23 2026).

User report (Nov 23): token AI, CA 0x2598c30330D5771AE9F983979209486aE26dE875.
- BigBang post (dexscreener.com/bsc/0xbacbea...) + Kolscope say BSC (correct).
- WizardScan dropped call shows Base + CA 0xbacbea... (the PAIR address, not the token).
- WizardScan Details shows the right CA but chain ETH.
So WizardScan is wrong in two places; BigBang is right.

Root causes (verified against live DexScreener data):
1. The token exists on MANY chains (ETH, BSC, Base, Arbitrum, Polygon,
   Optimism). The Base pair is the NEWEST (created 2025) but nearly dead
   (liq $3.32). The BSC pair is the real one (MC ~80K, the KOL's link).
2. Dropped call: the KOL posted only a DexScreener chart link, so the bot
   grabbed the PAIR address from the URL as the CA. _resolve_pair_to_token
   resolves it to the real token, but the PAIR's chain (BSC) is LOST — the
   recursive lookup is chain-agnostic, and _parse_dex_pairs' "newest pair"
   collision guard picks the newest chain (Base, the dead pair) instead of
   the BSC pair the KOL actually linked to.
3. Details: fetch_ca_data queries chain endpoints in order with ETH first
   for 0x addresses, and picks the FIRST chain with any pair. The token
   has a real ETH pair (bigger liq than BSC), so Details shows ETH.

Changes (core.py + dropped_call.py):
1. _resolve_pair_to_token returns (token, chain_slug) — the DexScreener
   chain slug where the pair was found (e.g. "bsc"). Cache stores
   (token, chain_slug, expires_at); old 2-tuple entries still honoured.
   Only ONE caller exists (_fetch_dex_sync), updated below.
2. _fetch_dex_sync accepts prefer_chain=None. In the pair-address
   fallback, the resolved pair's chain is passed to the recursive call,
   and _parse_dex_pairs is given prefer_chain so it only considers
   pairs on that chain. Normal token lookups (prefer_chain=None) are
   unchanged.
3. _parse_dex_pairs accepts prefer_chain=None. When set and pairs exist
   on that chain, sup is restricted to that chain (safe fallback: if no
   pair matches, sup is unchanged). The collision guard then only sees
   one chain, so it cannot pick a wrong one.
4. fetch_ca_data accepts chain_hint=None (a display code like "BNB" /
   "BASE" / "ETH", or a DexScreener slug). When given, that chain is
   moved to the front of the lookup order, so Details shows the call's
   chain instead of defaulting to ETH-first. "EVM" (generic) is ignored.
5. build_drop_details_for_call passes the tracked call's stored "chain"
   as the hint, so Details for a tracked call shows that call's chain.

Effect: a KOL pair link on BSC now tracks + displays as BSC (dropped
call, X alerts, Details), instead of Base/ETH. Existing tracked calls
keep their stored chain until re-resolved; a wrong stored chain can be
corrected with /fixoldcall using the correct pair link.

Requires: live /opt/bot/core.py + dropped_call.py. Run once from /opt/bot:
    python3 apply_wizchain_nov23.py core.py dropped_call.py
(or run twice, once per file — the script takes the files as arguments.)
VPS-only one-time script. Idempotent (marker WIZCHAIN_NOV23).
Backups: core.py.bak_wizchain_nov23, dropped_call.py.bak_wizchain_nov23.
Fail-safe: validates ALL anchors before writing anything; aborts
without touching any file on mismatch.
"""

import sys, shutil

MARKER = "WIZCHAIN_NOV23"

# ── core.py ──────────────────────────────────────────────────────────────────

# E1a: _resolve_pair_to_token cache read (handle old 2-tuple + new 3-tuple).
OLD_E1A = """    cached = _pair_token_cache.get(addr)
    if cached is not None:
        token_c, expires_at = cached
        if token_c or time.time() < expires_at:
            return token_c
        # negative result expired — fall through and try again
    token = None"""
NEW_E1A = """    cached = _pair_token_cache.get(addr)
    if cached is not None:
        # WIZCHAIN_NOV23: cache is (token, chain_slug, expires_at); old
        # 2-tuple entries (token, expires_at) are still honoured.
        if len(cached) == 3:
            token_c, chain_c, expires_at = cached
        else:
            token_c, expires_at = cached
            chain_c = None
        if token_c or time.time() < expires_at:
            return (token_c, chain_c)
        # negative result expired — fall through and try again
    token = None
    pair_slug = None  # WIZCHAIN_NOV23: DexScreener slug where the pair lives"""

# E1b: _resolve_pair_to_token DexScreener loop — track the slug.
OLD_E1B = """                base = ((p.get("baseToken") or {}).get("address") or "").strip()
                if base and base.lower() != addr.lower():
                    token = base
                    break
            if token:
                break"""
NEW_E1B = """                base = ((p.get("baseToken") or {}).get("address") or "").strip()
                if base and base.lower() != addr.lower():
                    token = base
                    pair_slug = slug  # WIZCHAIN_NOV23: remember the pair's chain
                    break
            if token:
                break"""

# E1c: _resolve_pair_to_token GeckoTerminal fallback — track the slug.
OLD_E1C = """                if "_" in base_id:
                    base_addr = base_id.split("_", 1)[1].strip()
                    if base_addr and base_addr.lower() != addr.lower():
                        token = base_addr
                        logger.info(f"🔗 Pair address resolved via GeckoTerminal (DexScreener "
                                    f"had no pool data): {addr[:10]}… → token {token[:10]}…")
                        break"""
NEW_E1C = """                if "_" in base_id:
                    base_addr = base_id.split("_", 1)[1].strip()
                    if base_addr and base_addr.lower() != addr.lower():
                        token = base_addr
                        pair_slug = slug  # WIZCHAIN_NOV23: remember the pair's chain
                        logger.info(f"🔗 Pair address resolved via GeckoTerminal (DexScreener "
                                    f"had no pool data): {addr[:10]}… → token {token[:10]}…")
                        break"""

# E1d: _resolve_pair_to_token cache write + return (tuple).
OLD_E1D = """    if len(_pair_token_cache) > 4000:
        _pair_token_cache.clear()
    # Positive resolves are permanent (a pair's base token never changes).
    # Negative resolves expire quickly so a too-early attempt gets retried
    # once DexScreener/GeckoTerminal actually indexes the pair.
    _pair_token_cache[addr] = (token, time.time() + _PAIR_RESOLVE_NEG_TTL)
    return token"""
NEW_E1D = """    if len(_pair_token_cache) > 4000:
        _pair_token_cache.clear()
    # Positive resolves are permanent (a pair's base token never changes).
    # Negative resolves expire quickly so a too-early attempt gets retried
    # once DexScreener/GeckoTerminal actually indexes the pair.
    # WIZCHAIN_NOV23: cache now stores (token, chain_slug, expires_at).
    _pair_token_cache[addr] = (token, pair_slug, time.time() + _PAIR_RESOLVE_NEG_TTL)
    return (token, pair_slug)"""

# E2a: _fetch_dex_sync signature — prefer_chain param.
OLD_E2A = """def _fetch_dex_sync(ca, retries=2, min_liquidity=500, allow_alt=True):"""
NEW_E2A = """def _fetch_dex_sync(ca, retries=2, min_liquidity=500, allow_alt=True, prefer_chain=None):"""

# E2b: _fetch_dex_sync _parse_dex_pairs calls — pass prefer_chain.
OLD_E2B = """        if pairs:
            result = _parse_dex_pairs(pairs, min_liquidity, ca)
            if result is None:
                # Pairs exist but all below the liquidity floor — retry without it
                # so the UI still shows a live price instead of "N/A".
                result = _parse_dex_pairs(pairs, 0, ca)"""
NEW_E2B = """        if pairs:
            result = _parse_dex_pairs(pairs, min_liquidity, ca, prefer_chain=prefer_chain)
            if result is None:
                # Pairs exist but all below the liquidity floor — retry without it
                # so the UI still shows a live price instead of "N/A".
                result = _parse_dex_pairs(pairs, 0, ca, prefer_chain=prefer_chain)"""

# E2c: _fetch_dex_sync scoped v1 fallback — pass prefer_chain.
OLD_E2C = """            if scoped:
                result = (_parse_dex_pairs(scoped, min_liquidity, ca)
                          or _parse_dex_pairs(scoped, 0, ca))"""
NEW_E2C = """            if scoped:
                result = (_parse_dex_pairs(scoped, min_liquidity, ca, prefer_chain=prefer_chain)
                          or _parse_dex_pairs(scoped, 0, ca, prefer_chain=prefer_chain))"""

# E2d: _fetch_dex_sync pair-address fallback — use the pair's chain.
OLD_E2D = """        if not result:
            _tok = _resolve_pair_to_token(ca)
            if _tok and _tok.lower() != (ca or "").lower():
                logger.info(f"🔗 Pair address resolved: {ca[:10]}… → token {_tok[:10]}…")
                result = _fetch_dex_sync(_tok, retries=1,
                                         min_liquidity=min_liquidity,
                                         allow_alt=allow_alt)
                if result:
                    result["resolved_ca"] = _tok"""
NEW_E2D = """        if not result:
            # WIZCHAIN_NOV23: the resolver now returns (token, chain_slug).
            # The pair's chain is the call's chain — pass it down so the
            # token lookup cannot wander off to another chain's pair.
            _tok, _pair_slug = _resolve_pair_to_token(ca)
            if _tok and _tok.lower() != (ca or "").lower():
                logger.info(f"🔗 Pair address resolved: {ca[:10]}… → token {_tok[:10]}…")
                result = _fetch_dex_sync(_tok, retries=1,
                                         min_liquidity=min_liquidity,
                                         allow_alt=allow_alt,
                                         prefer_chain=_pair_slug or prefer_chain)
                if result:
                    result["resolved_ca"] = _tok"""

# E3: _parse_dex_pairs — prefer_chain param + restrict sup to that chain.
OLD_E3 = """def _parse_dex_pairs(pairs: list, min_liquidity: int, token_address: str = "") -> dict | None:
    \"\"\"Parse a DexScreener pairs list into our internal dict. Returns None if unusable.\"\"\"
    sup = [p for p in pairs if p.get("chainId","").lower() in SUPPORTED_CHAINS
           and (p.get("liquidity",{}).get("usd") or 0) >= min_liquidity]
    # priceUsd always describes baseToken.  A searched contract can also occur
    # as quoteToken; treating that pair as the call token silently tracks the
    # other asset (often SOL/WETH) and leaves the call stuck around 1x.
    if token_address:
        wanted = token_address.lower()
        sup = [p for p in sup if ((p.get("baseToken") or {}).get("address") or "").lower() == wanted]
    if not sup:
        return None"""
NEW_E3 = """def _parse_dex_pairs(pairs: list, min_liquidity: int, token_address: str = "", prefer_chain: str = None) -> dict | None:
    \"\"\"Parse a DexScreener pairs list into our internal dict. Returns None if unusable.\"\"\"
    sup = [p for p in pairs if p.get("chainId","").lower() in SUPPORTED_CHAINS
           and (p.get("liquidity",{}).get("usd") or 0) >= min_liquidity]
    # priceUsd always describes baseToken.  A searched contract can also occur
    # as quoteToken; treating that pair as the call token silently tracks the
    # other asset (often SOL/WETH) and leaves the call stuck around 1x.
    if token_address:
        wanted = token_address.lower()
        sup = [p for p in sup if ((p.get("baseToken") or {}).get("address") or "").lower() == wanted]
    # WIZCHAIN_NOV23: when the caller knows the chain (e.g. the KOL's pair
    # link was on BSC), only pairs on that chain count. A multi-chain token
    # must not resolve to a different chain's pair (newest-pair guard /
    # ETH-first lookup). Safe fallback: if no pair matches, sup is unchanged.
    if prefer_chain:
        _pc = str(prefer_chain).lower()
        _on = [p for p in sup if (p.get("chainId") or "").lower() == _pc]
        if _on:
            sup = _on
    if not sup:
        return None"""

CORE_EDITS = [
    ("E1a pair resolver cache read", OLD_E1A, NEW_E1A),
    ("E1b pair resolver DexScreener slug", OLD_E1B, NEW_E1B),
    ("E1c pair resolver GeckoTerminal slug", OLD_E1C, NEW_E1C),
    ("E1d pair resolver cache write + return", OLD_E1D, NEW_E1D),
    ("E2a _fetch_dex_sync prefer_chain param", OLD_E2A, NEW_E2A),
    ("E2b _fetch_dex_sync parse calls", OLD_E2B, NEW_E2B),
    ("E2c _fetch_dex_sync scoped fallback", OLD_E2C, NEW_E2C),
    ("E2d pair fallback uses pair chain", OLD_E2D, NEW_E2D),
    ("E3 _parse_dex_pairs prefer_chain", OLD_E3, NEW_E3),
]

# ── dropped_call.py ───────────────────────────────────────────────────────────

# E4a: fetch_ca_data signature — chain_hint param.
OLD_E4A = """def fetch_ca_data(ca):"""
NEW_E4A = """def fetch_ca_data(ca, chain_hint=None):"""

# E4b: fetch_ca_data — hint chain goes first in the lookup order.
OLD_E4B = """    # ── DexScreener (chain-specific endpoints, first chain with pairs wins) ──
    try:
        if ca.startswith("0x"):
            dexpaths = ["ethereum", "bsc", "base", "arbitrum", "polygon",
                        "optimism", "avalanche", "linea", "zksync", "scroll",
                        "mantle", "blast", "fantom", "cronos", "gnosis",
                        "moonbeam", "celo", "pulsechain", "aptos", "sui"]
        else:
            dexpaths = ["solana", "ton", "tron"]"""
NEW_E4B = """    # ── DexScreener (chain-specific endpoints, first chain with pairs wins) ──
    try:
        if ca.startswith("0x"):
            dexpaths = ["ethereum", "bsc", "base", "arbitrum", "polygon",
                        "optimism", "avalanche", "linea", "zksync", "scroll",
                        "mantle", "blast", "fantom", "cronos", "gnosis",
                        "moonbeam", "celo", "pulsechain", "aptos", "sui"]
        else:
            dexpaths = ["solana", "ton", "tron"]
        # WIZCHAIN_NOV23: when the caller knows the chain (a tracked call's
        # stored chain), check it FIRST instead of defaulting to ETH-first.
        # A multi-chain token then shows its own call's chain, not ETH.
        if chain_hint:
            _hm = {"bnb": "bsc", "eth": "ethereum", "base": "base", "sol": "solana",
                   "rh": "robinhood", "ton": "ton", "arc": "arc",
                   "bsc": "bsc", "ethereum": "ethereum", "solana": "solana",
                   "robinhood": "robinhood"}
            _hs = _hm.get(str(chain_hint).lower())
            if _hs and _hs in dexpaths:
                dexpaths = [_hs] + [d for d in dexpaths if d != _hs]"""

# E5: build_drop_details_for_call — pass the call's stored chain as the hint.
OLD_E5 = """    ca = (call or {}).get("ca") or ""
    symbol = (call or {}).get("symbol") or "TOKEN"
    data = fetch_ca_data(ca)"""
NEW_E5 = """    ca = (call or {}).get("ca") or ""
    symbol = (call or {}).get("symbol") or "TOKEN"
    # WIZCHAIN_NOV23: pass the tracked call's chain so Details shows that
    # chain instead of ETH-first for a multi-chain token.
    data = fetch_ca_data(ca, chain_hint=(call or {}).get("chain"))"""

DROPPED_EDITS = [
    ("E4a fetch_ca_data chain_hint param", OLD_E4A, NEW_E4A),
    ("E4b fetch_ca_data hint goes first", OLD_E4B, NEW_E4B),
    ("E5 Details passes call chain", OLD_E5, NEW_E5),
]


def patch_file(path, edits):
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print("FAIL: %s not found" % path)
        return False
    if MARKER in src:
        print("OK: %s already has %s, skipping." % (path, MARKER))
        return True
    for name, old, new in edits:
        if src.count(old) != 1:
            print("FAIL: anchor missing/dup in %s for %s (found %dx) -- NOT writing "
                  "anything. Send the live file so the patch can be rebuilt."
                  % (path, name, src.count(old)))
            return False
    shutil.copy(path, path + ".bak_wizchain_nov23")
    print("Backup: %s.bak_wizchain_nov23" % path)
    for name, old, new in edits:
        src = src.replace(old, new, 1)
        print("OK: %s (%s)" % (name, path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return True


def main():
    args = sys.argv[1:]
    if not args:
        args = ["core.py", "dropped_call.py"]
    ok = True
    for path in args:
        edits = CORE_EDITS if path.endswith("core.py") else (
            DROPPED_EDITS if path.endswith("dropped_call.py") else None)
        if edits is None:
            print("FAIL: unknown file %s (expected core.py / dropped_call.py)" % path)
            ok = False
            continue
        if not patch_file(path, edits):
            ok = False
    if not ok:
        return 1
    print("DONE. Now restart the wizu bot (systemctl restart bot.service).")
    print("Verify on the next KOL pair-link call: dropped call + Details must")
    print("show the pair link's chain (e.g. BSC), not Base/ETH.")
    print("For the existing AI call (stored chain wrong), use /fixoldcall with")
    print("the BSC pair link to re-resolve it onto BSC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
