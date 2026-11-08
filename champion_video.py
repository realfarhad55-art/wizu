"""Champion KOL video — CLOUD-FAITHFUL speedometer (bot generator).
Recreates the user's Cloud AI video EXACTLY in PIL (no AI, pure code), so the
BOT can generate it for any champion X (2x / 5x / 8x / 10x) with real data:
  - 1920x684 (Cloud's native size), 30fps, 6s, no audio
  - red radial sunburst background (rays from the gauge hub) + embers
  - thin red neon gauge, lights up progressively 0 -> TARGET
  - WHITE needle sweeping 0 -> TARGET, glowing red hub
  - big white-pink X counting up, "$PI • SOL" below
  - top bar in black rounded boxes: Pumpwatch1 | Wizard Scan Call Tracker | RANK #1
  - right boxes: ENTRY MC / NOW / POINTS / CALLS / WIN RATE (with red bar)
  - thin red neon border around the whole frame
This file is ALSO the bot's generator: champion_alert_video(channel, x_val,
chain, entry_fmt, cur_fmt, ca, symbol, stats, avatar_path) renders the video
for one alert and returns its path. The bot calls it per champion alert.
TARGET_X from argv for the standalone preview (10 or 2)."""
import math, random, subprocess, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

TARGET_X = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
TARGET_LABEL = f"{int(TARGET_X)}x"

D = "/home/hatch/workspace/wizardscan-video"
OUT = "/home/hatch/workspace/your_files"
W, H = 1920, 684
FPS = 30
DUR = 6.0
FRAMES = int(FPS * DUR)
BOLD = "/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf"
REG = "/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf"
random.seed(5)

# ---------- colours (sampled from the Cloud frames) ----------
RED_NEON = (255, 30, 55)       # bright neon red (arc, borders)
RED_GLOW = (255, 45, 70)       # red glow
RED_DEEP = (120, 8, 20)        # deep red (unlit arc)
RED_DIM = (90, 12, 22)         # dim red (unlit arc fill)
WHITE = (255, 255, 255)
PINK_SOFT = (255, 225, 230)    # X soft pink-white
BG = (12, 2, 4)                # near-black red background
GOLD = (255, 190, 80)
GREEN = (0, 200, 100)

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def ease_out_cubic(x):
    return 1 - math.pow(1 - x, 3)

def lerp(a, b, u):
    return tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))

def scaled(img, f):
    if f <= 0:
        return None
    if f >= 1:
        return img
    a = img.split()[3].point(lambda x: int(x * f))
    out = img.copy()
    out.putalpha(a)
    return out

def vgrad(w, h, stops):
    xs = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=np.float32)
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for i in range(h):
        u = i / max(1, h - 1)
        arr[i, :, :] = [int(np.interp(u, xs, cols[:, k])) for k in range(3)]
    return Image.fromarray(arr, "RGB").convert("RGBA")

def grad_text(text, font, stops, glow=(255, 45, 70), outline=4, blur=14):
    sw = outline
    bb = font.getbbox(text, stroke_width=sw)
    pad = 40
    lw, lh = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    ox, oy = pad - bb[0], pad - bb[1]
    fill_mask = Image.new("L", (lw, lh), 0)
    ImageDraw.Draw(fill_mask).text((ox, oy), text, font=font, fill=255)
    ring = Image.new("L", (lw, lh), 0)
    ImageDraw.Draw(ring).text((ox, oy), text, font=font, fill=0,
                              stroke_width=sw, stroke_fill=255)
    out = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    g = Image.new("RGBA", (lw, lh), glow + (255,))
    g.putalpha(fill_mask.filter(ImageFilter.GaussianBlur(blur)))
    out = Image.alpha_composite(out, g)
    grad = vgrad(lw, lh, stops)
    grad.putalpha(fill_mask)
    out = Image.alpha_composite(out, grad)
    white = Image.new("RGBA", (lw, lh), (255, 255, 255, 255))
    white.putalpha(ring)
    out = Image.alpha_composite(out, white)
    return out, ox, oy

def neon_glow(layer, radius, alpha=200):
    g = layer.filter(ImageFilter.GaussianBlur(radius))
    a = g.split()[3].point(lambda x: int(x * alpha / 255.0))
    g.putalpha(a)
    return g

