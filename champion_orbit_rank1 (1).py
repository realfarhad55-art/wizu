#!/usr/bin/env python3
"""Rank #1 orbit video — 'CHAMPION KOL' (KrishnaCall, 190 pts).

Recreates the user's reference video (1536x588, 30fps, 5s): black
deep-space background, twinkling stars, amber/blue nebula, corner
planets, top title + rank/points pills, @Channel pill, centre K badge
with double yellow ring, 3 concentric elliptical orbit rings, 5 token
chips revolving (passing behind/in front of the badge), bottom
'LAST 5 ALPHA CALLS' + 'KOL PERFORMANCE' button, shooting star,
shine sweep. Title override: 'CHAMPION KOL' (white + yellow).

Themes (THEMES dict, --theme): yellow / green / blue / orange / purple.
The accent colour drives every accent element (badge ring/hexagon/K,
orbit rings, chips, title accent, pill text, button, glows, ripples);
the planets stay realistic and are never recoloured.

Programmatic entry point (used by champion_rankup_video.py):
render_orbit_video(channel, rank, points, calls, theme, avatar_path,
out_path, crf, preset) — calls is a list of (symbol, x) tuples, or None
to keep the module-default chip layout.

Usage: python3 champion_orbit_rank1.py [--out orbit_rank1.mp4]
"""
import math, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, DUR = 1536, 588, 30, 5.0
NFRAMES = int(FPS * DUR)
CX, CY = 768, 325
YELLOW = (255, 214, 0)
YELLOW_RGB = (255, 214, 0)
# Theme accent colour (set from --theme before rendering). All accent
# elements (badge ring/hexagon/K, orbit rings, chips, title accent, pill
# text, button, glows, ripples) read ACCENT; planets stay realistic.
ACCENT = (255, 214, 0)
# Nebula blobs per theme: (cx, cy, sx, sy, color, peak). Rank 5 purple is
# deliberately vivid (higher peaks + an extra blob) — the user said the
# purple background effects must stay alive, not flat/washed out.
THEMES = {
    "yellow": {
        "accent": (255, 214, 0),
        "nebula": [
            (300, 110, 300, 160, (58, 38, 12), 0.55),
            (1250, 470, 340, 190, (10, 26, 58), 0.60),
            (768, 300, 430, 210, (16, 10, 34), 0.45),
            (1400, 90, 200, 120, (30, 22, 8), 0.35),
        ],
    },
    "green": {
        "accent": (0, 230, 118),
        "nebula": [
            (300, 110, 300, 160, (14, 58, 30), 0.60),
            (1250, 470, 340, 190, (8, 52, 40), 0.62),
            (768, 300, 430, 210, (10, 38, 24), 0.50),
            (1400, 90, 200, 120, (16, 46, 22), 0.38),
        ],
    },
    "blue": {
        "accent": (0, 170, 255),
        "nebula": [
            (300, 110, 300, 160, (12, 36, 84), 0.62),
            (1250, 470, 340, 190, (10, 28, 70), 0.60),
            (768, 300, 430, 210, (8, 24, 64), 0.50),
            (1400, 90, 200, 120, (14, 42, 96), 0.38),
        ],
    },
    "orange": {
        "accent": (255, 140, 0),
        "nebula": [
            (300, 110, 300, 160, (74, 40, 8), 0.62),
            (1250, 470, 340, 190, (54, 26, 10), 0.60),
            (768, 300, 430, 210, (38, 18, 8), 0.50),
            (1400, 90, 200, 120, (66, 34, 6), 0.40),
        ],
    },
    "purple": {
        "accent": (178, 102, 255),
        "nebula": [
            (300, 110, 300, 160, (44, 16, 66), 0.68),
            (1250, 470, 340, 190, (36, 12, 76), 0.72),
            (768, 300, 430, 210, (54, 18, 92), 0.62),
            (1400, 90, 200, 120, (50, 16, 70), 0.48),
            (200, 460, 260, 150, (40, 14, 64), 0.45),
        ],
    },
}
NEBULA_BLOBS = THEMES["yellow"]["nebula"]
# Render config (set from CLI in main()): channel, rank, points, chips.
CFG_CHANNEL = "KrishnaCall"
CFG_RANK = 1
CFG_POINTS = 190
WHITE = (255, 255, 255)
GREY = (154, 160, 166)
DARK = (13, 13, 24)

DEJAVU_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
CJK_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def font(size, cjk=False):
    return ImageFont.truetype(CJK_B if cjk else DEJAVU_B, size)


def clamp(p, a=0.0, b=1.0):
    return max(a, min(b, p))


