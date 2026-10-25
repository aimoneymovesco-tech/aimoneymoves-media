"""Urban-fintech animated reel renderer (1080x1920, 30fps).
usage: python3 -I make_demo.py out.mp4 spec.json
Scenes:
  hook   {"text":"...", "kicker":"TOOL OF THE DAY"}            big words punch in; *words* become green stickers
  chat   {"tool":"ChatGPT","prompt":"...","reply":[...],"caption":"..."}  phone chat demo
  item   {"n":1,"of":5,"title":"...","lines":[...]}            numbered list beat
  money  {"from":0,"to":50,"prefix":"$","label":"per listing","sub":"..."} rolling counter
  cta    {"text":"..."}
"""
import sys, json, glob, math, subprocess, re, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
BLACK = (6, 6, 8)
INK = (248, 248, 246)
QUIET = (150, 155, 165)
GREEN = (0, 255, 133)
GRAY = (28, 29, 34)
BUBBLE_AI = (38, 40, 47)
BUBBLE_USER = (0, 170, 90)
HANDLE = "@AIMONEYMOVES.OFFICIAL"
SP = "/tmp/claude-0/-home-claude/9eb22da4-f985-5297-a876-b5a889afe175/scratchpad/fonts/"

def bebas(size): return ImageFont.truetype(SP + "BebasNeue.ttf", size)
def mono(size): return ImageFont.truetype(SP + "SpaceMono.ttf", size)
def inter(size, weight="Medium"):
    return ImageFont.truetype(glob.glob(f"/usr/share/fonts/opentype/inter/Inter-{weight}.otf")[0], size)

F_HOOK = bebas(168)
F_HOOK_S = bebas(130)
F_ITEM = bebas(120)
F_BODY = inter(48, "SemiBold")
F_CHAT = inter(42, "Medium")
F_SMALL = mono(30)
F_NUM = bebas(420)
F_TICK = bebas(40)
F_KICK = mono(34)

def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3
def back(t):
    t = max(0.0, min(1.0, t)); s = 1.70158
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2

def tokens(text):
    out, hl = [], False
    for part in re.split(r"(\*)", text):
        if part == "*": hl = not hl; continue
        for w in part.split(): out.append((w, hl))
    return out

def layout(d, toks, f, x0, maxw, pad=0):
    rows, x, li = [], x0, 0
    space = d.textlength(" ", font=f)
    for w, hl in toks:
        ww = d.textlength(w, font=f) + (pad * 2 if hl else 0)
        if x + ww > x0 + maxw and x > x0:
            li += 1; x = x0
        rows.append((w, hl, int(x), li, int(ww)))
        x += ww + space
    return rows

# ---------- background ----------
def make_bg():
    im = Image.fromarray(np.full((H, W, 3), BLACK, dtype=np.uint8))
    d = ImageDraw.Draw(im)
    for x in range(0, W, 90): d.line([x, 0, x, H], fill=(14, 15, 18), width=1)
    for y in range(0, H, 90): d.line([0, y, W, y], fill=(14, 15, 18), width=1)
    random.seed(7)
    pts, y = [], 1500
    for i in range(0, W + 60, 60):
        y -= random.randint(-40, 110); pts.append((i, y))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).line(pts, fill=(0, 90, 50), width=6)
    glow = glow.filter(ImageFilter.GaussianBlur(14))
    im = Image.fromarray(np.clip(np.asarray(im).astype(int) + np.asarray(glow).astype(int), 0, 255).astype("uint8"))
    ImageDraw.Draw(im).line(pts, fill=(0, 60, 36), width=3)
    yy, xx = np.mgrid[0:H, 0:W]
    v = 1 - 0.55 * (((xx - W / 2) / (W / 2)) ** 2 * 0.6 + ((yy - H / 2) / (H / 2)) ** 2) ** 1.2
    v = np.clip(v, 0, 1)[..., None]
    return Image.fromarray((np.asarray(im) * v).astype("uint8"))

