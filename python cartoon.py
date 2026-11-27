#!/usr/bin/env python3
# Setup:  pip install numpy      (also needs Node.js 18+ with npm; internet on first run)
# Run:    python make_cartoon.py
# Output: C:\Users\laptop villa\Documents\cnd\cartoon_60fps.mp4
import os, sys, re, json, math, shutil, subprocess, time, wave, hashlib
from pathlib import Path
import numpy as np

DIR = Path(os.environ.get("CND_DIR", r"C:\Users\laptop villa\Documents\cnd"))
AUDIO = DIR / "20204.mp3"
PROJ = DIR / "remotion_project"
OUT = DIR / "cartoon_60fps.mp4"
FPS, SR = 60, 44100
SCARE = 180        # jumpscare length in frames (3.0 s) appended after the narration
SFX_LEVEL = .28    # sound effects vs voice (lower = quieter effects)
CHUNK = 120        # frames per saved render chunk (2 s)
PREP = "--prep" in sys.argv          # build + analyse + mix only (no npm/render)

STAGES = [("Setup & checks", 2), ("Write Remotion project", 3), ("Install Remotion (npm)", 15),
          ("Analyse audio / sync map", 8), ("Sound design & mix", 10), ("Render 1080x1920 @60fps", 62)]


class Prog:
    def start(self, i):
        self.i, self.base, self.t0 = i, sum(w for _, w in STAGES[:i]), time.time()
        self.line(0)

    def line(self, frac, msg=""):
        tot = self.base + STAGES[self.i][1] * frac
        n = int(30 * tot / 100)
        print(f"\r[{self.i+1}/{len(STAGES)}] {STAGES[self.i][0]:<26}[{'#'*n}{'-'*(30-n)}] {tot:5.1f}%  {msg:<38}", end="", flush=True)

    def done(self, msg=""):
        self.line(1, msg or f"done in {time.time()-self.t0:.1f}s")
        print()


P = Prog()


