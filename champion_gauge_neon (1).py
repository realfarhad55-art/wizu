"""
champion_gauge_neon.py - native 1920x684 (Full HD) renderer, NEON style (black background, glowing outlines)
for CHAMPION KOL x-alert videos.

    build_gauge_video(kol_name="pumpwatch1", x_val=10, symbol="PI", chain="SOL", entry_mc=145500,
                      now_mc=875600, rank=1, points=142, calls=117, win_rate="42%",
                      avatar_path=None, logo_path=None, out_path="out.mp4")

Needs: Pillow, numpy, ffmpeg.  Fonts: Poppins-Bold.ttf + Poppins-BoldItalic.ttf next to this file
(or in assets/fonts, or CHAMPION_FONT_DIR).
"""
import math, os, random, shutil, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 684, 30
K = 1920 / 1124.0            # layout coordinates are in the 1124x400 design -> x1.708
DUR = 6.0
HERE = os.path.dirname(os.path.abspath(__file__))

# neon colour per multiplier tier  (n = neon tube colour, hot = near-white core, tx = soft text tint)
PALETTES = {
    "red":    dict(n=(255, 34, 52),  hot=(255, 225, 230), tx=(255, 214, 222)),
    "blue":   dict(n=(40, 140, 255), hot=(215, 238, 255), tx=(210, 232, 255)),
    "orange": dict(n=(255, 120, 20), hot=(255, 236, 210), tx=(255, 226, 196)),
    "green":  dict(n=(40, 255, 110), hot=(220, 255, 232), tx=(214, 255, 230)),
    "purple": dict(n=(170, 80, 255), hot=(236, 220, 255), tx=(232, 214, 255)),
    "bw":     dict(n=(255, 255, 255), hot=(255, 255, 255), tx=(240, 240, 240)),
}
GOLD = (255, 190, 0)


def tier_for(x):
    x = float(x)
    if x >= 100: return "bw"
    if x >= 51:  return "purple"
    if x >= 31:  return "green"
    if x >= 21:  return "orange"
    if x >= 11:  return "blue"
    return "red"


def _find(*names):
    for n in names:
        for d in (os.environ.get("CHAMPION_FONT_DIR", ""), HERE, os.path.join(HERE, "assets"),
                  os.path.join(HERE, "assets", "fonts"),
                  "/usr/share/fonts/truetype/google-fonts", "/usr/share/fonts/truetype/dejavu"):
            p = os.path.join(d, n)
            if d and os.path.exists(p):
                return p
    return None


F_BOLD = _find("Poppins-Bold.ttf", "DejaVuSans-Bold.ttf")
F_BI = _find("Poppins-BoldItalic.ttf", "Poppins-Bold.ttf", "DejaVuSans-Bold.ttf")


def font(path, px):
    return ImageFont.truetype(path, max(6, int(round(px)))) if path else ImageFont.load_default()


def ffmpeg_bin():
    p = shutil.which("ffmpeg")
    if p:
        return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def ease_out2(u):
    u = min(1.0, max(0.0, u)); return 1 - (1 - u) ** 2


def fmt_mc(v):
    v = float(v)
    if v >= 1e9: return f"${v/1e9:.1f}B MC"
    if v >= 1e6: return f"${v/1e6:.1f}M MC"
    if v >= 1e3: return f"${v/1e3:.1f}K MC"
    return f"${v:.0f} MC"


def blur(arr, sigma):
    im = Image.fromarray(np.clip(arr * 255, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(sigma)), np.float32) / 255.


def circle_crop(img, d):
    img = img.convert("RGBA").resize((d, d), Image.LANCZOS)
    m = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * 4 - 1, d * 4 - 1), fill=255)
    m = m.resize((d, d), Image.LANCZOS)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0)); out.paste(img, (0, 0), m)
    return out


