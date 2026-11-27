#!/usr/bin/env python3
"""
One-file pipeline: audio analysis -> Remotion project -> 1080x1920 / 60fps MP4 (audio-synced).
Run:  python make_video.py
Needs: Python 3.8+, Node.js 18+ (npm), internet on first run (npm + Chrome for Remotion).
"""
import os, sys, re, json, math, time, shutil, subprocess, threading, array

OUT_DIR = r"C:\Users\laptop villa\Documents\cnd"
AUDIO   = os.path.join(OUT_DIR, "Elevenlabs.mp3")
PROJ    = os.path.join(OUT_DIR, "remotion_project")
OUT_MP4 = os.path.join(OUT_DIR, "story_9x16_60fps.mp4")
FPS, W, H = 60, 1080, 1920
# relative narration length of the 8 story scenes (characters per paragraph) -> snapped to real pauses
WEIGHTS = [330, 190, 330, 330, 210, 130, 120, 260]
N_STEPS = 6

# ----------------------------------------------------------------- helpers
def step(i, msg): print(f"\n[{i}/{N_STEPS}] {msg}", flush=True)
def bar(f, w=32): n = int(max(0, min(1, f)) * w); return "█" * n + "░" * (w - n)
def fmt(s): s = int(s); return f"{s//60:02d}:{s%60:02d}"

SPIN = '|/-\\'
def run_spin(cmd, cwd, label):
    p = subprocess.Popen(cmd, cwd=cwd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    log = []
    th = threading.Thread(target=lambda: [log.append(l) for l in p.stdout]); th.start()
    t0, k = time.time(), 0
    while p.poll() is None:
        print(f"\r   {SPIN[k % 4]} {label}  {fmt(time.time()-t0)}", end="", flush=True); k += 1; time.sleep(0.2)
    th.join(); print(f"\r   ✓ {label}  {fmt(time.time()-t0)}        ")
    if p.returncode != 0:
        print("".join(log[-40:])); sys.exit(f"Failed: {cmd}")

def find_ffmpeg():
    f = shutil.which("ffmpeg")
    if f: return f
    print("   ffmpeg not on PATH -> installing imageio-ffmpeg ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"])
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

# ----------------------------------------------------------------- 1. checks
step(1, "Checking environment")
if not os.path.isfile(AUDIO): sys.exit(f"Audio not found: {AUDIO}")
for tool in ("node", "npm"):
    if not shutil.which(tool): sys.exit(f"{tool} not found. Install Node.js from nodejs.org")
FFMPEG = find_ffmpeg()
print(f"   audio : {AUDIO}\n   output: {OUT_MP4}")

# ----------------------------------------------------------------- 2. audio analysis
step(2, "Analysing audio (duration, loudness envelope @60fps, pauses)")
raw = subprocess.run([FFMPEG, "-v", "error", "-i", AUDIO, "-f", "s16le", "-ac", "1", "-ar", "8000", "-"],
                     stdout=subprocess.PIPE).stdout
