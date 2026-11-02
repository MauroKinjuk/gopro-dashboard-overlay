#!/usr/bin/env python3
"""Find talky segments: high voice-band (300-3400Hz) energy while GPX speed low.
Usage: find_talks.py day1|day2"""
import sys, json, subprocess, datetime
from pathlib import Path
import numpy as np
import gpxpy

VDIR = Path(r"E:\Videos\Crudos\Training Camp")
# recording -> (est_start_gpx 'HH:MM:SS', [chapter durations], date)
RECS = {
 "0151": ("14:41:45", [1217.2,1217.2,165.7], "2026-10-03", "gpx1"),
 "0152": ("15:30:57", [1217.2,1217.2,68.0],  "2026-10-03", "gpx1"),
 "0153": ("16:17:29", [1217.2,1217.2,1217.2,1217.2,89.8], "2026-10-03", "gpx1"),
 "0154": ("12:21:05", [1217.2,1217.2,1217.2,328.3], "2026-10-04", "gpx2"),
 "0155": ("13:32:51", [1217.2,163.8], "2026-10-04", "gpx2"),
 "0156": ("13:57:45", [1217.2]*7+[243.1], "2026-10-04", "gpx2"),
}
GPX = {"gpx1": r"C:\Users\tordy\Downloads\Training_Camp.gpx",
       "gpx2": r"C:\Users\tordy\Downloads\Training_Camp_Día_2.gpx"}

def hav(a,b,c,d):
    R=6371000;p1,p2=np.radians(a),np.radians(c);dp=p2-p1;dl=np.radians(d-b)
    x=np.sin(dp/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 2*R*np.arcsin(np.sqrt(x))

def load_spd(f):
    gpx=gpxpy.parse(open(f,encoding='utf-8'))
    e=[p for tr in gpx.tracks for s in tr.segments for p in s.points if p.time]
    e.sort(key=lambda p:p.time)
    t=np.array([p.time.replace(tzinfo=datetime.timezone.utc).timestamp() for p in e])
    lat=np.array([p.latitude for p in e]);lon=np.array([p.longitude for p in e])
    dt=np.diff(t);d=hav(lat[:-1],lon[:-1],lat[1:],lon[1:])
    spd=np.where((dt>0)&(dt<=10),d/np.maximum(dt,1e-9),0)*3.6
    g=np.arange(t[0],t[-1])
    idx=np.clip(np.searchsorted(t[:-1],g,'right')-1,0,len(dt)-1)
    s=np.where((g<=t[-2])&(dt[idx]<=10),spd[idx],np.nan)
    return g,s

def hh(x): return datetime.datetime.fromtimestamp(x,datetime.timezone.utc).strftime('%H:%M:%S')

which = sys.argv[1] if len(sys.argv)>1 else 'gpx1'
g,s = load_spd(GPX[which])
g0 = g[0]

for rec,(est,chd,day,gk) in RECS.items():
    if gk != which: continue
    h,m,sx = map(int,est.split(':')); y,mo,dd = map(int,day.split('-'))
    t0 = datetime.datetime(y,mo,dd,h,m,sx,tzinfo=datetime.timezone.utc).timestamp()
    coff = 0.0
    for ci,dur in enumerate(chd):
        f = f"GX{ci+1:02d}{rec}"
        npz = VDIR/f"{f}.syncsig.npz"
        npz2 = VDIR/f"{f}.windsig.npz"
        if npz.exists():
            w = np.load(npz)['wind'].astype(float)
        elif npz2.exists():
            w = np.load(npz2)['wind'].astype(float)
        else:
            continue
        n=len(w)
        idx = np.arange(n)+t0+coff-g0
        ok=(idx>=0)&(idx<len(s))
        sp = np.where(ok, s[np.clip(idx.astype(int),0,len(s)-1)], np.nan)
        sp = np.where(np.isnan(sp) & ok, 0.0, sp)  # gaps in track = probably stopped
        # talky windows: slow (<6kmh) + voice energy high
        W=90
        best=[]
        for i in range(0,n-W):
            seg_w=w[i:i+W]; seg_s=sp[i:i+W]
            if np.isnan(seg_s).sum()>W*0.4: continue
            if np.nanmean(seg_s)<6:
                best.append((np.nanmean(seg_w), i))
        best.sort(reverse=True)
        picks=[]
        for sc,i in best:
            if all(abs(i-j)>=240 for j in picks): picks.append(i)
            if len(picks)>=4: break
        for i in picks:
            print(f'{f} t={i:4d}-{i+W}  gpx {hh(t0+coff+i)}  voice={w[i:i+W].mean():.0f}  spd={np.nanmean(sp[i:i+W]):.1f}kmh')
        coff += dur