# ------------------------------------------------------------------ layout (design px) ---
PIV = (388, 358)
R_ARC = 207
HALF_T = 6.5
BOXES = dict(kol=(24, 22, 264, 78), rank=(900, 22, 1099, 78), entry=(836, 118, 1086, 166),
             now=(836, 174, 1086, 222), points=(836, 230, 962, 278), calls=(965, 230, 1086, 278),
             win=(836, 286, 1086, 317))
FRAME = (6, 6, 1117, 393)
RX0, RY0, RX1, RY1 = int(158 * K), int(120 * K), int(622 * K), int(396 * K)


def px(v):
    return v * K


# ------------------------------------------------------------------ static neon layers ---
def build_static(p, kol_name, symbol, chain, entry, now, rank, points, calls, win_rate, avatar_path, logo_path):
    n = np.array(p["n"], np.float32); hot = np.array(p["hot"], np.float32); tx = tuple(p["tx"])
    SS = 2
    S = lambda v: v * K * SS
    big = (W * SS, H * SS)

    # 1) neon tube outlines (mask)
    lines = Image.new("L", big, 0); ld = ImageDraw.Draw(lines)
    ld.rounded_rectangle((S(FRAME[0]), S(FRAME[1]), S(FRAME[2]), S(FRAME[3])), S(20), outline=255, width=int(S(2.2)))
    fills = Image.new("L", big, 0); fd = ImageDraw.Draw(fills)
    for k, b in BOXES.items():
        ld.rounded_rectangle((S(b[0]), S(b[1]), S(b[2]), S(b[3])), S(14), outline=255, width=int(S(2.2)))
        fd.rounded_rectangle((S(b[0]), S(b[1]), S(b[2]), S(b[3])), S(14), fill=255)
    ax, ay, ar = 53, 50, 16
    ld.ellipse((S(ax - ar), S(ay - ar), S(ax + ar), S(ay + ar)), outline=255, width=int(S(2)))
    lm = np.asarray(lines.resize((W, H), Image.LANCZOS), np.float32) / 255.
    fm = np.asarray(fills.resize((W, H), Image.LANCZOS), np.float32) / 255.

    # 2) text / logo layer
    tl = Image.new("RGBA", big, (0, 0, 0, 0)); td = ImageDraw.Draw(tl)
    fb = lambda sz: font(F_BOLD, S(sz))

    def txt(xy, s, f, fill, anchor="mm"):
        td.text((S(xy[0]), S(xy[1])), s, font=f, fill=fill, anchor=anchor)

    if avatar_path and os.path.exists(avatar_path):
        av = circle_crop(Image.open(avatar_path), int(S(2 * ar - 2)))
        tl.paste(av, (int(S(ax - ar + 1)), int(S(ay - ar + 1))), av)
    else:
        td.ellipse((S(ax - ar + 1), S(ay - ar + 1), S(ax + ar - 1), S(ay + ar - 1)), fill=(8, 8, 8, 255))
        txt((ax, ay - 4.5), "PUMP", fb(6.8), (60, 235, 120, 255))
        txt((ax, ay + 4.5), "WATCH", fb(6.8), (60, 235, 120, 255))
    name = (kol_name or "KOL").lstrip("@")
    sz = 22
    while sz > 10 and font(F_BOLD, S(sz)).getlength(name) > S(168):
        sz -= 1
    txt((86, 40), name, fb(sz), (255, 255, 255, 255), "lm")
    txt((86, 66), "CHAMPION KOL \u00b7 X ALERT", fb(8.6), (*p["n"], 255), "lm")
    f21 = fb(21)
    x0 = 368
    for part, col in (("Wizard ", (255, 255, 255, 255)), ("Scan", (*p["n"], 255)), (" Call Tracker", (255, 255, 255, 255))):
        txt((x0, 50), part, f21, col, "lm")
        x0 += f21.getlength(part) / (K * SS)
    txt((1000, 35), "RANK ON WIZARDSCANLIVE", fb(8), (240, 240, 245, 255))

    def stat(b, lab, val):
        cx = (b[0] + b[2]) / 2
        txt((cx, b[1] + 11.5), lab, fb(7.8), (235, 235, 240, 255))
        txt((cx, b[1] + 31), val, fb(15.5), (255, 255, 255, 255))
    stat(BOXES["entry"], "ENTRY MC", fmt_mc(entry))
    stat(BOXES["now"], "NOW", fmt_mc(now))
    stat(BOXES["points"], "POINTS", str(points))
    stat(BOXES["calls"], "CALLS", str(calls))
    wb = BOXES["win"]
    wr = float(str(win_rate).strip("%") or 0)
    txt(((wb[0] + wb[2]) / 2, wb[1] + 11), f"WIN RATE \u00b7 {int(wr)}%", fb(7.8), (235, 235, 240, 255))
    bx0, bx1, by0, by1 = wb[0] + 8, wb[2] - 8, wb[1] + 19, wb[1] + 25.5
    td.rounded_rectangle((S(bx0), S(by0), S(bx1), S(by1)), S(3), fill=(58, 8, 14, 255))
    td.rounded_rectangle((S(bx0), S(by0), S(bx0 + (bx1 - bx0) * min(1, wr / 100)), S(by1)), S(3), fill=(*p["n"], 255))
    # gauge static text: ticks + end labels
    cx, cy = PIV
    flab = fb(13)
    for v in (2, 4, 6, 8):
        ang = math.pi * (1 - v / 10)
        txt((cx + 176 * math.cos(ang), cy - 176 * math.sin(ang)), f"{v}x", flab, (*tx, 235))
    txt((cx - R_ARC - 6, cy + 25), "0x", flab, (255, 255, 255, 240))
    txt((cx + R_ARC + 6, cy + 25), "10x", flab, (255, 255, 255, 240))

    # glow-only text (rank number + token line), drawn separately so it can glow
    gl = Image.new("L", big, 0); gd = ImageDraw.Draw(gl)
    glow_txt = Image.new("RGBA", big, (0, 0, 0, 0)); gtd = ImageDraw.Draw(glow_txt)
    fr = font(F_BI, S(31))
    for target in (gd, gtd):
        pass
    gd.text((S(1000), S(60)), f"#{rank}", font=fr, fill=255, anchor="mm")
    gtd.text((S(1000), S(60)), f"#{rank}", font=fr, fill=(*tx, 255), anchor="mm", stroke_width=int(S(0.6)),
             stroke_fill=(*p["n"], 255))
    sub = f"${(symbol or 'TOKEN').upper()} \u00b7 {(chain or 'SOL').upper()}"
    fs = fb(17.5)
    gd.text((S(388), S(319)), sub, font=fs, fill=255, anchor="mm")
    gtd.text((S(388), S(319)), sub, font=fs, fill=(*p["n"], 255), anchor="mm")
    gm = np.asarray(gl.resize((W, H), Image.LANCZOS), np.float32) / 255.

    # 3) gold logo (ring + W) or provided file
    lgx, lgy, lgr = 328, 49, 25
    logo_alpha = Image.new("L", big, 0)
    if logo_path and os.path.exists(logo_path):
        lg = circle_crop(Image.open(logo_path), int(S(2 * lgr)))
        tl.paste(lg, (int(S(lgx - lgr)), int(S(lgy - lgr))), lg)
        ImageDraw.Draw(logo_alpha).ellipse((S(lgx - lgr + 3), S(lgy - lgr + 3), S(lgx + lgr - 3), S(lgy + lgr - 3)),
                                           outline=255, width=int(S(3)))
    else:
        td.ellipse((S(lgx - lgr), S(lgy - lgr), S(lgx + lgr), S(lgy + lgr)), fill=(8, 8, 8, 255),
                   outline=(*GOLD, 255), width=int(S(2.6)))
        txt((lgx, lgy + 0.5), "W", font(F_BOLD, S(21)), (*GOLD, 255))
        ImageDraw.Draw(logo_alpha).ellipse((S(lgx - lgr), S(lgy - lgr), S(lgx + lgr), S(lgy + lgr)), outline=255,
                                           width=int(S(2.6)))
    lam = np.asarray(logo_alpha.resize((W, H), Image.LANCZOS), np.float32) / 255.

    text_rgba = np.asarray(tl.resize((W, H), Image.LANCZOS), np.float32)
    gtext_rgba = np.asarray(glow_txt.resize((W, H), Image.LANCZOS), np.float32)

    # 4) glows
    glow_n = (blur(lm, 4.5 * K / 1.7) * 1.0 + blur(lm, 13 * K / 1.7) * 0.85 + blur(lm, 30 * K / 1.7) * 0.30)
    glow_t = (blur(gm, 5 * K / 1.7) * 0.9 + blur(gm, 14 * K / 1.7) * 0.5)
    G = n * (glow_n + glow_t)[..., None] * 0.55
    G += np.array(GOLD, np.float32) * (blur(lam, 6 * K / 1.7) * 0.7 + blur(lam, 16 * K / 1.7) * 0.4)[..., None] * 0.45
    # tint the box interiors very slightly
    tint = n * (fm * 0.035)[..., None]
    return dict(G=G.astype(np.float32), lm=lm, fm=fm, tint=tint.astype(np.float32),
                text=text_rgba, gtext=gtext_rgba, n=n, hot=hot)


