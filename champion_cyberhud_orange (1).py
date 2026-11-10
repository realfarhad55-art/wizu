"""
champion_cyberhud_orange.py - native 1600x640 renderer for the CYBER HUD (orange) design (2.5:1, fomo size):
huge multiplier in the centre, perspective grid floor, HUD brackets/bars, parallelogram stat boxes.

    build_cyber_video(kol_name="Pumpwatch1", x_val=40, entry="slam" | "count", ...)

entry="count": number counts up 0.0x -> value, flash on arrival (normal).
entry="slam" : charge-up (plasma core + converging streaks + screen vibration), BIG impact (white flash,
               shock rings, bolts, shake), number slams in from huge size with RGB-split glitch + ember burst.

Shares helpers with champion_rocket_neon.py and champion_gauge_neon.py (keep the three files together).
"""
import math, os, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import champion_rocket_neon as rk
from champion_rocket_neon import (W, H, FPS, K, px, blur, jag, font, F_BOLD, fmt_mc, put_text, local_masks,
                                  perimeter, ease_io, ease_out, STAT, LOGO, TITLE_X, TITLE_Y, ffmpeg_bin)
from champion_gauge_neon import make_embers, splat_embers

DUR = 6.0
HERE = os.path.dirname(os.path.abspath(__file__))
PAL = dict(n=(255, 102, 16), hot=(255, 228, 190), tx=(255, 170, 80), sub=(255, 150, 60),
           top=(255, 236, 205), bot=(255, 98, 22))
NUM_C = (568, 189)
VP = (562, 261)            # grid vanishing point (design px)
FLOOR_Y = 442


def dpx(v):
    return v * K


