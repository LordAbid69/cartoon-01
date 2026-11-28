#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Amar Poribar - audio-driven 2D hand-drawn horror animation (Remotion).
1080x1920 | 60 fps | resumable chunked render | audio-locked timeline.

    pip install rich
    (Node.js >= 18 required)  ->  python make_amar_poribar.py
    Options: --fresh (wipe render cache)   --stills (one preview PNG per scene, no video)
"""
import os, sys, json, math, time, shutil, hashlib, argparse, subprocess
from array import array
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import (Progress, SpinnerColumn, TextColumn, BarColumn,
                               TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn)
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import (Progress, SpinnerColumn, TextColumn, BarColumn,
                               TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ----------------------------------------------------------------------------- CONFIG
OUT_DIR = Path(r"C:\Users\laptop villa\Documents\cnd")
AUDIO_NAME = "Elevenlabs.mp3"
FINAL_NAME = "Amar_Poribar_1080x1920_60fps.mp4"
FPS, WIDTH, HEIGHT = 60, 1080, 1920
TAIL_SEC = 1.5          # eerie silence after the last word
HALF = 20               # half of the scene cross-dissolve, in frames
CHUNK_FRAMES = 600      # resume granularity (10 s)
CRF, JPEG_Q = 14, 97    # visual quality
TITLE_SPOKEN = True     # set False if the narration does not read the title
SR = 22050              # analysis sample rate
MIN_SIL = 0.20          # seconds of quiet that count as a pause
MIN_BEAT = 0.6          # minimum seconds per sentence

SCENES = [
    ("intro", ["আমার পরিবার", "আমি আট বছর আগে মারা গেছি।"]),
    ("road", ["ঘটনাটা তেমন মর্মান্তিক বা অস্বাভাবিক কিছু ছিল না।", "স্রেফ একটা সড়ক দুর্ঘটনা।",
              "যে লোকটা আমাকে ধাক্কা দিয়েছিল, তাকে আমি দোষ দিই না।",
              "তার স্ত্রীর প্রসবব্যথা উঠেছিল, তাই সে তাড়াহুড়ো করে গাড়ি চালাচ্ছিল।",
              "হঠাৎ গাড়ির নিয়ন্ত্রণ হারিয়ে ফেলে।", "আর সেই দুর্ঘটনাতেই আমার মৃত্যু হয়।"]),
    ("calm", ["এটা তার দোষ ছিল না।", "আমি জানি।", "আমি নিষ্ঠুর নই, প্রতিশোধ নেওয়ার ইচ্ছাও আমার নেই।"]),
    ("funeral", ["আসলে আমার কোনো পরিবার ছিল না।", "মৃত্যুর কিছুদিন আগেই হাতে গোনা কয়েকজন বন্ধুকেও হারিয়েছিলাম।",
                 "আমার জানাজায় শেষ পর্যন্ত মাত্র কয়েকজন মানুষ এসেছিল—আমার অফিসের বস আর সেই পরিবারটা, যাদের গাড়ির ধাক্কায় আমার মৃত্যু হয়েছিল।",
                 "মহিলাটির কোলে তখন তার সদ্যোজাত মেয়েটি।"]),
    ("follow", ["আমি আমার বসকে একদম সহ্য করতে পারতাম না।", "আর কবরস্থানে একা একা পড়ে থাকতেও ভালো লাগছিল না।",
                "তাই পরিবারটার পিছু নিয়ে তাদের বাসা পর্যন্ত চলে গেলাম।"]),
    ("nursery", ["ছোট্ট মায়াকে দেখে মনে হতো, সে যেন আমার নিজেরই মেয়ে।", "কী মিষ্টি আর হাসিখুশি ছিল!",
                 "রাতে কেউ দোলনা না দোলালে তার ঘুমই আসত না।", "ওর বাবা-মাও সারাদিনের পরিশ্রমে একেবারে ক্লান্ত থাকতেন।",
                 "তাই তারা ওকে ঘুম পাড়িয়ে চলে যাওয়ার পর আমি চুপচাপ দোলনাটা দুলিয়ে দিতাম।",
                 "আমার তো আর ক্লান্তি লাগত না।", "অন্তত ওর কাজে তো আসতে পারছিলাম।"]),
    ("aware", ["বছর গড়াতে লাগল।", "একসময় রায়হান আর নীলা বুঝতে পারল, তাদের বাসায় তারা ছাড়াও আরও কেউ আছে।",
               "আমার মৃত্যুর দিন আর আমার উপস্থিতির সময় মিলিয়ে তারা ব্যাপারটা বুঝে গেল।",
               "তবে আমি কখনো তাদের কোনো ক্ষতি করিনি।", "তাই তারা ভয়ও পেত না, রাগও করত না।"]),
    ("anniv", ["প্রতি বছর আমার মৃত্যুবার্ষিকীতে তারা মোমবাতি জ্বালাত।", "খাবারের টেবিলে আমার জন্য একটা চেয়ার খালি রাখত।",
               "ঈদ কিংবা অন্য কোনো উৎসবেও আমাকে ভুলত না।", "সত্যি বলতে, নিজেকে তাদের পরিবারেরই একজন মনে হতো।"]),
    ("door", ["কিন্তু এখন কেউ একজন দরজা ভাঙার চেষ্টা করছে।", "নীলার সাবেক স্বামী।", "লোকটা ভীষণ জেদি আর রাগী।",
              "সে আমার পরিবারটার ক্ষতি করতে এসেছে।", "আমার পরিবার।"]),
    ("power", ["ভূতদের একটা ব্যাপার আছে।", "যত বেশি উপহার আর স্মরণ পাবে, ততই তাদের শক্তি বাড়বে।",
               "গত পাঁচ বছর ধরে ওদের দেওয়া মোমবাতি, ছোটখাটো উপহার, এমনকি মাঝেমধ্যে খাবারও পেয়েছি।",
               "এসবের কারণে আমি এখন আগের চেয়ে অনেক শক্তিশালী।", "আমার হাতে ছুরিটা উষ্ণ লাগছে।",
               "বরফের মতো ঠান্ডা হাতের মধ্যে এক অদ্ভুত উত্তাপ।"]),
    ("finale", ["নীলা, রায়হান আর মায়া—ওরাই আমার পরিবার।", "আমি ওদের ভালোবাসি।",
                "আর ওদের এখনই আমার সঙ্গে ওপারে যেতে দেব না।"]),
]

console = Console()
TOTAL_STEPS = 7


def step(i, name):
    console.rule(f"[bold cyan]Step {i}/{TOTAL_STEPS}  {name}")


def die(msg):
    console.print(f"[bold red]ERROR:[/] {msg}")
    sys.exit(1)


# ----------------------------------------------------------------------------- JS SOURCES
PACKAGE_JSON = {
    "name": "amar-poribar", "version": "1.0.0", "private": True,
    "dependencies": {
        "react": "18.3.1", "react-dom": "18.3.1",
        "remotion": "^4.0.0", "@remotion/cli": "^4.0.0",
        "@remotion/bundler": "^4.0.0", "@remotion/renderer": "^4.0.0",
    },
}

JS_INDEX = r'''import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {Main} from './Main';
import data from './data.json';

const Root = () => (
  <Composition id="Story" component={Main} durationInFrames={data.totalFrames} fps={data.fps} width={1080} height={1920} />
);
registerRoot(Root);
'''

JS_RENDER = r''''use strict';
const path = require('path');
const fs = require('fs');
const {bundle} = require('@remotion/bundler');
const R = require('@remotion/renderer');
const emit = (o) => process.stdout.write('@@' + JSON.stringify(o) + '\n');

(async () => {
  const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  emit({t: 'stage', m: 'bundle'});
  const serveUrl = await bundle({
    entryPoint: path.join(job.root, 'src', 'index.jsx'),
    onProgress: (p) => emit({t: 'bundle', p}),
  });
  if (typeof R.ensureBrowser === 'function') {
    emit({t: 'stage', m: 'browser'});
    await R.ensureBrowser();
  }
  const comp = await R.selectComposition({serveUrl, id: 'Story', inputProps: {}});

  if (job.mode === 'stills') {
    emit({t: 'stage', m: 'render'});
    for (const [i, fr] of job.stills.entries()) {
      const out = path.join(job.stillsDir, 'scene_' + String(i).padStart(2, '0') + '.png');
      await R.renderStill({composition: comp, serveUrl, output: out, frame: fr, imageFormat: 'png'});
      emit({t: 'still', i, n: job.stills.length, out});
    }
    emit({t: 'end'});
    return;
  }

  emit({t: 'stage', m: 'render'});
  for (const [i, rg] of job.ranges.entries()) {
    const s = rg[0], e = rg[1], n = e - s + 1;
    const fin = path.join(job.cache, 'chunk_' + String(i).padStart(4, '0') + '.mp4');
    if (fs.existsSync(fin)) { emit({t: 'skip', i, n}); continue; }
    const tmp = fin.replace(/\.mp4$/, '.part.mp4');
    emit({t: 'start', i, n});
    let last = 0;
    await R.renderMedia({
      composition: comp, serveUrl, codec: 'h264', outputLocation: tmp,
      frameRange: [s, e], muted: true, crf: job.crf, pixelFormat: 'yuv420p', x264Preset: 'medium',
      imageFormat: 'jpeg', jpegQuality: job.jpegQuality, concurrency: job.concurrency,
      overwrite: true, logLevel: 'error',
      onProgress: (p) => {
        const now = Date.now();
        if (now - last > 150) { last = now; emit({t: 'prog', i, rf: p.renderedFrames, ef: p.encodedFrames}); }
      },
    });
    fs.renameSync(tmp, fin);
    emit({t: 'done', i, n});
  }
  emit({t: 'end'});
})().catch((e) => { emit({t: 'error', m: String((e && e.stack) || e)}); process.exit(1); });
'''

JS_MAIN = r'''import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame} from 'remotion';
import data from './data.json';

/* ============================== core helpers ============================== */
const W = 1080, H = 1920, INK = '#090705';
const C = {n0: '#060a16', n1: '#0c1530', n2: '#16224a', b0: '#1d130c', b1: '#33231a', b2: '#4d3626', b3: '#6b4b34', y: '#f2e2a0', y2: '#d9c274'};
const Boil = React.createContext(0);
const h = (n) => { const x = Math.sin(n * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); };
const cl = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const P = (f, a, b) => cl((f - a) / Math.max(1, b - a));
const E = (x) => x * x * (3 - 2 * x);
const lerp = (a, b, t) => a + (b - a) * t;
const mod = (a, n) => ((a % n) + n) % n;
const Seq = (f, beats, vals, tr = 28) => {
  let v = vals[0];
  for (let i = 1; i < vals.length; i++) { const t0 = beats[Math.min(i, beats.length - 1)]; v = lerp(v, vals[i], E(P(f, t0, t0 + tr))); }
  return v;
};
const Pick = (f, beats, vals) => vals[Math.min(vals.length - 1, Math.max(0, beats.filter((x) => f >= x).length - 1))];
const ell = (cx, cy, rx, ry, n = 12, rot = 0) => Array.from({length: n}, (_, i) => { const a = i / n * Math.PI * 2 + rot; return [cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]; });

const smooth = (p, closed) => {
  const n = p.length;
  if (n < 3) return `M${p[0][0]} ${p[0][1]}L${p[n - 1][0]} ${p[n - 1][1]}`;
  const g = (i) => (closed ? p[(i + n) % n] : p[Math.max(0, Math.min(n - 1, i))]);
  let d = `M${p[0][0].toFixed(1)} ${p[0][1].toFixed(1)}`;
  const m = closed ? n : n - 1;
  for (let i = 0; i < m; i++) {
    const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2);
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d + (closed ? 'Z' : '');
};
const jit = (pts, seed, bf, j) => pts.map((q, i) => [q[0] + (h(seed * 17.3 + i * 3.1 + bf * 7.7) - .5) * 2 * j, q[1] + (h(seed * 29.1 + i * 5.3 + bf * 3.9 + 9.1) - .5) * 2 * j]);

/* hand-drawn primitives: line "boil" re-seeds every 5 frames (12 fps drawing feel) */
const Shape = ({pts, fill = 'none', stroke = INK, sw = 5, seed = 1, j = 2.2, closed = true, op = 1}) => {
  const bf = React.useContext(Boil);
  return <path d={smooth(jit(pts, seed, bf, j), closed)} fill={fill} stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" opacity={op} />;
};
const Poly = ({pts, fill = 'none', stroke = INK, sw = 5, seed = 1, j = 1.8, op = 1}) => {
  const bf = React.useContext(Boil);
  const out = [];
  pts.forEach((a, i) => { const b = pts[(i + 1) % pts.length]; out.push(a); out.push([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]); });
  const p = jit(out, seed, bf, j);
  return <path d={'M' + p.map((q) => q[0].toFixed(1) + ' ' + q[1].toFixed(1)).join('L') + 'Z'} fill={fill} stroke={stroke} strokeWidth={sw} strokeLinejoin="round" opacity={op} />;
};

const Defs = () => (
  <defs>
    <linearGradient id="gWall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#070c20" /><stop offset="1" stopColor="#16224a" /></linearGradient>
    <linearGradient id="gFloor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2e1f15" /><stop offset="1" stopColor="#100a06" /></linearGradient>
    <linearGradient id="gWin" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#7f98c8" /><stop offset="1" stopColor="#25355f" /></linearGradient>
    <linearGradient id="gSky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#03060e" /><stop offset="1" stopColor="#1a2650" /></linearGradient>
    <linearGradient id="gSky2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#070c24" /><stop offset=".75" stopColor="#1b2448" /><stop offset="1" stopColor="#4a3a3a" /></linearGradient>
    <linearGradient id="gOpen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2c3250" /><stop offset="1" stopColor="#ecdca0" /></linearGradient>
    <linearGradient id="gMist" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#9fb4d6" stopOpacity="0" /><stop offset=".5" stopColor="#9fb4d6" stopOpacity=".22" /><stop offset="1" stopColor="#9fb4d6" stopOpacity="0" /></linearGradient>
    <radialGradient id="gLamp"><stop offset="0" stopColor="#ffe8a0" stopOpacity=".9" /><stop offset=".4" stopColor="#f0c870" stopOpacity=".33" /><stop offset="1" stopColor="#e8b050" stopOpacity="0" /></radialGradient>
    <radialGradient id="gMoon"><stop offset="0" stopColor="#9db8f0" stopOpacity=".5" /><stop offset="1" stopColor="#6f90d8" stopOpacity="0" /></radialGradient>
    <radialGradient id="gGhost"><stop offset="0" stopColor="#bcd4ff" stopOpacity=".55" /><stop offset="1" stopColor="#8aaaf0" stopOpacity="0" /></radialGradient>
    <radialGradient id="gEye"><stop offset="0" stopColor="#fff3b0" stopOpacity=".95" /><stop offset="1" stopColor="#ffd870" stopOpacity="0" /></radialGradient>
  </defs>
);
const Glow = ({x, y, r, g = 'gLamp', op = 1}) => <circle cx={x} cy={y} r={r} fill={`url(#${g})`} opacity={op} style={{mixBlendMode: 'screen'}} />;

/* camera: look-at point + zoom, clamped so the frame never leaves the canvas */
const Stage = ({f, d, z0 = 1, z1 = 1.12, z, cx = 540, cy = 960, children}) => {
  const zz = Math.max(1.03, z ?? lerp(z0, z1, f / Math.max(1, d)));
  const fx = cl(cx, 540 / zz, W - 540 / zz), fy = cl(cy, 960 / zz, H - 960 / zz);
  const sx = Math.sin(f / 53) * 3, sy = Math.cos(f / 61) * 2.5;
  return (
    <AbsoluteFill>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <g transform={`translate(${540 + sx} ${960 + sy}) scale(${zz}) translate(${-fx} ${-fy})`}>{children}</g>
      </svg>
    </AbsoluteFill>
  );
};

/* ================================ characters ================================ */
const KINDS = {
  man: {skin: '#a8917d', top: '#34406a', bot: '#231d17', hair: '#17120e'},
  boss: {skin: '#a58f7c', top: '#2c2b2e', bot: '#1a1a1d', hair: '#6e6c6a'},
  woman: {skin: '#b39b87', top: '#6a4636', bot: '#6a4636', hair: '#120d0a'},
  child: {skin: '#b9a28d', top: '#c4b277', bot: '#c4b277', hair: '#17120e'},
  ex: {skin: '#7f6c5c', top: '#14171f', bot: '#0f1118', hair: '#0b0a09'},
  ghost: {skin: '#cfdced', top: '#a9bcd9', bot: '#a9bcd9', hair: '#7f93b4'},
};

const Person = ({x = 0, y = 0, s = 1, kind = 'man', flip = 1, e = {}, mouth = 0, glow = 0, aura = .55, shadow = false, t = 0, seed = 1, arms = {}, op = 1, tilt = 0, float = 0, shade = 0, extra = null}) => {
  const K = KINDS[kind], G = kind === 'ghost', bf = React.useContext(Boil);
  const F = (c) => (shadow ? '#03050b' : c);
  const bob = G ? Math.sin(t / 30 + seed) * 14 : Math.sin(t / 57 + seed) * 3;
  const sway = Math.sin(t / 41 + seed * 2) * 6;
  const hy = -440 + bob * .4;
  const eyeS = e.eye ?? 1, br = e.brow ?? 0, lk = e.look || [0, 0], mo = e.mo || 'flat';
  const blink = ((t + seed * 53) % 190) < 6 ? .1 : 1;
  const jj = (v, i) => v + (h(seed * 7 + i * 1.7 + bf * 3.1) - .5) * 3;
  const hL = arms.l || [-122, -172 + sway], hR = arms.r || [122, -172 - sway];
  const limb = (a, b, w, col, bend = 0) => {
    const m = [(a[0] + b[0]) / 2 + bend, (a[1] + b[1]) / 2 + Math.abs(bend) * .3];
    const dd = `M${jj(a[0], 1)} ${jj(a[1], 2)}Q${m[0]} ${m[1]} ${jj(b[0], 3)} ${jj(b[1], 4)}`;
    return (<g>
      {!shadow && <path d={dd} fill="none" stroke={INK} strokeWidth={w + 9} strokeLinecap="round" />}
      <path d={dd} fill="none" stroke={F(col)} strokeWidth={w} strokeLinecap="round" />
    </g>);
  };
  const w = Math.sin(t / 14) * 14;
  const torso = G ? [[-100, -340], [100, -340], [104, -220], [78, -120 + w], [40, -50 - w], [6, 10 + w], [-30, -48 - w], [-70, -122 + w], [-104, -220]]
    : kind === 'woman' ? [[-88, -340], [88, -340], [100, -230], [142, -66], [-142, -66], [-100, -230]]
    : [[-98, -340], [98, -340], [90, -230], [84, -170], [-84, -170], [-90, -230]];
  const hairFront = kind === 'woman'
    ? [[-94, hy - 30], [-62, hy - 106], [0, hy - 120], [62, hy - 106], [94, hy - 30], [52, hy - 70], [0, hy - 60], [-52, hy - 70]]
    : [[-93, hy - 20], [-84, hy - 84], [-40, hy - 112], [22, hy - 116], [72, hy - 90], [93, hy - 26], [70, hy - 62], [10, hy - 80], [-50, hy - 72]];
  const hairBack = [[-112, hy - 40], [-100, hy - 112], [0, hy - 132], [100, hy - 112], [114, hy - 40], [128, hy + 170], [70, hy + 210], [-70, hy + 210], [-128, hy + 170]];
  const y0 = hy + 58;
  const talking = mouth > .12;
  return (
    <g transform={`translate(${x} ${y - float}) scale(${s * flip} ${s}) rotate(${tilt})`} opacity={op}>
      {G && !shadow && <Glow x={0} y={-250} r={430} g="gGhost" op={aura} />}
      {kind === 'woman' && <Shape pts={hairBack} fill={F(K.hair)} stroke={shadow ? 'none' : INK} seed={seed + 40} />}
      {!G && kind !== 'woman' && <g>{limb([-38, -180], [-42, -14], 46, K.bot)}{limb([38, -180], [42, -14], 46, K.bot)}
        {!shadow && <g><Shape pts={ell(-48, -8, 36, 14, 8)} fill="#0e0b09" stroke="none" seed={seed + 1} /><Shape pts={ell(48, -8, 36, 14, 8)} fill="#0e0b09" stroke="none" seed={seed + 2} /></g>}</g>}
      {kind === 'woman' && <g>{limb([-46, -70], [-46, -12], 26, K.skin)}{limb([46, -70], [46, -12], 26, K.skin)}</g>}
      <Shape pts={torso} fill={F(K.top)} stroke={shadow ? 'none' : INK} sw={5} seed={seed + 3} j={2.4} />
      {limb([-92, -322], hL, 38, K.top, -14)}
      {limb([92, -322], hR, 38, K.top, 14)}
      {!shadow && <g><circle cx={hL[0]} cy={hL[1]} r="21" fill={K.skin} stroke={INK} strokeWidth="4" /><circle cx={hR[0]} cy={hR[1]} r="21" fill={K.skin} stroke={INK} strokeWidth="4" /></g>}
      {kind === 'child' && <g><Shape pts={ell(-114, hy + 30, 28, 42, 8)} fill={F(K.hair)} stroke={shadow ? 'none' : INK} seed={seed + 5} /><Shape pts={ell(114, hy + 30, 28, 42, 8)} fill={F(K.hair)} stroke={shadow ? 'none' : INK} seed={seed + 6} /></g>}
      <circle cx="-90" cy={hy + 8} r="18" fill={F(K.skin)} stroke={shadow ? 'none' : INK} strokeWidth="4" />
      <circle cx="90" cy={hy + 8} r="18" fill={F(K.skin)} stroke={shadow ? 'none' : INK} strokeWidth="4" />
      <Shape pts={ell(0, hy, 90, 99, 12)} fill={F(K.skin)} stroke={shadow ? 'none' : INK} sw={5} seed={seed + 7} j={2.4} />
      <Shape pts={hairFront} fill={F(K.hair)} stroke={shadow ? 'none' : INK} sw={4} seed={seed + 8} j={2} />
      {!shadow && <g>
        {[-1, 1].map((sd) => {
          const ex = sd * 37, ey = hy - 8;
          return (<g key={sd}>
            {G ? (<g>
              <Shape pts={ell(ex, ey, 27, 37 * eyeS, 9)} fill="#04060c" sw={3} seed={seed + sd + 3} j={1.5} />
              <circle cx={ex + lk[0] * 9} cy={ey + lk[1] * 10} r={7 + glow * 7} fill={glow > .25 ? '#fff0a8' : '#c3d2ea'} />
              {glow > 0 && <Glow x={ex} y={ey} r={50 + glow * 70} g="gEye" op={glow} />}
            </g>) : (<g>
              <Shape pts={ell(ex, ey, 25, 29 * eyeS * blink, 9)} fill="#e8e0cc" sw={3.5} seed={seed + sd + 3} j={1.2} />
              <circle cx={ex + lk[0] * 9} cy={ey + lk[1] * 8} r={11 * Math.min(1, blink * 1.6)} fill="#14100d" />
            </g>)}
            <Shape pts={[[sd * 12, hy - 54 - 16 * br], [sd * 39, hy - 58 - 3 * br], [sd * 66, hy - 54 + 9 * br]]} closed={false} stroke={G ? '#2a3550' : '#171310'} sw={9} j={1.2} seed={seed + sd + 9} />
            <Shape pts={[[ex - 22, ey + 36], [ex, ey + 43], [ex + 22, ey + 36]]} closed={false} stroke="rgba(20,14,12,.4)" sw={4} j={1} seed={seed + sd + 12} />
          </g>);
        })}
        <Shape pts={[[-6, hy + 12], [0, hy + 32], [11, hy + 29]]} closed={false} sw={4} op={.55} j={1} seed={seed + 14} />
        {talking ? <Shape pts={ell(0, y0 + (5 + 28 * mouth) * .4, 18 + 10 * mouth, 5 + 28 * mouth, 8)} fill="#190b0c" sw={4} seed={seed + 15} j={1.2} />
          : mo === 'smile' ? <Shape pts={[[-34, y0 - 6], [0, y0 + 18], [34, y0 - 6]]} closed={false} sw={6} seed={seed + 16} j={1} />
          : mo === 'frown' ? <Shape pts={[[-30, y0 + 10], [0, y0 - 10], [30, y0 + 10]]} closed={false} sw={6} seed={seed + 16} j={1} />
          : mo === 'o' ? <Shape pts={ell(0, y0 + 6, 14, 19, 8)} fill="#190b0c" sw={4} seed={seed + 16} j={1} />
          : mo === 'grin' ? <g>
              <Shape pts={[[-58, y0 - 16], [-30, y0 + 22], [0, y0 + 34], [30, y0 + 22], [58, y0 - 16], [0, y0 + 2]]} fill="#12080a" sw={4} seed={seed + 16} j={1.2} />
              {[-3, -2, -1, 0, 1, 2, 3].map((i) => <path key={i} d={`M${i * 14} ${y0 - 2 + Math.abs(i)}v11`} stroke="#e8e0cc" strokeWidth="3.5" />)}
            </g>
          : <Shape pts={[[-28, y0], [0, y0 + 3], [28, y0]]} closed={false} sw={6} seed={seed + 16} j={1} />}
        {shade > 0 && <Poly pts={Array.from({length: 9}, (_, i) => { const a = Math.PI / 2 + i / 8 * Math.PI; return [Math.cos(a) * 90, hy + Math.sin(a) * 99]; })} fill="#000" stroke="none" op={shade * .5} seed={seed + 17} />}
      </g>}
      {extra}
    </g>
  );
};

/* ================================== props =================================== */
const Candle = ({x, y, t, k = 1, seed = 1, lit = 1}) => {
  const fl = 1 + .12 * Math.sin(t / 3.3 + seed) + .08 * Math.sin(t / 1.7 + seed * 2);
  const sw = Math.sin(t / 9 + seed) * 3;
  return (<g>
    <Poly pts={[[x - 16 * k, y - 90 * k], [x + 16 * k, y - 90 * k], [x + 18 * k, y], [x - 18 * k, y]]} fill="#d6ccae" seed={seed + 20} sw={3.5} />
    {lit > 0 && <g>
      <Glow x={x} y={y - 125 * k} r={300 * k * fl} op={.85 * lit} />
      <Shape pts={[[x + sw, y - 96 * k - 70 * k * fl * lit], [x + 17 * k, y - 125 * k], [x, y - 96 * k], [x - 17 * k, y - 125 * k]]} fill="#ffd36a" sw={2.5} seed={seed + 21} j={1} />
      <Shape pts={[[x + sw * .6, y - 140 * k], [x + 7 * k, y - 120 * k], [x, y - 103 * k], [x - 7 * k, y - 120 * k]]} fill="#fff4c4" stroke="none" seed={seed + 22} j={.6} />
    </g>}
  </g>);
};
const Gift = ({x, y, k = 1, col = '#5a4a2c', seed = 1}) => (<g>
  <Poly pts={[[x - 50 * k, y - 60 * k], [x + 50 * k, y - 60 * k], [x + 50 * k, y], [x - 50 * k, y]]} fill={col} seed={seed} sw={3.5} />
  <rect x={x - 7 * k} y={y - 60 * k} width={14 * k} height={60 * k} fill="#cdb872" />
  <path d={`M${x} ${y - 60 * k}q-30 -40 -42 -12q10 22 42 12q32 10 42 -12q-12 -28 -42 12`} fill="#cdb872" stroke={INK} strokeWidth="3" />
</g>);
const Table = ({y = 1330}) => (<g>
  <Poly pts={[[60, y], [1020, y], [1060, y + 50], [20, y + 50]]} fill={C.b3} seed={51} sw={5} />
  <Poly pts={[[40, y + 50], [1040, y + 50], [1040, y + 190], [40, y + 190]]} fill={C.b1} seed={52} sw={5} />
  <Poly pts={[[70, y + 190], [130, y + 190], [120, y + 560], [80, y + 560]]} fill={C.b2} seed={53} />
  <Poly pts={[[950, y + 190], [1010, y + 190], [1000, y + 560], [960, y + 560]]} fill={C.b2} seed={54} />
</g>);
const Chair = ({x, y}) => (<g>
  <Poly pts={[[x - 62, y - 340], [x + 62, y - 340], [x + 66, y - 130], [x - 66, y - 130]]} fill={C.b2} seed={61} />
  {[-36, 0, 36].map((o, i) => <rect key={i} x={x + o - 6} y={y - 320} width="12" height="170" fill={C.b1} />)}
</g>);
const Dust = ({t}) => (<g>{Array.from({length: 28}, (_, i) => {
  const x = mod(h(i * 7.1) * W + Math.sin(t / 90 + i) * 40, W), y = mod(h(i * 3.3) * H - t * (.2 + .3 * h(i * 1.7)), H);
  return <circle key={i} cx={x} cy={y} r={1.4 + 2.2 * h(i * 5.5)} fill="#f2e2a0" opacity={.15 + .25 * Math.abs(Math.sin(t / 40 + i))} />;
})}</g>);

const Room = ({t, lampOn = 1, mx = 270, moon = 1, win = true}) => {
  const fl = .9 + .07 * Math.sin(t / 8.3) + .04 * Math.sin(t / 2.7 + 1.3);
  const lx = 870, ly = 1150;
  return (<g>
    <rect width={W} height={H} fill="url(#gWall)" />
    {Array.from({length: 14}, (_, i) => <rect key={i} x={i * 80 + 30} width="5" height="1320" fill="#0f1836" opacity=".5" />)}
    <Poly pts={[[0, 1318], [W, 1318], [W, 1394], [0, 1394]]} fill={C.b1} seed={3} />
    <rect y="1394" width={W} height="526" fill="url(#gFloor)" />
    {Array.from({length: 9}, (_, i) => { const x0 = i * 135 - 30; return <path key={i} d={`M${x0} 1394L${540 + (x0 - 540) * 1.76} 1920`} stroke={C.b0} strokeWidth="4" opacity=".8" />; })}
    {[1470, 1570, 1710].map((yy, i) => <path key={i} d={`M0 ${yy}L${W} ${yy}`} stroke={C.b0} strokeWidth="3" opacity=".6" />)}
    {win && <g>
      <Poly pts={[[90, 330], [390, 330], [390, 800], [90, 800]]} fill="url(#gWin)" seed={5} sw={7} />
      <circle cx={mx} cy="470" r="44" fill="#dfe7f7" opacity={.9 * moon} />
      <path d="M240 330V800M90 560H390" stroke={C.b2} strokeWidth="12" />
      <Poly pts={[[70, 800], [410, 800], [410, 832], [70, 832]]} fill={C.b2} seed={6} />
      <Glow x={240} y={560} r={620} g="gMoon" op={.7 * moon} />
      <path d="M110 1400L390 1400L760 1900L120 1900Z" fill="#8fa8d8" opacity={.07 * moon} />
      <path d="M210 1400L228 1400L420 1900L360 1900Z" fill="#05070f" opacity={.2 * moon} />
    </g>}
    <Poly pts={[[450, 520], [600, 520], [600, 700], [450, 700]]} fill={C.b3} seed={11} />
    <Poly pts={[[466, 536], [584, 536], [584, 684], [466, 684]]} fill="#101a3a" seed={12} sw={3} />
    <Poly pts={[[640, 470], [1040, 470], [1040, 1330], [640, 1330]]} fill={C.b2} seed={7} sw={6} />
    <Poly pts={[[620, 440], [1060, 440], [1060, 492], [620, 492]]} fill={C.b3} seed={8} />
    <Poly pts={[[665, 520], [835, 520], [835, 1290], [665, 1290]]} fill={C.b1} seed={9} sw={4} />
    <Poly pts={[[845, 520], [1015, 520], [1015, 1290], [845, 1290]]} fill={C.b1} seed={10} sw={4} />
    <circle cx="820" cy="900" r="9" fill={C.y2} /><circle cx="860" cy="900" r="9" fill={C.y2} />
    <Poly pts={[[560, 1150], [1080, 1150], [1080, 1394], [560, 1394]]} fill={C.b2} seed={13} sw={6} />
    <Poly pts={[[540, 1128], [1080, 1128], [1080, 1160], [540, 1160]]} fill={C.b3} seed={14} />
    <path d="M600 1250H1060M600 1330H1060" stroke={C.b0} strokeWidth="4" />
    <Poly pts={[[lx - 40, ly - 14], [lx + 40, ly - 14], [lx + 30, ly], [lx - 30, ly]]} fill={C.b0} seed={15} sw={3} />
    <path d={`M${lx} ${ly - 14}V${ly - 150}`} stroke={C.b0} strokeWidth="9" />
    <Poly pts={[[lx - 68, ly - 250], [lx + 68, ly - 250], [lx + 104, ly - 130], [lx - 104, ly - 130]]} fill="#f0dc92" seed={16} sw={4} op={.55 + .4 * lampOn} />
    <Glow x={lx} y={ly - 190} r={600} op={lampOn * fl} />
    <Glow x={lx} y={ly - 190} r={200} op={lampOn * fl * .8} />
    <Dust t={t} />
  </g>);
};

const Tree = ({x, y, k = 1}) => {
  const br = [[-1, -.55, .75], [1, -.7, .8], [-1, -.95, .55], [1, -1.1, .5], [0, -1.3, .45]];
  return (<g stroke="#05070d" strokeLinecap="round" fill="none">
    <path d={`M${x} ${y}Q${x + 8 * k} ${y - 200 * k} ${x} ${y - 380 * k}`} strokeWidth={26 * k} />
    {br.map((q, i) => {
      const sx = x, sy = y - 380 * k * (.35 + i * .14), ex = sx + q[0] * 190 * k * q[2] * 1.2, ey = sy + q[1] * 150 * k;
      return <path key={i} d={`M${sx} ${sy}Q${(sx + ex) / 2} ${sy - 30 * k} ${ex} ${ey}`} strokeWidth={(12 - i) * k} />;
    })}
  </g>);
};
const Stone = ({x, y, k, seed}) => (<g>
  <Shape pts={[[x - 42 * k, y], [x - 42 * k, y - 110 * k], [x - 26 * k, y - 152 * k], [x, y - 162 * k], [x + 26 * k, y - 152 * k], [x + 42 * k, y - 110 * k], [x + 42 * k, y]]} fill="#262b3c" seed={seed + 80} sw={4} />
  <path d={`M${x} ${y - 125 * k}v58M${x - 18 * k} ${y - 108 * k}h36`} stroke="#0b0e18" strokeWidth={5 * k} />
</g>);
const Yard = ({t, scroll = 0}) => (<g>
  <rect width={W} height={H} fill="url(#gSky2)" />
  <circle cx="800" cy="380" r="84" fill="#e4dfc6" opacity=".85" />
  <Glow x={800} y={380} r={520} g="gMoon" op={.6} />
  <Shape pts={[[-80, 1060], [180, 950], [460, 1030], [760, 930], [1160, 1020], [1160, 1500], [-80, 1500]]} fill="#0a1022" stroke="none" j={5} seed={4} />
  <Tree x={mod(150 - scroll * .3, 1500) - 200} y={1190} k={1.2} />
  <Tree x={mod(750 - scroll * .3, 1500) - 200} y={1170} k={.95} />
  <Shape pts={[[-80, 1260], [300, 1232], [700, 1252], [1160, 1226], [1160, 1920], [-80, 1920]]} fill="#1a130e" stroke="none" j={3} seed={6} />
  {[0, 1, 2, 3, 4, 5].map((i) => <Stone key={i} x={mod(80 + i * 230 - scroll * .7, 1500) - 200} y={1290 + (i % 3) * 28} k={.8 + (i % 3) * .12} seed={i} />)}
  {[0, 1, 2].map((i) => <rect key={i} x={mod(t * .3 + i * 420, 1700) - 560} y={1240 + i * 90} width="1000" height="170" fill="url(#gMist)" />)}
</g>);
const House = ({x, y, t}) => (<g>
  <Poly pts={[[x - 200, y - 300], [x + 200, y - 300], [x + 200, y], [x - 200, y]]} fill="#1a1d2e" seed={41} />
  <Poly pts={[[x - 240, y - 300], [x, y - 460], [x + 240, y - 300]]} fill="#10131f" seed={42} />
  <Poly pts={[[x - 130, y - 230], [x - 40, y - 230], [x - 40, y - 140], [x - 130, y - 140]]} fill="#f0d98a" seed={43} sw={4} />
  <Glow x={x - 85} y={y - 185} r={260} op={.8 + .1 * Math.sin(t / 6)} />
  <Poly pts={[[x + 40, y - 180], [x + 130, y - 180], [x + 130, y], [x + 40, y]]} fill={C.b1} seed={44} />
</g>);
const Bundle = () => (<g>
  <Shape pts={ell(10, -246, 78, 46, 10)} fill="#d8cda4" sw={4} seed={31} />
  <Shape pts={ell(-46, -262, 30, 32, 8)} fill="#c3ab96" sw={3.5} seed={32} />
  <path d="M-58 -262q6 5 12 0M-40 -262q6 5 12 0" stroke={INK} strokeWidth="3" fill="none" />
</g>);
const Cradle = ({x, y, s = 1, rot = 0, asleep = 0}) => (
  <g transform={`translate(${x} ${y}) scale(${s}) rotate(${rot} 0 40)`}>
    <Shape pts={[[-175, -4], [-90, 36], [0, 48], [90, 36], [175, -4], [90, 14], [0, 24], [-90, 14]]} fill={C.b3} sw={5} seed={91} />
    <Poly pts={[[-165, -175], [165, -175], [125, -12], [-125, -12]]} fill={C.b2} seed={92} sw={5} />
    {[-90, -30, 30, 90].map((o, i) => <path key={i} d={`M${o} -160V-30`} stroke={C.b1} strokeWidth="9" />)}
    <Shape pts={ell(0, -168, 150, 44, 10)} fill="#d9ceaa" sw={4} seed={93} />
    <Shape pts={ell(-60, -196, 42, 44, 9)} fill="#c2ab96" sw={4} seed={94} />
    {asleep < .5 ? <g><circle cx="-74" cy="-200" r="5" fill={INK} /><circle cx="-46" cy="-200" r="5" fill={INK} /><path d="M-76 -182q16 14 32 0" stroke={INK} strokeWidth="4" fill="none" /></g>
      : <path d="M-82 -200q8 6 16 0M-54 -200q8 6 16 0M-70 -184q10 5 20 0" stroke={INK} strokeWidth="3.5" fill="none" />}
  </g>
);
const DoorArt = ({x0 = 270, y0 = 430, x1 = 810, y1 = 1392, open = 0, children}) => {
  const w = x1 - x0, sx = 1 - open * .8, pw = (w - 102) / 2, ph = (y1 - y0 - 120) / 2;
  return (<g>
    <Poly pts={[[x0 - 34, y0 - 34], [x1 + 34, y0 - 34], [x1 + 34, y1], [x0 - 34, y1]]} fill={C.b1} seed={71} sw={6} />
    <rect x={x0} y={y0} width={w} height={y1 - y0} fill="#06080f" />
    {open > 0 && <rect x={x0} y={y0} width={w} height={y1 - y0} fill="url(#gOpen)" opacity={open} />}
    <g transform={`translate(${x0} 0) scale(${sx} 1) translate(${-x0} 0)`}>
      <Poly pts={[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]} fill={C.b2} seed={72} sw={6} />
      {[0, 1].flatMap((r) => [0, 1].map((c) => { const px = x0 + 34 + c * (pw + 34), py = y0 + 40 + r * (ph + 40);
        return <Poly key={r * 2 + c} pts={[[px, py], [px + pw, py], [px + pw, py + ph], [px, py + ph]]} fill={C.b1} seed={73 + r * 2 + c} sw={4} />; }))}
      <circle cx={x1 - 46} cy={(y0 + y1) / 2} r="14" fill={C.y2} stroke={INK} strokeWidth="3" />
      {children}
    </g>
  </g>);
};
const Knife = ({k = 1, t = 0}) => (<g transform="rotate(-12)">
  <Glow x={0} y={-70} r={150} g="gLamp" op={(.75 + .15 * Math.sin(t / 5)) * k} />
  <Poly pts={[[-9, 10], [9, 10], [11, -130], [0, -176], [-9, -122]]} fill="#c6d1e6" seed={95} sw={3.5} op={k} />
  <Poly pts={[[0, 10], [9, 10], [11, -130], [0, -176]]} fill="#ffcf7a" stroke="none" seed={96} op={.6 * k} />
  <Poly pts={[[-13, 10], [13, 10], [13, 64], [-13, 64]]} fill={C.b2} seed={97} sw={3.5} op={k} />
</g>);

/* ================================= scenes =================================== */
const bt = (beats) => (i) => beats[Math.min(i, beats.length - 1)];

const Intro = ({f, d, beats, env}) => (
  <Stage f={f} d={d} z0={1} z1={1.22} cx={560} cy={1080}>
    <Room t={f} mx={lerp(150, 330, f / d)} />
    <Person x={560} y={1590} s={1.3} kind="ghost" float={34} t={f} seed={2} op={.92 * E(P(f, 25, 190))} mouth={env}
      e={{brow: .7, mo: 'flat', look: [Math.sin(f / 70) * .8, .1]}} />
  </Stage>
);

const RoadBg = () => (<g>
  <rect width={W} height={H} fill="url(#gSky)" />
  <circle cx="820" cy="330" r="70" fill="#dfe5f2" opacity=".85" />
  <Glow x={820} y={330} r={480} g="gMoon" op={.7} />
  {Array.from({length: 24}, (_, i) => <circle key={i} cx={h(i * 3.1) * W} cy={h(i * 7.7) * 620} r={1 + h(i) * 1.8} fill="#cfd8ee" opacity={.3 + .4 * h(i * 2.2)} />)}
  <Shape pts={[[-60, 900], [60, 780], [130, 860], [240, 730], [330, 850], [470, 800], [600, 880], [760, 760], [880, 850], [1000, 740], [1140, 880], [1140, 920], [-60, 920]]} fill="#05080f" stroke="none" seed={2} j={4} />
  <rect y="900" width={W} height="1020" fill="#0b0e18" />
  <path d="M470 900L610 900L1420 1920L-340 1920Z" fill="#161926" />
  <path d="M470 900L-340 1920M610 900L1420 1920" stroke="#2a2f45" strokeWidth="6" />
  {Array.from({length: 9}, (_, i) => { const z = (i + .5) / 9, zz = z * z, yy = 900 + 1020 * zz, hg = 20 + 170 * zz, wd = 4 + 34 * zz;
    return <Poly key={i} pts={[[540 - wd / 2, yy], [540 + wd / 2, yy], [540 + wd * .6, yy + hg], [540 - wd * .6, yy + hg]]} fill="#d9c97d" stroke="none" op={.5} seed={i} />; })}
  <Poly pts={[[160, 500], [174, 500], [180, 1250], [152, 1250]]} fill="#07090f" stroke="none" seed={5} />
  <Poly pts={[[160, 490], [310, 490], [310, 516], [160, 516]]} fill="#07090f" stroke="none" seed={6} />
  <Glow x={290} y={560} r={520} op={.9} />
  <ellipse cx="300" cy="1300" rx="380" ry="70" fill="#f0d98a" opacity=".1" />
</g>);
const Car = ({x, y, k, rot, t}) => (
  <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${k})`}>
    <Poly pts={[[-130, -50], [130, -50], [152, 62], [-152, 62]]} fill="#12141c" seed={81} sw={5} />
    <Poly pts={[[-92, -122], [92, -122], [122, -50], [-122, -50]]} fill="#1c2030" seed={82} sw={5} />
    <Poly pts={[[-76, -108], [76, -108], [100, -58], [-100, -58]]} fill="#3a4666" seed={83} sw={3} op={.7} />
    <Poly pts={[[-138, 62], [-96, 62], [-96, 98], [-138, 98]]} fill="#05060a" seed={84} sw={4} />
    <Poly pts={[[96, 62], [138, 62], [138, 98], [96, 98]]} fill="#05060a" seed={85} sw={4} />
    <Shape pts={ell(-96, 14, 28, 17, 8)} fill="#fff6c8" sw={3} seed={86} /><Shape pts={ell(96, 14, 28, 17, 8)} fill="#fff6c8" sw={3} seed={87} />
    <Glow x={-96} y={14} r={340} op={.9} /><Glow x={96} y={14} r={340} op={.9} />
  </g>
);
const Road = ({f, d, beats, env}) => {
  const b = bt(beats);
  const impact = b(5) + (d - b(5)) * .2;
  const q = Math.pow(P(f, b(3), impact + 4), 1.8);
  const swv = E(P(f, b(4), impact));
  const flash = f < impact ? P(f, impact - 5, impact) : Math.exp(-(f - impact) / 38);
  const shake = f > impact ? Math.exp(-(f - impact) / 14) * 22 * Math.sin(f * 1.9) : 0;
  const gi = E(P(f, impact + 30, impact + 150));
  return (<Stage f={f} d={d} z0={1} z1={1.14} cx={540} cy={1200}>
    <g transform={`translate(${shake} ${shake * .4})`}>
      <RoadBg />
      {f < impact && <Person x={660} y={1500} s={.85} kind="man" t={f} seed={3}
        e={q > .55 ? {eye: 1.45, brow: 1, mo: 'o', look: [-1, -.2]} : {brow: .1, mo: 'flat', look: [Math.sin(f / 50), 0]}} />}
      <Car x={540 + 110 * swv * q} y={905 + 700 * q} k={.18 + 2.9 * q} rot={8 * swv} t={f} />
      <rect width={W} height={H} fill="#02040a" opacity={.55 * P(f, impact + 30, impact + 150)} />
      {f >= impact && <Person kind="ghost" x={660} y={1500} s={.85} float={gi * 70} op={gi * .9} t={f} seed={4} mouth={env} e={{brow: .8, mo: 'flat'}} />}
    </g>
    <rect width={W} height={H} fill="#fff" opacity={cl(flash)} />
  </Stage>);
};

const Calm = ({f, d, beats, env}) => {
  const b = bt(beats);
  const sm = E(P(f, b(1), b(1) + 40));
  const e = {brow: lerp(.7, .35, sm), mo: sm > .5 ? 'smile' : 'flat', eye: 1, look: [Math.sin(f / 60) * .5, .2]};
  const tears = f > b(2) ? [0, 1].map((i) => { const p = mod(f * 1.2 + i * 65, 150); return <circle key={i} cx={(i ? 1 : -1) * 38} cy={-415 + p * .9} r="6" fill="#cfe0ff" opacity={(1 - p / 150) * .9} />; }) : null;
  return (<Stage f={f} d={d} z0={1.0} z1={1.1} cx={580} cy={800}>
    <Room t={f} mx={330} />
    <Person x={600} y={1960} s={2.7} kind="ghost" t={f} seed={5} mouth={env} e={e} shade={.7} aura={.4} extra={tears} />
  </Stage>);
};

const Funeral = ({f, d, beats, env}) => {
  const b = bt(beats);
  const vis = (i) => E(P(f, b(2) + i * 30, b(2) + i * 30 + 50));
  const push = E(P(f, b(3) - 20, d));
  return (<Stage f={f} d={d} z={lerp(1.0, 1.55, push)} cx={lerp(540, 680, push)} cy={lerp(1300, 1360, push)}>
    <Yard t={f} />
    <Person kind="boss" x={210} y={1560} s={1.05} t={f} seed={11} op={vis(0)} e={{brow: -.1, mo: 'flat'}} />
    <Person kind="man" x={430} y={1560} s={1.05} t={f} seed={12} op={vis(1)} e={{brow: .9, mo: 'frown', eye: 1.1, look: [0, .6]}} />
    <Person kind="woman" x={650} y={1560} s={1.05} t={f} seed={13} op={vis(2)} e={{brow: .7, mo: 'flat', look: [0, .7]}} arms={{l: [-10, -232], r: [70, -226]}} extra={<Bundle />} />
    <Person kind="ghost" x={900} y={1540} s={1.0} float={26} t={f} seed={14} op={.9 * E(P(f, 10, 70))} mouth={env} e={{brow: .8, mo: 'flat', look: [-.8, .5]}} />
    <Shape pts={[[40, 1700], [200, 1610], [540, 1580], [880, 1610], [1040, 1700], [1040, 1960], [40, 1960]]} fill="#241a12" seed={15} sw={5} />
    <Poly pts={[[520, 1590], [540, 1590], [540, 1470], [520, 1470]]} fill={C.b2} seed={16} sw={3} />
    <Poly pts={[[490, 1510], [570, 1510], [570, 1528], [490, 1528]]} fill={C.b2} seed={17} sw={3} />
  </Stage>);
};

const Follow = ({f, d, beats, env}) => {
  const b = bt(beats);
  const bossX = lerp(300, -200, E(P(f, 0, b(1))));
  const houseX = lerp(1550, 840, E(P(f, b(2), d)));
  const wk = (i) => Math.abs(Math.sin(f / 9 + i)) * -12;
  const gE = {brow: Seq(f, beats, [-.7, .8, -.3]), mo: Pick(f, beats, ['frown', 'flat', 'flat']), look: [Seq(f, beats, [-1, 0, 1]), .1], eye: 1};
  return (<Stage f={f} d={d} z0={1} z1={1.12} cx={540} cy={1300}>
    <Yard t={f} scroll={f * 1.4} />
    <House x={houseX} y={1330} t={f} />
    <Person kind="boss" x={bossX} y={1450 + wk(2)} s={.7} t={f} seed={21} op={.85 * (1 - P(f, b(1) - 20, b(1)))} tilt={Math.sin(f / 9) * 2} />
    <Person kind="man" x={560} y={1560 + wk(0)} s={1} t={f} seed={22} tilt={Math.sin(f / 9) * 2} e={{brow: .5, mo: 'flat', look: [.5, .5]}} />
    <Person kind="woman" x={790} y={1560 + wk(1)} s={1} t={f} seed={23} tilt={Math.sin(f / 9 + 1) * 2} arms={{l: [-10, -232], r: [70, -226]}} extra={<Bundle />} e={{brow: .4, mo: 'flat', look: [.5, .3]}} />
    <Person kind="ghost" x={260 + Math.sin(f / 50) * 20} y={1560} s={1} float={36} t={f} seed={24} op={.9} mouth={env} e={gE} />
  </Stage>);
};

const Nursery = ({f, d, beats, env}) => {
  const b = bt(beats);
  const par = E(P(f, b(3), b(3) + 40));
  const leave = E(P(f, b(4) + 20, b(4) + 130));
  const rock = f > b(4) + 60 ? Math.sin((f - b(4)) / 26) * 7 : Math.sin(f / 70) * 1.5;
  const asleep = P(f, b(4) + 40, b(4) + 140);
  const pe = {eye: .5, brow: .8, mo: 'flat', look: [.3, .8]};
  return (<Stage f={f} d={d} z0={1} z1={1.18} cx={620} cy={1250}>
    <Room t={f} mx={330} lampOn={.85} />
    <Person kind="woman" x={110 - 520 * leave} y={1560} s={1.1} t={f} seed={31} op={par} tilt={5} e={pe} />
    <Person kind="man" x={300 - 520 * leave} y={1560} s={1.1} t={f} seed={32} op={par} tilt={5} e={pe} />
    <Cradle x={610} y={1610} s={1.2} rot={rock} asleep={asleep} />
    <Person kind="ghost" x={960} y={1600} s={1.25} flip={-1} float={0} t={f} seed={33} op={.92} mouth={env}
      arms={{r: [128, -210 + rock * 3]}} e={{brow: .3, mo: 'smile', eye: .95, look: [-1, .6]}} />
  </Stage>);
};

const Aware = ({f, d, beats, env}) => {
  const b = bt(beats);
  const ge = Seq(f, beats, [0, .6, .9, 1, 1]);
  const pe = {eye: Seq(f, beats, [1, 1.35, 1.1, 1, 1]), brow: Seq(f, beats, [0, .9, .4, .2, .1]), mo: Pick(f, beats, ['flat', 'o', 'flat', 'smile', 'smile']), look: [Seq(f, beats, [0, 1, 1, 1, 1]), 0]};
  return (<Stage f={f} d={d} z0={1} z1={1.2} cx={600} cy={1200}>
    <Room t={f} mx={lerp(120, 360, P(f, 0, b(2)))} />
    <Person kind="man" x={330} y={1470} s={1.15} t={f} seed={6} e={pe} />
    <Person kind="woman" x={680} y={1470} s={1.15} t={f} seed={7} e={pe} />
    <Person kind="ghost" x={960} y={1540} s={1} float={26} flip={-1} op={.75 * E(P(f, b(1) - 20, b(1) + 40))} t={f} seed={8} mouth={env} aura={.35 + .3 * ge} e={{brow: .6, mo: 'smile', eye: .9, look: [-1, .2]}} />
    <Table />
  </Stage>);
};

const Anniv = ({f, d, beats, env}) => {
  const b = bt(beats);
  const lit = E(P(f, b(0) + 15, b(0) + 55));
  const gIn = E(P(f, b(3) - 10, b(3) + 70));
  const fe = {eye: .95, brow: .2, mo: 'smile', look: [Seq(f, beats, [0, 0, 0, -1]), 0]};
  const bun = E(P(f, b(2) - 10, b(2) + 40));
  const cols = [C.y2, '#3b4a78', '#7a5a40'];
  return (<Stage f={f} d={d} z0={1} z1={1.22} cx={540} cy={1250}>
    <Room t={f} lampOn={.4} mx={380} />
    <g opacity={bun}>
      <path d="M0 340Q540 700 1080 340" stroke={C.b3} strokeWidth="4" fill="none" />
      {Array.from({length: 10}, (_, i) => { const u = (i + .5) / 10, xx = 1080 * u + Math.sin(f / 30 + i) * 3, yy = 340 + 720 * u * (1 - u);
        return <Poly key={i} pts={[[xx - 28, yy], [xx + 28, yy], [xx, yy + 80]]} fill={cols[i % 3]} seed={100 + i} sw={3} op={.85} />; })}
    </g>
    <Chair x={190} y={1500} />
    <Person kind="ghost" x={190} y={1490} s={1} t={f} seed={41} op={.9 * gIn} mouth={env} aura={.3 + .5 * gIn} e={{brow: .3, mo: 'smile', look: [1, .2]}} />
    <Person kind="man" x={470} y={1470} s={1} t={f} seed={42} e={fe} />
    <Person kind="child" x={690} y={1470} s={.85} t={f} seed={43} e={fe} />
    <Person kind="woman" x={900} y={1470} s={1} t={f} seed={44} e={fe} />
    <Table />
    <Poly pts={[[330, 1332], [400, 1332], [396, 1300], [334, 1300]]} fill="#3b4a78" seed={45} sw={3} />
    <Poly pts={[[760, 1332], [830, 1332], [826, 1300], [764, 1300]]} fill="#3b4a78" seed={46} sw={3} />
    <Glow x={590} y={1250} r={720} op={.45 * lit} />
    <Candle x={590} y={1372} k={1.5} t={f} seed={47} lit={lit} />
  </Stage>);
};

const DoorS = ({f, d, beats, env}) => {
  const b = bt(beats);
  const hits = [];
  { let t = b(0) + 30, gap = 100; while (t < d) { hits.push(t); t += gap; gap = Math.max(32, gap * .8); } }
  const a = cl(hits.reduce((s, t) => (f >= t ? s + Math.exp(-(f - t) / 7) * Math.cos((f - t) * 1.7) : s), 0), -1.5, 1.5);
  const lamp = cl(.75 - .35 * Math.abs(a) + .1 * Math.sin(f / 4), .2, 1);
  const crack = P(f, b(2), d);
  const sx = Math.sin(f / 25) * 18;
  const ge = {brow: Seq(f, beats, [1, .2, -.6, -.9, -.9]), eye: Seq(f, beats, [1.2, 1, 1, 1.1, 1.2]), look: [Seq(f, beats, [-.6, -.3, 0, 0, 0]), Seq(f, beats, [-.3, 0, 0, 0, 0])], mo: 'flat'};
  return (<Stage f={f} d={d} z0={1} z1={1.3} cx={540} cy={1000}>
    <Room t={f} lampOn={lamp} win={false} mx={0} moon={.5} />
    <g transform={`translate(${a * 9} ${Math.abs(a) * 3})`}>
      <DoorArt>
        <g stroke="#05070d" strokeWidth="6" fill="none" strokeLinecap="round" opacity={crack}>
          <path d="M420 460L450 640L410 760L470 900" /><path d="M700 470L670 700L720 860" /><path d="M560 1040L600 1200L540 1300" />
        </g>
      </DoorArt>
    </g>
    <path d="M300 1394L780 1394L880 1520L200 1520Z" fill="#cfe0ff" opacity=".1" />
    <rect x="300" y="1378" width="480" height="16" fill="#dce8ff" opacity=".6" />
    <Shape pts={ell(450 + sx, 1386, 32, 9, 8)} fill="#000" stroke="none" seed={51} />
    <Shape pts={ell(560 + sx, 1386, 32, 9, 8)} fill="#000" stroke="none" seed={52} />
    <Person kind="ghost" x={540} y={1650} s={1.5} t={f} seed={53} op={.95} mouth={env} glow={Seq(f, beats, [0, 0, .2, .5, .9])} aura={.5 + .3 * env} e={ge} />
  </Stage>);
};

const Power = ({f, d, beats, env}) => {
  const b = bt(beats);
  const g = E(P(f, b(1), b(3)));
  const flow = E(P(f, b(0) + 10, b(2)));
  const kn = E(P(f, b(4) - 25, b(4) + 25));
  const cam = E(P(f, b(4) - 10, b(4) + 90));
  const src = [[170, 1390], [930, 1370], [330, 1610]];
  const tr = kn * (Math.sin(f * 1.3) * env * 3);
  const base = 1.02 + .1 * P(f, 0, b(4));
  const hand = [lerp(122, 170, kn), lerp(-172, -335, kn)];
  return (<Stage f={f} d={d} z={lerp(base, 2.5, cam)} cx={lerp(540, 795, cam)} cy={lerp(1150, 1117, cam)}>
    <Room t={f} lampOn={.25} mx={300} moon={.5} />
    <Candle x={170} y={1500} k={1.2} t={f} seed={61} />
    <Gift x={930} y={1480} k={1.3} seed={62} />
    <Gift x={330} y={1720} k={1.1} seed={63} col="#3b4a78" />
    {Array.from({length: 21}, (_, i) => {
      const s = src[i % 3], u = mod(f * .011 + i / 21, 1), tx = 540, ty = 1230;
      const qx = (s[0] + tx) / 2 + (h(i) - .5) * 160, qy = Math.min(s[1], ty) - 180;
      const px = (1 - u) * (1 - u) * s[0] + 2 * u * (1 - u) * qx + u * u * tx, py = (1 - u) * (1 - u) * s[1] + 2 * u * (1 - u) * qy + u * u * ty;
      return <circle key={i} cx={px} cy={py} r={5 + 5 * h(i * 2)} fill="#ffe9a0" opacity={Math.sin(u * Math.PI) * .9 * flow} style={{mixBlendMode: 'screen'}} />;
    })}
    <Glow x={540} y={1200} r={300 + 400 * g} g="gGhost" op={.45 + .4 * g + .2 * env} />
    <Person kind="ghost" x={540} y={1620} s={1.5} t={f} seed={64} op={.95} mouth={env} glow={Seq(f, beats, [0, .2, .7, 1, 1, 1])} aura={.3 + .3 * g}
      arms={{r: hand}} e={{brow: Seq(f, beats, [.3, 0, -.4, -.6, -.8, -.8]), mo: 'flat', look: [0, 0]}}
      extra={kn > 0 && <g transform={`translate(${hand[0] + tr} ${hand[1]})`}><Knife k={kn} t={f} /></g>} />
  </Stage>);
};

const Finale = ({f, d, beats, env}) => {
  const b = bt(beats);
  const sEnd = d - data.tail, rest = Math.max(30, sEnd - b(2));
  const open = E(P(f, b(2) + rest * .3, b(2) + rest * .3 + 45));
  const grin = E(P(f, sEnd - 6, sEnd + 40));
  const sc = {eye: 1.35, brow: 1, mo: 'o', look: [-1, 0]};
  const gl = Seq(f, beats, [0, .3, .8, 1]) * .8 + grin * .2;
  return (<Stage f={f} d={d} z={lerp(1.0, 1.45, E(P(f, 0, d)))} cx={480} cy={1100}>
    <Room t={f} lampOn={.5} win={false} mx={0} moon={.4} />
    <DoorArt x0={70} y0={720} x1={350} y1={1392} open={open} />
    {open > 0 && <g opacity={open * .9}><g transform="translate(215 1392) skewX(-62) scale(1.5 .34)"><Person kind="ex" shadow x={0} y={0} s={1.3} /></g></g>}
    <Person kind="woman" x={650} y={1640} s={1.1} t={f} seed={71} arms={{r: [150, -230]}} e={sc} />
    <Person kind="man" x={960} y={1640} s={1.1} t={f} seed={72} arms={{l: [-150, -230]}} e={sc} />
    <Person kind="child" x={800} y={1700} s={.85} t={f} seed={73} e={sc} />
    <Person kind="ghost" x={470} y={1600} s={1.4 * (1 + .02 * env)} float={20} t={f} seed={74} op={.96} mouth={grin > .4 ? 0 : env}
      glow={gl} aura={.5 + .4 * gl} arms={{l: [-200, -330], r: [200, -330]}}
      e={{brow: Seq(f, beats, [-.4, -.6, -1, -1]), eye: 1.1, mo: grin > .4 ? 'grin' : 'flat', look: [-1 * (1 - grin), 0]}} />
  </Stage>);
};

/* ================================ composition =============================== */
const SCENES = [Intro, Road, Calm, Funeral, Follow, Nursery, Aware, Anniv, DoorS, Power, Finale];

const NOISE = (() => {
  if (typeof document === 'undefined') return '';
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const x = c.getContext('2d'), im = x.createImageData(256, 256);
  let s = 12345;
  const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  for (let i = 0; i < im.data.length; i += 4) { const v = Math.floor(rnd() * 255); im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 255; }
  x.putImageData(im, 0, 0);
  return c.toDataURL('image/png');
})();

const SceneWrap = ({sc, idx}) => {
  const f = useCurrentFrame();
  const d = sc.to - sc.from;
  const env = data.env[Math.min(sc.from + f, data.env.length - 1)] || 0;
  const Comp = SCENES[idx];
  const last = idx === SCENES.length - 1;
  const op = (idx === 0 ? E(P(f, 0, 40)) : E(P(f, 0, data.half * 2))) * (last ? 1 - E(P(f, d - 100, d - 4)) : 1);
  return <AbsoluteFill style={{opacity: op}}><Comp f={f} d={d} beats={sc.beats} env={env} /></AbsoluteFill>;
};

const Overlay = () => {
  const f = useCurrentFrame();
  const env = data.env[Math.min(f, data.env.length - 1)] || 0;
  const gx = Math.floor(h(Math.floor(f / 2) * 1.3) * 256), gy = Math.floor(h(Math.floor(f / 2) * 2.9 + 5) * 256);
  return (<AbsoluteFill style={{pointerEvents: 'none'}}>
    <AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 46%, rgba(0,0,0,0) ${36 - env * 5}%, rgba(2,3,8,.82) 100%)`}} />
    <AbsoluteFill style={{backgroundImage: `url(${NOISE})`, backgroundSize: '256px 256px', backgroundPosition: `${gx}px ${gy}px`, mixBlendMode: 'overlay', opacity: .15}} />
  </AbsoluteFill>);
};

export const Main = () => {
  const frame = useCurrentFrame();
  return (
    <Boil.Provider value={Math.floor(frame / 5)}>
      <AbsoluteFill style={{background: '#05070f'}}>
        <Audio src={staticFile(data.audio)} />
        {data.scenes.map((sc, i) => (
          <Sequence key={i} from={sc.from} durationInFrames={sc.to - sc.from}><SceneWrap sc={sc} idx={i} /></Sequence>
        ))}
        <Overlay />
      </AbsoluteFill>
    </Boil.Provider>
  );
};
'''

SOURCES = {"src/index.jsx": JS_INDEX, "src/Main.jsx": JS_MAIN, "render.cjs": JS_RENDER}


# ----------------------------------------------------------------------------- helpers
def sh(cmd, cwd=None, check=True, capture=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        console.print((p.stdout or "")[-2500:])
        console.print((p.stderr or "")[-2500:])
        die(f"command failed: {' '.join(map(str, cmd))[:200]}")
    return p


def find_tool(name, root):
    p = shutil.which(name)
    if p:
        return [p]
    base = root / "node_modules" / "@remotion"
    if base.exists():
        for d in base.glob("compositor-*"):
            for n in (name + ".exe", name):
                if (d / n).exists():
                    return [str(d / n)]
    npx = shutil.which("npx")
    if not npx:
        die("npx not found")
    return [npx, "remotion", name]


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# ----------------------------------------------------------------------------- audio analysis
def analyze_samples(s, sr):
    n = len(s)
    dur = n / sr
    ps = [0.0] * (n + 1)
    acc = 0.0
    for i, v in enumerate(s):
        acc += v * v
        ps[i + 1] = acc
    nf = int(math.ceil(dur * FPS))
    hw = sr / FPS
    rms = []
    for i in range(nf):
        c = (i + .5) / FPS * sr
        lo, hi = max(0, int(c - hw)), min(n, int(c + hw))
        rms.append(math.sqrt(max(0.0, ps[hi] - ps[lo]) / max(1, hi - lo)))
    srt = sorted(rms)
    ref = max(srt[int(.95 * (nf - 1))], 1e-5)
    floor = srt[int(.05 * (nf - 1))] / ref
    norm = [min(1.3, r / ref) for r in rms]
    thr = min(.09, max(.03, 4 * floor))
    voiced = [x >= thr for x in norm]
    if True not in voiced:
        die("No speech detected in the audio file.")
    first = voiced.index(True)
    last = nf - 1 - voiced[::-1].index(True)
    sil, i = [], first
    while i <= last:
        if not voiced[i]:
            j = i
            while j <= last and not voiced[j]:
                j += 1
            if (j - i) / FPS >= MIN_SIL:
                sil.append((i / FPS, j / FPS))
            i = j
        else:
            i += 1
    mouth, m = [], 0.0
    for x in norm:
        v = min(1.0, max(0.0, (x - .06) * 1.7))
        m = max(v, m * .8)
        mouth.append(round(m, 3))
    return {"dur": dur, "nf": nf, "mouth": mouth, "sil": sil, "t0": first / FPS, "t1": (last + 1) / FPS, "thr": thr}


def decode_audio(audio, ff, root):
    cmd = ff + ["-v", "error", "-i", str(audio), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    p = subprocess.run(cmd, cwd=root, capture_output=True)
    if p.returncode != 0 or len(p.stdout) < 4:
        die("ffmpeg could not decode the audio:\n" + p.stderr.decode("utf-8", "replace")[-1500:])
    s = array("f")
    s.frombytes(p.stdout[: len(p.stdout) // 4 * 4])
    return s


# ----------------------------------------------------------------------------- scene alignment
def align(sentences, sil, t0, t1):
    """Monotonic DP: place each sentence boundary on the most plausible pause."""
    N = len(sentences)
    if N < 2:
        return []
    w = [len(x.replace(" ", "")) + 5 for x in sentences]
    tot, cum, Ex = float(sum(w)), 0.0, []
    for i in range(N - 1):
        cum += w[i]
        Ex.append(t0 + (t1 - t0) * cum / tot)
    L = t1 - t0
    sigma, win = max(1.5, .05 * L), min(12.0, max(3.5, .15 * L))
    cands = []
    for e in Ex:
        c = []
        for (a, b) in sil:
            m = (a + b) / 2
            if abs(m - e) <= win:
                c.append((m, ((m - e) / sigma) ** 2 - 1.2 * min(b - a, 1.5)))
        c.append((e, 2.5))
        cands.append(c)
    INF = 1e18
    dp = [[INF] * len(c) for c in cands]
    bk = [[-1] * len(c) for c in cands]
    for j, c in enumerate(cands[0]):
        dp[0][j] = c[1]
    for i in range(1, len(cands)):
        for j, c in enumerate(cands[i]):
            best, bi = INF, -1
            for k, pc in enumerate(cands[i - 1]):
                if dp[i - 1][k] < best and pc[0] + MIN_BEAT <= c[0]:
                    best, bi = dp[i - 1][k], k
            if bi >= 0:
                dp[i][j], bk[i][j] = best + c[1], bi
    j = min(range(len(cands[-1])), key=lambda q: dp[-1][q])
    if dp[-1][j] >= INF:
        return Ex
    out = [0.0] * len(cands)
    for i in range(len(cands) - 1, -1, -1):
        out[i] = cands[i][j][0]
        j = bk[i][j]
    return out


def build_timeline(an, scenes):
    total = int(math.ceil((an["dur"] + TAIL_SEC) * FPS))
    flat, owner = [], []
    for si, (_, sents) in enumerate(scenes):
        for s_ in sents:
            flat.append(s_)
            owner.append(si)
    bounds = [round(t * FPS) for t in align(flat, an["sil"], an["t0"], an["t1"])]
    starts = [0] + bounds
    out = []
    for si, (name, sents) in enumerate(scenes):
        idx = [k for k, o in enumerate(owner) if o == si]
        st = starts[idx[0]]
        en = starts[idx[-1] + 1] if idx[-1] + 1 < len(starts) else total
        fr = max(0, st - HALF) if si > 0 else 0
        to = min(total, en + HALF) if si < len(scenes) - 1 else total
        out.append({"id": si, "name": name, "from": fr, "to": to, "start": st, "end": en,
                    "beats": [max(0, starts[k] - fr) for k in idx]})
    return total, out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="delete cached chunks and start over")
    ap.add_argument("--stills", action="store_true", help="render one preview PNG per scene and exit")
    args = ap.parse_args()

    console.print(Panel.fit("[bold]Amar Poribar[/]  |  Remotion 2D hand-drawn horror  |  1080x1920 @ 60 fps  |  audio-locked",
                            border_style="cyan"))
    audio = OUT_DIR / AUDIO_NAME
    root, cache = OUT_DIR / "remotion_project", OUT_DIR / "render_cache"
    final = OUT_DIR / FINAL_NAME

    # 1 ---- environment
    step(1, "Environment")
    if not audio.exists():
        die(f"Audio not found: {audio}")
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        die("Node.js (>=18) and npm are required: https://nodejs.org")
    ver = sh([node, "-v"]).stdout.strip()
    if int(ver.lstrip("v").split(".")[0]) < 18:
        die(f"Node {ver} is too old; need >= 18")
    console.print(f"node {ver} | audio {audio.name} ({audio.stat().st_size/1e6:.2f} MB) | output {OUT_DIR}")
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "public").mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    # 2 ---- dependencies
    step(2, "Dependencies (npm)")
    pj = json.dumps(PACKAGE_JSON, indent=2)
    pj_file, pj_hash = root / "package.json", root / ".pkg_hash"
    need = (not (root / "node_modules" / "@remotion" / "renderer").exists()
            or not pj_file.exists() or pj_file.read_text(encoding="utf-8") != pj)
    if need:
        pj_file.write_text(pj, encoding="utf-8")
        with console.status("[cyan]npm install (first run downloads Remotion, ~1-3 min)..."):
            sh([npm, "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=root)
        console.print("[green]installed[/]")
    else:
        console.print("[green]already installed[/]")
    ffmpeg, ffprobe = find_tool("ffmpeg", root), find_tool("ffprobe", root)

    # 3 ---- audio analysis
    step(3, "Audio analysis (speech envelope + pause map)")
    with console.status("[cyan]decoding and measuring audio at 60 fps..."):
        samples = decode_audio(audio, ffmpeg, root)
        an = analyze_samples(samples, SR)
    console.print(f"duration {an['dur']:.2f}s | speech {an['t0']:.2f}s -> {an['t1']:.2f}s | "
                  f"pauses found {len(an['sil'])} | silence threshold {an['thr']:.3f}")

    # 4 ---- alignment
    step(4, "Scene alignment (audio-locked timeline)")
    scenes = [(n, list(s_)) for n, s_ in SCENES]
    if not TITLE_SPOKEN:
        scenes[0] = (scenes[0][0], scenes[0][1][1:])
    total, tl = build_timeline(an, scenes)
    tb = Table(show_header=True, header_style="bold magenta")
    for c in ("#", "scene", "start", "end", "length", "beats"):
        tb.add_column(c)
    for sc in tl:
        tb.add_row(str(sc["id"]), sc["name"], f"{sc['start']/FPS:6.2f}s", f"{sc['end']/FPS:6.2f}s",
                   f"{(sc['end']-sc['start'])/FPS:5.2f}s", str(len(sc["beats"])))
    console.print(tb)
    console.print(f"total {total} frames = {total/FPS:.3f}s (audio {an['dur']:.3f}s + {TAIL_SEC}s tail)")

    # 5 ---- project
    step(5, "Project build")
    env = an["mouth"] + [0.0] * max(0, total - len(an["mouth"]))
    data = {"fps": FPS, "totalFrames": total, "half": HALF, "tail": int(round(TAIL_SEC * FPS)), "audio": AUDIO_NAME,
            "scenes": [{"id": s["id"], "from": s["from"], "to": s["to"], "beats": s["beats"]} for s in tl],
            "env": env[:total]}
    data_txt = json.dumps(data, separators=(",", ":"))
    (root / "src" / "data.json").write_text(data_txt, encoding="utf-8")
    for rel, txt in SOURCES.items():
        (root / rel).write_text(txt, encoding="utf-8")
    pub = root / "public" / AUDIO_NAME
    if not pub.exists() or file_hash(pub) != file_hash(audio):
        shutil.copyfile(audio, pub)
    sig = hashlib.sha256((file_hash(audio) + data_txt + "".join(SOURCES.values()) +
                          f"{CRF}{JPEG_Q}{CHUNK_FRAMES}").encode("utf-8")).hexdigest()
    sig_file = cache / "signature.txt"
    if args.fresh or not sig_file.exists() or sig_file.read_text().strip() != sig:
        old = list(cache.glob("chunk_*.mp4"))
        if old:
            console.print(f"[yellow]inputs/code changed -> discarding {len(old)} cached chunk(s)[/]")
        for p in cache.glob("*.mp4"):
            p.unlink()
        sig_file.write_text(sig)
    for p in cache.glob("*.part.mp4"):
        p.unlink()
    ranges = [[s, min(s + CHUNK_FRAMES - 1, total - 1)] for s in range(0, total, CHUNK_FRAMES)]
    done_frames = sum(r[1] - r[0] + 1 for i, r in enumerate(ranges) if (cache / f"chunk_{i:04d}.mp4").exists())
    console.print(f"{len(ranges)} chunks of {CHUNK_FRAMES} frames | already rendered: {done_frames}/{total} frames")

    job = {"root": str(root), "cache": str(cache), "ranges": ranges, "crf": CRF, "jpegQuality": JPEG_Q,
           "concurrency": max(2, min(8, (os.cpu_count() or 4) // 2)), "mode": "video"}
    if args.stills:
        sd = OUT_DIR / "stills"
        sd.mkdir(exist_ok=True)
        job.update(mode="stills", stillsDir=str(sd),
                   stills=[min(total - 1, int((s["start"] + s["end"]) / 2)) for s in tl])
    job_file = root / "job.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")

    # 6 ---- render
    step(6, "Rendering stills" if args.stills else "Rendering (resumable)")
    log = open(root / "render.log", "a", encoding="utf-8")
    prog = Progress(SpinnerColumn(), TextColumn("[bold]{task.description}"), BarColumn(bar_width=None),
                    TaskProgressColumn(), TextColumn("{task.completed}/{task.total}"),
                    TimeElapsedColumn(), TimeRemainingColumn(), console=console, refresh_per_second=8)
    proc = subprocess.Popen([node, "render.cjs", str(job_file)], cwd=root, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
    t_bundle = prog.add_task("Bundling project", total=100)
    t_main = prog.add_task("Rendering", total=(len(job.get("stills", [])) or total), completed=0 if args.stills else done_frames, visible=False)
    t_start, session = time.time(), 0
    cur_n, base = 0, done_frames
    try:
        with prog:
            for line in proc.stdout:
                line = line.rstrip()
                if not line.startswith("@@"):
                    log.write(line + "\n")
                    continue
                ev = json.loads(line[2:])
                t = ev["t"]
                if t == "bundle":
                    prog.update(t_bundle, completed=ev["p"])
                elif t == "stage":
                    if ev["m"] == "browser":
                        prog.update(t_bundle, description="Preparing headless Chrome (first run downloads it)")
                    if ev["m"] == "render":
                        prog.update(t_bundle, completed=100, visible=False)
                        prog.update(t_main, visible=True)
                elif t == "skip":
                    prog.update(t_main, description=f"Chunk {ev['i']+1}/{len(ranges)} cached")
                elif t == "start":
                    cur_n = ev["n"]
                    prog.update(t_main, description=f"Chunk {ev['i']+1}/{len(ranges)}")
                elif t == "prog":
                    fr_now = base + ev["rf"]
                    el = max(1e-3, time.time() - t_start)
                    prog.update(t_main, completed=fr_now,
                                description=f"Chunk {ev['i']+1}/{len(ranges)} | {(session + ev['rf'])/el:.1f} fps")
                elif t == "done":
                    base += ev["n"]
                    session += ev["n"]
                    prog.update(t_main, completed=base)
                elif t == "still":
                    prog.update(t_main, completed=ev["i"] + 1, description=f"Still {ev['i']+1}/{ev['n']}")
                elif t == "error":
                    log.write(ev["m"] + "\n")
                    prog.stop()
                    die("render failed:\n" + ev["m"][-2500:])
        proc.wait()
    except KeyboardInterrupt:
        proc.kill()
        console.print("\n[yellow]Interrupted. Finished chunks are saved; run the script again to resume.[/]")
        sys.exit(130)
    log.close()
    if proc.returncode != 0:
        die(f"renderer exited with code {proc.returncode}; see {root / 'render.log'}")
    if args.stills:
        console.print(f"[green]stills saved to {OUT_DIR / 'stills'}[/]")
        return

    # 7 ---- assemble
    step(7, "Assemble, mux original audio, verify")
    chunks = [cache / f"chunk_{i:04d}.mp4" for i in range(len(ranges))]
    missing = [c.name for c in chunks if not c.exists()]
    if missing:
        die(f"missing chunks: {missing[:3]} ... rerun to resume")
    lst = cache / "concat.txt"
    lst.write_text("".join("file '" + c.as_posix().replace("'", "'\\''") + "'\n" for c in chunks), encoding="utf-8")
    cmd = ffmpeg + ["-y", "-v", "error", "-progress", "pipe:1", "-nostats", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                    "-af", "aresample=async=1:first_pts=0", "-movflags", "+faststart", str(final)]
    with Progress(SpinnerColumn(), TextColumn("[bold]Muxing"), BarColumn(bar_width=None), TaskProgressColumn(),
                  console=console) as p2:
        tk = p2.add_task("mux", total=100)
        mp = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace")
        tail = []
        for ln in mp.stdout:
            ln = ln.strip()
            if ln.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    p2.update(tk, completed=min(100, int(ln.split("=")[1]) / 1e6 / (total / FPS) * 100))
                except ValueError:
                    pass
            elif "=" not in ln:
                tail.append(ln)
        mp.wait()
        p2.update(tk, completed=100)
    if mp.returncode != 0:
        die("ffmpeg mux failed:\n" + "\n".join(tail[-15:]))

    pr = subprocess.run(ffprobe + ["-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,duration",
                                   "-of", "json", str(final)], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        streams = json.loads(pr.stdout)["streams"]
        v = next(s for s in streams if s["codec_type"] == "video")
        a = next(s for s in streams if s["codec_type"] == "audio")
        vd, ad = float(v.get("duration", 0)), float(a.get("duration", 0))
        exp = total / FPS
        ok = abs(vd - exp) < .05 and ad >= an["dur"] - .1
        console.print(f"video {v['width']}x{v['height']} {v['r_frame_rate']} {v['codec_name']} {vd:.3f}s (expected {exp:.3f}s) | "
                      f"audio {a['codec_name']} {ad:.3f}s (source {an['dur']:.3f}s) | sync check: "
                      + ("[bold green]PASS[/]" if ok else "[bold red]CHECK[/]"))
    except Exception:
        console.print("[yellow]ffprobe verification skipped[/]")
    console.print(Panel.fit(f"[bold green]Done[/]  {final}\nChunk cache kept in {cache}", border_style="green"))


if __name__ == "__main__":
    main()
