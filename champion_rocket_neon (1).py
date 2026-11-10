"""
champion_rocket_neon.py - native 1600x640 (2.5:1, fomo size) renderer for the ROCKET design (big multiplier on the
left, neon chart + rocket on the right, parallelogram stat boxes at the bottom).

    build_rocket_video(kol_name="Pumpwatch1", x_val=20, symbol="PI", chain="SOL", entry_mc=145500,
                       now_mc=875600, rank=1, points=142, calls=117, win_rate="42%",
                       logo_path=None, avatar_path=None, out_path="out.mp4")

Needs: Pillow, numpy, ffmpeg. Fonts: Poppins-Bold / BoldItalic / Regular next to this file (or CHAMPION_FONT_DIR).
Logo: golden_logo.png/jpg next to this file (or logo_path=...).
"""
import math, os, random, shutil, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1600, 640, 30
K = 1600 / 1124.0            # layout coordinates are in the 1124x450 design -> x1.4235 (2.5:1, fomo size)
# NOTE (Nov 10): design height is 450 (was 400) so 1124x450 = 2.5:1. All y design values
# were scaled by 450/400 = 1.125 from the 1920x684 version; KX ~= KY so one K is fine.
DUR = 6.0
HERE = os.path.dirname(os.path.abspath(__file__))

PALETTES = {
    "blue":   dict(n=(46, 112, 255), hot=(220, 234, 255), tx=(150, 185, 255), sub=(95, 145, 255), top=(215, 232, 255), bot=(66, 112, 255)),
    "red":    dict(n=(255, 34, 52), hot=(255, 225, 230), tx=(255, 190, 200), sub=(255, 110, 120), top=(255, 226, 230), bot=(255, 60, 80)),
    "orange": dict(n=(255, 120, 20), hot=(255, 236, 210), tx=(255, 214, 170), sub=(255, 160, 80), top=(255, 240, 215), bot=(255, 120, 30)),
    "green":  dict(n=(40, 255, 110), hot=(220, 255, 232), tx=(190, 255, 215), sub=(110, 255, 160), top=(225, 255, 236), bot=(40, 230, 100)),
    "purple": dict(n=(170, 80, 255), hot=(236, 220, 255), tx=(215, 190, 255), sub=(190, 130, 255), top=(240, 228, 255), bot=(160, 80, 255)),
    "bw":     dict(n=(255, 255, 255), hot=(255, 255, 255), tx=(235, 235, 235), sub=(220, 220, 220), top=(255, 255, 255), bot=(170, 170, 170)),
}


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
F_REG = _find("Poppins-Regular.ttf", "Poppins-Medium.ttf", "DejaVuSans.ttf")


def font(path, px_):
    return ImageFont.truetype(path, max(6, int(round(px_)))) if path else ImageFont.load_default()


def ffmpeg_bin():
    p = shutil.which("ffmpeg")
    if p:
        return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def ease_io(u):
    u = min(1.0, max(0.0, u)); return u * u * (3 - 2 * u)


def ease_out(u):
    u = min(1.0, max(0.0, u)); return 1 - (1 - u) ** 3


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


def jag(x0, y0, x1, y1, rng, n=9, amp=7):
    pts = []
    for i in range(n + 1):
        u = i / n
        pts.append((x0 + (x1 - x0) * u + (rng.uniform(-amp, amp) if 0 < i < n else 0),
                    y0 + (y1 - y0) * u + (rng.uniform(-amp, amp) if 0 < i < n else 0)))
    return pts


def px(v):
    return v * K


# ------------------------------------------------------------------ layout (design px) ---
FRAME = (6, 7, 1117, 442)
# Safe-zone layout (Nov 10): Telegram phone preview ~6% har side se crop karta hai.
# Left avatar/box x>=64, right rank box x<=1069. Big number centre moved right (232->265)
# so "20.0x" is not cut on the left. STAT row shifted right (was x=36) so no box is cut.
KOL = (64, 25, 302, 89)
RANK = (870, 25, 1069, 89)
SK = 14
STAT = dict(entry=(64, 356, 298, 425), now=(303, 356, 539, 425), points=(555, 356, 703, 425),
            calls=(718, 356, 866, 425), win=(870, 356, 1060, 425))
LOGO = (457, 55, 26)
TITLE_X, TITLE_Y = 493, 56
CHART = [(446, 336), (528, 333), (566, 315), (617, 312), (669, 286), (708, 289), (766, 250), (806, 252),
         (866, 203), (908, 200), (942, 171)]
NUM_C = (265, 189)
SUB_C = (200, 325)


def poly_pts(b, sk=SK):
    x0, y0, x1, y1 = b
    return [(x0 + sk, y0), (x1, y0), (x1 - sk, y1), (x0, y1)]


