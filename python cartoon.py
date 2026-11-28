#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_video.py  -  one-file pipeline: Elevenlabs.mp3  ->  1080x1920 @ 60fps 2D horror animation (Remotion)

What it does (all automatic, resumable):
  1. checks tools (node, npm, ffmpeg)         5. renders preview stills (fail-fast check)
  2. analyses the voice (per-frame loudness,  6. renders the video in 10-second chunks, each saved to disk
     pauses) and locks scene cuts to pauses      -> re-run the script and it continues where it stopped
  3. synthesises the sound-design bed         7. joins chunks + mixes audio (voice always louder, SFX ducked
  4. writes the Remotion project, npm install    under the voice) -> final_video.mp4

Run:   python make_video.py            (put Elevenlabs.mp3 in the output folder first)
Flags: --prep-only   only steps 1-4 (analysis, sfx, project)     --fresh  throw away saved chunks
       --no-preview  skip stills                                   --crf N  quality (default 17, lower = better)
"""
import os, sys, json, math, subprocess, shutil, time, re, hashlib, wave, zlib, struct, argparse
from pathlib import Path

OUT_DIR = Path(os.environ.get("CND_DIR", r"C:\Users\laptop villa\Documents\cnd"))
AUDIO   = OUT_DIR / "Elevenlabs.mp3"
WORK    = OUT_DIR / "work"
PROJ    = WORK / "remotion"
CHUNKS  = WORK / "chunks"
STILLS  = OUT_DIR / "previews"
FINAL   = OUT_DIR / "final_video.mp4"
FPS, CHUNK_FRAMES = 60, 600
SR = 44100

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ----------------------------------------------------------------------------- small UI helpers
T0 = time.time()
def hms(s):
    s = int(max(0, s)); return f"{s//3600:d}:{(s%3600)//60:02d}:{s%60:02d}" if s >= 3600 else f"{s//60:02d}:{s%60:02d}"
def stage(n, total, title):
    print(f"\n[{n}/{total}] {title}   (elapsed {hms(time.time()-T0)})", flush=True)
def bar(frac, w=34):
    frac = min(1.0, max(0.0, frac)); k = int(frac * w); return "[" + "#" * k + "-" * (w - k) + f"] {frac*100:5.1f}%"
def line(txt):
    sys.stdout.write("\r" + txt.ljust(118)[:118]); sys.stdout.flush()
def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)
def die(msg):
    print("\nERROR: " + msg); sys.exit(1)

def ensure_numpy():
    try:
        import numpy  # noqa
    except ImportError:
        print("numpy missing -> installing (one time)...")
        subprocess.run([sys.executable, "-m", "pip", "install", "numpy"], check=True)
ensure_numpy()
import numpy as np

# ----------------------------------------------------------------------------- scenes (story beats)
# name, narration characters (used to place the cut inside the nearest real pause), tension 0..1
SCENES = [
    ("title", 17, .15), ("alert_a", 86, .25), ("alert_b", 147, .35), ("disbelief", 96, .40),
    ("bathroom", 78, .50), ("texting", 96, .50), ("friend", 149, .60), ("clock", 29, .55),
    ("alert2", 127, .80), ("door2", 199, .85), ("sirens", 90, .90), ("outside", 107, .95),
    ("noreply", 77, .90), ("shaking", 102, 1.0), ("knock1", 79, .90), ("knock2", 138, 1.0),
]

# sentence lengths (characters) of the story, line by line, and how many sentences each scene covers
SENT_LINES = [[17], [34, 52, 47, 23, 36, 15, 26], [56, 40, 50, 28], [48, 20, 28, 28, 50, 24, 12, 35], [12], [17],
              [14, 35, 29, 49, 72, 21, 15, 28, 41, 22], [38, 8, 15, 29], [33, 11, 26, 12, 11, 40, 14], [29, 27, 21, 34, 32, 36], [59, 20, 15, 36, 26, 18, 43]]
SCENE_SENTS = [1, 2, 5, 2, 2, 3, 5, 2, 4, 6, 4, 7, 3, 3, 2, 5]

# ----------------------------------------------------------------------------- 2. voice analysis
def analyse(force=False):
    cache = WORK / "analysis.json"
    key = f"{AUDIO.stat().st_size}-{int(AUDIO.stat().st_mtime)}-v4"
    if cache.exists() and not force:
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("key") == key:
            print("  using cached analysis"); return d
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(AUDIO), "-f", "f32le", "-ac", "1", "-ar", "22050", "-"],
                       capture_output=True, check=True)
    x = np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64); sr = 22050
    dur = len(x) / sr
    nf = int(math.ceil(dur * FPS))
    cs = np.concatenate([[0.0], np.cumsum(x * x)])
    e = np.minimum((np.arange(nf + 1) * sr / FPS).astype(int), len(x))
    rms = np.sqrt((cs[e[1:]] - cs[e[:-1]]) / np.maximum(1, e[1:] - e[:-1]))
    db = 20 * np.log10(rms + 1e-9)
    p95 = np.percentile(rms, 95) + 1e-9
    raw = np.clip(rms / p95, 0, 1.4)
    env = np.zeros(nf); v = 0.0
    for i in range(nf):                       # fast attack, slow release -> feels like breath of the voice
        v += (raw[i] - v) * (0.55 if raw[i] > v else 0.10); env[i] = v
    silent = db < -35
    # pauses >= 0.3 s
    pauses, i = [], 0
    while i < nf:
        if silent[i]:
            j = i
            while j < nf and silent[j]: j += 1
            if j - i >= int(0.3 * FPS): pauses.append((i, j))
            i = j
        else: i += 1
    # ---- sentence-level alignment: choose, among the real pauses, the ones that best fit the story's sentence lengths
    sents = [c for ln in SENT_LINES for c in ln]
    para_end = set(); k = -1
    for ln in SENT_LINES:
        k += len(ln); para_end.add(k)
    rate = (np.count_nonzero(~silent) / FPS) / sum(sents)          # seconds of speech per character
    P = [(a, b) for a, b in pauses if a > 0.5 * FPS]               # candidate sentence boundaries
    M, NP = len(sents), len(P); INF = 1e18
    dp = [[INF] * NP for _ in range(M)]; back = [[-1] * NP for _ in range(M)]
    def seg_cost(i, t0, t1):
        exp = sents[i] * rate; act = max(0.05, (t1 - t0) / FPS)
        return ((act - exp) / (exp + 0.8)) ** 2
    def bonus(i, j):
        dur = (P[j][1] - P[j][0]) / FPS
        return -(1.2 + (1.6 if i in para_end else 0)) * min(dur, 1.2)
    for j in range(NP):
        dp[0][j] = seg_cost(0, 0, P[j][0]) + bonus(0, j)
    for i in range(1, M - 1):
        for j in range(i - 1, NP):
            for jp in range(j):
                if dp[i - 1][jp] >= INF: continue
                c = dp[i - 1][jp] + seg_cost(i, P[jp][1], P[j][0]) + bonus(i, j)
                if c < dp[i][j]: dp[i][j] = c; back[i][j] = jp
    best, bj = INF, -1
    for j in range(NP):
        if dp[M - 2][j] < INF:
            c = dp[M - 2][j] + seg_cost(M - 1, P[j][1], nf)
            if c < best: best, bj = c, j
    ends = [0] * (M - 1); j = bj
    for i in range(M - 2, -1, -1):
        ends[i] = j; j = back[i][j]
    sent_t = [int((P[j][0] + P[j][1]) / 2) for j in ends]           # cut in the middle of the pause
    bounds = [0]; idx = 0
    for n in SCENE_SENTS[:-1]:
        idx += n; bounds.append(sent_t[idx - 1])
    bounds.append(nf)
    scenes = [dict(i=i, name=SCENES[i][0], start=bounds[i], end=bounds[i + 1], tension=SCENES[i][2]) for i in range(len(SCENES))]
    d = dict(key=key, fps=FPS, frames=nf, duration=dur, env=[round(float(a), 3) for a in env], scenes=scenes)
    d["events"] = make_events([(s["start"] / FPS, s["end"] / FPS) for s in scenes])
    WORK.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(d), encoding="utf-8")
    return d

def make_events(S):
    """Every sound AND every visual accent is driven by this single list -> picture and sound can't drift apart."""
    ev = []
    def add(t, typ, v=1.0, dur=0.0): ev.append(dict(t=round(t, 3), type=typ, v=v, dur=round(dur, 3)))
    st = lambda i: S[i][0]; en = lambda i: S[i][1]; du = lambda i: S[i][1] - S[i][0]
    at = lambda i, f: S[i][0] + du(i) * f
    add(0.10, "alert", 1.0, 1.45); add(0.10, "buzz", 1.0, 1.4)
    add(at(1, .55), "creak", .5, 1.2)
    add(en(2) - 1.0, "lampoff", 1, .2)
    add(at(4, .08), "step", .5); add(at(4, .18), "step", .5); add(at(4, .28), "step", .5); add(at(4, .37), "step", .5)
    add(at(4, .52), "creak", .8, 1.3); add(at(4, .78), "thud", 1.0)
    add(at(5, .10), "sent"); add(at(5, .28), "sent"); add(at(5, .64), "pop")
    add(at(6, .08), "sent"); add(at(6, .46), "pop")
    add(st(7), "swoosh", 1.0, du(7)); add(st(7), "ticks", 1.0, du(7))
    add(st(8), "alert", 1.1, 2.0); add(st(8), "boom", 1.0, 3.0)
    for k in range(3): add(at(8, .45) + k * .55, "knock", .35)
    for k in range(3): add(at(8, .76) + k * .5, "knock", .3)
    for k in range(8): add(at(9, .04 + k * .11), "step", .75)
    add(at(9, .35), "scratch", .8, 1.0); add(at(9, .72), "scratch", .9, 1.1)
    add(st(10), "boom", .9, 3.0)
    add(st(10), "siren", 1.0, du(10) + 1.0); add(at(10, .45), "siren2", .55, du(10) * .55 + 1.0)
    add(st(10) + 2.0, "rumble", .35, max(1.0, du(10) - 2.5))
    add(st(11), "siren", .35, du(11) + du(12) + 0.5)
    add(st(11), "caralarm", .75, du(11) + du(12) * .7)
    for f in (.12, .45, .78): add(at(11, f), "crash", 1.0)
    add(at(12, .12), "sent"); add(at(12, .32), "sent"); add(at(12, .52), "sent")
    add(st(13) - .4, "siren", 1.15, du(13) + 1.2); add(st(13) - .2, "siren2", .8, du(13) + 1.0)
    add(st(13), "rumble", 1.0, du(13)); add(st(13), "boom", .9, 3.0)
    for f in (.2, .45, .7): add(at(13, f), "crash", .55)
    add(en(14) - 1.15, "knock", 1.0); add(en(14) - .62, "knock", 1.0)
    add(at(15, .10), "shout", 1.0, 2.2); add(at(15, .36), "knock", 1.0); add(at(15, .39), "knock", 1.0)
    add(at(15, .43), "shout", .9, 1.6); add(at(15, .60), "rattle", 1.0, .9)
    add(at(15, .68), "knock", 1.0); add(at(15, .715), "knock", 1.0); add(at(15, .75), "knock", 1.0)
    add(at(15, .80), "shout", 1.0, 1.8); add(en(15) - 2.2, "bang", 1.0); add(en(15) - 1.6, "boom", 1.0, 3.0)
    ev.sort(key=lambda e: e["t"]); return ev

# ----------------------------------------------------------------------------- 3. sound design (numpy synth)
RNG = np.random.default_rng(7)
def tt(n): return np.arange(n) / SR
def noise(n): return RNG.standard_normal(n)
def fbp(x, lo=None, hi=None):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); m = np.ones_like(f)
    if lo: m = m / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    if hi: m = m / np.sqrt(1 + (f / hi) ** 4)
    return np.fft.irfft(X * m, len(x))
