"""
most_shared_video.py — 8s (1440x626, 30fps) "MOST SHARED TOKENS TODAY" video.

Timeline:
    0.0 - 4.0s   page 1  (ranks 1-5)   rows slide in one by one, shine sweep
    3.9 - 4.5s   lightning flash transition
    4.5 - 8.0s   page 2  (ranks 6-10)  same animation

Input  : list of token dicts (rank order, 1..10)
            symbol   str        "ELON2028"   (no $)
            chain    str        "SOL" | "ETH" | "BNB" | "BASE" | "TON" | "RH" | "ARC"
            count    int        number of channels / calls
            ath_mc   float      highest market cap (USD)
            from_mc  float      entry market cap of the best call (USD)
            x        float      ath_mc / from_mc
            logo     bytes|None token logo (png/jpg/webp). None -> coloured letter badge
Output : path of an .mp4 (caller MUST delete it after posting -> see most_shared_cleanup()).

Needs Pillow, numpy and ffmpeg (system ffmpeg OR `pip install imageio-ffmpeg`).
"""
import gc
import hashlib
import io
import logging
import math
import os
import random
import shutil
import subprocess
import tempfile
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger("most_shared_video")

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
W, H, FPS, DUR = 1440, 626, 30, 8.0
NFRAMES = int(FPS * DUR)

MINT = (45, 226, 160)
BLUE = (96, 165, 250)
SKY = (110, 205, 255)
GRAY = (150, 158, 190)
CHAIN_COL = {
    "SOL": (90, 180, 255), "RH": (52, 211, 120), "BNB": (251, 191, 36), "ETH": (160, 170, 255),
    "BASE": (59, 130, 246), "TON": (56, 189, 248), "ARC": (167, 139, 250),
}
ROW_STYLE = [  # (accent, glow?, count colour)
    ((34, 255, 140), True, (45, 240, 150)),
    ((59, 130, 246), True, (70, 140, 255)),
    ((90, 200, 255), True, (90, 200, 255)),
    ((120, 128, 170), False, (255, 255, 255)),
    ((120, 128, 170), False, (255, 255, 255)),
]