# ------------------------------------------------------------------ big number -----------
class BigNum:
    def __init__(self):
        ref = font(F_BOLD, 200)
        self.size = 200 * (378 * K) / ref.getlength("6.0x")
        self.cache = {}

    def layer(self, s, scale):
        key = (s, round(scale, 2))
        if key in self.cache:
            return self.cache[key]
        if len(self.cache) > 60:
            self.cache.clear()
        f = font(F_BOLD, self.size * scale)
        bw, bh = int(dpx(560) * max(1, scale)), int(dpx(281) * max(1, scale))
        c = (bw // 2, bh // 2)
        m = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(m).text(c, s, font=f, fill=255, anchor="mm")
        mk = np.asarray(m, np.float32) / 255.
        ms = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(ms).text(c, s, font=f, fill=255, anchor="mm", stroke_width=max(2, int(5 * scale)), stroke_fill=255)
        mks = np.asarray(ms, np.float32) / 255.
        ys = np.where(mk.sum(1) > 0)[0]
        y0, y1 = (ys.min(), ys.max()) if len(ys) else (0, bh - 1)
        gy = np.clip((np.arange(bh, dtype=np.float32) - y0) / max(1, y1 - y0), 0, 1)[:, None, None]
        top = np.array((255, 238, 210), np.float32); mid = np.array((255, 150, 58), np.float32)
        bot = np.array(PAL["bot"], np.float32)
        t1 = np.clip(gy / 0.55, 0, 1); t2 = np.clip((gy - 0.55) / 0.45, 0, 1)
        face = np.where(gy < 0.55, top * (1 - t1) + mid * t1, mid * (1 - t2) + bot * t2)
        # FIX (Nov 10): face yahan (bh,1,3) banta tha — vertical gradient hai to
        # x par constant hai, lekin slice karne par width 0 ho jata tha jab
        # number bada hota (slam, scale>2) aur x0 negative hota. Ab poori
        # (bh,bw,3) shape me tile karo taake slice hamesha reg se match kare.
        face = np.broadcast_to(face, (bh, bw, 3)).copy()
        glow = blur(mks, 7.0 * scale) * 0.9 + blur(mks, 24.0 * scale) * 0.95
        edge = np.clip(mks - mk, 0, 1)
        out = (glow.astype(np.float32), face.astype(np.float32), mk, edge)
        self.cache[key] = out
        return out

    def draw(self, fr, s, pulse, scale=1.0, alpha=1.0, flash=0.0, glitch=0.0, rng=None, scan=None):
        n = np.array(PAL["n"], np.float32)
        glow, face, mk, edge = self.layer(s, scale)
        bh, bw = mk.shape
        cx, cy = dpx(NUM_C[0]), dpx(NUM_C[1])
        x0, y0 = int(cx - bw / 2), int(cy - bh / 2)
        xa, ya = max(0, x0), max(0, y0)
        xb, yb = min(W, x0 + bw), min(H, y0 + bh)
        if xb <= xa or yb <= ya:
            return
        sl = (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
        reg = fr[ya:yb, xa:xb]
        g_, f_, m_, e_ = glow[sl], face[sl], mk[sl], edge[sl]
        reg += n * (g_ * 0.70 * pulse * alpha)[..., None]
        face_c = f_.copy()
        if flash > 0:
            face_c = face_c * (1 - flash * 0.65) + 255 * flash * 0.65
        if scan is not None:                       # horizontal scan-line sweep over the digits
            ys_ = np.arange(reg.shape[0], dtype=np.float32)[:, None]
            band = np.exp(-(((ys_ - (scan * reg.shape[0])) / (dpx(10))) ** 2))[..., None]
            face_c = face_c * (1 - band * 0.55) + 255 * band * 0.55
        if glitch > 0.02:
            d = int(dpx(10) * glitch)
            for ch, sh in ((0, -d), (1, 0), (2, d)):
                mm = np.roll(m_, sh, axis=1)[..., None] * alpha
                reg[..., ch:ch + 1] = reg[..., ch:ch + 1] * (1 - mm) + face_c[..., ch:ch + 1] * mm
            if rng is not None:
                for _ in range(int(2 + 7 * glitch)):
                    yy = rng.randint(0, max(1, reg.shape[0] - 14)); hh = rng.randint(6, 22)
                    dx = int(rng.uniform(-1, 1) * dpx(40) * glitch)
                    reg[yy:yy + hh] = np.roll(reg[yy:yy + hh], dx, axis=1)
        else:
            a = m_[..., None] * alpha
            reg[:] = reg * (1 - a) + face_c * a
        ea = e_[..., None] * 0.55 * alpha
        reg[:] = reg * (1 - ea) + (np.array(PAL["hot"], np.float32) * 0.7 + n * 0.3) * ea


# ------------------------------------------------------------------ grid + HUD -----------
def grid_layers(t, speed_phase, pulse_gain):
    """returns (core mask, glow mask) float arrays for the floor region only: (y0, core, glow)."""
    y0 = int(dpx(VP[1]) - 4)
    hh = H - y0
    SS = 2
    lay = Image.new("L", (W * SS, hh * SS), 0)
    d = ImageDraw.Draw(lay)
    vx, vy = dpx(VP[0]), dpx(VP[1]) - y0
    wl = int(max(2, 1.2 * K * SS / 1.7 * 1.4))
    # horizontal lines (scroll toward the viewer)
    Nh = 8
    for k in range(Nh):
        f = (k + speed_phase) / Nh
        yy = vy + (dpx(FLOOR_Y) - dpx(VP[1])) * (f ** 1.7)
        d.line((0, yy * SS, W * SS, yy * SS), fill=255, width=wl)
    d.line((0, vy * SS, W * SS, vy * SS), fill=255, width=wl + 1)
    # radial lines
    for j in range(-11, 12):
        xb = dpx(VP[0] + j * 60)
        d.line((vx * SS, vy * SS, xb * SS, (dpx(FLOOR_Y) + 45 - y0) * SS), fill=255, width=wl)
    g = np.asarray(lay.resize((W, hh), Image.BOX), np.float32) / 255.
    ramp = (0.22 + 0.78 * (np.arange(hh, dtype=np.float32) / hh) ** 0.9)[:, None]
    core = g * ramp
    # energy pulses running outwards along the rays
    pl = Image.new("L", (W, hh), 0)
    pd = ImageDraw.Draw(pl)
    for j in range(-11, 12):
        if j == 0:
            continue
        u = (t * 0.7 + (j * 0.137) % 1.0) % 1.0
        if u < 0.55:
            xb = dpx(VP[0] + j * 60)
            ex = (xb - dpx(VP[0]))
            ey = (dpx(FLOOR_Y) + 45 - dpx(VP[1]))
            a0, a1 = u / 0.55, min(1.0, u / 0.55 + 0.16)
            pd.line((vx + ex * a0 ** 1.4, vy + ey * a0 ** 1.4, vx + ex * a1 ** 1.4, vy + ey * a1 ** 1.4), fill=255, width=3)
    pm = np.asarray(pl, np.float32) / 255.
    glow = blur(core, 3.0) * 0.8 + blur(core, 9.0) * 0.5 + blur(pm, 4.0) * 1.0
    return y0, core * pulse_gain, glow * pulse_gain, pm


BAR_Y = [177, 190, 204, 217, 231]
BAR_LEN = [44, 36, 28, 36, 44]


def hud_masks(t, jitter):
    """brackets + bars on both sides as one full-frame-region L mask (x-limited strips)."""
    SS = 2
    out = []
    for side in (0, 1):
        x0d, x1d = (30, 110) if side == 0 else (1014, 1094)
        x0, x1 = int(dpx(x0d)), int(dpx(x1d))
        y0, y1 = int(dpx(99)), int(dpx(245))
        lay = Image.new("L", ((x1 - x0) * SS, (y1 - y0) * SS), 0)
        d = ImageDraw.Draw(lay)
        S = lambda vx, vy: ((dpx(vx) - x0) * SS, (dpx(vy) - y0) * SS)
        wl = int(2.6 * K * SS / 1.7 * 1.2)
        if side == 0:
            d.line([S(85, 111), S(45, 111), S(45, 152)], fill=255, width=wl, joint="curve")
        else:
            d.line([S(1042, 111), S(1083, 111), S(1083, 152)], fill=255, width=wl, joint="curve")
        for i, (by, bl) in enumerate(zip(BAR_Y, BAR_LEN)):
            sc = 0.72 + 0.28 * math.sin(t * (3.0 + jitter * 6) + i * 0.9 + side)
            L = bl * sc
            if side == 0:
                d.rectangle([*S(46, by - 2), *S(46 + L, by + 2)], fill=255)
            else:
                d.rectangle([*S(1082 - L, by - 2), *S(1082, by + 2)], fill=255)
        out.append(((x0, y0, x1, y1), np.asarray(lay.resize((x1 - x0, y1 - y0), Image.BOX), np.float32) / 255.))
    return out


# ------------------------------------------------------------------ video ----------------
def build_cyber_video(*, kol_name="Pumpwatch1", x_val=6, symbol="PI", chain="SOL", entry_mc=0, now_mc=0, rank=1,
                      points=0, calls=0, win_rate="0%", avatar_path=None, logo_path=None, out_path="champion.mp4",
                      entry=None, preview_times=None, crf=14, preset="slow"):
    x_val = float(x_val)
    entry = entry or ("slam" if x_val >= 40 else "count")
    p = PAL
    n = np.array(p["n"], np.float32); hot = np.array(p["hot"], np.float32)
    if not logo_path:
        for nm in ("golden_logo.png", "golden_logo.jpg", "wizard_logo.png"):
            for d_ in (HERE, os.path.join(HERE, "assets")):
                if os.path.exists(os.path.join(d_, nm)):
                    logo_path = os.path.join(d_, nm); break
            if logo_path: break
    rk.SUB_C = (564, 295)
    st = rk.build_static(p, kol_name, symbol, chain, rank, avatar_path, logo_path)
    G, lm, fm, tint = st["G"], st["lm"], st["fm"], st["tint"]
    trgb, ta = st["text"][..., :3], st["text"][..., 3:4] / 255.
    gtrgb, gta = st["gtext"][..., :3], st["gtext"][..., 3:4] / 255.
    masks = local_masks()
    per = {k: perimeter(STAT[k]) for k in STAT}
    stat_glow = {}
    for k, b in STAT.items():
        x0, y0, x1, y1 = [int(round(v * K)) for v in b]
        pad = int(px(22))
        sub = lm[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
        stat_glow[k] = ((max(0, x0 - pad), max(0, y0 - pad)), blur(sub, 6.0) + blur(sub, 14.0) * 0.5)
    big = BigNum()
    Yg, Xg = np.mgrid[0:H, 0:W].astype(np.float32)
    cxn, cyn = dpx(NUM_C[0]), dpx(NUM_C[1])
    Rc = np.sqrt((Xg - cxn) ** 2 + (Yg - cyn) ** 2).astype(np.float32)
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    base = np.zeros((H, W, 3), np.float32)
    base += np.array([16, 7, 2], np.float32) * (1.1 - 0.5 * yy)[..., None]
    base += n * (0.11 * np.exp(-(((Xg - cxn) / dpx(420)) ** 2 + ((Yg - dpx(225)) / dpx(214)) ** 2)))[..., None]
    vig = 1 - 0.42 * (((xx - .5) / .75) ** 2 + ((yy - .55) / .95) ** 2)
    base *= np.clip(vig, 0.4, 1)[..., None]
    embers = make_embers(21, 110, W, H)
    noise = (np.random.RandomState(1).rand(H, W, 1).astype(np.float32) - 0.5) * 1.6
    wr = float(str(win_rate).strip("%") or 0)
    flick = [1, 0.15, 1, 0.5, 1, 1, 0.3, 1, 1, 0.7, 1, 1]
    n_frames = int(DUR * FPS)
    slam = entry == "slam"
    T_IMP = 1.45                      # impact time (slam)
    T_ARR = 2.05                      # arrival time (count)
    burst = []
    rg0 = random.Random(5)
    for _ in range(90):
        a = rg0.uniform(0, 2 * math.pi); v = rg0.uniform(180, 900) * K / 1.7
        burst.append((a, v, rg0.uniform(0.9, 2.0), rg0.choice([0, 1, 2])))

    def block_active(i, salt, prob):
        return random.Random((i // 3) * 31 + salt).random() < prob

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
        if t < 0.08: pw = 0.0
        elif t < 0.5: pw = flick[int((t - 0.08) * 30) % len(flick)]
        else: pw = 1.0
        ts_i = t - T_IMP
        ts_a = t - T_ARR
        pulse = (1.0 + 0.09 * math.sin(2 * math.pi * t / 2.4)) * pw
        charge = 0.0
        if slam:
            charge = min(1.0, max(0.0, (t - 0.55) / 0.9)) if t < T_IMP else 0.0
            if 0 <= ts_i < 1.0:
                pulse *= 1.0 + 0.8 * math.exp(-ts_i / 0.35)
        elif 0 <= ts_a < 1.0:
            pulse *= 1.0 + 0.5 * math.exp(-ts_a / 0.4)
        fr = base.copy() * (0.4 + 0.6 * pw)
        # --- moving background: sweeping beam + embers + faint scanlines
        beam_pos = ((t * 0.28) % 1.6 - 0.3) * (W + H)
        beam = np.exp(-((((Xg * 0.82 + Yg * 0.57) - beam_pos) / dpx(95)) ** 2))
        fr += n * (beam * 0.045)[..., None]
        splat_embers(fr, embers, t, p["n"])
        # --- perspective grid floor
        spd = 0.35 * t
        gain = pw * (1.0 + 0.12 * math.sin(2 * math.pi * t / 1.6))
        if slam:
            spd = 0.35 * t + 1.4 * (charge ** 2) + (0.0 if ts_i < 0 else 0.8 * min(ts_i, 0.6))
            gain *= 1.0 + 1.6 * charge * 0.5 + (2.0 * math.exp(-ts_i / 0.5) if ts_i >= 0 else 0.0)
        elif 0 <= ts_a < 0.8:
            gain *= 1.0 + 1.0 * math.exp(-ts_a / 0.35)
        gy0, gcore, gglow, gpm = grid_layers(t, spd % 1.0, 1.0)
        fr[gy0:] += n * (gglow * 0.55 * gain)[..., None]
        fr[gy0:] = fr[gy0:] * (1 - (gcore * 0.85 * pw)[..., None]) + (n * 0.9 + 25) * (gcore * 0.85 * pw)[..., None]
        fr[gy0:] += (hot * 0.9) * (gpm * 0.6 * pw)[..., None]
        # horizon glow band
        hy = dpx(VP[1])
        fr += n * (np.exp(-(((Yg - hy) / dpx(11)) ** 2)) * 0.12 * gain)[..., None]
        # --- HUD brackets + bars
        jit = (charge * 1.0) + (max(0.0, 1 - ts_i / 0.6) if slam and ts_i >= 0 else 0)
        for (bb, hm) in hud_masks(t, jit):
            x0, y0, x1, y1 = bb
            hg = blur(hm, 5.0) * 1.1 + blur(hm, 12.0) * 0.5
            fr[y0:y1, x0:x1] += n * (hg * 0.9 * pw * pulse)[..., None]
            a = (hm * pw)[..., None]
            fr[y0:y1, x0:x1] = fr[y0:y1, x0:x1] * (1 - a) + (n * 0.95 + 28) * a
        # --- neon structure (frame, boxes, text)
        fr += tint * pw
        fr += G * pulse
        for bi, (k, ((gx0, gy0), gg)) in enumerate(stat_glow.items()):
            gn = 0.45 * max(0.0, math.sin(2 * math.pi * (t / 2.2 - bi * 0.13))) ** 2 * pw
            fr[gy0:gy0 + gg.shape[0], gx0:gx0 + gg.shape[1]] += n * (gg * gn)[..., None]
        fr = fr * (1 - fm[..., None] * 0.9)
        core = (lm * pw)[..., None]
        fr = fr * (1 - core) + (n * 0.98 + 14) * core
        fr = fr * (1 - ta * pw) + trgb * ta * pw
        fr = fr * (1 - gta * pw) + gtrgb * gta * pw
        # --- hero number
        rg = random.Random(i * 17 + 3)
        label = f"{x_val:.1f}x"
        shake = (0.0, 0.0)
        if slam:
            if t < T_IMP:
                # charge: plasma core + converging streaks
                u = charge
                cc = hot * 0.5 + n * 0.5
                fr += n * (np.exp(-(Rc / dpx(10 + 120 * u)) ** 2) * (0.35 + 0.9 * u))[..., None] * pw
                fr += (hot * 0.9 + 30) * (np.exp(-(Rc / dpx(4 + 30 * u)) ** 2) * u)[..., None] * pw
                lay = Image.new("L", (W, H), 0); sd = ImageDraw.Draw(lay)
                for kk in range(46):
                    r3 = random.Random(kk * 7 + 1)
                    an = r3.uniform(0, 2 * math.pi); R0 = dpx(r3.uniform(230, 520))
                    ph = ((t - 0.5) * (0.9 + 0.6 * r3.random()) + r3.random()) % 1.0
                    rr0 = R0 * (1 - ph ** 1.6)
                    rr1 = rr0 + dpx(14 + 36 * u)
                    if t > 0.5 and rr0 > dpx(14):
                        sd.line((cxn + rr0 * math.cos(an), cyn + rr0 * math.sin(an),
                                 cxn + rr1 * math.cos(an), cyn + rr1 * math.sin(an)), fill=int(120 + 135 * u), width=2)
                sk = np.asarray(lay, np.float32) / 255.
                fr += (n * 0.8 + 110) * (blur(sk, 1.6) * 0.9 * (0.3 + u))[..., None]
                amp = 0.6 + 4.5 * u
                shake = (rg.uniform(-amp, amp), rg.uniform(-amp, amp))
            else:
                sc = 1.0 + 1.5 * math.exp(-ts_i / 0.06) if ts_i < 0.5 else 1.0
                sc += 0.035 * math.sin(ts_i * 22) * math.exp(-ts_i / 0.3)
                gl = math.exp(-ts_i / 0.28) if ts_i < 1.0 else 0.0
                if ts_i > 1.0 and ((i // 4) % 11 == 0):
                    gl = 0.35                                    # occasional glitch flick while idle
                al = min(1.0, ts_i / 0.03 + 0.2)
                scan = ((t - T_IMP - 0.9) * 0.4) % 1.5
                big.draw(fr, label, pulse, scale=sc, alpha=al, flash=math.exp(-ts_i / 0.1), glitch=gl, rng=rg,
                         scan=scan if scan < 1.0 and ts_i > 0.9 else None)
                amp = 17 * math.exp(-ts_i / 0.22)
                shake = (rg.uniform(-amp, amp), rg.uniform(-amp, amp))
        else:
            prog = ease_out((t - 0.35) / 1.7) if t >= 0.35 else 0.0
            num = x_val * prog
            lab = f"{x_val:.1f}x" if prog >= 1 else f"{num:.1f}x"
            fl = rg.uniform(0.82, 1.0) if prog < 1 else 1.0
            sc = 1.0 + (0.07 * math.exp(-ts_a / 0.18) * math.cos(ts_a * 14) if ts_a >= 0 else 0.0)
            scan = ((t - T_ARR - 0.4) * 0.45) % 1.6
            big.draw(fr, lab, pulse, scale=sc, alpha=fl if t > 0.3 else 0.0,
                     flash=math.exp(-ts_a / 0.12) if ts_a >= 0 else 0.0,
                     scan=scan if (scan < 1.0 and ts_a > 0.3) else None)
            if 0 <= ts_a < 0.4:
                amp = 4 * math.exp(-ts_a / 0.15)
                shake = (rg.uniform(-amp, amp), rg.uniform(-amp, amp))
        # --- stat boxes: count-up values
        t_s = (T_IMP + 0.15) if slam else 0.7
        cu = ease_out((t - t_s) / 1.5) if t >= t_s else 0.0
        vals = dict(entry=fmt_mc(entry_mc * cu), now=fmt_mc(now_mc * cu), points=str(int(round(points * cu))),
                    calls=str(int(round(calls * cu))), win=f"{int(round(wr * cu))}%")
        for k, sv in vals.items():
            b = STAT[k]
            put_text(fr, sv, F_BOLD, 18 * K, (b[0] + b[2]) / 2 * K, (b[1] + 42) * K, (255, 255, 255, 255))
        # --- impact / arrival effects
        def radial(ts, big_=True):
            fr_ = (n * 0.8 + 120) * (np.exp(-Rc / dpx(430 if big_ else 280)) * math.exp(-ts / (0.26 if big_ else 0.2)) * 0.85)[..., None]
            return fr_
        if slam and 0 <= ts_i < 1.3:
            fr += radial(ts_i)
            fr += (hot * 0.9 + 40) * (0.78 * math.exp(-ts_i / 0.07))
            for (spd_, wd_, amp_, dl) in ((2300, 20, 0.95, 0.0), (1700, 13, 0.7, 0.09), (1200, 9, 0.5, 0.2)):
                tt = ts_i - dl
                if 0 <= tt < 0.85:
                    fr += (n * 0.8 + 90) * (np.exp(-(((Rc - tt * spd_) / dpx(wd_)) ** 2)) * (1 - tt / 0.85) * amp_)[..., None]
            if ts_i < 0.35:
                r2 = random.Random(i * 13 + 5)
                lay2 = Image.new("L", (W, H), 0); ld2 = ImageDraw.Draw(lay2)
                for _ in range(12):
                    an = r2.uniform(0, 2 * math.pi); ln = dpx(r2.uniform(120, 330))
                    ld2.line(jag(cxn, cyn, cxn + ln * math.cos(an), cyn + ln * math.sin(an), r2, 10, 16), fill=255, width=3)
                lmk = np.asarray(lay2, np.float32) / 255.; lgk = blur(lmk, 5)
                amp = 1 - ts_i / 0.35
                fr += (n * 0.8 + 90) * (lgk * 1.6 * amp)[..., None] + 255 * (lmk * 0.9 * amp)[..., None]
            # ember burst
            for (an, v, life, col) in burst:
                age = ts_i
                if age > life:
                    continue
                dist = v * (1 - math.exp(-age * 3.2)) / 3.2
                ex_, ey_ = cxn + dist * math.cos(an), cyn + dist * math.sin(an) + 293 * age * age * K / 1.7
                al = max(0, 1 - age / life)
                r_ = dpx(2.4) * (0.5 + al)
                xi, yi = int(ex_), int(ey_)
                Rr = int(r_ * 3) + 2
                if Rr < xi < W - Rr and Rr < yi < H - Rr:
                    gy2, gx2 = np.mgrid[-Rr:Rr + 1, -Rr:Rr + 1].astype(np.float32)
                    g = np.exp(-(((gx2 - (ex_ - xi)) ** 2 + (gy2 - (ey_ - yi)) ** 2) / (r_ * r_))) * al
                    cl = ((255, 235, 200), (255, 150, 60), (255, 100, 25))[col]
                    fr[yi - Rr:yi + Rr + 1, xi - Rr:xi + Rr + 1] += g[..., None] * np.array(cl, np.float32) * 0.9
        if (not slam) and 0 <= ts_a < 0.9:
            fr += radial(ts_a, False)
            fr += (n * 0.3 + 90) * (0.4 * math.exp(-ts_a / 0.09))
            if ts_a < 0.7:
                fr += (n * 0.75 + 70) * (np.exp(-(((Rc - ts_a * 1700) / dpx(14)) ** 2)) * (1 - ts_a / 0.7) * 0.8)[..., None]
            if ts_a < 0.3:
                r2 = random.Random(i * 13 + 5)
                lay2 = Image.new("L", (W, H), 0); ld2 = ImageDraw.Draw(lay2)
                for _ in range(7):
                    an = r2.uniform(0, 2 * math.pi); ln = dpx(r2.uniform(100, 230))
                    ld2.line(jag(cxn, cyn, cxn + ln * math.cos(an), cyn + ln * math.sin(an), r2, 9, 14), fill=255, width=3)
                lmk = np.asarray(lay2, np.float32) / 255.; lgk = blur(lmk, 5)
                amp = 1 - ts_a / 0.3
                fr += (n * 0.8 + 90) * (lgk * 1.5 * amp)[..., None] + 255 * (lmk * 0.9 * amp)[..., None]
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
                seq = per[k]; Lp = len(seq)
                s0 = int(((t * 0.45 + bi * 0.21) % 1.0) * Lp); ln = int(Lp * 0.13)
                seg = [seq[(s0 + j) % Lp] for j in range(ln)]
                lay3 = Image.new("L", (x1 - x0 + 60, y1 - y0 + 60), 0)
                ImageDraw.Draw(lay3).line([((x - STAT[k][0]) * K + 30, (y - STAT[k][1]) * K + 30) for x, y in seg], fill=255, width=3)
                lmk = np.asarray(lay3, np.float32) / 255.
                lgk = np.asarray(lay3.filter(ImageFilter.GaussianBlur(5)), np.float32) / 255.
                ya, xa = y0 - 30, x0 - 30
                ysa, xsa = max(0, ya), max(0, xa)
                ysb, xsb = min(H, ya + lay3.height), min(W, xa + lay3.width)
                sl = (slice(ysa - ya, ysb - ya), slice(xsa - xa, xsb - xa))
                fr[ysa:ysb, xsa:xsb] += (n * 0.8 + 100) * (lgk[sl] * 1.3)[..., None] + 255 * (lmk[sl] * 0.85)[..., None]
        # --- lightning: rank box + kol box ONLY (logo/title lightning REMOVED per owner request)
        forced = (slam and (0 <= ts_i < 0.6 or (charge > 0.5 and block_active(i, 9, 0.8)))) or ((not slam) and 0 <= ts_a < 0.6)
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
        if forced or block_active(i, 3, 0.55):
            r4 = random.Random(i * 3 + 9)

            def dk(d, w, h):
                x = r4.uniform(110, w - 25)
                d.line(jag(x, 1, x + r4.uniform(-30, 30), h - 1, r4, 8, 8), fill=255, width=2)
                if r4.random() < 0.6:
                    x2 = r4.uniform(110, w - 25)
                    d.line(jag(x2, 1, x2 + r4.uniform(-35, 35), h - 1, r4, 8, 8), fill=255, width=2)
            local_fx(fr, "kol", dk, 1.4)
        # --- subtle scanlines
        fr *= (1 - 0.018 * (0.5 + 0.5 * np.sin(2 * np.pi * (Yg[:, :1] / 4.0 - t * 0.6))))[..., None]
        if t < 0.08:
            fr *= 0.0
        fr += noise
        out = np.clip(fr, 0, 255).astype(np.uint8)
        dx, dy = int(round(shake[0])), int(round(shake[1]))
        if dx or dy:
            o2 = np.zeros_like(out)
            o2[:] = out[0:1, 0:1]
            ys0, ys1 = max(0, dy), H + min(0, dy)
            xs0, xs1 = max(0, dx), W + min(0, dx)
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


if __name__ == "__main__":
    import sys
    xv = float(sys.argv[1]) if len(sys.argv) > 1 else 40
    build_cyber_video(kol_name="Pumpwatch1", x_val=xv, symbol="PI", chain="SOL", entry_mc=145500, now_mc=875600,
                      rank=1, points=142, calls=117, win_rate="42%",
                      out_path=sys.argv[2] if len(sys.argv) > 2 else "champion_cyber.mp4")
