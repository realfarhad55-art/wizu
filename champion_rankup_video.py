"""
champion_rankup_video.py - Champion Rank-Up Alert video renderer (1600x640, 30fps, 6s).

One renderer, one PER-RANK theme per rank (all five ranks have their own
sample video now - the theme map is COMPLETE, no fallback rank exists):

    RANK_THEMES = {
        1: purple + floating pills   (sample #1/#5 style)
        2: green  + vertical bars    (green aurora + planets, bars rise
                                      from a baseline, max-X bar gold)
        3: gold   + rising chart     (dark starry sky, gold chart line
                                      draws left->right, blue fill under
                                      the line, pills sit ON the line)
        4: orange + bottom pill row  (retro sunset: striped sun rising
                                      over a perspective grid floor,
                                      pills in a row on the grid)
        5: purple + floating pills   (same as #1)
    }

Shared across all themes (same structure as the samples): top bar with
#N RANK box / title / POINTS box counting up, @Channel pill, centre K
logo circle (real avatar when avatar_path is given, else the gold-ring
+ hexagon + first-letter fallback), "LAST 5 ALPHA CALLS" label and the
"KOL PERFORMANCE" button. Rank-box lightning is gold on every theme.

Per-theme differences (besides colours): the token display mode
("pills" / "bars" / "chart" / "row"), the background (purple nebula +
shooting stars / green aurora + planets / dark navy stars / retro sun +
grid), the button gradient, the logo position/size, and the box-border
accent colour. Add a new rank/theme later as ONE dict entry in
RANK_THEMES (plus a background + a token-layout function if the mode is
new) - nothing else needs to change.

CALL FILTER (defense-in-depth, STRICT >= 2.0x): the bot module
(champion_rankup.py) already selects Last-5 Alpha Calls at peak X >= 2.0,
but build_rankup_video ALSO drops any call with peak X < 2.0 before
rendering - so a bad input (1.9x / 1.5x / 1.2x) can never put a sub-2x
pill, bar or line point on screen. Peak = max(x, current_x, highest_x)
if the row carries those fields (a call that hit 2x then fell to 1.5x
still counts); exactly 2.0x qualifies. At most 5 calls, input order kept.

BAR HEIGHTS (#2, log scale - a 77x bar must not dwarf a 2x bar away):
    frac(x) = (ln x - ln 2) / (ln xmax - ln 2)   (xmax = biggest X listed)
    height(x) = 60 + 110 * frac(x)               (2x -> 60px, xmax -> 170px)
    If xmax <= 2 (all calls exactly 2x) frac = 1 for every bar.
    Bars rise from the baseline at y=505, so the smallest bar is always
    a clearly visible 60px and the tallest tops out at y=335.

CHART LINE (#3, same log scale for the pill heights):
    pill y(x) = 530 - (45 + 245 * frac(x))       (2x -> y=485, xmax -> y=240)
    Pills sit at evenly spaced x positions with a gap left for the
    centre logo (same as the sample, which skips the logo zone), the line
    is a Catmull-Rom smooth curve through the pill points extended to
    both frame edges, drawn left->right in sync with the points count-up;
    a blue gradient fills under the drawn part of the line.

Reuse: _font, _ffmpeg, _circle_crop, HERE and jag() are imported from
champion_video.py (final/) - never redefined here, that file is untouched.
Fonts: _font() falls back to DejaVuSans-Bold on the VPS (no Noto there).

Render: simple per-frame PIL composite + one ffmpeg encode, no pre-render
base needed for v1. Cold render target < 20s.

    build_rankup_video(channel="Flokiarmywhale", rank=5, points=150,
                       calls=[{"symbol": "PEPE", "x": 10}, ...],
                       title="@Flokiarmywhale Enters the Top 5 Champions",
                       avatar_path=None, out_path="rankup.mp4")
"""
import math
import os
import random
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# --- reuse the champion helpers (do NOT redefine, do NOT edit that file) ---
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (os.path.join(_HERE, "..", "final"),
              os.path.join(_HERE, "..", "speedwork", "vps"),
              os.environ.get("CHAMP_VIDEO_DIR", "")):
    if _cand and os.path.exists(os.path.join(_cand, "champion_video.py")):
        if _cand not in sys.path:
            sys.path.insert(0, os.path.abspath(_cand))
        break
from champion_video import _font, _ffmpeg, _circle_crop, HERE, jag  # noqa: E402

W, H, FPS = 1600, 640, 30
DUR = 6.0
N_FRAMES = int(DUR * FPS)

# Safe zone: Telegram phone preview crops ~6% of each side.
SAFE_X0, SAFE_X1 = 96, 1504
SAFE_Y0, SAFE_Y1 = 38, 602

GOLD = (255, 190, 0)
YELLOW = (255, 210, 0)
WHITE = (255, 255, 255)
PURPLE = (168, 85, 247)
PURPLE_DK = (120, 50, 200)
GREEN = (34, 197, 94)
GREEN_DK = (10, 60, 30)
GREEN_LT = (74, 222, 128)
ORANGE = (255, 140, 0)
ORANGE_LT = (255, 190, 60)
GRAY = (170, 170, 180)

# ---------------------------------------------------------------------------
# Per-rank themes. mode: "pills" | "bars" | "chart" | "row".
# accent = box borders / token borders / glows; ring = centre-logo ring
# gradient (gold -> accent); button = KOL PERFORMANCE button style;
# bg = background builder; meteors = shooting stars (pills theme only,
# the others have stars baked into their background); logo_cy/logo_ring
# = centre logo position/size (bars + sunset sit the logo higher/smaller
# so the bars / the sun sit right, like their samples).
# ---------------------------------------------------------------------------
RANK_THEMES = {
    1: {"mode": "pills", "accent": PURPLE, "accent_dk": PURPLE_DK,
        "accent_lt": (190, 130, 255), "bg": "purple", "ring": (GOLD, PURPLE),
        "button": "gradient", "meteors": True, "logo_cy": 350,
        "logo_ring": 280},
    2: {"mode": "bars", "accent": GREEN, "accent_dk": GREEN_DK,
        "accent_lt": GREEN_LT, "bg": "aurora", "ring": (GOLD, GREEN),
        "button": "gold", "meteors": False, "logo_cy": 272,
        "logo_ring": 220},
    3: {"mode": "chart", "accent": GOLD, "accent_dk": (176, 128, 0),
        "accent_lt": (255, 220, 80), "bg": "navy", "ring": (GOLD, GOLD),
        "button": "gold", "meteors": False, "logo_cy": 350,
        "logo_ring": 280},
    4: {"mode": "row", "accent": ORANGE, "accent_dk": (160, 70, 0),
        "accent_lt": ORANGE_LT, "bg": "sunset", "ring": (GOLD, ORANGE),
        "button": "orange", "meteors": False, "logo_cy": 280,
        "logo_ring": 240},
    5: {"mode": "pills", "accent": PURPLE, "accent_dk": PURPLE_DK,
        "accent_lt": (190, 130, 255), "bg": "purple", "ring": (GOLD, PURPLE),
        "button": "gradient", "meteors": True, "logo_cy": 350,
        "logo_ring": 280},
}