def make_photo_bg(path, dark=0.78):
    im = Image.open(path).convert("RGB")
    w, h = im.size; sc = max(W / w, H / h)
    im = im.resize((int(w * sc) + 1, int(h * sc) + 1), Image.LANCZOS)
    w, h = im.size; im = im.crop(((w - W) // 2, (h - H) // 2, (w - W) // 2 + W, (h - H) // 2 + H))
    im = im.filter(ImageFilter.GaussianBlur(1.2))
    yy, xx = np.mgrid[0:H, 0:W]
    v = 1 - 0.45 * (((xx - W / 2) / (W / 2)) ** 2 * 0.6 + ((yy - H / 2) / (H / 2)) ** 2) ** 1.2
    band = 1 - 0.3 * np.exp(-((yy - H * 0.47) / (H * 0.22)) ** 2)
    v = np.clip(v, 0, 1) * band * dark
    return Image.fromarray((np.asarray(im) * v[..., None]).astype("uint8"))

def make_grain(n=4):
    rng = np.random.default_rng(3)
    return [Image.fromarray(rng.integers(0, 18, (H, W, 1), dtype=np.uint8).repeat(3, axis=2)) for _ in range(n)]

def make_ticker():
    txt = "   //   ".join(["AI MONEY MOVES", "TOOL OF THE DAY", "TESTED NOT HYPED", "AI SIDE HUSTLES", "AUTOMATE YOUR MONEY"] * 3) + "   //   "
    tmp = Image.new("RGB", (10, 10)); tl = int(ImageDraw.Draw(tmp).textlength(txt, font=F_TICK))
    strip = Image.new("RGB", (tl, 70), GREEN)
    ImageDraw.Draw(strip).text((0, 14), txt, font=F_TICK, fill=BLACK)
    return strip

# ---------- helpers ----------
def alpha_paste(frame, layer, xy, a):
    if a <= 0: return
    if a < 1:
        r, g, b, al = layer.split()
        layer = Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * a))))
    frame.paste(layer, xy, layer)

