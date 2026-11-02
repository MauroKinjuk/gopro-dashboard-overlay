#!/usr/bin/env python3
"""Find interesting ride segments with gap-cleaned data."""
import sys, datetime
import numpy as np
import gpxpy

def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2-p1; dl = np.radians(lon2-lon1)
    a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 2*R*np.arcsin(np.sqrt(a))

def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2-lon1)
    y = np.sin(dl)*np.cos(p2)
    x = np.cos(p1)*np.sin(p2)-np.sin(p1)*np.cos(p2)*np.cos(dl)
    return np.degrees(np.arctan2(y, x))

def load(f):
    gpx = gpxpy.parse(open(f, encoding="utf-8"))
    e = [p for tr in gpx.tracks for s in tr.segments for p in s.points if p.time]
    e.sort(key=lambda p: p.time)
    t = np.array([p.time.replace(tzinfo=datetime.timezone.utc).timestamp() for p in e])
    lat = np.array([p.latitude for p in e]); lon = np.array([p.longitude for p in e])
    ele = np.array([p.elevation or 0 for p in e])
    dt = np.diff(t)
    d = hav(lat[:-1], lon[:-1], lat[1:], lon[1:])
    spd = np.where((dt>0)&(dt<=10), d/np.maximum(dt,1e-9), np.nan)*3.6
    spd = np.where(spd<80, spd, np.nan)
    hd = bearing(lat[:-1], lon[:-1], lat[1:], lon[1:])
    dhd = np.abs(np.diff(hd)); dhd = np.minimum(dhd, 360-dhd)
    turn = np.where((dt[1:]>0)&(dt[1:]<=10), dhd/np.maximum(dt[1:],1e-9), np.nan)
    turn = np.clip(turn, 0, 120)
    g = np.arange(t[0], t[-1])
    # assign each grid second the interval containing it; NaN where gap
    idx = np.clip(np.searchsorted(t[:-1], g, side="right")-1, 0, len(dt)-1)
    valid = (g <= t[-2]) & (dt[idx] <= 10)
    gs = np.where(valid, spd[idx], np.nan)
    tidx = np.clip(np.searchsorted(t[1:-1], g, side="right"), 0, len(turn)-1)
    tvalid = (g >= t[1]) & (g <= t[-2]) & (dt[1:][tidx] <= 10)
    gt = np.where(tvalid, turn[tidx], np.nan)
    ge = np.interp(g, t, ele)
    return g, gs, ge, gt

def hh(ts): return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime('%H:%M:%S')

def rank_windows(g, score, W=60, valid=None, topk=8, min_sep=240, min_valid=0.8):
    n = len(score)-W
    out = []
    valid = np.ones_like(score, bool) if valid is None else valid
    vals = []
    for i in range(n):
        seg = score[i:i+W]; v = valid[i:i+W]
        if np.isnan(seg).sum() > W*(1-min_valid) or v.sum() < W*min_valid:
            vals.append(-np.inf)
        else:
            vals.append(np.nanmean(seg))
    vals = np.array(vals)
    order = np.argsort(-vals)
    for i in order:
        if all(abs(i-j) >= min_sep for j in out):
            out.append(i)
        if len(out) >= topk:
            break
    return [(g[i], g[i+W], vals[i]) for i in out if np.isfinite(vals[i])]

for f in sys.argv[1:]:
    print('='*20, f.split('\\')[-1])
    g, spd, ele, turn = load(f)
    d60 = np.array([ele[i+60]-ele[i] for i in range(len(ele)-60)])
    spd60 = np.array([np.nanmean(spd[i:i+60]) for i in range(len(spd)-60)])
    nan60 = np.array([np.isnan(spd[i:i+60]).sum() for i in range(len(spd)-60)])
    dele = ele  # per-second elevation
    # descents: lose >=10m and fast
    desc_score = np.where(d60 < -8, -d60 * np.clip(spd60,0,None), -np.inf)
    valid = nan60 <= 12
    print('--- DESCENTS (60s, ele loss & speed) ---')
    n = len(spd)-60
    rows = []
    for i in range(n):
        if nan60[i] <= 12:
            rows.append((i, d60[i], spd60[i]))
    rows = [r for r in rows if r[1] < -8]
    rows.sort(key=lambda r: r[1]*r[2])
    picks=[]
    for i,de,sp in rows:
        if all(abs(i-j)>=240 for j,_ in picks): picks.append((i,(de,sp)))
        if len(picks)>=8: break
    for i,(de,sp) in picks:
        print(f'  {hh(g[i])}-{hh(g[i+60])}  {de:+6.1f}m  {sp:4.1f}km/h')
    print('--- CLIMBS (60s, gain & grade) ---')
    rows = [(i, d60[i], spd60[i]) for i in range(n) if nan60[i] <= 12 and d60[i] > 10]
    rows.sort(key=lambda r: -r[1])
    picks=[]
    for i,de,sp in rows:
        if all(abs(i-j)>=240 for j,_ in picks): picks.append((i,(de,sp)))
        if len(picks)>=8: break
    for i,(de,sp) in picks:
        print(f'  {hh(g[i])}-{hh(g[i+60])}  +{de:5.1f}m  {sp:4.1f}km/h')
    print('--- TWISTY (turn deg/s * speed, 60s) ---')
    tw = np.where(np.isnan(turn)|np.isnan(spd), np.nan, turn*spd)
    for a,b,sc in rank_windows(g, tw, topk=6):
        i = int(a-g[0])
        print(f'  {hh(a)}-{hh(b)}  score={sc:5.0f} spd={np.nanmean(spd[i:i+60]):.1f}km/h')
