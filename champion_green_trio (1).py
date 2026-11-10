"""
champion_green_trio.py - native 1600x640 (2.5:1, fomo size) renderer for the three champion designs:
    design="area"   -> area chart (35x style)
    design="orbit"  -> orbit nodes (45x style)
    design="matrix" -> matrix rain terminal (40x style)

Common effects: electric lightning crackling INSIDE the big neon number, a full-screen FLASH the moment the
multiplier lands, lightning in the rank box / logo / channel name, count-up stats.

    build_green_video(design="matrix", x_val=40, color="green", kol_name="Pumpwatch1", ..., out_path="out.mp4")

Needs champion_rocket_neon.py + champion_gauge_neon.py next to this file (shared helpers) and golden_logo.jpg/png.
"""
import math, os, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import champion_rocket_neon as rk
from champion_rocket_neon import (W, H, FPS, K, px, blur, jag, font, F_BOLD, F_REG, fmt_mc, ease_io, ease_out,
                                  circle_crop, ffmpeg_bin, TITLE_X, TITLE_Y, LOGO, KOL, RANK, FRAME)

DUR = 6.0
HERE = os.path.dirname(os.path.abspath(__file__))
# Neon palettes (same tier colours as champion_video.py PALETTES; "sub" is the
# bright mid-tone used for small labels). Picked by the `color` param of
# build_green_video (default "green"); a new theme is a one-line change.
PALETTES = {
    "green":  dict(n=(40, 255, 110), hot=(220, 255, 232), tx=(214, 255, 230), sub=(110, 255, 160)),
    "purple": dict(n=(170, 80, 255), hot=(236, 220, 255), tx=(232, 214, 255), sub=(190, 130, 255)),
    "bw":     dict(n=(255, 255, 255), hot=(255, 255, 255), tx=(240, 240, 240), sub=(220, 220, 220)),
}
def palette_for(color):
    return PALETTES.get(color, PALETTES["green"])
def _derive(pal):
    """Derived shades from a palette (dark fill, line, number interior, fringe)."""
    n = np.array(pal["n"], np.float32); hot = np.array(pal["hot"], np.float32)
    return dict(
        dark=(n * 0.25).astype(np.float32),
        line=(n * 0.9).astype(np.float32),
        base_int=(n * 0.5).astype(np.float32),
        edge_c=(n * 0.85).astype(np.float32),
        fringe=((n * 0.6 + hot * 0.4)).astype(np.float32),
    )
BOXC = np.array((2, 26, 11), np.float32)        # fill colour of the boxes (measured)
MONO = rk._find("DejaVuSansMono-Bold.ttf", "Poppins-Bold.ttf")
DESIGN = dict(
    area=dict(num_c=(227, 213.75), sub_c=(222, 313.875), size=160.875),
    orbit=dict(num_c=(570, 213.75), sub_c=(563, 313.875), size=163.125),
    matrix=dict(num_c=(570, 210.375), sub_c=(570, 333.0), size=190.125),
)