def fade(x, a=.01, b=.03):
    n = len(x); na, nb = max(1, int(a * SR)), max(1, int(b * SR)); w = np.ones(n)
    w[:na] = np.linspace(0, 1, na); w[-nb:] = np.minimum(w[-nb:], np.linspace(1, 0, nb)); return x * w
def saw(ph, h=8): return sum(np.sin(k * ph) / k for k in range(1, h + 1))
def echo(x, taps=((.31, .45), (.73, .28))):
    y = x.copy()
    for d, g in taps:
        k = int(d * SR)
        if k < len(x): y[k:] += x[:-k] * g
    return y

def s_knock(v, far=False):
    n = int(.5 * SR); t = tt(n)
    body = np.sin(2 * np.pi * (92 + 70 * np.exp(-t * 30)) * t) * np.exp(-t * 13)
    wood = .5 * np.sin(2 * np.pi * 230 * t) * np.exp(-t * 20) + .25 * np.sin(2 * np.pi * 415 * t) * np.exp(-t * 28)
    click = .8 * fbp(noise(n), 600, 3500) * np.exp(-t * 90)
    x = (body + wood + click) * v
    return fbp(x, None, 520) * 1.5 if far else x
def s_thump(f0=62, d=.25, a=1.0):
    n = int(d * SR); t = tt(n); return a * np.sin(2 * np.pi * f0 * (1 + .5 * np.exp(-t * 25)) * t) * np.exp(-t * 17) * (1 - np.exp(-t * 500))
def s_step(v):
    n = int(.3 * SR); t = tt(n)
    return v * (s_thump(68, .3, 1.0) + .5 * fbp(noise(n), 70, 380) * np.exp(-t * 22) + .25 * fbp(noise(n), 900, 3000) * np.exp(-t * 60))
def s_creak(v, d):
    n = int(d * SR); t = tt(n); f = 135 + 80 * (t / d) ** 1.5 + 7 * np.sin(2 * np.pi * 9 * t)
    ph = 2 * np.pi * np.cumsum(f) / SR; x = fbp(saw(ph, 10), 320, 1900) * np.sin(np.pi * t / d) ** 1.6
    return v * .5 * x / (np.abs(x).max() + 1e-9)
def s_buzz(d):
    n = int(d * SR); t = tt(n); gate = (np.sin(2 * np.pi * 3.3 * t) > -.15).astype(float)
    x = fbp(noise(n), 90, 800) * (.55 + .45 * np.sign(np.sin(2 * np.pi * 52 * t))) + .35 * np.sin(2 * np.pi * 150 * t)
    return fade(x * gate, .02, .05) * .55
def s_alert(v, d):
    n = int(d * SR); t = tt(n); x = np.sin(2 * np.pi * 853 * t) + np.sin(2 * np.pi * 960 * t)
    return fade(fbp(x, 300, 3600), .02, .08) * .26 * v
def s_pop():
    n = int(.4 * SR); t = tt(n); return (np.sin(2 * np.pi * 880 * t) * np.exp(-t * 14) + .8 * np.sin(2 * np.pi * 1320 * (t - .09).clip(0)) * np.exp(-(t - .09).clip(0) * 12) * (t > .09)) * .4
def s_sent():
    n = int(.32 * SR); t = tt(n); return fbp(noise(n), 1400, 7000) * np.sin(np.pi * t / .32) ** 2 * .3
def s_swoosh(d):
    n = int(d * SR); t = tt(n); x = fbp(noise(n), 400, 5000) * (t / d) ** 2; return fade(x, .2, .2) * .5
def s_ticks(d):
    n = int(d * SR); x = np.zeros(n); tm = 0.0; k = 0
    while tm < d:
        rate = 3 + 11 * min(1, tm / (d * .7)); i = int(tm * SR); m = int(.05 * SR)
        if i + m < n:
            t = tt(m); c = fbp(noise(m), 1500, 6500) * np.exp(-t * 400) + np.sin(2 * np.pi * (1100 if k % 2 else 780) * t) * np.exp(-t * 90) * .6
            x[i:i + m] += c
        tm += 1 / rate; k += 1
    return x * .45
def s_siren(d, kind="wail"):
    n = int(d * SR); t = tt(n)
    if kind == "wail":
        f = 400 + 420 * (.5 - .5 * np.cos(2 * np.pi * t / 8.5)); x = saw(2 * np.pi * np.cumsum(f) / SR, 6)
    else:
        f = np.where((t % 1.9) < .95, 435, 585); f = np.convolve(f, np.ones(400) / 400, "same"); x = saw(2 * np.pi * np.cumsum(f) / SR, 5)
    x = echo(fbp(x, None, 1800)); return fade(x, .8, .9) * .3
def s_caralarm(d):
    n = int(d * SR); t = tt(n); f = 750 + 750 * ((t * 3.2) % 1) ** .7
    x = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)); gate = ((t % 2.3) < 1.8).astype(float)
    return echo(fbp(x * gate, 400, 2300), ((.4, .4),)) * .22
def s_crash(v):
    n = int(1.7 * SR); t = tt(n); x = fbp(noise(n), 150, 5000) * np.exp(-t * 4.5) + 1.1 * s_thump(55, 1.7, 1) * np.exp(-t * 2)
    for _ in range(14):
        i = int(RNG.uniform(.05, .9) * SR); m = int(.05 * SR)
        x[i:i + m] += fbp(noise(m), 3500, 9500) * np.exp(-tt(m) * 140) * RNG.uniform(.3, .8)
    return v * .8 * x / (np.abs(x).max() + 1e-9)
def s_scratch(v, d):
    n = int(d * SR); t = tt(n); am = np.clip(np.sin(2 * np.pi * 2.6 * t) , 0, 1) ** 2
    return v * .45 * fbp(noise(n), 2200, 6500) * am * np.sin(np.pi * t / d)
def s_rumble(v, d):
    n = int(d * SR); t = tt(n); am = .6 + .4 * np.sin(2 * np.pi * 7 * t + np.sin(2 * np.pi * .7 * t) * 3)
    x = fbp(noise(n), 20, 110) * 6 * am + .5 * np.sin(2 * np.pi * 38 * t) + .3 * np.sin(2 * np.pi * 52 * t)
    return fade(x, .8, .8) * v * .55
def s_boom(v, d):
    n = int(d * SR); t = tt(n); x = np.sin(2 * np.pi * 46 * t) * np.exp(-t * 2.3) + 2.5 * fbp(noise(n), None, 140) * np.exp(-t * 3)
    return v * .9 * x
def s_shout(v, d):
    n = int(d * SR); t = tt(n); f0 = 128 + 28 * np.sin(2 * np.pi * .8 * t) + 38 * (t / d) + 3 * np.sin(2 * np.pi * 6 * t)
    src = saw(2 * np.pi * np.cumsum(f0) / SR, 30); syl = np.clip(np.sin(2 * np.pi * 2.6 * t) * 3, 0, 1)
    x = (fbp(src, 650, 950) + .8 * fbp(src, 1050, 1500) + .3 * fbp(src, 2200, 2900)) * syl
    return v * .55 * fade(fbp(x, None, 2200), .05, .15) / 40
def s_rattle(d):
    n = int(d * SR); t = tt(n); return fbp(noise(n), 800, 4800) * (.5 + .5 * np.sign(np.sin(2 * np.pi * 21 * t))) * np.exp(-t * 2.4) * .55 + .2 * np.sin(2 * np.pi * 1850 * t) * np.exp(-t * 7)
def s_click():
    n = int(.15 * SR); t = tt(n); return fbp(noise(n), 900, 5500) * np.exp(-t * 130) * .8 + s_thump(90, .15, .6)

def build_sfx(d):
    N = int(d["duration"] * SR) + SR; L = np.zeros(N); R = np.zeros(N)
    def put(sig, t0, pan=0.0, g=1.0):
        i = int(t0 * SR)
        if i >= N: return
        sig = sig[:N - i] * g; a = (pan + 1) * math.pi / 4
        L[i:i + len(sig)] += sig * math.cos(a); R[i:i + len(sig)] += sig * math.sin(a)
    sc = d["scenes"]; mids = [(s["start"] + s["end"]) / 2 / FPS for s in sc]; tens = [s["tension"] for s in sc]
    t = tt(N); ten = np.interp(t, mids, tens)
    # --- continuous bed: drone, air, eerie high tone
    drone = (np.sin(2 * np.pi * 55 * t + 3 * np.sin(2 * np.pi * .1 * t)) * .5 + np.sin(2 * np.pi * 58.3 * t) * .4 + np.sin(2 * np.pi * 110 * t) * .15)
    put(drone * (.25 + .75 * ten) * .55, 0, 0)
    put(np.sin(2 * np.pi * 3136 * t + 2 * np.sin(2 * np.pi * .13 * t)) * .02 * ten ** 2 * (.6 + .4 * np.sin(2 * np.pi * .21 * t)), 0, .2)
    air = fbp(noise(N), 70, 520) * (.55 + .45 * np.sin(2 * np.pi * .07 * t)) * (.05 + .06 * ten) * 4
    put(air, 0, 0)
    # --- heartbeat (from first alert on, speeds up with tension)
    tm = d["scenes"][1]["start"] / FPS
    while tm < d["duration"]:
        k = float(np.interp(tm, mids, tens)); period = 60 / (62 + 70 * k)
        put(s_thump(60, .26, .8 + .3 * k), tm, 0, .55); put(s_thump(52, .22, .6), tm + .27, 0, .5); tm += period
    # --- breathing (stops while she holds her breath at the end)
    stop = d["scenes"][15]["start"] / FPS; tm = d["scenes"][3]["start"] / FPS
    while tm < stop - 3:
        k = float(np.interp(tm, mids, tens)); m = int(1.2 * SR)
        put(fbp(noise(m), 600, 4200) * np.sin(np.pi * tt(m) / 1.2) ** 2 * (.07 + .08 * k), tm, 0)
        m2 = int(1.4 * SR); put(fbp(noise(m2), 400, 3200) * np.sin(np.pi * tt(m2) / 1.4) ** 2 * (.06 + .07 * k), tm + 1.5, 0)
        tm += 3.4 - 1.0 * k + RNG.uniform(-.2, .2)
    # --- scripted events (same list the picture uses)
    for e in d["events"]:
        ty, v, du, t0 = e["type"], e["v"], max(e["dur"], .1), e["t"]
        if ty == "knock":    put(s_knock(v, v < .5), t0, 0, .8 if v >= .5 else .9)
        elif ty == "thud":   put(s_thump(70, .4, 1.2) + .3 * fbp(noise(int(.4 * SR)), 80, 500) * np.exp(-tt(int(.4 * SR)) * 14), t0, .3, .9)
        elif ty == "step":   put(s_step(v), t0, RNG.uniform(-.4, .4), .6)
        elif ty == "creak":  put(s_creak(v, du), t0, -.3, .6)
        elif ty == "buzz":   put(s_buzz(du), t0, -.5, .9)
        elif ty == "alert":  put(s_alert(v, du), t0, -.3, 1.0)
        elif ty == "pop":    put(s_pop(), t0, -.2, .8)
        elif ty == "sent":   put(s_sent(), t0, .2, .7)
        elif ty == "swoosh": put(s_swoosh(du), t0, 0, .6)
        elif ty == "ticks":  put(s_ticks(du), t0, .25, .8)
        elif ty == "boom":   put(s_boom(v, du), t0, 0, .8)
        elif ty == "siren":  put(s_siren(du, "wail"), t0, -.35, v)
        elif ty == "siren2": put(s_siren(du, "hilo"), t0, .35, v)
        elif ty == "caralarm": put(s_caralarm(du), t0, .6, v)
        elif ty == "crash":  put(s_crash(v), t0, RNG.uniform(-.5, .5), .75)
        elif ty == "scratch": put(s_scratch(v, du), t0, .1, .8)
        elif ty == "rumble": put(s_rumble(v, du), t0, 0, .9)
        elif ty == "shout":  put(s_shout(v, du), t0, .15, .6)
        elif ty == "rattle": put(s_rattle(du), t0, .1, .8)
        elif ty == "bang":   put(s_knock(1.4) * 1.3, t0, 0, .9); put(s_crash(.6), t0, 0, .8)
        elif ty == "lampoff": put(s_click(), t0, -.6, .8)
    m = max(np.abs(L).max(), np.abs(R).max()) + 1e-9
    n = int(d["duration"] * SR); return L[:n] / m * .95, R[:n] / m * .95

