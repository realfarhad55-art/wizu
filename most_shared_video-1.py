"""
most_shared_video.py — 8s (1440x626, 30fps) "MOST SHARED TOKENS TODAY" video — BLACK & YELLOW HAZARD theme.

Timeline:
    0.0 - 3.9s   page 1  (ranks 1-5)   lightning strikes each row as it slides in, count-up, shine
    3.6 - 4.4s   big lightning + flash transition
    4.15 - 8.0s  page 2  (ranks 6-10)  same animation
Title logo = the 3s Wizard Scan video (assets/wizard_logo.mp4), looped inside a hazard ring.

Input  : list of token dicts (rank order, 1..10)
            symbol   str        "ELON2028"   (no $)
            chain    str        "SOL" | "ETH" | "BNB" | "BASE" | "TON" | "RH" | "ARC"
            count    int        number of channels / calls
            ath_mc   float      highest market cap (USD)
            from_mc  float      entry market cap of the best call (USD)
            x        float      ath_mc / from_mc
            logo     bytes|None token logo (png/jpg/webp). None -> coloured letter badge
Output : path of an .mp4 (caller MUST delete it after posting -> see most_shared_cleanup()).

Logo video lookup: env MOST_SHARED_LOGO_VIDEO, assets/wizard_logo.mp4, ./wizard_logo.mp4
                   (falls back to assets/wizard_logo.png, then a plain "W").
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

YEL = (255, 200, 0)
BLK = (10, 10, 10)
GOLD = (255, 216, 58)
DIM = (154, 154, 154)
SUB = (217, 211, 184)


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
    glow = None          # NO glow / shade / outline behind any text (owner request)
    stroke = 0
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
                bg = Image.new("RGBA", im.size, (14, 14, 14, 255))
                bg.alpha_composite(im.convert("RGBA"))
                return _circle(bg, d)
        except Exception as e:
            log.warning(f"logo decode failed for {symbol}: {e!r}")
    return _letter_badge(symbol, d)


# ───────────────────────── hazard art helpers ─────────────────────────
def _stripes(w, h, period=20, phase=0):
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx + yy + phase) % period) < (period // 2)
    arr = np.empty((h, w, 3), np.uint8)
    arr[...] = BLK
    arr[m] = YEL
    return arr


def _rr_mask(w, h, r, ss=4):
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _circle_mask(d, ss=4):
    m = Image.new("L", (d * ss, d * ss), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=255)
    return m.resize((d, d), Image.LANCZOS)


def _hazard_box(w, h, r, border, period=20):
    """striped rounded box with a solid black rounded inner box (border = stripe thickness)."""
    base = Image.fromarray(_stripes(w, h, period), "RGB").convert("RGBA")
    base.putalpha(_rr_mask(w, h, r))
    iw, ih = w - 2 * border, h - 2 * border
    inner = Image.new("RGBA", (iw, ih), BLK + (255,))
    inner.putalpha(_rr_mask(iw, ih, max(2, r - border)))
    base.alpha_composite(inner, (border, border))
    return base


def _hazard_ring(d, border, period=20):
    base = Image.fromarray(_stripes(d, d, period), "RGB").convert("RGBA")
    base.putalpha(_circle_mask(d))
    di = d - 2 * border
    inner = Image.new("RGBA", (di, di), BLK + (255,))
    inner.putalpha(_circle_mask(di))
    base.alpha_composite(inner, (border, border))
    return base


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
    im = Image.new("RGBA", (d, d), (12, 12, 12, 255))
    dr = ImageDraw.Draw(im)
    f = _font(int(d * 0.5))
    dr.text((d * 0.25, d * 0.14), "W", font=f, fill=YEL + (255,))
    return _circle(im, d)


def _logo_frames(d):
    """Frames (RGBA, circle-masked, 30fps) of the 3s title-logo video; falls back to a static logo."""
    p = _first(os.environ.get("MOST_SHARED_LOGO_VIDEO"),
               os.path.join(ASSETS, "wizard_logo.mp4"), os.path.join(HERE, "wizard_logo.mp4"))
    frames = []
    if p:
        try:
            cmd = [_ffmpeg(), "-loglevel", "error", "-i", p, "-an",
                   "-vf", f"scale={d}:{d}:flags=lanczos,fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            raw = subprocess.run(cmd, capture_output=True, timeout=60).stdout
            sz = d * d * 3
            mask = _circle_mask(d)
            for i in range(len(raw) // sz):
                im = Image.frombytes("RGB", (d, d), raw[i * sz:(i + 1) * sz]).convert("RGBA")
                im.putalpha(mask)
                frames.append(im)
        except Exception as e:
            log.warning(f"logo video failed: {e!r}")
    return frames or [_logo_wizard(d)]


_TXT_CACHE = {}


def _txt(text, size, fill, spacing=0.0):
    k = (text, size, fill, spacing)
    v = _TXT_CACHE.get(k)
    if v is None:
        if len(_TXT_CACHE) > 700:
            _TXT_CACHE.clear()
        v = _TXT_CACHE[k] = _text_layer(text, size, fill, spacing=spacing, italic=False)
    return v


def _vcenter(size, ref="0"):
    """y offset so that the glyph box of `ref` is centred on a given line (layer origin -> centre)."""
    b = _font(size).getbbox(ref)
    return (b[1] + b[3]) / 2.0


# ───────────────────────── static art ─────────────────────────
def _background():
    """Near-black with a warm yellow glow in the top-left (like the reference)."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    far = math.hypot(0.7 * W, H)
    r = np.sqrt((xs - 0.3 * W) ** 2 + ys ** 2) / far
    c0 = np.array((42, 34, 0), np.float32)
    c1 = np.array((11, 11, 11), np.float32)
    c2 = np.array((5, 5, 5), np.float32)
    t1 = np.clip(r / 0.55, 0, 1)[..., None]
    t2 = np.clip((r - 0.55) / 0.45, 0, 1)[..., None]
    arr = np.where(r[..., None] < 0.55, c0 * (1 - t1) + c1 * t1, c1 * (1 - t2) + c2 * t2)
    return np.clip(arr, 0, 255).astype(np.uint8)