def box_masks():
    SS = 2
    out = {}
    for k, bx in BOXES.items():
        x0, y0, x1, y1 = [int(round(v * K)) for v in bx]
        m = Image.new("L", ((x1 - x0) * SS, (y1 - y0) * SS), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, (x1 - x0) * SS - 1, (y1 - y0) * SS - 1), 14 * K * SS, fill=255)
        out[k] = ((x0, y0, x1, y1), np.asarray(m.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32) / 255.)
    return out


def build_background(p):
    n = np.array(p["n"], np.float32)
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    gx, gy = px(PIV[0]), px(PIV[1] + 10)
    base = np.zeros((H, W, 3), np.float32)
    base += n * (0.085 * (1.15 - 0.65 * yy))[..., None]
    glow = np.exp(-(((X - gx) / px(330)) ** 2 + ((Y - gy) / px(200)) ** 2))
    base += n * (0.20 * glow)[..., None]
    wide = np.exp(-(((X - gx) / px(760)) ** 2 + ((Y - gy) / px(340)) ** 2))
    base += n * (0.07 * wide)[..., None]
    vig = 1 - 0.40 * (((xx - .5) / .75) ** 2 + ((yy - .55) / .95) ** 2)
    base *= np.clip(vig, 0.4, 1)[..., None]
    return base, (X - gx), (Y - px(PIV[1]))