# ───────────────────────── helpers ─────────────────────────
def _first(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def _font_path():
    return _first(os.environ.get("MOST_SHARED_FONT"),
                  os.path.join(ASSETS, "fonts", "Poppins-Bold.ttf"),
                  os.path.join(HERE, "Poppins-Bold.ttf"),
                  "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")


@lru_cache(maxsize=64)
def _font(size):
    p = _font_path()
    return ImageFont.truetype(p, size) if p else ImageFont.load_default()


def _ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _ease_out(u):
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** 3


def _clamp(u):
    return min(1.0, max(0.0, u))


def fmt_usd(v):
    """$1.34M / $998.9K / $15.8K / $950"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "N/A"
    if v <= 0:
        return "N/A"
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:.1f}K"
    return f"${v:.0f}"


def fmt_x(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "1.0X"
    if x >= 100:
        return f"{x:.0f}X"
    return f"{max(x, 1.0):.1f}X"


def _text_w(text, font, spacing=0.0):
    return sum(font.getlength(c) for c in text) + spacing * max(0, len(text) - 1)


def _text_layer(text, size, fill, spacing=0.0, italic=True, glow=None, glow_r=10, grad=None, stroke=0):
    """RGBA layer holding `text`. fill=(r,g,b) or grad=((r,g,b),(r,g,b)) (left->right).
    Returns (layer, pad) — the text's top-left is at (pad, pad) inside the layer."""
    f = _font(size)
    tw = int(_text_w(text, f, spacing)) + 4
    th = int(size * 1.5)
    pad = glow_r * 3 + 8 + int(size * 0.35)
    mask = Image.new("L", (tw + pad * 2, th + pad * 2), 0)
    d = ImageDraw.Draw(mask)
    x = pad
    for c in text:
        d.text((x, pad), c, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
        x += f.getlength(c) + spacing
    if italic:
        k = 0.2
        mask = mask.transform(mask.size, Image.AFFINE, (1, k, -k * (pad + th * 0.8), 0, 1, 0), Image.BICUBIC)
    lw, lh = mask.size
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    if glow:
        g = mask.filter(ImageFilter.GaussianBlur(glow_r))
        g = g.point(lambda v: min(255, int(v * 1.6)))
        glay = Image.new("RGBA", (lw, lh), tuple(glow) + (0,))
        glay.putalpha(g)
        layer = Image.alpha_composite(layer, glay)
    if grad:
        a, b = grad
        xs = np.linspace(0, 1, lw, dtype=np.float32)[None, :, None]
        col = (np.array(a, np.float32)[None, None, :] * (1 - xs) + np.array(b, np.float32)[None, None, :] * xs)
        col = np.broadcast_to(col, (lh, lw, 3)).astype(np.uint8)
        fl = Image.fromarray(col, "RGB").convert("RGBA")
    else:
        fl = Image.new("RGBA", (lw, lh), tuple(fill) + (255,))
    fl.putalpha(mask)
    layer = Image.alpha_composite(layer, fl)
    return layer, pad


def _paste(dst, layer, x, y):
    """alpha-composite `layer` onto RGBA `dst` at (x, y) (negative / overflow safe)."""
    dst.alpha_composite(layer, (int(x), int(y))) if (x >= 0 and y >= 0) else _paste_clip(dst, layer, x, y)


def _paste_clip(dst, layer, x, y):
    x, y = int(x), int(y)
    sx, sy = max(0, -x), max(0, -y)
    crop = layer.crop((sx, sy, layer.width, layer.height))
    dst.alpha_composite(crop, (x + sx, y + sy))


def _circle(img, d):
    img = img.convert("RGBA").resize((d, d), Image.LANCZOS)
    m = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=255)
    m = m.resize((d, d), Image.LANCZOS)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(img, (0, 0), m)
    return out


def _letter_badge(symbol, d):
    h = int(hashlib.md5((symbol or "?").encode()).hexdigest()[:6], 16)
    r = random.Random(h)
    import colorsys
    c1 = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(r.random(), 0.65, 0.85))
    c2 = tuple(int(v * 255) for v in colorsys.hsv_to_rgb((r.random() * 0.2 + 0.1) % 1, 0.7, 0.55))
    g = np.linspace(0, 1, d, dtype=np.float32)[:, None, None]
    arr = (np.array(c1, np.float32) * (1 - g) + np.array(c2, np.float32) * g)
    arr = np.broadcast_to(arr, (d, d, 3)).astype(np.uint8)
    img = Image.fromarray(arr, "RGB").convert("RGBA")
    ch = (symbol or "?").strip("$")[:1].upper() or "?"
    dr = ImageDraw.Draw(img)
    f = _font(int(d * 0.5))
    tw = f.getlength(ch)
    dr.text(((d - tw) / 2, d * 0.18), ch, font=f, fill=(255, 255, 255, 255))
    return _circle(img, d)


def _logo_circle(logo_bytes, symbol, d):
    if logo_bytes:
        try:
            im = Image.open(io.BytesIO(logo_bytes))
            im.load()
            if im.width > 1 and im.height > 1:
                if im.mode in ("P", "LA") or "transparency" in im.info:
                    im = im.convert("RGBA")
                # centre-square crop
                s = min(im.size)
                im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                              (im.width - s) // 2 + s, (im.height - s) // 2 + s))
                bg = Image.new("RGBA", im.size, (14, 18, 40, 255))
                bg.alpha_composite(im.convert("RGBA"))
                return _circle(bg, d)
        except Exception as e:
            log.warning(f"logo decode failed for {symbol}: {e!r}")
    return _letter_badge(symbol, d)