def run(cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(f"\nFAILED: {' '.join(map(str, cmd))}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r


# ----------------------------------------------------------------------------- JSX sources
ART = r'''import React from 'react';
export const C={ink:'#3b2a1f',wall:'#eadcb9',wall2:'#dccb9e',floor:'#b78f60',floor2:'#a27a4f',wood:'#8b5b3a',wood2:'#6f4528',yel:'#f2dc86',grn:'#a4ba8b',grn2:'#7e9a6b',skin:'#d9a273',skin2:'#c48b5b',cream:'#fff8e8',pee:'#f0d230',red:'#cf6a49',dark:'#4c3426',tan:'#c9a06a'};
const K=C.ink;
export const clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v));
export const ease=p=>1-Math.pow(1-clamp(p),3);
export const seg=(u,a,b)=>clamp((u-a)/(b-a));
export const lerp=(a,b,p)=>a+(b-a)*p;
export const back=p=>{p=clamp(p);const c=1.9;return 1+(c+1)*Math.pow(p-1,3)+c*Math.pow(p-1,2);};
const rad=d=>d*Math.PI/180;
const endPt=(s,deg,len)=>[s[0]+len*Math.sin(rad(deg)),s[1]+len*Math.cos(rad(deg))];
const Limb=({a,b,bend=0,w=34,col})=>{const mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2,dx=b[0]-a[0],dy=b[1]-a[1];const d=`M${a[0]} ${a[1]} Q${mx-dy*bend} ${my+dx*bend} ${b[0]} ${b[1]}`;return(<g fill="none" strokeLinecap="round"><path d={d} stroke={K} strokeWidth={w+12}/><path d={d} stroke={col} strokeWidth={w}/></g>);};
const Hand=({p,col})=><circle cx={p[0]} cy={p[1]} r={25} fill={col} stroke={K} strokeWidth={7}/>;

const EX={
 angry:{eye:'open',h:.7,br:[24,-24],bro:-2,m:'M-48 90 Q0 34 48 90',fill:false,blush:C.red},
 sneaky:{eye:'half',h:.55,br:[-8,20],bro:-6,m:'M-44 74 Q8 106 54 54',fill:false},
 innocent:{eye:'open',h:1.1,br:[-24,24],bro:-14,m:'M-14 78 a14 18 0 1 0 28 0 a14 18 0 1 0 -28 0',fill:true},
 relief:{eye:'closed',h:0,br:[-12,12],bro:-8,m:'M-54 62 Q0 128 54 62 Z',fill:true,blush:C.red},
 grin:{eye:'open',h:.95,br:[-14,14],bro:-10,m:'M-62 64 Q0 126 62 64 Z',fill:true,teeth:true},
 shock:{eye:'open',h:1.35,br:[-26,26],bro:-22,m:'M-22 70 a22 34 0 1 0 44 0 a22 34 0 1 0 -44 0',fill:true},
 flat:{eye:'half',h:.6,br:[8,-8],bro:0,m:'M-40 86 L40 86',fill:false},
 gross:{eye:'closed',h:0,br:[22,-22],bro:0,m:'M-50 98 Q-25 60 0 92 Q25 60 50 98',fill:false},
};
const Face=({ex,look,blink,sniff,skin})=>{
 const e=EX[ex]||EX.flat;const h=Math.max(.04,e.h*(1-blink));
 return(<g>
  {e.blush&&[-82,82].map(x=><circle key={x} cx={x} cy={46} r={21} fill={e.blush} opacity={.55}/>)}
  {[-48,48].map((x,i)=>e.eye==='closed'
   ?<path key={i} d={`M${x-30} 2 Q${x} -30 ${x+30} 2`} fill="none" stroke={K} strokeWidth={8} strokeLinecap="round"/>
   :<g key={i}>
     <ellipse cx={x} cy={-8} rx={36} ry={40*h} fill={C.cream} stroke={K} strokeWidth={6}/>
     <circle cx={x+look[0]*12} cy={-8+look[1]*10} r={14} fill={K}/>
     <circle cx={x+look[0]*12+5} cy={-8+look[1]*10-5} r={4} fill={C.cream}/>
     {e.eye==='half'&&<g><path d={`M${x-40} ${-8-40*h-4} H${x+40} V-9 H${x-40}Z`} fill={skin}/><line x1={x-38} x2={x+38} y1={-9} y2={-9} stroke={K} strokeWidth={7} strokeLinecap="round"/></g>}
    </g>)}
  {[-48,48].map((x,i)=><line key={i} transform={`translate(${x} ${-62+e.bro}) rotate(${e.br[i]})`} x1={-34} x2={34} y1={0} y2={0} stroke={K} strokeWidth={12} strokeLinecap="round"/>)}
  <g transform={`translate(0 30) scale(${1+sniff*.7})`}><path d="M-8 -6 Q14 10 -8 18" fill="none" stroke={K} strokeWidth={6} strokeLinecap="round"/></g>
  <path d={e.m} fill={e.fill?'#7b2f2b':'none'} stroke={K} strokeWidth={7} strokeLinejoin="round" strokeLinecap="round"/>
  {e.teeth&&<g><path d="M-56 67 H56 L50 83 H-50Z" fill={C.cream}/><line x1={0} x2={0} y1={67} y2={83} stroke={K} strokeWidth={4}/></g>}
 </g>);
};
const Head=({skin,ex,look,blink,sniff,rot=0,mom})=>(
 <g transform={`rotate(${rot})`}>
  {[-1,1].map(s=><circle key={s} cx={s*124} cy={8} r={28} fill={skin} stroke={K} strokeWidth={7}/>)}
  {mom&&<circle cx={0} cy={-150} r={52} fill={K}/>}
  <circle r={125} fill={skin} stroke={K} strokeWidth={8}/>
  <path d={mom?"M-122 -30 Q-120 -150 0 -140 Q120 -150 122 -30 Q70 -105 0 -98 Q-70 -105 -122 -30Z":"M-118 -40 Q-110 -150 0 -135 Q110 -150 118 -40 Q80 -95 0 -88 Q-80 -95 -118 -40Z"} fill={K}/>
  {!mom&&<path d="M-8 -130 Q4 -178 30 -152" fill="none" stroke={K} strokeWidth={9} strokeLinecap="round"/>}
  {mom&&<g><circle cx={0} cy={-84} r={7} fill={C.red}/>{[-1,1].map(s=><circle key={s} cx={s*126} cy={44} r={9} fill="#d9b44a" stroke={K} strokeWidth={4}/>)}</g>}
  <Face ex={ex} look={look} blink={blink} sniff={sniff} skin={skin}/>
 </g>);

export const Sweat=({x,y,t})=>{const p=(t*.9)%1;return <path transform={`translate(${x} ${y+p*50})`} d="M0 -26 Q22 6 0 24 Q-22 6 0 -26Z" fill="#a9d4e6" stroke={K} strokeWidth={5} opacity={1-p*.6}/>;};

export const Kid=({x,y,s=1,t=0,ex='flat',look=[0,0],walk=0,aL=-15,aR=15,squash=0,rot=0,blink=0,sniff=0,lift=0,sweat=0,children})=>{
 const sw=Math.sin(walk),bob=walk?-Math.abs(sw)*14:0;
 const sL=[-80,-300+bob],sR=[80,-300+bob],eL=endPt(sL,aL,150),eR=endPt(sR,aR,150);
 return(<g transform={`translate(${x} ${y-lift}) scale(${s*(1+.08*squash)} ${s*(1-.12*squash)})`}>
  <ellipse cx={0} cy={lift/s} rx={115} ry={22} fill={C.dark} opacity={.22}/>
  <Limb a={[-38,-110]} b={[-38+sw*26,-16]} w={30} col={C.skin}/><Limb a={[38,-110]} b={[38-sw*26,-16]} w={30} col={C.skin}/>
  {[[-38+sw*26,-16],[38-sw*26,-16]].map((p,i)=><ellipse key={i} cx={p[0]+8} cy={p[1]+6} rx={34} ry={15} fill={C.dark} stroke={K} strokeWidth={6}/>)}
  <path d="M-90 -140 L90 -140 L84 -80 L8 -80 L0 -100 L-8 -80 L-84 -80Z" fill={C.grn2} stroke={K} strokeWidth={7} strokeLinejoin="round"/>
  <path d="M-84 -340 Q0 -364 84 -340 L92 -130 Q0 -112 -92 -130Z" fill={C.yel} stroke={K} strokeWidth={7} strokeLinejoin="round"/>
  <Limb a={sL} b={eL} bend={.12} w={28} col={C.skin}/><Hand p={eL} col={C.skin}/>
  <Limb a={sR} b={eR} bend={-.12} w={28} col={C.skin}/><Hand p={eR} col={C.skin}/>
  <g transform={`translate(0 ${-455+bob})`}><Head skin={C.skin} ex={ex} look={look} blink={blink} sniff={sniff} rot={rot}/></g>
  {sweat>0&&<Sweat x={118} y={-540+bob} t={t}/>}
  {children}
 </g>);
};

export const Mom=({x,y,s=1,t=0,ex='flat',look=[0,0],walk=0,aL=-30,aR=40,rot=0,blink=0,sniff=0,tint=0,children})=>{
 const sw=Math.sin(walk),bob=walk?-Math.abs(sw)*10:0,skin=tint?'#b9c48a':C.skin2;
 const sL=[-88,-325+bob],sR=[88,-325+bob],eL=endPt(sL,aL,170),eR=endPt(sR,aR,170);
 return(<g transform={`translate(${x} ${y}) scale(${s})`}>
  <ellipse cx={0} cy={4} rx={150} ry={24} fill={C.dark} opacity={.22}/>
  {[-48,48].map((p,i)=><ellipse key={i} cx={p+(i?1:-1)*sw*8} cy={-8} rx={36} ry={15} fill={C.dark} stroke={K} strokeWidth={6}/>)}
  <path d="M-90 -350 Q0 -375 90 -350 L132 -30 Q0 -6 -132 -30Z" fill={C.grn2} stroke={K} strokeWidth={7} strokeLinejoin="round"/>
  <path d="M-128 -54 Q0 -32 128 -54 L132 -30 Q0 -6 -132 -30Z" fill={C.wood} stroke={K} strokeWidth={6}/>
  <path d="M-90 -350 L-38 -352 L112 -150 L62 -120Z" fill={C.grn} stroke={K} strokeWidth={6} strokeLinejoin="round"/>
  <path d="M-90 -350 Q0 -375 90 -350 L84 -296 Q0 -274 -84 -296Z" fill={C.yel} stroke={K} strokeWidth={6} strokeLinejoin="round"/>
  <Limb a={sL} b={eL} bend={.1} w={32} col={skin}/><Hand p={eL} col={skin}/>
  <Limb a={sR} b={eR} bend={-.1} w={32} col={skin}/><Hand p={eR} col={skin}/>
  <g transform={`translate(0 ${-470+bob})`}><Head skin={skin} ex={ex} look={look} blink={blink} sniff={sniff} rot={rot} mom/></g>
  {children}
 </g>);
};

export const Dog=({x,y,s=1,t=0,bark=0})=>(
 <g transform={`translate(${x} ${y}) scale(${s})`}>
  <g transform={`rotate(${Math.sin(t*14)*18} 70 -70)`}><path d="M70 -70 Q130 -90 120 -150" fill="none" stroke={K} strokeWidth={30} strokeLinecap="round"/><path d="M70 -70 Q130 -90 120 -150" fill="none" stroke={C.tan} strokeWidth={18} strokeLinecap="round"/></g>
  <ellipse cx={0} cy={-60} rx={85} ry={56} fill={C.tan} stroke={K} strokeWidth={7}/>
  {[-45,45].map(p=><rect key={p} x={p-16} y={-40} width={32} height={42} rx={14} fill={C.tan} stroke={K} strokeWidth={7}/>)}
  <g transform={`translate(-72 ${-132-bark*14}) rotate(${-bark*6})`}>
   <ellipse cx={34} cy={-6} rx={22} ry={44} transform="rotate(20 34 -6)" fill={C.wood} stroke={K} strokeWidth={7}/>
   <circle r={52} fill={C.tan} stroke={K} strokeWidth={7}/>
   <ellipse cx={-34} cy={14} rx={34} ry={24} fill={C.cream} stroke={K} strokeWidth={7}/>
   <circle cx={-56} cy={6} r={10} fill={K}/>
   <circle cx={-8} cy={-14} r={9} fill={K}/>
   <path d={`M-52 32 Q-34 ${34+bark*26} -14 30`} fill={bark?'#7b2f2b':'none'} stroke={K} strokeWidth={6} strokeLinecap="round"/>
   <path d={`M-30 ${34+bark*8} q4 ${14+bark*10} 14 0`} fill="#e48a8a" stroke={K} strokeWidth={5}/>
  </g>
 </g>);

export const Pile=({x,y,s=1,pop=1})=>(
 <g transform={`translate(${x} ${y}) scale(${s*pop})`}>
  <path d="M-150 0 Q-165 -60 -95 -82 Q-30 -120 40 -90 Q130 -100 152 -20 L152 0Z" fill={C.grn} stroke={K} strokeWidth={7} strokeLinejoin="round"/>
  <path d="M-90 -2 Q-100 -70 -30 -70 L-10 -118 L40 -80 L60 -118 L110 -60 Q150 -40 130 -2Z" fill={C.yel} stroke={K} strokeWidth={7} strokeLinejoin="round"/>
  <path d="M-130 -2 Q-120 -45 -60 -40 Q-10 -48 10 -2Z" fill={C.cream} stroke={K} strokeWidth={6} strokeLinejoin="round"/>
  <path d="M-110 -12 H-20 M-100 -28 H-40" stroke={C.red} strokeWidth={5} opacity={.7}/>
 </g>);
export const Stain=({x,y,rx,ry,t})=><g><ellipse cx={x} cy={y} rx={rx*(1+.03*Math.sin(t*9))} ry={ry} fill={C.pee} opacity={.88}/><ellipse cx={x-rx*.3} cy={y-ry*.3} rx={rx*.25} ry={ry*.22} fill="#fff6b0" opacity={.5}/></g>;
export const Drops=({x,y,t,n=4,len=70})=><g>{Array.from({length:n}).map((_,i)=>{const p=(t*1.6+i/n)%1;return <path key={i} transform={`translate(${x+(i-n/2)*16} ${y+p*len})`} d="M0 -9 Q8 4 0 10 Q-8 4 0 -9Z" fill={C.pee} stroke={K} strokeWidth={2} opacity={1-p}/>;})}</g>;
export const Wavy=({x,y,t,col=C.grn2,n=3,h=110})=><g fill="none" stroke={col} strokeWidth={9} strokeLinecap="round">{Array.from({length:n}).map((_,i)=><path key={i} opacity={.55+.45*Math.sin(t*6+i*2)} transform={`translate(${x+(i-1)*34} ${y-Math.abs(Math.sin(t*3+i))*14})`} d={`M0 0 q14 ${-h/4} 0 ${-h/2} q-14 ${-h/4} 0 ${-h}`}/>)}</g>;
export const Note=({x,y,p})=><g transform={`translate(${x+Math.sin(p*8)*14} ${y-p*150})`} opacity={1-p}><ellipse cx={0} cy={0} rx={13} ry={10} fill={K}/><path d="M12 0 V-40 q16 6 14 24" fill="none" stroke={K} strokeWidth={5} strokeLinecap="round"/></g>;
export const Steam=({x,y,t})=><g>{[0,1,2,3].map(i=>{const p=(t*1.3+i/4)%1,sd=i%2?1:-1;return <circle key={i} cx={x+sd*(150+Math.sin(p*6+i)*14)} cy={y-p*190} r={16+p*34} fill={C.cream} stroke={K} strokeWidth={5} opacity={(1-p)*.9}/>;})}</g>;
export const Vein=({x,y,k=1})=><g transform={`translate(${x} ${y}) scale(${k})`} fill="none" stroke={C.red} strokeWidth={8} strokeLinecap="round"><path d="M-16 -18 Q0 -6 -16 8 M16 -18 Q0 -6 16 8"/></g>;
export const Sparkles=({x,y,t})=><g>{[[-120,-60],[130,-30],[40,-130]].map((o,i)=>{const k=.6+.4*Math.sin(t*7+i*2);return <path key={i} transform={`translate(${x+o[0]} ${y+o[1]}) scale(${k}) rotate(${t*40})`} d="M0 -20 L5 -5 L20 0 L5 5 L0 20 L-5 5 L-20 0 L-5 -5Z" fill="#fff2a0" stroke={K} strokeWidth={3}/>;})}</g>;
export const Bubble=({cx,cy,r,p,tx,ty})=>{
 const bumps=Array.from({length:8}).map((_,i)=>[cx+Math.cos(i*Math.PI/4)*r*.78,cy+Math.sin(i*Math.PI/4)*r*.72,r*.34]);
 const tail=[[tx,ty,16],[lerp(tx,cx,.28),lerp(ty,cy+r*.8,.3),24],[lerp(tx,cx,.55),lerp(ty,cy+r*.8,.62),32]];
 const all=[[cx,cy,r*.82],...bumps,...tail];
 return(<g transform={`translate(${tx} ${ty}) scale(${p}) translate(${-tx} ${-ty})`}>
  {all.map((c,i)=><circle key={'a'+i} cx={c[0]} cy={c[1]} r={c[2]} fill={C.cream} stroke={K} strokeWidth={7}/>)}
  {all.map((c,i)=><circle key={'b'+i} cx={c[0]} cy={c[1]} r={c[2]-3} fill={C.cream}/>)}
 </g>);};
export const Poof=({cx,cy,p})=><g opacity={1-p}>{Array.from({length:10}).map((_,i)=>{const a=i*Math.PI/5,r0=40+p*120,r1=r0+40*(1-p);return <line key={i} x1={cx+Math.cos(a)*r0} y1={cy+Math.sin(a)*r0} x2={cx+Math.cos(a)*r1} y2={cy+Math.sin(a)*r1} stroke={K} strokeWidth={9} strokeLinecap="round"/>;})}<circle cx={cx} cy={cy} r={30+p*90} fill="none" stroke={C.cream} strokeWidth={14}/></g>;

export const ScareDog=({j=.5,t=0})=>{
 const jw=j*230,M=1250+jw;
 const up=Array.from({length:8},(_,i)=>{const x=240+i*86;return `M${x} 1060 L${x+43} ${1150+(i%3)*22} L${x+86} 1060Z`;});
 const lo=Array.from({length:7},(_,i)=>{const x=283+i*86;return `M${x} ${M} L${x+43} ${M-115-(i%2)*28} L${x+86} ${M}Z`;});
 const veins=Array.from({length:14},(_,i)=>{const a=i*Math.PI/7;return [Math.cos(a)*40,Math.sin(a)*40,Math.cos(a+.15)*118,Math.sin(a+.15)*118];});
 const Eye=({x,flip})=>(<g transform={`translate(${x} 720)`}>
  <circle r={135} fill="#f4efe0" stroke="#000" strokeWidth={10}/>
  {veins.map((v,i)=><path key={i} d={`M${v[0]} ${v[1]} Q${v[0]*1.6+8} ${v[1]*1.6-8} ${v[2]} ${v[3]}`} stroke="#c01010" strokeWidth={5} fill="none"/>)}
  <circle cx={flip*10+Math.sin(t*30)*6} cy={8} r={30} fill="#000"/><circle cx={flip*10-6} cy={-2} r={8} fill="#fff"/>
 </g>);
 return(<g>
  <rect x={-60} y={-60} width={1200} height={2040} fill="#120505"/>
  <path d="M120 600 L30 110 L340 400Z" fill="#1e110b" stroke="#000" strokeWidth={10}/><path d="M960 600 L1050 110 L740 400Z" fill="#1e110b" stroke="#000" strokeWidth={10}/>
  <ellipse cx={540} cy={980} rx={480} ry={650} fill="#2b1a12" stroke="#000" strokeWidth={14}/>
  <ellipse cx={540} cy={1010} rx={310} ry={240} fill="#3b2418" stroke="#000" strokeWidth={8}/>
  <Eye x={350} flip={1}/><Eye x={730} flip={-1}/>
  <path d="M190 580 L505 745 L505 520 L300 480Z" fill="#1e110b" stroke="#000" strokeWidth={9}/><path d="M890 580 L575 745 L575 520 L780 480Z" fill="#1e110b" stroke="#000" strokeWidth={9}/>
  <path d="M430 450 L470 520 M650 450 L610 520 M540 400 V500" stroke="#000" strokeWidth={9} strokeLinecap="round"/>
  <ellipse cx={540} cy={885} rx={115} ry={72} fill="#000"/><ellipse cx={500} cy={865} rx={30} ry={14} fill="#555"/>
  <path d={`M230 1060 Q540 990 850 1060 L885 ${M} Q540 ${1400+jw} 195 ${M}Z`} fill="#4a0505" stroke="#000" strokeWidth={8}/>
  <ellipse cx={540} cy={M+10} rx={165} ry={70} fill="#8a1a1a"/>
  {lo.map((d,i)=><path key={'l'+i} d={d} fill="#fffbe8" stroke="#000" strokeWidth={5}/>)}
  {up.map((d,i)=><path key={'u'+i} d={d} fill="#fffbe8" stroke="#000" strokeWidth={5}/>)}
  <path d="M225 1062 Q540 985 855 1062" fill="none" stroke="#000" strokeWidth={26}/>
  <path d={`M190 ${M} Q540 ${1520+jw} 890 ${M} L910 ${M+90} Q540 ${1620+jw} 170 ${M+90}Z`} fill="#2b1a12" stroke="#000" strokeWidth={9}/>
  {[300,420,560,690,800].map((x,i)=><line key={i} x1={x} x2={x+Math.sin(t*9+i)*10} y1={M-10} y2={M+90+((t*3+i*.3)%1)*220} stroke="#c8e6ee" strokeWidth={9} strokeLinecap="round" opacity={.85}/>)}
 </g>);};

export const Room=({T=0})=>{
 const sway=Math.sin(T*1.6)*8;
 return(<g>
  <rect x={-60} y={-60} width={1200} height={2040} fill={C.wall}/>
  <rect x={-60} y={1180} width={1200} height={340} fill={C.wall2}/>
  <path d="M-60 1180 H1140" stroke={C.wood} strokeWidth={14}/>
  <rect x={-60} y={1500} width={1200} height={480} fill={C.floor}/>
  <rect x={-60} y={1500} width={1200} height={26} fill={C.wood2}/>
  {[1590,1690,1800,1910].map(y=><path key={y} d={`M-60 ${y} H1140`} stroke={C.floor2} strokeWidth={6}/>)}
  {[[200,1500,120,1590],[610,1500,590,1590],[920,1590,940,1690],[330,1690,300,1800]].map((l,i)=><path key={i} d={`M${l[0]} ${l[1]} V${l[3]}`} stroke={C.floor2} strokeWidth={5}/>)}
  <path d="M110 900 L350 900 L760 1900 L400 1900Z" fill="#fff0a8" opacity={.13}/>
  <rect x={90} y={430} width={300} height={470} fill="#fbf1c6" stroke={K} strokeWidth={9}/>
  {[140,190,240,290,340].map(x=><line key={x} x1={x} x2={x} y1={430} y2={900} stroke={C.wood2} strokeWidth={8}/>)}
  <line x1={90} x2={390} y1={660} y2={660} stroke={C.wood2} strokeWidth={8}/>
  <rect x={74} y={414} width={332} height={500} fill="none" stroke={C.wood} strokeWidth={22}/>
  <path d={`M70 410 H170 Q${150+sway} 600 ${160+sway} 930 H70Z`} fill={C.grn} stroke={K} strokeWidth={7}/>
  <path d={`M410 410 H310 Q${330+sway} 600 ${320+sway} 930 H410Z`} fill={C.grn} stroke={K} strokeWidth={7}/>
  <rect x={470} y={330} width={110} height={150} fill={C.cream} stroke={K} strokeWidth={6}/><rect x={470} y={330} width={110} height={34} fill={C.red} stroke={K} strokeWidth={6}/>
  <path d="M488 390 H562 M488 414 H562 M488 438 H540" stroke={C.wood} strokeWidth={5}/>
  <g transform="translate(900 400)"><path d="M0 0 q20 -20 50 -8 q16 -22 40 -4 l16 -6 l-12 14 q-16 12 -40 10 q-20 20 -52 6Z" fill={C.grn2} stroke={K} strokeWidth={5}/><circle cx={74} cy={-8} r={5} fill={K}/></g>
  <line x1={540} y1={-20} x2={540} y2={110} stroke={K} strokeWidth={8}/>
  <g transform={`rotate(${T*330} 540 130)`}>{[0,120,240].map(a=><ellipse key={a} cx={540+Math.cos(rad(a))*140} cy={130+Math.sin(rad(a))*140} rx={90} ry={16} transform={`rotate(${a} ${540+Math.cos(rad(a))*140} ${130+Math.sin(rad(a))*140})`} fill={C.wood} stroke={K} strokeWidth={6}/>)}</g>
  <circle cx={540} cy={130} r={30} fill={C.wood2} stroke={K} strokeWidth={7}/>
  <rect x={10} y={1030} width={44} height={330} fill={C.wood2} stroke={K} strokeWidth={7}/>
  <rect x={44} y={1290} width={540} height={60} fill={C.wood} stroke={K} strokeWidth={7}/>
  <rect x={50} y={1350} width={34} height={170} fill={C.wood2} stroke={K} strokeWidth={7}/><rect x={540} y={1350} width={34} height={170} fill={C.wood2} stroke={K} strokeWidth={7}/>
  <path d="M54 1296 V1200 Q54 1176 80 1176 H560 Q584 1176 584 1200 V1296Z" fill={C.yel} stroke={K} strokeWidth={8}/>
  <path d="M120 1200 V1290 M260 1200 V1290 M400 1200 V1290 M520 1200 V1290" stroke={C.grn2} strokeWidth={14}/>
  <ellipse cx={130} cy={1168} rx={80} ry={34} fill={C.cream} stroke={K} strokeWidth={7}/>
  <rect x={86} y={1390} width={450} height={110} fill={C.dark} opacity={.28}/>
 </g>);};

export const Almirah=({th=0,children})=>{
 const sx=Math.cos(rad(th));
 const Door=({hx,dir})=>(<g transform={`translate(${hx} 0) scale(${sx} 1) translate(${-hx} 0)`}>
  <rect x={dir>0?hx:hx-177} y={600} width={177} height={840} fill={C.wood} stroke={K} strokeWidth={8}/>
  <rect x={dir>0?hx+22:hx-155} y={640} width={133} height={360} fill="none" stroke={C.wood2} strokeWidth={7}/>
  <rect x={dir>0?hx+22:hx-155} y={1040} width={133} height={360} fill="none" stroke={C.wood2} strokeWidth={7}/>
  <circle cx={dir>0?hx+158:hx-158} cy={1020} r={12} fill={C.yel} stroke={K} strokeWidth={5}/>
 </g>);
 return(<g>
  <rect x={650} y={560} width={390} height={960} fill={C.wood2} stroke={K} strokeWidth={9}/>
  <rect x={634} y={534} width={422} height={42} fill={C.wood} stroke={K} strokeWidth={8}/>
  <rect x={668} y={600} width={354} height={840} fill="#53382a"/>
  <line x1={668} x2={1022} y1={800} y2={800} stroke={C.wood2} strokeWidth={10}/><line x1={668} x2={1022} y1={1000} y2={1000} stroke={C.wood2} strokeWidth={10}/>
  <rect x={668} y={1440} width={354} height={80} fill={C.wood} stroke={K} strokeWidth={8}/>
  <rect x={680} y={1520} width={40} height={26} fill={C.dark}/><rect x={970} y={1520} width={40} height={26} fill={C.dark}/>
  <clipPath id="int"><rect x={668} y={600} width={354} height={840}/></clipPath>
  <g clipPath="url(#int)">{children}</g>
  <Door hx={668} dir={1}/><Door hx={1022} dir={-1}/>
 </g>);};
'''

MAIN = r'''import React from 'react';
import {AbsoluteFill,Audio,staticFile,useCurrentFrame} from 'remotion';
import T from './timing.json';
import {C,clamp,ease,seg,lerp,back,Room,Almirah,Kid,Mom,Dog,Pile,Stain,Drops,Wavy,Note,Steam,Vein,Sparkles,Bubble,Poof,ScareDog} from './Art';

const FPS=T.fps;
const bl=s=>{const c=(s*60)%140;return c<7?Math.sin(c/7*Math.PI):0;};
const kf=(u,a)=>{if(u<=a[0][0])return a[0].slice(1);for(let i=1;i<a.length;i++){if(u<=a[i][0]){const p=ease((u-a[i-1][0])/(a[i][0]-a[i-1][0]));return a[i].slice(1).map((v,j)=>a[i-1][j+1]+(v-a[i-1][j+1])*p);}}return a[a.length-1].slice(1);};

const CAM=[
 [[0,540,960,1],[.07,380,1250,2],[.45,380,1270,2.2],[.55,380,1450,1.2],[.9,380,1450,1.25]],
 [[0,300,1300,1.15],[.18,430,1350,1.2],[.40,780,1350,1.25],[.46,845,1100,1.7],[.62,845,1030,2.3],[.88,845,1030,2.5],[.9,845,1040,2.7]],
 [[0,540,1100,1],[.2,540,1150,1.1],[.22,790,1250,1.7],[.34,790,1230,2.4],[.5,790,1230,2.4],[.58,300,1260,1.9],[.78,300,1260,2],[.8,420,1300,1.4]],
 [[0,330,1500,1.5],[.28,540,1450,1.2],[.4,780,1250,1.5],[.6,420,1100,1.5],[.66,600,900,1.9],[1,600,900,1.95]],
 [[0,600,1200,1.3],[.12,600,900,1.9],[.28,780,1260,1.9],[.5,330,1260,1.9],[.56,540,1000,1],[.86,540,1000,1.05],[.93,330,1240,2.2]],
 [[0,330,1225,2.97],[.41,330,1240,3.4]],
];
const FACE=[[380,1240],[845,1040],[300,1225],[600,860],[330,1225],[330,1240]];

const S1=({t,u,Tg})=>{
 const p=Math.abs(Math.sin(u*Math.PI*4)),sq=Math.max(0,1-p*3),kx=380,ky=1720,hy=ky-455*1.1-p*55;
 return(<g><Room T={Tg}/>
  <Kid x={kx} y={ky} s={1.1} lift={p*55} squash={sq} t={t} ex="angry" look={[Math.sin(t*5)*.5,.2]} aL={-25+Math.sin(t*30)*12} aR={25-Math.sin(t*30)*12} rot={Math.sin(t*40)*2.5} blink={bl(Tg)}/>
  <Steam x={kx} y={hy-10} t={t}/><Vein x={kx+75} y={hy-105} k={.8+.4*Math.sin(t*14)}/>
 </g>);};

const S2=({t,u,Tg})=>{
 const wp=seg(u,0,.42),dp=seg(u,.42,.54),jp=seg(u,.54,.63),inside=u>=.63,th=75*ease(dp);
 let kx=lerp(90,770,wp),ky=1720,ks=1.1,lift=0;
 if(u>.54&&!inside){kx=lerp(770,845,ease(jp));ky=lerp(1720,1400,ease(jp));ks=lerp(1.1,.8,ease(jp));lift=Math.sin(jp*Math.PI)*240;}
 if(inside){kx=845;ky=1400;ks=.8;}
 const back_=(u>.1&&u<.2)||(u>.27&&u<.37);
 let ex='sneaky',look=back_?[-1,-.2]:[1,0];
 if(u>.42&&u<.54)look=[.8,-.5];
 if(inside&&u<.9){ex='relief';look=[0,0];}
 if(u>=.9)look=[Math.sin(t*9)>0?1:-1,0];
 const walk=wp<1?wp*Math.PI*2*7:0,sp=seg(u,.65,.88);
 const kid=<Kid x={kx} y={ky} s={ks} lift={lift} walk={walk} t={t} ex={ex} look={look} blink={ex==='relief'?0:bl(Tg)} rot={inside&&u<.9?Math.sin(t*3)*3:0} aL={inside?-20:-65} aR={inside?20:65}>
  {!inside&&<Pile x={0} y={-215} s={.55}/>}</Kid>;
 return(<g><Room T={Tg}/>
  <Almirah th={th}>{inside&&<g>{kid}
   <Pile x={845} y={1440} s={1.35} pop={back(seg(u,.63,.7))}/>
   <Stain x={845} y={1330} rx={lerp(10,125,sp)} ry={lerp(4,26,sp)} t={t}/>
   {u>.65&&u<.9&&<g><Wavy x={845} y={1280} t={t} col="#e6d36a"/><Sparkles x={845} y={1040} t={t}/></g>}
  </g>}</Almirah>
  {!inside&&kid}
  {u>.7&&<g><rect x={832} y={1440} width={26} height={lerp(0,92,seg(u,.7,.8))} fill={C.pee}/><ellipse cx={845} cy={1538} rx={lerp(0,160,seg(u,.75,.95))} ry={26} fill={C.pee} opacity={.9}/>{u<.88&&<Drops x={845} y={1450} t={t} n={3} len={70}/>}</g>}
 </g>);};

const S3=({t,u,Tg})=>{
 const arr=ease(seg(u,0,.25)),mx=lerp(1350,800,arr),ms=1.15;
 const sn=u>.28&&u<.48?Math.abs(Math.sin((u-.28)/.2*Math.PI*3)):0,gag=u>.5&&u<.6;
 const ksn=u>.6&&u<.78?Math.abs(Math.sin((u-.6)/.18*Math.PI*2)):0,shr=ease(seg(u,.82,.88));
 const kLook=u<.55?[1,-.1]:u<.8?[Math.sin(t*3),-1]:[0,-.3];
 return(<g><Room T={Tg}/><Almirah th={0}/>
  <Kid x={300} y={1720} s={1.1} t={t} ex="innocent" look={kLook} sniff={ksn} aL={lerp(-12,-135,shr)} aR={lerp(12,135,shr)} blink={bl(Tg)} sweat={u>.8?1:0}/>
  {u>.55&&u<.82&&[0,1,2].map(i=><Note key={i} x={370} y={1190} p={(t*1.1+i/3)%1}/>)}
  <Mom x={mx} y={1720} s={ms} t={t} ex={gag?'gross':'flat'} look={u<.5?[-.6,.4]:[-1,0]} sniff={sn} walk={u<.25?arr*Math.PI*2*5:0} aL={-95} aR={35} rot={gag?Math.sin(t*45)*4:-sn*5} tint={gag?1:0} blink={bl(Tg)}>
   <Pile x={-257} y={-320} s={.55}/></Mom>
  {u<.62&&<Wavy x={mx-257*ms} y={1720-340*ms-70} t={t}/>}
 </g>);};

const S4=({t,u,Tg})=>{
 const gp=seg(u,0,.3),ma=ease(seg(u,.3,.45)),mx=lerp(1350,780,ma);
 const ex=u<.3?'relief':u<.5?'shock':u<.6?'sneaky':'grin';
 const pt=ease(seg(u,.58,.64)),bp=back(seg(u,.62,.72)),bk=Math.max(0,1-Math.abs(u-.7)/.035,1-Math.abs(u-.78)/.035);
 return(<g><Room T={Tg}/><Almirah th={0}/>
  <Stain x={330} y={1740} rx={lerp(10,175,gp)} ry={lerp(4,30,gp)} t={t}/>
  <Kid x={330} y={1720} s={1.1} t={t} ex={ex} look={u<.5?[0,.3]:[1,-1]} aL={-15} aR={lerp(15,130,pt)} sweat={u>.3?1:0} blink={u<.3?0:bl(Tg)} squash={u<.3?.15*Math.sin(t*6)**2:0}/>
  <Mom x={mx} y={1720} s={1.15} t={t} ex={u<.3?'flat':u<.62?'angry':'flat'} look={u<.62?[-1,.5]:[-1,-.6]} aL={-50} aR={55} walk={u>.3&&u<.45?ma*Math.PI*2*4:0} rot={u>.3&&u<.6?Math.sin(t*20)*2:0} blink={bl(Tg)}/>
  {u>.62&&<g><Bubble cx={600} cy={790} r={190} p={bp} tx={400} ty={1085}/><g transform={`translate(600 900) scale(${bp}) translate(-600 -900)`}><Dog x={600} y={905} s={.9} t={t} bark={bk}/></g></g>}
 </g>);};

const S5=({t,u,Tg})=>{
 const pop=seg(u,.12,.3);
 return(<g><Room T={Tg}/><Almirah th={0}/>
  <Stain x={330} y={1740} rx={175} ry={30} t={0}/>
  <Kid x={330} y={1720} s={1.1} t={t} ex="grin" look={u>.5?[Math.sin(t*8)>0?1:-1,0]:[1,-.2]} aL={-18} aR={18} rot={Math.sin(t*25)*1.5} sweat={1} blink={bl(Tg)}/>
  <Mom x={780} y={1720} s={1.15} t={t} ex="flat" look={u<.28?[-1,-.6]:[-1,.15]} aL={-50} aR={55} blink={bl(Tg)}/>
  {u<.15&&<g><Bubble cx={600} cy={790} r={190} p={1} tx={400} ty={1085}/><Dog x={600} y={905} s={.9} t={t} bark={0}/></g>}
  {u>=.12&&pop<1&&<Poof cx={600} cy={800} p={pop}/>}
 </g>);};

const S6=({t,u,Tg})=>(<g><Room T={Tg}/><Almirah th={0}/>
  <Stain x={330} y={1740} rx={175} ry={30} t={0}/>
  <Kid x={330} y={1720} s={1.1} t={t} ex={t<.5?'grin':t<.95?'flat':'shock'} look={[lerp(1,-1,seg(t,.3,.9)),0]} aL={-18} aR={18} sweat={1} blink={bl(Tg)} rot={Math.sin(t*25)*(t>.9?3:1)}/>
  <Mom x={780} y={1720} s={1.15} t={t} ex="flat" look={[-1,.15]} aL={-50} aR={55}/>
 </g>);
const SCENES=[S1,S2,S3,S4,S5,S6];

export const Main=()=>{
 const f=useCurrentFrame(),NB=T.bounds.length-1;
 let k=NB-1;for(let i=0;i<NB;i++){if(f<T.bounds[i+1]){k=i;break;}}
 const hold=T.holds[k],t0=T.bounds[k];
 const clock=g=>{let c=g;for(const [a,b] of T.holds){if(g>a)c-=Math.min(g,b)-a;}return c;};
 const t=(clock(f)-clock(t0))/FPS,ta=Math.max(.01,(hold[0]-t0)/FPS),u=Math.min(1,t/ta),Tg=clock(f)/FPS;
 const hp=f>=hold[0]?f-hold[0]:-1,pz=hp>=0?ease(hp/10):0;
 const scare=k===5&&t>=1.25;
 let [cx,cy,z]=kf(u,CAM[k]);
 cx=lerp(cx,FACE[k][0],pz);cy=lerp(cy,FACE[k][1],pz);
 z=z*(1+.35*pz)*(1+(hp>0?hp*.0006:0))*(1+.012*(T.env[f]||0));
 z=Math.max(1,z);cx=clamp(cx,540/z,1080-540/z);cy=clamp(cy,960/z,1920-960/z);
 const shk=(hp>=0&&hp<12?(1-hp/12)*12:0)+(k===0?3:0)+(k===5?2+8*seg(t,.5,1.25):0),sx=Math.sin(f*2.9)*shk,sy=Math.cos(f*3.7)*shk;
 const dark=k===5&&t<1.25?lerp(0,.55,t/1.25)+((f%7===0&&t>.7)?.25:0):0;
 const seed=Math.floor(clock(f)/6)%4+1,Sc=SCENES[k];
 let sc=null;
 if(scare){
  const td=t-1.28,W=<rect width={1080} height={1920}/>;
  if(t>=2.55)sc=<g><rect width={1080} height={1920} fill="#000"/><rect width={1080} height={1920} filter="url(#st)" opacity={.22}/></g>;
  else if(t>=2.5)sc=<rect width={1080} height={1920} fill="#fff"/>;
  else if(td<0)sc=<rect width={1080} height={1920} fill="#000"/>;
  else{
   const lunge=td<.07?lerp(.55,1.25,back(td/.07)):1.25+td*.2+Math.sin(td*45)*.04;
   const jx=Math.sin(f*7.3)*30,jy=Math.cos(f*5.9)*30,j=.35+.65*Math.abs(Math.sin(td*13)),inv=(f%11)<2;
   sc=<g><g transform={`translate(${540+jx} ${960+jy}) scale(${lunge}) translate(-540 -960)`} filter={inv?'url(#inv)':undefined}><ScareDog j={j} t={td}/></g>
    {f%5===0&&<rect width={1080} height={1920} fill="#ff0000" opacity={.35}/>}</g>;
  }
 }
 return(<AbsoluteFill style={{background:'#000'}}>
  <Audio src={staticFile('mix.wav')}/>
  <svg width={1080} height={1920} viewBox="0 0 1080 1920">
   <defs>
    <filter id="boil" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency="0.014" numOctaves="2" seed={seed} result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="6" xChannelSelector="R" yChannelSelector="G"/></filter>
    <filter id="inv"><feColorMatrix type="matrix" values="-1 0 0 0 1  0 -1 0 0 1  0 0 -1 0 1  0 0 0 1 0"/></filter>
    <filter id="st"><feTurbulence type="fractalNoise" baseFrequency="0.8" seed={f%50}/><feColorMatrix type="saturate" values="0"/></filter>
    <radialGradient id="vig" cx="50%" cy="50%" r="75%"><stop offset="55%" stopColor="#5a3a1c" stopOpacity="0"/><stop offset="100%" stopColor="#5a3a1c" stopOpacity=".38"/></radialGradient>
   </defs>
   {scare?sc:<g>
    <g transform={`translate(${540+sx} ${960+sy}) scale(${z}) translate(${-cx} ${-cy})`}><g filter="url(#boil)"><Sc t={t} u={u} Tg={Tg}/></g></g>
    <rect width={1080} height={1920} fill="#ffe3a0" opacity={.07}/>
    <rect width={1080} height={1920} fill="url(#vig)"/>
    {dark>0&&<rect width={1080} height={1920} fill="#000" opacity={Math.min(.85,dark)}/>}
    {hp>=0&&hp<6&&<rect width={1080} height={1920} fill="#fff" opacity={.45*(1-hp/6)}/>}
   </g>}
  </svg>
 </AbsoluteFill>);
};
'''

INDEX = "import {registerRoot} from 'remotion';\nimport {Root} from './Root';\nregisterRoot(Root);\n"
ROOT = ("import React from 'react';\nimport {Composition} from 'remotion';\nimport {Main} from './Main';\nimport T from './timing.json';\n"
        "export const Root=()=><Composition id=\"Main\" component={Main} durationInFrames={T.total} fps={T.fps} width={1080} height={1920}/>;\n")

RENDER_JS = r"""const path=require('path'),fs=require('fs');
const {bundle}=require('@remotion/bundler');
const {renderMedia,selectComposition}=require('@remotion/renderer');
(async()=>{
 const dir=process.argv[2],size=+process.argv[3];
 fs.mkdirSync(dir,{recursive:true});
 const serveUrl=await bundle({entryPoint:path.resolve('src/index.jsx'),publicDir:path.resolve('public'),onProgress:p=>console.log('BUNDLE '+p)});
 const composition=await selectComposition({serveUrl,id:'Main'});
 const total=composition.durationInFrames,n=Math.ceil(total/size);
 console.log('START '+total+' '+n);
 let done=0;
 for(let i=0;i<n;i++){
  const a=i*size,b=Math.min(total-1,a+size-1),name=path.join(dir,'part_'+String(i).padStart(4,'0')+'.mp4');
  if(fs.existsSync(name)){done+=b-a+1;console.log('SKIP '+done+' '+total);continue;}
  const tmp=name.replace(/\.mp4$/,'.tmp.mp4');
  await renderMedia({composition,serveUrl,codec:'h264',crf:17,pixelFormat:'yuv420p',muted:true,frameRange:[a,b],outputLocation:tmp,
   onProgress:({renderedFrames})=>console.log('FRAME '+(done+renderedFrames)+' '+total)});
  fs.renameSync(tmp,name);done+=b-a+1;console.log('CHUNK '+(i+1)+' '+n+' '+done+' '+total);
 }
 console.log('DONE');
})().catch(e=>{console.error(e);process.exit(1);});
"""


# ----------------------------------------------------------------------------- audio analysis
def ffcmd():
    ff = shutil.which("ffmpeg")
    return [ff] if ff else [shutil.which("npx") or "npx", "remotion", "ffmpeg"]


def decode_pcm(mp3, raw):
    # Remotion's bundled ffmpeg has no raw muxer, so decode to a 16-bit wav and read it with the wave module
    wav = str(Path(raw).with_suffix(".wav"))
    run(ffcmd() + ["-y", "-i", mp3, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", "-f", "wav", wav], cwd=PROJ)
    with wave.open(wav, "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    Path(wav).unlink(missing_ok=True)
    return data


def find_pauses(x, dur):
    win = SR // 100
    n = len(x) // win
    db = 20 * np.log10(np.sqrt((x[:n * win].reshape(n, win) ** 2).mean(1)) + 1e-9)
    found = []
    for thr in (-38, -34, -30, -26, -22):
        found, i = [], 0
        sil = db < thr
        while i < n:
            if sil[i]:
                j = i
                while j < n and sil[j]:
                    j += 1
                a, b = i / 100, j / 100
                if b - a >= .22 and a > .3 and b < dur - .25:
                    found.append((a, b))
                i = j
            else:
                i += 1
        if len(found) >= 4:
            break
    found = sorted(sorted(found, key=lambda p: p[0] - p[1])[:4])
    k = 1
    while len(found) < 4:                      # fallback: even split
        found.append((dur * k / 5, dur * k / 5)); k += 1
    return sorted(found)


def frame_env(x, total):
    sq = np.concatenate([[0], np.cumsum(x.astype(np.float64) ** 2)])
    idx = np.arange(total)
    a = np.clip(((idx - .5) * SR / FPS).astype(int), 0, len(x))
    b = np.clip(((idx + 1.5) * SR / FPS).astype(int), 0, len(x))
    e = np.sqrt((sq[b] - sq[a]) / np.maximum(b - a, 1))
    e = np.clip(e / (np.percentile(e, 98) + 1e-9), 0, 1)
    return np.convolve(e, [.25, .5, .25], "same")


# ----------------------------------------------------------------------------- sound design
rng = np.random.default_rng(7)
def tt(d): return np.arange(int(d * SR)) / SR
def hann(d): return np.hanning(int(d * SR))
def lp(n, k): return np.convolve(n, np.ones(k) / k, "same")
def sine(f, d, dec=8): t = tt(d); return np.sin(2 * np.pi * f * t) * np.exp(-dec * t)
def slide(f0, f1, d, dec=3, saw=False, vib=0):
    t = tt(d); f = f0 * (f1 / f0) ** (t / d) * (1 + vib * np.sin(2 * np.pi * 6 * t))
    ph = np.cumsum(2 * np.pi * f / SR)
    s = (((ph / (2 * np.pi)) % 1) * 2 - 1) if saw else np.sin(ph)
    return lp(s, 6) * np.exp(-dec * t) if saw else s * np.exp(-dec * t)
def noise(d, dec=10, l=0, h=0):
    n = rng.standard_normal(int(d * SR))
    if l: n = lp(n, l)
    if h: n = n - lp(n, h)
    return n * np.exp(-dec * tt(d))

def mx(*a):
    n = max(len(i) for i in a); o = np.zeros(n)
    for i in a: o[:len(i)] += i
    return o

def s_boing():
    t = tt(.5); f = 250 + 500 * np.exp(-9 * t) + 90 * np.sin(2 * np.pi * 16 * t) * np.exp(-5 * t)
    return np.sin(np.cumsum(2 * np.pi * f / SR)) * np.exp(-4 * t)
def s_thump(): return mx(slide(150, 40, .2, 16), noise(.02, 100, 3) * .5)
def s_step(): return slide(120, 60, .1, 30) * .7
def s_zip(): return mx(noise(.2, 0, 5) * hann(.2) * 1.2, slide(300, 2400, .15, 6) * .25)
def s_pluck(f): return mx(sine(f, .22, 14), .4 * sine(2 * f, .22, 20))
def s_gulp(): return slide(420, 140, .12, 12)
def s_creak():
    d = .6; t = tt(d); f = 220 + 140 * t / d + 25 * np.sin(2 * np.pi * 23 * t)
    s = ((np.cumsum(f) / SR) % 1) * 2 - 1
    return lp(s, 5) * hann(d) * (.6 + .4 * np.abs(np.sin(2 * np.pi * 9 * t)))
def s_trickle(d):
    n = int(d * SR); out = lp(rng.standard_normal(n), 3) * .22
    for _ in range(int(d * 28)):
        b = sine(rng.uniform(500, 1500), .05, 60) * .5; i = rng.integers(0, max(1, n - len(b)))
        out[i:i + len(b)] += b[:max(0, n - i)][:len(b)] if i + len(b) <= n else b[:n - i]
    return out * np.minimum(1, np.minimum(tt(d) * 15, (d - tt(d)) * 15))
def s_sniff(): d = .14; return (noise(d, 0, 0, 8)) * hann(d) * .9
def s_gag(): return slide(320, 80, .4, 4, True, .05)
def s_whistle():
    out = np.zeros(int(1.1 * SR))
    for i, f in enumerate((1318, 1480, 1568, 1760)):
        s = slide(f, f * 1.04, .22, 2, vib=.01) * hann(.22) * .5; o = int(i * .26 * SR); out[o:o + len(s)] += s
    return out
def s_dundun():
    a, b = sine(98, .4, 5) + sine(196, .4, 7) * .4, sine(87, .6, 4) + sine(174, .6, 6) * .4
    out = np.zeros(int(1 * SR)); out[:len(a)] += a; o = int(.3 * SR); out[o:o + len(b)] += b; return out
def s_bark(): return mx(slide(560, 230, .14, 14, True), noise(.1, 25, 3) * .4)
def s_poof(): return mx(noise(.3, 9, 5), sine(180, .2, 15) * .5)
def s_ding(): return mx(sine(1760, .7, 5), .5 * sine(2637, .5, 7))
def s_bonk(): return mx(sine(880, .12, 35), .5 * sine(1320, .1, 45), s_thump() * .5)
def s_cricket():
    out = np.zeros(int(.35 * SR))
    for j in range(4): s = sine(4300, .035, 35); o = int(j * .06 * SR); out[o:o + len(s)] += s
    return out
def s_trombone():
    out = np.zeros(int(2.2 * SR)); o = 0
    for f0, f1, d in ((233, 220, .38), (220, 208, .38), (208, 196, .38), (196, 140, .55)):
        s = slide(f0, f1, d, 1.2, True, .03) * np.minimum(1, tt(d) * 30); out[o:o + len(s)] += s; o += int((d + .02) * SR)
    return out

def s_heart(): return mx(slide(70, 40, .22, 12), sine(110, .15, 25) * .4)
def s_riser(d):
    n = int(d * SR); t = tt(d); f = 70 * (1100 / 70) ** (t / d)
    nz = (rng.standard_normal(n) - lp(rng.standard_normal(n), 4)) * .35
    return (np.sin(np.cumsum(2 * np.pi * f / SR)) * .8 + nz) * np.linspace(0, 1, n) ** 2.2
def s_scream(d=1.22):
    t = tt(d); n = len(t)
    f = 700 + 500 * (1 - np.exp(-6 * t)) + 45 * np.sin(2 * np.pi * 55 * t) + lp(rng.standard_normal(n), 900) * 500
    ph = np.cumsum(2 * np.pi * f / SR)
    sig = sum(((ph * r / (2 * np.pi)) % 1) * 2 - 1 for r in (1, 1.007, 1.5, 2.01)) / 4
    sig = np.tanh(sig * 5) * np.minimum(1, t * 80) * (1 - .2 * t / d) + rng.standard_normal(n) * .5 * np.exp(-2 * t)
    return np.tanh(sig * 2.5)
def s_boom(): return mx(slide(130, 28, 1.2, 2.2) * 1.3, noise(.5, 5, 10) * 1.2)
def s_dbark(): return np.tanh(s_bark() * 6)
def s_ring(): return sine(6200, .8, 3) * .25

def make_music(n):
    t_end = n / SR; beat = 60 / 112; out = np.zeros(n)
    sc = [261.63, 293.66, 329.63, 392.0, 440.0, 523.25, 587.33, 659.25]
    mel = [0, 2, 4, 2, 5, 4, 2, 1, 0, 2, 4, 5, 7, 5, 4, 2]; bass = [130.8, 196.0, 220.0, 174.6]
    def put(sig, t0, g):
        i = int(t0 * SR)
        if i < n: seg_ = sig[:n - i]; out[i:i + len(seg_)] += seg_ * g
    for i in range(int(t_end / (beat / 2)) + 1):
        t0 = i * beat / 2
        f = sc[mel[i % 16]]; put(mx(sine(f, .35, 7), .3 * sine(4 * f, .35, 18)), t0, .5)
        if i % 2 == 0: put(sine(bass[(i // 8) % 4], .4, 5) * .9, t0, .6)
        else: put(noise(.04, 60, 0, 4), t0, .12)
    return out

def build_mix(x, total, pauses, bounds, holds):
    n = int(total / FPS * SR); A = bounds[5] / FPS; An = int(A * SR)
    narr = np.zeros(n); m_ = min(n, len(x)); narr[:m_] = x[:m_]
    env = lp(np.abs(narr), int(.15 * SR)); env = np.clip(env / (np.percentile(env, 98) + 1e-9), 0, 1)
    gate = np.ones(n)
    for ps, pe in pauses: gate[int(ps * SR):int(pe * SR)] = 0
    gate[An:] = 0; gate = lp(gate, int(.06 * SR))
    pkn = np.percentile(np.abs(narr[:An]), 99.8) + 1e-9
    narr = narr * (.85 / pkn)                       # voice = loudest element
    music = make_music(n) * .09 * (1 - .6 * env) * gate
    sfx = np.zeros(n)                               # SFX bus: quiet, ducked while the voice speaks
    starts = [b / FPS for b in bounds[:5]]; acts = [h[0] / FPS for h in holds[:5]]
    def at(k, u): return starts[k] + u * (acts[k] - starts[k])
    def put(sig, t0, g=1.0):
        i = int(max(0, t0) * SR)
        if i < n: s_ = sig[:n - i]; sfx[i:i + len(s_)] += s_ * g
    for k in range(5):
        put(s_zip(), at(k, 0), .35); put(s_bonk(), acts[k], .55)
    for u in (.25, .5, .75, .98): put(s_thump(), at(0, u), .9)
    put(s_boing(), at(0, .07), .5)
    put(slide(700, 1500, .8, 0) * hann(.8), at(0, .3), .18)
    for u, f in zip((.05, .11, .17, .23, .29, .35, .41), (523, 494, 466, 440, 466, 440, 392)): put(s_pluck(f), at(1, u), .45)
    for u in (.15, .31): put(s_gulp(), at(1, u), .5)
    put(s_creak(), at(1, .42), .5); put(s_boing(), at(1, .54), .45); put(s_thump(), at(1, .63), .7)
    put(s_trickle(.24 * (acts[1] - starts[1])), at(1, .64), .55); put(s_ding(), at(1, .9), .4)
    for u in (.04, .10, .16, .22): put(s_step(), at(2, u), .5)
    for u in (.313, .38, .447): put(s_sniff(), at(2, u), .7)
    put(s_gag(), at(2, .5), .4); put(s_zip(), at(2, .22), .3); put(s_zip(), at(2, .58), .3)
    put(s_whistle(), at(2, .56), .25)
    for u in (.64, .70): put(s_sniff(), at(2, u), .5)
    put(s_boing(), at(2, .83), .45)
    put(s_trickle(.28 * (acts[3] - starts[3])), at(3, .02), .55); put(s_dundun(), at(3, .30), .55)
    put(s_boing(), at(3, .58), .4); put(s_poof(), at(3, .63), .3)
    for u in (.70, .78): put(s_bark(), at(3, u), .6)
    put(s_poof(), at(4, .15), .6)
    for u in np.linspace(.30, .80, 9): put(s_cricket(), at(4, u), .22)
    put(s_zip(), at(4, .56), .3); put(s_trombone(), at(4, .60), .5); put(s_zip(), at(4, .93), .3)
    mix = narr + music + sfx * SFX_LEVEL * (1 - .5 * env)
    pk = np.abs(mix[:An]).max()
    if pk > .97: mix *= .97 / pk
    mix[An:] = 0; fo = int(.03 * SR); mix[An - fo:An] *= np.linspace(1, 0, fo)
    def put(sig, t0, g=1.0):                         # scare hits go straight to the mix at full level
        i = int(max(0, t0) * SR)
        if i < n: s_ = sig[:n - i]; mix[i:i + len(s_)] += s_ * g
    # ---- jumpscare (after narration): heartbeat + riser -> silence -> scream/boom/barks -> hard cut
    for d in (.2, .36, .7, .83, 1.0, 1.1): put(s_heart(), A + d, .9)
    put(s_riser(.87), A + .25, .35)
    put(s_scream(), A + 1.28, 1.0); put(s_boom(), A + 1.28, 1.0)
    for d in (.5, .85, 1.1): put(s_dbark(), A + 1.28 + d, .8)
    put(s_ring(), A + 2.5, .3)
    return np.clip(mix, -1, 1)


def write_wav(path, mono):
    pcm = (np.clip(mono, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(np.repeat(pcm[:, None], 2, 1).tobytes())


# ----------------------------------------------------------------------------- main
def main():
    if "--clean" in sys.argv: shutil.rmtree(DIR / "render_cache", ignore_errors=True); print("render cache cleared")
    P.start(0)
    node, npm = shutil.which("node"), shutil.which("npm")
    if not PREP and not (node and npm): sys.exit("\nNode.js/npm not found. Install Node 18+ from nodejs.org")
    if not AUDIO.exists():
        alt = Path(__file__).parent / "20204.mp3"
        if alt.exists(): DIR.mkdir(parents=True, exist_ok=True); shutil.copy(alt, AUDIO)
        else: sys.exit(f"\nMissing audio: {AUDIO}")
    P.done("node/npm/audio OK")

    P.start(1)
    (PROJ / "src").mkdir(parents=True, exist_ok=True); (PROJ / "public").mkdir(exist_ok=True)
    for name, txt in (("src/Art.jsx", ART), ("src/Main.jsx", MAIN), ("src/index.jsx", INDEX), ("src/Root.jsx", ROOT), ("render.js", RENDER_JS)):
        (PROJ / name).write_text(txt, encoding="utf-8")
    if not (PROJ / "package.json").exists(): (PROJ / "package.json").write_text('{"name":"cnd","private":true}', encoding="utf-8")
    P.done("6 source files")

    P.start(2)
    if PREP: P.done("skipped (--prep)")
    elif (PROJ / "node_modules" / "remotion").exists(): P.done("already installed")
    else:
        P.line(.1, "npm install (1-3 min)...")
        run([npm, "install", "--no-audit", "--no-fund", "--loglevel=error", "remotion@^4", "@remotion/bundler@^4",
             "@remotion/renderer@^4", "@remotion/cli@^4", "react@18", "react-dom@18"], cwd=PROJ)
        P.done()

    P.start(3)
    raw = PROJ / "pcm.raw"; P.line(.2, "decoding mp3")
    x = decode_pcm(str(AUDIO), str(raw)); raw.unlink(missing_ok=True)
    dur = len(x) / SR; atotal = math.ceil(dur * FPS); total = atotal + SCARE
    P.line(.6, "finding pauses")
    pauses = find_pauses(x, dur)
    bounds = [0] + [round(pe * FPS) for _, pe in pauses] + [atotal, total]
    holds = []
    for k, (ps, pe) in enumerate(pauses):
        b = bounds[k + 1]; a = min(max(round((ps + .12) * FPS), bounds[k] + 30), b - 6); holds.append([a, b])
    holds.append([max(atotal - 54, bounds[4] + 30), atotal]); holds.append([total, total])
    P.line(.9, "frame envelope")
    env = frame_env(x, total)
    (PROJ / "src" / "timing.json").write_text(json.dumps({"fps": FPS, "total": total, "bounds": bounds, "holds": holds,
                                                           "env": [round(float(v), 3) for v in env]}), encoding="utf-8")
    P.done(f"{dur:.2f}s audio + {SCARE/FPS:.1f}s scare = {total} frames; cuts @ " + ", ".join(f"{b/FPS:.2f}s" for b in bounds[1:5]))

    P.start(4)
    P.line(.3, "synth SFX + music + jumpscare")
    mix = build_mix(x, total, pauses, bounds, holds)
    write_wav(PROJ / "public" / "mix.wav", mix)
    P.done(f"mix.wav {len(mix)/SR:.2f}s")
    if PREP: print("--prep done."); return

    # render in saved chunks: finished chunks survive Ctrl-C / crashes and are skipped on re-run
    h = hashlib.md5((ART + MAIN + ROOT + INDEX + (PROJ / "src" / "timing.json").read_text(encoding="utf-8")).encode()).hexdigest()[:10]
    cdir = DIR / "render_cache" / h
    P.start(5)
    nch0 = math.ceil(total / CHUNK); have = len(list(cdir.glob("part_????.mp4"))) if cdir.exists() else 0
    print(f"\n   cache folder : {cdir}\n   saved chunks : {have}/{nch0} found" + ("  -> resuming" if have else "  (fresh render)"))
    pr = subprocess.Popen([node, "render.js", str(cdir), str(CHUNK)], cwd=PROJ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace", bufsize=1)
    tail, t0, skipped, tot, nch = [], None, 0, total, math.ceil(total / CHUNK)
    P.line(0, "bundling (first run downloads Chromium)")
    try:
        for ln in pr.stdout:
            ln = ln.strip(); tail = (tail + [ln])[-25:]; w = ln.split()
            if not w: continue
            if w[0] == "BUNDLE": P.line(.03 * float(w[1]) / 100, f"bundling {w[1]}%")
            elif w[0] == "START": tot, nch = int(w[1]), int(w[2])
            elif w[0] == "SKIP": skipped = int(w[1]); P.line(.03 + .92 * skipped / tot, f"resumed: {skipped}/{tot} fr cached")
            elif w[0] in ("FRAME", "CHUNK"):
                if w[0] == "CHUNK": print(f"\n   saved chunk {w[1]}/{w[2]}  ({w[3]}/{w[4]} frames safe on disk)")
                cum = int(w[1]) if w[0] == "FRAME" else int(w[3]); t0 = t0 or time.time()
                el = time.time() - t0; r = cum - skipped; fps_ = r / el if el > 1 else 0
                eta = (tot - cum) / fps_ if fps_ else 0
                P.line(.03 + .92 * cum / tot, f"{cum}/{tot} fr {fps_:.1f}fps ETA {eta:.0f}s")
    except KeyboardInterrupt:
        pr.kill(); sys.exit("\n\nStopped. Finished chunks are saved in render_cache - run again to resume.")
    if pr.wait(): sys.exit("\nRender failed (finished chunks are kept):\n" + "\n".join(tail))
    parts = sorted(cdir.glob("part_????.mp4"))
    if len(parts) != nch: sys.exit(f"\nExpected {nch} chunks, found {len(parts)}")
    P.line(.96, "joining chunks + audio")
    lst = cdir / "list.txt"; lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    OUT.unlink(missing_ok=True)
    mix_wav = PROJ / "public" / "mix.wav"
    r = subprocess.run([str(c) for c in ffcmd() + ["-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", mix_wav, "-map", "0:v:0", "-map", "1:a:0",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", OUT]], cwd=PROJ, capture_output=True, text=True, errors="replace")
    if r.returncode:      # fallback for stripped ffmpeg builds: concat filter + re-encode
        ins = sum([["-i", p] for p in parts], [])
        fc = "".join(f"[{i}:v]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
        run(ffcmd() + ["-y"] + ins + ["-i", mix_wav, "-filter_complex", fc, "-map", "[v]", "-map", f"{len(parts)}:a", "-c:v", "libx264", "-crf", "17",
                       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", OUT], cwd=PROJ)
    P.done(f"saved {OUT.name} ({OUT.stat().st_size/1e6:.1f} MB)")
    print(f"\nDONE -> {OUT}\nChunks kept in {cdir} (re-run resumes/re-joins instantly; --clean deletes cache)")


if __name__ == "__main__":
    main()