pcm = array.array("h"); pcm.frombytes(raw[: len(raw) // 2 * 2])
dur = len(pcm) / 8000.0
TOTAL = math.ceil(dur * FPS)
spf = 8000 / FPS
rms = []
for f in range(TOTAL):
    seg = pcm[int(f * spf): int((f + 1) * spf)]
    rms.append(math.sqrt(sum(x * x for x in seg) / len(seg)) if seg else 0.0)
db = [20 * math.log10(max(r, 1) / 32768) for r in rms]
ref = sorted(rms)[int(len(rms) * 0.95)] or 1
env = [min(1.0, r / ref) for r in rms]
sm = []                                   # 5-frame smoothing
for i in range(len(env)):
    a = env[max(0, i - 2): i + 3]; sm.append(round(sum(a) / len(a), 3))
# pauses: >=0.2 s below -32 dBFS
pauses, run0 = [], None
for i, d in enumerate(db + [0]):
    if d < -32 and run0 is None: run0 = i
    if d >= -32 and run0 is not None:
        if i - run0 >= 12: pauses.append((run0, i))
        run0 = None
pauses = [p for p in pauses if p[0] > 30 and p[1] < TOTAL - 30]
beats = [p[1] for p in pauses]
mids = [(a + b) // 2 for a, b in pauses]
bounds, acc, tw = [0], 0, sum(WEIGHTS)
for w in WEIGHTS[:-1]:
    acc += w; tgt = int(acc / tw * TOTAL)
    near = min(mids, key=lambda m: abs(m - tgt), default=None)
    b = near if near is not None and abs(near - tgt) < 3.5 * FPS else tgt
    b = max(b, bounds[-1] + 4 * FPS)
    bounds.append(b)
bounds.append(TOTAL)
print(f"   duration {dur:.2f}s -> {TOTAL} frames | {len(pauses)} pauses | scene cuts (s): "
      + ", ".join(f"{b/FPS:.1f}" for b in bounds[1:-1]))

# ----------------------------------------------------------------- 3. project files
step(3, "Writing Remotion project")
os.makedirs(os.path.join(PROJ, "src"), exist_ok=True)
os.makedirs(os.path.join(PROJ, "public"), exist_ok=True)
shutil.copyfile(AUDIO, os.path.join(PROJ, "public", "Elevenlabs.mp3"))
def wr(rel, txt):
    with open(os.path.join(PROJ, rel), "w", encoding="utf-8") as f: f.write(txt)
wr("package.json", json.dumps({"name": "story", "version": "1.0.0", "private": True, "dependencies": {
    "remotion": "^4.0.0", "@remotion/cli": "^4.0.0", "react": "18.3.1", "react-dom": "18.3.1",
    "typescript": "5.4.5", "@types/react": "18.3.3"}}, indent=1))
wr("tsconfig.json", json.dumps({"compilerOptions": {"target": "ES2018", "module": "commonjs", "jsx": "react-jsx",
    "strict": False, "resolveJsonModule": True, "esModuleInterop": True, "skipLibCheck": True,
    "lib": ["dom", "es2019"]}}))
import zlib, struct, random, base64
def grain_uri(n=128):
    rnd = random.Random(7)
    rows = b"".join(b"\x00" + bytes(rnd.randrange(256) for _ in range(n)) for _ in range(n))
    def ch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 0, 0, 0, 0))
           + ch(b"IDAT", zlib.compress(rows)) + ch(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()
wr("src/data.json", json.dumps({"total": TOTAL, "bounds": bounds, "beats": beats, "env": sm, "grain": grain_uri()}))
wr("src/index.ts", "import {registerRoot} from 'remotion';\nimport {Root} from './Root';\nregisterRoot(Root);\n")
wr("src/Root.tsx", """import React from 'react';
import {Composition} from 'remotion';
import {Main} from './Video';
import D from './data.json';
export const Root = () => <Composition id="Main" component={Main} durationInFrames={D.total} fps={60} width={1080} height={1920} />;
""")

VIDEO = r'''import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame} from 'remotion';
import D from './data.json';

const W = 1080, H = 1920, XF = 24;
const C = {n0:'#05080f',n1:'#0b1530',n2:'#14234a',n3:'#22345f',b1:'#4a3626',b2:'#2b1f16',b3:'#6a4e37',
  y:'#e6d686',y2:'#b3a35a',sk:'#b89d89',pale:'#cfc8bd',amb:'#d19a43',bone:'#e4dfd2',blk:'#05070c'};
const SK = '#c4b8ab';
const cl = (v:number,a=0,b=1)=>Math.min(b,Math.max(a,v));
const es = (x:number)=>{x=cl(x);return x*x*(3-2*x)};
const lp = (a:number,b:number,p:number)=>a+(b-a)*es(p);
const sg = (p:number,a:number,b:number)=>cl((p-a)/(b-a));
const OL:any = {stroke:C.n0,strokeWidth:5,strokeLinejoin:'round',strokeLinecap:'round'};

/* ---------- light & texture helpers ---------- */
const Glow = ({x,y,r,a=1,c='gl'}:any)=><circle cx={x} cy={y} r={r} fill={`url(#${c})`} opacity={a}/>;
const Dark = ({x,y,r,a=.8,id}:any)=><><radialGradient id={id} gradientUnits="userSpaceOnUse" cx={x} cy={y} r={r}>
  <stop offset=".22" stopColor="#02040a" stopOpacity="0"/><stop offset="1" stopColor="#02040a" stopOpacity={a}/></radialGradient>
  <rect width={W} height={H} fill={`url(#${id})`}/></>;
const Sh = ({x,y,L,w=50,a=.55}:any)=><polygon points={`${x-w},${y} ${x+w},${y} ${x+L+w*.3},${y+38} ${x+L-w*.3},${y+6}`} fill="#02040a" opacity={a} filter="url(#bl)"/>;
const Flash = ({t,a=1}:any)=><rect width={W} height={H} fill={(Math.floor(t/9)%2)?'#3b5bc4':'#8c2f35'} opacity={a*.2}/>;
const Wood = ({x,y,w,h,c=C.b1,g=5}:any)=><g><rect x={x} y={y} width={w} height={h} fill={c} {...OL}/>
  {Array.from({length:g}).map((_,i)=><path key={i} d={`M${x+8},${y+(i+1)*h/(g+1)} q${w/4},-7 ${w/2},0 t${w/2-16},0`} stroke={C.b2} strokeWidth={2.5} fill="none" opacity={.7}/>)}</g>;
const Dresser = ({x,y,w=300,h=240}:any)=><g><Wood x={x} y={y} w={w} h={h} g={6}/>
  {[0,1].map(i=><g key={i}><rect x={x+16} y={y+16+i*108} width={w-32} height={96} fill="none" {...OL} strokeWidth={4}/>
  <circle cx={x+w/2} cy={y+64+i*108} r={9} fill={C.y2} {...OL} strokeWidth={3}/></g>)}</g>;
const Lamp = ({x,y,f}:any)=><g><Glow x={x} y={y-50} r={560} a={f*.6}/>
  <path d={`M${x-24},${y} h48 l-6,-26 h-36z`} fill={C.b1} {...OL}/>
  <path d={`M${x-36},${y-26} L${x-22},${y-84} h44 L${x+36},${y-26}z`} fill={C.y} {...OL}/></g>;
const Room = ({fy=1400}:any)=><g>
  <rect width={W} height={fy} fill="url(#wall)"/>
  {Array.from({length:12}).map((_,i)=><rect key={i} x={i*95+20} width={36} height={fy} fill={C.n2} opacity={.18}/>)}
  <rect y={fy} width={W} height={H-fy} fill={C.b2}/>
  {Array.from({length:9}).map((_,i)=><path key={i} d={`M0,${fy+24+i*i*9+i*12}H${W}`} stroke={C.n0} strokeWidth={3} opacity={.5}/>)}
  <rect y={fy-34} width={W} height={34} fill={C.b1} {...OL}/></g>;
const Win = ({x,y,w=320,h=470}:any)=><g><rect x={x} y={y} width={w} height={h} fill={C.n3} {...OL} strokeWidth={10} stroke={C.b1}/>
  <circle cx={x+w*.75} cy={y+h*.22} r={34} fill={C.pale} opacity={.85}/>
  <path d={`M${x+w/2},${y}V${y+h}M${x},${y+h*.55}H${x+w}`} stroke={C.b1} strokeWidth={8}/></g>;

/* ---------- characters ---------- */
const HEAD='M-72,-6 C-72,-62 -40,-84 0,-84 C42,-84 72,-60 72,-4 C72,54 40,88 0,88 C-40,88 -72,54 -72,-6Z';
const HAIR='M-78,-8 C-92,-100 -30,-104 0,-100 C46,-104 92,-92 78,-6 C62,-52 34,-62 0,-60 C-34,-62 -60,-52 -78,-8Z';
const Head = ({ex='neutral',t=0,m=0,skin=C.sk,hair=C.b2,scar=false,lk=0,lh=false}:any)=>{
  const bl=(t%130)<6?.15:1;
  const eye=(s:number)=>{
    let rx=12,ry=10,pr=4.5;
    if(ex==='scared'){rx=18;ry=21;pr=3.5} if(ex==='grin'){rx=20;ry=20;pr=3} if(ex==='angry'){rx=13;ry=7}
    return <g key={s} transform={`translate(${s*30},-6)`}><ellipse rx={rx} ry={ry*bl} fill={C.bone} {...OL} strokeWidth={ex==='grin'?7:3}/>
      <circle cx={lk*4} r={pr} fill={C.n0}/></g>;
  };
  const by:any={neutral:[-34,-34],scared:[-46,-62],angry:[-40,-18],sad:[-32,-48],smile:[-36,-38],grin:[-56,-58]};
  const [bo,bi]=by[ex]||by.neutral;
  let mouth:any;
  if(ex==='neutral') mouth=m>.05?<ellipse cx={0} cy={46} rx={12} ry={4+m*14} fill={C.n0}/>:<path d="M-18,46 Q0,48 18,46" {...OL} fill="none"/>;
  if(ex==='smile') mouth=<path d="M-26,38 Q0,60 26,38" {...OL} fill="none"/>;
  if(ex==='sad') mouth=<path d="M-20,52 Q0,36 20,52" {...OL} fill="none"/>;
  if(ex==='scared') mouth=<ellipse cx={0} cy={50} rx={15} ry={12+m*14} fill={C.n0} {...OL} strokeWidth={3}/>;
  if(ex==='angry') mouth=<path d="M-28,40 L28,40 L24,60 L-24,60Z M-9,40V60 M9,40V60" fill={C.bone} {...OL} strokeWidth={3}/>;
  if(ex==='grin') mouth=<g><path d={`M-66,14 Q0,${34} 66,14 Q0,${92+m*34} -66,14Z`} fill={C.n0} {...OL}/>
    <path d="M-58,20 Q0,40 58,20 L54,34 Q0,56 -54,34Z" fill={C.bone}/>
    <path d="M-30,30V47M-10,34V52M10,34V52M30,30V47" stroke={C.n0} strokeWidth={3}/>
    <path d="M-66,14 l-9,-12 M66,14 l9,-12" {...OL} strokeWidth={4}/></g>;
  return <g><path d={HEAD} fill={skin} {...OL}/><path d="M44,-80 C82,-40 80,44 42,84 C70,48 68,-48 44,-80Z" fill={C.n0} opacity={.28}/>
    {scar&&<g opacity={.4}><ellipse cx={-34} cy={30} rx={24} ry={17} fill="#5a3a32"/><ellipse cx={38} cy={-30} rx={18} ry={26} fill="#5a3a32"/><path d="M-60,-30 q20,20 8,50" stroke="#3b2420" strokeWidth={6} fill="none"/></g>}
    {eye(-1)}{eye(1)}
    {ex!=='grin'&&[-1,1].map(s=><path key={s} d={`M${s*46},${bo} L${s*14},${bi}`} {...OL} strokeWidth={7}/>)}
    {mouth}<path d={HAIR} fill={hair} {...OL}/>
    {lh&&<path d="M-78,-20 L-88,76 L-58,76 L-64,-20Z M78,-20 L88,76 L58,76 L64,-20Z" fill={hair} {...OL}/>}</g>;
};
const Person = ({x,y,s=1.4,skin=C.sk,hair=C.b2,cloth=C.n3,pants=C.n2,ex='neutral',t=0,m=0,flip=false,arm=[8,-8],tilt=0,lk=0,scar=false,rot=0,ph=0,lh=false,children}:any)=>{
  const br=Math.sin((t+ph)/16)*3, hd=Math.sin((t+ph)/37)*2+tilt;
  return <g transform={`translate(${x},${y}) rotate(${rot}) scale(${flip?-s:s},${s})`}>
    <ellipse cy={6} rx={96} ry={13} fill="#02040a" opacity={.5}/>
    {[-1,1].map(k=><path key={k} d={`M${k*42-22},-120 L${k*44-20},-8 L${k*44+20},-8 L${k*42+22},-120Z`} fill={pants} {...OL}/>)}
    {[-1,1].map(k=><ellipse key={k} cx={k*50} cy={-4} rx={30} ry={13} fill={C.n0}/>)}
    <path d="M-64,-292 Q0,-314 64,-292 L72,-110 L-72,-110Z" fill={cloth} {...OL}/>
    {[-1,1].map((k,i)=><g key={k} transform={`translate(${k*64},-280) rotate(${arm[i]})`}>
      <path d={`M0,0 L${k*14},118`} stroke={C.n0} strokeWidth={40} strokeLinecap="round"/>
      <path d={`M0,0 L${k*14},118`} stroke={cloth} strokeWidth={30} strokeLinecap="round"/>
      <circle cx={k*14} cy={130} r={17} fill={skin} {...OL} strokeWidth={4}/></g>)}
    <rect x={-18} y={-330} width={36} height={44} fill={skin} {...OL}/>
    <g transform={`translate(0,${-372+br}) rotate(${hd})`}><Head ex={ex} t={t} m={m} skin={skin} hair={hair} scar={scar} lk={lk} lh={lh}/></g>
    {children}</g>;
};
const Knife = ({x,y,r=0}:any)=><g transform={`translate(${x},${y}) rotate(${r})`}><rect x={-7} y={-6} width={14} height={34} fill={C.b2} {...OL} strokeWidth={3}/>
  <path d="M-9,-6 L9,-6 L4,-120 Z" fill="#d7d9de" {...OL} strokeWidth={3}/><path d="M0,-30 L0,-110" stroke="#fff" strokeWidth={3} opacity={.8}/></g>;
const JEFF:any = {skin:SK,hair:'#09090c',cloth:C.n3,pants:C.n1};
const SIL:any = {skin:'#07090f',hair:C.blk,cloth:C.blk,pants:C.blk};

type SP = {t:number;p:number;f:number;e:number};

/* ---------- S1: the intruder at the window ---------- */
const S1 = ({t,p,f}:SP)=>{
  const gap=lp(34,68,p), fy=lp(570,510,p), fs=lp(.8,1.2,p);
  return <g><Room/><Win x={380} y={260} w={320} h={470}/>
    <g transform={`translate(540,${fy}) scale(${fs})`}><ellipse rx={84} ry={100} fill="#c4beb1" {...OL}/>
      {[-1,1].map(s=><g key={s}><ellipse cx={s*32} cy={-14} rx={24} ry={18} fill={C.n0}/><circle cx={s*32} cy={-14} r={4} fill={C.bone}/></g>)}
      <path d={`M-62,34 Q0,${84+Math.sin(t/20)*5} 62,34 Q0,52 -62,34Z`} fill={C.n0} {...OL}/>
      <path d="M-52,38 Q0,64 52,38 L48,46 Q0,70 -48,46Z" fill={C.bone}/></g>
    <path d={`M330,250H${540-gap}Q${520-gap},500 ${540-gap},740H330Z`} fill={C.b2} {...OL}/>
    <path d={`M750,250H${540+gap}Q${560+gap},500 ${540+gap},740H750Z`} fill={C.b2} {...OL}/>
    <rect x={320} y={236} width={460} height={16} fill={C.b1} {...OL}/>
    <Dresser x={40} y={1180}/><Lamp x={150} y={1180} f={f}/>
    <Wood x={990} y={980} w={60} h={450} g={5}/>
    <Person x={720} y={1340} s={1.15} ex={p<.22?'neutral':'scared'} t={t} lh={false} cloth={C.pale} lk={-1}/>
    <path d="M400,1270 Q700,1226 1000,1276 L1000,1430 L400,1430Z" fill={C.n3} {...OL}/>
    <Sh x={720} y={1440} L={-520} w={120}/>
    <Dark x={150} y={1130} r={1150} a={.82} id="d1"/>
    {p>.9&&<Flash t={t} a={sg(p,.9,.96)}/>}</g>;
};

/* ---------- S2: the new neighbourhood ---------- */
const S2 = ({t,p,f}:SP)=>{
  const fam=[{x:170,ex:'neutral',c:C.b3,s:1.35},{x:330,ex:'smile',c:C.n3,s:1.25,lh:true},{x:500,ex:'sad',c:C.n2,s:1.1,tilt:6,lk:-1,jeff:true},{x:640,ex:'smile',c:C.b1,s:.95}];
  return <g><rect width={W} height={1340} fill="url(#wall)"/>
    {[[100,160],[300,90],[640,200],[780,120],[980,60],[420,300]].map((s,i)=><circle key={i} cx={s[0]} cy={s[1]} r={3} fill={C.pale} opacity={.7}/>)}
    <circle cx={860} cy={250} r={90} fill={C.pale} opacity={.9}/><Glow x={860} y={250} r={400} a={.25}/>
    <polygon points="90,640 540,330 990,640" fill={C.n2} {...OL}/><Wood x={130} y={640} w={820} h={700} g={10}/>
    {[200,640].map(x=><g key={x}><rect x={x} y={730} width={190} height={220} fill={C.y} opacity={.55+f*.35} {...OL}/><path d={`M${x+95},730V950M${x},840H${x+190}`} stroke={C.b2} strokeWidth={7}/></g>)}
    <rect x={470} y={1030} width={140} height={310} fill={C.b2} {...OL}/><circle cx={590} cy={1190} r={8} fill={C.y2}/>
    <Glow x={540} y={1000} r={260} a={.25*f}/>
    <rect y={1340} width={W} height={H-1340} fill={C.n1}/>
    <Wood x={50} y={1270} w={130} h={110} g={2}/><Wood x={130} y={1200} w={100} h={80} g={2}/>
    {fam.map((m:any,i)=><React.Fragment key={i}><Sh x={m.x} y={1750} L={-340} w={60}/>
      <Person x={m.x} y={1750} s={m.s} ex={m.ex} cloth={m.c} t={t} ph={i*20} lh={m.lh} tilt={m.tilt||0} lk={m.lk||0} {...(m.jeff?{skin:SK,hair:JEFF.hair}:{})}/></React.Fragment>)}
    <Sh x={940} y={1750} L={-340} w={60}/>
    <Person x={940} y={1750} s={1.2} flip ex="smile" cloth="#6f5b4a" lh hair={C.b3} arm={[0,-80]} t={t}/>
    <g transform="translate(705,1415) rotate(-10)"><rect x={-36} y={-26} width={72} height={52} fill={C.pale} {...OL}/><path d="M-36,-26 L0,6 L36,-26" fill="none" {...OL} strokeWidth={3}/></g>
    <Dark x={540} y={1000} r={1400} a={.72} id="d2"/></g>;
};

/* ---------- S3: the bus stop ---------- */
const S3 = ({t,p,f}:SP)=>{
  const ja=sg(p,.35,.55), ret=sg(p,.5,.72), cop=sg(p,.74,.92);
  const bx=(k:number,x:number)=>lp(1300,x,sg(p,0,.12))+lp(0,90,ret);
  return <g><rect width={W} height={1380} fill="url(#wall)"/>
    {[[0,700,230],[250,560,200],[480,760,240],[760,620,180],[900,820,200]].map((b,i)=><g key={i}><rect x={b[0]} y={b[1]} width={b[2]} height={1380-b[1]} fill={C.n1} {...OL}/>
      {[0,1,2].map(j=><rect key={j} x={b[0]+30+j*60} y={b[1]+50+(i%2)*70} width={30} height={40} fill={C.y} opacity={.35}/>)}</g>)}
    <rect y={1380} width={W} height={H-1380} fill={C.b2}/><rect y={1380} width={W} height={26} fill={C.b1} {...OL}/>
    <rect x={190} y={800} width={14} height={580} fill={C.pale} {...OL}/><rect x={130} y={760} width={130} height={80} fill={C.y2} {...OL}/>
    <path d="M880,1380 V560 Q880,520 820,520" stroke={C.n3} strokeWidth={16} fill="none" {...OL}/>
    <polygon points="780,540 860,540 1000,1380 640,1380" fill={C.y} opacity={.1}/><Glow x={810} y={560} r={420} a={.55*f}/>
    <ellipse cx={810} cy={532} rx={42} ry={16} fill={C.y} {...OL}/>
    {[{x:bx(0,560),y:1640,c:C.b3},{x:bx(1,760),y:1700,c:C.n2},{x:bx(2,930),y:1650,c:C.b1}].map((b,i)=><React.Fragment key={i}>
      <Sh x={b.x} y={b.y} L={-380} w={60}/>
      <Person x={b.x} y={b.y} s={1.3} flip ex={ret>.3?'scared':'smile'} cloth={b.c} hair={i?C.b2:C.n0} t={t} ph={i*30} arm={i===1?[0,-80]:[8,-8]}>
        {i===1&&p>.12&&p<.72&&<g><Knife x={194} y={-271} r={90}/><path d="M290,-290 l16,-16 M290,-290 l-16,-16 M290,-290 l16,16" stroke="#fff" strokeWidth={4} opacity={.5+.5*Math.sin(t/3)}/></g>}</Person></React.Fragment>)}
    <Sh x={140} y={1640} L={-380} w={60}/><Person x={lp(140,-300,cop)} y={1640} s={1.05} ex={cop>0?'sad':'scared'} cloth={C.b1} hair={C.b3} t={t}/>
    <Sh x={340} y={1710} L={-380} w={60}/>
    <Person x={lp(340,500,ja)} y={1710} s={1.4} ex={ja>.2?'angry':'neutral'} {...JEFF} tilt={ja*-4} t={t} scar={false} arm={[ja*20,-ja*20]}/>
    {cop>0&&<Person x={lp(-250,-40,cop)} y={1650} s={1.35} ex="neutral" cloth={C.blk} pants={C.blk} hair={C.n0} t={t}/>}
    <Dark x={600} y={1100} r={1400} a={.75} id="d3"/>{p>.72&&<Flash t={t} a={sg(p,.72,.8)}/>}</g>;
};

/* ---------- S4: birthday party & fire ---------- */
const Fire = ({t,k}:any)=><g>{Array.from({length:9}).map((_,i)=>{const x=(i+.5)*W/9,h=(300+Math.sin(t/5+i*2)*80+Math.sin(t/3+i)*45)*k;
  return <g key={i}><path d={`M${x-90},${H} Q${x-60},${H-h*.6} ${x+Math.sin(t/4+i)*24},${H-h} Q${x+66},${H-h*.5} ${x+90},${H}Z`} fill={C.amb} opacity={.88}/>
  <path d={`M${x-48},${H} Q${x-30},${H-h*.4} ${x},${H-h*.62} Q${x+34},${H-h*.35} ${x+48},${H}Z`} fill={C.y}/></g>})}</g>;
const S4 = ({t,p,f}:SP)=>{
  const ent=sg(p,.28,.42), ch=sg(p,.45,1), fire=sg(p,.62,.9), fall=sg(p,.74,.9);
  const sh=Math.sin(t*1.9)*10*ch;
  return <g transform={`translate(${sh},${Math.cos(t*2.3)*6*ch})`}><Room/>
    <path d="M0,200 Q270,330 540,200 T1080,200" stroke={C.y2} strokeWidth={4} fill="none"/>
    {Array.from({length:9}).map((_,i)=>{const x=i*120+40,y=205+105*Math.sin(Math.PI*(x%540)/540);return <polygon key={i} points={`${x-24},${y} ${x+24},${y} ${x},${y+54}`} fill={[C.y,C.b3,C.n3][i%3]} {...OL} strokeWidth={3}/>})}
    {[[120,520,C.y2],[960,560,C.n3],[200,740,C.b3],[900,780,C.y]].map((b:any,i)=><g key={i}><path d={`M${b[0]},${b[1]+64} q${Math.sin(t/20+i)*20},120 0,260`} stroke={C.pale} strokeWidth={2} fill="none"/><ellipse cx={b[0]} cy={b[1]} rx={52} ry={64} fill={b[2]} {...OL}/></g>)}
    <Wood x={330} y={1250} w={420} h={150} g={3}/><rect x={430} y={1170} width={220} height={82} fill={C.pale} {...OL}/><rect x={430} y={1170} width={220} height={26} fill={C.b3} {...OL}/>
    {[470,540,610].map(x=><g key={x}><rect x={x-4} y={1128} width={8} height={42} fill={C.y2}/><ellipse cx={x} cy={1112} rx={9} ry={16+Math.sin(t/4+x)*3} fill={C.y}/></g>)}
    <Glow x={540} y={1180} r={300} a={.4*f}/>
    {[170,350,760].map((x,i)=><Person key={i} x={x-lp(0,620,ch)} y={1640+i*40} s={.95} ex={ch>.1?'scared':'smile'} cloth={[C.b3,C.n2,C.b1][i]} t={t} ph={i*25} m={ch}/>)}
    {[560,700,800].map((x,i)=><Person key={i} x={lp(1350,x,ent)} y={1620+i*50} s={1.3} flip ex="angry" cloth={[C.b1,C.n2,C.b3][i]} t={t} ph={i*17} arm={[ch*40,-ch*40]}/>)}
    <Person x={930} y={1680} s={1.35} rot={lp(0,78,fall)} ex={fall>.1?'scared':ch>.1?'angry':'neutral'} {...JEFF} t={t}/>
    {fire>0&&<><Fire t={t} k={fire}/><Glow x={540} y={H} r={1100} a={fire*.55} c="gl2"/></>}
    <Dark x={540} y={1000} r={1500} a={.72-fire*.3} id="d4"/></g>;
};

/* ---------- S5: hospital, bandages off ---------- */
const S5 = ({t,p,f,e}:SP)=>{
  const unb=sg(p,.3,.45), lau=sg(p,.52,.62), ex=lau>0?'grin':'neutral';
  return <g><Room/>
    <ellipse cx={850} cy={640} rx={135} ry={195} fill={C.n3} {...OL} strokeWidth={14} stroke={C.b3}/>
    <g opacity={sg(p,.42,.52)} transform="translate(850,650) scale(1.1)"><Head ex="grin" t={t} m={.5+.5*Math.sin(t/3)} skin={SK} hair={JEFF.hair} scar/></g>
    <path d="M160,1330 V520 H320" stroke={C.pale} strokeWidth={8} fill="none"/><rect x={285} y={520} width={70} height={110} rx={12} fill={C.y2} opacity={.7} {...OL}/>
    <Wood x={120} y={1330} w={840} h={60} c={C.b3}/><rect x={140} y={1230} width={800} height={110} fill="#7d8794" {...OL}/>
    <Person x={540} y={1370} s={1.5} ex={ex} {...JEFF} skin={SK} cloth="#8b95a3" t={t} scar={unb>.5} m={lau*(.4+.6*Math.abs(Math.sin(t/3)))} tilt={lau*Math.sin(t/2.2)*5}/>
    <path d="M150,1330 Q540,1290 930,1340 L930,1440 L150,1440Z" fill="#a7b0bd" {...OL}/>
    <g opacity={1-unb} transform={`translate(0,${-unb*420})`}><ellipse cx={540} cy={805} rx={120} ry={128} fill={C.pale} {...OL}/>
      {[0,1,2].map(i=><path key={i} d={`M${440+i*10},${740+i*45} Q540,${770+i*45} ${640-i*10},${740+i*45}`} stroke={C.b3} strokeWidth={4} fill="none"/>)}
      <rect x={470} y={840} width={140} height={60} fill={C.pale} {...OL}/></g>
    <Sh x={130} y={1790} L={420} w={60}/>
    <Person x={130} y={1790} s={1.3} ex={lau>0?'scared':'neutral'} cloth={C.pale} pants={C.n2} t={t} hair={C.b2}/>
    <Person x={950} y={1790} s={1.3} flip ex={lau>0?'scared':'sad'} cloth="#6f6a66" lh hair={C.b3} t={t} m={lau}/>
    <Lamp x={540} y={1390} f={0}/><Dark x={540} y={900} r={1200} a={.78} id="d5"/></g>;
};

/* ---------- S6: bathroom ---------- */
const S6 = ({t,p,f,e}:SP)=>{
  const mx=lp(180,80,sg(p,.4,1));
  return <g><rect width={W} height={1400} fill={C.n2}/>
    {Array.from({length:10}).map((_,i)=><path key={i} d={`M${i*120},0V1400M0,${i*150}H${W}`} stroke={C.n0} strokeWidth={3} opacity={.35}/>)}
    <rect y={1400} width={W} height={H-1400} fill={C.n1}/>
    <polygon points="0,300 250,420 250,1390 0,1500" fill={C.y} opacity={.2+e*.05}/><polygon points="0,1480 0,1920 960,1920 420,1470" fill={C.y} opacity={.13}/>
    <rect x={390} y={520} width={300} height={430} fill={C.n3} {...OL} strokeWidth={14} stroke={C.b3}/>
    <g transform="translate(540,760) scale(.9)"><Head ex="grin" t={t} m={e} skin={SK} hair={JEFF.hair} scar/></g>
    <rect x={380} y={1150} width={320} height={210} fill="#8f9aa8" {...OL}/><rect x={500} y={1100} width={80} height={50} fill={C.b3} {...OL}/>
    <Sh x={620} y={1690} L={470} w={110}/><Sh x={mx} y={1690} L={470} w={80}/>
    <Person x={620} y={1690} s={1.7} ex="grin" {...JEFF} scar m={Math.min(1,e*1.4)} t={t} tilt={Math.sin(t/25)*5}/>
    <Person x={mx} y={1690} s={1.45} ex="scared" cloth="#6f6a66" pants="#4a4a52" lh hair={C.b3} t={t} m={e}/>
    <Dark x={560} y={1000} r={1250} a={.8} id="d6"/></g>;
};

/* ---------- S7: corridor, light goes out ---------- */
const S7 = ({t,p,f,e}:SP)=>{
  const a=sg(p,.35,.85), lamp=1-sg(p,.55,.9), run=sg(p,.05,.5), sw=Math.sin(t/4);
  return <g><rect width={W} height={H} fill={C.n1}/>
    <polygon points="0,0 260,420 260,1380 0,1920" fill={C.b2} {...OL}/><polygon points="1080,0 820,420 820,1380 1080,1920" fill={C.b2} {...OL}/>
    <rect x={260} y={420} width={560} height={960} fill={C.n2} {...OL}/>
    <polygon points="0,1920 260,1380 820,1380 1080,1920" fill={C.b1}/>
    {Array.from({length:7}).map((_,i)=><path key={i} d={`M540,1380 L${i*180},1920`} stroke={C.b2} strokeWidth={4}/>)}
    <rect x={400} y={640} width={280} height={740} fill={C.y} opacity={.9*lamp} {...OL}/>
    <polygon points="400,1380 680,1380 960,1920 120,1920" fill={C.y} opacity={.22*lamp}/><Glow x={540} y={1000} r={640} a={.5*lamp}/>
    <polygon points={`${540-90*lp(1,2.6,a)},${lp(1380,1700,a)} ${540+90*lp(1,2.6,a)},${lp(1380,1700,a)} ${540+500*a},1920 ${540-500*a},1920`} fill="#02040a" opacity={.6} filter="url(#bl)"/>
    <Person x={540} y={lp(1380,1620,a)} s={lp(.85,1.7,a)} ex="grin" {...SIL} arm={[0,-150]} t={t} m={Math.min(1,e*1.2)}><Knife x={117} y={-400} r={8}/></Person>
    <Person x={lp(780,-260,run)} y={1760-Math.abs(sw)*16} s={1.25} flip ex="scared" cloth="#6f6a66" lh hair={C.b3} arm={[sw*45,-sw*45]} t={t}/>
    <Dark x={540} y={1100} r={lp(1500,420,sg(p,.5,.95))} a={.9} id="d7"/></g>;
};

/* ---------- S8: Liu, the whisper, police lights fade ---------- */
const S8 = ({t,p,f}:SP)=>{
  const ap=sg(p,.15,.45), hand=sg(p,.45,.58), q=sg(p,.6,.95), gone=1-sg(p,.6,.7);
  return <g><Room/><Win x={60} y={260} w={300} h={460}/>
    {q>0&&<g opacity={1-sg(q,.75,1)}><circle cx={lp(90,330,q)} cy={540} r={lp(60,14,q)} fill={(Math.floor(t/9)%2)?'#3b5bc4':'#a13a40'} opacity={.9}/>
      <Glow x={lp(90,330,q)} y={540} r={lp(260,70,q)} a={.5} c={(Math.floor(t/9)%2)?'glb':'glr'}/></g>}
    <Dresser x={40} y={1180} w={260}/>
    <Wood x={960} y={980} w={60} h={450} g={5}/>
    <g opacity={gone}><Person x={650} y={1340} s={1.2} ex="scared" t={t} cloth={C.pale} lk={1} m={1-hand}/>
    <path d="M360,1270 Q660,1230 960,1276 L960,1430 L360,1430Z" fill={C.n3} {...OL}/>
    <Person x={lp(1050,780,ap)} y={1500} s={1.9} flip ex="grin" {...SIL} t={t} arm={[0,-8]} m={.3}/>
    <g transform={`translate(${lp(840,655,hand)},${lp(1080,905,hand)}) rotate(-20)`} opacity={sg(p,.45,.5)}><ellipse rx={74} ry={50} fill={C.blk}/>{[-48,-16,16,44].map(x=><ellipse key={x} cx={x} cy={-48} rx={14} ry={30} fill={C.blk}/>)}</g></g>
    <Dark x={lp(650,210,sg(p,.55,.8))} y={lp(1000,520,sg(p,.55,.8))} r={lp(1250,620,sg(p,.55,.8))} a={.9} id="d8"/></g>;
};

const SC = [S1,S2,S3,S4,S5,S6,S7,S8];
const ORG = [[540,560],[540,1100],[620,1400],[700,1300],[540,860],[600,1200],[540,1100],[420,700]];

const Scene = ({Sc,from,len,i}:any)=>{
  const t=useCurrentFrame(), g=t+from, p=cl(t/len);
  const e=(D.env as number[])[Math.min(g,D.env.length-1)]||0;
  const f=.86+.08*Math.sin(g/3.1)+.04*Math.sin(g/7.7)+e*.12;
  let bt=-999; for(const b of D.beats as number[]){ if(b<=g) bt=b; }
  const z=1+.11*p+e*.004+.007*Math.exp(-(g-bt)/18);
  const seed=Math.floor(g/6)%6+1;
  return <AbsoluteFill style={{opacity:i===0?1:es(t/XF)}}>
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{transform:`scale(${z})`,transformOrigin:`${ORG[i][0]}px ${ORG[i][1]}px`}}>
      <defs>
        <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={C.n0}/><stop offset="1" stopColor={C.n2}/></linearGradient>
        <radialGradient id="gl"><stop offset="0" stopColor={C.y} stopOpacity=".9"/><stop offset="1" stopColor={C.y} stopOpacity="0"/></radialGradient>
        <radialGradient id="gl2"><stop offset="0" stopColor={C.amb} stopOpacity=".9"/><stop offset="1" stopColor={C.amb} stopOpacity="0"/></radialGradient>
        <radialGradient id="glb"><stop offset="0" stopColor="#3b5bc4" stopOpacity=".9"/><stop offset="1" stopColor="#3b5bc4" stopOpacity="0"/></radialGradient>
        <radialGradient id="glr"><stop offset="0" stopColor="#a13a40" stopOpacity=".9"/><stop offset="1" stopColor="#a13a40" stopOpacity="0"/></radialGradient>
        <filter id="bl"><feGaussianBlur stdDeviation="9"/></filter>
        <filter id="boil" x="-2%" y="-2%" width="104%" height="104%"><feTurbulence type="fractalNoise" baseFrequency="0.011" numOctaves="2" seed={seed} result="n"/>
          <feDisplacementMap in="SourceGraphic" in2="n" scale="9" xChannelSelector="R" yChannelSelector="G"/></filter>
      </defs>
      <g filter="url(#boil)"><Sc t={t} p={p} f={f} e={e}/></g>
    </svg></AbsoluteFill>;
};

const Overlay = ()=>{
  const g=useCurrentFrame(), fo=sg(g,D.total-150,D.total-30), fi=1-sg(g,0,24);
  return <AbsoluteFill style={{pointerEvents:'none'}}><svg width={W} height={H}><defs>
    <radialGradient id="vg" cx=".5" cy=".5" r=".75"><stop offset=".45" stopColor="#000" stopOpacity="0"/><stop offset="1" stopColor="#000" stopOpacity=".78"/></radialGradient>
    <pattern id="gp" width="128" height="128" patternUnits="userSpaceOnUse" patternTransform={`translate(${(g*37)%128},${(g*61)%128})`}><image href={(D as any).grain} width="128" height="128"/></pattern></defs>
    <rect width={W} height={H} fill="url(#vg)"/><rect width={W} height={H} fill="url(#gp)" opacity={.08}/>
    <rect width={W} height={H} fill="#000" opacity={Math.max(fo,fi)}/></svg></AbsoluteFill>;
};

export const Main = ()=>{
  const B = D.bounds as number[];
  return <AbsoluteFill style={{background:'#000'}}>
    <Audio src={staticFile('Elevenlabs.mp3')}/>
    {SC.map((Sc,i)=><Sequence key={i} from={B[i]} durationInFrames={B[i+1]-B[i]+(i<SC.length-1?XF:0)}>
      <Scene Sc={Sc} from={B[i]} len={B[i+1]-B[i]} i={i}/></Sequence>)}
    <Overlay/>
  </AbsoluteFill>;
};
'''
wr("src/Video.tsx", VIDEO)
print("   ✓ project written")

# ----------------------------------------------------------------- 4. install
step(4, "Installing dependencies (first run only)")
if os.path.isdir(os.path.join(PROJ, "node_modules", "remotion")):
    print("   ✓ already installed")
else:
    run_spin("npm install --no-audit --no-fund --loglevel=error", PROJ, "npm install")

# ----------------------------------------------------------------- 5. render
step(5, f"Rendering {TOTAL} frames @ {FPS}fps, {W}x{H} (audio muxed from the same timeline)")
def free_gb():
    try:
        import ctypes
        class MS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("ml", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ("tp", "ap", "tpf", "apf", "tv", "av", "ae")]
        m = MS(); m.l = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); return m.ap / 2**30
    except Exception:
        return 8.0
conc = max(2, min((os.cpu_count() or 4) - 1, int(free_gb() / 0.9), 14))
print(f"   using {conc} parallel Chrome tabs ({os.cpu_count()} cores, {free_gb():.1f} GB free RAM)")
cmd = (f'npx remotion render src/index.ts Main "{OUT_MP4}" --codec=h264 --crf=18 '
       f'--image-format=jpeg --jpeg-quality=95 --concurrency={conc} --overwrite --log=info')
p = subprocess.Popen(cmd, cwd=PROJ, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     env={**os.environ, "FORCE_COLOR": "0"})
t0, stage, done, tail = time.time(), "Starting (bundling / launching Chrome)", 0, []
while True:
    ch = p.stdout.read1(4096)
    if not ch and p.poll() is not None: break
    txt = ch.decode("utf-8", "replace"); tail.append(txt); tail = tail[-30:]
    low = txt.lower()
    if "ncod" in low: stage = "Encoding"
    elif "ender" in low: stage = "Rendering frames"
    elif "tich" in low or "ombin" in low: stage = "Muxing audio + video"
    for m in re.finditer(r"(\d+)\s*/\s*(\d+)", txt):
        if int(m.group(2)) == TOTAL: done = max(done, int(m.group(1)))
    el = time.time() - t0; fr = done / TOTAL
    eta = el / fr - el if fr > 0.01 else 0
    print(f"\r   {stage:<22} {bar(fr)} {fr*100:5.1f}%  {done}/{TOTAL} fr  "
          f"elapsed {fmt(el)}  ETA {fmt(eta) if eta else '--:--'}   ", end="", flush=True)
if p.returncode != 0:
    print("\n" + "".join(tail)); sys.exit("Render failed")
print(f"\r   ✓ Render complete {bar(1)} 100%  total {fmt(time.time()-t0)}                    ")

# ----------------------------------------------------------------- 6. verify
step(6, "Verifying sync")
info = subprocess.run([FFMPEG, "-i", OUT_MP4], stderr=subprocess.PIPE, text=True).stderr
m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
vd = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
print(f"   audio {dur:.2f}s | video file {vd:.2f}s | drift {abs(vd-dur)*1000:.0f} ms")
print(f"\nDONE -> {OUT_MP4}  ({os.path.getsize(OUT_MP4)/1e6:.1f} MB)")