# ───────────────────────── static art ─────────────────────────
def _background():
    """RGB array (H,W,3): deep navy gradient + faint grid + vignette."""
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    top = np.array((3, 6, 20), np.float32)
    bot = np.array((6, 12, 36), np.float32)
    arr = top * (1 - y) + bot * y
    arr = np.broadcast_to(arr, (H, W, 3)).copy()
    xs = np.linspace(-1, 1, W, dtype=np.float32)[None, :]
    ys = np.linspace(-1, 1, H, dtype=np.float32)[:, None]
    glow = np.exp(-((xs * 0.9) ** 2 + (ys * 1.2) ** 2) * 1.6)[..., None]
    arr += glow * np.array((4, 10, 28), np.float32)
    arr[::38, :, :] += 3
    arr[:, ::38, :] += 3
    return np.clip(arr, 0, 255).astype(np.uint8)


def _stars(seed=7, n=70):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        out.append((rnd.randrange(8, W - 8), rnd.randrange(6, H - 6), rnd.choice((1, 1, 1, 2)),
                    rnd.random() * 6.28, 0.6 + rnd.random() * 1.8))
    sparks = [(rnd.randrange(30, W - 30), rnd.randrange(130, H - 40), rnd.random() * 6.28) for _ in range(9)]
    return out, sparks


