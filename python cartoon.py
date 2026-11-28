#!/usr/bin/env python3
"""
Slenderman 2D horror animation  -  Remotion + Python (single file)
1080x1920 (9:16) | 60 fps | audio-driven | chunked, resumable renders
Usage:   python make_slenderman.py            (renders / resumes)
         python make_slenderman.py --fresh    (discard cached chunks)
         python make_slenderman.py --analyze-only
Needs:   Node.js 18+, ffmpeg + ffprobe on PATH.
"""
import os, sys, re, json, math, time, shutil, subprocess, hashlib, array
from pathlib import Path

OUT_DIR = Path(os.environ.get("SLENDER_OUT", r"C:\Users\laptop villa\Documents\cnd"))
FPS, CHUNK = 60, 300                      # 300 frames (5 s) per resumable chunk
FINAL = "Slenderman_final.mp4"

SCENES = [  # story split into 11 beats; timing of each is derived from the audio
 "“THERE IT IS AGAIN!” For days, I’ve seen the same thing: a towering, impossibly thin man in a black suit. No face. No expression. He only stands still… watching me. Now he’s in my dreams, too.",
 "I searched for him online. One name kept appearing: Slenderman. A myth, people said. But how could a myth follow me? I barely sleep or leave home.",
 "At night, I hear slow footsteps outside my room. The doors open by themselves. Whenever they do, the air turns freezing cold. Every time I look, nobody is there. The creaks sounded like footsteps, not a settling house. Even outside my room, I felt watched.",
 "Today, I went outside for fresh air. For a while, everything felt normal. Then, on a quiet woodland path, I found a spotless sheet of paper. On it was a rough drawing of the faceless man, surrounded by the same words: “NO. NO. NO.” The sky suddenly darkened. I hurried home, staring at it.",
 "That night, he returned in my dream. I was frozen in bed as his impossibly long arm reached towards me. Strange tendrils covered my eyes. When I woke, my room was empty—but my laptop, television and phone had all started malfunctioning. Static. Sudden shutdowns. No signal. I burned it.",
 "I watched it turn to ash. But the next morning, another copy was waiting in my mailbox.",
 "Then came more drawings. I kept glimpsing a tall shape in mirrors and at the edge of my vision.",
 "I locked the doors and windows, bringing food and water into my room. I thought I was safe.",
 "At midnight, a heavy THUD shook the room. The lights wouldn’t work. In the darkness, one corner looked darker than the rest. And then… it moved.",
 "A tall, thin silhouette emerged. A black suit. No face. It was him. I couldn’t move. Just like in the nightmare, his arm stretched across the room. Tendrils reached towards me, spreading over my body and climbing towards my face. I shut my eyes, terrified. But just before the darkness covered them, I forced them open.",
 "He was standing over my bed. Faceless… yet somehow, I knew he was smiling—again.",
]

# ----------------------------------------------------------------- Remotion sources
INDEX_JSX = r"""import {registerRoot} from 'remotion';
import {Root} from './Root';
registerRoot(Root);
"""
ROOT_JSX = r"""import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Main';
import D from './data.json';
export const Root = () => <Composition id="Main" component={Main} durationInFrames={D.frames} fps={D.fps} width={1080} height={1920} />;
"""
RENDER_MJS = r"""import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import fs from 'fs';
import path from 'path';
const cfg = JSON.parse(fs.readFileSync('plan.json', 'utf8'));
const serveUrl = await bundle({entryPoint: path.resolve('src/index.jsx'), publicDir: path.resolve('public')});
const composition = await selectComposition({serveUrl, id: 'Main'});
for (const c of cfg.chunks) {
  const out = path.join(cfg.dir, 'chunk_' + String(c.i).padStart(4, '0') + '.mp4');
  if (fs.existsSync(out)) { console.log('SKIP ' + c.i); continue; }
  const tmp = out + '.part.mp4';
  await renderMedia({
    composition, serveUrl, codec: 'h264', outputLocation: tmp, frameRange: [c.a, c.b],
    muted: true, crf: 16, pixelFormat: 'yuv420p', concurrency: cfg.concurrency,
    onProgress: ({progress}) => console.log('PROG ' + c.i + ' ' + progress.toFixed(4)),
  });
  fs.renameSync(tmp, out);
  console.log('DONE ' + c.i);
}
console.log('ALLDONE');
process.exit(0);
"""

