#!/usr/bin/env python3
"""Focused sync check: score video<->GPX offsets within +/-120s of creation_time.
Each signal is matched against its proper track feature:
  wind/vibration -> speed,  yawrate -> turn-rate (heading change while moving).
Usage: sync_fine.py video.mp4 track.gpx"""
import sys, json, subprocess, datetime
from pathlib import Path
import numpy as np
import gpxpy


def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 2*R*np.arcsin(np.sqrt(a))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    y = np.sin(dl)*np.cos(p2)
    x = np.cos(p1)*np.sin(p2)-np.sin(p1)*np.cos(p2)*np.cos(dl)
    return np.degrees(np.arctan2(y, x))


def track_feats(track):
    gpx = gpxpy.parse(open(track, encoding="utf-8"))
    e = [p for tr in gpx.tracks for s in tr.segments for p in s.points if p.time]
    e.sort(key=lambda p: p.time)
    t = np.array([p.time.replace(tzinfo=datetime.timezone.utc).timestamp() for p in e])
    lat = np.array([p.latitude for p in e]); lon = np.array([p.longitude for p in e])
    ele = np.array([p.elevation or 0 for p in e])
    dt = np.diff(t)
    d = hav(lat[:-1], lon[:-1], lat[1:], lon[1:])
    spd = np.clip(np.where(dt > 0, d/np.maximum(dt, 1e-9), 0), 0, 40)
    spd = np.where(dt < 60, spd, 0)
    st = t[:-1]+dt/2
    hd = bearing(lat[:-1], lon[:-1], lat[1:], lon[1:])
    dhd = np.abs(np.diff(hd)); dhd = np.minimum(dhd, 360-dhd)
    turn = np.clip(np.where(dt[1:] > 0, dhd/np.maximum(dt[1:], 1e-9), 0), 0, 90)
    turn = np.where(dt[1:] < 60, turn, 0)
    tt = t[1:-1]
    g = np.arange(t[0], t[-1])
    s1 = np.interp(g, st, spd)
    r1 = np.interp(g, tt, turn)
    r1 = np.where(s1 > 1.5, r1, 0)  # only while moving
    e1 = np.interp(g, t, ele)
    return g, s1, r1, e1


FEATURE = {"wind": "speed", "vibration": "speed", "motion": "speed", "yawrate": "turn"}


def zscore(a):
    a = np.asarray(a, np.float64)
    s = a.std()
    return (a-a.mean())/(s or 1.0)


def main():
    video, gpxf = Path(sys.argv[1]), Path(sys.argv[2])
    meta = json.loads(subprocess.run(["ffprobe","-v","error","-show_format","-of","json",str(video)],capture_output=True,text=True).stdout)
    created = datetime.datetime.fromisoformat(meta["format"]["tags"]["creation_time"].replace("Z","+00:00"))
    sig = dict(np.load(video.with_suffix(".syncsig.npz")))
    g, s1, r1, e1 = track_feats(gpxf)
    g0 = g[0]
    feats = {"speed": s1, "turn": r1}
    votes = {}
    for name, s in sig.items():
        feat = feats[FEATURE.get(name, "speed")]
        s = s.astype(np.float64)
        n = len(s)
        # full-track scan: off ranges so video window slides across whole track
        off_lo = int(g0 - created.timestamp() - n)
        off_hi = int(g[-1] - created.timestamp())
        offs = np.arange(off_lo, off_hi+1)
        scores = np.full(len(offs), np.nan)
        v_all = zscore(s)
        for i, off in enumerate(offs):
            idx = np.arange(n) + created.timestamp() + off - g0
            idx = idx.astype(int)
            ok = (idx >= 0) & (idx < len(feat))
            if ok.sum() < n*0.9:
                continue
            f = feat[idx[ok]]
            fz = zscore(f)
            corr = float((v_all[ok]*fz).mean())
            hi = f > np.percentile(feat, 90); lo = f < np.percentile(feat, 20)
            foc = float((v_all[ok][hi].mean()-v_all[ok][lo].mean())) if hi.sum() >= 20 and lo.sum() >= 20 else 0.0
            scores[i] = corr + 0.5*foc
        order = np.argsort(-np.nan_to_num(scores, nan=-9))
        # top-3 global (>=60s apart) + best within +/-120s of creation
        tops = []
        for o in order:
            if all(abs(o-t) >= 60 for t in tops):
                tops.append(o)
            if len(tops) == 3:
                break
        gtop = ", ".join(f"{int(offs[o]):+d}s:{scores[o]:.2f}" for o in tops)
        near = np.abs(offs) <= 120
        bo = int(offs[np.nanargmax(np.where(near, np.nan_to_num(scores,nan=-9), -9))])
        votes[name] = bo
        print(f"{name:10s} near-0 best {bo:+5d}s({scores[np.where(offs==bo)[0][0]]:.2f})   global: {gtop}")
    vals = list(votes.values())
    if vals:
        print(f">> median offset {int(np.median(vals)):+d}s   votes {votes}")


if __name__ == "__main__":
    main()