def write_wav(path, L, R):
    a = (np.stack([L, R], 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(a.tobytes())

def make_audio(d, sfx_gain=.60):
    wav = WORK / "sfx_bed.wav"; mix = WORK / "final_mix.wav"
    if not wav.exists() or not mix.exists() or wav.stat().st_mtime < (WORK / "analysis.json").stat().st_mtime:
        print("  synthesising sound-design bed ...", flush=True)
        L, R = build_sfx(d); write_wav(wav, L, R)
        print("  mixing (voice on top, SFX ducked under the voice) ...", flush=True)
        graph = (f"[0:a]aformat=sample_rates={SR}:channel_layouts=stereo,asplit=2[v][sc];"
                 f"[1:a]volume={sfx_gain}[s];"
                 "[s][sc]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=450:makeup=1[sd];"
                 "[v][sd]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.96[a]")
        base = ["ffmpeg", "-y", "-v", "error", "-i", str(AUDIO), "-i", str(wav), "-filter_complex", graph, "-map", "[a]", "-ar", "48000"]
        r = subprocess.run(base + [str(mix)], capture_output=True, text=True)
        if r.returncode != 0:      # very old ffmpeg without amix normalize=0
            graph = graph.replace("amix=inputs=2:duration=first:normalize=0", "amix=inputs=2:duration=first,volume=2")
            base[base.index("-filter_complex") + 1] = graph; run(base + [str(mix)])
    else:
        print("  using cached audio mix")
    return mix

# ----------------------------------------------------------------------------- 4. Remotion project files
def write_png(path, arr):
    h, w, _ = arr.shape; raw = b"".join(b"\x00" + arr[y].tobytes() for y in range(h))
    def ch(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))

def make_textures(pub):
    r = np.random.default_rng(3)
    g = np.clip(r.normal(128, 46, (256, 256)), 0, 255).astype(np.uint8)
    write_png(pub / "grain.png", np.dstack([g, g, g, np.full_like(g, 255)]))
    n = r.standard_normal((512, 512)); F = np.fft.fft2(n); fy = np.fft.fftfreq(512)[:, None]; fx = np.fft.fftfreq(512)[None, :]
    n = np.real(np.fft.ifft2(F * np.exp(-(fx ** 2 + fy ** 2) * 900))); n = (n - n.min()) / (n.max() - n.min())
    p = (110 + n * 70).astype(np.uint8); write_png(pub / "paper.png", np.dstack([p, p, p, np.full_like(p, 255)]))

def scaffold(d):
    src = PROJ / "src"; pub = PROJ / "public"; src.mkdir(parents=True, exist_ok=True); pub.mkdir(exist_ok=True)
    for name, text in FILES.items():
        f = PROJ / name; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text, encoding="utf-8")
    (src / "analysis.json").write_text(json.dumps({k: d[k] for k in ("frames", "fps", "env", "scenes", "events")}), encoding="utf-8")
    if not (pub / "grain.png").exists(): make_textures(pub)

def which(n):
    p = shutil.which(n) or shutil.which(n + ".cmd") or shutil.which(n + ".exe"); return p
def npm_install():
    if (PROJ / "node_modules" / "@remotion" / "renderer").exists(): print("  node_modules present"); return
    npm = which("npm") or die("npm not found - install Node.js 18+ from nodejs.org")
    print("  installing Remotion + dependencies (first run only, a few minutes) ...", flush=True)
    p = subprocess.Popen([npm, "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=PROJ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t = time.time()
    while p.poll() is None:
        line(f"  npm install ... {hms(time.time()-t)}"); time.sleep(1)
    print()
    if p.returncode != 0: die("npm install failed:\n" + p.stdout.read()[-1500:])

# ----------------------------------------------------------------------------- 5/6. render with resume
def probe_frames(f):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(f)],
                           capture_output=True, text=True); return int(r.stdout.strip().split(",")[0])
    except Exception: return -1

def source_signature(d):
    h = hashlib.sha1()
    for name in sorted(FILES): h.update(FILES[name].encode())
    h.update(json.dumps(d["scenes"]).encode()); h.update(json.dumps(d["events"]).encode()); return h.hexdigest()[:16]