def _fmt_x(x):
    """10 -> '10x', 12.3 -> '12.3x', 2.5 -> '2.5x'."""
    v = float(x)
    return f"{v:g}x"


def _cap_name(name):
    """First letter capital, rest untouched (Flokiarmywhale stays as-is)."""
    name = (name or "Channel").lstrip("@")
    return name[:1].upper() + name[1:] if name else "Channel"


def _ease_out(u):
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** 2


def _ease_out_back(u):
    u = min(1.0, max(0.0, u))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2


def _smoothstep(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


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
    is below 2.0, so 1.9x / 1.5x / 1.2x can never appear as a pill, bar or
    line point. Exactly 2.0x qualifies. Returns normalized
    [{"symbol": str, "x": peak}] (max 5, input order kept)."""
    out = []
    for c in (calls or []):
        try:
            peak = _call_peak_x(c)
        except Exception:
            continue
        if peak < 2.0:
            continue
        out.append({"symbol": str(c.get("symbol") or "TOKEN"), "x": peak})
        if len(out) >= 5:
            break
    return out


def _log_frac(x, xmax):
    """Log-scale fraction 0..1 of x between 2 and xmax (see module docstring
    for the bar/chart formulas). xmax <= 2 -> every bar gets frac 1."""
    if xmax <= 2.0:
        return 1.0
    return (math.log(max(2.0, float(x))) - math.log(2.0)) / \
        (math.log(float(xmax)) - math.log(2.0))


def _fit_title(title, max_w, start=56, minimum=40):
    """One line if it fits (shrink start -> minimum), else two lines max."""
    title = (title or "").strip().upper()
    words = title.split()
    for size in range(start, minimum - 1, -2):
        f = _font(size)
        if f.getlength(title) <= max_w:
            return [(title, f)], size
    # Two lines: balanced split (minimise the wider line) at the minimum
    # size, then shrink if the pair still does not fit.
    for size in range(minimum, 27, -2):
        f = _font(size)
        widths = [f.getlength(w) for w in words]
        space = f.getlength(" ")
        best, best_w = None, None
        for k in range(1, len(words)):
            w0 = sum(widths[:k]) + space * (k - 1)
            w1 = sum(widths[k:]) + space * (len(words) - k - 1)
            m = max(w0, w1)
            if best_w is None or m < best_w:
                best, best_w = k, m
        if best is not None and best_w <= max_w:
            return [(" ".join(words[:best]), f), (" ".join(words[best:]), f)], size
    f = _font(28)
    return [(title, f)], 28


def _gradient_button(w, h, stops=None):
    """Horizontal gradient, rounded, RGBA. Default stops = the purple
    theme's orange -> pink -> purple; gold/orange themes pass their own."""
    if stops is None:
        stops = [(255, 140, 40), (255, 70, 150), (168, 85, 247)]
    x = np.linspace(0, 1, w, dtype=np.float32)
    arr = np.zeros((h, w, 3), np.float32)
    for i in range(3):
        c0 = np.array(stops[0][i], np.float32)
        c1 = np.array(stops[1][i], np.float32)
        c2 = np.array(stops[2][i], np.float32)
        col = np.where(x < 0.5, c0 + (c1 - c0) * (x / 0.5),
                       c1 + (c2 - c1) * ((x - 0.5) / 0.5))
        arr[:, :, i] = col[None, :]
    img = Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=255)
    img.putalpha(mask)
    return img


def _ring_image(d, c0=GOLD, c1=PURPLE):
    """Gradient ring (angle-blended c0 -> c1), transparent centre."""
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32)
    cx = cy = d / 2.0
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    ang = (np.arctan2(yy - cy, xx - cx) / (2 * math.pi) + 0.5)  # 0..1 round
    ring = (r >= d * 0.36) & (r <= d * 0.44)
    col0 = np.array(c0, np.float32)
    col1 = np.array(c1, np.float32)
    t = np.clip(ang * 1.6, 0, 1)[..., None]
    col = col0 * (1 - t) + col1 * t
    out = np.zeros((d, d, 4), np.uint8)
    out[..., :3] = np.clip(col, 0, 255).astype(np.uint8)
    out[..., 3] = np.where(ring, 255, 0).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _hexagon_points(cx, cy, r):
    return [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
             cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]


# ---------------------------------------------------------------------------
# Backgrounds (one per theme; built once, returned as an RGB numpy array).
# ---------------------------------------------------------------------------
def _add_stars(img, seed, n, tint=(255, 255, 255)):
    """Static twinkling-free stars baked into an RGBA base image."""
    rng = random.Random(seed)
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(0.6, 1.8)
        d.ellipse((x - r, y - r, x + r, y + r),
                  fill=tint + (rng.randint(90, 220),))
    return img


