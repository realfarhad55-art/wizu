"""
champion_rankup_video.py - Champion Rank-Up Alert video renderer.

ORBIT design (user-approved, replaces the old per-rank themes):
every rank uses the SAME orbit video (1536x588, 30fps, 5.0s, h264,
no audio) — black deep-space background, twinkling stars, nebula,
realistic corner planets (Jupiter/Saturn/Mars/Earth/Neptune/teal),
top title "CHAMPION KOL" + #N RANK / POINTS pills, @Channel pill,
centre badge (real avatar when avatar_path is given, else the
accent ring + hexagon + first-letter fallback), 3 concentric
elliptical orbit rings, token chips revolving on the rings (the
highest-X chip is solid accent, the rest outlined), "LAST 5 ALPHA
CALLS" + "KOL PERFORMANCE" button, shooting star, shine sweep.

Only the THEME colour changes per rank:

    RANK_THEMES = {1: "yellow", 2: "green", 3: "blue",
                   4: "orange", 5: "purple"}

The renderer lives in champion_orbit_rank1.py (same directory, NEW
file — upload it to GitHub + the VPS alongside this one); this module
is a thin wrapper that keeps the exact build_rankup_video() signature
champion_rankup.py calls, so champion_rankup.py needs NO change.
The frame title is always "CHAMPION KOL" — the passed `title`
(the post title) is accepted for signature compatibility but is NOT
drawn on the frame.

CALL FILTER (defense-in-depth, STRICT >= 2.0x): the bot module
(champion_rankup.py) already selects Last-5 Alpha Calls at peak X
>= 2.0, but build_rankup_video ALSO drops any call with peak X < 2.0
before rendering - so a bad input (1.9x / 1.5x / 1.2x) can never put
a sub-2x chip on screen. Peak = max(x, current_x, highest_x) if the
row carries those fields (a call that hit 2x then fell to 1.5x still
counts); exactly 2.0x qualifies. At most 5 calls.

CHIP ORDER (same as the orbit videos): highest X takes the solid
accent chip on the outer ring, the rest fill the remaining ring slots
by X desc.

Render: champion_orbit_rank1.render_orbit_video() (per-frame PIL
composite + one ffmpeg encode, no pre-render base needed).
Cold render target < 20s.

    build_rankup_video(channel="Flokiarmywhale", rank=5, points=150,
                       calls=[{"symbol": "PEPE", "x": 10}, ...],
                       title="@Flokiarmywhale Enters the Top 5 Champions",
                       avatar_path=None, out_path="rankup.mp4")
"""
import os
import sys

# --- the orbit renderer lives next to this file (importable both on the
# VPS (/opt/bot) and standalone; no champion_video dependency) ---
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import champion_orbit_rank1 as _orbit  # noqa: E402

# Rank -> orbit theme colour (the ONLY per-rank difference now).
RANK_THEMES = {1: "yellow", 2: "green", 3: "blue", 4: "orange", 5: "purple"}


def _cap_name(name):
    """First letter capital, rest untouched (Flokiarmywhale stays as-is)."""
    name = (name or "Channel").lstrip("@")
    return name[:1].upper() + name[1:] if name else "Channel"


def _call_peak_x(call):
    """Peak X from any X field the row carries (x / current_x / highest_x).
    Mirrors champion_rankup.py _rankup_call_peak: a call that hit 2x then
    fell to 1.5x still counts on its peak."""
    best = 0.0
    for k in ("x", "current_x", "highest_x"):
        try:
            v = float(call.get(k) or 0)
        except (TypeError, ValueError):
            continue
        if v > best:
            best = v
    return best


def _filter_alpha_calls(calls):
    """STRICT >= 2.0 filter (defense-in-depth): drop any call whose peak X
    is below 2.0, so 1.9x / 1.5x / 1.2x can never appear as a chip.
    Exactly 2.0x qualifies. Returns normalized [(symbol, peak)] tuples
    (max 5, input order kept — the orbit renderer re-sorts by X desc
    for the chip slots)."""
    out = []
    for c in (calls or []):
        try:
            peak = _call_peak_x(c)
        except Exception:
            continue
        if peak < 2.0:
            continue
        out.append((str(c.get("symbol") or "TOKEN"), peak))
        if len(out) >= 5:
            break
    return out


def build_rankup_video(*, channel, rank, points, calls, title, avatar_path=None,
                       out_path, crf=12, preset="veryfast"):
    """Render the rank-up video (orbit design, per-rank theme colour).
    channel: str (no @). rank: int 1-5. points: int. calls: list of
    dicts {symbol: str, x: float} (0-5, each x>=2) - any call with peak
    X < 2.0 is dropped here too (see the module docstring: STRICT >=
    2.0 filter). title: full title string (accepted for signature
    compatibility — the frame always shows "CHAMPION KOL").
    avatar_path: optional path to a square channel avatar image.
    out_path: output .mp4 path. Returns out_path. Raises on failure."""
    name = _cap_name(channel)
    rank = int(rank)
    points = int(points)
    # STRICT >= 2.0 filter (defense-in-depth, see module docstring).
    calls = _filter_alpha_calls(calls)
    if not (1 <= rank <= 5):
        raise ValueError(f"rank must be 1-5, got {rank}")
    if points < 0:
        raise ValueError("points must be >= 0")
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)

    return _orbit.render_orbit_video(
        channel=name, rank=rank, points=points, calls=calls,
        theme=RANK_THEMES[rank], avatar_path=avatar_path,
        out_path=out_path, crf=crf, preset=preset)


def rankup_video_path_for(channel, rank, base_dir=None):
    """Output path for a rank-up video. Mirrors rocket_base_path_for style:
    one file per (channel, rank)."""
    d = base_dir or os.path.join(os.environ.get("CHAMP_VIDEO_DIR", "/tmp"),
                                 "rankup")
    os.makedirs(d, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in str(channel).lstrip("@"))
    return os.path.join(d, f"rankup-{safe}-{int(rank)}.mp4")


if __name__ == "__main__":
    import sys as _sys
    build_rankup_video(
        channel=_sys.argv[1] if len(_sys.argv) > 1 else "TestChannel",
        rank=int(_sys.argv[2]) if len(_sys.argv) > 2 else 5,
        points=int(_sys.argv[3]) if len(_sys.argv) > 3 else 150,
        calls=[{"symbol": "PEPE", "x": 10}, {"symbol": "DOGE", "x": 2},
               {"symbol": "BONK", "x": 15}, {"symbol": "WIF", "x": 12.3},
               {"symbol": "POPCAT", "x": 77}],
        title="@TestChannel Enters the Top 5 Champions",
        out_path=_sys.argv[4] if len(_sys.argv) > 4 else "rankup_test.mp4")