def _embers(seed=9, n=46):
    rnd = random.Random(seed)
    return [(rnd.random() * W, rnd.random() * H, 12 + rnd.random() * 30, rnd.random() * 6.28,
             1.0 + rnd.random() * 1.8, (rnd.random() - 0.5) * 10) for _ in range(n)]


def _ember_overlay(em, t):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x0, y0, v, ph, s, dx in em:
        y = (y0 - t * v) % H
        x = (x0 + math.sin(t * 1.3 + ph) * 14 + dx * t) % W
        a = 0.25 + 0.45 * max(0.0, math.sin(t * 3 + ph))
        d.ellipse((x - s * 3, y - s * 3, x + s * 3, y + s * 3), fill=(255, 190, 40, int(40 * a)))
        d.ellipse((x - s, y - s, x + s, y + s), fill=(255, 215, 70, int(255 * a)))
    return im


BAR_H = 14
LOGO_RING, LOGO_IN = 86, 72


def _title_layer():
    t, pad = _text_layer("MOST SHARED TOKENS TODAY", 46, YEL, italic=False)
    return t, pad


def _header_layer(page_label):
    """RGBA (W,130) WITHOUT the title (title is blended separately so it can glitch)."""
    L = Image.new("RGBA", (W, 130), (0, 0, 0, 0))
    L.alpha_composite(_hazard_ring(LOGO_RING, 7), (34, 22))
    s, pad = _text_layer("CALLED BY THE MOST CHANNELS  •  ATH = HIGHEST MARKET CAP", 15, SUB,
                         spacing=1.8, italic=False)
    _paste(L, s, 142 - pad, 86 - pad)
    pill = _hazard_box(264, 54, 16, 4, period=16)
    L.alpha_composite(pill, (1141, 24))
    bt, pad = _text_layer("LAST 24 HOURS", 22, YEL, spacing=1.8, italic=False)
    bw = _text_w("LAST 24 HOURS", _font(22), 1.8)
    _paste(L, bt, 1273 - bw / 2 - pad, 51 - _vcenter(22, "H") - pad)
    pt, pad = _text_layer(page_label, 15, (168, 154, 98), spacing=2.0, italic=False)
    pw = _text_w(page_label, _font(15), 2.0)
    _paste(L, pt, 1273 - pw / 2 - pad, 94 - pad)
    return L


def _footer_layer():
    L = Image.new("RGBA", (W, 40), (0, 0, 0, 0))
    txt = "WIZARD SCAN   •   wizardscanlive.com"
    t, pad = _text_layer(txt, 15, (187, 167, 90), spacing=2.2, italic=False)
    tw = _text_w(txt, _font(15), 2.2)
    _paste(L, t, W / 2 - tw / 2 - pad, 6 - pad)
    return L