def _build_background_purple():
    """Static dark purple/black background + centre radial glow + vignette."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    # vertical falloff: deep purple top, near-black bottom
    base += np.array((14, 5, 28), np.float32) * (1 - yy / H * 0.55)[..., None]
    # radial glow behind the centre logo
    glow = np.exp(-(((xx - 800) / 430) ** 2 + ((yy - 350) / 300) ** 2))
    base += np.array((88, 30, 150), np.float32) * (glow * 0.55)[..., None]
    wide = np.exp(-(((xx - 800) / 900) ** 2 + ((yy - 320) / 500) ** 2))
    base += np.array((40, 14, 80), np.float32) * (wide * 0.5)[..., None]
    # vignette
    vig = 1 - 0.45 * (((xx - 800) / 950) ** 2 + ((yy - 320) / 520) ** 2)
    base *= np.clip(vig, 0.45, 1)[..., None]
    return np.clip(base, 0, 255).astype(np.uint8)


def _planet(img, cx, cy, r, base_col, stripe_col=None, ring=False):
    """Small planet disc (optional stripes / flat ring), pasted on img."""
    s = r * 2
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((0, 0, s - 1, s - 1), fill=base_col + (255,))
    if stripe_col is not None:
        stripes = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        sd = ImageDraw.Draw(stripes)
        for y0, y1 in ((0.22, 0.32), (0.45, 0.56), (0.68, 0.78)):
            sd.rectangle((0, s * y0, s, s * y1), fill=stripe_col + (255,))
        layer = Image.alpha_composite(layer, stripes)
        # clip stripes back to the disc
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, s - 1, s - 1), fill=255)
        arr = np.array(layer)
        arr[..., 3] = np.minimum(arr[..., 3], np.asarray(mask))
        layer = Image.fromarray(arr, "RGBA")
    if ring:
        ring_layer = Image.new("RGBA", (s * 3, s * 3), (0, 0, 0, 0))
        rd = ImageDraw.Draw(ring_layer)
        rd.ellipse((s * 3 // 2 - r * 2, s * 3 // 2 - int(r * 0.55),
                    s * 3 // 2 + r * 2, s * 3 // 2 + int(r * 0.55)),
                   outline=(215, 225, 200, 220), width=3)
        img.paste(ring_layer, (cx - s * 3 // 2, cy - s * 3 // 2), ring_layer)
    img.paste(layer, (cx - r, cy - r), layer)
    return img


def _build_background_aurora():
    """Green aurora: dark green-black + two wavy glowing bands + planets."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    base += np.array((3, 9, 6), np.float32) * (1 - yy / H * 0.4)[..., None]
    # wavy horizontal aurora bands (bright green, soft falloff)
    for yc, amp, per, ph, col, strength in (
            (170, 38, 420, 0.0, (0, 150, 80), 0.85),
            (265, 55, 300, 1.7, (0, 110, 70), 0.6)):
        ycen = yc + amp * np.sin(xx / per * 2 * math.pi + ph)
        band = np.exp(-((yy - ycen) / 55) ** 2)
        base += np.array(col, np.float32) * (band * strength)[..., None]
    glow = np.exp(-(((xx - 800) / 430) ** 2 + ((yy - 272) / 300) ** 2))
    base += np.array((20, 90, 45), np.float32) * (glow * 0.5)[..., None]
    vig = 1 - 0.4 * (((xx - 800) / 950) ** 2 + ((yy - 320) / 520) ** 2)
    base *= np.clip(vig, 0.5, 1)[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8),
                          "RGB").convert("RGBA")
    _add_stars(img, seed=7, n=90)
    # planets, like the #2 sample: striped left, ringed right, small blue
    # bottom-right, small pale moon bottom-left.
    _planet(img, 150, 215, 26, (205, 225, 195), stripe_col=(150, 170, 150))
    _planet(img, 1435, 180, 20, (200, 210, 190), ring=True)
    _planet(img, 1470, 470, 13, (100, 150, 230))
    _planet(img, 95, 480, 9, (190, 205, 215))
    return np.asarray(img.convert("RGB"), np.uint8)


def _build_background_navy():
    """Gold/chart theme: very dark navy starry sky, slight top glow."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    base += np.array((6, 10, 26), np.float32) * (1 - yy / H * 0.35)[..., None]
    base += np.array((3, 5, 14), np.float32) * (yy / H * 0.35)[..., None]
    wide = np.exp(-(((xx - 800) / 900) ** 2 + ((yy - 200) / 500) ** 2))
    base += np.array((12, 20, 55), np.float32) * (wide * 0.5)[..., None]
    vig = 1 - 0.4 * (((xx - 800) / 950) ** 2 + ((yy - 320) / 520) ** 2)
    base *= np.clip(vig, 0.5, 1)[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8),
                          "RGB").convert("RGBA")
    _add_stars(img, seed=5, n=150)
    return np.asarray(img.convert("RGB"), np.uint8)


def _build_background_sunset():
    """Orange/retro theme: near-black starry sky + faint warm horizon glow.
    The sun, arcs and grid floor are drawn per frame (the sun rises)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    base += np.array((3, 2, 5), np.float32)
    glow = np.exp(-(((xx - 800) / 700) ** 2 + ((yy - 390) / 260) ** 2))
    base += np.array((50, 18, 0), np.float32) * (glow * 0.5)[..., None]
    vig = 1 - 0.35 * (((xx - 800) / 950) ** 2 + ((yy - 320) / 520) ** 2)
    base *= np.clip(vig, 0.55, 1)[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8),
                          "RGB").convert("RGBA")
    _add_stars(img, seed=9, n=110)
    return np.asarray(img.convert("RGB"), np.uint8)


_BG_BUILDERS = {"purple": _build_background_purple,
                "aurora": _build_background_aurora,
                "navy": _build_background_navy,
                "sunset": _build_background_sunset}


def _make_meteors(seed=11, n=26):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        out.append(dict(
            x=rng.uniform(-100, W + 300), y=rng.uniform(-50, H + 100),
            # drift down-left, heads leading (sample streaks run up-right)
            vx=rng.uniform(-260, -140), vy=rng.uniform(55, 130),
            ln=rng.uniform(70, 190), w=rng.uniform(1.2, 2.4),
            tw=rng.uniform(0.6, 2.0), tp=rng.uniform(0, 6.28),
            bright=rng.uniform(0.55, 1.0)))
    return out


# ---------------------------------------------------------------------------
# Token layouts. Each returns (call, position, is_highlight) tuples.
# ---------------------------------------------------------------------------
# Pill slot centres (sample layout): 0 left-mid, 1 bottom-left,
# 2 bottom-right, 3 right-mid, 4 top-right (highlight slot).
_PILL_SLOTS = [(250, 335), (400, 478), (1200, 478), (1350, 335), (1340, 205)]
# Balanced subsets when fewer than 5 calls (keeps the frame symmetric).
_PILL_SUBSETS = {5: [0, 1, 2, 3, 4], 4: [0, 1, 2, 3], 3: [0, 3, 2],
                 2: [0, 3], 1: [0], 0: []}


def _pill_layout(calls):
    """(call, centre, is_highlight) per pill, highlight = biggest X."""
    calls = list(calls or [])[:5]
    if not calls:
        return []
    slots = _PILL_SUBSETS[len(calls)]
    hi = max(range(len(calls)), key=lambda i: float(calls[i].get("x", 0)))
    return [(calls[i], _PILL_SLOTS[slots[i]], i == hi) for i in range(len(calls))]


# #2 bars: x centres (sample positions, scaled to 1600px), baseline y=505.
_BAR_SLOTS = [333, 531, 677, 823, 1062]
_BAR_BASELINE = 505
_BAR_W = 130
_BAR_H_MIN, _BAR_H_MAX = 60, 170
# Centre slots (677, 823) sit under the logo (bottom y=382): a bar there
# taller than 120px would draw over the logo, so centre bars are capped
# at 120 (top y=385). 2-call uses the two outer slots for the same reason.
_BAR_SUBSETS = {5: [0, 1, 2, 3, 4], 4: [0, 1, 3, 4], 3: [0, 2, 4],
                2: [0, 4], 1: [2], 0: []}
_BAR_CENTRE_CAP = 120