def word_layer(w, f, hl, pad, radius=10, rot=0):
    tmp = Image.new("RGBA", (10, 10)); d = ImageDraw.Draw(tmp)
    bb = d.textbbox((0, 0), w, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if hl:
        lay = Image.new("RGBA", (tw + pad * 2 + 8, th + pad * 2 + 8), (0, 0, 0, 0))
        dd = ImageDraw.Draw(lay)
        dd.rounded_rectangle([0, 0, tw + pad * 2, th + pad * 2], radius=radius, fill=GREEN + (255,))
        dd.text((pad - bb[0], pad - bb[1]), w, font=f, fill=BLACK + (255,))
        if rot: lay = lay.rotate(rot, resample=Image.BICUBIC, expand=True)
    else:
        lay = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((-bb[0] + 4, -bb[1] + 4), w, font=f, fill=INK + (255,))
    return lay, bb

def punch_words(frame, rows, f, y0, line_h, t, start, per_word=0.14, dur=0.32, pad=14):
    for i, (w, hl, x, li, ww) in enumerate(rows):
        k = (t - start - i * per_word) / dur
        if k <= 0: continue
        s = back(k)
        lay, bb = word_layer(w, f, hl, pad, rot=(-2 if hl and i % 2 else (2 if hl else 0)))
        ox, oy = x - 4, y0 + li * line_h + bb[1] - 4 - (pad if hl else 0)
        if s < 0.999:
            nw, nh = max(1, int(lay.width * s)), max(1, int(lay.height * s))
            cx, cy = ox + lay.width // 2, oy + lay.height // 2
            alpha_paste(frame, lay.resize((nw, nh), Image.BICUBIC), (cx - nw // 2, cy - nh // 2), min(1.0, k * 3))
        else:
            frame.paste(lay, (ox, oy), lay)

def fade_words(frame, rows, f, y0, line_h, t, start, per_word=0.04, dur=0.3, color=INK):
    d = ImageDraw.Draw(frame)
    for i, (w, hl, x, li, ww) in enumerate(rows):
        a = ease((t - start - i * per_word) / dur)
        if a <= 0: continue
        y = y0 + li * line_h + int((1 - a) * 18)
        col = GREEN if hl else color
        if a >= 0.999: d.text((x, y), w, font=f, fill=col); continue
        bb = d.textbbox((x, y), w, font=f)
        lay = Image.new("RGBA", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((x - bb[0] + 4, y - bb[1] + 4), w, font=f, fill=col + (int(255 * a),))
        frame.paste(lay, (bb[0] - 4, bb[1] - 4), lay)

def wrap_plain(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split(" "):
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= maxw: cur = trial
        else: lines.append(cur); cur = w
    lines.append(cur)
    return lines

# ---------- scenes ----------
def scene_hook(spec, t, frame):
    d = ImageDraw.Draw(frame)
    f = F_HOOK if len(spec["text"]) < 48 else F_HOOK_S
    lh = int(f.size * 0.98)
    rows = layout(d, tokens(spec["text"]), f, 80, W - 160, pad=14)
    nl = rows[-1][3] + 1
    y0 = (H - nl * lh) // 2 - 60
    kick = spec.get("kicker")
    if kick:
        k = ease(t / 0.3)
        d.rectangle([80, y0 - 110, 80 + int(d.textlength(kick.upper(), font=F_KICK)) + 40, y0 - 50], outline=GREEN, width=3)
        if k > 0.5: d.text((100, y0 - 100), kick.upper(), font=F_KICK, fill=GREEN)
    punch_words(frame, rows, f, y0, lh, t, 0.25)
    k = ease((t - 0.25 - len(rows) * 0.14 - 0.3) / 0.4)
    if k > 0:
        d.text((80, y0 + nl * lh + 50), ">> WATCH", font=F_KICK, fill=tuple(int(c * k) for c in GREEN))

def _wc(*xs): return sum(len(str(x).split()) for x in xs)
WPS = 4.0  # max words per second before pace; pace 1.2 -> ~3.3 w/s, pace 1.35 -> ~3 w/s (Ryan 2026-10-18)
def hook_dur(spec): return max(0.25 + len(tokens(spec["text"])) * 0.14 + 2.0, _wc(spec["text"]) / WPS + 1.2)

def scene_chat(spec, t, frame):
    d = ImageDraw.Draw(frame)
    px0, py0, px1, py1 = 70, 250, W - 70, H - 560
    k = ease(t / 0.35)
    if k <= 0: return
    off = int((1 - k) * 90)
    d.rounded_rectangle([px0, py0 + off, px1, py1 + off], radius=56, fill=(16, 17, 21), outline=(50, 52, 60), width=3)
    d.rounded_rectangle([W // 2 - 90, py0 + off + 22, W // 2 + 90, py0 + off + 52], radius=15, fill=BLACK)
    d.ellipse([px0 + 44, py0 + off + 84, px0 + 92, py0 + off + 132], fill=GREEN)
    d.text((px0 + 54, py0 + off + 92), "AI", font=inter(28, "Bold"), fill=BLACK)
    d.text((px0 + 110, py0 + off + 84), spec.get("tool", "ChatGPT"), font=inter(36, "Bold"), fill=INK)
    d.text((px0 + 110, py0 + off + 128), "online", font=inter(24, "Medium"), fill=GREEN)
    d.line([px0 + 30, py0 + off + 172, px1 - 30, py0 + off + 172], fill=(40, 42, 50), width=2)
    if k < 1: return
    cps = 34
    prompt = spec["prompt"]; t0 = 0.45
    n = int(max(0, t - t0) * cps)
    shown = prompt[:n]
    done = n >= len(prompt)
    bw = 780
    lines = wrap_plain(d, shown if shown else " ", F_CHAT, bw - 64)
    bh = len(lines) * 52 + 48
    bx1, by0 = px1 - 36, py0 + 200
    d.rounded_rectangle([bx1 - bw, by0, bx1, by0 + bh], radius=30, fill=BUBBLE_USER)
    yy = by0 + 24
    for ln in lines:
        d.text((bx1 - bw + 32, yy), ln, font=F_CHAT, fill=INK); yy += 52
    if not done and int(t * 3) % 2 == 0:
        lw = d.textlength(lines[-1], font=F_CHAT)
        d.rectangle([bx1 - bw + 36 + lw, yy - 46, bx1 - bw + 40 + lw, yy - 8], fill=INK)
    t_done = t0 + len(prompt) / cps
    ay0 = by0 + bh + 36
    if t < t_done + 0.25: return
    t_reply = t_done + 1.2
    if t < t_reply:
        d.rounded_rectangle([px0 + 36, ay0, px0 + 200, ay0 + 72], radius=30, fill=BUBBLE_AI)
        for j in range(3):
            p = 0.5 + 0.5 * math.sin(t * 7 - j * 1.3)
            r = 7 + int(5 * p); cx = px0 + 80 + j * 40
            d.ellipse([cx - r, ay0 + 36 - r, cx + r, ay0 + 36 + r], fill=QUIET)
        return
    per = 0.8
    vis = [i for i in range(len(spec["reply"])) if t >= t_reply + i * per]
    rendered = []
    for i in vis:
        rows = layout(d, tokens(spec["reply"][i]), F_CHAT, px0 + 68, bw - 40)
        rendered.append((i, rows, rows[-1][3] + 1))
    total = sum(nl for _, _, nl in rendered)
    bh2 = total * 52 + 48 + (len(rendered) - 1) * 16
    d.rounded_rectangle([px0 + 36, ay0, px0 + 36 + bw + 20, ay0 + bh2], radius=30, fill=BUBBLE_AI)
    yy = ay0 + 24
    for i, rows, nl in rendered:
        fade_words(frame, rows, F_CHAT, yy, 52, t, t_reply + i * per, per_word=0.025)
        yy += nl * 52 + 16
    cap = spec.get("caption")
    tc = t_reply + len(spec["reply"]) * per + 0.3
    if cap and t > tc:
        fc = bebas(72)
        rows = layout(d, tokens(cap), fc, 80, W - 160, pad=12)
        punch_words(frame, rows, fc, py1 + 50, 76, t, tc, per_word=0.08, pad=12)

def chat_dur(spec): return 0.45 + len(spec["prompt"]) / 34 + 1.2 + len(spec["reply"]) * 0.8 + 2.6

def scene_item(spec, t, frame):
    d = ImageDraw.Draw(frame)
    num = f"{spec['n']:02d}"
    nx = 60 - int((1 - ease(t / 0.4)) * 200)
    d.text((nx, 360), num, font=F_NUM, fill=(14, 40, 26) if GREEN == (0, 255, 133) else (52, 44, 26))
    d.text((80, 420), f"{spec['n']} / {spec['of']}", font=F_KICK, fill=GREEN)
    rows = layout(d, tokens(spec["title"]), F_ITEM, 80, W - 160, pad=12)
    lh = 116; y0 = 700
    punch_words(frame, rows, F_ITEM, y0, lh, t, 0.15, per_word=0.1, pad=12)
    y = y0 + (rows[-1][3] + 1) * lh + 40
    start = 0.15 + len(rows) * 0.1 + 0.15
    for j, ln in enumerate(spec.get("lines", [])):
        r2 = layout(d, tokens(ln), F_BODY, 116, W - 196)
        nl = r2[-1][3] + 1
        a = ease((t - start - j * 0.55) / 0.3)
        if a > 0:
            d.rounded_rectangle([80, y + 6, 88, y + nl * 62 - 8], radius=4, fill=GREEN)
        fade_words(frame, r2, F_BODY, y, 62, t, start + j * 0.55, per_word=0.035)
        y += nl * 62 + 26

def item_dur(spec): return max(0.15 + len(tokens(spec["title"])) * 0.1 + len(spec.get("lines", [])) * 0.55 + 2.4, _wc(spec["title"], *spec.get("lines", [])) / WPS + 1.0)

def scene_money(spec, t, frame):
    d = ImageDraw.Draw(frame)
    a, b = spec.get("from", 0), spec["to"]
    k = ease(t / 1.6)
    val = a + (b - a) * k
    s = f"{spec.get('prefix','$')}{int(val):,}"
    fs = 360; f = bebas(fs); tw = d.textlength(s, font=f)
    while tw > W - 90 and fs > 120:  # shrink long figures ($13,000,000) to fit the frame
        fs -= 10; f = bebas(fs); tw = d.textlength(s, font=f)
    lay = Image.new("RGBA", (W, 460), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text(((W - tw) / 2, 0), s, font=f, fill=GREEN + (255,))
    glow = lay.filter(ImageFilter.GaussianBlur(28))
    frame.paste(glow, (0, 640), glow)
    frame.paste(lay, (0, 640), lay)
    lab = spec.get("label", "")
    if lab:
        fl = bebas(80)
        rows = layout(d, tokens(lab), fl, 80, W - 160, pad=12)
        tw2 = sum(r[4] for r in rows) + int(d.textlength(" ", font=fl)) * (len(rows) - 1)
        rows = [(w, hl, x + (W - 160 - tw2) // 2, li, ww) for (w, hl, x, li, ww) in rows]
        punch_words(frame, rows, fl, 1080, 84, t, 1.2, per_word=0.08, pad=12)
    sub = spec.get("sub")
    if sub:
        a2 = ease((t - 1.9) / 0.4)
        if a2 > 0:
            d.text((W // 2 - d.textlength(sub, font=F_KICK) // 2, 1220), sub, font=F_KICK,
                   fill=tuple(int(c * a2) for c in QUIET))

def money_dur(spec): return max(3.6, 2.2 + _wc(spec.get("label",""), spec.get("sub","")) / WPS)

def scene_cta(spec, t, frame):
    d = ImageDraw.Draw(frame)
    f = F_HOOK_S; lh = int(f.size * 0.98)
    rows = layout(d, tokens(spec["text"]), f, 80, W - 160, pad=14)
    nl = rows[-1][3] + 1
    y0 = (H - nl * lh) // 2 - 140
    punch_words(frame, rows, f, y0, lh, t, 0.15)
    k = ease((t - 0.15 - len(rows) * 0.14) / 0.45)
    if k > 0:
        by = y0 + nl * lh + 60
        d.rounded_rectangle([80, by, 80 + int(560 * k), by + 110], radius=20, fill=INK)
        if k > 0.95:
            d.text((120, by + 14), "FOLLOW + SAVE", font=bebas(76), fill=BLACK)
            d.text((80, by + 140), HANDLE, font=F_KICK, fill=GREEN)

def cta_dur(spec): return max(0.15 + len(tokens(spec["text"])) * 0.14 + 2.6, _wc(spec["text"]) / WPS + 1.4)

RENDER = {"hook": (scene_hook, hook_dur), "chat": (scene_chat, chat_dur), "item": (scene_item, item_dur),
          "money": (scene_money, money_dur), "cta": (scene_cta, cta_dur)}

def chrome(frame, progress, ticker, fi):
    d = ImageDraw.Draw(frame)
    shift = (fi * 4) % ticker.width
    strip = Image.new("RGB", (W, 70), GREEN)
    strip.paste(ticker.crop((shift, 0, min(ticker.width, shift + W), 70)), (0, 0))
    if shift + W > ticker.width:
        strip.paste(ticker.crop((0, 0, shift + W - ticker.width, 70)), (ticker.width - shift, 0))
    frame.paste(strip, (0, H - 190))
    d.rectangle([0, 0, W, 10], fill=GRAY)
    d.rectangle([0, 0, int(W * progress), 10], fill=GREEN)
    d.text((80, 60), HANDLE, font=F_SMALL, fill=QUIET)
    d.text((W - 80 - d.textlength("AI MONEY MOVES", font=F_SMALL), 60), "AI MONEY MOVES", font=F_SMALL, fill=GREEN)

def video_mask(dark):
    yy, xx = np.mgrid[0:H, 0:W]
    v = 1 - 0.45 * (((xx - W / 2) / (W / 2)) ** 2 * 0.6 + ((yy - H / 2) / (H / 2)) ** 2) ** 1.2
    band = 1 - 0.3 * np.exp(-((yy - H * 0.47) / (H * 0.22)) ** 2)
    return (np.clip(v, 0, 1) * band * dark)[..., None].astype(np.float32)

def render(scenes, out, frame_cb=None, bg_image=None, bg_dark=0.78, bg_video=None, pace=1.0):
    bg, grains, ticker = (make_photo_bg(bg_image, bg_dark) if bg_image else make_bg()), make_grain(), make_ticker()
    vdecs, vmask, ibgs = {}, video_mask(bg_dark), {}
    def cam(img, u, move):
        # u in 0..1 across the scene; slow push/pull with a drift
        z0, z1 = {"in": (1.0, 1.10), "out": (1.10, 1.0), "left": (1.06, 1.06), "right": (1.06, 1.06)}.get(move, (1.0, 1.10))
        z = z0 + (z1 - z0) * u; cw, ch = int(W / z), int(H / z)
        px = {"left": -1 + 2 * u, "right": 1 - 2 * u}.get(move, 0.0) * 0.9
        x0 = int((W - cw) / 2 * (1 + px)); y0 = (H - ch) // 2
        return img.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)
    def decoder(path):
        if path not in vdecs:
            vdecs[path] = subprocess.Popen(["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", path, "-vf", f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=1.2",
                                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        return vdecs[path]
    # pace > 1 holds every scene longer so it reads slower; animations keep their timing
    durs = [float(s["dur"]) if s.get("dur") else RENDER[s["type"]][1](s) * pace for s in scenes]  # per-scene "dur" override (narration timing)
    total = sum(durs); nframes = int(total * FPS)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    acc, si = 0.0, 0
    for fi in range(nframes):
        T = fi / FPS
        while si < len(scenes) - 1 and T >= acc + durs[si]:
            acc += durs[si]; si += 1
        t = T - acc
        vpath = scenes[si].get("bg_video", bg_video)
        ipath = scenes[si].get("bg")
        if ipath:
            if ipath not in ibgs: ibgs[ipath] = make_photo_bg(ipath, scenes[si].get("bg_dark", bg_dark))
            frame = cam(ibgs[ipath], t / durs[si], scenes[si].get("move", "in"))
            if t < 0.4 and si > 0:
                prev = scenes[si - 1]; pp = prev.get("bg")
                if pp:
                    if pp not in ibgs: ibgs[pp] = make_photo_bg(pp, prev.get("bg_dark", bg_dark))
                    frame = Image.blend(cam(ibgs[pp], 1.0, prev.get("move", "in")), frame, t / 0.4)
        elif vpath:
            raw = decoder(vpath).stdout.read(W * H * 3)
            arr = np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3).astype(np.float32) * vmask
            frame = Image.fromarray(arr.astype(np.uint8))
        else:
            z = 1.0 + 0.03 * (t / durs[si])
            cw, ch = int(W / z), int(H / z)
            frame = bg.crop(((W - cw) // 2, (H - ch) // 2, (W - cw) // 2 + cw, (H - ch) // 2 + ch)).resize((W, H), Image.BILINEAR)
        RENDER[scenes[si]["type"]][0](scenes[si], t, frame)
        if t < 0.1 and si > 0 and not scenes[si].get("bg"):
            frame = Image.blend(frame, Image.new("RGB", (W, H), GREEN), 0.22 * (1 - t / 0.1))
        frame = Image.fromarray(np.clip(np.asarray(frame).astype(np.int16) + np.asarray(grains[fi % 4]).astype(np.int16) - 9, 0, 255).astype(np.uint8))
        chrome(frame, T / total, ticker, fi)
        p.stdin.write(frame.tobytes())
    p.stdin.close(); p.wait()
    for _d in vdecs.values(): _d.kill()
    print(out, round(total, 1), "s")

def set_palette(name):
    """'vintage' = cream/gold on teal film scenes (brand direction from 2026-10-17)."""
    g = globals()
    if name == "vintage":
        g["GREEN"] = (214, 178, 102)      # aged gold
        g["INK"] = (236, 226, 196)        # cream
        g["QUIET"] = (170, 160, 130)
        g["GRAY"] = (40, 44, 40)
if __name__ == "__main__":
    _spec = json.load(open(sys.argv[2]))
    set_palette(_spec.get("palette"))
    render(_spec["scenes"], sys.argv[1], bg_image=_spec.get("bg"), bg_dark=_spec.get("bg_dark", 0.78), bg_video=_spec.get("bg_video"), pace=_spec.get("pace", 1.0))