def neon_halo(layer):
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out = Image.alpha_composite(out, neon_glow(layer, 40, alpha=100))
    out = Image.alpha_composite(out, neon_glow(layer, 18, alpha=170))
    out = Image.alpha_composite(out, neon_glow(layer, 7, alpha=230))
    return out

# ---------- golden Wizard Scan logo (STATIC, one file) ----------
# The Cloud design uses a static golden logo. It lives next to this file
# as golden_logo.png (upload it to the server alongside champion_video.py).
# Falls back to a gold "W" circle if the file is missing.
_LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_logo.png")
LOGO_D = 84
try:
    _LOGO_IMG = Image.open(_LOGO_PATH).convert("RGBA").resize((LOGO_D, LOGO_D), Image.LANCZOS)
except Exception:
    _LOGO_IMG = None

def gold_logo_frame(f):
    if _LOGO_IMG is not None:
        return _LOGO_IMG
    # fallback: gold "W" circle (used only if golden_logo.png is missing)
    fb = Image.new("RGBA", (LOGO_D, LOGO_D), (0, 0, 0, 0))
    d = ImageDraw.Draw(fb)
    d.ellipse([2, 2, LOGO_D - 3, LOGO_D - 3], fill=(60, 40, 5, 255),
              outline=GOLD + (255,), width=3)
    d.text((LOGO_D // 2, LOGO_D // 2 - 14), "W", font=ImageFont.truetype(BOLD, 44),
           fill=GOLD + (255,), anchor="ma")
    return fb

# ---------- data (set by champion_alert_video from the real alert) ----------
# Defaults = the Cloud sample (Pumpwatch1 / $PI • SOL). The bot overwrites
# these per alert with the real channel + call data.
DATA = {
    "channel": "pumpwatch1",
    "symbol": "$PI",
    "chain": "SOL",
    "entry_fmt": "$145.5K MC",
    "cur_fmt": "$875.6K MC",
    "points": "142",
    "calls": "117",
    "win_rate": "42%",
    "rank": "#1",
}

# ---------- geometry (measured from the Cloud frames) ----------
GX, GY, GR = 750, 600, 400   # gauge hub + radius
ARC_W = 16                    # thin neon arc (Cloud is thinner than my v8)
X_CX, X_CY = 750, 430         # big X centre
F_X = ImageFont.truetype(BOLD, 210)
X_STOPS = [(0.0, (255, 255, 255)), (0.5, (255, 225, 230)), (1.0, (255, 120, 140))]
COUNT_IMGS = {}
for _i in range(int(TARGET_X * 10) + 1):
    _v = _i / 10.0
    _s = f"{_v:.1f}x" if _v != int(_v) else f"{int(_v)}x"
    _im, _ox, _oy = grad_text(_s, F_X, X_STOPS, glow=(255, 45, 70), outline=4, blur=16)
    COUNT_IMGS[_i] = (_im, _ox, _oy)
FINAL_X_IMG, _, _ = grad_text(TARGET_LABEL, F_X, X_STOPS, glow=(255, 45, 70), outline=4, blur=16)

F_CHAN = ImageFont.truetype(BOLD, 52)
F_SUB = ImageFont.truetype(BOLD, 22)
F_WIZ = ImageFont.truetype(BOLD, 48)
F_RANKL = ImageFont.truetype(BOLD, 20)
F_RANK = ImageFont.truetype(BOLD, 64)
F_LABEL = ImageFont.truetype(BOLD, 20)
F_VAL = ImageFont.truetype(BOLD, 38)
F_SYM = ImageFont.truetype(BOLD, 34)
F_TICK = ImageFont.truetype(REG, 24)
F_SMALL = ImageFont.truetype(BOLD, 17)

def angle_for_x(xval):
    return 180.0 + (xval / 10.0) * 180.0

# ---------- background: radial sunburst from the hub + embers ----------
RAYS = []
_rnd = random.Random(31)
for _ in range(30):
    # ray angle (spread around the hub, mostly upward) + width + brightness
    a = _rnd.uniform(185, 355)
    wdt = _rnd.uniform(10, 30)
    br = _rnd.uniform(0.6, 1.0)
    RAYS.append((math.radians(a), wdt, br))
EMBERS = []
for _ in range(70):
    EMBERS.append((_rnd.randint(20, W - 20), _rnd.randint(20, H - 20),
                   _rnd.randint(1, 3), _rnd.uniform(0, 6.28), _rnd.uniform(0.6, 2.2),
                   _rnd.uniform(0.4, 1.0)))

def bg_layer(t):
    img = Image.new("RGBA", (W, H), BG + (255,))
    # radial sunburst rays from the gauge hub
    rays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rays)
    for (ang, wdt, br) in RAYS:
        # each ray is a long thin triangle from the hub outward
        L = 1100
        x1 = GX + L * math.cos(ang)
        y1 = GY + L * math.sin(ang)
        px, py = -math.sin(ang), math.cos(ang)
        hw = wdt / 2
        alpha = int(52 * br * (0.8 + 0.2 * math.sin(t * 1.5 + ang)))
        rd.polygon([(GX + px * 4, GY + py * 4),
                    (x1 + px * hw, y1 + py * hw),
                    (x1 - px * hw, y1 - py * hw)],
                   fill=(255, 40, 60, max(0, alpha)))
    rays = rays.filter(ImageFilter.GaussianBlur(4))
    img = Image.alpha_composite(img, rays)
    # soft red glow at the hub
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([GX - 320, GY - 320, GX + 320, GY + 320], fill=(140, 10, 25, 55))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    img = Image.alpha_composite(img, glow)
    # embers (tiny red/orange dots drifting up)
    d = ImageDraw.Draw(img)
    for (ex, ey, er, ph, sp, br) in EMBERS:
        y = H - ((t * sp * 22 + ey) % (H + 40)) + 20
        a = int(110 * br * (0.6 + 0.4 * math.sin(t * 3 + ph)))
        d.ellipse([ex - er, y - er, ex + er, y + er], fill=(255, 90, 60, max(0, a)))
    return img