def _bar_layout(calls):
    """(call, centre_x, full_height, is_highlight) per bar."""
    calls = list(calls or [])[:5]
    if not calls:
        return []
    slots = _BAR_SUBSETS[len(calls)]
    xmax = max(float(c.get("x", 2)) for c in calls)
    hi = max(range(len(calls)), key=lambda i: float(calls[i].get("x", 0)))
    out = []
    for i, c in enumerate(calls):
        frac = _log_frac(c.get("x", 2), xmax)
        h = _BAR_H_MIN + (_BAR_H_MAX - _BAR_H_MIN) * frac
        if _BAR_SLOTS[slots[i]] in (677, 823):
            h = min(h, _BAR_CENTRE_CAP)
        out.append((c, _BAR_SLOTS[slots[i]], int(round(h)), i == hi))
    return out


# #3 chart: pill x slots - evenly spaced with a gap for the centre logo
# (the sample skips the logo zone the same way). y from the log scale.
_CHART_SLOTS = [180, 420, 1000, 1180, 1410]
_CHART_SUBSETS = {5: [0, 1, 2, 3, 4], 4: [0, 1, 3, 4], 3: [0, 2, 4],
                  2: [1, 3], 1: [2], 0: []}
_CHART_Y_BASE, _CHART_Y_MIN, _CHART_Y_MAX = 530, 45, 290


def _chart_layout(calls):
    """(call, anchor_x, anchor_y, is_highlight) per chart pill."""
    calls = list(calls or [])[:5]
    if not calls:
        return []
    slots = _CHART_SUBSETS[len(calls)]
    xmax = max(float(c.get("x", 2)) for c in calls)
    hi = max(range(len(calls)), key=lambda i: float(calls[i].get("x", 0)))
    out = []
    for i, c in enumerate(calls):
        frac = _log_frac(c.get("x", 2), xmax)
        y = _CHART_Y_BASE - (_CHART_Y_MIN +
                             (_CHART_Y_MAX - _CHART_Y_MIN) * frac)
        out.append((c, _CHART_SLOTS[slots[i]], int(round(y)), i == hi))
    return out


# #4 row: pill centres along the bottom, on the grid floor (y=476, so the
# pills clear the "LAST 5 ALPHA CALLS" label at y=528).
_ROW_SLOTS = [375, 615, 844, 1083, 1323]
_ROW_Y = 476
_ROW_SUBSETS = {5: [0, 1, 2, 3, 4], 4: [0, 1, 3, 4], 3: [0, 2, 4],
                2: [1, 3], 1: [2], 0: []}


def _row_layout(calls):
    """(call, centre, is_highlight) per row pill, highlight = biggest X."""
    calls = list(calls or [])[:5]
    if not calls:
        return []
    slots = _ROW_SUBSETS[len(calls)]
    hi = max(range(len(calls)), key=lambda i: float(calls[i].get("x", 0)))
    return [(calls[i], (_ROW_SLOTS[slots[i]], _ROW_Y), i == hi)
            for i in range(len(calls))]