MAIN_JSX = r"""import React from 'react';
import {AbsoluteFill, Audio, staticFile, useCurrentFrame} from 'remotion';
import D from './data.json';

const W = 1080, H = 1920;
const INK = '#080a14', SUIT = '#06070d', RIM = '#2c3764', PALE = '#ecdc8f';
const SKIN = '#b9a591', SKIN2 = '#8d7a6b', WOOD = '#4b3626', WOOD2 = '#33241a', WOOD3 = '#6a4d36';
const cl = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => { t = cl(t); return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
const rnd = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const ln = {stroke: INK, strokeWidth: 7, strokeLinejoin: 'round', strokeLinecap: 'round'};

/* ---------------------------------------------------------------- Slender */
const Slender = ({x, y, s, op, reach = 0, rt = [0, 0], tend = 0, smile = 0, f, part = 'body'}) => {
  if (op < .01) return null;
  const lx = (rt[0] - x) / s, ly = (rt[1] - y) / s;
  const sw = Math.sin(f / 45) * 4;
  if (part === 'tend') {
    if (tend <= 0.01) return null;
    return <g transform={`translate(${x} ${y}) scale(${s})`} opacity={op}>
      {Array.from({length: 9}, (_, k) => {
        const tx = lx + (rnd(k + 1) - .5) * 240, ty = ly + (rnd(k + 7) - .5) * 280;
        const ox = (k % 2 ? 1 : -1) * 22, oy = -575, g = cl(tend * 1.3 - rnd(k) * .3);
        const dx = tx - ox, dy = ty - oy, d = Math.hypot(dx, dy) || 1, px = -dy / d, py = dx / d;
        let dd = '';
        for (let i = 0; i <= 16; i++) {
          const u = (i / 16) * g, wv = Math.sin(f / 9 + i * .8 + k * 2) * 22 * u;
          dd += (i ? 'L' : 'M') + (lerp(ox, tx, u) + px * wv).toFixed(1) + ' ' + (lerp(oy, ty, u) + py * wv).toFixed(1);
        }
        return <g key={k} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d={dd} stroke={RIM} strokeWidth={9 + (k % 3) * 2} /><path d={dd} stroke={SUIT} strokeWidth={5 + (k % 3) * 2} />
        </g>;
      })}
    </g>;
  }
  const arm = (sd) => {
    const S = [sd * 30, -580], hang = [sd * 48 + sw * sd, -190];
    const h = sd === 1 ? [lerp(hang[0], lx, reach), lerp(hang[1], ly, reach)] : hang;
    const el = [(S[0] + h[0]) / 2 + sd * 18, (S[1] + h[1]) / 2 + 60 * (1 - (sd === 1 ? reach : 0)) + Math.sin(f / 20) * 5];
    const d = `M${S[0]} ${S[1]} Q${el[0]} ${el[1]} ${h[0]} ${h[1]}`;
    const base = Math.atan2(h[1] - el[1], h[0] - el[0]);
    return <g key={sd} fill="none" strokeLinecap="round">
      <path d={d} stroke={RIM} strokeWidth="19" /><path d={d} stroke={SUIT} strokeWidth="14" />
      {[0, 1, 2, 3, 4].map(i => {
        const a = base + (i - 2) * .3 + Math.sin(f / 15 + i) * .05, L = 62 - Math.abs(i - 2) * 6;
        return <path key={i} d={`M${h[0]} ${h[1]} L${h[0] + Math.cos(a) * L} ${h[1] + Math.sin(a) * L}`} stroke={SUIT} strokeWidth="4" />;
      })}
    </g>;
  };
  return <g transform={`translate(${x} ${y}) scale(${s})`} opacity={op} stroke={RIM} strokeWidth="4" strokeLinejoin="round">
    <path d="M-24 -250 L24 -250 L20 0 L4 0 L0 -220 L-4 0 L-20 0Z" fill={SUIT} />
    {arm(-1)}
    <path d="M-38 -592 Q0 -606 38 -592 L34 -250 L-34 -250Z" fill={SUIT} />
    <path d="M-11 -596 L0 -520 L11 -596Z" fill="#d6d0c2" stroke="none" />
    <path d="M-4 -560 L4 -560 L8 -420 L0 -400 L-8 -420Z" fill="#0b0b10" stroke="none" />
    {arm(1)}
    <rect x="-9" y="-628" width="18" height="40" fill="#cfc8b8" />
    <ellipse cx="0" cy="-662" rx="34" ry="48" fill="#d9d3c4" />
    <path d="M10 -705 Q40 -670 18 -618 Q30 -660 10 -705Z" fill="#000" opacity=".15" stroke="none" />
    {smile > 0 && <path d="M-22 -648 Q0 -618 22 -648" fill="none" stroke="#6f695e" strokeWidth="3.5" opacity={smile} />}
  </g>;
};

/* ---------------------------------------------------------------- Protagonist */
const Prot = ({x, y, s, e, f, fear, look, eye = 1, body = 330, shadow = true}) => {
  const trem = fear * 2.2 * Math.sin(f * 1.9) + fear * 1.2 * Math.sin(f * 3.1);
  const br = Math.sin(f / 38) * 3, t = (f + 53) % 200, bl = t < 9 ? 1 - Math.abs(t - 4.5) / 4.5 : 0;
  const open = cl(eye, 0, 1.5) * (1 - bl) * (1 + fear * .3);
  const lx = look[0] * 9 + Math.sin(f * .7) * fear * 2.2, ly = look[1] * 8 + Math.cos(f * .9) * fear * 1.8;
  return <g transform={`translate(${x + trem} ${y + br}) scale(${s * (1 + e * .012)})`}>
    {shadow && <ellipse cx="-250" cy="60" rx="120" ry="190" fill="#000" opacity=".3" />}
    <path d={`M-160 ${body + 80} Q-165 150 -70 118 L70 118 Q165 150 160 ${body + 80}Z`} fill="#2b3658" {...ln} />
    <path d="M-40 135 L-34 230 M40 135 L34 230" stroke={INK} strokeWidth="5" />
    <rect x="-28" y="80" width="56" height="52" fill={SKIN2} {...ln} strokeWidth="6" />
    <circle cx="-92" cy="8" r="16" fill={SKIN} {...ln} strokeWidth="5" /><circle cx="92" cy="8" r="16" fill={SKIN2} {...ln} strokeWidth="5" />
    <ellipse cx="0" cy="0" rx="92" ry="104" fill={SKIN} {...ln} />
    <path d="M24 -100 Q100 -80 90 20 Q78 92 24 104Z" fill="#000" opacity=".16" />
    <path d="M-100 -8 Q-118 -122 0 -128 Q118 -122 100 -8 Q84 -72 22 -84 Q-40 -64 -100 -8Z" fill="#1d1510" {...ln} />
    <path d="M-60 -92 L-72 -120 M-10 -104 L-6 -138 M42 -98 L58 -126" stroke={INK} strokeWidth="7" strokeLinecap="round" />
    {[-1, 1].map(sd => <g key={sd} transform={`translate(${sd * 40} -4)`}>
      <ellipse rx="25" ry={26 * open + 1} fill="#e8e2d2" {...ln} strokeWidth="5" />
      {open > .25 && <circle cx={lx} cy={ly} r={Math.max(3, 6.5 - fear * 2.5)} fill={INK} />}
      <path d={`M-28 ${28 * Math.min(open, 1.2) + 10} Q0 ${28 * Math.min(open, 1.2) + 24} 28 ${28 * Math.min(open, 1.2) + 10}`} stroke="#5b4b58" strokeWidth="5" fill="none" opacity=".75" />
    </g>)}
    {[-1, 1].map(sd => <path key={sd} d={`M${sd * 68} ${-44 - fear * 6} L${sd * 14} ${-58 - fear * 24}`} stroke="#1a130f" strokeWidth="10" strokeLinecap="round" />)}
    <path d="M-4 14 Q-15 34 5 37" fill="none" stroke={SKIN2} strokeWidth="5" strokeLinecap="round" />
    <ellipse cx="0" cy={64} rx={17 + e * 9} ry={3 + e * 30} fill="#2a1215" {...ln} strokeWidth="5" />
  </g>;
};

/* ---------------------------------------------------------------- Backgrounds */
const Room = ({f, door = 0, lock, supplies, drawings = 0, mirrorOp = 0, lampOn = 1}) => {
  const dx = 50 + 230 * (1 - .72 * door);
  const sheets = [[330, 760, -8], [470, 800, 5], [620, 745, -4], [740, 820, 7], [400, 880, 3], [560, 880, -6]];
  return <g>
    <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#090e2b" /><stop offset="1" stopColor="#1d2a55" /></linearGradient>
    <rect width={W} height={1320} fill="url(#wall)" />
    {Array.from({length: 14}, (_, i) => <rect key={i} x={i * 80 + 20} width="14" height={1320} fill="#fff" opacity=".025" />)}
    <rect y={1320} width={W} height={600} fill={WOOD2} />
    {[40, 95, 165, 250, 355, 480, 630].map((o, i) => <path key={i} d={`M0 ${1320 + o}H${W}`} stroke={INK} strokeWidth="4" opacity=".55" />)}
    <path d="M0 1320H1080" {...ln} />
    <polygon points="770,1320 1050,1320 330,1740 20,1700" fill="#000" opacity=".34" />
    <polygon points="250,1560 950,1560 300,1900 0,1900" fill="#000" opacity=".3" />
    {/* window */}
    <rect x="430" y="250" width="270" height="400" fill="#1c2c5c" {...ln} />
    <circle cx="610" cy="380" r="46" fill="#e9e3b8" opacity=".8" />
    <path d="M565 250V650M430 450H700" {...ln} />
    <rect x="410" y="640" width="310" height="26" fill={WOOD3} {...ln} />
    <path d="M410 240Q380 450 395 660L440 650Q430 450 450 250Z" fill="#3a2a2f" {...ln} />
    <path d="M720 240Q750 450 735 660L690 650Q700 450 680 250Z" fill="#3a2a2f" {...ln} />
    {/* door */}
    <rect x="50" y="430" width="230" height="890" fill="#010206" {...ln} />
    <path d={`M50 430L${dx} ${430 - 30 * door}L${dx} ${1320 + 20 * door}L50 1320Z`} fill={WOOD} {...ln} />
    <circle cx={dx - 20} cy="900" r="12" fill={PALE} {...ln} strokeWidth="4" />
    {door > .05 && <ellipse cx="170" cy="1300" rx="190" ry="60" fill="#b8d4ff" opacity={door * .16} />}
    {lock && <g><rect x="30" y="860" width="270" height="30" fill={WOOD3} {...ln} /><path d="M60 890Q100 960 140 890" fill="none" {...ln} /></g>}
    {/* wardrobe + mirror */}
    <rect x="770" y="330" width="290" height="990" fill={WOOD} {...ln} />
    <path d="M915 340V1310M790 360H895V780H790ZM935 360H1040V780H935Z" fill="none" {...ln} strokeWidth="5" />
    <circle cx="900" cy="900" r="9" fill={PALE} /><circle cx="930" cy="900" r="9" fill={PALE} />
    <clipPath id="mclip"><ellipse cx="910" cy="650" rx="86" ry="170" /></clipPath>
    <ellipse cx="910" cy="650" rx="86" ry="170" fill="#22305a" />
    <g clipPath="url(#mclip)"><Slender x={910} y={830} s={.4} op={mirrorOp} f={f} /></g>
    <ellipse cx="910" cy="650" rx="92" ry="176" fill="none" stroke={WOOD3} strokeWidth="14" /><ellipse cx="910" cy="650" rx="99" ry="183" fill="none" {...ln} strokeWidth="5" />
    {/* drawings on wall */}
    {sheets.slice(0, drawings).map(([sx, sy, r], i) => <g key={i} transform={`translate(${sx} ${sy}) rotate(${r})`}>
      <rect x="-50" y="-65" width="100" height="130" fill="#e6dfca" {...ln} strokeWidth="4" />
      <path d="M0 -45V25M-12 -30H12M0 -35L-14 20M0 -35L14 20M0 25L-8 52M0 25L8 52" stroke="#222" strokeWidth="3" fill="none" /><circle cx="0" cy="-52" r="8" fill="none" stroke="#222" strokeWidth="3" />
    </g>)}
    {/* bed */}
    <rect x="250" y="940" width="700" height="340" rx="30" fill={WOOD} {...ln} />
    <rect x="290" y="985" width="620" height="250" rx="18" fill="none" stroke={WOOD2} strokeWidth="6" />
    <path d="M230 1240Q580 1200 960 1240L990 1580H200Z" fill="#26304f" {...ln} />
    <ellipse cx="470" cy="1255" rx="120" ry="42" fill="#3a4568" {...ln} /><ellipse cx="690" cy="1255" rx="120" ry="42" fill="#3a4568" {...ln} />
    {/* nightstand + lamp */}
    <rect x="950" y="1290" width="140" height="300" fill={WOOD} {...ln} /><path d="M950 1380H1090" {...ln} />
    <rect x="990" y="1210" width="22" height="80" fill={WOOD3} {...ln} strokeWidth="5" />
    <path d="M955 1215L1050 1215L1030 1115L975 1115Z" fill={lampOn > .3 ? PALE : '#6b6340'} {...ln} />
    {supplies && <g><rect x="965" y="1245" width="26" height="48" rx="6" fill="#7f9cc4" {...ln} strokeWidth="4" /><ellipse cx="1040" cy="1285" rx="34" ry="12" fill="#9b8a66" {...ln} strokeWidth="4" /></g>}
  </g>;
};

const Woods = ({f, mail, ash}) => <g>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#0a1130" /><stop offset="1" stopColor="#6a583a" /></linearGradient>
  <rect width={W} height={1150} fill="url(#sky)" /><circle cx="800" cy="300" r="70" fill="#efe6b8" opacity=".75" />
  <rect y="1040" width={W} height="880" fill="#231a11" />
  {Array.from({length: 9}, (_, i) => <rect key={i} x={i * 140 - 20 + rnd(i) * 40} y="0" width={36 + rnd(i + 3) * 20} height={1100} fill="#0e1733" />)}
  <path d="M330 1920L770 1920L575 1040L525 1040Z" fill="#4d4030" {...ln} />
  <path d="M440 1700Q550 1660 660 1700M470 1450Q550 1430 620 1450" stroke={INK} strokeWidth="4" fill="none" opacity=".5" />
  {[70, 300, 830, 1010].map((tx, i) => <g key={i}>
    <rect x={tx - 50 - i * 6} y="0" width={110 + i * 12} height="1700" fill="#07090f" {...ln} />
    <path d={`M${tx} ${400 + i * 130}Q${tx + 90 * (i % 2 ? -1 : 1)} ${330 + i * 130} ${tx + 170 * (i % 2 ? -1 : 1)} ${300 + i * 130}`} stroke="#07090f" strokeWidth="18" fill="none" strokeLinecap="round" />
  </g>)}
  <rect y="1000" width={W} height="260" fill="#cfd8ff" opacity=".06" />
  {mail && <g>
    <rect x="195" y="1150" width="28" height="500" fill={WOOD} {...ln} />
    <path d="M110 1170V1090Q110 1040 200 1040Q290 1040 290 1090V1170Z" fill="#3a4766" {...ln} />
    <rect x="268" y="1060" width="14" height="80" fill="#8a3b32" {...ln} strokeWidth="4" />
    <rect x="240" y="1120" width="70" height="100" fill="#ebe4d0" transform="rotate(-8 240 1120)" {...ln} strokeWidth="4" />
  </g>}
  {ash && <g><ellipse cx="640" cy="1560" rx="70" ry="14" fill="#2a2a2a" />
    {Array.from({length: 16}, (_, i) => { const t = ((f * 1.2 + i * 31) % 520) / 520; return <circle key={i} cx={640 + Math.sin(f / 30 + i) * 40 + i * 5 - 40} cy={1550 - t * 520} r={3 + rnd(i) * 4} fill="#9a9a96" opacity={(1 - t) * .8} />; })}</g>}
</g>;

const Paper = ({k}) => k <= 0 ? null : <g transform={`translate(540 1060) rotate(-4) scale(${lerp(.6, 1.35, ease(k))})`} opacity={cl(k * 3)}>
  <rect x="-170" y="-230" width="340" height="460" fill="#ebe4d0" {...ln} />
  <g stroke="#2a2a2a" strokeWidth="6" fill="none" strokeLinecap="round"><circle cx="0" cy="-120" r="22" /><path d="M0 -98V60M-30 -70L30 -70M0 -80L-40 40M0 -80L40 40M0 60L-18 190M0 60L18 190" /></g>
  <g fill="#7d1f1f" fontFamily="'Segoe Print','Comic Sans MS',cursive" fontSize="36" fontWeight="700" textAnchor="middle">
    <text x="0" y="-188">NO. NO. NO.</text><text x="0" y="214">NO. NO. NO.</text>
    <text transform="translate(-140 0) rotate(-90)">NO. NO. NO.</text><text transform="translate(145 0) rotate(90)">NO. NO. NO.</text>
  </g>
</g>;

const Glitch = ({f, k}) => { const g = Math.floor(f / 3); return <g opacity={k}>
  {Array.from({length: 10}, (_, i) => <rect key={i} y={rnd(g * 9 + i) * H} width={W} height={4 + rnd(g + i * 3) * 60} fill={i % 3 ? '#bfe' : '#f55'} opacity={.1 + rnd(g + i) * .25} transform={`translate(${(rnd(g * 3 + i) - .5) * 60} 0)`} style={{mixBlendMode: 'screen'}} />)}
  <rect width={W} height={H} fill="#fff" opacity={rnd(g) > .85 ? .22 : 0} /></g>; };

/* ---------------------------------------------------------------- Scene table (p = progress 0..1 inside the scene) */
const SC = [
  {bg: 'room', cam: [330, 1150, 1.05, 430, 1110, 1.4], door: () => .85, fear: p => .3 + .35 * p, look: () => [-1, .1],
    sl: p => ({x: 165, y: 1320, s: .8, op: .12 + .6 * ease(p)})},
  {bg: 'room', cam: [540, 1250, 1.1, 560, 1100, 1.55], lamp: () => .8, laptop: 1, fear: p => .35 + .3 * p, look: () => [0, .6],
    sl: p => ({x: 565, y: 650, s: .42, op: cl((p - .45) * 2) * .7})},
  {bg: 'room', cam: [600, 1150, 1.1, 260, 1000, 1.5], cold: 1, lamp: () => .8, fear: p => .5 + .4 * p, look: () => [-1, -.1],
    door: (p, f) => ease(cl(p * 1.8)) * (.75 + .25 * Math.sin(f / 40))},
  {bg: 'woods', cam: [540, 1250, 1.0, 600, 1100, 1.45], dark: p => cl((p - .55) * 3) * .55, fear: p => .25 + .65 * p,
    look: p => [p > .3 ? -.6 : .6, .4], paper: p => ease(cl((p - .36) / .12)) * (1 - ease(cl((p - .78) / .1))),
    sl: p => ({x: 250, y: 1060, s: .55, op: cl((p - .72) * 3) * .6})},
  {bg: 'room', cam: [500, 1150, 1.1, 560, 1050, 1.6], fear: p => .6 + .35 * p, look: () => [-1, 0],
    lamp: (p, f) => p < .45 ? .5 : .2 + .8 * (rnd(Math.floor(f / 5)) > .5 ? 1 : 0),
    eye: p => p < .45 ? 1 - ease(cl((p - .3) / .12)) * .9 : 1,
    glitch: (p, f) => p > .5 && rnd(Math.floor(f / 7)) > .3 ? 1 : 0,
    sl: p => ({x: 330, y: 1390, s: 1.1, op: p < .45 ? .9 : cl(1 - (p - .45) * 12), reach: ease(cl(p / .4)), rt: [560, 1060], tend: p < .45 ? cl((p - .2) / .25) : 0})},
  {bg: 'woods', mail: 1, ash: 1, px: 720, cam: [350, 1250, 1.0, 330, 1280, 1.45], dark: () => .12, fear: () => .55, look: () => [-1, .3],
    sl: p => ({x: 545, y: 1050, s: .32, op: cl((p - .6) * 3) * .5})},
  {bg: 'room', cam: [880, 800, 1.15, 700, 900, 1.3], drawings: p => Math.floor(2 + p * 4.99), lamp: () => .7, fear: () => .7,
    look: (p, f) => [Math.sin(f / 20), Math.cos(f / 33) * .5], mirrorOp: (p, f) => rnd(Math.floor(f / 9)) > .55 ? .75 : 0,
    sl: (p, f) => ({x: 1050, y: 1330, s: .8, op: rnd(Math.floor(f / 11) + 5) > .8 ? .55 : 0})},
  {bg: 'room', cam: [540, 1200, 1.05, 560, 1150, 1.25], lock: 1, supplies: 1, lamp: () => .85, fear: p => .6 - .2 * p, look: (p, f) => [Math.sin(f / 90), .2]},
  {bg: 'room', cam: [350, 1200, 1.0, 170, 1230, 1.55], lock: 1, supplies: 1, fear: p => .7 + .25 * p, look: () => [-1, .3],
    lamp: (p, f) => p < .22 ? 1 : p < .32 ? (rnd(Math.floor(f / 3)) > .5 ? .6 : 0) : 0,
    shake: p => p > .22 ? Math.max(0, 1 - (p - .22) * 30) * 22 : 0,
    sl: p => ({x: 120, y: 1320, s: .85, op: cl((p - .5) * 3) * .5})},
  {bg: 'room', cam: [400, 1150, 1.0, 520, 1060, 1.5], lock: 1, supplies: 1, fear: p => .9 + .1 * p, look: () => [-1, 0],
    lamp: (p, f) => .1 + .08 * rnd(Math.floor(f / 4)),
    eye: p => p < .5 ? 1 : p < .88 ? 1 - ease(cl((p - .5) / .08)) : 1.4,
    sl: p => ({x: lerp(120, 430, ease(p * 1.2)), y: 1400, s: lerp(.85, 1.2, p), op: .92, reach: ease(cl((p - .1) / .5)), rt: [560, 1070],
      tend: p < .8 ? ease(cl((p - .3) / .5)) : 1 - .4 * ease(cl((p - .8) / .1))})},
  {bg: 'room', cam: [560, 800, 1.0, 560, 620, 1.9], lock: 1, supplies: 1, lamp: () => .15, fear: () => 1, eye: () => 1.35, look: () => [0, -.2],
    sl: p => ({x: 560, y: 1400, s: 1.45, op: .95, smile: ease(cl((p - .5) / .3))})},
];

/* ---------------------------------------------------------------- Main */
export const Main = () => {
  const f = useCurrentFrame(), B = D.bounds;
  let i = 0; while (i < SC.length - 1 && f >= B[i + 1]) i++;
  const sc = SC[i], p = cl((f - B[i]) / (B[i + 1] - B[i]));
  const e = D.env[Math.min(f, D.env.length - 1)] || 0;
  const room = sc.bg === 'room';
  const fear = sc.fear(p, f), look = sc.look(p, f), eye = sc.eye ? sc.eye(p, f) : 1;
  const lamp0 = sc.lamp ? sc.lamp(p, f) : 1, lamp = cl(lamp0 * (1 - .1 * rnd(Math.floor(f / 3)) + .03 * Math.sin(f / 9)));
  const sl = sc.sl ? sc.sl(p, f) : null;
  const P = room ? {x: 560, y: 1060, s: 1, body: 330} : {x: sc.px || 700, y: 1000, s: .95, body: 640};

  const [x0, y0, z0, x1, y1, z1] = sc.cam;
  const z = lerp(z0, z1, p) * (1 + e * .004);
  const cx = cl(lerp(x0, x1, p) + Math.sin(f / 70) * 4, 540 / z, W - 540 / z), cy = cl(lerp(y0, y1, p) + Math.cos(f / 90) * 4, 960 / z, H - 960 / z);
  const sh = sc.shake ? sc.shake(p) : 0, shx = Math.sin(f * 2.3) * sh, shy = Math.cos(f * 3.1) * sh;

  let dip = 0; for (const b of B.slice(1, -1)) dip = Math.max(dip, cl(1 - Math.abs(f - b) / 9));
  dip = Math.max(dip, cl(1 - f / 20), cl(1 - (D.frames - 1 - f) / 40));
  const boil = Math.floor(f / 5) % 6 + 1;
  const sd = sl ? {...sl, f} : null;

  return <AbsoluteFill style={{background: '#02030a'}}>
    <Audio src={staticFile('voice.mp3')} />
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <defs>
        <filter id="wob" x="-3%" y="-3%" width="106%" height="106%"><feTurbulence type="fractalNoise" baseFrequency="0.012 0.018" numOctaves="2" seed={boil} result="n" /><feDisplacementMap in="SourceGraphic" in2="n" scale="9" xChannelSelector="R" yChannelSelector="G" /></filter>
        <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="1" seed={Math.floor(f / 2) % 50} /><feColorMatrix type="saturate" values="0" /></filter>
        <radialGradient id="lampg" gradientUnits="userSpaceOnUse" cx="1000" cy="1130" r="1250"><stop offset="0" stopColor="#030510" stopOpacity="0" /><stop offset=".28" stopColor="#030510" stopOpacity=".35" /><stop offset=".65" stopColor="#020310" stopOpacity=".78" /><stop offset="1" stopColor="#010206" stopOpacity=".94" /></radialGradient>
        <radialGradient id="glow"><stop offset="0" stopColor={PALE} stopOpacity=".8" /><stop offset="1" stopColor={PALE} stopOpacity="0" /></radialGradient>
        <radialGradient id="screen"><stop offset="0" stopColor="#9ec8ff" stopOpacity=".7" /><stop offset="1" stopColor="#9ec8ff" stopOpacity="0" /></radialGradient>
        <radialGradient id="vig" cx=".5" cy=".5" r=".75"><stop offset=".55" stopColor="#000" stopOpacity="0" /><stop offset="1" stopColor="#000" stopOpacity=".7" /></radialGradient>
      </defs>
      <g filter="url(#wob)"><g transform={`translate(${540 + shx} ${960 + shy}) scale(${z}) translate(${-cx} ${-cy})`}>
        {room ? <Room f={f} door={sc.door ? sc.door(p, f) : 0} lock={sc.lock} supplies={sc.supplies} drawings={sc.drawings ? sc.drawings(p) : 0} mirrorOp={sc.mirrorOp ? sc.mirrorOp(p, f) : 0} lampOn={lamp} />
          : <Woods f={f} mail={sc.mail} ash={sc.ash} />}
        {sd && <Slender {...sd} part="body" />}
        <Prot x={P.x} y={P.y} s={P.s} e={e} f={f} fear={fear} look={look} eye={eye} body={P.body} shadow={room} />
        {room && <g>
          <path d="M215 1300Q500 1240 910 1305L950 1580H190Z" fill="#2b365c" {...ln} />
          <path d="M300 1380Q330 1450 300 1560M600 1330Q630 1450 590 1570M820 1360Q850 1450 830 1560" stroke={INK} strokeWidth="5" fill="none" opacity=".6" />
          {sc.laptop && <g><rect x="450" y="1270" width="220" height="150" rx="8" fill="#39415a" {...ln} /><circle cx="560" cy="1345" r="12" fill="#cfe3ff" opacity=".7" /></g>}
        </g>}
        {sd && <Slender {...sd} part="tend" />}
        {sc.paper && <Paper k={sc.paper(p)} />}
        {sc.cold && Array.from({length: 5}, (_, k) => { const t = ((f / 60) * .9 + k / 5) % 1; return <circle key={k} cx={555 - t * 50} cy={1125 - t * 60} r={14 + t * 46} fill="#dfeaff" opacity={(1 - t) * .3} />; })}
        {/* lighting */}
        {room ? <g>
          <rect x="-200" y="-200" width={W + 400} height={H + 400} fill="#02030a" opacity={(1 - lamp) * .9} />
          <rect x="-200" y="-200" width={W + 400} height={H + 400} fill="url(#lampg)" opacity={lamp} />
          <circle cx="1000" cy="1130" r="520" fill="url(#glow)" opacity={.5 * lamp} style={{mixBlendMode: 'screen'}} />
          {sc.laptop && <circle cx="560" cy="1120" r="300" fill="url(#screen)" opacity={.5 + .1 * Math.sin(f / 5)} style={{mixBlendMode: 'screen'}} />}
        </g> : <rect x="-200" y="-200" width={W + 400} height={H + 400} fill="#02030a" opacity={.3 + (sc.dark ? sc.dark(p) : 0)} />}
      </g></g>
      {sc.glitch && <Glitch f={f} k={sc.glitch(p, f)} />}
      <rect width={W} height={H} fill="url(#vig)" />
      <rect width={W} height={H} filter="url(#grain)" opacity=".09" style={{mixBlendMode: 'overlay'}} />
      <rect width={W} height={H} fill="#000" opacity={dip} />
    </svg>
  </AbsoluteFill>;
};
"""