ROW_X0, ROW_X1, ROW_H, ROW_Y0, ROW_STEP = 60, 1380, 80, 125, 90
ROW_PAD = 22
RW = ROW_X1 - ROW_X0
BADGE = 60
X_CNT, X_SEP, X_ATH, X_ATHV = 600, 924, 946, 1004


def _row_art(rank, tok, hot):
    """Returns dict(final, empty, glow, badge_mask). `empty` = row WITHOUT count + ATH value (count-up draws them)."""
    P = ROW_PAD
    w, h = RW + 2 * P, ROW_H + 2 * P
    # body
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    grad = np.zeros((ROW_H, RW, 3), np.float32)
    xs = np.linspace(0, 1, RW, dtype=np.float32)[None, :, None]
    ca, cb = (np.array((42, 34, 0), np.float32), np.array((17, 17, 17), np.float32)) if hot else \
             (np.array((22, 22, 22), np.float32), np.array((14, 14, 14), np.float32))
    grad = ca * (1 - xs) + cb * xs
    grad = np.broadcast_to(grad, (ROW_H, RW, 3)).astype(np.uint8)
    fill = Image.fromarray(grad, "RGB").convert("RGBA")
    fill.putalpha(_rr_mask(RW, ROW_H, 14))
    body.alpha_composite(fill, (P, P))
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle((P, P, P + RW - 1, P + ROW_H - 1), radius=14,
                         outline=(YEL if hot else (43, 43, 43)) + (255,), width=2)
    glow = None
    if hot:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle((P, P, P + RW - 1, P + ROW_H - 1), radius=14,
                                            outline=YEL + (255,), width=5)
        glow = g.filter(ImageFilter.GaussianBlur(9))

    def put(L, layer, pad, rx, ry):
        _paste(L, layer, P + rx - pad, P + ry - pad)

    # rank badge
    bx, by = 12, (ROW_H - BADGE) // 2
    badge = _hazard_box(BADGE, BADGE, 13, 5, period=20)
    bsz = 28 if rank < 10 else 22
    t, pad = _text_layer(str(rank), bsz, GOLD, italic=False)
    tw = _text_w(str(rank), _font(bsz))
    badge_i = badge.copy()
    _paste(badge_i, t, BADGE / 2 - tw / 2 - pad, BADGE / 2 - _vcenter(bsz) - pad)
    body.alpha_composite(badge_i, (P + bx, P + by))
    bmask = badge.getchannel("A")
    # token logo (yellow ring)
    cx, cy = 120, ROW_H // 2
    ring = Image.new("RGBA", (56, 56), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, 55, 55), fill=YEL + (255,))
    ring.alpha_composite(Image.new("RGBA", (52, 52), BLK + (0,)), (2, 2))
    rm = _circle_mask(56)
    ring.putalpha(rm)
    dk = Image.new("RGBA", (52, 52), BLK + (255,))
    dk.putalpha(_circle_mask(52))
    ring.alpha_composite(dk, (2, 2))
    body.alpha_composite(ring, (P + cx - 28, P + cy - 28))
    lg = _logo_circle(tok.get("logo"), tok.get("symbol", ""), 46)
    body.alpha_composite(lg, (P + cx - 23, P + cy - 23))
    # symbol + chain
    sym = "$" + str(tok.get("symbol", "TOKEN")).upper().lstrip("$")
    sz = 36
    while sz > 22 and _text_w(sym, _font(sz)) > 380:
        sz -= 2
    t, pad = _text_layer(sym, sz, (255, 255, 255), italic=False)
    put(body, t, pad, 166, 6 + (36 - sz) // 3)
    ch = str(tok.get("chain", "")).upper()
    t, pad = _text_layer(ch, 15, YEL, spacing=1.2, italic=False)
    put(body, t, pad, 168, 54)
    # CHANNELS label
    n = int(tok.get("count", 0))
    lab = "CHANNELS" if n != 1 else "CHANNEL"
    lw = _text_w(lab, _font(12), 1.6)
    t, pad = _text_layer(lab, 12, DIM, spacing=1.6, italic=False)
    put(body, t, pad, X_CNT - lw / 2, 58)
    # hazard separator
    body.alpha_composite(Image.fromarray(_stripes(4, 52, 10), "RGB").convert("RGBA"), (P + X_SEP, P + 14))
    # ATH label + FROM line
    t, pad = _text_layer("ATH", 14, DIM, spacing=1.0, italic=False)
    put(body, t, pad, X_ATH, 22)
    fr = f"FROM {fmt_usd(tok.get('from_mc'))}  •  {fmt_x(tok.get('x'))}"
    t, pad = _text_layer(fr, 17, YEL, spacing=0.3, italic=False)
    put(body, t, pad, X_ATH, 52)

    empty = body.copy()
    final = body.copy()
    cnt = str(n)
    t, pad = _text_layer(cnt, 44, YEL, italic=False)
    put(final, t, pad, X_CNT - _text_w(cnt, _font(44)) / 2, 6)
    ath = fmt_usd(tok.get("ath_mc"))
    asz = 42
    while asz > 26 and _text_w(ath, _font(asz)) > 330:
        asz -= 2
    t, pad = _text_layer(ath, asz, (255, 255, 255), italic=False)
    put(final, t, pad, X_ATHV, 6 + (42 - asz) // 3)
    return {"final": final, "empty": empty, "glow": glow, "bmask": bmask,
            "n": n, "ath": float(tok.get("ath_mc") or 0), "asz": asz}


# ───────────────────────── lightning ─────────────────────────
def _jag(x1, y1, x2, y2, r, d, out, lvl):
    if lvl == 0:
        out.append((x2, y2))
        return
    mx = (x1 + x2) / 2 + (r.random() - 0.5) * d
    my = (y1 + y2) / 2 + (r.random() - 0.5) * d
    _jag(x1, y1, mx, my, r, d / 2, out, lvl - 1)
    _jag(mx, my, x2, y2, r, d / 2, out, lvl - 1)


def _build_events(pages, rows_per_page):
    ev = []
    for s in range(pages):
        base = 0.2 if s == 0 else 4.15
        for k in range(rows_per_page[s]):
            r = random.Random(s * 50 + k + 7)
            t0 = base + k * 0.2
            y = ROW_Y0 + k * ROW_STEP + ROW_H // 2
            ev.append(dict(t=t0, life=0.38, x1=220 + r.random() * 900, y1=0, x2=ROW_X0 + 42, y2=y,
                           disp=150, seed=s * 99 + k * 13, w=1.0, f=0.10, br=1))
            ev.append(dict(t=t0 + 0.04, life=0.26, x1=0, y1=y - 20 + r.random() * 40, x2=W,
                           y2=y + (r.random() - 0.5) * 30, disp=60, seed=s * 77 + k * 5 + 1, w=0.6, f=0.0, br=0))
    if pages == 2:
        ev.append(dict(t=3.68, life=0.55, x1=720, y1=0, x2=640, y2=H, disp=200, seed=501, w=1.8, f=0.5, br=1))
        ev.append(dict(t=3.75, life=0.45, x1=280, y1=0, x2=420, y2=H, disp=150, seed=502, w=1.1, f=0.0, br=1))
        ev.append(dict(t=3.80, life=0.45, x1=1150, y1=0, x2=980, y2=H, disp=150, seed=503, w=1.1, f=0.0, br=1))
        ev.append(dict(t=6.20, life=0.40, x1=500, y1=0, x2=420, y2=330, disp=130, seed=602, w=1.0, f=0.12, br=1))
        ev.append(dict(t=7.35, life=0.50, x1=760, y1=0, x2=700, y2=H, disp=190, seed=603, w=1.5, f=0.30, br=1))
    ev.append(dict(t=2.20, life=0.40, x1=900, y1=0, x2=1000, y2=300, disp=130, seed=601, w=1.0, f=0.12, br=1))
    return ev


def _bolt_alpha(age, life):
    a = 1.0 if age < 0.06 else (1.0 if math.sin(age * 95) > -0.2 else 0.3)
    a *= max(0.0, 1 - age / life)
    return min(1.0, a * 1.3)


def _draw_bolts(frame, ev, t):
    act = [e for e in ev if 0 <= t - e["t"] < e["life"]]
    if not act:
        return
    hw, hh = W // 2, H // 2
    gl = Image.new("L", (hw, hh), 0)
    c1 = Image.new("L", (W, H), 0)
    c2 = Image.new("L", (W, H), 0)
    dg, d1, d2 = ImageDraw.Draw(gl), ImageDraw.Draw(c1), ImageDraw.Draw(c2)

    def stroke(p, w, a):
        v = int(255 * a)
        dg.line([(x / 2, y / 2) for x, y in p], fill=v, width=max(1, int(9 * w / 2)), joint="curve")
        d1.line(p, fill=v, width=max(1, int(3.6 * w)), joint="curve")
        d2.line(p, fill=v, width=max(1, int(1.4 * w + 0.5)), joint="curve")

    for e in act:
        age = t - e["t"]
        r = random.Random(e["seed"] * 31 + int(age / 0.045))
        pts = [(e["x1"], e["y1"])]
        _jag(e["x1"], e["y1"], e["x2"], e["y2"], r, e["disp"], pts, 6)
        a = _bolt_alpha(age, e["life"])
        stroke(pts, e["w"], a)
        if e["br"]:
            for _ in range(3):
                i = int(len(pts) * (0.2 + r.random() * 0.6))
                sx, sy = pts[i]
                dr_ = -1 if r.random() < 0.5 else 1
                q = [(sx, sy)]
                _jag(sx, sy, sx + dr_ * (60 + r.random() * 120), sy + 50 + r.random() * 110, r, 50, q, 4)
                stroke(q, e["w"] * 0.45, a * 0.8)
    g = np.asarray(gl.filter(ImageFilter.GaussianBlur(5)).resize((W, H), Image.BILINEAR), np.float32) / 255.0
    k1 = np.asarray(c1.filter(ImageFilter.GaussianBlur(0.7)), np.float32) / 255.0
    k2 = np.asarray(c2.filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255.0
    frame += g[..., None] * np.array((255, 170, 0), np.float32) * 0.85
    frame += k1[..., None] * np.array((255, 215, 50), np.float32)
    frame += k2[..., None] * np.array((255, 255, 235), np.float32)


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


def _ath_text(v, cp):
    return fmt_usd(v) if cp >= 0.999 else fmt_usd(max(1.0, v * cp))


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
    em = _embers()
    ember_frames = [_ember_overlay(em, k / FPS) for k in range(0, NFRAMES, 2)]   # 15 fps twinkle, reused
    footer = _footer_layer()
    title, tpad = _title_layer()
    headers = [_header_layer("TOP 1 – 5")] + ([_header_layer("TOP 6 – 10")] if pages == 2 else [])
    logo = _logo_frames(LOGO_IN)
    strip_t = _stripes(W + 40, BAR_H, 28)
    strip_t = np.concatenate([strip_t, strip_t], axis=1)
    rows = []
    for p in range(pages):
        pr = []
        for i, tk in enumerate(_page_tokens(tokens, p)):
            rank = p * 5 + i + 1
            pr.append(_row_art(rank, tk, hot=(rank == 1)))
        rows.append(pr)
    ev = _build_events(pages, [len(r) for r in rows])
    shine_w = 150
    shine = np.zeros((ROW_H + 2 * ROW_PAD, shine_w), np.float32)
    for xx in range(shine_w):
        shine[:, xx] = max(0.0, 1 - abs(xx - shine_w / 2) / (shine_w / 2)) ** 1.6
    for yy in range(shine.shape[0]):
        shine[yy] = np.roll(shine[yy], int((yy - shine.shape[0] / 2) * 0.55))
    yy_b, xx_b = np.mgrid[0:BADGE, 0:BADGE].astype(np.float32)

    enc = _Enc(out_path)
    try:
        for fi in range(NFRAMES):
            t = fi / FPS
            frame = bg.astype(np.float32)
            frame += 0  # float copy
            # hazard bars (opposite directions)
            off = int(t * 45) % 28
            frame[0:BAR_H] = strip_t[:, off:off + W]
            frame[H - BAR_H:H] = strip_t[:, 28 - off:28 - off + W] if off else strip_t[:, 0:W]
            # embers
            _blend(frame, ember_frames[(fi // 2) % len(ember_frames)], 0, 0, 1.0, add=True)
            # flash level from bolts
            fl = 0.0
            for e in ev:
                a = t - e["t"]
                if a >= 0 and e["f"]:
                    fl += e["f"] * math.exp(-a * 16)
            fl = min(0.7, fl)
            # header + title (glitch while flashing) + logo video
            ha = _ease_out((t - 0.02) / 0.4)
            hp = 0 if (pages == 1 or t < 3.95) else 1
            _blend(frame, headers[hp], 0, 0, ha)
            gx = 2 if (fl > 0.15 and math.sin(t * 120) > 0) else 0
            _blend(frame, title, 142 - tpad + gx, 20 - tpad, ha)
            _blend(frame, footer, 0, H - 52, ha)
            _blend(frame, logo[fi % len(logo)], 34 + (LOGO_RING - LOGO_IN) // 2, 22 + (LOGO_RING - LOGO_IN) // 2, ha)
            # rows
            for page in range(pages):
                base = 0.2 if page == 0 else 4.15
                for k, ra in enumerate(rows[page]):
                    p_ = (t - (base + k * 0.2)) / 0.5
                    if p_ <= 0:
                        continue
                    al, dx = 1.0, 0.0
                    if page == 0 and pages == 2 and t >= 3.55 + k * 0.04:
                        q = min(1.0, (t - 3.55 - k * 0.04) / 0.32)
                        al, dx = 1 - q, q * q * 140
                        if t >= 3.95:
                            continue
                    else:
                        u = _ease_out(p_)
                        dx = (1 - u) * -110
                        al = min(1.0, p_ * 3)
                        if p_ < 0.4 and math.sin(t * 75) <= -0.3:
                            al *= 0.35
                    if al <= 0.001:
                        continue
                    x = ROW_X0 - ROW_PAD + dx
                    y = ROW_Y0 + k * ROW_STEP - ROW_PAD
                    cp = _ease_out((t - (base + k * 0.2) - 0.05) / 0.9)
                    if ra["glow"] is not None:
                        g = 0.5 + 0.5 * math.sin(t * 4.2)
                        _blend(frame, ra["glow"], x, y, al * (0.45 + 0.35 * g))
                    if cp < 0.999:
                        _blend(frame, ra["empty"], x, y, al)
                        n_ = int(round(ra["n"] * cp))
                        ct, cpad = _txt(str(n_), 44, YEL)
                        cw = _text_w(str(n_), _font(44))
                        _blend(frame, ct, x + ROW_PAD + X_CNT - cw / 2 - cpad, y + ROW_PAD + 6 - cpad, al)
                        at, apad = _txt(_ath_text(ra["ath"], cp), ra["asz"], (255, 255, 255))
                        _blend(frame, at, x + ROW_PAD + X_ATHV - apad, y + ROW_PAD + 6 + (42 - ra["asz"]) // 3 - apad, al)
                    else:
                        _blend(frame, ra["final"], x, y, al)
                    done = p_ >= 1.0 and al > 0.99 and dx == 0
                    # badge shine (every 2.2s, staggered)
                    if done:
                        ph = ((t - (base + k * 0.2) - 0.5) + k * 0.35) % 2.2
                        bs = ph / 0.7
                        if 0 <= bs <= 1:
                            c = -30 + bs * 100
                            band = np.clip(1 - np.abs((xx_b + 0.36 * (yy_b - BADGE / 2)) - c) / 15.0, 0, 1)
                            m = np.asarray(ra["bmask"], np.float32) / 255.0
                            bx0, by0 = int(ROW_X0 + 12), int(ROW_Y0 + k * ROW_STEP + (ROW_H - BADGE) // 2)
                            frame[by0:by0 + BADGE, bx0:bx0 + BADGE] += (band * m * 105)[..., None]
                        # row shine sweep (yellow) once per row, after entrance
                        ss = base + k * 0.2 + 0.7
                        su = (t - ss) / 0.8
                        if 0.0 <= su <= 1.0:
                            sx = int(ROW_X0 + (RW + shine_w) * su - shine_w)
                            ral = np.asarray(ra["final"])[..., 3].astype(np.float32) / 255.0
                            gx0 = sx - (ROW_X0 - ROW_PAD)
                            reg = np.zeros_like(ral)
                            a0, a1 = max(0, gx0), min(reg.shape[1], gx0 + shine_w)
                            if a1 > a0:
                                reg[:, a0:a1] = shine[:, a0 - gx0:a1 - gx0]
                                reg *= ral
                                sub = frame[int(y):int(y) + reg.shape[0], ROW_X0 - ROW_PAD:ROW_X0 - ROW_PAD + reg.shape[1]]
                                sub += reg[..., None] * np.array((255, 215, 90), np.float32) * 0.35
            # lightning + flash
            _draw_bolts(frame, ev, t)
            if fl > 0:
                frame += (255.0 - frame) * (np.array((255, 243, 176), np.float32) / 255.0) * (fl * 0.6)
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
        _TXT_CACHE.clear()
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