def render_all(d, args):
    total = d["frames"]; CHUNKS.mkdir(parents=True, exist_ok=True); STILLS.mkdir(exist_ok=True)
    sig = source_signature(d); sf = CHUNKS / ".sig"
    if args.fresh or (sf.exists() and sf.read_text() != sig):
        if any(CHUNKS.glob("chunk_*.mp4")): print("  scene timing / animation code changed -> old chunks discarded")
        for f in CHUNKS.glob("*"): f.unlink()
    sf.write_text(sig)
    chunks, done_frames = [], 0
    for idx, a in enumerate(range(0, total, CHUNK_FRAMES)):
        b = min(total - 1, a + CHUNK_FRAMES - 1); out = CHUNKS / f"chunk_{idx:03d}.mp4"
        if out.exists() and probe_frames(out) == b - a + 1: done_frames += b - a + 1; continue
        if out.exists(): out.unlink()
        chunks.append(dict(idx=idx, **{"from": a, "to": b}, out=str(out)))
    n_chunks = math.ceil(total / CHUNK_FRAMES)
    stills = []
    if not args.no_preview:
        for s in d["scenes"]:
            fr = int(s["start"] + (s["end"] - s["start"]) * .55); stills.append(dict(frame=fr, out=str(STILLS / f"scene_{s['i']:02d}_{s['name']}.jpg")))
    todo_stills = [s for s in stills if not Path(s["out"]).exists()]
    if not chunks and not todo_stills:
        print(f"  all {n_chunks} chunks already rendered - nothing to do"); return
    print(f"  {done_frames}/{total} frames already saved from earlier runs; rendering {len(chunks)} chunk(s) of {CHUNK_FRAMES} frames", flush=True)
    job = dict(stills=todo_stills, chunks=chunks, crf=args.crf, concurrency=args.concurrency)
    (WORK / "job.json").write_text(json.dumps(job), encoding="utf-8")
    node = which("node") or die("node not found")
    p = subprocess.Popen([node, "render.mjs", str(WORK / "job.json")], cwd=PROJ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    t0 = time.time(); base_done = done_frames; cur = {}; finished = 0; first = None
    for raw in p.stdout:
        raw = raw.strip()
        if not raw.startswith("@@"):
            if raw and not raw.startswith("("): print("\n  " + raw[:160])
            continue
        m = json.loads(raw[2:]); ev = m["ev"]
        if ev == "bundling": line("  bundling animation code ...")
        elif ev == "bundle": line(f"  bundling animation code ... {int(m['p'])}%")
        elif ev == "still":
            print(f"\n  preview still saved (frame {m['frame']})  -> {STILLS}", end="")
            if first is None: first = time.time()
        elif ev == "frames":
            cur[m["chunk"]] = m["done"]
            done = base_done + sum((c["to"] - c["from"] + 1) for c in chunks if c["idx"] not in cur and c["idx"] < m["chunk"]) + m["done"]
            el = time.time() - t0; fresh = done - base_done; rate = fresh / el if el > 1 else 0
            eta = (total - done) / rate if rate > 0 else 0
            line(f"  {bar(done/total)} chunk {m['chunk']+1}/{n_chunks} frame {done}/{total} {rate:4.1f} fps  elapsed {hms(el)}  eta {hms(eta)}")
        elif ev == "chunk_done":
            finished += 1
        elif ev == "done": print()
    if p.wait() != 0: die("renderer stopped. Re-run the script - finished chunks are kept and it will resume.")

def assemble(d):
    files = sorted(CHUNKS.glob("chunk_*.mp4")); need = math.ceil(d["frames"] / CHUNK_FRAMES)
    if len(files) != need: die(f"expected {need} chunks, found {len(files)} - re-run to finish rendering")
    lst = WORK / "concat.txt"; lst.write_text("".join(f"file '{f.as_posix()}'\n" for f in files), encoding="utf-8")
    mix = WORK / "final_mix.wav"; dur = d["frames"] / FPS
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(mix), "-map", "0:v", "-map", "1:a",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-t", f"{dur:.4f}", "-movflags", "+faststart", str(FINAL)]
    print("  joining chunks + muxing audio ...", flush=True); run(cmd)
    def sd(kind):
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", kind, "-show_entries", "stream=duration", "-of", "csv=p=0", str(FINAL)], capture_output=True, text=True)
        try: return float(r.stdout.strip())
        except Exception: return 0
    v, a = sd("v:0"), sd("a:0"); n = probe_frames(FINAL)
    print(f"  video {v:.3f}s ({n} frames) | audio {a:.3f}s | offset {abs(v-a)*1000:.0f} ms")
    if n != d["frames"] or abs(v - a) > 0.05:
        print("  timing mismatch from stream-copy -> re-encoding once to guarantee frame-exact sync ...", flush=True)
        run(["ffmpeg", "-y", "-v", "error", "-stats", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-vf", f"fps={FPS}",
             "-c:v", "libx264", "-crf", "15", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-t", f"{dur:.4f}", "-movflags", "+faststart", str(FINAL)])

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--prep-only", action="store_true"); ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--no-preview", action="store_true"); ap.add_argument("--crf", type=int, default=17); ap.add_argument("--concurrency", type=int, default=None)
    args = ap.parse_args(); total_stages = 6
    OUT_DIR.mkdir(parents=True, exist_ok=True); WORK.mkdir(exist_ok=True)
    stage(1, total_stages, "checking tools")
    for tool in ("ffmpeg", "ffprobe"): which(tool) or die(f"{tool} not found - install FFmpeg and add it to PATH")
    if not args.prep_only: which("node") or die("Node.js not found - install Node 18+ from nodejs.org")
    AUDIO.exists() or die(f"audio not found: {AUDIO}")
    print("  ok")
    stage(2, total_stages, "analysing the voice -> scene cuts locked to real pauses")
    d = analyse(); print(f"  {d['duration']:.2f}s of audio = {d['frames']} frames @ {FPS} fps, {len(d['scenes'])} scenes, {len(d['events'])} sound/visual cues")
    lines = [f"scene {s['i']:2d} {s['name']:10s} {s['start']/FPS:7.2f}s -> {s['end']/FPS:7.2f}s" for s in d["scenes"]]
    (OUT_DIR / "sync_report.txt").write_text("\n".join(lines), encoding="utf-8"); print("  scene timing saved to sync_report.txt")
    stage(3, total_stages, "sound design + mix (voice louder than effects)")
    make_audio(d)
    stage(4, total_stages, "building the Remotion project")
    scaffold(d)
    if args.prep_only: print("  prep-only: project written to", PROJ); return
    npm_install()
    stage(5, total_stages, "rendering (resumable - safe to stop with Ctrl+C and run again)")
    render_all(d, args)
    stage(6, total_stages, "assembling final video")
    assemble(d)
    print(f"\nDONE  ->  {FINAL}   (total {hms(time.time()-T0)})")

# ============================================================================= embedded Remotion project
FILES = {}
FILES["package.json"] = r'''{
  "name": "horror-anim", "version": "1.0.0", "private": true, "type": "module",
  "dependencies": {
    "@remotion/bundler": "4.0.250", "@remotion/cli": "4.0.250", "@remotion/renderer": "4.0.250", "remotion": "4.0.250",
    "react": "18.3.1", "react-dom": "18.3.1"
  },
  "devDependencies": { "@types/react": "18.3.3", "typescript": "5.5.4" }
}
'''
FILES["tsconfig.json"] = r'''{ "compilerOptions": { "target": "ES2020", "module": "ESNext", "moduleResolution": "bundler", "jsx": "react-jsx", "strict": false, "skipLibCheck": true, "resolveJsonModule": true, "esModuleInterop": true, "noEmit": true }, "include": ["src"] }
'''
FILES["render.mjs"] = r'''import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import path from 'node:path';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const log = (o) => console.log('@@' + JSON.stringify(o));
(async () => {
  log({ev: 'bundling'});
  const serveUrl = await bundle({entryPoint: path.join(here, 'src/index.ts'), publicDir: path.join(here, 'public'), onProgress: (p) => log({ev: 'bundle', p})});
  const comp = await selectComposition({serveUrl, id: 'Main', timeoutInMilliseconds: 180000});
  for (const s of job.stills) {
    await renderStill({composition: comp, serveUrl, frame: s.frame, output: s.out, imageFormat: 'jpeg', jpegQuality: 92, timeoutInMilliseconds: 180000});
    log({ev: 'still', frame: s.frame});
  }
  for (const c of job.chunks) {
    const tmp = c.out + '.part.mp4';
    let last = -1;
    await renderMedia({
      composition: comp, serveUrl, codec: 'h264', outputLocation: tmp, frameRange: [c.from, c.to], muted: true,
      crf: job.crf, pixelFormat: 'yuv420p', x264Preset: 'medium', imageFormat: 'jpeg', jpegQuality: 100,
      concurrency: job.concurrency, timeoutInMilliseconds: 240000,
      onProgress: ({renderedFrames}) => { if (renderedFrames !== last) { last = renderedFrames; log({ev: 'frames', chunk: c.idx, done: renderedFrames}); } },
    });
    fs.renameSync(tmp, c.out);
    log({ev: 'chunk_done', chunk: c.idx});
  }
  log({ev: 'done'});
})().catch((e) => { console.error(e); process.exit(1); });
'''
FILES["src/index.ts"] = r'''import {registerRoot} from 'remotion';
import {Root} from './Root';
registerRoot(Root);
'''
FILES["src/Root.tsx"] = r'''import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Main';
import {A} from './lib';
export const Root: React.FC = () => (
  <Composition id="Main" component={Main} durationInFrames={A.frames} fps={60} width={1080} height={1920} />
);
'''
FILES["src/lib.tsx"] = r'''import React from 'react';
import data from './analysis.json';

export const A: any = data;
export const FPS = 60;
export type P = [number, number];
export const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const ease = (t: number) => { t = clamp(t); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
export const hash = (n: number) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
export const noise = (x: number, seed = 0) => { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i + seed * 17.3), hash(i + 1 + seed * 17.3), u) * 2 - 1; };

// palette: deep navy, muted brown, pale yellow, desaturated skin
export const C = {
  ink: '#05080f', n0: '#050914', n1: '#0b1530', n2: '#14264d', n3: '#22406f',
  b0: '#241911', b1: '#43301f', b2: '#6a4d36', b3: '#8c6d4c',
  yel: '#f2e3a0', yel2: '#cdb870', skin: '#b7a091', skinSh: '#8b766b', skinDk: '#5f504d',
  hair: '#15121a', hood: '#26365a', hoodDk: '#18233d', white: '#d9d3c2',
};

const EV: Record<string, any[]> = {};
for (const e of A.events) { (EV[e.type] = EV[e.type] || []).push(e); }

export const makeFx = (f: number) => {
  const t = f / FPS; let i = 0;
  for (let k = 0; k < A.scenes.length; k++) if (f >= A.scenes[k].start) i = k;
  const sc = A.scenes[i]; const len = sc.end - sc.start; const lf = f - sc.start;
  const env = A.env[Math.min(f, A.env.length - 1)];
  const pulse = (type: string, decay = 0.25) => { let m = 0; for (const e of (EV[type] || [])) { const d = t - e.t; if (d >= 0) m = Math.max(m, Math.exp(-d / decay) * e.v); } return m; };
  const within = (type: string) => { let m = 0; for (const e of (EV[type] || [])) if (t >= e.t && t <= e.t + e.dur) m = Math.max(m, e.v); return m; };
  const since = (type: string) => { let r = -1; for (const e of (EV[type] || [])) if (t >= e.t) r = t - e.t; return r; };
  return { f, t, i, lf, len, p: lf / Math.max(1, len), env, b: Math.floor(f / 5), pulse, within, since, sc };
};
export const Fx = React.createContext<any>(null);
export const useFx = () => React.useContext(Fx);

export const smoothPath = (pts: P[], closed = true) => {
  const n = pts.length; const g = (i: number) => pts[closed ? (i + n) % n : Math.max(0, Math.min(n - 1, i))];
  let d = 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1); const m = closed ? n : n - 1;
  for (let i = 0; i < m; i++) {
    const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2);
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += 'C' + c1[0].toFixed(1) + ',' + c1[1].toFixed(1) + ' ' + c2[0].toFixed(1) + ',' + c2[1].toFixed(1) + ' ' + p2[0].toFixed(1) + ',' + p2[1].toFixed(1);
  }
  return closed ? d + 'Z' : d;
};
export const ell = (cx: number, cy: number, rx: number, ry: number, n = 10, rot = 0): P[] => {
  const out: P[] = []; const c = Math.cos(rot), s = Math.sin(rot);
  for (let k = 0; k < n; k++) { const a = (k / n) * Math.PI * 2; const x = Math.cos(a) * rx, y = Math.sin(a) * ry; out.push([cx + x * c - y * s, cy + x * s + y * c]); }
  return out;
};
export const box = (x: number, y: number, w: number, h: number): P[] => [[x, y], [x + w / 2, y], [x + w, y], [x + w, y + h / 2], [x + w, y + h], [x + w / 2, y + h], [x, y + h], [x, y + h / 2]];

// hand-drawn "boiling" line: every shape re-wobbles at 12 fps like traditional frame-by-frame animation
export const Ink: React.FC<any> = ({ pts, fill = 'none', stroke = C.ink, sw = 6, seed = 0, amp = 2, closed = true, smooth = true, op = 1, blend, dash }) => {
  const { b } = useFx();
  const q: P[] = pts.map((p: P, i: number) => [p[0] + (hash(i * 3.1 + seed * 7.7 + b * 13.3) - 0.5) * 2 * amp, p[1] + (hash(i * 5.3 + seed * 3.3 + b * 17.9 + 50) - 0.5) * 2 * amp] as P);
  const d = smooth ? smoothPath(q, closed) : 'M' + q.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join('L') + (closed ? 'Z' : '');
  return <path d={d} fill={fill} stroke={stroke} strokeWidth={sw} strokeLinejoin="round" strokeLinecap="round" opacity={op} strokeDasharray={dash} style={blend ? { mixBlendMode: blend } : undefined} />;
};

export const Glow: React.FC<any> = ({ id, x, y, r, color = '242,227,160', a = 0.5, sx = 1, sy = 1, blend = 'screen' }) => (
  <g style={{ mixBlendMode: blend }}>
    <defs><radialGradient id={id} cx="50%" cy="50%" r="50%">
      <stop offset="0%" stopColor={'rgb(' + color + ')'} stopOpacity={a} />
      <stop offset="45%" stopColor={'rgb(' + color + ')'} stopOpacity={a * 0.35} />
      <stop offset="100%" stopColor={'rgb(' + color + ')'} stopOpacity={0} />
    </radialGradient></defs>
    <ellipse cx={x} cy={y} rx={r * sx} ry={r * sy} fill={'url(#' + id + ')'} />
  </g>
);
export const Dark: React.FC<any> = ({ id = 'dk', x = 540, y = 960, r = 1300, a = 0.8, inner = 0.25 }) => (
  <g>
    <defs><radialGradient id={id} cx={x} cy={y} r={r} gradientUnits="userSpaceOnUse">
      <stop offset={inner} stopColor="#04070f" stopOpacity={0} /><stop offset="1" stopColor="#04070f" stopOpacity={a} />
    </radialGradient></defs>
    <rect width="1080" height="1920" fill={'url(#' + id + ')'} />
  </g>
);
export const Dust: React.FC<any> = ({ n = 30, x0 = 0, y0 = 0, w = 1080, h = 1920, color = C.yel, a = 0.5, seed = 1, vy = -14, op = 1 }) => {
  const { t } = useFx(); const els: any[] = [];
  for (let k = 0; k < n; k++) {
    const px = x0 + (((hash(k + seed) * w + noise(t * 0.4 + k, seed) * 40) % w) + w) % w;
    const py = y0 + (((hash(k * 7 + seed) * h + t * vy * (0.5 + hash(k))) % h) + h) % h;
    els.push(<circle key={k} cx={px} cy={py} r={0.8 + hash(k * 5) * 2.4} fill={color} opacity={a * op * (0.3 + 0.7 * hash(k * 9 + Math.floor(t * 2)))} />);
  }
  return <g>{els}</g>;
};
export const Shadow: React.FC<any> = ({ dx = 0, dy = 0, sk = -20, sc = 1, op = 0.45, ox = 540, oy = 1200, children }) => (
  <g opacity={op} filter="url(#bl6)" transform={'translate(' + dx + ',' + dy + ') translate(' + ox + ',' + oy + ') skewX(' + sk + ') scale(' + sc + ') translate(' + (-ox) + ',' + (-oy) + ')'}>{children}</g>
);

// ----------------------------------------------------------------------------- the phone
export const PhoneUI: React.FC<any> = ({ x, y, w = 190, h = 330, mode = 'dark' }) => {
  const { p, t } = useFx();
  const bub = (key: string, side: number, yy: number, fw: number, show: number) => {
    if (p < show) return null; const k = ease((p - show) / 0.04); const bw = w * fw;
    return (<g key={key} opacity={k} transform={'translate(0,' + (1 - k) * 8 + ')'}>
      <Ink pts={box(side > 0 ? w - 14 - bw : 14, yy, bw, h * 0.085)} fill={side > 0 ? C.yel2 : '#2b3a5e'} stroke="none" amp={0.5} seed={yy} />
      <rect x={(side > 0 ? w - 14 - bw : 14) + 8} y={yy + h * 0.028} width={bw * 0.7} height={h * 0.012} rx={2} fill={C.ink} opacity={0.45} />
      {side > 0 && <rect x={w - 14 - bw + bw * 0.62} y={yy + h * 0.06} width={bw * 0.28} height={h * 0.008} rx={2} fill={C.ink} opacity={0.5} />}
    </g>);
  };
  const dots = (yy: number) => [0, 1, 2].map((k) => <circle key={k} cx={26 + k * 11} cy={yy} r={3.4} fill="#7c8fb6" opacity={0.4 + 0.6 * Math.max(0, Math.sin(t * 8 - k * 0.9))} />);
  const flash = Math.floor(t * 5) % 2;
  let screen: any = null;
  if (mode === 'alert') {
    screen = (<g>
      <rect x={10} y={20} width={w - 20} height={h - 40} rx={10} fill={flash ? '#e8dc98' : '#2a2415'} />
      <Ink pts={[[w / 2, h * 0.28], [w * 0.2, h * 0.64], [w * 0.8, h * 0.64]]} fill={flash ? C.ink : C.yel} stroke="none" amp={0.8} seed={4} />
      <rect x={w / 2 - 4} y={h * 0.42} width={8} height={h * 0.1} rx={3} fill={flash ? C.yel : C.ink} />
      <circle cx={w / 2} cy={h * 0.575} r={5} fill={flash ? C.yel : C.ink} />
    </g>);
  } else if (mode !== 'dark') {
    const a = mode === 'chat' ? [[1, .10, .62], [1, .28, .45]] : mode === 'chat2' ? [[1, .08, .74]] : [[1, .08, .6], [1, .30, .5], [1, .52, .7]];
    screen = (<g>
      <rect x={10} y={20} width={w - 20} height={h - 40} rx={10} fill="#0d1425" />
      <rect x={10} y={20} width={w - 20} height={h * 0.1} rx={10} fill="#18223b" />
      <circle cx={30} cy={20 + h * 0.05} r={h * 0.028} fill={C.skinSh} /><rect x={52} y={20 + h * 0.035} width={w * 0.32} height={5} rx={2} fill="#7c8fb6" opacity={0.7} />
      {a.map((m: number[], k: number) => bub('o' + k, 1, h * (0.2 + k * 0.13), m[2], m[1]))}
      {mode === 'chat' && (p > 0.42 && p < 0.62 ? dots(h * 0.46) : null)}
      {mode === 'chat' && bub('i1', -1, h * 0.46, 0.5, 0.62)}
      {mode === 'chat2' && bub('i2', -1, h * 0.34, 0.62, 0.46)}
      {mode === 'chat2' && bub('i3', -1, h * 0.46, 0.4, 0.56)}
      {mode === 'empty' && <g><circle cx={w - 24} cy={20 + h * 0.05} r={4} fill="#555" /><rect x={w - 70} y={h * 0.86} width={52} height={5} rx={2} fill="#7c8fb6" opacity={0.35} /></g>}
    </g>);
  }
  return (<g transform={'translate(' + (x - w / 2) + ',' + y + ')'}>
    <Ink pts={box(0, 0, w, h)} fill="#090c14" sw={7} seed={61} amp={1.2} />
    {screen}
  </g>);
};

// ----------------------------------------------------------------------------- the character
export const Character: React.FC<any> = (props) => {
  const { x, y, s = 1, fear = 0.3, look = [0, 0], mouth = 'flat', hands = 'none', tilt = 0, lit = 0, litDir = -1, tint, seed = 1, phoneAt, sleep = 0, tears = 0, children } = props;
  const { f, t, env } = useFx();
  const trem = fear * 2.4 + env * 1.4;
  const ox = noise(f * 0.8, seed) * trem, oy = noise(f * 0.8, seed + 4) * trem * 0.6;
  const br = 1 + Math.sin(t * (1.5 + fear * 2.5)) * 0.012 * (1 + fear);
  const bt = (t + seed * 1.3) % 3.9; const blinkRaw = bt < 0.14 ? Math.sin((bt / 0.14) * Math.PI) : 0;
  const open = clamp(0.95 + fear * 0.5 - Math.max(blinkRaw, sleep) * 1.1, 0.05, 1.5);
  const F = (c: string) => (tint ? tint : c);
  const K = tint ? 'none' : C.ink;
  const pr = Math.min(lerp(16, 7, clamp(fear)), 34 * open);

  const eye = (sx: number) => {
    const ex = sx * 47, ey = -205;
    const lx = look[0] * 13 + noise(f * 0.35, seed + sx) * fear * 3, ly = look[1] * 10 + noise(f * 0.31, seed + 3 + sx) * fear * 3;
    return (<g key={'e' + sx}>
      <Ink pts={ell(ex, ey, 33, 37 * open, 10)} fill={F(C.white)} stroke={K} sw={5} seed={seed + sx + 10} amp={1.2} />
      {open > 0.25 && !tint && <g>
        <circle cx={ex + lx} cy={ey + ly * open} r={pr} fill="#0a0a10" />
        <circle cx={ex + lx - pr * 0.35} cy={ey + ly * open - pr * 0.35} r={pr * 0.28} fill={C.yel} opacity={0.9} />
      </g>}
      {!tint && <Ink pts={[[ex - 36, ey - 4 * open], [ex, ey - 40 * open - 2], [ex + 36, ey - 4 * open]]} closed={false} stroke={C.skinDk} sw={7} seed={seed + sx + 20} amp={1} />}
      {!tint && <Ink pts={[[ex - 28, -163], [ex, -152], [ex + 28, -163]]} closed={false} stroke={C.skinDk} sw={5} op={0.55} seed={seed + sx + 25} amp={0.8} />}
    </g>);
  };
  const brow = (sx: number) => (<Ink key={'br' + sx} pts={[[sx * 84, -248 + fear * 10], [sx * 48, -266 - fear * 14], [sx * 14, -256 - fear * 26]]} closed={false} stroke={C.hair} sw={14} seed={seed + 30 + sx} amp={1.2} />);
  const mY = -106; let mouthEl: any;
  if (mouth === 'gasp') mouthEl = <Ink pts={ell(0, mY, 15 + fear * 6, 20 + env * 12 + fear * 6, 8)} fill="#1a0b0f" stroke={K} sw={5} seed={seed + 40} amp={0.8} />;
  else if (mouth === 'open') mouthEl = <Ink pts={ell(0, mY, 28, 16 + env * 20, 8)} fill="#1a0b0f" stroke={K} sw={5} seed={seed + 40} amp={0.8} />;
  else if (mouth === 'frown') mouthEl = <Ink pts={[[-36, -96], [0, -118], [36, -96]]} closed={false} stroke={K} sw={6} seed={seed + 40} amp={1} />;
  else if (mouth === 'tremble') mouthEl = <Ink pts={[0, 1, 2, 3, 4, 5, 6].map((k) => [-34 + k * 11.3, mY + (k % 2 ? -4 : 4) * (0.6 + fear)] as P)} closed={false} smooth={false} stroke={K} sw={6} seed={seed + 40} amp={2} />;
  else mouthEl = <Ink pts={[[-30, mY], [0, mY + 2], [30, mY - 2]]} closed={false} stroke={K} sw={6} seed={seed + 40} amp={1} />;

  const arm = (ax: number, ay: number, bx: number, by: number, sd: number) => {
    const dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L; const bend = sd > 0 ? 14 : -14;
    return <Ink key={'a' + sd} pts={[[ax + nx * 44, ay + ny * 44], [(ax + bx) / 2 + nx * 42 + bend, (ay + by) / 2 + ny * 42], [bx + nx * 36, by + ny * 36], [bx - nx * 36, by - ny * 36], [(ax + bx) / 2 - nx * 42 + bend, (ay + by) / 2 - ny * 42], [ax - nx * 44, ay - ny * 44]]} fill={F(C.hood)} stroke={K} sw={7} seed={sd + 50} amp={2} />;
  };
  const hand = (hx: number, hy: number, rot: number, sc: number, sd: number) => (
    <g key={'h' + sd} transform={'translate(' + hx + ',' + hy + ') rotate(' + rot + ') scale(' + sc + ')'}>
      {[0, 1, 2, 3].map((k) => <Ink key={k} pts={ell((k - 1.5) * 21, -44 - (k === 1 || k === 2 ? 8 : 0), 10.5, 27, 7)} fill={F(C.skin)} stroke={K} sw={5} seed={sd + k + 1} amp={1} />)}
      <Ink pts={ell(0, 0, 40, 36, 9)} fill={F(C.skin)} stroke={K} sw={5} seed={sd} amp={1.2} />
      <Ink pts={ell(-46, -6, 12, 26, 7, -0.7)} fill={F(C.skin)} stroke={K} sw={5} seed={sd + 9} amp={1} />
    </g>
  );
  let hp: number[][] = [];
  if (hands === 'ears') hp = [[-172, -190, -8], [172, -190, 8]];
  else if (hands === 'mouth') hp = [[22, -108, 0], [-70, 160, 10]];
  else if (hands === 'phone') hp = phoneAt || [[-100, 178, -12], [100, 178, 12]];
  else if (hands === 'hug') hp = [[-80, 190, -70], [80, 190, 70]];
  const sd = -litDir || 1;

  return (
    <g transform={'translate(' + (x + ox) + ',' + (y + oy) + ') scale(' + s + ',' + s * br + ')'}>
      <Ink pts={[[-270, 440], [-275, 170], [-225, 40], [-120, -22], [0, -34], [120, -22], [225, 40], [275, 170], [270, 440]]} fill={F(C.hood)} stroke={K} sw={7} seed={seed + 1} amp={2.5} />
      <Ink pts={ell(0, -28, 118, 36, 10)} fill={F(C.hoodDk)} stroke={K} sw={6} seed={seed + 2} amp={1.5} />
      {!tint && <Ink pts={[[-30, -6], [-34, 80]]} closed={false} smooth={false} stroke={C.hoodDk} sw={6} seed={seed + 3} amp={1} />}
      {!tint && <Ink pts={[[30, -6], [34, 90]]} closed={false} smooth={false} stroke={C.hoodDk} sw={6} seed={seed + 4} amp={1} />}
      {hands !== 'none' && hands !== 'ears' && hp.map((h, k) => arm(k ? 215 : -215, 40, h[0] * 0.8 + (k ? 40 : -40) * 0.2, h[1] + 36, k ? 1 : -1))}
      {hands === 'ears' && hp.map((h, k) => arm(k ? 215 : -215, 40, h[0], h[1] + 70, k ? 1 : -1))}
      <Ink pts={box(-46, -96, 92, 80)} fill={F(C.skinSh)} stroke={K} sw={6} seed={seed + 5} amp={1.5} />
      <g transform={'rotate(' + tilt + ' 0 -50)'}>
        <Ink pts={ell(0, -218, 132, 148, 12)} fill={F(C.hair)} stroke={K} sw={7} seed={seed + 6} amp={2} />
        <Ink pts={ell(-112, -195, 20, 32, 8)} fill={F(C.skinSh)} stroke={K} sw={5} seed={seed + 7} amp={1} />
        <Ink pts={ell(112, -195, 20, 32, 8)} fill={F(C.skinSh)} stroke={K} sw={5} seed={seed + 8} amp={1} />
        <Ink pts={ell(0, -200, 112, 132, 12)} fill={F(C.skin)} stroke={K} sw={7} seed={seed + 9} amp={1.8} />
        {!tint && <Ink pts={[[sd * 78, -318], [sd * 116, -230], [sd * 108, -120], [sd * 62, -76], [sd * 92, -170], [sd * 96, -250]]} fill={C.skinSh} stroke="none" op={0.6} seed={seed + 12} amp={1.5} />}
        {!tint && lit > 0 && <Ink pts={ell(0, -148, 100, 80, 10)} fill={C.yel} stroke="none" op={0.3 * lit} blend="screen" seed={seed + 13} amp={1} />}
        {!tint && lit > 0 && <Ink pts={[[litDir * 110, -270], [litDir * 118, -200], [litDir * 104, -130]]} closed={false} stroke={C.yel} sw={6} op={0.55 * lit} seed={seed + 14} amp={1} />}
        {!tint && eye(-1)}{!tint && eye(1)}{!tint && brow(-1)}{!tint && brow(1)}
        {tint && <g />}
        {!tint && <Ink pts={[[-4, -196], [-12, -160], [6, -155]]} closed={false} stroke={C.skinDk} sw={5} seed={seed + 15} amp={0.8} />}
        {!tint && mouthEl}
        {!tint && tears > 0 && [-1, 1].map((q) => <Ink key={'t' + q} pts={[[q * 46, -168], [q * 52, -168 + 40 * tears], [q * 50, -168 + 80 * tears]]} closed={false} stroke="#9fb3c8" sw={5} op={0.7} seed={seed + 16 + q} amp={1} />)}
        {!tint && fear > 0.45 && [0, 1, 2].map((k) => { const ph = (t * 0.35 + k * 0.37 + seed * 0.1) % 1; const dx = [-86, 92, -60][k], dy = -300 + ph * 150;
          return <Ink key={'s' + k} pts={[[dx, dy - 14], [dx + 8, dy + 4], [dx, dy + 12], [dx - 8, dy + 4]]} fill="#aab8c8" stroke="none" op={0.6 * (1 - ph) * clamp((fear - 0.4) * 3)} seed={k} amp={0.5} />; })}
        <Ink pts={[[-118, -215], [-100, -310], [-40, -345], [40, -345], [105, -300], [118, -215], [80, -262], [30, -272], [-20, -288], [-70, -255]]} fill={F(C.hair)} stroke={K} sw={6} seed={seed + 17} amp={2} />
      </g>
      {children}
      {hp.map((h, k) => hand(h[0], h[1], h[2], hands === 'mouth' && k === 0 ? 1.25 : 1, k * 7 + 3))}
    </g>
  );
};
'''
FILES["src/shots.tsx"] = r'''import React from 'react';
import { A, C, Ink, Glow, Dark, Dust, Shadow, PhoneUI, Character, useFx, clamp, lerp, ease, hash, noise, ell, box, P } from './lib';

const lines = (n: number, f: (k: number) => any) => { const o: any[] = []; for (let k = 0; k < n; k++) o.push(f(k)); return o; };

// ============================================================ bedroom (scenes 0-2)
export const Bed: React.FC<any> = ({ cfg }) => {
  const { t, f, p, i, env, pulse, within, since } = useFx();
  const off = since('lampoff') >= 0;
  const lamp = off ? clamp(1 - since('lampoff') * 9) : (0.82 + 0.18 * noise(f * 0.3, 3)) * (1 - 0.4 * pulse('alert', 0.5) * Math.abs(Math.sin(t * 13)));
  const sleep = i === 0 ? clamp(1 - (t - 0.8) * 3) : 0;
  const fear = lerp(cfg.fear[0], cfg.fear[1], p) + env * 0.1;
  const screenOn = i >= 1 || within('alert') > 0;
  const glow = (off ? 1 : 0.65) * (screenOn ? 0.7 + 0.3 * (Math.floor(t * 5) % 2) : 0.08);
  const chr = (props: any) => <Character x={540} y={1130} s={1.45} fear={fear} look={[0, 0.7]} mouth={fear > 0.6 ? 'tremble' : 'flat'} hands="phone" phoneAt={[[-70, 185, -10], [70, 185, 10]]} sleep={sleep} tilt={sleep * 6} lit={0.5 + glow * 0.4} litDir={-1} {...props}>
    <PhoneUI x={0} y={95} w={150} h={270} mode={screenOn ? 'alert' : 'dark'} />
  </Character>;
  return (<g>
    <rect width="1080" height="1500" fill={C.n1} />
    {lines(10, (k) => <Ink key={k} pts={[[k * 120 + 20, 0], [k * 120 + 22, 1180]]} closed={false} smooth={false} stroke={C.n2} sw={26} op={0.28} amp={1.5} seed={k} />)}
    <rect y="1170" width="1080" height="340" fill={C.b0} />
    <Ink pts={box(0, 1160, 1080, 26)} smooth={false} fill={C.b1} sw={4} seed={3} amp={1} />
    {lines(6, (k) => <Ink key={'p' + k} pts={box(30 + k * 180, 1215, 150, 240)} smooth={false} fill="none" stroke={C.b1} sw={5} seed={k + 5} amp={1.5} />)}
    <rect y="1500" width="1080" height="420" fill="#1a120c" />
    {lines(7, (k) => <Ink key={'f' + k} pts={[[0, 1540 + k * 58], [1080, 1544 + k * 58]]} closed={false} smooth={false} stroke={C.b0} sw={4} op={0.7} amp={2} seed={k + 20} />)}
    {/* window with drawn curtains */}
    <Ink pts={box(70, 250, 290, 580)} smooth={false} fill="#1b2f58" stroke={C.b2} sw={22} seed={30} amp={1.5} />
    <Ink pts={[[78, 256], [210, 256], [214, 600], [190, 830], [78, 830]]} fill={C.b1} sw={6} seed={31} amp={2} />
    <Ink pts={[[352, 256], [222, 256], [216, 600], [240, 830], [352, 830]]} fill={C.b1} sw={6} seed={32} amp={2} />
    {lines(5, (k) => <Ink key={'c' + k} pts={[[100 + k * 28, 270], [104 + k * 28, 800]]} closed={false} stroke={C.b0} sw={5} op={0.7} seed={k + 33} amp={2} />)}
    {/* wardrobe */}
    <Shadow dx={90} dy={0} sk={-8} sc={1.0} op={0.35} ox={900} oy={1500}><rect x={780} y={380} width={260} height={1120} fill="#000" /></Shadow>
    <Ink pts={box(780, 380, 270, 1120)} smooth={false} fill={C.b1} stroke={C.ink} sw={8} seed={40} amp={2} />
    <Ink pts={box(770, 350, 290, 44)} smooth={false} fill={C.b2} sw={7} seed={41} amp={1.5} />
    <Ink pts={box(800, 430, 105, 980)} smooth={false} fill="none" stroke={C.b0} sw={7} seed={42} amp={2} />
    <Ink pts={box(925, 430, 105, 980)} smooth={false} fill="none" stroke={C.b0} sw={7} seed={43} amp={2} />
    <circle cx={905} cy={900} r={12} fill={C.yel2} /><circle cx={925} cy={900} r={12} fill={C.yel2} />
    {/* pictures */}
    <g transform="rotate(-3 550 450)"><Ink pts={box(450, 350, 190, 200)} smooth={false} fill={C.n0} stroke={C.b2} sw={14} seed={44} amp={1.5} />
      <Ink pts={[[460, 530], [520, 450], [560, 500], [600, 430], [632, 530]]} fill={C.n2} stroke="none" seed={45} /></g>
    {/* bed */}
    <Ink pts={[[200, 1500], [200, 980], [330, 870], [540, 840], [750, 870], [880, 980], [880, 1500]]} fill={C.b2} stroke={C.ink} sw={9} seed={46} amp={2} />
    <Ink pts={ell(380, 1050, 150, 90, 10)} fill="#7a766c" sw={7} seed={47} amp={2} />
    <Ink pts={ell(700, 1050, 150, 90, 10)} fill="#7a766c" sw={7} seed={48} amp={2} />
    {/* long shadow of the character thrown by the lamp */}
    <Shadow dx={330} dy={-120} sk={-22} sc={1.25} op={0.45} ox={540} oy={1300}>{chr({ tint: '#02040a', hands: 'none', children: null })}</Shadow>
    {chr({})}
    {/* blanket */}
    <Ink pts={[[100, 1470], [300, 1440], [540, 1460], [780, 1440], [980, 1470], [1080, 1560], [1080, 1920], [0, 1920], [0, 1560]]} fill={C.b1} stroke={C.ink} sw={9} seed={49} amp={3} />
    {lines(5, (k) => <Ink key={'w' + k} pts={[[120 + k * 200, 1560], [150 + k * 200, 1740], [110 + k * 200, 1900]]} closed={false} stroke={C.b0} sw={6} op={0.8} seed={k + 50} amp={3} />)}
    {/* night lamp + table */}
    <Ink pts={box(60, 1250, 230, 300)} smooth={false} fill={C.b1} stroke={C.ink} sw={8} seed={60} amp={2} />
    <Ink pts={box(80, 1330, 190, 90)} smooth={false} fill={C.b2} stroke={C.ink} sw={6} seed={61} amp={1.5} />
    <Ink pts={[[178, 1250], [182, 1140]]} closed={false} stroke={C.ink} sw={10} seed={62} amp={1} />
    <Ink pts={[[112, 1050], [250, 1050], [292, 1175], [70, 1175]]} fill={off ? '#2a2318' : C.yel} stroke={C.ink} sw={7} op={1} seed={63} amp={1.5} />
    <Dark x={540} y={1150} r={1450} a={0.82 - env * 0.05} />
    <Glow id="g1" x={180} y={1130} r={900} a={0.6 * lamp} />
    <Glow id="g2" x={540} y={1380} r={560} a={0.5 * glow} color="225,232,255" />
    <Dust n={34} x0={150} y0={700} w={700} h={800} a={0.5 * (0.3 + lamp)} seed={3} />
  </g>);
};

// ============================================================ close-up face (scenes 3,5,6,12,14)
export const Face: React.FC<any> = ({ cfg }) => {
  const { t, f, p, env, pulse } = useFx();
  const fear = clamp(lerp(cfg.fear[0], cfg.fear[1], p) + env * 0.12);
  const mouth = p < (cfg.sw || 0.5) ? cfg.mouth : (cfg.mouth2 || cfg.mouth);
  const glow = 0.8 + 0.2 * noise(f * 0.25, 2);
  const hands = cfg.hands === 'mouthLate' ? (p > 0.82 ? 'mouth' : 'none') : cfg.hands;
  const ch = (props: any) => <Character x={540} y={1180} s={2.7} fear={fear} look={cfg.look(p, t)} mouth={mouth} hands={hands} phoneAt={[[-110, 235, -10], [110, 235, 10]]} lit={cfg.lit} litDir={cfg.litDir || 0} tears={cfg.tears ? clamp((p - 0.3) * 2) : 0} tilt={cfg.tilt || 0} {...props}>
    {cfg.phone && <PhoneUI x={0} y={60} w={190} h={330} mode={cfg.phone} />}
  </Character>;
  return (<g>
    <rect width="1080" height="1920" fill={C.n1} />
    {lines(7, (k) => <Ink key={k} pts={box(k * 165 - 20, -20, 150, 1960)} smooth={false} fill={C.b0} stroke={C.n0} sw={6} op={0.8} seed={k} amp={2} />)}
    <Shadow dx={260} dy={-260} sk={-8} sc={1.5} op={0.6} ox={540} oy={1180}>{ch({ tint: '#02040a', hands: 'none', children: null })}</Shadow>
    {ch({})}
    <Dark x={540} y={900} r={1350} a={0.86 - env * 0.06} inner={0.2} />
    <Glow id="g3" x={540} y={cfg.phone ? 1500 : 1650} r={900} a={0.5 * glow * (cfg.phone ? 1 : 0.6)} color={cfg.phone ? '232,236,255' : '242,227,160'} />
    <Dust n={26} x0={0} y0={200} w={1080} h={1400} a={0.35} seed={5} />
  </g>);
};

// ============================================================ bathroom (scenes 4, 13)
export const Bath: React.FC<any> = ({ cfg }) => {
  const { t, f, p, env, pulse, within } = useFx();
  const enter = cfg.mode === 'enter';
  const fear = clamp(lerp(cfg.fear[0], cfg.fear[1], p) + env * 0.12);
  const walk = enter ? ease(clamp(p / 0.38)) : 1;
  const cx = enter ? lerp(1350, 540, walk) : 540;
  const crouch = enter ? ease(clamp((p - 0.36) / 0.2)) : 1;
  const bob = enter && p < 0.38 ? Math.abs(Math.sin(t * 7)) * 22 : 0;
  const cy = lerp(1010, 1250, crouch) - bob;
  const beam = 0.55 + 0.2 * noise(f * 0.2, 6) + 0.1 * env;
  const doorX = enter ? lerp(1080, 880, clamp((p - 0.76) / 0.05)) : 1080;
  const crack = cfg.mode === 'shake' ? clamp((p - 0.2) * 1.6) : 0;
  const ch = (props: any) => <Character x={cx} y={cy} s={1.55} fear={fear} look={[-0.6, 0.2]} mouth={fear > 0.7 ? 'tremble' : 'flat'} hands={cfg.hands} lit={0.7} litDir={1} {...props}>
    {cfg.hands === 'hug' && <Ink pts={ell(0, 175, 165, 100, 10)} fill="#8f8b7d" sw={7} seed={77} amp={2} />}
  </Character>;
  return (<g>
    <rect width="1080" height="1500" fill="#13244a" />
    {lines(9, (k) => <Ink key={'v' + k} pts={[[k * 135, 0], [k * 135 + 2, 1500]]} closed={false} smooth={false} stroke={C.n1} sw={4} amp={1.5} seed={k} />)}
    {lines(12, (k) => <Ink key={'h' + k} pts={[[0, k * 130], [1080, k * 130 + 2]]} closed={false} smooth={false} stroke={C.n1} sw={4} amp={1.5} seed={k + 20} />)}
    <rect y="1500" width="1080" height="420" fill={C.b0} />
    {lines(8, (k) => <Ink key={'t' + k} pts={[[k * 150, 1500], [k * 150 - 60 + (k - 4) * 10, 1920]]} closed={false} smooth={false} stroke={C.n0} sw={5} op={0.6} amp={2} seed={k + 40} />)}
    <Ink pts={box(560, 1170, 520, 330)} fill="#6e7890" sw={8} seed={51} amp={2} />
    <Ink pts={box(560, 1150, 520, 40)} smooth={false} fill="#8d95a8" sw={6} seed={52} amp={1} />
    <Ink pts={box(30, 980, 260, 40)} fill="#8d95a8" sw={7} seed={53} amp={1.5} />
    <Ink pts={box(80, 1020, 150, 480)} fill="#7a8398" sw={7} seed={54} amp={2} />
    <Ink pts={box(50, 520, 220, 330)} smooth={false} fill="#0a1228" stroke={C.b2} sw={12} seed={55} amp={1.5} />
    {enter && p > 0.7 && <g opacity={0.5 + 0.4 * Math.sin(t * 3)}><circle cx={140} cy={640} r={7} fill={C.yel} /><circle cx={180} cy={640} r={7} fill={C.yel} /></g>}
    {cfg.mode === 'shake' && <g opacity={crack}><Ink pts={[[700, 0], [640, 160], [700, 300], [610, 470], [660, 620], [590, 780]]} closed={false} smooth={false} stroke={C.ink} sw={7} amp={1.5} seed={71} />
      <Ink pts={[[640, 160], [560, 230], [520, 330]]} closed={false} smooth={false} stroke={C.ink} sw={5} amp={1.5} seed={72} /></g>}
    {/* torch on the floor: cone of pale light */}
    <defs><linearGradient id="tc" gradientUnits="userSpaceOnUse" x1="820" y1="1600" x2="250" y2="1000"><stop offset="0" stopColor={C.yel} stopOpacity={0.7 * beam} /><stop offset="1" stopColor={C.yel} stopOpacity={0} /></linearGradient></defs>
    <g filter="url(#bl18)" style={{ mixBlendMode: 'screen' }}><path d="M820,1600 L110,1050 L380,1480 Z" fill="url(#tc)" /></g>
    <Ink pts={box(790, 1570, 110, 44)} fill={C.b3} sw={6} seed={73} amp={1} />
    <Shadow dx={-420} dy={80} sk={22} sc={1.5} op={0.5} ox={cx} oy={1500}>{ch({ tint: '#02040a', hands: 'none', children: null })}</Shadow>
    {ch({})}
    {enter && <Ink pts={box(doorX, 0, 1080 - doorX + 20, 1500)} smooth={false} fill={C.b1} stroke={C.ink} sw={8} seed={74} amp={1.5} />}
    <Dark x={540} y={1150} r={1250} a={0.84 - env * 0.05} />
    <Glow id="g4" x={800} y={1590} r={640} a={0.55 * beam} />
    <Dust n={cfg.mode === 'shake' ? 70 : 26} a={cfg.mode === 'shake' ? 0.7 : 0.4} color={cfg.mode === 'shake' ? '#9aa0ae' : C.yel} vy={cfg.mode === 'shake' ? 150 : -12} seed={9} op={cfg.mode === 'shake' ? 0.4 + within('rumble') : 1} />
  </g>);
};

// ============================================================ the wall clock (scene 7)
export const ClockShot: React.FC<any> = ({ cfg }) => {
  const { t, f, p, env } = useFx();
  const fear = lerp(cfg.fear[0], cfg.fear[1], p) + env * 0.1;
  const min = ease(p) * 120, hr = 300 + ease(p) * 10, sec = ease(p) * 360 * 28;
  const R = 330, cx = 540, cy = 800;
  const hand = (ang: number, len: number, tail: number, w: number, col: string, sd: number) => {
    const a = (ang - 90) * Math.PI / 180, ca = Math.cos(a), sa = Math.sin(a);
    return <Ink key={sd} pts={[[cx - ca * tail, cy - sa * tail], [cx + ca * len, cy + sa * len]]} closed={false} smooth={false} stroke={col} sw={w} amp={0.8} seed={sd} />;
  };
  const phoneFlash = p > 0.9 ? Math.floor(t * 12) % 2 : 0;
  return (<g>
    <rect width="1080" height="1920" fill={C.n1} />
    {lines(8, (k) => <Ink key={k} pts={[[k * 150, 0], [k * 150 + 3, 1500]]} closed={false} smooth={false} stroke={C.n2} sw={22} op={0.25} amp={1.5} seed={k} />)}
    <rect y="1500" width="1080" height="420" fill="#1a120c" />
    <Shadow dx={170} dy={90} sk={-12} sc={1.04} op={0.5} ox={cx} oy={cy}><Ink pts={ell(cx, cy, R + 24, R + 24, 18)} fill="#000" stroke="none" seed={8} /></Shadow>
    <Ink pts={ell(cx, cy, R + 26, R + 26, 18)} fill={C.b2} sw={9} seed={80} amp={2.5} />
    <Ink pts={ell(cx, cy, R, R, 18)} fill="#c9c0a0" sw={7} seed={81} amp={1.8} />
    {lines(12, (k) => { const a = k * Math.PI / 6; const big = k % 3 === 0; return <Ink key={'k' + k} pts={[[cx + Math.sin(a) * R * (big ? 0.78 : 0.85), cy - Math.cos(a) * R * (big ? 0.78 : 0.85)], [cx + Math.sin(a) * R * 0.93, cy - Math.cos(a) * R * 0.93]]} closed={false} smooth={false} stroke={C.ink} sw={big ? 12 : 6} amp={1} seed={k + 82} />; })}
    {hand(hr, 170, 30, 18, C.ink, 90)}{hand(min, 255, 36, 13, C.ink, 91)}{hand(sec, 285, 50, 5, '#8a3d36', 92)}
    <circle cx={cx} cy={cy} r={16} fill={C.ink} />
    <Ink pts={[[cx - 230, cy - 170], [cx - 150, cy - 250], [cx - 60, cy - 285]]} closed={false} stroke="#fff" sw={7} op={0.14} amp={1} seed={95} />
    <Character x={230} y={1640} s={1.0} fear={fear} look={[0.3, -0.9]} mouth="tremble" hands="hug" lit={0.4} litDir={1} seed={3}>
      <Ink pts={ell(0, 175, 165, 100, 10)} fill="#8f8b7d" sw={7} seed={96} amp={2} />
    </Character>
    <Dark x={540} y={800} r={1250} a={0.82 - env * 0.05} inner={0.3} />
    <Glow id="g5" x={160} y={300} r={900} a={0.3 + 0.05 * noise(f * 0.2, 4)} />
    <Glow id="g6" x={230} y={1500} r={380} a={0.35} />
    {phoneFlash > 0 && <g><Ink pts={box(760, 1680, 110, 170)} fill="#e8dc98" sw={5} seed={97} /><Glow id="g7" x={815} y={1740} r={460} a={0.7} color="232,236,255" /></g>}
    <Dust n={30} a={0.4} seed={7} />
  </g>);
};

// ============================================================ the door (scenes 8, 9, 14b, 15)
export const DoorShot: React.FC<any> = ({ cfg }) => {
  const { t, f, p, env, pulse } = useFx();
  const fear = clamp(lerp(cfg.fear[0], cfg.fear[1], p) + env * 0.1);
  const kn = pulse('knock', 0.1), rat = pulse('rattle', 0.25);
  const jx = noise(f * 2.1, 1) * 10 * kn + noise(f * 3, 2) * 3 * rat, jy = noise(f * 2.3, 3) * 5 * kn;
  const lightA = 0.75 + 0.25 * noise(f * 0.2, 4);
  const watched = cfg.watch && p > 0.55;
  const legs: any[] = [];
  const nL = cfg.mode === 'human' ? 2 : cfg.legs;
  for (let k = 0; k < nL; k++) {
    const human = cfg.mode === 'human';
    const px = human ? 450 + k * 140 + noise(t * 0.5, k) * 6 : 260 + k * (cfg.legs > 2 ? 150 : 260) + noise(t * 0.25 + k * 3, k) * 90 + (Math.floor(t * 0.7 + k) % 2) * 60;
    const w = human ? 62 : 22 + hash(k) * 14, tall = human ? 1 : 1.9;
    legs.push(<g key={k}>
      <Ink pts={[[px, 1472], [px + w, 1472], [px + w * (1.6 + tall * 0.6) + 20, 1760], [px - w * 0.5 + 20, 1760]]} fill={C.ink} stroke="none" op={0.55} amp={2} seed={k + 5} />
      <Ink pts={box(px, 1450, w, 22)} smooth={false} fill={C.ink} stroke="none" amp={1} seed={k + 9} />
    </g>);
  }
  const ch = (props: any) => <Character x={540} y={1990} s={1.3} fear={fear} look={[0, -0.9]} mouth={fear > 0.8 ? 'tremble' : 'flat'} hands={cfg.hands} lit={0.5} litDir={0} seed={4} tears={cfg.tears ? 0.8 : 0} {...props} />;
  return (<g>
    <rect width="1080" height="1920" fill={C.n1} />
    <g transform={'translate(' + jx + ',' + jy + ')'}>
      <Ink pts={box(150, 120, 780, 1350)} smooth={false} fill={C.b0} stroke={C.ink} sw={9} seed={100} amp={2} />
      <Ink pts={box(190, 160, 700, 1290)} smooth={false} fill={C.b1} stroke={C.ink} sw={8} seed={101} amp={2} />
      {[0, 1].map((c) => [0, 1, 2].map((r) => <g key={c + '-' + r}>
        <Ink pts={box(250 + c * 360, [230, 650, 1070][r], 220, [340, 340, 320][r])} smooth={false} fill={C.b0} stroke={C.ink} sw={6} seed={c * 3 + r + 110} amp={1.8} />
        <Ink pts={[[250 + c * 360, [230, 650, 1070][r] + 340], [250 + c * 360, [230, 650, 1070][r]], [470 + c * 360, [230, 650, 1070][r]]]} closed={false} smooth={false} stroke={C.b3} sw={4} op={0.5} seed={c * 3 + r + 120} amp={1} />
      </g>))}
      {lines(9, (k) => <Ink key={'g' + k} pts={[[205 + k * 77, 170], [210 + k * 77, 1440]]} closed={false} stroke={C.b0} sw={3} op={0.5} seed={k + 130} amp={2} />)}
      <circle cx={540} cy={605} r={26} fill={C.yel2} stroke={C.ink} strokeWidth={5} />
      <circle cx={540} cy={605} r={15} fill={watched ? '#050505' : C.yel} opacity={watched ? 1 : 0.4 + 0.3 * noise(f * 0.2, 2)} />
      {watched && <ellipse cx={540} cy={605} rx={6} ry={9} fill="#cfd6c0" opacity={0.5 + 0.4 * Math.sin(t * 2)} />}
      <circle cx={800} cy={760} r={28} fill={C.yel2} stroke={C.ink} strokeWidth={5} /><rect x={796} y={752} width={8} height={22} fill={C.ink} />
      <g transform={'rotate(' + rat * 28 + ' 800 920)'}><Ink pts={ell(800, 920, 36, 36, 9)} fill={C.yel2} sw={6} seed={140} amp={1} /><circle cx={790} cy={910} r={9} fill="#f4ecc0" opacity={0.6} /></g>
      <Ink pts={[[870, 430], [900, 470], [930, 430]]} closed={false} stroke={C.yel2} sw={5} seed={141} amp={1} />
    </g>
    <rect x={190} y={1450} width={700} height={22} fill={C.yel} opacity={lightA} />
    <rect y="1472" width="1080" height="448" fill="#1a120c" />
    <g filter="url(#bl18)" style={{ mixBlendMode: 'screen' }}><path d="M190,1472 L890,1472 L1060,1780 L20,1780 Z" fill={C.yel} opacity={0.35 * lightA} /></g>
    {legs}
    {ch({})}
    <Dark x={540} y={1100} r={1350} a={0.87 - env * 0.05} inner={0.3} />
    <Glow id="g8" x={540} y={1470} r={760} sy={0.55} a={0.55 * lightA} />
    <Dust n={40} x0={150} y0={0} w={780} h={1450} a={0.5} vy={30} seed={11} op={0.2 + kn * 2} />
  </g>);
};

// ============================================================ curtained window (scenes 10, 11)
export const WindowShot: React.FC<any> = ({ cfg }) => {
  const { t, f, p, env, pulse, within } = useFx();
  const fear = clamp(lerp(cfg.fear[0], cfg.fear[1], p) + env * 0.12);
  const sirenOn = within('siren') > 0 ? 1 : 0;
  const beat = 0.5 + 0.5 * Math.sin(t * Math.PI * 2 / 2.2);
  const alarm = within('caralarm') > 0 ? (Math.floor(t * 5) % 2) : 0;
  const lightOut = clamp(0.22 + 0.35 * beat * sirenOn + 0.4 * alarm * 0.7 + 0.9 * pulse('crash', 0.18));
  const figs: any[] = [];
  for (let k = 0; k < cfg.figs; k++) {
    const stop = cfg.stop && p > 0.62 && k === 0;
    const x = stop ? lerp(300 + ((t * 18) % 600), 540, ease((p - 0.62) / 0.1)) : 240 + (((t * 16 + k * 330) % 720));
    const hx = stop ? noise(t * 0.7, 3) * 30 : Math.sin(t * 1.3 + k) * 10;
    figs.push(<g key={k} transform={'translate(' + x + ',1260)'} opacity={0.62}>
      <Ink pts={[[-12, 0], [12, 0], [8, -560], [-8, -560]]} fill="#04040a" stroke="none" amp={2} seed={k + 150} />
      <Ink pts={ell(hx, -640, 36, 62, 8, 0.2)} fill="#04040a" stroke="none" amp={2} seed={k + 160} />
      <Ink pts={[[-6, -520], [-110, -250], [-120, -40]]} closed={false} stroke="#04040a" sw={11} amp={3} seed={k + 170} />
      <Ink pts={[[6, -520], [100, -260], [130, -50]]} closed={false} stroke="#04040a" sw={11} amp={3} seed={k + 180} />
    </g>);
  }
  return (<g>
    <rect width="1080" height="1920" fill={C.n1} />
    {lines(8, (k) => <Ink key={k} pts={[[k * 150, 0], [k * 150 + 3, 1340]]} closed={false} smooth={false} stroke={C.n2} sw={22} op={0.25} amp={1.5} seed={k} />)}
    <rect y="1340" width="1080" height="580" fill="#1a120c" />
    <Ink pts={box(150, 190, 780, 1110)} smooth={false} fill="#2a2118" stroke={C.b2} sw={30} seed={200} amp={2} />
    <Ink pts={box(180, 220, 720, 1050)} smooth={false} fill="#34291d" stroke="none" seed={201} amp={2} />
    <rect x={180} y={220} width={720} height={1050} fill={C.yel} opacity={lightOut * 0.55} style={{ mixBlendMode: 'screen' }} />
    <g filter="url(#bl8)"><g clipPath="url(#win)">{figs}</g></g>
    <defs><clipPath id="win"><rect x={180} y={220} width={720} height={1050} /></clipPath></defs>
    {lines(14, (k) => <Ink key={'c' + k} pts={[[205 + k * 50, 230], [212 + k * 50, 760], [205 + k * 50, 1260]]} closed={false} stroke={C.b0} sw={5} op={0.65} amp={2.5} seed={k + 210} />)}
    {lines(14, (k) => <Ink key={'l' + k} pts={[[225 + k * 50, 230], [232 + k * 50, 760], [225 + k * 50, 1260]]} closed={false} stroke={C.yel} sw={3} op={lightOut * 0.35} amp={2.5} seed={k + 230} />)}
    <Ink pts={box(110, 1290, 860, 50)} smooth={false} fill={C.b2} stroke={C.ink} sw={7} seed={250} amp={1.5} />
    {sirenOn > 0 && lines(3, (k) => { const ph = (t / 2.2 + k / 3) % 1; return <Ink key={'r' + k} pts={ell(540, 740, 220 + ph * 900, 220 + ph * 900, 26)} stroke={C.yel} sw={5} op={0.35 * (1 - ph)} amp={4} seed={k + 260} />; })}
    <g filter="url(#bl18)" style={{ mixBlendMode: 'screen' }}><path d="M180,1340 L900,1340 L1080,1920 L0,1920 Z" fill={C.yel} opacity={lightOut * 0.22} /></g>
    <Ink pts={[[535, 1340], [545, 1340], [620, 1920], [470, 1920]]} fill={C.ink} stroke="none" op={0.4} seed={270} amp={2} />
    <Ink pts={[[180, 1520], [900, 1560], [900, 1620], [180, 1580]]} fill={C.ink} stroke="none" op={0.3} seed={271} amp={2} />
    <Character x={250} y={1740} s={1.0} fear={fear} look={[0.7, -0.6]} mouth="tremble" hands="hug" lit={0.5 * lightOut} litDir={1} seed={5}>
      <Ink pts={ell(0, 175, 165, 100, 10)} fill="#8f8b7d" sw={7} seed={96} amp={2} />
    </Character>
    <Dark x={540} y={800} r={1300} a={0.86 - env * 0.05 - lightOut * 0.25} inner={0.3} />
    <Glow id="g9" x={540} y={760} r={640} a={0.5 * lightOut} />
    <Dust n={30} a={0.4} seed={13} />
  </g>);
};
'''
FILES["src/scenes.ts"] = r'''// one entry per scene (same order as SCENES in make_video.py)
const look = (x: number, y: number) => () => [x, y];
export const SC: any[] = [
  { shot: 'bed', z: [1.04, 1.12], o: [540, 880], shake: 0.4, fear: [0.1, 0.3] },
  { shot: 'bed', z: [1.12, 1.22], o: [540, 880], shake: 0.7, fear: [0.4, 0.65] },
  { shot: 'bed', z: [1.22, 1.36], o: [540, 880], shake: 0.9, fear: [0.65, 0.8] },
  { shot: 'face', z: [1.04, 1.14], o: [540, 650], shake: 0.4, fear: [0.45, 0.55], phone: 'alert', hands: 'phone', lit: 0.7, mouth: 'flat', mouth2: 'frown', look: (p: number, t: number) => [Math.sin(t * 0.8) * 0.2, 0.8] },
  { shot: 'bath', mode: 'enter', hands: 'hug', z: [1.04, 1.14], o: [540, 1000], shake: 0.8, fear: [0.5, 0.65] },
  { shot: 'face', z: [1.06, 1.18], o: [540, 650], shake: 0.4, fear: [0.5, 0.65], phone: 'chat', hands: 'phone', lit: 0.8, mouth: 'flat', mouth2: 'frown', look: (p: number) => [0, 0.8] },
  { shot: 'face', z: [1.18, 1.32], o: [540, 650], shake: 0.6, fear: [0.65, 0.88], phone: 'chat2', hands: 'phone', lit: 0.8, mouth: 'frown', mouth2: 'tremble', tears: true, look: (p: number, t: number) => [Math.sin(t * 2) * 0.3, 0.7] },
  { shot: 'clock', z: [1.04, 1.18], o: [540, 800], shake: 0.5, fear: [0.6, 0.8] },
  { shot: 'door', legs: 2, hands: 'mouth', z: [1.04, 1.14], o: [540, 1200], shake: 0.7, fear: [0.8, 0.92] },
  { shot: 'door', legs: 4, watch: true, hands: 'mouth', tears: true, z: [1.14, 1.28], o: [540, 1300], shake: 0.8, fear: [0.9, 1.0] },
  { shot: 'window', figs: 2, z: [1.04, 1.16], o: [540, 800], shake: 1.4, fear: [0.9, 1.0] },
  { shot: 'window', figs: 3, stop: true, z: [1.16, 1.3], o: [540, 800], shake: 1.6, fear: [0.95, 1.0] },
  { shot: 'face', z: [1.06, 1.2], o: [540, 650], shake: 0.9, fear: [0.8, 0.95], phone: 'empty', hands: 'phone', lit: 0.8, mouth: 'tremble', tears: true, look: (p: number, t: number) => [Math.sin(t * 3) * 0.2, 0.7] },
  { shot: 'bath', mode: 'shake', hands: 'ears', z: [1.04, 1.2], o: [540, 1100], shake: 5, fear: [0.95, 1.0] },
  { shot: 'face', z: [1.1, 1.3], o: [540, 640], shake: 0.9, fear: [0.85, 0.95], hands: 'mouthLate', lit: 0.6, litDir: -1, mouth: 'gasp', tears: true, look: (p: number) => [lerp0(-0.2, 1, p), 0] },
  { shot: 'door', mode: 'human', legs: 2, hands: 'mouth', tears: true, watch: true, z: [1.06, 1.3], o: [540, 1000], shake: 0.9, fear: [0.9, 1.0] },
];
function lerp0(a: number, b: number, t: number) { return a + (b - a) * Math.min(1, t * 3); }
'''
FILES["src/Main.tsx"] = r'''import React from 'react';
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from 'remotion';
import { A, Fx, makeFx, clamp, lerp, hash, noise } from './lib';
import { Bed, Face, Bath, ClockShot, DoorShot, WindowShot } from './shots';
import { SC } from './scenes';

const SHOTS: any = { bed: Bed, face: Face, bath: Bath, clock: ClockShot, door: DoorShot, window: WindowShot };

export const Main: React.FC = () => {
  const f = useCurrentFrame();
  const fx = makeFx(f);
  const cfg = SC[Math.min(fx.i, SC.length - 1)];
  const Shot = SHOTS[cfg.shot];
  const sh = (cfg.shake || 0) + 14 * fx.pulse('knock', 0.1) + 16 * fx.pulse('crash', 0.35) + 9 * fx.within('rumble') + 8 * fx.pulse('bang', 0.3);
  const z = lerp(cfg.z[0], cfg.z[1], fx.p) + 0.03 + 0.03 * fx.pulse('boom', 0.4) + 0.02 * fx.pulse('knock', 0.1);
  const px = noise(f * 0.012, 1) * 5 + noise(f * 1.9, 2) * sh * 0.9;
  const py = noise(f * 0.011, 3) * 5 + noise(f * 1.9, 4) * sh * 0.9;
  const rot = noise(f * 1.3, 5) * sh * 0.04;
  const last = fx.i === SC.length - 1;
  const alpha = clamp(Math.min(fx.lf / (fx.i === 0 ? 30 : 9), (fx.len - fx.lf) / (last ? 150 : 7)));
  const grainX = Math.floor(hash(f) * 256), grainY = Math.floor(hash(f + 77) * 256);
  const pb = Math.floor(f / 5);
  return (
    <Fx.Provider value={fx}>
      <AbsoluteFill style={{ background: '#02040a' }}>
        <Img src={staticFile('grain.png')} style={{ display: 'none' }} />
        <Img src={staticFile('paper.png')} style={{ display: 'none' }} />
        <div style={{ position: 'absolute', inset: 0, opacity: alpha, transformOrigin: cfg.o[0] + 'px ' + cfg.o[1] + 'px', transform: 'translate(' + px + 'px,' + py + 'px) rotate(' + rot + 'deg) scale(' + z + ')' }}>
          <svg width={1080} height={1920} viewBox="0 0 1080 1920">
            <defs>
              <filter id="bl6"><feGaussianBlur stdDeviation="6" /></filter>
              <filter id="bl8"><feGaussianBlur stdDeviation="8" /></filter>
              <filter id="bl18"><feGaussianBlur stdDeviation="18" /></filter>
            </defs>
            <Shot cfg={cfg} />
          </svg>
        </div>
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 36%, rgba(2,4,10,0.74) 100%)' }} />
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'url(' + staticFile('paper.png') + ')', backgroundSize: '512px 512px', backgroundPosition: Math.floor(hash(pb) * 512) + 'px ' + Math.floor(hash(pb + 5) * 512) + 'px', mixBlendMode: 'soft-light', opacity: 0.35 }} />
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'url(' + staticFile('grain.png') + ')', backgroundPosition: grainX + 'px ' + grainY + 'px', mixBlendMode: 'overlay', opacity: 0.24 }} />
        <div style={{ position: 'absolute', inset: 0, background: '#000', opacity: 0.05 * (1 + noise(f * 0.6, 9)) }} />
      </AbsoluteFill>
    </Fx.Provider>
  );
};
'''

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped. Everything already rendered is saved - run the script again to resume.")