# ------------------------------------------------------------------ static ---------------
def build_static(p, kol_name, symbol, chain, rank, avatar_path, logo_path):
    n = np.array(p["n"], np.float32)
    SS = 2
    S = lambda v: v * K * SS
    big = (W * SS, H * SS)
    lines = Image.new("L", big, 0); ld = ImageDraw.Draw(lines)
    fills = Image.new("L", big, 0); fd = ImageDraw.Draw(fills)
    lw = int(S(2.2))

    def rr(b, r):
        ld.rounded_rectangle((S(b[0]), S(b[1]), S(b[2]), S(b[3])), S(r), outline=255, width=lw)
        fd.rounded_rectangle((S(b[0]), S(b[1]), S(b[2]), S(b[3])), S(r), fill=255)

    ld.rounded_rectangle((S(FRAME[0]), S(FRAME[1]), S(FRAME[2]), S(FRAME[3])), S(20), outline=255, width=lw)
    rr(KOL, 14); rr(RANK, 14)
    for k, b in STAT.items():
        pts = [(S(x), S(y)) for x, y in poly_pts(b)]
        fd.polygon(pts, fill=255)
        ld.line(pts + [pts[0], pts[1]], fill=255, width=lw, joint="curve")
        r_ = lw / 2
        for (x, y) in pts:
            ld.ellipse((x - r_, y - r_, x + r_, y + r_), fill=255)
    ax, ay, ar = 93, 56, 16
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
        txt((ax, ay - 5), "PUMP", fb(8), (60, 235, 120, 255))
        txt((ax, ay + 5), "WATCH", fb(8), (60, 235, 120, 255))
    name = (kol_name or "KOL").lstrip("@")
    sz = 25
    while sz > 10 and font(F_BOLD, S(sz)).getlength(name) > S(168):
        sz -= 1
    txt((126, 44), name, fb(sz), (255, 255, 255, 255), "lm")
    txt((126, 73), "CHAMPION KOL \u00b7 X ALERT", fb(10), (*p["sub"], 255), "lm")
    # title
    x0 = TITLE_X
    for part, fnt, col in (("Wizard ", fb(25), (255, 255, 255, 255)), ("Scan", fb(25), (*p["sub"], 255)),
                           (" Call Tracker", font(F_REG, S(25)), (255, 255, 255, 255))):
        txt((x0, TITLE_Y), part, fnt, col, "lm")
        x0 += fnt.getlength(part) / (K * SS)
    txt((970, 41), "RANK ON WIZARDSCANLIVE", fb(9), (240, 240, 245, 255))
    # stat labels
    for k, lab in (("entry", "ENTRY MC"), ("now", "NOW"), ("points", "POINTS"), ("calls", "CALLS"), ("win", "WIN RATE")):
        b = STAT[k]
        txt(((b[0] + b[2]) / 2, b[1] + 21), lab, fb(9), (235, 235, 242, 255))
    # logo
    lgx, lgy, lgr = LOGO
    la = Image.new("L", big, 0)
    if logo_path and os.path.exists(logo_path):
        lg = circle_crop(Image.open(logo_path), int(S(2 * lgr)))
        tl.paste(lg, (int(S(lgx - lgr)), int(S(lgy - lgr))), lg)
    else:
        td.ellipse((S(lgx - lgr), S(lgy - lgr), S(lgx + lgr), S(lgy + lgr)), fill=(8, 8, 8, 255), outline=(255, 190, 0, 255), width=int(S(2.6)))
        txt((lgx, lgy + 0.5), "W", font(F_BOLD, S(27)), (255, 190, 0, 255))
    ImageDraw.Draw(la).ellipse((S(lgx - lgr + 3), S(lgy - lgr + 3), S(lgx + lgr - 3), S(lgy + lgr - 3)), outline=255, width=int(S(3)))
    lam = np.asarray(la.resize((W, H), Image.LANCZOS), np.float32) / 255.

    # glowing texts
    gl = Image.new("L", big, 0); gd = ImageDraw.Draw(gl)
    gt = Image.new("RGBA", big, (0, 0, 0, 0)); gtd = ImageDraw.Draw(gt)
    fr_ = font(F_BI, S(35))
    gd.text((S(970), S(70)), f"#{rank}", font=fr_, fill=255, anchor="mm")
    gtd.text((S(970), S(70)), f"#{rank}", font=fr_, fill=(235, 242, 255, 255), anchor="mm")
    sub = f"${(symbol or 'TOKEN').upper()} \u00b7 {(chain or 'SOL').upper()}"
    fs = fb(24)
    gd.text((S(SUB_C[0]), S(SUB_C[1])), sub, font=fs, fill=255, anchor="mm")
    gtd.text((S(SUB_C[0]), S(SUB_C[1])), sub, font=fs, fill=(*p["sub"], 255), anchor="mm")
    gm = np.asarray(gl.resize((W, H), Image.LANCZOS), np.float32) / 255.
    text_rgba = np.asarray(tl.resize((W, H), Image.LANCZOS), np.float32)
    gtext_rgba = np.asarray(gt.resize((W, H), Image.LANCZOS), np.float32)

    glow_n = blur(lm, 2.7) * 1.0 + blur(lm, 7.7) * 0.85 + blur(lm, 17.6) * 0.30
    glow_t = blur(gm, 3.0) * 0.9 + blur(gm, 8.2) * 0.5
    G = n * (glow_n + glow_t)[..., None] * 0.55
    G += np.array((255, 190, 0), np.float32) * (blur(lam, 3.5) * 0.7 + blur(lam, 9.4) * 0.4)[..., None] * 0.35
    tint = n * (fm * 0.03)[..., None]
    return dict(G=G.astype(np.float32), lm=lm, fm=fm, tint=tint.astype(np.float32), text=text_rgba, gtext=gtext_rgba)