# ---------- top bar (black rounded boxes, Cloud layout) ----------
def top_bar():
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # --- channel box (left): black fill, red border ---
    d.rounded_rectangle([40, 30, 440, 132], radius=18, fill=(5, 2, 3, 255),
                        outline=RED_NEON + (255,), width=3)
    d.ellipse([62, 48, 118, 104], fill=(0, 90, 45, 255), outline=(0, 220, 110, 255), width=2)
    d.text((90, 54), "PUMP", font=F_SMALL, fill=(140, 255, 190, 255), anchor="ma")
    d.text((90, 76), "WATCH", font=F_SMALL, fill=(140, 255, 190, 255), anchor="ma")
    d.text((132, 40), DATA["channel"], font=F_CHAN, fill=(255, 255, 255, 255))
    d.text((132, 100), "CHAMPION KOL  •  X ALERT", font=F_SUB, fill=RED_NEON + (255,))
    # --- Wizard Scan (centre): golden logo + name, centred on x=960 ---
    tmp = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    w_wiz = tmp.textlength("Wizard ", font=F_WIZ)
    w_scan = tmp.textlength("Scan ", font=F_WIZ)
    w_ct = tmp.textlength("Call Tracker", font=F_WIZ)
    gap = 16
    total = LOGO_D + gap + w_wiz + w_scan + w_ct
    sx = 960 - total / 2
    logo_cx = sx + LOGO_D / 2
    tx = sx + LOGO_D + gap
    d.text((tx, 48), "Wizard", font=F_WIZ, fill=(255, 255, 255, 255))
    d.text((tx + w_wiz, 48), "Scan", font=F_WIZ, fill=RED_NEON + (255,))
    d.text((tx + w_wiz + w_scan, 48), "Call Tracker", font=F_WIZ, fill=(255, 255, 255, 255))
    # --- rank box (right): black fill, red border ---
    d.rounded_rectangle([1480, 30, 1880, 132], radius=18, fill=(5, 2, 3, 255),
                        outline=RED_NEON + (255,), width=3)
    d.text((1680, 44), "RANK ON WIZARDSCANLIVE", font=F_RANKL, fill=(255, 255, 255, 255), anchor="ma")
    d.text((1680, 96), DATA["rank"], font=F_RANK, fill=WHITE + (255,), anchor="mm",
           stroke_width=3, stroke_fill=RED_NEON + (255,))
    # glow on the boxes' borders + Scan + subtitle
    glow_src = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_src)
    gd.rounded_rectangle([40, 30, 440, 132], radius=18, outline=RED_GLOW + (255,), width=3)
    gd.rounded_rectangle([1480, 30, 1880, 132], radius=18, outline=RED_GLOW + (255,), width=3)
    gd.text((132, 100), "CHAMPION KOL  •  X ALERT", font=F_SUB, fill=RED_GLOW + (255,))
    gd.text((tx + w_wiz, 48), "Scan", font=F_WIZ, fill=RED_GLOW + (255,))
    gd.text((1680, 96), DATA["rank"], font=F_RANK, fill=RED_GLOW + (255,), anchor="mm",
            stroke_width=3, stroke_fill=RED_GLOW + (255,))
    out = Image.alpha_composite(neon_halo(glow_src), layer)
    return out, logo_cx