# ----------------------------------------------------------------- helpers
def die(msg):
    print(f"\n[ERROR] {msg}"); sys.exit(1)

def step(n, total, title):
    print(f"\n[{n}/{total}] {title}\n" + "-" * 60)

def fmt_t(s):
    s = int(max(0, s)); return f"{s//3600:d}:{s%3600//60:02d}:{s%60:02d}" if s >= 3600 else f"{s//60:02d}:{s%60:02d}"

def find_audio():
    cands = [p for p in OUT_DIR.glob("*") if p.suffix.lower() == ".mp3"]
    for p in cands:
        if p.name.lower() == "elevenlabs.mp3": return p
    if cands: return max(cands, key=lambda p: p.stat().st_mtime)
    die(f"No .mp3 found in {OUT_DIR}. Put 'Elevenlabs.mp3' there.")

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

# ----------------------------------------------------------------- audio analysis
def analyze(audio):
    sr = 16000
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
                         stdout=subprocess.PIPE, check=True).stdout
    smp = array.array("h"); smp.frombytes(pcm[: len(pcm) // 2 * 2])
    dur = len(smp) / sr
    n = math.ceil(dur * FPS)
    rms = []
    for i in range(n):
        a, b = int(i * sr / FPS), int((i + 1) * sr / FPS)
        seg = smp[a:b] or [0]
        rms.append(math.sqrt(sum(x * x for x in seg) / len(seg)))
    srt = sorted(rms); ref = max(srt[int(len(srt) * .95)], 1.0)
    raw = [min(1.0, r / ref) for r in rms]
    env, cur = [], 0.0                              # attack / release smoothing -> natural mouth motion
    for v in raw:
        cur = cur + (v - cur) * (.65 if v > cur else .28); env.append(round(cur ** .85, 3))
    voiced = [v > .06 for v in raw]
    first = voiced.index(True) if True in voiced else 0
    last = n - 1 - voiced[::-1].index(True) if True in voiced else n - 1
    pauses, i = [], first                            # (center, length) of silences inside the speech
    while i <= last:
        if not voiced[i]:
            j = i
            while j <= last and not voiced[j]: j += 1
            if j - i >= 10: pauses.append(((i + j) // 2, j - i))
            i = j
        else: i += 1
    w = [len(t) for t in SCENES]; tot = sum(w); cum = 0; bounds = [0]
    for k in range(len(SCENES) - 1):                 # cut scenes on the best pause near the proportional target
        cum += w[k]; target = first + (last - first) * cum / tot
        best, bs = int(target), -1e9
        for c, l in pauses:
            if abs(c - target) < 150 and c > bounds[-1] + 90:
                sc = l - abs(c - target) / 6
                if sc > bs: best, bs = c, sc
        bounds.append(max(best, bounds[-1] + 90))
    bounds.append(n)
    print(f"  audio length : {dur:.3f}s  ->  {n} frames @ {FPS} fps")
    print(f"  speech       : {first/FPS:.2f}s - {last/FPS:.2f}s   | pauses found: {len(pauses)}")
    for k in range(len(SCENES)):
        print(f"  scene {k+1:02d}     : {bounds[k]/FPS:7.2f}s -> {bounds[k+1]/FPS:7.2f}s  ({SCENES[k][:38]}…)")
    return {"fps": FPS, "frames": n, "duration": dur, "bounds": bounds, "env": env}

# ----------------------------------------------------------------- project
def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")

def setup_project(proj, audio, data):
    put(proj / "src" / "index.jsx", INDEX_JSX); put(proj / "src" / "Root.jsx", ROOT_JSX)
    put(proj / "src" / "Main.jsx", MAIN_JSX); put(proj / "render.mjs", RENDER_MJS)
    put(proj / "src" / "data.json", json.dumps(data, separators=(",", ":")))
    put(proj / "package.json", json.dumps({"name": "slender", "private": True, "version": "1.0.0"}))
    dst = proj / "public" / "voice.mp3"; dst.parent.mkdir(exist_ok=True)
    if not dst.exists() or dst.stat().st_size != audio.stat().st_size: shutil.copy2(audio, dst)
    if not (proj / "node_modules" / "@remotion" / "renderer").exists():
        print("  installing Remotion (first run only, a few minutes)…")
        pk = ["remotion", "@remotion/cli", "@remotion/bundler", "@remotion/renderer", "react@18.3.1", "react-dom@18.3.1"]
        npm = shutil.which("npm") or "npm"
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund", *pk], cwd=proj)
        if r.returncode: die("npm install failed – check your internet connection and rerun.")
    else:
        print("  Remotion already installed.")

# ----------------------------------------------------------------- render with progress
def render(proj, rdir, frames):
    chunks = [{"i": k, "a": a, "b": min(a + CHUNK - 1, frames - 1)} for k, a in enumerate(range(0, frames, CHUNK))]
    for f in rdir.glob("*.part.mp4"): f.unlink()
    size = {c["i"]: c["b"] - c["a"] + 1 for c in chunks}
    done_set = {c["i"] for c in chunks if (rdir / f"chunk_{c['i']:04d}.mp4").exists()}
    base = sum(size[i] for i in done_set)
    print(f"  chunks: {len(chunks)} x {CHUNK} frames | already rendered: {len(done_set)} ({base}/{frames} frames)")
    if len(done_set) == len(chunks): print("  nothing to render – resuming at merge."); return chunks
    (proj / "plan.json").write_text(json.dumps({"dir": str(rdir), "chunks": chunks, "concurrency": max(2, min(8, (os.cpu_count() or 4) // 2))}))
    node = shutil.which("node") or "node"
    proc = subprocess.Popen([node, "render.mjs"], cwd=proj, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    t0, cur, tail, bundled = time.time(), (0, 0.0), [], False
    start_base = base
    def bar():
        d = base + cur[1] * size.get(cur[0], 0); frac = d / frames
        el = time.time() - t0; fps = (d - start_base) / el if el > 1 and d > start_base else 0
        eta = (frames - d) / fps if fps else 0
        n = int(frac * 30)
        sys.stdout.write(f"\r  [{'█'*n}{'░'*(30-n)}] {frac*100:5.1f}% | frame {int(d)}/{frames} | chunk {len(done_set)+1}/{len(chunks)} | {fps:5.1f} fps | elapsed {fmt_t(el)} | ETA {fmt_t(eta)}   ")
        sys.stdout.flush()
    print("  bundling project (first chunk starts after this)…")
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("PROG"):
            _, i, fr = line.split(); cur = (int(i), float(fr)); bar()
        elif line.startswith("DONE"):
            i = int(line.split()[1]); done_set.add(i); base += size[i]; cur = (i, 0.0); bar()
        elif line and not line.startswith(("SKIP", "ALLDONE")):
            tail.append(line); tail = tail[-15:]
    proc.wait(); print()
    if proc.returncode: print("\n".join(tail)); die("Render stopped. Run the script again – finished chunks are kept and it resumes.")
    return chunks

def merge(rdir, chunks, audio, final):
    lst = rdir / "list.txt"
    lst.write_text("".join(f"file '{(rdir / f'chunk_{c['i']:04d}.mp4').as_posix()}'\n" for c in chunks), encoding="utf-8")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(final)])
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", str(final)],
                         capture_output=True, text=True).stdout.split()
    print("  stream durations (type,sec):", " | ".join(out))

def main():
    args = sys.argv[1:]
    total = 5; t_all = time.time()
    step(1, total, "Checking tools")
    for t in ("ffmpeg", "ffprobe") + (() if "--analyze-only" in args else ("node",)):
        if not shutil.which(t): die(f"'{t}' not found on PATH. Install " + ("Node.js 18+ from nodejs.org" if t == "node" else "ffmpeg (winget install ffmpeg)") + ".")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    audio = find_audio(); print(f"  audio  : {audio}\n  output : {OUT_DIR}")
    step(2, total, "Analysing audio (loudness envelope + pauses -> scene timing)")
    data = analyze(audio)
    if "--analyze-only" in args: return
    proj, rdir = OUT_DIR / "remotion_project", OUT_DIR / "renders"
    step(3, total, "Preparing Remotion project")
    setup_project(proj, audio, data)
    sig = hashlib.sha1(audio.read_bytes() + (MAIN_JSX + RENDER_MJS + json.dumps(data["bounds"])).encode()).hexdigest()
    sf = rdir / "signature.txt"; rdir.mkdir(exist_ok=True)
    if "--fresh" in args or (sf.exists() and sf.read_text() != sig):
        print("  audio/animation changed (or --fresh): clearing cached chunks")
        for f in rdir.glob("chunk_*.mp4"): f.unlink()
    sf.write_text(sig)
    step(4, total, "Rendering 1080x1920 @ 60 fps (resumable)")
    chunks = render(proj, rdir, data["frames"])
    step(5, total, "Merging chunks + original audio")
    final = OUT_DIR / FINAL; merge(rdir, chunks, audio, final)
    print(f"\n✔ DONE in {fmt_t(time.time()-t_all)}  ->  {final}")

if __name__ == "__main__":
    main()