def make_embers(seed, n=120, w=None, h=None):
    rng = random.Random(seed)
    w = W if w is None else w
    h = H if h is None else h
    return [dict(x=rng.uniform(0, w), y=rng.uniform(0, h), vy=rng.uniform(6, 34) * K / 1.7,
                 amp=rng.uniform(4, 22), ph=rng.uniform(0, 6.28), fr=rng.uniform(.4, 1.4),
                 r=rng.uniform(1.0, 3.0) * K / 1.7 * 0.8, c=rng.choice(["w", "o", "r", "r", "r"]),
                 tw=rng.uniform(.8, 2.4), tp=rng.uniform(0, 6.28)) for _ in range(n)]


def splat_embers(frame, embers, t, n):
    # NOTE: bounds come from the FRAME shape, not this module's W/H globals,
    # so callers rendering at a different canvas size (e.g. cyber at 1600x640)
    # don't crash on edge-clipped embers.
    FH, FW = frame.shape[0], frame.shape[1]
    cols = dict(w=(255, 235, 225), o=(255, 170, 80), r=np.array(n) * 0.9 + 30)
    for e in embers:
        y = (e["y"] - e["vy"] * t) % (FH + 20) - 10
        x = e["x"] + e["amp"] * math.sin(e["ph"] + e["fr"] * t)
        al = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(e["tp"] + e["tw"] * t))
        r = e["r"]; Rr = int(r * 3) + 2
        x0, y0 = int(x) - Rr, int(y) - Rr
        if x0 < 0 or y0 < 0 or x0 + 2 * Rr + 1 > FW or y0 + 2 * Rr + 1 > FH:
            continue
        gy, gx = np.mgrid[-Rr:Rr + 1, -Rr:Rr + 1].astype(np.float32)
        g = np.exp(-(((gx - (x - int(x))) ** 2 + (gy - (y - int(y))) ** 2) / (0.9 * r * r))) * al
        frame[y0:y0 + 2 * Rr + 1, x0:x0 + 2 * Rr + 1] += g[..., None] * np.array(cols[e["c"]], np.float32) * 0.85