TOP, LOGO_CX = top_bar()
LOGO_CY = 81

# ---------- gauge ----------
def gauge_layer(xval):
    # unlit arc (dim red, full semicircle)
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    bbox = [GX - GR, GY - GR, GX + GR, GY + GR]
    d.arc(bbox, 180, 360, fill=RED_DIM + (255,), width=ARC_W)
    # lit arc (bright neon, 0 -> xval)
    lit = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lit)
    if xval > 0:
        a1 = angle_for_x(xval)
        n = max(2, int((a1 - 180) / 2.0))
        for i in range(n):
            s = 180 + (a1 - 180) * i / n
            e = 180 + (a1 - 180) * (i + 1) / n
            u = (s - 180) / 180.0
            col = lerp(RED_DEEP, (255, 60, 85), u)
            ld.arc(bbox, s, e, fill=col + (255,), width=ARC_W)
        ld.arc(bbox, 180, a1, fill=(255, 240, 245, 255), width=5)
    lit_glow = neon_halo(lit)
    # ticks + labels
    tick = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(tick)
    for xv in [0, 2, 4, 6, 8, 10]:
        ang = math.radians(angle_for_x(xv))
        r1 = GR + ARC_W // 2 + 6
        r2 = r1 + 14
        x1 = GX + r1 * math.cos(ang); y1 = GY + r1 * math.sin(ang)
        x2 = GX + r2 * math.cos(ang); y2 = GY + r2 * math.sin(ang)
        td.line([(x1, y1), (x2, y2)], fill=(255, 120, 135, 255), width=3)
        lx = GX + (GR + ARC_W // 2 + 44) * math.cos(ang)
        ly = GY + (GR + ARC_W // 2 + 44) * math.sin(ang)
        td.text((lx, ly), f"{xv}x", font=F_TICK, fill=(255, 255, 255, 255), anchor="mm")
    out = Image.alpha_composite(base, lit_glow)
    out = Image.alpha_composite(out, lit)
    out = Image.alpha_composite(out, tick)
    return out

def needle_layer(xval):
    """WHITE needle (Cloud style): long tapered blade from the hub."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ang = math.radians(angle_for_x(xval))
    tip_r = GR - 30
    tx = GX + tip_r * math.cos(ang); ty = GY + tip_r * math.sin(ang)
    perp = ang + math.pi / 2
    bw = 9
    bx1 = GX + bw * math.cos(perp); by1 = GY + bw * math.sin(perp)
    bx2 = GX - bw * math.cos(perp); by2 = GY - bw * math.sin(perp)
    d.polygon([(tx, ty), (bx1, by1), (bx2, by2)], fill=(255, 255, 255, 255))
    # hub: glowing red ring + white core
    d.ellipse([GX - 26, GY - 26, GX + 26, GY + 26], fill=RED_GLOW + (255,))
    d.ellipse([GX - 18, GY - 18, GX + 18, GY + 18], fill=(255, 255, 255, 255))
    return layer

def needle_glow_layer(xval):
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(gl)
    ang = math.radians(angle_for_x(xval))
    tip_r = GR - 30
    tx = GX + tip_r * math.cos(ang); ty = GY + tip_r * math.sin(ang)
    d.line([(GX, GY), (tx, ty)], fill=RED_GLOW + (255,), width=12)
    d.ellipse([GX - 34, GY - 34, GX + 34, GY + 34], fill=RED_GLOW + (255,))
    return neon_halo(gl)

# ---------- right boxes (values from DATA, rebuilt per alert) ----------
def _boxes_def():
    return [
        (1400, 200, 1850, 292, "ENTRY MC", DATA["entry_fmt"], "two"),
        (1400, 306, 1850, 398, "NOW", DATA["cur_fmt"], "two"),
        (1400, 412, 1610, 504, "POINTS", DATA["points"], "two"),
        (1640, 412, 1850, 504, "CALLS", DATA["calls"], "two"),
        (1400, 518, 1850, 580, "WIN RATE", DATA["win_rate"], "winrate"),
    ]

def box_mask(w, h, radius=16):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    return m

def box_static(x0, y0, x1, y1, label, value, kind):
    w, h = x1 - x0, y1 - y0
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([0, 0, w - 1, h - 1], radius=16,
                                           outline=RED_GLOW + (255,), width=3)
    glow = neon_halo(glow)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=16,
                        fill=(5, 2, 3, 255), outline=RED_NEON + (255,), width=3)
    if kind == "two":
        d.text((w / 2, 10), label, font=F_LABEL, fill=(255, 255, 255, 255), anchor="ma")
        d.text((w / 2, 40), value, font=F_VAL, fill=WHITE + (255,), anchor="ma")
    else:
        d.text((w / 2, 6), f"WIN RATE  •  {DATA['win_rate']}", font=F_LABEL, fill=(255, 255, 255, 255), anchor="ma")
        # red progress bar at the bottom
        bx0, bx1 = 24, w - 24
        by0, by1 = h - 22, h - 10
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=6, fill=(60, 8, 14, 255))
        try:
            _wr = float(str(DATA["win_rate"]).strip().rstrip("%")) / 100.0
        except Exception:
            _wr = 0.42
        fw = (bx1 - bx0) * clamp(_wr, 0, 1)
        d.rounded_rectangle([bx0, by0, bx0 + fw, by1], radius=6, fill=RED_NEON + (255,))
    out = Image.alpha_composite(glow, layer)
    return out

def _box_statics():
    return [box_static(*b) for b in _boxes_def()]

def shine_layer(w, h, prog, band_w=110):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = -band_w + prog * (w + 2 * band_w)
    slant = 40
    d.polygon([(cx - band_w / 2, -14), (cx + band_w / 2, -14),
               (cx + band_w / 2 + slant, h + 14), (cx - band_w / 2 + slant, h + 14)],
              fill=RED_GLOW + (90,))
    d.polygon([(cx - 18, -14), (cx + 18, -14),
               (cx + 18 + slant, h + 14), (cx - 18 + slant, h + 14)],
              fill=(255, 215, 220, 120))
    return layer

def draw_boxes(img, t, shine_progs, box_statics):
    boxes = _boxes_def()
    for i, (x0, y0, x1, y1, label, value, kind) in enumerate(boxes):
        w, h = x1 - x0, y1 - y0
        layer = box_statics[i].copy()
        sp = shine_progs[i]
        if sp is not None and 0.0 <= sp <= 1.0:
            sh = shine_layer(w, h, sp)
            sh.putalpha(Image.composite(sh.split()[3], Image.new("L", (w, h), 0), box_mask(w, h)))
            layer = Image.alpha_composite(layer, sh)
        img.paste(layer, (x0, y0), layer)

def sym_layer():
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((750, 528), f"{DATA['symbol']}  •  {DATA['chain']}", font=F_SYM, fill=RED_NEON + (255,), anchor="ma")
    return layer

def outer_border(img):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rounded_rectangle([10, 10, W - 11, H - 11], radius=28, outline=RED_NEON + (255,), width=4)
    ov = Image.alpha_composite(neon_halo(ov), ov)
    out = Image.alpha_composite(img, ov)
    return out

# ---------- build ----------
def build(out_path):
    global TOP, LOGO_CX
    # rebuild the data-dependent layers from the current DATA (per alert)
    TOP, LOGO_CX = top_bar()
    SYM = sym_layer()
    box_statics = _box_statics()
    frames_dir = f"{D}/champcloud_{TARGET_LABEL}"
    os.makedirs(frames_dir, exist_ok=True)
    for f in range(FRAMES):
        t = f / FPS
        img = bg_layer(t)
        # sweep 0 -> TARGET over 1.8s (Cloud sweeps fast, then holds)
        su = ease_out_cubic(clamp(t / 1.8, 0, 1))
        gv = TARGET_X * su
        img = Image.alpha_composite(img, gauge_layer(gv))
        img = Image.alpha_composite(img, needle_glow_layer(gv))
        # X number: count-up during the sweep, final label after
        if t < 1.8:
            idx = int(round(gv * 10))
            idx = max(0, min(int(TARGET_X * 10), idx))
            cim, _, _ = COUNT_IMGS[idx]
            img.paste(cim, (X_CX - cim.width // 2, X_CY - cim.height // 2), cim)
        else:
            pulse = 1 + 0.02 * math.sin((t - 1.8) * 3.0)
            w0, h0 = FINAL_X_IMG.width, FINAL_X_IMG.height
            nw, nh = int(w0 * pulse), int(h0 * pulse)
            xi = FINAL_X_IMG.resize((nw, nh), Image.LANCZOS)
            img.paste(xi, (X_CX - nw // 2, X_CY - nh // 2), xi)
        img = Image.alpha_composite(img, needle_layer(gv))
        img = Image.alpha_composite(img, SYM)
        o_top = clamp(t / 0.4, 0, 1)
        if o_top > 0:
            tb = scaled(TOP, o_top)
            if tb:
                img.paste(tb, (0, 0), tb)
            logo = gold_logo_frame(f)
            if o_top < 1:
                logo = scaled(logo, o_top)
            if logo:
                img.paste(logo, (int(LOGO_CX - LOGO_D / 2), LOGO_CY - LOGO_D // 2), logo)
        progs = []
        for i in range(5):
            st = 1.0 + i * 0.3
            if t < st:
                progs.append(None)
            elif t < st + 0.8:
                progs.append((t - st) / 0.8)
            else:
                progs.append(None)
        draw_boxes(img, t, progs, box_statics)
        img = outer_border(img)
        oall = 1 - clamp((t - 5.2) / 0.8, 0, 1)
        if oall < 1.0:
            img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)), 1 - oall)
        img.convert("RGB").save(f"{frames_dir}/c{f:03d}.png")
    print("frames done:", TARGET_LABEL, FRAMES)
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", "30",
           "-i", f"{frames_dir}/c%03d.png",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", out_path]
    r = subprocess.run(cmd)
    print("build rc:", r.returncode)
    if r.returncode == 0:
        for ts in ["0.6", "1.4", "2.6", "4.0"]:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", ts, "-i",
                            out_path, "-frames:v", "1",
                            f"{D}/champcloud-{TARGET_LABEL}-check-{ts}.png"])
        pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of", "csv=p=0", out_path],
                            capture_output=True, text=True)
        print("out:", TARGET_LABEL, pr.stdout.strip())

# ---------- bot entry point (drop-in for the server's champion_video.py) ----------
def champion_alert_video(channel="", x_val=10, chain="SOL", entry_fmt="$145.5K",
                         cur_fmt="$875.6K", ca="", symbol="$PI", stats=None,
                         avatar_path=None):
    """Render the Cloud-style champion video for one alert.
    Returns the path of the generated .mp4 (caller deletes it after posting).
    stats: dict with points/calls/win_rate/rank (falls back to the sample)."""
    global TARGET_X, TARGET_LABEL, COUNT_IMGS, FINAL_X_IMG, DATA
    TARGET_X = float(x_val)
    TARGET_LABEL = f"{int(TARGET_X)}x"
    st = stats or {}
    DATA = {
        "channel": (channel or "pumpwatch1").lstrip("@"),
        "symbol": symbol or "$PI",
        "chain": chain or "SOL",
        "entry_fmt": (entry_fmt or "$145.5K") + (" MC" if "MC" not in str(entry_fmt) else ""),
        "cur_fmt": (cur_fmt or "$875.6K") + (" MC" if "MC" not in str(cur_fmt) else ""),
        "points": str(st.get("points", "142")),
        "calls": str(st.get("calls", "117")),
        "win_rate": str(st.get("win_rate", "42%")),
        "rank": f"#{st.get('rank', 1)}",
    }
    COUNT_IMGS = {}
    for _i in range(int(TARGET_X * 10) + 1):
        _v = _i / 10.0
        _s = f"{_v:.1f}x" if _v != int(_v) else f"{int(_v)}x"
        _im, _ox, _oy = grad_text(_s, F_X, X_STOPS, glow=(255, 45, 70), outline=4, blur=16)
        COUNT_IMGS[_i] = (_im, _ox, _oy)
    FINAL_X_IMG, _, _ = grad_text(TARGET_LABEL, F_X, X_STOPS, glow=(255, 45, 70), outline=4, blur=16)
    out_path = os.path.join(os.environ.get("CHAMP_VIDEO_DIR", "/tmp"),
                            f"champ-cloud-{int(TARGET_X)}x.mp4")
    build(out_path)
    return out_path

if __name__ == "__main__":
    build(f"{OUT}/champ-cloud-{TARGET_LABEL}.mp4")
    print("DONE")