def local_masks():
    out = {}
    SS = 2
    for k, b in STAT.items():
        pts = poly_pts(b)
        x0, y0, x1, y1 = [int(round(v * K)) for v in (b[0], b[1], b[2], b[3])]
        m = Image.new("L", ((x1 - x0) * SS, (y1 - y0) * SS), 0)
        ImageDraw.Draw(m).polygon([((x - b[0]) * K * SS, (y - b[1]) * K * SS) for x, y in pts], fill=255)
        out[k] = ((x0, y0, x1, y1), np.asarray(m.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32) / 255.)
    for k, b in (("kol", KOL), ("rank", RANK)):
        x0, y0, x1, y1 = [int(round(v * K)) for v in b]
        m = Image.new("L", ((x1 - x0) * SS, (y1 - y0) * SS), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, (x1 - x0) * SS - 1, (y1 - y0) * SS - 1), 14 * K * SS, fill=255)
        out[k] = ((x0, y0, x1, y1), np.asarray(m.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32) / 255.)
    return out


def perimeter(b, step=2.0):
    pts = poly_pts(b)
    seq = []
    for i in range(4):
        a, c = pts[i], pts[(i + 1) % 4]
        L = math.hypot(c[0] - a[0], c[1] - a[1])
        m = max(2, int(L / step))
        for j in range(m):
            u = j / m
            seq.append((a[0] + (c[0] - a[0]) * u, a[1] + (c[1] - a[1]) * u))
    return seq


# ------------------------------------------------------------------ background ----------
def build_background(p):
    n = np.array(p["n"], np.float32)
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    base = np.zeros((H, W, 3), np.float32)
    base += np.array([3, 7, 24], np.float32) * (1.05 - 0.35 * yy)[..., None] * (0.6 + 0.4 * n / 255.)
    vig = 1 - 0.40 * (((xx - .5) / .75) ** 2 + ((yy - .55) / .95) ** 2)
    base *= np.clip(vig, 0.45, 1)[..., None]
    return base


def make_stars(seed):
    rng = random.Random(seed)
    L = []
    for layer, (cnt, sp, rr, al) in enumerate(((70, 10, 1.1, 0.55), (45, 26, 1.7, 0.75), (22, 60, 2.4, 0.95))):
        for _ in range(cnt):
            L.append(dict(x=rng.uniform(0, W), y=rng.uniform(0, H), sp=sp * K / 1.7 * rng.uniform(.8, 1.2),
                          r=rr * K / 1.7 * rng.uniform(.8, 1.25), al=al, tw=rng.uniform(.6, 2.2), tp=rng.uniform(0, 6.28)))
    return L


def splat_stars(fr, stars, t, n):
    for s in stars:
        x = (s["x"] - s["sp"] * 0.8 * t) % W
        y = (s["y"] + s["sp"] * 0.45 * t) % H
        al = s["al"] * (0.55 + 0.45 * math.sin(s["tp"] + s["tw"] * t))
        r = s["r"]; Rr = int(r * 3) + 2
        x0, y0 = int(x) - Rr, int(y) - Rr
        if x0 < 0 or y0 < 0 or x0 + 2 * Rr + 1 > W or y0 + 2 * Rr + 1 > H:
            continue
        gy, gx = np.mgrid[-Rr:Rr + 1, -Rr:Rr + 1].astype(np.float32)
        g = np.exp(-(((gx - (x - int(x))) ** 2 + (gy - (y - int(y))) ** 2) / (0.8 * r * r))) * al
        fr[y0:y0 + 2 * Rr + 1, x0:x0 + 2 * Rr + 1] += g[..., None] * (n * 0.55 + 105)