def _pill_image(symbol, xval, highlight, accent=PURPLE):
    """One token pill as a full-size RGBA image (pasted scaled for pop-in,
    so the text scales with the pill instead of spilling out of it).
    Normal: dark fill + accent border, white symbol, yellow X.
    Highlight (biggest X): solid yellow fill, dark text."""
    sym = str(symbol or "TOKEN").lstrip("$").upper()
    f_sym = _font(26)
    f_x = _font(38)
    w_sym = f_sym.getlength(sym)
    w_x = f_x.getlength(_fmt_x(xval))
    gap, pad_x, h = 14, 26, 64
    w = int(pad_x * 2 + w_sym + gap + w_x)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if highlight:
        fill, border = YELLOW, YELLOW
        c_sym, c_x = (20, 20, 20), (20, 20, 20)
    else:
        fill, border = (16, 8, 30), accent
        c_sym, c_x = (235, 235, 240), YELLOW
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=fill + (255,),
                        outline=border + (255,), width=3)
    total = w_sym + gap + w_x
    tx = (w - total) / 2
    d.text((tx, h // 2 - 2), sym, font=f_sym, fill=c_sym + (255,), anchor="lm")
    d.text((tx + w_sym + gap, h // 2 - 2), _fmt_x(xval), font=f_x,
           fill=c_x + (255,), anchor="lm")
    return img


def _chart_pill_image(symbol, xval, highlight):
    """Small pill that sits ON the chart line (#3): dark fill + gold border
    (white symbol, gold X); highlight (biggest X) = solid gold, dark text,
    slightly bigger - like the sample's 77x pill."""
    sym = str(symbol or "TOKEN").lstrip("$").upper()
    h = 56 if highlight else 52
    f_sym = _font(20)
    f_x = _font(34 if highlight else 30)
    w_sym = f_sym.getlength(sym)
    w_x = f_x.getlength(_fmt_x(xval))
    gap, pad_x = 10, 20
    w = int(pad_x * 2 + w_sym + gap + w_x)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if highlight:
        fill, border = GOLD, GOLD
        c_sym, c_x = (20, 20, 20), (20, 20, 20)
    else:
        fill, border = (10, 10, 18), GOLD
        c_sym, c_x = (235, 235, 240), GOLD
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=fill + (255,),
                        outline=border + (255,), width=3)
    total = w_sym + gap + w_x
    tx = (w - total) / 2
    d.text((tx, h // 2 - 2), sym, font=f_sym, fill=c_sym + (255,), anchor="lm")
    d.text((tx + w_sym + gap, h // 2 - 2), _fmt_x(xval), font=f_x,
           fill=c_x + (255,), anchor="lm")
    return img


def _bar_image(highlight):
    """One vertical bar at full height (130x170), vertical gradient.
    Green gradient for normal bars, gold gradient for the max-X bar.
    Resized per frame as the bar grows, so the gradient stays relative."""
    w, h = _BAR_W, _BAR_H_MAX
    if highlight:
        top, bot = (255, 220, 60), (190, 130, 0)
    else:
        top, bot = (90, 230, 140), (8, 60, 25)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    top_a = np.array(top, np.float32)
    bot_a = np.array(bot, np.float32)
    arr = (top_a * (1 - yy) + bot_a * yy).astype(np.uint8)
    arr = np.repeat(arr, w, axis=1)
    img = Image.fromarray(arr, "RGB").convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=12,
                                           fill=255)
    img.putalpha(mask)
    return img


def _catmull_rom(pts, samples_per_seg=60):
    """Smooth curve through pts (Catmull-Rom), dense (x, y) list."""
    if len(pts) < 2:
        return list(pts)
    ext = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(len(ext) - 3):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for j in range(samples_per_seg):
            u = j / samples_per_seg
            u2, u3 = u * u, u * u * u
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * u +
                       (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * u2 +
                       (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * u3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * u +
                       (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * u2 +
                       (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * u3)
            out.append((x, y))
    out.append(pts[-1])
    return out


def _chart_fill_image(line_pts):
    """Blue gradient fill under the full chart line (RGBA, W x H):
    strongest right under the line, fading to nothing ~380px below it."""
    xs = np.array([p[0] for p in line_pts], np.float32)
    ys = np.array([p[1] for p in line_pts], np.float32)
    cols = np.arange(W, dtype=np.float32)
    line_y = np.interp(cols, xs, ys)  # line height per column
    yy = np.arange(H, dtype=np.float32)[:, None]
    dist = np.clip((yy - line_y[None, :]) / 380.0, 0, 1)
    below = yy > line_y[None, :]
    alpha = np.where(below, 185 * (1 - dist), 0)
    top_c = np.array((35, 105, 225), np.float32)
    bot_c = np.array((10, 18, 55), np.float32)
    col = top_c * (1 - dist)[..., None] + bot_c * dist[..., None]
    out = np.zeros((H, W, 4), np.uint8)
    out[..., :3] = np.clip(col, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _sun_image(size=600):
    """Retro sun disc at full size: yellow->orange vertical gradient with
    horizontal dark stripes across the lower half (they get thicker
    toward the bottom, like the #4 sample). Circular alpha."""
    r = size // 2
    yy = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
    top_c = np.array((255, 225, 0), np.float32)
    bot_c = np.array((255, 130, 0), np.float32)
    arr = (top_c * (1 - yy) + bot_c * yy).astype(np.uint8)
    arr = np.repeat(arr, size, axis=1)
    img = Image.fromarray(arr, "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)
    # stripes: (centre_y as fraction of radius, thickness)
    for yf, th in ((0.55, 5), (0.68, 7), (0.80, 10), (0.92, 14)):
        y = int(r + r * yf)
        d.rectangle((0, y - th // 2, size, y + th // 2), fill=(0, 0, 0, 255))
    # circular mask
    yy2, xx2 = np.mgrid[0:size, 0:size].astype(np.float32)
    disc = ((xx2 - r) ** 2 + (yy2 - r) ** 2) <= r * r
    a = np.array(img)
    a[..., 3] = np.where(disc, a[..., 3], 0).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


# Sunset geometry (#4 sample): horizon at y=390, sun centre on the horizon.
_SUN_HORIZON = 390
_SUN_R_MAX = 300


def build_rankup_video(*, channel, rank, points, calls, title, avatar_path=None,
                       out_path, crf=12, preset="veryfast"):
    """Render the rank-up video. channel: str (no @). rank: int 1-5.
    points: int. calls: list of dicts {symbol: str, x: float} (0-5, each
    x>=2) - any call with peak X < 2.0 is dropped here too (see the module
    docstring: STRICT >= 2.0 filter). title: full title string (already
    includes @Channel). avatar_path: optional path to a square channel
    avatar image. out_path: output .mp4 path. Returns out_path. Raises
    on failure."""
    name = _cap_name(channel)
    rank = int(rank)
    points = int(points)
    # STRICT >= 2.0 filter (defense-in-depth, see module docstring).
    calls = _filter_alpha_calls(calls)
    title = str(title or f"@{name} Rank Up")
    if not (1 <= rank <= 5):
        raise ValueError(f"rank must be 1-5, got {rank}")
    if points < 0:
        raise ValueError("points must be >= 0")
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)

    theme = RANK_THEMES.get(rank, RANK_THEMES[5])  # map is complete 1-5
    mode = theme["mode"]
    accent = theme["accent"]
    accent_lt = theme["accent_lt"]
    ring_c0, ring_c1 = theme["ring"]
    logo_cy = theme["logo_cy"]
    logo_ring = theme["logo_ring"]
    ccx = 800

    # ---- static pieces (built once) ----
    base = _BG_BUILDERS[theme["bg"]]()
    ring_img = _ring_image(logo_ring, ring_c0, ring_c1)
    if theme["button"] == "gold":
        button = _gradient_button(340, 50, stops=[(255, 200, 0),
                                                  (255, 210, 30),
                                                  (255, 200, 0)])
    elif theme["button"] == "orange":
        button = _gradient_button(340, 50, stops=[(255, 140, 0),
                                                  (255, 175, 25),
                                                  (255, 205, 60)])
    else:
        button = _gradient_button(340, 50)
    meteors = _make_meteors() if theme["meteors"] else []

    # token display plan for this theme's mode
    pill_plan = bar_plan = chart_plan = row_plan = []
    pill_imgs = chart_pill_imgs = {}
    bar_img_n = bar_img_h = None
    line_pts = fill_img = None
    if mode == "pills":
        pill_plan = _pill_layout(calls)
        pill_imgs = {(str(c.get("symbol")).upper(), float(c.get("x", 2)), hi):
                     _pill_image(c.get("symbol"), c.get("x", 2), hi, accent)
                     for c, _, hi in pill_plan}
    elif mode == "row":
        row_plan = _row_layout(calls)
        pill_imgs = {(str(c.get("symbol")).upper(), float(c.get("x", 2)), hi):
                     _pill_image(c.get("symbol"), c.get("x", 2), hi, accent)
                     for c, _, hi in row_plan}
    elif mode == "bars":
        bar_plan = _bar_layout(calls)
        bar_img_n = _bar_image(highlight=False)
        bar_img_h = _bar_image(highlight=True)
    elif mode == "chart":
        chart_plan = _chart_layout(calls)
        chart_pill_imgs = {(str(c.get("symbol")).upper(), float(c.get("x", 2)), hi):
                           _chart_pill_image(c.get("symbol"), c.get("x", 2), hi)
                           for c, _, _, hi in chart_plan}
        if chart_plan:
            anchors = [(ax, ay) for _, ax, ay, _ in chart_plan]
            # line runs edge to edge through the pill anchors
            ctrl = [(0, min(555, max(190, anchors[0][1] + 25)))] + anchors + \
                   [(W, min(555, max(190, anchors[-1][1] - 25)))]
            line_pts = _catmull_rom(ctrl)
            fill_img = _chart_fill_image(line_pts)

    # retro sun (#4): full-size disc + soft glow, resized per frame as it
    # rises (stripes + gradient scale with it, like the sample).
    sun_img = sun_glow = None
    if mode == "row":
        sun_img = _sun_image(2 * _SUN_R_MAX)
        sun_glow = sun_img.filter(ImageFilter.GaussianBlur(24))

    # bars baseline glow (#2): blurred once, alpha-scaled per frame
    # (a full-frame GaussianBlur every frame cost ~7s per render).
    baseline_glow = None
    if mode == "bars":
        _bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(_bl).line(
            (180, _BAR_BASELINE, 1420, _BAR_BASELINE),
            fill=(74, 222, 128, 255), width=4)
        baseline_glow = _bl.filter(ImageFilter.GaussianBlur(4))

    title_lines, _tsize = _fit_title(title, max_w=980)
    two_line = len(title_lines) > 1

    # centre avatar (real photo) or fallback hexagon + first letter
    avatar = None
    if avatar_path and os.path.exists(avatar_path):
        try:
            avatar = _circle_crop(Image.open(avatar_path),
                                  int(logo_ring * 0.63))
        except Exception:
            avatar = None

    # top-bar geometry (widened so "150 POINTS" / "388 POINTS" fit inside)
    rank_box = (100, 52, 300, 118)      # x0, y0, x1, y1
    pts_box = (1290, 52, 1500, 118)
    pill_y0, pill_y1 = (140, 182) if two_line else (134, 176)
    title_cy = 88 if not two_line else 85
    f_rank_num = _font(54)
    f_rank_lab = _font(24)
    # points number+label: shrink until they fit the box with padding
    for _ns in (48, 44, 40, 36):
        _ls = max(18, _ns - 26)
        if 16 + _font(_ns).getlength(str(points)) + 10 + \
                _font(_ls).getlength("POINTS") + 8 <= pts_box[2] - pts_box[0]:
            break
    f_pts_num, f_pts_lab = _font(_ns), _font(_ls)
    f_chan = _font(30)
    f_label = _font(26)
    f_btn = _font(26)
    f_fallback = _font(max(28, int(92 * logo_ring / 280)))
    f_bar_sym = _font(20)

    chan_text = f"@{name}"
    chan_w = f_chan.getlength(chan_text) + 56

    # logo geometry scales with the theme's ring size
    disc_r = int(logo_ring * 0.33)
    hex_r = int(logo_ring * 0.22)
    av_size = int(logo_ring * 0.63)
    ring_r0 = int(logo_ring * 0.46)
    ring_r1 = int(170 * logo_ring / 280)

    def frame_at(i):
        t = i / FPS
        img = Image.fromarray(base, "RGB").convert("RGBA")
        d = ImageDraw.Draw(img)
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)

        # ---- shooting stars (pills theme only; other themes have stars
        # baked into their background) ----
        span_x, span_y = W + 500, H + 300
        for m in meteors:
            hx = (m["x"] + m["vx"] * t) % span_x - 250
            hy = (m["y"] + m["vy"] * t) % span_y - 150
            ux, uy = -m["vx"], -m["vy"]
            ul = math.hypot(ux, uy)
            ux, uy = ux / ul, uy / ul
            tx_, ty_ = hx + ux * m["ln"], hy + uy * m["ln"]
            tw = 0.55 + 0.45 * math.sin(m["tp"] + m["tw"] * t)
            a = int(200 * m["bright"] * tw)
            # tail: purple, fading away from the head
            for s in range(6):
                u0, u1 = s / 6, (s + 1) / 6
                gd.line((hx + ux * m["ln"] * u0, hy + uy * m["ln"] * u0,
                         hx + ux * m["ln"] * u1, hy + uy * m["ln"] * u1),
                        fill=(150, 80, 255, int(a * (0.12 + 0.5 * u0))), width=3)
            gd.line((hx, hy, tx_, ty_), fill=(255, 255, 255, a), width=max(1, int(m["w"])))
            gd.ellipse((hx - 4, hy - 4, hx + 4, hy + 4), fill=(255, 255, 255, a))
            gd.ellipse((hx - 8, hy - 8, hx + 8, hy + 8), outline=(190, 140, 255, int(a * 0.5)), width=2)

        # ---- retro sunset scene (#4): rising striped sun, concentric arcs,
        # perspective grid floor (drawn before the logo / pills) ----
        if mode == "row":
            horizon = _SUN_HORIZON
            sun_u = _ease_out(min(1.0, t / 2.2))
            R = int(_SUN_R_MAX * (0.45 + 0.55 * sun_u))
            # concentric arcs around the sun (upper halves only)
            arc_fade = _ease_out(min(1.0, t / 1.0))
            for rr, al in ((350, 70), (415, 55), (480, 40)):
                gd.arc((ccx - rr, horizon - rr, ccx + rr, horizon + rr),
                       180, 360, fill=(255, 140, 0, int(al * arc_fade)), width=3)
            # sun glow + disc (clipped to above the horizon)
            for src, alpha_mul in ((sun_glow, 0.45), (sun_img, 1.0)):
                s_r = src.resize((2 * R, 2 * R), Image.LANCZOS)
                arr = np.asarray(s_r).copy()
                arr[R:, :, 3] = 0  # rows below the horizon stay invisible
                if alpha_mul < 1.0:
                    arr[..., 3] = (arr[..., 3].astype(np.float32) *
                                   alpha_mul).astype(np.uint8)
                s_r = Image.fromarray(arr, "RGBA")
                img.paste(s_r, (ccx - R, horizon - R), s_r)
            # grid floor: radial lines from the vanishing point + horizontal
            # lines with perspective spacing, fading in with the sun
            grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gdd = ImageDraw.Draw(grid)
            gf = 0.3 + 0.7 * _ease_out(min(1.0, t / 1.2))
            for xb in range(-600, 2201, 120):
                gdd.line((ccx, horizon, xb, H),
                         fill=(255, 120, 0, int(110 * gf)), width=2)
            for k in range(1, 9):
                yk = horizon + 250 * (k / 8) ** 2.2
                gdd.line((0, yk, W, yk),
                         fill=(255, 120, 0, int((50 + 15 * k) * gf)), width=2)
            gdd.line((0, horizon, W, horizon),
                     fill=(255, 180, 0, int(255 * gf)), width=4)
            img = Image.alpha_composite(img, grid)
            d = ImageDraw.Draw(img)  # alpha_composite returns a new image

        # ---- chart line + fill (#3): draws left->right with the count-up;
        # pills pop in as the line head reaches them ----
        line_u = _smoothstep((t - 0.6) / 3.9) if mode == "chart" else 0.0
        head_x = line_u * W
        if mode == "chart" and line_pts and fill_img is not None:
            hx = int(head_x)
            if hx > 0:
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                main_x = max(0, hx - 90)
                if main_x > 0:
                    part = fill_img.crop((0, 0, main_x, H))
                    layer.paste(part, (0, 0), part)
                if hx > main_x:
                    edge = fill_img.crop((main_x, 0, hx, H))
                    arr = np.asarray(edge).astype(np.float32)
                    ramp = np.linspace(0, 1, hx - main_x,
                                       dtype=np.float32)[None, :]
                    arr[..., 3] *= ramp
                    edge2 = Image.fromarray(
                        np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
                    layer.paste(edge2, (main_x, 0), edge2)
                img = Image.alpha_composite(img, layer)
                d = ImageDraw.Draw(img)  # alpha_composite returns a new image
            # The line lives on its OWN layer composited onto the frame
            # BEFORE the logo (not on the glow layer): the sample hides the
            # line behind the centre K circle, and the glow layer is
            # composited over everything at the end, which would draw the
            # line across the logo.
            ll = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ld = ImageDraw.Draw(ll)
            # the line itself (gold, wide soft halo + bright core)
            vis = [p for p in line_pts if p[0] <= head_x]
            if len(vis) >= 2:
                vis = vis + [(head_x, np.interp(
                    head_x, [p[0] for p in line_pts],
                    [p[1] for p in line_pts]))]
                ld.line(vis, fill=(255, 200, 0, 90), width=11, joint="curve")
                ld.line(vis, fill=(255, 220, 60, 255), width=4, joint="curve")
                # glowing head dot
                hy = float(np.interp(head_x, [p[0] for p in line_pts],
                                     [p[1] for p in line_pts]))
                ld.ellipse((head_x - 7, hy - 7, head_x + 7, hy + 7),
                           fill=(255, 255, 255, 255))
                ld.ellipse((head_x - 12, hy - 12, head_x + 12, hy + 12),
                           outline=(255, 200, 0, 200), width=3)
            # anchor dots on the line (appear as the head passes them)
            for c, ax, ay, hi in chart_plan:
                if head_x >= ax - 5:
                    ld.ellipse((ax - 7, ay - 7, ax + 7, ay + 7),
                               fill=(255, 200, 0, 255))
                    ld.ellipse((ax - 11, ay - 11, ax + 11, ay + 11),
                               outline=(255, 200, 0, 160), width=2)
            img = Image.alpha_composite(img, ll)
            d = ImageDraw.Draw(img)  # alpha_composite returns a new image

        # ---- centre: expanding rings (mid-animation pulse), theme colours ----
        if 1.2 <= t <= 5.6:
            for k, col in enumerate((GOLD, accent, GOLD)):
                ph = ((t - 1.2 - k * 0.7) % 2.1) / 2.1
                r = ring_r0 + ph * ring_r1
                al = int(200 * (1 - ph) * (1 - ph))
                gd.ellipse((ccx - r, logo_cy - r, ccx + r, logo_cy + r),
                           outline=col + (al,), width=5)

        # ---- centre logo: pop-in, then steady ----
        pop = _ease_out_back((t - 0.25) / 0.5)
        if pop > 0:
            rs = int(logo_ring * max(0.15, pop))
            ring = ring_img.resize((rs, rs), Image.LANCZOS)
            img.paste(ring, (ccx - rs // 2, logo_cy - rs // 2), ring)
            # dark disc behind the avatar/letter
            d.ellipse((ccx - disc_r, logo_cy - disc_r,
                       ccx + disc_r, logo_cy + disc_r), fill=(10, 5, 20, 255))
            if avatar is not None:
                av = avatar.resize((av_size, av_size), Image.LANCZOS) \
                    if pop < 1 else avatar
                img.paste(av, (ccx - av_size // 2, logo_cy - av_size // 2), av)
            else:
                d.polygon(_hexagon_points(ccx, logo_cy, hex_r),
                          outline=GOLD + (255,), width=5)
                d.text((ccx, logo_cy - 4), name[:1].upper(), font=f_fallback,
                       fill=YELLOW + (255,), anchor="mm")

        # ---- token display, per theme mode ----
        if mode == "pills":
            # Pills are pre-rendered images pasted scaled, so text scales
            # with the pill during the pop-in instead of spilling out.
            for idx, (call, (px_, py_), hi) in enumerate(pill_plan):
                appear = 0.5 + idx * 0.3
                u = (t - appear) / 0.35
                if u <= 0:
                    continue
                sc = _ease_out_back(u)
                if 0 < u < 0.45:
                    rr = 40 + u / 0.45 * 90
                    gd.ellipse((px_ - rr, py_ - rr, px_ + rr, py_ + rr),
                               outline=(accent if not hi else GOLD) +
                                       (int(180 * (1 - u / 0.45)),),
                               width=4)
                pim = pill_imgs[(str(call.get("symbol")).upper(),
                                 float(call.get("x", 2)), hi)]
                pw, ph = pim.size
                sw, sh = max(4, int(pw * sc)), max(4, int(ph * sc))
                scaled = pim.resize((sw, sh), Image.LANCZOS)
                img.paste(scaled, (px_ - sw // 2, py_ - sh // 2), scaled)
        elif mode == "row":
            # Same pills, one row on the grid floor, staggered pop-in.
            for idx, (call, (px_, py_), hi) in enumerate(row_plan):
                appear = 0.5 + idx * 0.3
                u = (t - appear) / 0.35
                if u <= 0:
                    continue
                sc = _ease_out_back(u)
                if 0 < u < 0.45:
                    rr = 40 + u / 0.45 * 90
                    gd.ellipse((px_ - rr, py_ - rr, px_ + rr, py_ + rr),
                               outline=(accent if not hi else GOLD) +
                                       (int(180 * (1 - u / 0.45)),),
                               width=4)
                pim = pill_imgs[(str(call.get("symbol")).upper(),
                                 float(call.get("x", 2)), hi)]
                pw, ph = pim.size
                sw, sh = max(4, int(pw * sc)), max(4, int(ph * sc))
                scaled = pim.resize((sw, sh), Image.LANCZOS)
                img.paste(scaled, (px_ - sw // 2, py_ - sh // 2), scaled)
        elif mode == "bars":
            # Bars grow up from the baseline one by one as points count up.
            # Baseline: bright green glowing line.
            bfade = min(1.0, max(0.0, (t - 0.4) / 0.5))
            if bfade > 0:
                if bfade < 1:
                    bg = baseline_glow.copy()
                    bg.putalpha(bg.split()[3].point(
                        lambda a: int(a * bfade)))
                    glow = Image.alpha_composite(glow, bg)
                else:
                    glow = Image.alpha_composite(glow, baseline_glow)
                gd = ImageDraw.Draw(glow)  # glow was rebound above
                gd.line((180, _BAR_BASELINE, 1420, _BAR_BASELINE),
                        fill=(120, 240, 160, int(255 * bfade)), width=3)
            for idx, (call, cx_, h_full, hi) in enumerate(bar_plan):
                appear = 0.5 + idx * 0.35
                u = (t - appear) / 0.45
                if u <= 0:
                    continue
                h_cur = max(4, int(h_full * _ease_out(u)))
                src = bar_img_h if hi else bar_img_n
                bar = src.resize((_BAR_W, h_cur), Image.LANCZOS)
                img.paste(bar, (cx_ - _BAR_W // 2, _BAR_BASELINE - h_cur), bar)
                # label inside the top of the bar (symbol small, X bold),
                # fades in once the bar is tall enough to hold it - the
                # shortest bar is 60px, so the label must fit in 56px:
                # symbol at top+6, X (30pt) at top+26.
                if h_cur >= 56:
                    la = min(1.0, (h_cur - 56) / 14.0)
                    top = _BAR_BASELINE - h_cur
                    c_txt = (20, 20, 20) if hi else WHITE
                    c_x = (20, 20, 20) if hi else YELLOW
                    sym = str(call.get("symbol") or "TOKEN").lstrip("$").upper()
                    d.text((cx_, top + 6), sym, font=f_bar_sym,
                           fill=c_txt + (int(255 * la),), anchor="ma")
                    d.text((cx_, top + 26), _fmt_x(call.get("x", 2)),
                           font=_font(30), fill=c_x + (int(255 * la),),
                           anchor="ma")
        elif mode == "chart":
            # Pills sit ON the line, popping in as the head reaches them.
            for idx, (call, ax, ay, hi) in enumerate(chart_plan):
                if head_x < ax - 5:
                    continue
                u = (head_x - (ax - 5)) / 120.0
                sc = _ease_out_back(min(1.0, u / 0.35)) if u > 0 else 0.0
                if sc <= 0:
                    continue
                pim = chart_pill_imgs[(str(call.get("symbol")).upper(),
                                       float(call.get("x", 2)), hi)]
                pw, ph = pim.size
                sw, sh = max(4, int(pw * sc)), max(4, int(ph * sc))
                scaled = pim.resize((sw, sh), Image.LANCZOS)
                img.paste(scaled, (ax - sw // 2, ay - 42 - sh // 2), scaled)

        # ---- top bar: rank box, title, points box, @Channel pill ----
        fade = min(1.0, t / 0.5)
        # rank box (accent border, dark fill)
        d.rounded_rectangle(rank_box, radius=16, fill=(16, 8, 30, int(255 * fade)),
                            outline=accent + (int(255 * fade),), width=3)
        d.text((rank_box[0] + 16, 85), f"#{rank}", font=f_rank_num,
               fill=YELLOW + (int(255 * fade),), anchor="lm")
        d.text((rank_box[0] + 16 + f_rank_num.getlength(f"#{rank}") + 12, 88),
               "RANK", font=f_rank_lab, fill=WHITE + (int(255 * fade),), anchor="lm")
        # points box
        pts_now = int(round(points * _smoothstep(t / 4.5)))
        d.rounded_rectangle(pts_box, radius=16, fill=(16, 8, 30, int(255 * fade)),
                            outline=accent + (int(255 * fade),), width=3)
        pts_txt = str(pts_now)
        d.text((pts_box[0] + 16, 85), pts_txt, font=f_pts_num,
               fill=YELLOW + (int(255 * fade),), anchor="lm")
        d.text((pts_box[0] + 16 + f_pts_num.getlength(pts_txt) + 10, 88),
               "POINTS", font=f_pts_lab, fill=WHITE + (int(255 * fade),), anchor="lm")
        # title (white + yellow last two words, caps, one line or two)
        flat = [w for ln, _ in title_lines for w in ln.split()]
        n_yellow = min(2, len(flat))
        wi = 0
        for li, (ln, f) in enumerate(title_lines):
            ly = title_cy if not two_line else (66 if li == 0 else 112)
            lw = f.getlength(ln)
            x = 800 - lw / 2
            for w in ln.split():
                is_y = wi >= len(flat) - n_yellow
                d.text((x, ly), w, font=f,
                       fill=(YELLOW if is_y else WHITE) + (int(255 * fade),), anchor="lm")
                x += f.getlength(w + " ")
                wi += 1        # @Channel pill
        d.rounded_rectangle((800 - chan_w // 2, pill_y0, 800 + chan_w // 2, pill_y1),
                            radius=(pill_y1 - pill_y0) // 2,
                            fill=(16, 8, 30, int(255 * fade)),
                            outline=accent + (int(255 * fade),), width=3)
        d.text((800, (pill_y0 + pill_y1) // 2 - 1), chan_text, font=f_chan,
               fill=YELLOW + (int(255 * fade),), anchor="mm")

        # ---- lightning in/around the RANK box (jag bolts, gold + white core) ----
        # flashes in short windows (~0.18s every 1.1s) once the bar is in.
        # Gold glow goes on its own blurred layer; the white core is drawn
        # sharp on the frame AFTER the glow composite (blurring the whole
        # glow layer would wash the core out, as v1 did).
        bolt_cores = []
        if t > 0.6:
            cyc = int(t / 1.1)
            if (t % 1.1) < 0.18:
                rng = random.Random(cyc * 31 + 7)
                bx0, by0, bx1, by1 = rank_box
                bolts = [
                    jag(rng.uniform(bx0 + 30, bx1 - 30), by0 + 2,
                        rng.uniform(bx0 + 10, bx1 - 10), by1 - 2, rng, 9, 9),
                    jag(bx1 - 6, rng.uniform(by0 + 8, by0 + 30),
                        bx1 + 46, rng.uniform(by0 + 30, by1 - 6), rng, 7, 8),
                ]
                bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                bd = ImageDraw.Draw(bl)
                for pts in bolts:
                    bd.line(pts, fill=(255, 190, 0, 220), width=7, joint="curve")
                    bolt_cores.append(pts)
                glow = Image.alpha_composite(
                    glow, bl.filter(ImageFilter.GaussianBlur(5)))

        # ---- bottom: label + gradient button ----
        bfade = min(1.0, max(0.0, (t - 0.8) / 0.5))
        d.text((800, 528), "LAST 5 ALPHA CALLS", font=f_label,
               fill=GRAY + (int(255 * bfade),), anchor="mm")
        if bfade > 0:
            btn = button.copy()
            if bfade < 1:
                btn.putalpha(btn.split()[3].point(lambda a: int(a * bfade)))
            img.paste(btn, (800 - 170, 552), btn)
            d.text((800, 577), "KOL PERFORMANCE", font=f_btn,
                   fill=(20, 20, 20, int(255 * bfade)), anchor="mm")

        # composite the glow layer (meteors, rings, lightning) over the frame
        img = Image.alpha_composite(img, glow)
        # sharp white lightning cores, on top of the glow
        if bolt_cores:
            cd = ImageDraw.Draw(img)
            for pts in bolt_cores:
                cd.line(pts, fill=(255, 255, 255, 255), width=2, joint="curve")
        out = np.asarray(img.convert("RGB"), np.uint8)
        if t < 0.08:  # fade in from black, like the sample
            out = (out.astype(np.float32) * (t / 0.08)).astype(np.uint8)
        return out

    cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo",
           "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-movflags", "+faststart", "-an", out_path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(N_FRAMES):
            pr.stdin.write(frame_at(i).tobytes())
    finally:
        pr.stdin.close()
    if pr.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding rank-up video")
    return out_path


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