def ptext(fr, s, path, size, x, y, fill, anchor="m"):
    """draw text (size in design px) with anchor l / m / r horizontally, centred vertically at y."""
    f = font(path, size * K * 2)
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, t, r, b = tmp.textbbox((0, 0), s, font=f, anchor="ls")
    pad = 6
    im = Image.new("RGBA", ((r - l) + pad * 2, int(size * K * 2 * 1.5) + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad - l, pad + int(size * K * 2 * 1.1)), s, font=f, fill=fill, anchor="ls")
    w2, h2 = (im.width + 1) // 2, (im.height + 1) // 2
    im = im.resize((w2, h2), Image.LANCZOS)
    arr = np.asarray(im, np.float32)
    cx = x * K
    x0 = int(round(cx - w2 / 2)) if anchor == "m" else (int(round(cx)) - pad // 2 if anchor == "l" else int(round(cx - w2 + pad // 2)))
    y0 = int(round(y * K - (pad + size * K * 1.1 - size * K * 0.36) / 1.0 * 0 - h2 / 2 + size * K * 0.05))
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(W, x0 + w2), min(H, y0 + h2)
    if xb <= xa or yb <= ya:
        return
    sub = arr[ya - y0:yb - y0, xa - x0:xb - x0]
    reg = fr[ya:yb, xa:xb]
    a = sub[..., 3:4] / 255.
    reg[:] = reg * (1 - a) + sub[..., :3] * a



def est_bg(ref_png, excl, thr=48, sigma=34, cache=None):
    """Background colour map estimated from the design image: pixels that are not foreground
    (dark enough, outside `excl` rectangles) are smoothed with a normalised blur -> (H,W,3) float for 1600x640."""
    if cache and os.path.exists(cache):
        low = np.asarray(Image.open(cache).convert("RGB"), np.float32)
    else:
        ref = np.asarray(Image.open(ref_png).convert("RGB"), np.float32)
        h, w = ref.shape[:2]
        m = (ref[..., 1] < thr).astype(np.float32)
        for item in excl:
            if item and item[0] == "poly":
                pm = Image.new("L", (w, h), 0)
                ImageDraw.Draw(pm).polygon(item[1], fill=255)
                m[np.asarray(pm) > 0] = 0
            else:
                x0, y0, x1, y1 = item
                m[y0:y1, x0:x1] = 0
        num = np.stack([blur_f(ref[..., c] * m, sigma) for c in range(3)], -1)
        den = blur_f(m, sigma)[..., None]
        den2 = blur_f(m, sigma * 3)[..., None]
        num2 = np.stack([blur_f(ref[..., c] * m, sigma * 3) for c in range(3)], -1)
        low = np.where(den > 0.02, num / np.maximum(den, 1e-4), num2 / np.maximum(den2, 1e-4))
        low = np.asarray(Image.fromarray(np.clip(low, 0, 255).astype(np.uint8)).resize((w // 4, h // 4), Image.LANCZOS), np.float32)
        if cache:
            Image.fromarray(low.astype(np.uint8)).save(cache)
    up = Image.fromarray(np.clip(low, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    return np.asarray(up, np.float32)


def blur_f(a, sigma):
    """float gaussian blur (separable, numpy)"""
    r = int(sigma * 3)
    k = np.exp(-(np.arange(-r, r + 1) ** 2) / (2.0 * sigma * sigma)).astype(np.float32); k /= k.sum()
    pad = np.pad(a.astype(np.float32), ((r, r), (r, r)), mode="edge")
    out = np.zeros_like(pad)
    for i, kv in enumerate(k):
        out[:, r:-r] += kv * pad[:, i:i + a.shape[1]] if False else 0
    tmp = np.zeros((pad.shape[0], a.shape[1]), np.float32)
    for i, kv in enumerate(k):
        tmp += kv * pad[:, i:i + a.shape[1]]
    res = np.zeros(a.shape, np.float32)
    for i, kv in enumerate(k):
        res += kv * tmp[i:i + a.shape[0], :]
    return res


# ------------------------------------------------------------------ header (common) ------
def build_header(kol_name, rank, avatar_path, logo_path, sub_c, symbol, chain, pal=None):
    p = pal or PALETTES["green"]
    n = np.array(p["n"], np.float32)
    SS = 2
    S = lambda v: v * K * SS
    big = (W * SS, H * SS)
    lines = Image.new("L", big, 0); ld = ImageDraw.Draw(lines)
    fills = Image.new("L", big, 0); fd = ImageDraw.Draw(fills)
    lw = int(S(2.2))
    ld.rounded_rectangle((S(FRAME[0]), S(FRAME[1]), S(FRAME[2]), S(FRAME[3])), S(20), outline=255, width=lw)
    for b in (KOL, RANK):
        ld.rounded_rectangle((S(b[0]), S(b[1]), S(b[2]), S(b[3])), S(14), outline=255, width=lw)
        fd.rounded_rectangle((S(b[0]), S(b[1]), S(b[2]), S(b[3])), S(14), fill=255)
    ax, ay, ar = 93, 56.25, 18  # safe-zone: avatar fully inside the KOL box (was 53,50,16)
    ld.ellipse((S(ax - ar), S(ay - ar), S(ax + ar), S(ay + ar)), outline=255, width=int(S(2)))
    lm = np.asarray(lines.resize((W, H), Image.LANCZOS), np.float32) / 255.
    fm = np.asarray(fills.resize((W, H), Image.LANCZOS), np.float32) / 255.
    tl = Image.new("RGBA", big, (0, 0, 0, 0)); td = ImageDraw.Draw(tl)
    fb = lambda sz: font(F_BOLD, S(sz))

    def txt(xy, s, f, fill, anchor="mm"):
        td.text((S(xy[0]), S(xy[1])), s, font=f, fill=fill, anchor=anchor)
    if avatar_path and os.path.exists(avatar_path):
        av = circle_crop(Image.open(avatar_path), int(S(2 * ar - 2)))
        tl.paste(av, (int(S(ax - ar + 1)), int(S(ay - ar + 1))), av)
    else:
        td.ellipse((S(ax - ar + 1), S(ay - ar + 1), S(ax + ar - 1), S(ay + ar - 1)), fill=(8, 8, 8, 255))
        txt((ax, ay - 5.0625), "PUMP", fb(7.65), (*p["sub"], 255))
        txt((ax, ay + 5.0625), "WATCH", fb(7.65), (*p["sub"], 255))
    name = (kol_name or "KOL").lstrip("@")
    sz = 22
    while sz > 10 and font(F_BOLD, S(sz)).getlength(name) > S(168):
        sz -= 1
    txt((126, 43.875), name, fb(sz), (255, 255, 255, 255), "lm")
    txt((126, 73.125), "CHAMPION KOL \u00b7 X ALERT", fb(9.675), (*p["sub"], 255), "lm")
    x0 = TITLE_X
    for part, fnt, col in (("Wizard ", fb(24.75), (255, 255, 255, 255)), ("Scan", fb(24.75), (*p["sub"], 255)),
                           (" Call Tracker", font(F_REG, S(24.75)), (255, 255, 255, 255))):
        txt((x0, TITLE_Y), part, fnt, col, "lm")
        x0 += fnt.getlength(part) / (K * SS)
    txt((999, 40.5), "RANK ON WIZARDSCANLIVE", fb(9), (240, 240, 245, 255))
    lgx, lgy, lgr = LOGO
    la = Image.new("L", big, 0)
    if logo_path and os.path.exists(logo_path):
        lg = circle_crop(Image.open(logo_path), int(S(2 * lgr)))
        tl.paste(lg, (int(S(lgx - lgr)), int(S(lgy - lgr))), lg)
    else:
        td.ellipse((S(lgx - lgr), S(lgy - lgr), S(lgx + lgr), S(lgy + lgr)), fill=(8, 8, 8, 255), outline=(255, 190, 0, 255), width=int(S(2.6)))
        txt((lgx, lgy + 0.5625), "W", font(F_BOLD, S(27)), (255, 190, 0, 255))
    ImageDraw.Draw(la).ellipse((S(lgx - lgr + 3), S(lgy - lgr + 3), S(lgx + lgr - 3), S(lgy + lgr - 3)), outline=255, width=int(S(3)))
    lam = np.asarray(la.resize((W, H), Image.LANCZOS), np.float32) / 255.
    gl = Image.new("L", big, 0); gd = ImageDraw.Draw(gl)
    gt = Image.new("RGBA", big, (0, 0, 0, 0)); gtd = ImageDraw.Draw(gt)
    fr_ = font(F_BI if False else rk.F_BI, S(31))
    gd.text((S(999), S(69.75)), f"#{rank}", font=fr_, fill=255, anchor="mm")
    gtd.text((S(999), S(69.75)), f"#{rank}", font=fr_, fill=(235, 255, 240, 255), anchor="mm")
    sub = f"${(symbol or 'TOKEN').upper()} \u00b7 {(chain or 'SOL').upper()}"
    fs = fb(23.625)
    gd.text((S(sub_c[0]), S(sub_c[1])), sub, font=fs, fill=255, anchor="mm")
    gtd.text((S(sub_c[0]), S(sub_c[1])), sub, font=fs, fill=(*p["sub"], 255), anchor="mm")
    gm = np.asarray(gl.resize((W, H), Image.LANCZOS), np.float32) / 255.
    text_rgba = np.asarray(tl.resize((W, H), Image.LANCZOS), np.float32)
    gtext_rgba = np.asarray(gt.resize((W, H), Image.LANCZOS), np.float32)
    glow_n = blur(lm, 2.7) + blur(lm, 7.7) * 0.85 + blur(lm, 17.6) * 0.30
    glow_t = blur(gm, 3.0) * 0.9 + blur(gm, 8.2) * 0.5
    G = n * (glow_n + glow_t)[..., None] * 0.55
    G += np.array((255, 190, 0), np.float32) * (blur(lam, 3.5) * 0.7 + blur(lam, 9.4) * 0.4)[..., None] * 0.35
    return dict(G=G.astype(np.float32), lm=lm, fm=fm, text=text_rgba, gtext=gtext_rgba)


def hdr_masks():
    out = {}
    SS = 2
    for k, b in (("kol", KOL), ("rank", RANK)):
        x0, y0, x1, y1 = [int(round(v * K)) for v in b]
        m = Image.new("L", ((x1 - x0) * SS, (y1 - y0) * SS), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, (x1 - x0) * SS - 1, (y1 - y0) * SS - 1), 14 * K * SS, fill=255)
        out[k] = ((x0, y0, x1, y1), np.asarray(m.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32) / 255.)
    return out


# ------------------------------------------------------------------ neon outline number ----
class NeonNum:
    def __init__(self, size_design, pal=None):
        self.size = size_design * K
        self.pal = pal or PALETTES["green"]
        self.drv = _derive(self.pal)
        self.cache = {}

    def layer(self, s):
        if s in self.cache:
            return self.cache[s]
        f = font(F_BOLD, self.size)
        bw, bh = int(px(520)), int(px(281.25))
        c = (bw // 2, bh // 2)

        def mask(sw):
            m = Image.new("L", (bw, bh), 0)
            ImageDraw.Draw(m).text(c, s, font=f, fill=255, anchor="mm", stroke_width=sw, stroke_fill=255)
            return m
        m0, m1, mo = mask(0), mask(2), mask(10)
        er = m0.filter(ImageFilter.MinFilter(3))
        a0 = np.asarray(m0, np.float32) / 255.
        a1 = np.asarray(m1, np.float32) / 255.
        ae = np.asarray(er, np.float32) / 255.
        ao = np.asarray(mo, np.float32) / 255.
        hair = np.clip(a1 - ae, 0, 1)                                   # thin white edge line
        glow_out = np.clip(blur(a0, 6.0) * 2.0, 0, 1) * (1 - a0)        # neon falloff outside the glyph
        ig = np.clip(blur(1 - a0, 10.0) * 2.0, 0, 1)                    # inner glow (bright at edge, fades inward)
        fringe = np.clip(blur(hair, 1.6) * 1.6, 0, 1)
        pts = np.argwhere(ae > 0.5)
        edge = np.argwhere(hair > 0.6)
        out = dict(glow_out=glow_out.astype(np.float32), ig=ig.astype(np.float32), a0=a0, hair=hair,
                   fringe=fringe.astype(np.float32), amb=(blur(ao, 22.0)).astype(np.float32), clip=ao,
                   pts=pts[::29] if len(pts) else pts, edge=edge[::19] if len(edge) else edge, bw=bw, bh=bh)
        if len(self.cache) > 70:
            self.cache.clear()
        self.cache[s] = out
        return out

    def region(self, center):
        bw, bh = int(px(520)), int(px(281.25))
        return int(px(center[0]) - bw / 2), int(px(center[1]) - bh / 2), bw, bh

    def draw(self, fr, s, center, pulse, alpha=1.0, flash=0.0, scale_flick=1.0):
        n = np.array(self.pal["n"], np.float32); hot = np.array(self.pal["hot"], np.float32)
        L = self.layer(s)
        x0, y0, bw, bh = self.region(center)
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + bw), min(H, y0 + bh)
        sl = (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
        reg = fr[ya:yb, xa:xb]
        k = alpha * pulse
        reg += n * (L["glow_out"][sl] * 1.12 * k + L["amb"][sl] * 0.16 * k)[..., None]
        base_int = self.drv["base_int"]
        edge_c = self.drv["edge_c"]
        ig = L["ig"][sl][..., None]
        interior = (base_int * (1 - ig) + edge_c * ig) * scale_flick
        if flash > 0:
            interior = interior * (1 - flash * 0.7) + 255 * flash * 0.7
        a0 = (L["a0"][sl] * alpha)[..., None]
        reg[:] = reg * (1 - a0) + interior * a0
        fr_ = (L["fringe"][sl] * 0.9 * alpha)[..., None]
        reg[:] = reg * (1 - fr_) + self.drv["fringe"] * fr_
        h = (L["hair"][sl] * alpha)[..., None]
        reg[:] = reg * (1 - h) + hot * h

    def lightning(self, fr, s, center, rng, intensity=1.0, bolts=4):
        n = np.array(self.pal["n"], np.float32)
        L = self.layer(s)
        if len(L["pts"]) < 4:
            return
        x0, y0, bw, bh = self.region(center)
        lay = Image.new("L", (bw, bh), 0); d = ImageDraw.Draw(lay)
        spk = Image.new("L", (bw, bh), 0); sd = ImageDraw.Draw(spk)
        pts = L["pts"]
        for _ in range(bolts):
            a = pts[rng.randrange(len(pts))]; b = pts[rng.randrange(len(pts))]
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) < 40:
                continue
            seg = jag(a[1], a[0], b[1], b[0], rng, 9, 11)
            d.line(seg, fill=255, width=2)
            if rng.random() < 0.6:
                m = seg[len(seg) // 2]
                d.line(jag(m[0], m[1], m[0] + rng.uniform(-60, 60), m[1] + rng.uniform(-40, 40), rng, 5, 7), fill=200, width=1)
        if len(L["edge"]):
            for _ in range(int(3 + bolts)):
                e = L["edge"][rng.randrange(len(L["edge"]))]
                an = rng.uniform(0, 2 * math.pi); ln = rng.uniform(14, 40) * K / 1.7
                sd.line(jag(e[1], e[0], e[1] + ln * math.cos(an), e[0] + ln * math.sin(an), rng, 4, 4), fill=255, width=2)
        la = np.asarray(lay, np.float32) / 255. * np.clip(L["clip"] * 1.6, 0, 1)
        sa = np.asarray(spk, np.float32) / 255.
        comb = np.clip(la + sa, 0, 1)
        gl = blur(comb, 3.2)
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + bw), min(H, y0 + bh)
        sl = (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
        reg = fr[ya:yb, xa:xb]
        reg += (n * 0.6 + 90) * (gl[sl] * 1.6 * intensity)[..., None]
        reg += 255 * (comb[sl] * 0.95 * intensity)[..., None]


# ------------------------------------------------------------------ design: area chart ---
AREA_PTS = [(418, 340.875), (435, 338.625), (447, 342), (458, 348.75), (468, 340.875), (480, 336.375), (492, 343.125), (500, 344.25), (512, 339.75), (525, 335.25), (537, 331.875), (547, 336.375), (556, 333), (566, 328.5), (576, 334.125), (588, 329.625), (596, 333), (606, 327.375), (618, 322.875), (630, 320.625), (642, 320.625), (655, 321.75), (668, 322.875), (675, 324), (686, 315), (698, 307.125), (712, 303.75), (727, 302.625), (740, 302.625), (752, 300.375), (765, 293.625), (780, 286.875), (793, 279), (806, 276.75), (818, 276.75), (830, 258.75), (842, 257.625), (851, 258.75), (860, 249.75), (872, 239.625), (886, 232.875), (898, 225), (910, 218.25), (922, 212.625), (934, 207), (947, 203.625), (955, 198), (965, 185.625), (975, 180), (985, 174.375), (995, 167.625), (1005, 158.625), (1015, 150.75), (1028, 140.625), (1040, 133.875), (1054, 129.375), (1068, 126)]
BG_EXCL = dict(
    area=[(60, 106.875, 400, 343.125), ("poly", [(x, y - 3) for x, y in AREA_PTS] + [(1068, 362.25), (418, 362.25)]), (1060, 106.875, 1082, 146.25), (20, 351.0, 1075, 450.0), (20, 16.875, 270, 95.625), (895, 16.875, 1105, 95.625), (375, 16.875, 450, 95.625)],
)

A_COLS = dict(entry=(42, 268), now=(285, 510), points=(528, 680), calls=(696, 846), win=(864, 1062))
A_LAB = dict(entry="ENTRY MC", now="NOW", points="POINTS", calls="CALLS", win="WIN RATE")


def area_static():
    """static layer: bottom columns (gradient + glowing base line) -> (fill_rgb_alpha, line_mask)"""
    SS = 2
    S = lambda v: v * K * SS
    ln = Image.new("L", (W * SS, H * SS), 0); d = ImageDraw.Draw(ln)
    for k, (x0, x1) in A_COLS.items():
        d.rounded_rectangle((S(x0), S(423.5625), S(x1), S(426.5625)), S(1.5), fill=255)  # 3px capsule, like the original (376.5-379.5)
    lm = np.asarray(ln.resize((W, H), Image.LANCZOS), np.float32) / 255.
    colfill = np.zeros((H, W), np.float32)
    for k, (x0, x1) in A_COLS.items():
        xa, xb = int(x0 * K), int(x1 * K)
        ya, yb = int(357.75 * K), int(425.25 * K)
        g = (np.linspace(0, 1, yb - ya, dtype=np.float32) ** 1.4)[:, None]
        colfill[ya:yb, xa:xb] = g * 0.95
    return lm, colfill


def draw_area(fr, t, ctx):
    n = ctx["n"]; hot = ctx["hot"]
    # grid dashes + y labels
    lay = Image.new("L", (W, H), 0); d = ImageDraw.Draw(lay)
    for yv in (120.375, 195.75, 271.125, 346.5):
        off = (t * 14) % 12
        x = 415.0 - off
        while x < 1068:
            xa, xb = max(415.0, x), min(1068.0, x + 6)
            if xb > xa:
                d.line((xa * K, yv * K, xb * K, yv * K), fill=255, width=2)
            x += 12
    gm = np.asarray(lay, np.float32) / 255.
    fr[:] = fr * (1 - (gm * 0.9)[..., None]) + ctx["dark"] * (gm * 0.9)[..., None]
    for yv, lab in ctx["area_labels"]:
        ptext(fr, lab, F_BOLD, 10.125, 411, yv, (*ctx["label"], 255), "r")
    # chart reveal
    prog = ease_io((t - 0.45) / 1.7) if t >= 0.45 else 0.0
    if prog <= 0.003:
        return None
    pts = [(x * K, (y + 1.4625 * math.sin(t * 2.1 + i * 1.7)) * K) for i, (x, y) in enumerate(AREA_PTS)]
    xhead = pts[0][0] + (pts[-1][0] - pts[0][0]) * prog
    vis = [p_ for p_ in pts if p_[0] <= xhead]
    if len(vis) < len(pts):
        i = len(vis)
        if i < len(pts) and i > 0:
            a, b = pts[i - 1], pts[i]
            u = (xhead - a[0]) / max(1e-6, b[0] - a[0])
            vis.append((xhead, a[1] + (b[1] - a[1]) * u))
    if len(vis) < 2:
        return None
    x0r, y0r, x1r, y1r = int(405 * K), int(106.875 * K), int(1085 * K), int(362.25 * K)
    SS = 2
    wh, hh = x1r - x0r, y1r - y0r
    pm = Image.new("L", (wh * SS, hh * SS), 0)
    poly = [((x - x0r) * SS, (y - y0r) * SS) for x, y in vis]
    ImageDraw.Draw(pm).polygon(poly + [(poly[-1][0], hh * SS), (poly[0][0], hh * SS)], fill=255)
    area = np.asarray(pm.resize((wh, hh), Image.BOX), np.float32) / 255.
    lm_ = Image.new("L", (wh * SS, hh * SS), 0)
    ImageDraw.Draw(lm_).line(poly, fill=255, width=int(3.0 * K * SS / 1.7), joint="curve")
    ln = np.asarray(lm_.resize((wh, hh), Image.BOX), np.float32) / 255.
    ys_d = (np.arange(hh, dtype=np.float32) + y0r) / K            # design-space y of each row
    _u = np.clip((ys_d - 106.875) / max(1.0, 362.25 - 106.875), 0, 1)
    gcol = np.clip(98 - 84 * _u, 14, 98)[:, None]
    reg = fr[y0r:y1r, x0r:x1r]
    fillc = ((n / max(1.0, float(n.max()))) * gcol)[..., None, :] * np.ones((1, wh, 1), np.float32)  # palette-tinted fill (was hardcoded green)
    reg[:] = reg * (1 - area[..., None]) + fillc * area[..., None]
    reg += n * (blur(ln, 3.4) * 0.8 + blur(ln, 10.0) * 0.5)[..., None] * 0.7 * ctx["pulse"]
    a = ln[..., None]
    reg[:] = reg * (1 - a) + ctx["line"] * a
    core = (ln > 0.5).astype(np.float32)
    core_l = Image.fromarray((core * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
    core_a = (np.asarray(core_l, np.float32) / 255.)[..., None]
    reg[:] = reg * (1 - core_a * 0.9) + hot * (core_a * 0.9)
    # end marker
    ex, ey = vis[-1]
    gy_, gx_ = np.mgrid[0:hh, 0:wh].astype(np.float32)
    dist = np.sqrt((gx_ - (ex - x0r)) ** 2 + (gy_ - (ey - y0r)) ** 2)
    reg += n * (np.exp(-((dist / px(20.25)) ** 2)) * 0.9)[..., None]
    ring = np.clip(px(9.5625) + 1 - dist, 0, 1)[..., None]
    reg[:] = reg * (1 - ring) + n * ring
    core = np.clip(px(5.85) + 1 - dist, 0, 1)[..., None]
    reg[:] = reg * (1 - core) + 255 * core
    if prog >= 1:
        for k in range(2):
            u = ((t - 2.2) * 0.8 + k * 0.5) % 1.0
            rr = px(10.125 + 38.25 * u)
            reg += n * (np.exp(-(((dist - rr) / px(2.475)) ** 2)) * (1 - u) * 0.9)[..., None]
    return (ex, ey)


def draw_area_bottom(fr, t, ctx, vals):
    n = ctx["n"]
    lm, colfill = ctx["area_static"]
    fr[:] = fr * (1 - (colfill * ctx["pw"])[..., None]) + ctx["dark"] * (colfill * ctx["pw"])[..., None]
    fr += n * (blur(lm, 4.0) * 1.0 + blur(lm, 11.0) * 0.8)[..., None] * 0.9 * ctx["pulse"]
    fr[:] = fr * (1 - (lm * ctx["pw"])[..., None]) + n * (lm * ctx["pw"])[..., None]
    # travelling highlight on the base lines
    for i, (k, (x0, x1)) in enumerate(A_COLS.items()):
        u = ((t * 0.55 + i * 0.17) % 1.0)
        hx = (x0 + (x1 - x0) * u) * K
        gy_, gx_ = slice(int(411.75 * K), int(436.5 * K)), slice(max(0, int(hx - 80)), min(W, int(hx + 80)))
        yy, xx = np.mgrid[gy_, gx_].astype(np.float32)
        g = np.exp(-(((xx - hx) / px(24.75)) ** 2 + ((yy - 425.25 * K) / px(5.625)) ** 2))
        fr[gy_, gx_] += (n * 0.5 + 150) * (g * 0.8)[..., None]
    for k, (x0, x1) in A_COLS.items():
        cx = (x0 + x1) / 2
        ptext(fr, A_LAB[k], F_BOLD, 8.775, cx, 376.875, (235, 245, 238, 255))
        ptext(fr, vals[k], F_BOLD, 18, cx, 402.75, (255, 255, 255, 255))


# ------------------------------------------------------------------ design: orbit --------
ORB = [dict(c=(563, 240.75), a=398, b=117.0, rot=-12.0), dict(c=(564, 236.25), a=300, b=96.75, rot=8.0),
       dict(c=(563, 230.625), a=215, b=132.75, rot=0.0)]
ORB_NODES = dict(entry=(0, (178, 284.625), -0.30), now=(0, (933, 129.375), -0.30), points=(1, (327, 149.625), 0.42),
                 calls=(1, (814, 228.375), 0.42), win=(0, (480, 371.25), -0.30))


def ell_pt(e, th):
    r = math.radians(e["rot"])
    x, y = e["a"] * math.cos(th), e["b"] * math.sin(th)
    return (e["c"][0] + x * math.cos(r) - y * math.sin(r), e["c"][1] + x * math.sin(r) + y * math.cos(r))


def ell_theta(e, pt):
    best, bt = 1e18, 0
    for i in range(720):
        th = i / 720 * 2 * math.pi
        q = ell_pt(e, th)
        d = (q[0] - pt[0]) ** 2 + (q[1] - pt[1]) ** 2
        if d < best:
            best, bt = d, th
    return bt


def draw_orbit(fr, t, ctx, vals):
    n = ctx["n"]; hot = ctx["hot"]
    SS = 2
    lay = Image.new("L", (W * SS, H * SS), 0); d = ImageDraw.Draw(lay)
    comet = Image.new("L", (W, H), 0); cd = ImageDraw.Draw(comet)
    for ei, e in enumerate(ORB):
        br = 1 + 0.012 * math.sin(t * 1.3 + ei)
        e2 = dict(e); e2["a"] = e["a"] * br; e2["b"] = e["b"] * br
        pts = [ell_pt(e2, i / 180 * 2 * math.pi) for i in range(181)]
        d.line([(x * K * SS, y * K * SS) for x, y in pts], fill=255, width=int(1.7 * K * SS / 1.7 * 1.1))
        th0 = (t * (0.9 - 0.2 * ei) * (1 if ei % 2 == 0 else -1) + ei * 2.1) % (2 * math.pi)
        for j in range(26):
            th = th0 - j * 0.035 * (1 if ei % 2 == 0 else -1)
            q = ell_pt(e2, th)
            cd.ellipse((q[0] * K - 2.4, q[1] * K - 2.4, q[0] * K + 2.4, q[1] * K + 2.4), fill=int(255 * (1 - j / 26)))
    lm = np.asarray(lay.resize((W, H), Image.BOX), np.float32) / 255.
    cm = np.asarray(comet, np.float32) / 255.
    fr += n * (blur(lm, 3.5) * 0.9 + blur(lm, 10.0) * 0.6)[..., None] * 0.65 * ctx["pulse"]
    fr[:] = fr * (1 - (lm * 0.8)[..., None]) + (n * 0.9 + 20) * (lm * 0.8)[..., None]
    fr += (n * 0.5 + 140) * (blur(cm, 3.0) * 1.3)[..., None]
    # nodes + labels
    out = {}
    for i, (k, (ei, pt, w)) in enumerate(ORB_NODES.items()):
        e = ORB[ei]
        th = ctx["orb_theta"][k] + w * t * 0.5
        q = ell_pt(e, th)
        out[k] = q
        gy_, gx_ = np.mgrid[0:H, 0:W].astype(np.float32) if False else (None, None)
        cx, cy = q[0] * K, q[1] * K
        R = int(px(29.25))
        x0, y0 = int(cx) - R, int(cy) - R
        if R < x0 < W - 2 * R and 0 <= y0 < H - 2 * R:
            yy, xx = np.mgrid[y0:y0 + 2 * R, x0:x0 + 2 * R].astype(np.float32)
            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            reg = fr[y0:y0 + 2 * R, x0:x0 + 2 * R]
            reg += n * (np.exp(-((dist / px(12)) ** 2)) * (0.9 + 0.3 * math.sin(t * 4 + i)))[..., None]
            ra = np.clip(px(7.5) + 1 - dist, 0, 1)[..., None]
            reg[:] = reg * (1 - ra) + (n * 0.95 + 20) * ra
            ca = np.clip(px(4.2) + 1 - dist, 0, 1)[..., None]
            reg[:] = reg * (1 - ca) + 255 * ca
        left = q[0] < 563
        ax_ = q[0] - 14 if left else q[0] + 14
        anc = "r" if left else "l"
        ptext(fr, A_LAB[k] if k != "win" else "WIN RATE", F_BOLD, 9.5625, ax_, q[1] - 12.375, (240, 250, 244, 255), anc)
        ptext(fr, vals[k], F_BOLD, 17.4375, ax_, q[1] + 9, (255, 255, 255, 255), anc)
    return out


# ------------------------------------------------------------------ design: matrix -------
M_CHARS = "0123456789ABCDEF$X"
M_COLS = dict(entry=(42, 251), now=(251, 459), points=(459, 665), calls=(665, 873), win=(873, 1082))
M_LAB = dict(entry="> ENTRY_MC", now="> NOW", points="> POINTS", calls="> CALLS", win="> WIN_RATE")


def matrix_static():
    SS = 2
    S = lambda v: v * K * SS
    ln = Image.new("L", (W * SS, H * SS), 0); d = ImageDraw.Draw(ln)
    fl = Image.new("L", (W * SS, H * SS), 0); fd = ImageDraw.Draw(fl)
    d.rounded_rectangle((S(42), S(365.625), S(1082), S(426.375)), S(6), outline=255, width=int(S(2.2)))
    fd.rounded_rectangle((S(42), S(365.625), S(1082), S(426.375)), S(6), fill=255)
    dash = Image.new("L", (W * SS, H * SS), 0); dd = ImageDraw.Draw(dash)
    for x in (251, 459, 665, 873):
        y = 372.375
        while y < 419.625:
            dd.line((S(x), S(y), S(x), S(y + 3)), fill=255, width=int(S(1.2)))
            y += 6
    lm = np.asarray(ln.resize((W, H), Image.LANCZOS), np.float32) / 255.
    fm = np.asarray(fl.resize((W, H), Image.LANCZOS), np.float32) / 255.
    dm = np.asarray(dash.resize((W, H), Image.LANCZOS), np.float32) / 255.
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((X - px(570)) / px(335)) ** 2 + ((Y - px(212)) / px(112)) ** 2)
    ell = 1 / (1 + np.exp((r - 1.0) * 9))
    return lm, fm, dm, ell.astype(np.float32)


def matrix_rain(t):
    """returns (tail, head) float masks of the digital rain (full frame)."""
    f = font(MONO, 16.875 * K)
    tail = Image.new("L", (W, H), 0); td = ImageDraw.Draw(tail)
    head = Image.new("L", (W, H), 0); hd = ImageDraw.Draw(head)
    step = 21.375 * K
    y_min, y_max = 94.5 * K, 362.25 * K
    span = y_max - y_min
    for j in range(31):
        rg = random.Random(j * 97 + 3)
        x = (22 + j * 36.3) * K
        sp = rg.uniform(60, 170) * K
        ln = rg.randint(10, 20)
        off = rg.uniform(0, 900) * K
        cyc = span + ln * step
        y_head = y_min + ((off + sp * t) % cyc)
        for r in range(ln):
            y = y_head - r * step
            if y < y_min or y > y_max:
                continue
            ch = M_CHARS[(j * 7 + r * 13 + int(t * (2 + (j % 3)) + r * 0.3)) % len(M_CHARS)]
            br = (1 - r / ln) ** 1.1
            if r == 0:
                hd.text((x, y), ch, font=f, fill=240, anchor="mm")
            td.text((x, y), ch, font=f, fill=int(255 * br), anchor="mm")
    return np.asarray(tail, np.float32) / 255., np.asarray(head, np.float32) / 255.


def scramble(s, frac, rg):
    k = int(round(len(s) * frac))
    out = []
    for i, c in enumerate(s):
        if i < k or c in " .,$%MKB":
            out.append(c)
        else:
            out.append(rg.choice("0123456789ABCDEF"))
    return "".join(out)


# ------------------------------------------------------------------ video ----------------
def build_green_video(*, design="matrix", x_val=40, color="green", tier=None, kol_name="Pumpwatch1", symbol="PI", chain="SOL", entry_mc=0, now_mc=0,
                      rank=1, points=0, calls=0, win_rate="0%", avatar_path=None, logo_path=None,
                      out_path="champion.mp4", preview_times=None, crf=14, preset="slow"):
    x_val = float(x_val)
    cfg = DESIGN[design]
    pal = palette_for(tier or color)
    drv = _derive(pal)
    n = np.array(pal["n"], np.float32); hot = np.array(pal["hot"], np.float32)
    if not logo_path:
        for nm in ("golden_logo.png", "golden_logo.jpg", "wizard_logo.png"):
            for d_ in (HERE, os.path.join(HERE, "assets")):
                if os.path.exists(os.path.join(d_, nm)):
                    logo_path = os.path.join(d_, nm); break
            if logo_path: break
    hd = build_header(kol_name, rank, avatar_path, logo_path, cfg["sub_c"], symbol, chain, pal)
    G, lm, fm = hd["G"], hd["lm"], hd["fm"]
    trgb, ta = hd["text"][..., :3], hd["text"][..., 3:4] / 255.
    gtrgb, gta = hd["gtext"][..., :3], hd["gtext"][..., 3:4] / 255.
    masks = hdr_masks()
    num = NeonNum(cfg["size"], pal)
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    gcx, gcy = px(cfg["num_c"][0]), px(cfg["num_c"][1])
    ref_png = os.path.join(HERE, f"ref_{design}.png")
    cache_png = os.path.join(HERE, f"bg_{design}.png")
    if design in BG_EXCL and (os.path.exists(ref_png) or os.path.exists(cache_png)):
        base = est_bg(ref_png, BG_EXCL[design], cache=cache_png)
    else:
        base = np.zeros((H, W, 3), np.float32)
        base += np.array([2, 11, 6], np.float32) * (1.1 - 0.4 * yy)[..., None]
        base += n * (0.07 * np.exp(-(((X - gcx) / px(380)) ** 2 + ((Y - gcy) / px(190)) ** 2)))[..., None]
        vig = 1 - 0.42 * (((xx - .5) / .75) ** 2 + ((yy - .55) / .95) ** 2)
        base *= np.clip(vig, 0.4, 1)[..., None]
    noise = (np.random.RandomState(1).rand(H, W, 1).astype(np.float32) - 0.5) * 1.6
    ctx = dict(n=n, hot=hot, pal=pal, drv=drv, label=tuple(int(v) for v in pal["sub"]),
               dark=drv["dark"], line=drv["line"],
               area_labels=[(120.375, f"{int(round(x_val))}x"), (195.75, f"{int(round(x_val * 0.7))}x"),
                            (271.125, f"{int(round(x_val * 0.43))}x"), (346.5, f"{int(round(x_val * 0.15))}x")])
    if design == "area":
        ctx["area_static"] = area_static()
    if design == "orbit":
        ctx["orb_theta"] = {k: ell_theta(ORB[ei], pt) for k, (ei, pt, w) in ORB_NODES.items()}
    if design == "matrix":
        mlm, mfm, mdm, mell = matrix_static()
        base *= (1 - 0.55 * mell)[..., None]
    wr = float(str(win_rate).strip("%") or 0)
    sparks = make_sparks(33)
    flick = [1, 0.15, 1, 0.5, 1, 1, 0.3, 1, 1, 0.7, 1, 1]
    n_frames = int(DUR * FPS)
    T0, T1 = 0.55, 1.55

    def block_active(i, salt, prob, size=3):
        return random.Random((i // size) * 31 + salt).random() < prob

    def local_fx(fr, key, draw_fn, intensity=1.0):
        bb, m = masks[key]
        x0, y0, x1, y1 = bb
        lay = Image.new("L", (x1 - x0, y1 - y0), 0)
        draw_fn(ImageDraw.Draw(lay), x1 - x0, y1 - y0)
        lmk = np.asarray(lay, np.float32) / 255.
        lgk = np.asarray(lay.filter(ImageFilter.GaussianBlur(4)), np.float32) / 255.
        fr[y0:y1, x0:x1] += (n * 0.8 + 90)[None, None, :] * (lgk * 1.5 * intensity * m)[..., None]
        fr[y0:y1, x0:x1] += 255 * (lmk * 0.9 * intensity * m)[..., None]

    def frame_at(i):
        t = i / FPS
        ts = t - T1
        if t < 0.08: pw = 0.0
        elif t < 0.5: pw = flick[int((t - 0.08) * 30) % len(flick)]
        else: pw = 1.0
        pulse = (1.0 + 0.09 * math.sin(2 * math.pi * t / 2.4)) * pw
        if 0 <= ts < 1.0:
            pulse *= 1.0 + 0.7 * math.exp(-ts / 0.35)
        ctx["pw"], ctx["pulse"] = pw, pulse
        fr = base.copy() * (0.4 + 0.6 * pw)
        rg = random.Random(i * 17 + 3)
        # --- moving background
        if design == "matrix":
            tail, head = matrix_rain(t)
            vis = (1 - mell * 0.93)
            fr += (n * 0.55)[None, None, :] * (tail * vis * 1.0 * min(1, t / 0.5))[..., None]
            fr += (hot * 0.6 + 40) * (head * vis * 0.5 * min(1, t / 0.5))[..., None]
        else:
            beam_pos = ((t * 0.25) % 1.6 - 0.3) * (W + H)
            beam = np.exp(-((((X * 0.82 + Y * 0.57) - beam_pos) / px(110)) ** 2))
            fr += n * (beam * 0.035)[..., None]
            splat_sparks(fr, sparks, t, n)
        fr += G * pulse
        fr = fr * (1 - fm[..., None] * 0.97) + BOXC * (fm[..., None] * 0.97)
        core = (lm * pw)[..., None]
        fr = fr * (1 - core) + n * core
        fr = fr * (1 - ta * pw) + trgb * ta * pw
        fr = fr * (1 - gta * pw) + gtrgb * gta * pw
        # --- count + value strings
        prog = ease_out((t - T0) / (T1 - T0)) if t >= T0 else 0.0
        cu = ease_out((t - 1.0) / 1.7) if t >= 1.0 else 0.0
        vals = dict(entry=fmt_mc(entry_mc * cu), now=fmt_mc(now_mc * cu), points=str(int(round(points * cu))),
                    calls=str(int(round(calls * cu))), win=f"{int(round(wr * cu))}%")
        if design == "matrix":
            for k in vals:
                full = dict(entry=fmt_mc(entry_mc), now=fmt_mc(now_mc), points=str(points), calls=str(calls), win=f"{int(wr)}%")[k]
                vals[k] = scramble(full, min(1.0, cu * 1.15), random.Random(i * 5 + hash(k) % 97)) if cu < 1 else full
        # --- design body
        if design == "area":
            draw_area(fr, t, ctx)
            draw_area_bottom(fr, t, ctx, vals)
        elif design == "orbit":
            draw_orbit(fr, t, ctx, vals)
        else:
            fr[:] = fr * (1 - (mfm * 0.92 * pw)[..., None])
            fr += n * (blur(mlm, 3.5) + blur(mlm, 10.0) * 0.8)[..., None] * 0.5 * pulse
            fr[:] = fr * (1 - (mlm * pw)[..., None]) + (n * 0.95 + 20) * (mlm * pw)[..., None]
            fr[:] = fr * (1 - (mdm * 0.7 * pw)[..., None]) + (n * 0.55 + 20) * (mdm * 0.7 * pw)[..., None]
            for k, (x0, x1) in M_COLS.items():
                ptext(fr, M_LAB[k] + ("_" if (int(t * 2.2) % 2 == 0 and k == "win") else ""), MONO, 9.675, x0 + 24, 382.5, (*pal["sub"], 255), "l")
                ptext(fr, vals[k], F_BOLD, 19.125, x0 + 24, 402.75, (255, 255, 255, 255), "l")
            sy = ((t * 0.5) % 1.4) * 90 + 362.25
            if 365.625 < sy < 426.375:
                fr[int(sy * K):int(sy * K) + 2, int(44 * K):int(1080 * K)] += (n * 0.5 + 100) * 0.5
        # --- hero number: count-up, neon outline, lightning inside, flash on landing
        if t >= T0:
            label = f"{int(round(x_val * prog))}x" if prog < 1 else f"{int(x_val)}x"
            fl_ = rg.uniform(0.78, 1.0) if prog < 1 else 1.0
            flash = math.exp(-ts / 0.1) if ts >= 0 else 0.0
            num.draw(fr, label, cfg["num_c"], pulse, alpha=1.0, flash=flash, scale_flick=fl_)
            if prog < 1:
                act = block_active(i, 41, 0.35, 2)
                bl = 2
            else:
                act = (0 <= ts < 0.7) or block_active(i, 43, 0.72, 2)
                bl = 7 if 0 <= ts < 0.5 else 4
            if act:
                num.lightning(fr, label, cfg["num_c"], random.Random(i * 29 + 7), 1.0 + (0.6 if 0 <= ts < 0.5 else 0), bl)
        # --- FULL SCREEN FLASH when the x lands
        if 0 <= ts < 0.9:
            f1 = math.exp(-ts / 0.085)
            f2 = 0.55 * math.exp(-max(0.0, ts - 0.13) / 0.08) if ts >= 0.13 else 0.0
            fl_all = min(1.0, f1 + f2)
            fr += (hot * 0.75 + n * 0.25 + 40) * (0.72 * fl_all)
            Rc = np.sqrt((X - gcx) ** 2 + (Y - gcy) ** 2)
            fr += (n * 0.6 + 120) * (np.exp(-Rc / px(520)) * math.exp(-ts / 0.3) * 0.7)[..., None]
            if ts < 0.7:
                fr += (n * 0.75 + 70) * (np.exp(-(((Rc - ts * 1900) / px(15)) ** 2)) * (1 - ts / 0.7) * 0.85)[..., None]
            if ts < 0.3:
                r2 = random.Random(i * 13 + 5)
                lay2 = Image.new("L", (W, H), 0); ld2 = ImageDraw.Draw(lay2)
                for _ in range(9):
                    an = r2.uniform(0, 2 * math.pi); ln = px(r2.uniform(110, 300))
                    ld2.line(jag(gcx, gcy, gcx + ln * math.cos(an), gcy + ln * math.sin(an), r2, 10, 16), fill=255, width=3)
                lmk = np.asarray(lay2, np.float32) / 255.; lgk = blur(lmk, 5)
                amp = 1 - ts / 0.3
                fr += (n * 0.8 + 90) * (lgk * 1.5 * amp)[..., None] + 255 * (lmk * 0.9 * amp)[..., None]
        # --- header lightning (rank box, logo + channel name, kol box)
        forced = 0 <= ts < 0.6
        if forced or block_active(i, 1, 0.55):
            r2 = random.Random(i * 5 + 1)

            def dr(d, w, h):
                x = r2.uniform(25, w - 25)
                d.line(jag(x, 1, x + r2.uniform(-35, 35), h - 1, r2, 9, 9), fill=255, width=2)
                if r2.random() < 0.7:
                    x2 = r2.uniform(25, w - 25)
                    d.line(jag(x2, 1, x2 + r2.uniform(-45, 45), h - 1, r2, 8, 8), fill=255, width=2)
                my = r2.uniform(h * .3, h * .7)
                d.line(jag(x, my, x + r2.choice([-1, 1]) * r2.uniform(25, 60), my + r2.uniform(-10, 14), r2, 5, 5), fill=255, width=1)
            local_fx(fr, "rank", dr, 1.2)
        if forced or block_active(i, 2, 0.40):
            r3 = random.Random(i * 11 + 7)
            lx, ly, lr = LOGO
            lay4 = Image.new("L", (W, H), 0); d4 = ImageDraw.Draw(lay4)
            cxl, cyl, rl = px(lx), px(ly), px(lr)
            for _ in range(r3.randint(3, 5)):
                an = r3.uniform(0, 2 * math.pi)
                a0 = (cxl + rl * 0.98 * math.cos(an), cyl + rl * 0.98 * math.sin(an))
                a1 = (cxl + rl * r3.uniform(1.25, 1.7) * math.cos(an + r3.uniform(-.4, .4)),
                      cyl + rl * r3.uniform(1.25, 1.7) * math.sin(an + r3.uniform(-.4, .4)))
                d4.line(jag(a0[0], a0[1], a1[0], a1[1], r3, 5, 5), fill=255, width=2)
            an0 = r3.uniform(0, 6.28); span = r3.uniform(0.9, 2.0)
            arc = []
            for j in range(16):
                a_ = an0 + span * j / 15; rr_ = rl * (1.08 + r3.uniform(-.05, .08))
                arc.append((cxl + rr_ * math.cos(a_), cyl + rr_ * math.sin(a_)))
            d4.line(arc, fill=255, width=2)
            tx0, tx1 = px(TITLE_X), px(740)
            for _ in range(2):
                xa = r3.uniform(tx0, tx1 - 120); ya = px(TITLE_Y) + r3.choice([-1, 1]) * px(r3.uniform(13, 19))
                d4.line(jag(xa, ya, xa + r3.uniform(70, 170), ya + r3.uniform(-9, 9), r3, 11, 7), fill=255, width=2)
            for _ in range(3):
                xa = r3.uniform(tx0, tx1)
                d4.line(jag(xa, px(TITLE_Y) - px(17), xa + r3.uniform(-10, 10), px(TITLE_Y) + px(17), r3, 5, 6), fill=255, width=1)
            sub_ = lay4.crop((int(px(360)), int(px(11.25)), int(px(770)), int(px(103.5))))
            lmk = np.asarray(sub_, np.float32) / 255.; lgk = np.asarray(sub_.filter(ImageFilter.GaussianBlur(4)), np.float32) / 255.
            ya, xa = int(px(11.25)), int(px(360))
            fr[ya:ya + lmk.shape[0], xa:xa + lmk.shape[1]] += (n * 0.8 + 90) * (lgk * 1.5)[..., None] + 255 * (lmk * 0.9)[..., None]
        if block_active(i, 3, 0.20):
            r4 = random.Random(i * 3 + 9)

            def dk(d, w, h):
                x = r4.uniform(110, w - 25)
                d.line(jag(x, 1, x + r4.uniform(-30, 30), h - 1, r4, 8, 8), fill=255, width=2)
            local_fx(fr, "kol", dk, 1.0)
        if t < 0.08:
            fr *= 0.0
        fr += noise
        out = np.clip(fr, 0, 255).astype(np.uint8)
        if 0 <= ts < 0.4:
            amp = 5 * math.exp(-ts / 0.15)
            dx, dy = int(round(rg.uniform(-amp, amp))), int(round(rg.uniform(-amp, amp)))
            if dx or dy:
                o2 = np.zeros_like(out); o2[:] = out[0:1, 0:1]
                ys0, ys1 = max(0, dy), H + min(0, dy); xs0, xs1 = max(0, dx), W + min(0, dx)
                o2[ys0:ys1, xs0:xs1] = out[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
                out = o2
        return out

    if preview_times:
        for tt in preview_times:
            Image.fromarray(frame_at(int(tt * FPS))).save(f"{out_path}_t{tt}.png")
        return None
    cmd = [ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", "-an", out_path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n_frames):
        pr.stdin.write(frame_at(i).tobytes())
    pr.stdin.close()
    if pr.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out_path


def make_sparks(seed, n=90):
    rng = random.Random(seed)
    return [dict(x=rng.uniform(0, W), y=rng.uniform(0, H), vy=rng.uniform(5, 26) * K / 1.7, amp=rng.uniform(3, 16),
                 ph=rng.uniform(0, 6.28), fr=rng.uniform(.3, 1.2), r=rng.uniform(1.0, 2.6) * K / 1.7 * 0.8,
                 tw=rng.uniform(.8, 2.4), tp=rng.uniform(0, 6.28)) for _ in range(n)]


def splat_sparks(fr, sp, t, n):
    for e in sp:
        y = (e["y"] - e["vy"] * t) % (H + 20) - 10
        x = e["x"] + e["amp"] * math.sin(e["ph"] + e["fr"] * t)
        al = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(e["tp"] + e["tw"] * t))
        r = e["r"]; R = int(r * 3) + 2
        x0, y0 = int(x) - R, int(y) - R
        if x0 < 0 or y0 < 0 or x0 + 2 * R + 1 > W or y0 + 2 * R + 1 > H:
            continue
        gy, gx = np.mgrid[-R:R + 1, -R:R + 1].astype(np.float32)
        g = np.exp(-(((gx - (x - int(x))) ** 2 + (gy - (y - int(y))) ** 2) / (0.8 * r * r))) * al
        fr[y0:y0 + 2 * R + 1, x0:x0 + 2 * R + 1] += g[..., None] * (n * 0.6 + 80)


if __name__ == "__main__":
    import sys
    d_ = sys.argv[1] if len(sys.argv) > 1 else "matrix"
    xv = float(sys.argv[2]) if len(sys.argv) > 2 else {"area": 35, "orbit": 45, "matrix": 40}[d_]
    build_green_video(design=d_, x_val=xv, kol_name="Pumpwatch1", symbol="PI", chain="SOL", entry_mc=145500,
                      now_mc=875600, rank=1, points=142, calls=117, win_rate="42%",
                      out_path=sys.argv[3] if len(sys.argv) > 3 else f"champion_{d_}.mp4")