# ------------------------------------------------------------------ rocket ---------------
def build_sprite(p):
    SSr = 4
    wd, ht = 120, 90
    im = Image.new("RGBA", (wd * SSr, ht * SSr), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = 60 * SSr, 45 * SSr

    def P(pts):
        return [(cx + x * SSr, cy + y * SSr) for x, y in pts]

    nb = tuple(p["bot"])
    d.polygon(P([(-4, -13), (-30, -37), (-41, -31), (-35, -9)]), fill=(*nb, 255))
    d.polygon(P([(-4, 13), (-30, 37), (-41, 31), (-35, 9)]), fill=(int(nb[0] * .7), int(nb[1] * .7), int(nb[2] * .85), 255))
    body = [(55, 0), (46, -6), (36, -10), (20, -13.5), (-10, -14.5), (-34, -11.5), (-41, -8), (-41, 8), (-34, 11.5),
            (-10, 14.5), (20, 13.5), (36, 10), (46, 6)]
    d.polygon(P(body), fill=(236, 243, 255, 255))
    d.polygon(P([(-41, 8), (-34, 11.5), (-10, 14.5), (20, 13.5), (36, 10), (46, 6), (30, 3), (-20, 4), (-41, 2)]),
              fill=(186, 206, 250, 255))
    d.polygon(P([(55, 0), (46, -6), (36, -10), (44, -3)]), fill=(255, 255, 255, 255))
    d.polygon(P([(55, 0), (47, -5), (47, 5)]), fill=(*nb, 255))
    d.ellipse((cx + 5 * SSr, cy - 8 * SSr, cx + 23 * SSr, cy + 8 * SSr), fill=(*nb, 255))
    d.ellipse((cx + 8 * SSr, cy - 5.2 * SSr, cx + 20 * SSr, cy + 5.2 * SSr), fill=(14, 28, 120, 255))
    d.ellipse((cx + 10 * SSr, cy - 3.8 * SSr, cx + 14 * SSr, cy - 0.4 * SSr), fill=(150, 190, 255, 255))
    return im, SSr, (wd, ht)


class PathInfo:
    def __init__(self):
        self.pts = [(x * K, y * K) for x, y in CHART]
        self.cum = [0.0]
        for a, b in zip(self.pts[:-1], self.pts[1:]):
            self.cum.append(self.cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.total = self.cum[-1]

    def at(self, s):
        s = min(max(s, 0), self.total)
        for i in range(1, len(self.pts)):
            if s <= self.cum[i]:
                u = (s - self.cum[i - 1]) / max(1e-6, self.cum[i] - self.cum[i - 1])
                a, b = self.pts[i - 1], self.pts[i]
                return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        return self.pts[-1]

    def direction(self, s):
        look = px(80)
        a = self.at(max(0, s - look)) if s > look else self.at(0)
        b = self.at(s) if s > look else self.at(look)
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        return dx / L, dy / L

    def partial(self, s):
        out = [self.pts[0]]
        for i in range(1, len(self.pts)):
            if s >= self.cum[i]:
                out.append(self.pts[i])
            else:
                out.append(self.at(s)); break
        return out


# ------------------------------------------------------------------ big number -----------
class BigNumber:
    def __init__(self, p, final_label):
        self.p = p
        self.cache = {}
        ref = font(F_BI, 200)
        w_ref = ref.getlength("6.0x")
        self.size_ref = 200 * (365 * K) / w_ref
        w_fin = ref.getlength(final_label)
        self.size = min(self.size_ref, 200 * (372 * K) / max(w_fin, 1))

    def layer(self, s):
        if s in self.cache:
            return self.cache[s]
        p = self.p
        f = font(F_BI, self.size)
        bw, bh = int(px(430)), int(px(200))
        c = (bw // 2, bh // 2 + 8)
        m = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(m).text(c, s, font=f, fill=255, anchor="mm")
        mk = np.asarray(m, np.float32) / 255.
        ms = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(ms).text(c, s, font=f, fill=255, anchor="mm", stroke_width=5, stroke_fill=255)
        mks = np.asarray(ms, np.float32) / 255.
        ys = np.where(mk.sum(1) > 0)[0]
        y0, y1 = (ys.min(), ys.max()) if len(ys) else (0, bh - 1)
        gy = np.clip((np.arange(bh, dtype=np.float32) - y0) / max(1, y1 - y0), 0, 1)[:, None, None]
        top = np.array(p["top"], np.float32); bot = np.array(p["bot"], np.float32)
        face = top * (1 - gy) + bot * gy
        glow = blur(mks, 6.0) * 0.9 + blur(mks, 20.0) * 0.8
        edge = np.clip(mks - mk, 0, 1)
        self.cache[s] = (glow.astype(np.float32), face.astype(np.float32), mk, edge)
        return self.cache[s]

    def draw(self, fr, s, pulse, flash=0.0):
        n = np.array(self.p["n"], np.float32)
        glow, face, mk, edge = self.layer(s)
        bh, bw = mk.shape
        cx, cy = px(NUM_C[0]), px(NUM_C[1])
        x0, y0 = int(cx - bw / 2), int(cy - bh / 2)
        reg = fr[y0:y0 + bh, x0:x0 + bw]
        reg += n * (glow * 0.62 * pulse)[..., None]
        a = mk[..., None]
        face_c = face + np.array(self.p["hot"], np.float32) * 0.0
        if flash > 0:
            face_c = face_c * (1 - flash * 0.6) + 255 * flash * 0.6
        reg[:] = reg * (1 - a) + face_c * a
        ea = edge[..., None] * 0.55
        reg[:] = reg * (1 - ea) + (np.array(self.p["hot"], np.float32) * 0.7 + n * 0.3) * ea


def put_text(fr, s, path, size, cx, cy, fill, bold_pulse=1.0):
    f = font(path, size * 2)
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, t, r, b = tmp.textbbox((0, 0), s, font=f, anchor="lt")
    pad = 8
    im = Image.new("RGBA", ((r - l) + pad * 2, (b - t) + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), s, font=f, fill=fill, anchor="lt")
    w2, h2 = (im.width + 1) // 2, (im.height + 1) // 2
    im = im.resize((w2, h2), Image.LANCZOS)
    arr = np.asarray(im, np.float32)
    x0 = int(round(cx - w2 / 2)); y0 = int(round(cy - h2 / 2))
    reg = fr[y0:y0 + h2, x0:x0 + w2]
    a = arr[..., 3:4] / 255.
    reg[:] = reg * (1 - a) + arr[..., :3] * a


# ------------------------------------------------------------------ video ----------------
def build_rocket_video(*, kol_name="Pumpwatch1", x_val=20, symbol="PI", chain="SOL", entry_mc=0, now_mc=0,
                       rank=1, points=0, calls=0, win_rate="0%", avatar_path=None, logo_path=None,
                       out_path="champion.mp4", tier=None, preview_times=None, crf=14, preset="slow"):
    x_val = float(x_val)
    tier = tier or tier_for(x_val)
    p = PALETTES[tier]
    n = np.array(p["n"], np.float32); hot = np.array(p["hot"], np.float32)
    if not logo_path:
        for nm in ("golden_logo.png", "golden_logo.jpg", "wizard_logo.png"):
            for d_ in (HERE, os.path.join(HERE, "assets")):
                if os.path.exists(os.path.join(d_, nm)):
                    logo_path = os.path.join(d_, nm); break
            if logo_path: break
    st = build_static(p, kol_name, symbol, chain, rank, avatar_path, logo_path)
    G, lm, fm, tint = st["G"], st["lm"], st["fm"], st["tint"]
    trgb, ta = st["text"][..., :3], st["text"][..., 3:4] / 255.
    gtrgb, gta = st["gtext"][..., :3], st["gtext"][..., 3:4] / 255.
    masks = local_masks()
    base = build_background(p)
    stars = make_stars(11)
    path = PathInfo()
    sprite, SSr, (spw, sph) = build_sprite(p)
    big = BigNumber(p, f"{x_val:.1f}x")
    Yg, Xg = np.mgrid[0:H, 0:W].astype(np.float32)
    noise = (np.random.RandomState(1).rand(H, W, 1).astype(np.float32) - 0.5) * 1.6
    per = {k: perimeter(STAT[k]) for k in STAT}
    stat_glow = {}
    for k, b in STAT.items():
        x0, y0, x1, y1 = [int(round(v * K)) for v in b]
        pad = int(px(22))
        sub = lm[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
        stat_glow[k] = ((max(0, x0 - pad), max(0, y0 - pad)), blur(sub, 6.0) * 1.0 + blur(sub, 14.0) * 0.5)
    wr = float(str(win_rate).strip("%") or 0)
    T0, T1 = 0.40, 2.70          # chart/rocket flight
    n_frames = int(DUR * FPS)
    flick = [1, 0.15, 1, 0.5, 1, 1, 0.3, 1, 1, 0.7, 1, 1]
    chart_core_w = 2.4 * K

    def rocket_state(t):
        prog = ease_io((t - T0) / (T1 - T0)) if t >= T0 else 0.0
        s = path.total * prog
        d = path.direction(s)
        tipp = path.at(s)
        cen = (tipp[0] + d[0] * px(52), tipp[1] + d[1] * px(52))
        ang = d
        if t > T1:
            tt = t - T1
            cen = (cen[0], cen[1] - px(3.2) * math.sin(2 * math.pi * tt / 1.7))
            a0 = math.atan2(d[1], d[0]) + math.radians(1.6) * math.sin(2 * math.pi * tt / 2.3 + 1)
            ang = (math.cos(a0), math.sin(a0))
        return prog, s, tipp, cen, ang

    def draw_chart(fr, s, t, pulse):
        if s < 2:
            return
        pts = path.partial(s)
        x0r, y0r = int(px(430)), int(px(90)); x1r, y1r = int(px(1075)), int(px(371))
        SSl = 2
        wmask = Image.new("L", ((x1r - x0r) * SSl, (y1r - y0r) * SSl), 0)
        cmask = Image.new("L", wmask.size, 0)
        pp = [((x - x0r) * SSl, (y - y0r) * SSl) for x, y in pts]
        ImageDraw.Draw(wmask).line(pp, fill=255, width=int(5.5 * K * SSl / 1.7), joint="curve")
        ImageDraw.Draw(cmask).line(pp, fill=255, width=int(chart_core_w * SSl / 1.7 * 1.05), joint="curve")
        wm = np.asarray(wmask.resize((x1r - x0r, y1r - y0r), Image.BOX), np.float32) / 255.
        cm = np.asarray(cmask.resize((x1r - x0r, y1r - y0r), Image.BOX), np.float32) / 255.
        reg = fr[y0r:y1r, x0r:x1r]
        gw = blur(wm, 4.0) * 1.0 + blur(wm, 11.0) * 0.8
        reg += n * (gw * 0.7 * pulse)[..., None]
        a = wm[..., None] * 0.9
        reg[:] = reg * (1 - a) + (n * 0.85 + 40) * a
        a = cm[..., None]
        reg[:] = reg * (1 - a) + (hot * 0.9 + 25) * a
        # travelling highlight along the line
        if t > T1:
            ph = ((t - T1) * 0.5) % 1.4
            hs = path.total * ph
            if hs <= path.total:
                hx, hy = path.at(hs)
                lx, ly = hx - x0r, hy - y0r
                if 0 <= lx < reg.shape[1] and 0 <= ly < reg.shape[0]:
                    gy_, gx_ = np.mgrid[0:reg.shape[0], 0:reg.shape[1]].astype(np.float32)
                    gg = np.exp(-(((gx_ - lx) ** 2 + (gy_ - ly) ** 2) / (px(11) ** 2)))
                    reg += (hot * 0.8 + 40) * (gg * 0.8 * cm.max() * np.clip(wm * 3, 0, 1) + gg * 0.25)[..., None] * 0.9

    def draw_rocket(fr, t, cen, d, pulse):
        # flame + sprite + trail
        ang = d
        # flame
        R0 = int(px(190))
        x0, y0 = int(cen[0]) - R0, int(cen[1]) - R0
        x0c, y0c = max(0, x0), max(0, y0)
        x1c, y1c = min(W, x0 + 2 * R0), min(H, y0 + 2 * R0)
        gy_, gx_ = np.mgrid[y0c:y1c, x0c:x1c].astype(np.float32)
        rx, ry = gx_ - cen[0], gy_ - cen[1]
        u = rx * ang[0] + ry * ang[1]
        v = -rx * ang[1] + ry * ang[0]
        dd = -(u + px(40))
        fl = 1 + 0.18 * math.sin(t * 37) + 0.10 * math.sin(t * 61 + 1)
        Lf = px(58) * fl * (1.0 if t < T1 else 0.8)
        wv = px(11) * np.clip(1 - dd / (Lf * 1.15), 0.02, 1)
        I = np.exp(-(np.maximum(dd, 0) / Lf) * 1.7) * np.exp(-((v / wv) ** 2)) * (dd > -px(6))
        reg = fr[y0c:y1c, x0c:x1c]
        reg += (n * 1.0)[None, None, :] * (I * 0.9)[..., None] + hot * (I ** 3 * 0.85)[..., None]
        # trail particles
        for k in range(26):
            age = (t * 45 - k) % 1  # unused (kept simple)
        for k in range(1, 28):
            ts_ = t - k / 45.0
            if ts_ < T0:
                break
            _, s_, tp_, c_, d_ = rocket_state(ts_)
            tx, ty = c_[0] - d_[0] * px(42), c_[1] - d_[1] * px(42)
            age = t - ts_
            rg = random.Random(int(ts_ * 1000) + 3)
            ox, oy = rg.uniform(-5, 5) * K / 1.7, rg.uniform(-5, 5) * K / 1.7
            xx_, yy_ = tx + ox - d_[0] * age * px(60), ty + oy - d_[1] * age * px(60)
            al = max(0.0, 1 - age / 0.6)
            r_ = px(2.6) * (0.6 + 0.8 * al)
            xi, yi = int(xx_), int(yy_)
            Rr = int(r_ * 3) + 2
            if Rr < xi < W - Rr and Rr < yi < H - Rr:
                gy2, gx2 = np.mgrid[-Rr:Rr + 1, -Rr:Rr + 1].astype(np.float32)
                g = np.exp(-(((gx2 - (xx_ - xi)) ** 2 + (gy2 - (yy_ - yi)) ** 2) / (r_ * r_))) * al * 0.7
                fr[yi - Rr:yi + Rr + 1, xi - Rr:xi + Rr + 1] += g[..., None] * (n * 0.6 + 90)
        # sprite
        rot = math.degrees(math.atan2(-ang[1], ang[0]))
        sp = sprite.rotate(rot, resample=Image.BICUBIC, expand=True)
        scale = K / SSr
        sw, sh = max(1, int(sp.width * scale)), max(1, int(sp.height * scale))
        sp = sp.resize((sw, sh), Image.LANCZOS)
        arr = np.asarray(sp, np.float32)
        ox_, oy_ = int(round(cen[0] - sw / 2)), int(round(cen[1] - sh / 2))
        reg = fr[oy_:oy_ + sh, ox_:ox_ + sw]
        a = arr[..., 3:4] / 255.
        # soft glow around the body
        reg += n * (blur(arr[..., 3] / 255., 8.0) * 0.45 * pulse)[..., None]
        reg[:] = reg * (1 - a) + arr[..., :3] * a

    def local_fx(fr, key, draw_fn, intensity=1.0, masked=True):
        bb, m = masks[key]
        x0, y0, x1, y1 = bb
        lay = Image.new("L", (x1 - x0, y1 - y0), 0)
        draw_fn(ImageDraw.Draw(lay), x1 - x0, y1 - y0)
        lmk = np.asarray(lay, np.float32) / 255.
        lgk = np.asarray(lay.filter(ImageFilter.GaussianBlur(4)), np.float32) / 255.
        mm = m if masked else 1.0
        fr[y0:y1, x0:x1] += (n * 0.8 + 90)[None, None, :] * (lgk * 1.5 * intensity * mm)[..., None] if masked else 0
        fr[y0:y1, x0:x1] += 255 * (lmk * 0.9 * intensity * mm)[..., None] if masked else 0

    def block_active(i, salt, prob):
        return random.Random((i // 3) * 31 + salt).random() < prob

    def frame_at(i):
        t = i / FPS
        ts = t - T1
        if t < 0.08: pw = 0.0
        elif t < 0.5: pw = flick[int((t - 0.08) * 30) % len(flick)]
        else: pw = 1.0
        pulse = (1.0 + 0.09 * math.sin(2 * math.pi * t / 2.4)) * pw
        if 0 <= ts < 1.0:
            pulse *= 1.0 + 0.6 * math.exp(-ts / 0.4)
        fr = base.copy() * (0.4 + 0.6 * pw)
        # --- moving background: blobs, speed streaks, stars
        for k, (fx, fy, amp, col) in enumerate(((0.21, 0.17, 1.0, 0.10), (0.13, 0.27, 0.9, 0.08), (0.31, 0.11, 0.8, 0.07))):
            bx = W * (0.5 + 0.36 * math.sin(t * fx * 2 + k * 2.1))
            by = H * (0.45 + 0.3 * math.sin(t * fy * 2 + k * 1.3))
            blob = np.exp(-(((Xg - bx) / px(280)) ** 2 + ((Yg - by) / px(150)) ** 2))
            fr += n * (blob * col * amp)[..., None]
        lay = Image.new("L", (W, H), 0); sd = ImageDraw.Draw(lay)
        dirx, diry = math.cos(math.radians(-33)), math.sin(math.radians(-33))
        for k in range(14):
            rg = random.Random(900 + k)
            sp_ = rg.uniform(380, 900); ln = rg.uniform(110, 300) * K / 1.7
            x0_ = rg.uniform(-400, W + 200); y0_ = rg.uniform(60, H + 300)
            pos = (t * sp_) % (W + 700)
            hx, hy = x0_ + dirx * pos - 350 + 0, y0_ + diry * pos
            hx = (hx + 400) % (W + 800) - 400
            hy = (y0_ + diry * pos) % (H + 300)
            sd.line((hx - dirx * ln, hy - diry * ln, hx, hy), fill=int(rg.uniform(60, 150)), width=2)
        sk_ = np.asarray(lay.filter(ImageFilter.GaussianBlur(1.3)), np.float32) / 255.
        fr += n * (sk_ * 0.55 * min(1.0, t / 0.6))[..., None]
        splat_stars(fr, stars, t, n)
        # --- neon structure
        fr += tint * pw
        fr += G * pulse
        # extra glow wave on stat boxes
        for bi, (k, ((gx0, gy0), gg)) in enumerate(stat_glow.items()):
            gain = 0.45 * max(0.0, math.sin(2 * math.pi * (t / 2.2 - bi * 0.13))) ** 2 * pw
            fr[gy0:gy0 + gg.shape[0], gx0:gx0 + gg.shape[1]] += n * (gg * gain)[..., None]
        fr = fr * (1 - fm[..., None] * 0.9)
        core = (lm * pw)[..., None]
        fr = fr * (1 - core) + (n * 0.98 + 14) * core
        fr = fr * (1 - ta * pw) + trgb * ta * pw
        fr = fr * (1 - gta * pw) + gtrgb * gta * pw
        # --- hero: number, chart, rocket
        prog, s, tipp, cen, ang = rocket_state(t)
        num = x_val * prog
        label = f"{x_val:.1f}x" if prog >= 1 else f"{num:.1f}x"
        flashn = (math.exp(-ts / 0.12) if ts >= 0 else 0.0)
        big.draw(fr, label, pulse, flash=flashn)
        draw_chart(fr, s, t, pulse)
        if t >= T0:
            draw_rocket(fr, t, cen, ang, pulse)
            # glowing tip dot while flying
            if t < T1:
                gy_, gx_ = np.mgrid[0:H, 0:W].astype(np.float32) if False else (None, None)
        # --- stat values (count-up) + win bar
        cu = ease_out((t - 0.7) / 1.6) if t >= 0.7 else 0.0
        vals = dict(entry=fmt_mc(entry_mc * cu), now=fmt_mc(now_mc * cu), points=str(int(round(points * cu))),
                    calls=str(int(round(calls * cu))))
        for k, sv in vals.items():
            b = STAT[k]
            put_text(fr, sv, F_BOLD, 18 * K, (b[0] + b[2]) / 2 * K, (b[1] + 42) * K, (255, 255, 255, 255))
        b = STAT["win"]
        put_text(fr, f"{int(round(wr * cu))}%", F_BOLD, 18 * K, (b[0] + b[2]) / 2 * K, (b[1] + 37) * K, (255, 255, 255, 255))
        bx0, bx1, by0, by1 = [int(round(v * K)) for v in (b[0] + 42, b[2] - 42, b[1] + 54, b[1] + 60)]
        fr[by0:by1, bx0:bx1] = fr[by0:by1, bx0:bx1] * 0.4 + np.array([20, 36, 100], np.float32) * 0.6
        fw = int((bx1 - bx0) * min(1, wr / 100) * cu)
        if fw > 0:
            xs = np.arange(fw, dtype=np.float32)[None, :, None]
            gl_ = 0.85 + 0.3 * np.exp(-(((xs - ((t * 160) % (fw + 60) - 20)) / 14.0) ** 2))
            fr[by0:by1, bx0:bx0 + fw] = (n * 0.85 + 30) * gl_ + (hot * 0.5) * (gl_ - 0.85).clip(0) * 1.2
        # --- arrival effects (flash + shock + bolts from the rocket)
        if 0 <= ts < 0.9:
            Rr_ = np.sqrt((Xg - cen[0]) ** 2 + (Yg - cen[1]) ** 2)
            fr += (n * 0.75 + 120) * (np.exp(-Rr_ / px(260)) * math.exp(-ts / 0.2) * 0.8)[..., None]
            fr += (n * 0.3 + 90) * (0.45 * math.exp(-ts / 0.09))
            if ts < 0.75:
                fr += (n * 0.75 + 70) * (np.exp(-(((Rr_ - ts * 1500) / px(14)) ** 2)) * (1 - ts / 0.75) * 0.85)[..., None]
            if ts < 0.3:
                r2 = random.Random(i * 13 + 5)
                lay2 = Image.new("L", (W, H), 0); ld2 = ImageDraw.Draw(lay2)
                for _ in range(7):
                    an = r2.uniform(0, 2 * math.pi); ln = px(r2.uniform(70, 160))
                    ld2.line(jag(cen[0], cen[1], cen[0] + ln * math.cos(an), cen[1] + ln * math.sin(an), r2, 9, 14),
                             fill=255, width=3)
                lmk = np.asarray(lay2, np.float32) / 255.; lgk = blur(lmk, 5)
                amp = 1 - ts / 0.3
                fr += (n * 0.8 + 90) * (lgk * 1.5 * amp)[..., None]
                fr += 255 * (lmk * 0.9 * amp)[..., None]
        # --- shine sweeps + chase lights on the bottom boxes
        for bi, k in enumerate(STAT):
            bb, m = masks[k]
            x0, y0, x1, y1 = bb
            ph = (t * 0.45 + bi * 0.17) % 1.0
            if ph < 0.6 and t > 0.6:
                u = ph / 0.6
                xs = np.arange(x1 - x0, dtype=np.float32)[None, :]
                ys = np.arange(y1 - y0, dtype=np.float32)[:, None]
                pos = -40 + u * (x1 - x0 + 120)
                band = np.exp(-(((xs + ys * 0.55 - pos) / 22.0) ** 2))
                fr[y0:y1, x0:x1] += (n * 0.35 + 150) * (band * m * 0.22)[..., None]
            if t > 0.6:
                seq = per[k]
                Lp = len(seq)
                s0 = int(((t * 0.45 + bi * 0.21) % 1.0) * Lp)
                ln = int(Lp * 0.13)
                seg = [seq[(s0 + j) % Lp] for j in range(ln)]
                lay3 = Image.new("L", (x1 - x0 + 60, y1 - y0 + 60), 0)
                ImageDraw.Draw(lay3).line([((x - STAT[k][0]) * K + 30, (y - STAT[k][1]) * K + 30) for x, y in seg],
                                          fill=255, width=3)
                lmk = np.asarray(lay3, np.float32) / 255.; lgk = np.asarray(lay3.filter(ImageFilter.GaussianBlur(5)), np.float32) / 255.
                ya, xa = y0 - 30, x0 - 30
                yb, xb = ya + lay3.height, xa + lay3.width
                ysa, xsa = max(0, ya), max(0, xa)
                ysb, xsb = min(H, yb), min(W, xb)
                sl = (slice(ysa - ya, ysb - ya), slice(xsa - xa, xsb - xa))
                fr[ysa:ysb, xsa:xsb] += (n * 0.8 + 100) * (lgk[sl] * 1.3)[..., None] + 255 * (lmk[sl] * 0.85)[..., None]
        # --- lightning: rank box + kol box ONLY (logo/title lightning REMOVED per owner request)
        # rank box: zyada frequent aur thoda bright, same neon color/theme
        forced = 0 <= ts < 0.6
        if forced or block_active(i, 1, 0.75):
            r2 = random.Random(i * 5 + 1)

            def dr(d, w, h):
                x = r2.uniform(25, w - 25)
                d.line(jag(x, 1, x + r2.uniform(-35, 35), h - 1, r2, 9, 9), fill=255, width=2)
                if r2.random() < 0.7:
                    x2 = r2.uniform(25, w - 25)
                    d.line(jag(x2, 1, x2 + r2.uniform(-45, 45), h - 1, r2, 8, 8), fill=255, width=2)
                my = r2.uniform(h * .3, h * .7)
                d.line(jag(x, my, x + r2.choice([-1, 1]) * r2.uniform(25, 60), my + r2.uniform(-10, 14), r2, 5, 5), fill=255, width=1)
            local_fx(fr, "rank", dr, 1.5)
            bb, m = masks["rank"]
            fr[bb[1]:bb[3], bb[0]:bb[2]] += (n * 0.5 + 60) * (m * 0.09)[..., None]
        # kol box (channel name): pehle 0.20 prob thi, ab 0.55 — zyada dikhe, same style
        if forced or block_active(i, 3, 0.55):
            r4 = random.Random(i * 3 + 9)

            def dk(d, w, h):
                x = r4.uniform(110, w - 25)
                d.line(jag(x, 1, x + r4.uniform(-30, 30), h - 1, r4, 8, 8), fill=255, width=2)
                if r4.random() < 0.6:
                    x2 = r4.uniform(110, w - 25)
                    d.line(jag(x2, 1, x2 + r4.uniform(-35, 35), h - 1, r4, 8, 8), fill=255, width=2)
            local_fx(fr, "kol", dk, 1.4)
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
    build_rocket_video(kol_name="Pumpwatch1", x_val=float(sys.argv[1]) if len(sys.argv) > 1 else 20,
                       symbol="PI", chain="SOL", entry_mc=145500, now_mc=875600, rank=1, points=142, calls=117,
                       win_rate="42%", out_path=sys.argv[2] if len(sys.argv) > 2 else "champion_rocket.mp4")