def ease_out_cubic(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_out_back(p, c1=1.70158):
    p = clamp(p)
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def ease_in_out(p):
    p = clamp(p)
    return p * p * (3 - 2 * p)


def is_cjk(ch):
    return ord(ch) > 0x2E7F


def text_w(draw, s, f):
    return draw.textlength(s, font=f)


def draw_mixed(draw, xy, parts, anchor="la"):
    """parts: list of (text, font, fill). Handles CJK chars with CJK font.
    anchor: 2 chars, horizontal (l/m/r) + vertical (a/m/b)."""
    x, y = xy
    segs = []
    total = 0
    for txt, f, fill in parts:
        run, run_cjk = "", None
        for ch in txt:
            c = is_cjk(ch)
            if run_cjk is None:
                run_cjk, run = c, ch
            elif c == run_cjk:
                run += ch
            else:
                segs.append((run, f if not run_cjk else font(f.size, True), fill))
                run_cjk, run = c, ch
        if run:
            segs.append((run, f if not run_cjk else font(f.size, True), fill))
    for s, f, _ in segs:
        total += draw.textlength(s, font=f)
    ax = x
    if anchor[0] == "m":
        ax = x - total / 2
    elif anchor[0] == "r":
        ax = x - total
    va = anchor[1] if len(anchor) > 1 else "a"
    for s, f, fill in segs:
        draw.text((ax, y), s, font=f, fill=fill, anchor="l" + va)
        ax += draw.textlength(s, font=f)
    return total


def letter_spaced(draw, xy, s, f, fill, spacing=4, anchor="ma"):
    x, y = xy
    widths = [draw.textlength(ch, font=f) for ch in s]
    total = sum(widths) + spacing * (len(s) - 1)
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    va = anchor[1] if len(anchor) > 1 else "a"
    for ch, w in zip(s, widths):
        draw.text((x, y), ch, font=f, fill=fill, anchor="l" + va)
        x += w + spacing
    return total


def paste_faded(base, sprite, xy, alpha):
    """Paste RGBA sprite with extra global alpha (0..1)."""
    if alpha <= 0:
        return
    if alpha >= 1.0:
        base.paste(sprite, xy, sprite)
        return
    sp = sprite.copy()
    a = sp.split()[3].point(lambda v: int(v * alpha))
    sp.putalpha(a)
    base.paste(sp, xy, sp)


def paste_scaled(base, sprite, cx, cy, scale, alpha=1.0, resample=Image.LANCZOS):
    if scale <= 0 or alpha <= 0:
        return
    w, h = sprite.size
    if abs(scale - 1.0) < 0.002:
        # already at native size — skip the (lossy) resize entirely
        paste_faded(base, sprite, (int(cx - w / 2), int(cy - h / 2)), alpha)
        return
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    sp = sprite.resize((nw, nh), resample)
    paste_faded(base, sp, (int(cx - nw / 2), int(cy - nh / 2)), alpha)


# ─── background ──────────────────────────────────────────────────────────────
def make_background():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    top = np.array([4, 4, 13], np.float32)
    bot = np.array([10, 10, 32], np.float32)
    t = (yy / H)[..., None]
    img = top * (1 - t) + bot * t

    def blob(cx, cy, sx, sy, color, peak):
        g = np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
        return g[..., None] * np.array(color, np.float32) * peak

    for (bcx, bcy, bsx, bsy, bcol, bpeak) in NEBULA_BLOBS:
        img += blob(bcx, bcy, bsx, bsy, bcol, bpeak)
    # vignette
    vx = 1 - 0.16 * (((xx - W / 2) / (W / 2)) ** 2)
    vy = 1 - 0.16 * (((yy - H / 2) / (H / 2)) ** 2)
    img *= (vx * vy)[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def make_stars(n=130, seed=7):
    rng = np.random.default_rng(seed)
    stars = []
    guard = 0
    while len(stars) < n and guard < n * 10:
        guard += 1
        x = float(rng.uniform(8, W - 8))
        y = float(rng.uniform(8, H - 8))
        # keep stars out of the title band so none reads as a typo dot
        if 560 <= x <= 980 and 8 <= y <= 78:
            continue
        r = float(rng.uniform(0.8, 2.0))
        ph = float(rng.uniform(0, 6.28))
        fr = float(rng.uniform(0.5, 2.0))
        bright = rng.random() < 0.07
        stars.append((x, y, r, ph, fr, bright))
    return stars


# ─── planets ─────────────────────────────────────────────────────────────────
# Realistic shaded spheres: each planet is an RGBA sprite — a surface
# pattern (bands / continents / patches) under spherical lambert shading
# (light from top-left) + limb darkening + a soft atmosphere glow.
# Rendered at 2-3x supersample, then downscaled for smooth edges.

_LIGHT = (-0.55, -0.55, 0.62)


def _blob(u, v, cu, cv, su, sv):
    return np.exp(-(((u - cu) / su) ** 2 + ((v - cv) / sv) ** 2))


def _sphere(d, surf, glow_rgb, glow_alpha=110, ss=2, pad=12, surf_blur=0.0):
    """d: disc diameter (px, final). surf(u, v) -> (S,S,3) float RGB in disc
    coords u,v in [-1,1]. Returns RGBA sprite (d+2*pad) square, disc
    centred, with a soft glow behind it."""
    S = d * ss
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    u = (xx - S / 2 + 0.5) / (S / 2)
    v = (yy - S / 2 + 0.5) / (S / 2)
    rgb = surf(u, v)
    if surf_blur:
        im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
        rgb = np.asarray(im.filter(ImageFilter.GaussianBlur(surf_blur)), np.float32)
    r2 = u * u + v * v
    inside = r2 <= 1.0
    z = np.sqrt(np.clip(1 - r2, 0, None))
    L = np.array(_LIGHT, np.float32)
    L = L / np.linalg.norm(L)
    diff = np.clip(u * L[0] + v * L[1] + z * L[2], 0, 1)
    shade = (0.30 + 0.70 * diff) * (0.60 + 0.40 * z)
    rgb = np.clip(rgb * shade[..., None], 0, 255)
    r = np.sqrt(r2)
    alpha = np.clip((1 - r) * ss * 1.2, 0, 1) * 255
    alpha = np.where(inside, alpha, 0)
    arr = np.zeros((S, S, 4), np.uint8)
    arr[..., :3] = rgb.astype(np.uint8)
    arr[..., 3] = alpha.astype(np.uint8)
    disc = Image.fromarray(arr, "RGBA").resize((d, d), Image.LANCZOS)
    size = d + 2 * pad
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    a = disc.split()[3].filter(ImageFilter.GaussianBlur(6))
    ga = a.point(lambda x: int(x * glow_alpha / 255))
    tint = Image.new("RGBA", (d, d), (*glow_rgb, 0))
    tint.putalpha(ga)
    out.paste(tint, (pad, pad), tint)
    out.paste(disc, (pad, pad), disc)
    return out


def _surf_jupiter(u, v):
    vb = (v + 0.02 * np.sin(2 * np.pi * 2.2 * u + 1.3)
          + 0.012 * np.sin(2 * np.pi * 4.7 * u + 0.6))
    bounds = np.array([-0.78, -0.50, -0.24, 0.02, 0.28, 0.55, 0.80])
    palette = np.array([
        (214, 178, 140), (233, 207, 167), (183, 139, 93), (239, 221, 189),
        (217, 179, 141), (191, 141, 89), (233, 207, 167), (207, 165, 125),
    ], np.float32)
    rgb = palette[np.searchsorted(bounds, vb)]
    # Great Red Spot, lower half
    e = ((u - 0.30) / 0.17) ** 2 + ((v - 0.30) / 0.10) ** 2
    m = np.clip((1 - e) * 3, 0, 1)[..., None]
    rgb = rgb * (1 - m) + np.array([198, 112, 66], np.float32) * m
    return rgb


def _surf_saturn(u, v):
    base = np.ones(u.shape + (3,), np.float32) * np.array([228, 208, 160], np.float32)
    mod = 1 + 0.05 * np.sin(v * 16) + 0.03 * np.sin(v * 31 + 1.0)
    return base * mod[..., None]


def _surf_mars(u, v):
    rgb = np.ones(u.shape + (3,), np.float32) * np.array([198, 98, 54], np.float32)
    dark = np.array([130, 52, 26], np.float32)
    for cu, cv, su, sv, s in [(-0.30, -0.10, 0.34, 0.20, 0.90),
                              (0.35, 0.35, 0.30, 0.18, 0.85),
                              (0.10, -0.55, 0.24, 0.14, 0.75)]:
        m = _blob(u, v, cu, cv, su, sv) * s
        rgb = rgb * (1 - m[..., None]) + dark * m[..., None]
    cap = np.clip((-0.72 - v) * 6, 0, 1)[..., None]
    rgb = rgb * (1 - cap) + np.array([240, 238, 232], np.float32) * cap
    return rgb


def _surf_earth(u, v):
    rgb = np.ones(u.shape + (3,), np.float32) * np.array([36, 100, 198], np.float32)
    green = np.array([60, 135, 80], np.float32)
    tan = np.array([172, 152, 108], np.float32)
    for cu, cv, su, sv, s, col in [(-0.35, -0.20, 0.34, 0.26, 0.95, green),
                                   (0.30, 0.30, 0.32, 0.24, 0.9, green),
                                   (0.45, -0.45, 0.20, 0.16, 0.85, green),
                                   (0.05, 0.05, 0.22, 0.16, 0.75, tan)]:
        m = _blob(u, v, cu, cv, su, sv) * s
        rgb = rgb * (1 - m[..., None]) + col * m[..., None]
    # thin white cloud streaks, broken up along their length
    for off in (-0.30, 0.05, 0.40):
        vc = v - (0.05 * np.sin(2 * np.pi * 2.0 * u + off * 9) + off)
        m = np.exp(-(vc / 0.025) ** 2) * 0.38
        m = m * (0.35 + 0.65 * np.clip(0.5 + 0.5 * np.sin(2 * np.pi * 1.3 * u + off * 3), 0, 1))
        rgb = rgb * (1 - m[..., None]) + np.array([255, 255, 255], np.float32) * m[..., None]
    caps = np.clip((np.abs(v) - 0.82) * 8, 0, 1)[..., None]
    rgb = rgb * (1 - caps) + np.array([245, 247, 250], np.float32) * caps
    return rgb


def _surf_neptune(u, v):
    rgb = np.ones(u.shape + (3,), np.float32) * np.array([52, 94, 212], np.float32)
    dark = np.array([36, 68, 178], np.float32)
    for cv, s in [(-0.30, 0.65), (0.35, 0.60)]:
        m = np.exp(-((v - cv) / 0.13) ** 2) * s
        rgb = rgb * (1 - m[..., None]) + dark * m[..., None]
    vc = v - (0.04 * np.sin(2 * np.pi * 2.0 * u + 1.0) + 0.05)
    m = np.exp(-(vc / 0.02) ** 2) * 0.35
    rgb = rgb * (1 - m[..., None]) + np.array([225, 235, 255], np.float32) * m[..., None]
    m = _blob(u, v, 0.25, 0.30, 0.12, 0.08) * 0.8
    rgb = rgb * (1 - m[..., None]) + np.array([28, 48, 130], np.float32) * m[..., None]
    return rgb


def _surf_teal(u, v):
    rgb = np.ones(u.shape + (3,), np.float32) * np.array([66, 168, 156], np.float32)
    dark = np.array([38, 118, 110], np.float32)
    m = _blob(u, v, 0.20, 0.20, 0.30, 0.20) * 0.8
    rgb = rgb * (1 - m[..., None]) + dark * m[..., None]
    vc = v - (0.03 * np.sin(2 * np.pi * 2.0 * u) - 0.20)
    m = np.exp(-(vc / 0.03) ** 2) * 0.4
    rgb = rgb * (1 - m[..., None]) + np.array([150, 225, 214], np.float32) * m[..., None]
    return rgb


def planet_jupiter():
    return _sphere(56, _surf_jupiter, (216, 180, 143),
                   glow_alpha=90, ss=2, surf_blur=2.0)


def planet_saturn():
    d = 46
    disc = _sphere(d, _surf_saturn, (228, 208, 160),
                   glow_alpha=80, ss=2, surf_blur=0.8)
    # ring system in its own local frame, then tilted -18 deg.
    # Back half (upper) goes behind the disc, front half (lower) in front.
    rx, ry = 46, 17
    C = 130
    ss = 2
    S = C * ss
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    x = (xx - S / 2) / ss
    y = (yy - S / 2) / ss
    e = np.sqrt((x / rx) ** 2 + (y / ry) ** 2)
    ring_mask = ((e >= 0.62) & (e <= 1.0)).astype(np.float32)
    gap = ((e >= 0.76) & (e <= 0.84)).astype(np.float32)
    edge = np.clip((1.0 - e) * 8, 0, 1) * np.clip((e - 0.62) * 12, 0, 1)
    bright = (1.05 - 0.25 * e) * (1 + 0.12 * (-x / rx * 0.5 - y / ry * 0.5))
    col = np.array([208, 182, 126], np.float32)
    rgb = col * bright[..., None]
    alpha = ring_mask * edge * (1 - gap * 0.6) * 225
    arr = np.zeros((S, S, 4), np.uint8)
    arr[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    arr[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    ring_img = Image.fromarray(arr, "RGBA").resize((C, C), Image.LANCZOS)
    empty = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    mask_back = Image.new("L", (C, C), 0)
    ImageDraw.Draw(mask_back).rectangle([0, 0, C, C // 2], fill=255)
    back = Image.composite(ring_img, empty, mask_back)
    mask_front = Image.new("L", (C, C), 0)
    ImageDraw.Draw(mask_front).rectangle([0, C // 2, C, C], fill=255)
    front = Image.composite(ring_img, empty, mask_front)
    out = Image.new("RGBA", (C, C), (0, 0, 0, 0))
    out.paste(back, (0, 0), back)
    out.paste(disc, ((C - disc.width) // 2, (C - disc.height) // 2), disc)
    out.paste(front, (0, 0), front)
    return out.rotate(-18, resample=Image.BICUBIC, center=(C / 2, C / 2))


def planet_mars():
    return _sphere(20, _surf_mars, (198, 98, 54),
                   glow_alpha=90, ss=3, surf_blur=0.5)


def planet_earth():
    return _sphere(30, _surf_earth, (70, 120, 210),
                   glow_alpha=100, ss=3, surf_blur=0.8)


def planet_neptune():
    return _sphere(24, _surf_neptune, (60, 100, 215),
                   glow_alpha=100, ss=3, surf_blur=0.8)


def planet_teal():
    return _sphere(18, _surf_teal, (66, 168, 156),
                   glow_alpha=90, ss=3, surf_blur=0.8)


def make_glow_sprite(size=320, color=None):
    if color is None:
        color = ACCENT
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = size / 2
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    a = np.clip(1 - r, 0, 1) ** 2.2 * 255
    arr = np.zeros((size, size, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color
    arr[..., 3] = a.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


# ─── badge ───────────────────────────────────────────────────────────────────
def _circle_crop_photo(path, size):
    """Square centre-crop + resize + circular mask. Returns RGBA or None."""
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    im = im.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    im.putalpha(mask)
    return im


def make_badge(letter="K", avatar_path=None):
    s = 260
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    c = s // 2
    dr.ellipse([c - 86, c - 86, c + 86, c + 86], fill=(11, 11, 20, 255))
    dr.ellipse([c - 86, c - 86, c + 86, c + 86], outline=(*ACCENT, 220), width=2)
    dr.ellipse([c - 95, c - 95, c + 95, c + 95], outline=(*ACCENT, 255), width=3)
    photo = _circle_crop_photo(avatar_path, 172) if avatar_path else None
    if photo is not None:
        # real channel avatar inside the double ring (rings stay accent)
        img.paste(photo, (c - 86, c - 86), photo)
        dr.ellipse([c - 86, c - 86, c + 86, c + 86],
                   outline=(*ACCENT, 255), width=2)
        return img
    # hexagon
    pts = []
    for k in range(6):
        a = math.radians(60 * k - 90)
        pts.append((c + 56 * math.cos(a), c + 56 * math.sin(a)))
    dr.polygon(pts, outline=(*ACCENT, 255), width=4)
    dr.polygon(pts, fill=(8, 8, 14, 255))
    dr.polygon(pts, outline=(*ACCENT, 255), width=4)
    f = font(64)
    dr.text((c, c), letter, font=f, fill=(*ACCENT, 255), anchor="mm")
    return img

# ─── chips & pills ───────────────────────────────────────────────────────────
def make_chip(symbol, xval, solid=False):
    """Token chip sprite. Returns (sprite, w, h)."""
    f_sym = font(19)
    f_x = font(22)
    tmp = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    w_sym = td.textlength(symbol, font=f_sym)
    # measure CJK-aware width
    w_sym = 0
    x = 0
    for ch in symbol:
        ff = font(19, True) if is_cjk(ch) else f_sym
        w_sym += td.textlength(ch, font=ff)
    w_x = td.textlength(xval, font=f_x)
    w = int(w_sym + 8 + w_x + 30)
    h = 44
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    if solid:
        dr.rounded_rectangle([1, 1, w - 1, h - 1], radius=22, fill=(*ACCENT, 255))
        # glow halo drawn by caller via glow sprite
        draw_mixed(dr, (15, h / 2), [(symbol, f_sym, (20, 20, 20, 255))], anchor="lm")
        x0 = 15 + w_sym + 8
        dr.text((x0, h / 2), xval, font=f_x, fill=(20, 20, 20, 255), anchor="lm")
    else:
        dr.rounded_rectangle([1, 1, w - 1, h - 1], radius=22,
                             fill=(13, 13, 24, 235), outline=(*ACCENT, 255), width=2)
        draw_mixed(dr, (15, h / 2), [(symbol, f_sym, (230, 230, 230, 255))], anchor="lm")
        x0 = 15 + w_sym + 8
        dr.text((x0, h / 2), xval, font=f_x, fill=(*ACCENT, 255), anchor="lm")
    return img


def pill_frame(w, h, r, outline=None, width=2, fill=(10, 10, 18, 200)):
    if outline is None:
        outline = (*ACCENT, 255)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([1, 1, w - 1, h - 1], radius=r, fill=fill,
                         outline=outline, width=width)
    return img


def make_title_sprite():
    f_big = font(38)
    tmp = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    w1 = td.textlength("CHAMPION ", font=f_big)
    w2 = td.textlength("KOL", font=f_big)
    w = int(w1 + w2 + 24)
    h = 56
    # glow layer
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text((12, h / 2), "CHAMPION ", font=f_big, fill=(255, 255, 255, 255), anchor="lm")
    gd.text((12 + w1, h / 2), "KOL", font=f_big, fill=(*ACCENT, 255), anchor="lm")
    glow_b = glow.filter(ImageFilter.GaussianBlur(6))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste(glow_b, (0, 0), glow_b)
    dr = ImageDraw.Draw(img)
    dr.text((12, h / 2), "CHAMPION ", font=f_big, fill=(255, 255, 255, 255), anchor="lm")
    dr.text((12 + w1, h / 2), "KOL", font=f_big, fill=(*ACCENT, 255), anchor="lm")
    return img


def make_button():
    w, h = 360, 50
    img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([20, 20, 20 + w, 20 + h], radius=25, fill=(*ACCENT, 255))
    f = font(21)
    letter_spaced(dr, (20 + w / 2, 20 + h / 2), "KOL PERFORMANCE", f,
                  (20, 20, 20, 255), spacing=3, anchor="mm")
    return img


def make_at_pill(channel):
    label = "@" + channel
    tmp = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    tw = ImageDraw.Draw(tmp).textlength(label, font=font(20))
    w = max(200, int(tw) + 40)
    img = pill_frame(w, 34, 17, fill=(10, 10, 18, 210))
    dr = ImageDraw.Draw(img)
    dr.text((w // 2, 17), label, font=font(20), fill=(*ACCENT, 255), anchor="mm")
    return img


def make_bottom_label():
    img = Image.new("RGBA", (560, 30), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    letter_spaced(dr, (280, 15), "LAST 5 ALPHA CALLS", font(17),
                  (154, 160, 166, 255), spacing=5, anchor="mm")
    return img


_CHIP_GLOW = None


def chip_glow():
    global _CHIP_GLOW
    if _CHIP_GLOW is None:
        _CHIP_GLOW = make_glow_sprite(150, ACCENT)
    return _CHIP_GLOW


# ─── scene setup ─────────────────────────────────────────────────────────────
RINGS = [  # (rx, ry, sweep_start, sweep_end)
    (660, 132, 0.50, 1.20),
    (470, 110, 0.60, 1.30),
    (280, 80, 0.70, 1.40),
]

# chips: (symbol, xval, ring_idx, angle_at_t2.2_deg, pop_time, solid)
# Default = the approved rank-1 layout (KrishnaCall). Other ranks are
# built by build_chips(): highest X -> slot 0 (solid), rest by X desc.
CHIPS = [
    ("WORTH", "3.7x", 0, 180, 1.2, True),    # outer, solid yellow
    ("DOJE", "2.7x", 0, 0, 1.8, False),      # outer
    ("HYGG", "3.6x", 1, 225, 1.6, False),    # middle
    ("SIA", "2.9x", 1, 45, 1.4, False),      # middle
    ("慌啥子嘛", "2.2x", 2, 200, 1.0, False),  # inner
]
CHIP_SLOTS = [(0, 180, 1.2), (0, 0, 1.8), (1, 225, 1.6), (1, 45, 1.4),
              (2, 200, 1.0)]


def build_chips(calls):
    """calls: [(symbol, xval)] -> CHIPS-format list. Highest X takes the
    solid outer-left slot; the rest fill the remaining slots by X desc."""
    ordered = sorted(calls, key=lambda c: c[1], reverse=True)
    out = []
    for i, (sym, xv) in enumerate(ordered):
        ring, ang, pop = CHIP_SLOTS[i]
        out.append((sym, f"{xv:g}x", ring, ang, pop, i == 0))
    return out
OMEGA = [80.0, 55.0, 35.0]  # deg/s, clockwise

# Ring crop geometry (SPEED): all three rings fit in this box with a 16px
# glow margin, so the ring overlay + its blur are computed on this crop
# instead of the full 1536x588 frame. The blur is local (radius 4), so
# the cropped result is pixel-identical to the full-frame one.
_RING_X0, _RING_Y0 = 92, 177
_RING_W, _RING_H = 1352, 296
# All three rings are fully drawn-in at/after this t (last sweep ends 1.40).
_RING_STATIC_T = 1.40


def _blur_glow(img, radius=4):
    """Soft glow blur: downscale 2x, blur at half radius, upscale. For a
    soft halo this is visually identical to a full-res blur at ~4x the
    speed (SPEED: the per-frame ring glow)."""
    w, h = img.size
    small = img.resize((max(1, w // 2), max(1, h // 2)), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(max(1, radius // 2)))
    return small.resize((w, h), Image.BILINEAR)


def _make_static_rings():
    """Full rings (alpha 235) + their glow, cropped. Used for t >= 1.40
    when the rings no longer change — pasted per frame with pulse alpha."""
    ov = Image.new("RGBA", (_RING_W, _RING_H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    for (rx, ry, _s0, _s1) in RINGS:
        x0 = CX - rx - _RING_X0
        y0 = CY - ry - _RING_Y0
        x1 = CX + rx - _RING_X0
        y1 = CY + ry - _RING_Y0
        dr.ellipse([x0, y0, x1, y1], outline=(*ACCENT, 235), width=2)
    glow = _blur_glow(ov, 4)
    return ov, glow


def chip_angle(chip, t):
    _, _, ring, a22, _, _ = chip
    return a22 + OMEGA[ring] * (t - 2.2)


def chip_xy(chip, t):
    _, _, ring, _, _, _ = chip
    rx, ry, _, _ = RINGS[ring]
    a = math.radians(chip_angle(chip, t))
    return CX + rx * math.cos(a), CY + ry * math.sin(a)


def draw_ring(draw, rx, ry, sweep, pulse):
    """Draw one elliptical orbit ring; sweep 0..1 = arc extent.
    `draw` is an ImageDraw on the ring overlay image."""
    if sweep <= 0:
        return
    x0, y0, x1, y1 = CX - rx, CY - ry, CX + rx, CY + ry
    col = (*ACCENT, int(235 * pulse))
    if sweep >= 0.999:
        draw.ellipse([x0, y0, x1, y1], outline=col, width=2)
    else:
        end = 180 + 360 * sweep
        draw.arc([x0, y0, x1, y1], 180, end, fill=col, width=2)


def render_frame(t, assets):
    (bg, stars, planets, badge, glow, title, button, chip_sprites,
     at_pill, bottom_label, ring_static, ring_static_glow,
     pill_rank, pill_pts) = assets
    frame = bg.copy()
    dr = ImageDraw.Draw(frame)

    # stars (twinkle) — drawn directly on the frame with the pre-blended
    # colour (SPEED: was a full-size RGBA overlay + paste per frame).
    # bg_rgb is the static background colour under the star.
    for (x, y, r, ph, fr, bright, bgrgb) in stars:
        a = 0.55 + 0.45 * math.sin(2 * math.pi * (fr * t + ph))
        al = int(255 * a)
        c = (bgrgb[0] + (255 - bgrgb[0]) * al // 255,
             bgrgb[1] + (255 - bgrgb[1]) * al // 255,
             bgrgb[2] + (255 - bgrgb[2]) * al // 255)
        if bright:
            alf = int(al * 0.7)
            cf = (bgrgb[0] + (255 - bgrgb[0]) * alf // 255,
                  bgrgb[1] + (255 - bgrgb[1]) * alf // 255,
                  bgrgb[2] + (255 - bgrgb[2]) * alf // 255)
            dr.line([x - r * 3, y, x + r * 3, y], fill=cf, width=1)
            dr.line([x, y - r * 3, x, y + r * 3], fill=cf, width=1)
        dr.ellipse([x - r, y - r, x + r, y + r], fill=c)

    # planets (slow drift)
    for (sprite, bx, by, amp, ph) in planets:
        dx = amp * math.sin(2 * math.pi * 0.12 * t + ph)
        dy = amp * 0.6 * math.cos(2 * math.pi * 0.10 * t + ph)
        w, h = sprite.size
        frame.paste(sprite, (int(bx - w / 2 + dx), int(by - h / 2 + dy)), sprite)

    pulse = 0.92 + 0.08 * math.sin(2 * math.pi * 0.8 * t)

    # orbit rings — SPEED: cropped overlay + blur (identical: blur is local,
    # rings sit 16px inside the crop). After t=1.40 the rings are static,
    # so the pre-rendered full rings + glow are pasted with pulse alpha.
    if t >= _RING_STATIC_T:
        paste_faded(frame, ring_static_glow, (_RING_X0, _RING_Y0), pulse)
        paste_faded(frame, ring_static, (_RING_X0, _RING_Y0), pulse)
    else:
        ring_ov = Image.new("RGBA", (_RING_W, _RING_H), (0, 0, 0, 0))
        ring_dr = ImageDraw.Draw(ring_ov)
        for i, (rx, ry, s0, s1) in enumerate(RINGS):
            sweep = ease_out_cubic((t - s0) / (s1 - s0))
            if sweep <= 0:
                continue
            x0 = CX - rx - _RING_X0
            y0 = CY - ry - _RING_Y0
            x1 = CX + rx - _RING_X0
            y1 = CY + ry - _RING_Y0
            col = (*ACCENT, int(235 * pulse))
            if sweep >= 0.999:
                ring_dr.ellipse([x0, y0, x1, y1], outline=col, width=2)
            else:
                end = 180 + 360 * sweep
                ring_dr.arc([x0, y0, x1, y1], 180, end, fill=col, width=2)
        ring_glow = _blur_glow(ring_ov, 4)
        frame.paste(ring_glow, (_RING_X0, _RING_Y0), ring_glow)
        frame.paste(ring_ov, (_RING_X0, _RING_Y0), ring_ov)

    # chips on the far (upper) half — drawn before the badge
    for i, chip in enumerate(CHIPS):
        a = chip_angle(chip, t)
        if math.sin(math.radians(a)) >= 0:
            continue
        draw_chip(frame, chip, chip_sprites[i], t)

    # badge glow + ripples + badge
    glow_a = 0.55 + 0.25 * math.sin(2 * math.pi * 0.8 * t)
    gs = glow.copy()
    gs.putalpha(gs.split()[3].point(lambda v: int(v * 0.55 * glow_a)))
    frame.paste(gs, (CX - 160, CY - 160), gs)
    # ripples on a small overlay centred on the badge (SPEED: was full-size)
    rov = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    rdr = ImageDraw.Draw(rov)
    for start in (0.05, 0.25):
        p = (t - start) / 0.6
        if 0 <= p <= 1:
            rr = 100 + 70 * ease_out_cubic(p)
            al = int(150 * (1 - p))
            rdr.ellipse([180 - rr, 180 - rr, 180 + rr, 180 + rr],
                        outline=(*ACCENT, al), width=3)
    frame.paste(rov, (CX - 180, CY - 180), rov)
    scale = ease_out_back(t / 0.6) if t < 0.6 else 1.0 + 0.02 * math.sin(2 * math.pi * 1.1 * t)
    paste_scaled(frame, badge, CX, CY, max(0.05, scale), resample=Image.BILINEAR)

    # chips on the near (lower) half — drawn after the badge
    for i, chip in enumerate(CHIPS):
        a = chip_angle(chip, t)
        if math.sin(math.radians(a)) < 0:
            continue
        draw_chip(frame, chip, chip_sprites[i], t)

    # top UI on a cropped overlay (content lives in y 0..90; SPEED: was
    # full-size) — slide in 0.35 -> 1.0
    slide = ease_out_cubic((t - 0.35) / 0.65)
    dy = -28 * (1 - slide)
    ta = clamp(slide)
    top = Image.new("RGBA", (W, 96), (0, 0, 0, 0))
    td = ImageDraw.Draw(top)
    tw, th = title.size
    top.paste(title, (int(CX - tw / 2), 14), title)
    top.paste(pill_rank, (230, 16), pill_rank)
    td.text((252, 46), f"#{CFG_RANK}", font=font(30), fill=(*ACCENT, 255), anchor="lm")
    letter_spaced(td, (308, 47), "RANK", font(19), (255, 255, 255, 255), spacing=3, anchor="lm")
    top.paste(pill_pts, (1130, 16), pill_pts)
    cp = ease_out_cubic((t - 0.7) / 1.4)
    pts = int(round(CFG_POINTS * cp))
    td.text((1152, 46), str(pts), font=font(30), fill=(*ACCENT, 255), anchor="lm")
    nw = td.textlength(str(pts), font=font(30))
    letter_spaced(td, (1152 + nw + 10, 47), "POINTS", font(18), (255, 255, 255, 255), spacing=2, anchor="lm")
    paste_faded(frame, top, (0, int(dy)), ta)
    # @ pill pop 0.9 -> 1.3 (text baked into the sprite)
    asc = ease_out_back((t - 0.9) / 0.4)
    if asc > 0:
        paste_scaled(frame, at_pill, CX, 100, asc, 1.0)

    # bottom label + button
    bp = ease_out_cubic((t - 3.2) / 0.6)
    if bp > 0:
        paste_faded(frame, bottom_label, (CX - 280, 485), bp)
        paste_faded(frame, button, (CX - 200, int(502 + 22 * (1 - bp))), bp)
    # shine sweep on button 3.9 -> 4.6 (cropped to the button; SPEED)
    sp = (t - 3.9) / 0.7
    if 0 <= sp <= 1:
        sx = 568 + sp * 400
        sh = Image.new("RGBA", (360, 50), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        sd.polygon([(sx - 40 - 568, 0), (sx + 10 - 568, 0),
                    (sx - 10 - 568, 50), (sx - 60 - 568, 50)],
                   fill=(255, 255, 255, 70))
        mask = Image.new("L", (360, 50), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle([0, 0, 360, 50], radius=25, fill=255)
        sh.putalpha(Image.composite(sh.split()[3], Image.new("L", (360, 50), 0), mask))
        frame.paste(sh, (568, 522), sh)

    # shooting star 1.9 -> 2.4 (top right), cropped overlay (SPEED)
    st = (t - 1.9) / 0.5
    if 0 <= st <= 1:
        hx = 1230 + 210 * ease_out_cubic(st)
        hy = 55 + 85 * ease_out_cubic(st)
        st_ov = Image.new("RGBA", (380, 110), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st_ov)
        for k in range(6):
            f = 1 - k / 6
            x1 = hx - 26 * k * ease_out_cubic(st) - 1070
            y1 = hy - 10 * k * ease_out_cubic(st) - 40
            sd.line([x1, y1, hx - 1070, hy - 40], fill=(255, 255, 255, int(220 * f * (1 - st * 0.5))), width=2)
        sd.ellipse([hx - 1070 - 3, hy - 40 - 3, hx - 1070 + 3, hy - 40 + 3], fill=(255, 255, 255, 255))
        frame.paste(st_ov, (1070, 40), st_ov)

    # global fade-in from black
    fa = ease_out_cubic(t / 0.35)
    if fa < 1:
        frame = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), frame, fa)
    return frame


def draw_chip(frame, chip, sprite, t):
    symbol, xval, ring, a22, pop, solid = chip
    p = ease_out_back((t - pop) / 0.45)
    if p <= 0:
        return
    x, y = chip_xy(chip, t)
    float_y = 2 * math.sin(2 * math.pi * 0.7 * t + ring)
    if solid:
        ga = chip_glow().copy()
        ga.putalpha(ga.split()[3].point(lambda v: int(v * 0.5)))
        frame.paste(ga, (int(x - 75), int(y + float_y - 75)), ga)
    paste_scaled(frame, sprite, x, y + float_y, max(0.05, p))


def build_assets(avatar_path=None):
    bg = make_background()
    stars = make_stars()
    # SPEED: precompute the static background colour under each star so
    # the twinkle can be drawn directly on the frame (no full-size overlay
    # + paste per frame). The frame starts as bg.copy(), so the colour
    # under a star is exactly bg at that point.
    stars = [(x, y, r, ph, fr, bright, bg.getpixel((int(x), int(y))))
             for (x, y, r, ph, fr, bright) in stars]
    planets = [
        (planet_jupiter(), 120, 150, 4, 0.0),
        (planet_saturn(), 1400, 156, 4, 1.2),
        (planet_mars(), 124, 490, 3, 2.1),
        (planet_earth(), 1440, 540, 4, 0.5),
        (planet_neptune(), 1505, 385, 3, 3.0),
        (planet_teal(), 55, 410, 3, 4.0),
    ]
    badge = make_badge(CFG_CHANNEL[0].upper(), avatar_path)
    glow = make_glow_sprite(320, ACCENT)
    title = make_title_sprite()
    button = make_button()
    at_pill = make_at_pill(CFG_CHANNEL)
    bottom_label = make_bottom_label()
    chip_sprites = [make_chip(s, x, solid) for (s, x, _, _, _, solid) in CHIPS]
    # SPEED: pill frames are static (same outline every frame) — build once.
    pill_rank = pill_frame(170, 60, 14)
    pill_pts = pill_frame(200, 60, 14)
    # SPEED: full rings + glow, pre-rendered once for the static phase.
    ring_static, ring_static_glow = _make_static_rings()
    return (bg, stars, planets, badge, glow, title, button, chip_sprites,
            at_pill, bottom_label, ring_static, ring_static_glow,
            pill_rank, pill_pts)


def render_orbit_video(*, channel, rank, points, calls, theme="yellow",
                       avatar_path=None, out_path, crf=18,
                       preset="veryfast", verbose=False):
    """Programmatic entry point (used by champion_rankup_video.py).
    channel: str (no @). rank: int 1-5. points: int. calls: list of
    (symbol, x) tuples (0-5, already filtered >= 2.0 by the caller), or
    None to keep the module-default chip layout. theme: one of THEMES.
    Returns out_path. Raises on ffmpeg failure."""
    global ACCENT, NEBULA_BLOBS, CFG_CHANNEL, CFG_RANK, CFG_POINTS, CHIPS
    global _CHIP_GLOW
    if theme not in THEMES:
        raise ValueError(
            f"unknown orbit theme {theme!r}, want one of {sorted(THEMES)}")
    ACCENT = THEMES[theme]["accent"]
    NEBULA_BLOBS = THEMES[theme]["nebula"]
    CFG_CHANNEL, CFG_RANK, CFG_POINTS = channel, int(rank), int(points)
    if calls is not None:
        CHIPS = build_chips([(str(s), float(x)) for s, x in calls])
    _CHIP_GLOW = None  # glow sprite is baked in the old accent colour
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    assets = build_assets(avatar_path=avatar_path)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
           "-preset", preset, "-movflags", "+faststart", "-an", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(NFRAMES):
            t = i / FPS
            proc.stdin.write(render_frame(t, assets).tobytes())
            if verbose and i % 30 == 0:
                print(f"frame {i}/{NFRAMES} t={t:.2f}s", flush=True)
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed while encoding {out_path}")
    return out_path


def parse_calls(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        sym, _, xv = part.rpartition(":")
        out.append((sym.strip(), float(xv)))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="orbit_rank1.mp4")
    ap.add_argument("--theme", default="yellow",
                    choices=list(THEMES))
    ap.add_argument("--channel", default="KrishnaCall")
    ap.add_argument("--rank", type=int, default=1)
    ap.add_argument("--points", type=int, default=190)
    ap.add_argument("--calls", default=None,
                    help='"SYM:X,SYM:X,..." — rebuilds CHIPS from calls')
    a = ap.parse_args()
    out = render_orbit_video(
        channel=a.channel, rank=a.rank, points=a.points,
        calls=parse_calls(a.calls) if a.calls else None,
        theme=a.theme, out_path=a.out, verbose=True)
    print("done:", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