def _star_overlay(stars, sparks, t):
    """small RGBA full-frame overlay with twinkling stars (cheap: draws ~80 dots)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x, y, r, ph, sp in stars:
        a = int(70 + 150 * (0.5 + 0.5 * math.sin(t * sp + ph)))
        d.ellipse((x - r + 1, y - r + 1, x + r - 1, y + r - 1), fill=(220, 230, 255, a))
    for x, y, ph in sparks:
        a = int(40 + 170 * max(0.0, math.sin(t * 1.3 + ph)))
        d.line((x - 7, y, x + 7, y), fill=(220, 235, 255, a), width=1)
        d.line((x, y - 7, x, y + 7), fill=(220, 235, 255, a), width=1)
    return im


def _logo_wizard(d):
    p = _first(os.environ.get("MOST_SHARED_LOGO"),
               os.path.join(ASSETS, "wizard_logo.png"), os.path.join(HERE, "wizard_logo.png"))
    if p:
        try:
            im = Image.open(p).convert("RGBA")
            s = min(im.size)
            im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                          (im.width - s) // 2 + s, (im.height - s) // 2 + s))
            return _circle(im, d)
        except Exception as e:
            log.warning(f"wizard logo load failed: {e!r}")
    im = Image.new("RGBA", (d, d), (30, 24, 10, 255))
    dr = ImageDraw.Draw(im)
    dr.ellipse((3, 3, d - 4, d - 4), outline=(255, 190, 60, 255), width=3)
    f = _font(int(d * 0.5))
    dr.text((d * 0.27, d * 0.16), "W", font=f, fill=(255, 200, 80, 255))
    return _circle(im, d)


def _header_layer(page_label):
    """RGBA (W, 130): logo, title, subtitle, badge, line, TOP x-y."""
    L = Image.new("RGBA", (W, 130), (0, 0, 0, 0))
    # logo + warm glow
    lg = _logo_wizard(76)
    glow = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((20, 20, 120, 120), fill=(255, 170, 40, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(16))
    L.alpha_composite(glow, (4, -14))
    L.alpha_composite(lg, (36, 18))
    # title
    t, pad = _text_layer("MOST SHARED TOKENS TODAY", 56, None, spacing=0.0, italic=True,
                         glow=(60, 150, 255), glow_r=9, grad=(MINT, BLUE))
    _paste(L, t, 145 - pad, 16 - pad)
    # subtitle
    s, pad = _text_layer("CALLED BY THE MOST CHANNELS  •  ATH = HIGHEST MARKET CAP", 17, (240, 244, 255),
                         spacing=1.7, italic=False, glow=None)
    _paste(L, s, 142 - pad, 82 - pad)
    # badge
    bd = Image.new("RGBA", (W, 130), (0, 0, 0, 0))
    dr = ImageDraw.Draw(bd)
    dr.rounded_rectangle((1145, 27, 1405, 78), radius=26, fill=(14, 34, 66, 200), outline=(110, 200, 255, 255), width=3)
    gl = bd.filter(ImageFilter.GaussianBlur(6))
    L.alpha_composite(gl)
    L.alpha_composite(bd)
    bt, pad = _text_layer("LAST 24 HOURS", 24, (160, 210, 255), spacing=2.0, italic=True, glow=None)
    bw = _text_w("LAST 24 HOURS", _font(24), 2.0)
    _paste(L, bt, 1275 - bw / 2 - pad, 40 - pad)
    pt, pad = _text_layer(page_label, 17, (245, 248, 255), spacing=2.0, italic=False)
    pw = _text_w(page_label, _font(17), 2.0)
    _paste(L, pt, 1275 - pw / 2 - pad, 90 - pad)
    # gradient line
    xs = np.linspace(0, 1, 1360, dtype=np.float32)[None, :, None]
    col = np.array(MINT, np.float32) * (1 - xs) + np.array(BLUE, np.float32) * xs
    line = np.broadcast_to(col, (2, 1360, 3)).astype(np.uint8)
    lim = Image.fromarray(line, "RGB").convert("RGBA")
    L.alpha_composite(lim, (40, 113))
    return L


def _footer_layer():
    L = Image.new("RGBA", (W, 40), (0, 0, 0, 0))
    txt = "WIZARD SCAN   •   wizardscanlive.com"
    t, pad = _text_layer(txt, 16, (235, 240, 255), spacing=2.2, italic=False)
    tw = _text_w(txt, _font(16), 2.2)
    _paste(L, t, W / 2 - tw / 2 - pad, 6 - pad)
    return L


ROW_X0, ROW_X1, ROW_H, ROW_Y0, ROW_STEP = 60, 1380, 80, 125, 90
ROW_PAD = 22  # glow margin around row layer


def _row_layer(rank, tok, local_idx, page_style_gray):
    """RGBA layer (ROW_X1-ROW_X0+2*PAD, ROW_H+2*PAD) for one token row."""
    accent, glow_on, count_col = ROW_STYLE[local_idx]
    if page_style_gray:                     # page 2 = dim rows (like the reference)
        accent, glow_on, count_col = ROW_STYLE[3]
    w = ROW_X1 - ROW_X0 + ROW_PAD * 2
    h = ROW_H + ROW_PAD * 2
    L = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    P = ROW_PAD
    # glow + body
    if glow_on:
        gl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(gl).rounded_rectangle((P, P, P + ROW_X1 - ROW_X0, P + ROW_H), radius=18,
                                             outline=accent + (210,), width=4)
        L.alpha_composite(gl.filter(ImageFilter.GaussianBlur(7)))
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle((P, P, P + ROW_X1 - ROW_X0, P + ROW_H), radius=18, fill=(8, 14, 38, 232),
                         outline=accent + ((255,) if glow_on else (140,)), width=2)
    bd.rounded_rectangle((P + 2, P + 16, P + 6, P + ROW_H - 16), radius=2, fill=accent + (255,))
    L.alpha_composite(body)

    def at(layer, pad, x, y):                # x, y = absolute canvas coords of text top-left
        _paste(L, layer, x - ROW_X0 + P - pad, y - (ROW_Y0 + 0) + P - pad - 0)

    # NB: y is given relative to the row top, so shift by local row top = ROW_Y0 + idx*STEP -> handled by caller
    return L


def _compose_row(rank, tok, local_idx, gray_page):
    """Full row art. Coordinates inside are relative to row top-left (ROW_X0, rowtop)."""
    accent, glow_on, count_col = ROW_STYLE[local_idx]
    if gray_page:
        accent, glow_on, count_col = ROW_STYLE[3]
    w = ROW_X1 - ROW_X0 + ROW_PAD * 2
    h = ROW_H + ROW_PAD * 2
    P = ROW_PAD
    L = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if glow_on:
        gl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(gl).rounded_rectangle((P, P, P + ROW_X1 - ROW_X0, P + ROW_H), radius=18,
                                             outline=accent + (200,), width=4)
        L.alpha_composite(gl.filter(ImageFilter.GaussianBlur(7)))
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle((P, P, P + ROW_X1 - ROW_X0, P + ROW_H), radius=18, fill=(8, 14, 38, 235),
                         outline=accent + ((255,) if glow_on else (130,)), width=2)
    bd.rounded_rectangle((P + 2, P + 16, P + 6, P + ROW_H - 16), radius=2, fill=accent + (255,))
    L.alpha_composite(body)

    def put(layer, pad, rx, ry):             # rx, ry relative to row's top-left (inside the 60..1380 box)
        _paste(L, layer, P + rx - pad, P + ry - pad)

    # rank
    rk = f"{rank:02d}"
    rcol = accent if (glow_on and not gray_page) else (165, 172, 205)
    t, pad = _text_layer(rk, 36, rcol, italic=True, glow=accent if (glow_on and not gray_page) else None, glow_r=8)
    rw = _text_w(rk, _font(36))
    put(t, pad, 61 - rw / 2, 18)
    # logo ring + logo
    cx, cy, r = 216 - ROW_X0, ROW_H // 2, 28
    ring = Image.new("RGBA", (r * 2 + 12, r * 2 + 12), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((2, 2, r * 2 + 9, r * 2 + 9), outline=accent + (255,), width=3)
    if glow_on and not gray_page:
        ring = Image.alpha_composite(ring.filter(ImageFilter.GaussianBlur(4)), ring)
    _paste(L, ring, P + cx - r - 6, P + cy - r - 6)
    lg = _logo_circle(tok.get("logo"), tok.get("symbol", ""), 46)
    _paste(L, lg, P + cx - 23, P + cy - 23)
    # symbol
    sym = "$" + str(tok.get("symbol", "TOKEN")).upper().lstrip("$")
    sz = 36
    while sz > 22 and _text_w(sym, _font(sz)) > 410:
        sz -= 2
    t, pad = _text_layer(sym, sz, (255, 255, 255), italic=True,
                         glow=accent if (glow_on and local_idx == 0 and not gray_page) else None, glow_r=7)
    put(t, pad, 274 - ROW_X0, 8 + (36 - sz) // 3)
    # chain
    ch = str(tok.get("chain", "")).upper()
    t, pad = _text_layer(ch, 17, CHAIN_COL.get(ch, SKY), spacing=0.6, italic=False)
    put(t, pad, 272 - ROW_X0, 54)
    # count + label
    cnt = str(int(tok.get("count", 0)))
    cw = _text_w(cnt, _font(46))
    t, pad = _text_layer(cnt, 46, count_col, italic=False)
    put(t, pad, 859 - ROW_X0 - cw / 2, 3)
    lab = "CHANNELS" if int(tok.get("count", 0)) != 1 else "CHANNEL"
    lw = _text_w(lab, _font(13), 1.6)
    t, pad = _text_layer(lab, 13, (240, 244, 255), spacing=1.6, italic=False)
    put(t, pad, 859 - ROW_X0 - lw / 2, 56)
    # separator
    sp = Image.new("RGBA", (2, 44), (90, 100, 135, 200))
    _paste(L, sp, P + 958 - ROW_X0, P + 18)
    # ATH
    t, pad = _text_layer("ATH", 17, MINT, spacing=1.0, italic=False)
    put(t, pad, 990 - ROW_X0, 19)
    ath = fmt_usd(tok.get("ath_mc"))
    asz = 44
    while asz > 26 and _text_w(ath, _font(asz)) > 320:
        asz -= 2
    t, pad = _text_layer(ath, asz, None, italic=True, grad=(MINT, BLUE), glow=(50, 190, 200), glow_r=5)
    put(t, pad, 1043 - ROW_X0, 6 + (44 - asz) // 3)
    fr = f"FROM {fmt_usd(tok.get('from_mc'))}  •  {fmt_x(tok.get('x'))}"
    t, pad = _text_layer(fr, 20, (245, 248, 255), spacing=0.3, italic=False)
    put(t, pad, 990 - ROW_X0, 48)
    return L


# ───────────────────────── lightning ─────────────────────────
def _bolt_points(rnd, x0, y0, x1, y1, depth=0):
    pts = [(x0, y0)]
    steps = 14
    for i in range(1, steps):
        t = i / steps
        pts.append((x0 + (x1 - x0) * t + rnd.uniform(-26, 26), y0 + (y1 - y0) * t))
    pts.append((x1, y1))
    return pts


def _lightning_layer(seed=3):
    rnd = random.Random(seed)
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    for bx in (300, 735, 1125):
        pts = _bolt_points(rnd, bx + rnd.uniform(-20, 20), 0, bx + rnd.uniform(-40, 40), H)
        d.line(pts, fill=(235, 245, 255, 255), width=3)
        for _ in range(3):             # branches
            k = rnd.randrange(3, 10)
            bx0, by0 = pts[k]
            ex = bx0 + rnd.choice((-1, 1)) * rnd.uniform(120, 260)
            ey = by0 + rnd.uniform(60, 150)
            bp = _bolt_points(rnd, bx0, by0, ex, ey)
            d.line(bp, fill=(225, 238, 255, 230), width=2)
    glow = L.filter(ImageFilter.GaussianBlur(7))
    out = Image.alpha_composite(glow, L)
    return out


# ───────────────────────── frame composition ─────────────────────────
def _blend(dst, layer, x, y, alpha=1.0, add=False):
    """dst: float32 (H,W,3). layer: PIL RGBA. alpha scales layer alpha."""
    lw, lh = layer.size
    x, y = int(x), int(y)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + lw), min(H, y + lh)
    if x1 <= x0 or y1 <= y0 or alpha <= 0:
        return
    arr = np.asarray(layer)[y0 - y:y1 - y, x0 - x:x1 - x]
    a = (arr[..., 3:4].astype(np.float32) / 255.0) * alpha
    rgb = arr[..., :3].astype(np.float32)
    reg = dst[y0:y1, x0:x1]
    if add:
        reg += rgb * a
    else:
        reg *= (1.0 - a)
        reg += rgb * a


def _page_tokens(tokens, page):
    return tokens[page * 5:(page + 1) * 5]


class _Enc:
    def __init__(self, path):
        cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-threads", str(max(1, int(os.environ.get("MOST_SHARED_FFMPEG_THREADS", "2") or 2))),
               "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", path]
        self._err = tempfile.TemporaryFile()
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self._err)

    def write(self, b):
        try:
            self.p.stdin.write(b)
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"ffmpeg died: rc={self.p.poll()} {self._tail()}") from e

    def _tail(self):
        try:
            self._err.seek(0)
            return self._err.read()[-500:].decode("utf-8", "replace")
        except Exception:
            return ""

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        rc = self.p.wait(timeout=120)
        if rc != 0:
            raise RuntimeError(f"ffmpeg rc={rc}: {self._tail()}")
        try:
            self._err.close()
        except Exception:
            pass


def build_most_shared_video(tokens, out_path=None):
    """Render the 8s video. `tokens`: list of up to 10 dicts (rank order). Returns mp4 path."""
    tokens = list(tokens or [])[:10]
    if len(tokens) < 1:
        raise ValueError("no tokens")
    pages = 2 if len(tokens) > 5 else 1
    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix="most_shared_", suffix=".mp4")
        os.close(fd)
    bg = _background()
    stars, sparks = _stars()
    star_phases = [_star_overlay(stars, sparks, k * 0.55) for k in range(6)]
    footer = _footer_layer()
    headers = [_header_layer("TOP 1 - 5")] + ([_header_layer("TOP 6 - 10")] if pages == 2 else [])
    rows = []
    for p in range(pages):
        pr = []
        for i, tk in enumerate(_page_tokens(tokens, p)):
            pr.append(_compose_row(p * 5 + i + 1, tk, i, gray_page=(p == 1)))
        rows.append(pr)
    bolts = [_lightning_layer(s) for s in (3, 11)]
    shine_w = 150
    shine = np.zeros((ROW_H + 2 * ROW_PAD, shine_w), np.float32)
    for xx in range(shine_w):
        shine[:, xx] = max(0.0, 1 - abs(xx - shine_w / 2) / (shine_w / 2)) ** 1.6
    # slant: shift each row of the band
    for yy in range(shine.shape[0]):
        shine[yy] = np.roll(shine[yy], int((yy - shine.shape[0] / 2) * 0.55))

    enc = _Enc(out_path)
    try:
        for fi in range(NFRAMES):
            t = fi / FPS
            frame = bg.astype(np.float32)
            _blend(frame, star_phases[(fi // 6) % len(star_phases)], 0, 0, 1.0)
            page = 0 if t < 4.0 else 1
            if page >= pages:
                page = 0
            lt = t if page == 0 else t - 4.5          # local page time
            # header / footer fade
            if page == 0:
                ha = _ease_out((t - 0.1) / 0.55)
            else:
                ha = 1.0
            _blend(frame, headers[page], 0, 0, ha)
            _blend(frame, footer, 0, H - 44, ha)
            # rows
            vis_page = page
            for i, rl in enumerate(rows[vis_page]):
                st = 0.45 + 0.17 * i
                u = _ease_out((lt - st) / 0.38)
                if page == 1 and t < 4.5:
                    u = 0.0
                out_f = 1.0
                if page == 0 and t > 3.85:           # fade out into the flash
                    out_f = _clamp(1 - (t - 3.85) / 0.15)
                al = u * out_f
                if al <= 0.001:
                    continue
                dx = (1 - u) * -70
                y = ROW_Y0 + i * ROW_STEP - ROW_PAD
                x = ROW_X0 - ROW_PAD + dx
                # flicker while entering
                if 0 < u < 0.7:
                    al *= 0.75 + 0.25 * math.sin(fi * 2.7 + i)
                _blend(frame, rl, x, y, al)
                # shine sweep
                ss = 1.9 + 0.2 * i if page == 0 else 6.2 + 0.2 * i
                su = (t - ss) / 0.75
                if 0.0 <= su <= 1.0 and u > 0.99 and out_f > 0.99:
                    sx = int(ROW_X0 + (ROW_X1 - ROW_X0 + shine_w) * su - shine_w)
                    rl_alpha = np.asarray(rl)[..., 3].astype(np.float32) / 255.0
                    # clip the shine to the row body
                    gx0 = sx - (ROW_X0 - ROW_PAD)
                    reg = np.zeros_like(rl_alpha)
                    a0, a1 = max(0, gx0), min(reg.shape[1], gx0 + shine_w)
                    if a1 > a0:
                        reg[:, a0:a1] = shine[:, a0 - gx0:a1 - gx0]
                        reg *= rl_alpha
                        yy0, xx0 = y, ROW_X0 - ROW_PAD
                        sub = frame[yy0:yy0 + reg.shape[0], xx0:xx0 + reg.shape[1]]
                        sub += reg[..., None] * np.array((190, 215, 255), np.float32) * 0.55
            # lightning flash between pages (3.9 - 4.55)
            if pages == 2 and 3.9 <= t <= 4.55:
                fu = (t - 3.9) / 0.65
                env = math.sin(min(1.0, fu) * math.pi)
                flick = 0.75 + 0.25 * math.sin(fi * 5.1)
                flash = env * flick
                frame += flash * np.array((70, 85, 120), np.float32) * 1.1
                _blend(frame, bolts[(fi // 3) % 2], 0, 0, min(1.0, flash * 1.4), add=True)
            elif pages == 1 and 0.4 < t < 0.7:
                fu = (t - 0.4) / 0.3
                env = math.sin(fu * math.pi)
                _blend(frame, bolts[0], 0, 0, env * 0.9, add=True)
            np.clip(frame, 0, 255, out=frame)
            enc.write(frame.astype(np.uint8).tobytes())
        enc.close()
    except Exception:
        try:
            enc.p.kill()
        except Exception:
            pass
        try:
            os.remove(out_path)
        except Exception:
            pass
        raise
    finally:
        gc.collect()
    return out_path


def most_shared_cleanup(*paths):
    """Delete the temp video (and anything else passed) right after posting + give memory back."""
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception as e:
            log.warning(f"cleanup failed for {p}: {e!r}")
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