def jag(x0, y0, x1, y1, rng, n=9, amp=7):
    pts = []
    for i in range(n + 1):
        u = i / n
        pts.append((x0 + (x1 - x0) * u + (rng.uniform(-amp, amp) if 0 < i < n else 0),
                    y0 + (y1 - y0) * u + (rng.uniform(-amp, amp) if 0 < i < n else 0)))
    return pts


# ------------------------------------------------------------------ gauge (dynamic) -----
class Gauge:
    def __init__(self, p):
        self.p = p
        self.n = np.array(p["n"], np.float32); self.hot = np.array(p["hot"], np.float32)
        self.tx = np.array(p["tx"], np.float32)
        w, h = RX1 - RX0, RY1 - RY0
        self.w, self.h = w, h
        SS = 3
        cx, cy = px(PIV[0]) - RX0, px(PIV[1]) - RY0
        self.c = (cx, cy)

        def ring(r_out, r_in):
            m = Image.new("L", (w * SS, h * SS), 0)
            dd = ImageDraw.Draw(m)
            dd.ellipse(((cx - r_out) * SS, (cy - r_out) * SS, (cx + r_out) * SS, (cy + r_out) * SS), fill=255)
            dd.ellipse(((cx - r_in) * SS, (cy - r_in) * SS, (cx + r_in) * SS, (cy + r_in) * SS), fill=0)
            dd.rectangle((0, (cy + 1) * SS, w * SS, h * SS), fill=0)
            rc = (r_out - r_in) / 2.0
            rm = (r_out + r_in) / 2.0
            for ex in (cx - rm, cx + rm):
                dd.ellipse(((ex - rc) * SS, (cy - rc) * SS, (ex + rc) * SS, (cy + rc) * SS), fill=255)
            return np.asarray(m.resize((w, h), Image.BOX), np.float32) / 255.

        Ra = px(R_ARC)
        self.ring = ring(Ra + px(HALF_T), Ra - px(HALF_T))
        self.hi = ring(Ra + px(1.9), Ra - px(1.9))
        self.glow = blur(self.ring, 6 * K / 1.7) * 1.0 + blur(self.ring, 17 * K / 1.7) * 0.8
        Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
        self.v = 1 - np.arctan2(cy - Y, X - cx) / math.pi
        self.X, self.Y = X, Y
        self.numcache = {}
        # width of "10x" should be ~170 design px
        f = font(F_BI, 200)
        wd = f.getlength("10x")
        self.num_size = 200 * (170 * K) / wd

    def number_layer(self, s):
        if s in self.numcache:
            return self.numcache[s]
        n = tuple(int(v) for v in self.p["n"]); tx = tuple(int(v) for v in self.p["tx"])
        f = font(F_BI, self.num_size)
        bw, bh = int(px(300)), int(px(150))
        c = (bw // 2, bh // 2)
        m = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(m).text(c, s, font=f, fill=255, anchor="mm", stroke_width=3, stroke_fill=255)
        mm = np.asarray(m, np.float32) / 255.
        glow = blur(mm, 5 * K / 1.7) * 0.9 + blur(mm, 16 * K / 1.7) * 0.75
        base = np.zeros((bh, bw, 3), np.float32) + np.array(n, np.float32) * glow[..., None] * 0.9
        alpha_g = np.clip(glow, 0, 1)
        # coloured outline + pale fill
        ol = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        od = ImageDraw.Draw(ol)
        od.text(c, s, font=f, fill=(*n, 255), anchor="mm", stroke_width=4, stroke_fill=(*n, 255))
        od.text(c, s, font=f, fill=(*tx, 255), anchor="mm")
        ola = np.asarray(ol, np.float32)
        arr = np.zeros((bh, bw, 4), np.float32)
        # additive glow stored in rgb with alpha 0 -> keep separate
        self.numcache[s] = (base, ola)
        return self.numcache[s]

    def draw(self, frame, vcur, label, ts, t, pulse, trav):
        n, hot = self.n, self.hot
        reg = frame[RY0:RY1, RX0:RX1]
        fm = np.clip((vcur - self.v) / 0.010, 0, 1)
        fm_g = np.clip((vcur - self.v) / 0.05, 0, 1)
        # dim track
        reg += n * (self.ring * 0.16)[..., None]
        # glow of the filled part
        reg += n * (self.glow * fm_g * 0.62 * pulse)[..., None]
        al = (self.ring * fm)[..., None]
        reg[:] = reg * (1 - al) + n * al
        hl = self.hi * fm
        tb = np.exp(-(((self.v - trav) / 0.03) ** 2)) * 0.45 if trav is not None else 0
        hl = (hl * np.clip(0.82 + tb, 0, 1))[..., None]
        reg[:] = reg * (1 - hl) + (hot * 0.9 + 25) * hl
        # needle
        cx, cy = self.c
        ang = math.pi * (1 - vcur)
        L = px(R_ARC - 12)
        tip = (cx + L * math.cos(ang), cy - L * math.sin(ang))
        nx, ny = -math.sin(ang), -math.cos(ang)
        SS = 3
        m = Image.new("L", (self.w * SS, self.h * SS), 0)
        dd = ImageDraw.Draw(m)
        bw_, tw_ = px(5.2), px(1.2)
        poly = [(cx + nx * bw_, cy + ny * bw_), (tip[0] + nx * tw_, tip[1] + ny * tw_),
                (tip[0] - nx * tw_, tip[1] - ny * tw_), (cx - nx * bw_, cy - ny * bw_)]
        dd.polygon([(x * SS, y * SS) for x, y in poly], fill=255)
        nm = np.asarray(m.resize((self.w, self.h), Image.BOX), np.float32) / 255.
        ng = blur(nm, 5 * K / 1.7)
        reg += n * (ng * 1.1)[..., None]
        al = nm[..., None]
        reg[:] = reg * (1 - al) + (hot * 0.92 + 20) * al
        # pivot
        dist = np.sqrt((self.X - cx) ** 2 + (self.Y - cy) ** 2)
        reg += n * (np.exp(-((dist / px(30)) ** 2)) * 0.95 * pulse)[..., None]
        ra = np.clip(px(17) + 1 - dist, 0, 1)[..., None]
        reg[:] = reg * (1 - ra) + n * ra
        ca = np.clip(px(10) + 1 - dist, 0, 1)[..., None]
        reg[:] = reg * (1 - ca) + (hot * 0.95 + 15) * ca
        # big number
        glow, ola = self.number_layer(label)
        nh, nw = glow.shape[:2]
        ox, oy = int(cx - nw / 2), int(px(255) - RY0 - nh / 2)
        reg[oy:oy + nh, ox:ox + nw] += glow * pulse
        a_ = ola[..., 3:4] / 255.
        reg[oy:oy + nh, ox:ox + nw] = reg[oy:oy + nh, ox:ox + nw] * (1 - a_) + ola[..., :3] * a_


# ------------------------------------------------------------------ render ---------------
def build_gauge_video(*, kol_name="pumpwatch1", x_val=10, symbol="PI", chain="SOL", entry_mc=0, now_mc=0,
                      rank=1, points=0, calls=0, win_rate="0%", avatar_path=None, logo_path=None,
                      out_path="champion.mp4", tier=None, preview_times=None, crf=14, preset="slow"):
    x_val = float(x_val)
    tier = tier or tier_for(x_val)
    p = PALETTES[tier]
    n = np.array(p["n"], np.float32)
    if not logo_path:
        for nm in ("golden_logo.png", "golden_logo.jpg", "wizard_logo.png"):
            for d_ in (HERE, os.path.join(HERE, "assets")):
                if os.path.exists(os.path.join(d_, nm)):
                    logo_path = os.path.join(d_, nm)
                    break
            if logo_path:
                break
    st = build_static(p, kol_name, symbol, chain, entry_mc, now_mc, rank, points, calls, win_rate, avatar_path,
                      logo_path)
    G, lm, fm, tint = st["G"], st["lm"], st["fm"], st["tint"]
    trgb, ta = st["text"][..., :3], st["text"][..., 3:4] / 255.
    gtrgb, gta = st["gtext"][..., :3], st["gtext"][..., 3:4] / 255.
    masks = box_masks()
    base, DX, DY = build_background(p)
    R = np.sqrt(DX * DX + DY * DY).astype(np.float32)
    g = Gauge(p)
    TH = np.arctan2(DY, DX).astype(np.float32)
    ray_fall = np.exp(-R / px(560)).astype(np.float32)
    embers = make_embers(7)
    rows = np.arange(H, dtype=np.float32)[:, None]
    cols_ = np.arange(W, dtype=np.float32)[None, :]
    noise = (np.random.RandomState(1).rand(H, W, 1).astype(np.float32) - 0.5) * 1.6
    vmax = min(x_val, 10.0) / 10.0
    T_START, T_END = 0.30, 1.70
    n_frames = int(DUR * FPS)
    flick = [1, 0.15, 1, 0.5, 1, 1, 0.3, 1, 1, 0.7, 1, 1]
    lf = {}
    for k in range(40, n_frames - 2, 27):
        for j in range(3):
            lf[k + j] = (["kol", "rank"][(k // 27) % 2], k)

    def frame_at(i):
        t = i / FPS
        ts = t - T_END
        if t < 0.08:
            pw = 0.0
        elif t < 0.5:
            pw = flick[int((t - 0.08) * 30) % len(flick)]
        else:
            pw = 1.0
        pulse = (1.0 + 0.09 * math.sin(2 * math.pi * t / 2.4)) * pw
        if ts >= 0:
            pulse *= 1.0 + 0.55 * math.exp(-ts / 0.45)
        fr = base.copy() * (0.35 + 0.65 * pw)
        # rotating light rays + soft streak + embers (behind everything)
        boost = 1.0 + (2.6 * math.exp(-ts / 0.8) if ts >= 0 else 0.0)
        rays = (0.5 + 0.5 * np.cos(26 * (TH + 0.22 * t))) ** 3 * ray_fall
        rays *= (DY < px(40))
        fr += n * (rays * 0.14 * boost * min(1.0, t / 0.5))[..., None]
        streak = np.exp(-(((rows - px(300)) / px(9)) ** 2))
        shimmer = 0.5 + 0.5 * np.sin(cols_ / 140 + t * 1.3)
        fr += (n * 0.5 + 40) * (streak * shimmer * 0.075)[..., None]
        splat_embers(fr, embers, t, p["n"])
        fr += tint * pw
        fr += G * pulse
        fr = fr * (1 - fm[..., None] * 0.88)
        core = (lm * pw)[..., None]
        fr = fr * (1 - core) + (n * 0.98 + 12) * core
        fr = fr * (1 - ta * pw) + trgb * ta * pw
        fr = fr * (1 - gta * pw) + gtrgb * gta * pw
        prog = ease_out2((t - T_START) / (T_END - T_START)) if t >= T_START else 0.0
        vcur = vmax * prog
        if ts >= 0:
            vcur = vmax + 0.004 * math.sin(ts * 26) * math.exp(-ts / 0.35)
        num = x_val * prog
        if prog >= 1:
            label = f"{x_val:g}x"
        else:
            label = f"{int(num)}x" if num >= 1 else "0x"
        trav = ((t - T_END) * 0.45) % 1.5 if ts >= 0.4 else None
        g.draw(fr, vcur, label, ts, t, pulse if pw > 0 else 0.0, trav)
        # arrival: FLASH + shockwave + electric bolts
        if 0 <= ts < 0.9:
            fl = math.exp(-ts / 0.2)
            fr += (n * 0.75 + 120) * (np.exp(-R / px(340)) * fl * 0.7)[..., None]
            fr += (n * 0.30 + 95) * (0.42 * math.exp(-ts / 0.09))
            if ts < 0.75:
                fr += (n * 0.75 + 70) * (np.exp(-(((R - ts * 1900) / px(15)) ** 2)) * (1 - ts / 0.75) * 0.85)[..., None]
            if ts < 0.30:
                r2 = random.Random(i * 13 + 5)
                lay = Image.new("L", (W, H), 0)
                ld = ImageDraw.Draw(lay)
                pxp, pyp = px(PIV[0]), px(PIV[1])
                for _ in range(6):
                    an = r2.uniform(math.pi * 0.08, math.pi * 0.92)
                    ln = px(R_ARC) * r2.uniform(0.85, 1.08)
                    ld.line(jag(pxp, pyp, pxp + ln * math.cos(an), pyp - ln * math.sin(an), r2, 10, 16),
                            fill=255, width=3)
                lmk = np.asarray(lay, np.float32) / 255.
                lgk = blur(lmk, 5)
                amp = 1.0 - ts / 0.30
                fr += (n * 0.8 + 90) * (lgk * 1.5 * amp)[..., None]
                fr += 255 * (lmk * 0.9 * amp)[..., None]
        # shine sweeps across the boxes
        for bi, (k, (bb, m)) in enumerate(masks.items()):
            ph = (t * 0.33 + bi * 0.11) % 1.0
            if ph < 0.55 and t > 0.6:
                x0, y0, x1, y1 = bb
                u = ph / 0.55
                xs = np.arange(x1 - x0, dtype=np.float32)[None, :]
                pos = -40 + u * (x1 - x0 + 80)
                band = np.exp(-(((xs - pos) / 24.0) ** 2))
                fr[y0:y1, x0:x1] += (n * 0.35 + 150) * (band * m * 0.22)[..., None]
        # electric lightning inside the header boxes
        if i in lf:
            k, k0 = lf[i]
            bb, m = masks[k]
            x0, y0, x1, y1 = bb
            r2 = random.Random(k0 * 7 + i)
            lay = Image.new("L", (x1 - x0, y1 - y0), 0)
            ld = ImageDraw.Draw(lay)
            xs_ = r2.uniform(30, x1 - x0 - 30)
            ld.line(jag(xs_, 2, xs_ + r2.uniform(-40, 40), y1 - y0 - 2, r2, 9, 8), fill=255, width=2)
            lm_ = np.asarray(lay, np.float32) / 255.
            lg_ = np.asarray(lay.filter(ImageFilter.GaussianBlur(5)), np.float32) / 255.
            fr[y0:y1, x0:x1] += (n * 0.8 + 90) * (lg_ * 1.5 * m)[..., None]
            fr[y0:y1, x0:x1] += 255 * (lm_ * 0.9 * m)[..., None]
        if t < 0.08:
            fr *= 0.0
        fr += noise
        return np.clip(fr, 0, 255).astype(np.uint8)

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


if __name__ == "__main__":
    import sys
    build_gauge_video(kol_name="pumpwatch1", x_val=float(sys.argv[1]) if len(sys.argv) > 1 else 10,
                      symbol="PI", chain="SOL", entry_mc=145500, now_mc=875600, rank=1, points=142, calls=117,
                      win_rate="42%", out_path=sys.argv[2] if len(sys.argv) > 2 else "champion_10x.mp4")
