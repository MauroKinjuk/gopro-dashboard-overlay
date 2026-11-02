#!/usr/bin/env python3
"""
Estimate the time offset between a GoPro video (without GPS) and a GPX/FIT
track by cross-correlating several independent signals with features from
the track:

  - wind noise RMS (audio)            vs  speed
  - accel vibration (gpmd ACCL)       vs  speed
  - video motion (frame diff)         vs  speed
  - gyro rotation rate (gpmd GYRO)    vs  heading-change rate

Extracted signals are cached to <video>.syncsig.npz so re-runs are instant.

Usage:
    python gopro-sync-offset.py <video.mp4> <track.gpx> [--around "YYYY-MM-DD HH:MM:SS" --window 3600]
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.signal import correlate

# Use local source code instead of installed package
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir.parent))

from gopro_overlay import gpx as gpx_module
from gopro_overlay.units import units


def cache_path(video: Path):
    return video.with_suffix(".syncsig.npz")


def video_info(video: Path):
    meta = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(video)],
        capture_output=True, text=True, check=True
    ).stdout)
    duration = float(meta["format"]["duration"])
    created = meta["format"].get("tags", {}).get("creation_time")
    created_dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None
    stream = next(s for s in meta["streams"] if s["codec_type"] == "video")
    gpmd_idx = next(
        (s["index"] for s in meta["streams"] if s.get("codec_tag_string") == "gpmd"),
        None
    )
    return duration, created_dt, int(stream["width"]), int(stream["height"]), gpmd_idx


# ---------- signal extraction ----------

def video_motion(video: Path, vw: int, vh: int, fps: int, width: int):
    height = max(2, int(round(vh * width / vw / 2) * 2))
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-hwaccel", "auto",
        "-i", str(video),
        "-vf", f"scale={width}:{height},fps={fps}",
        "-f", "rawvideo", "-pix_fmt", "gray", "-"
    ]
    frame_size = width * height
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    prev = None
    diffs = []
    while True:
        data = proc.stdout.read(frame_size)
        if len(data) < frame_size:
            break
        frame = np.frombuffer(data, dtype=np.uint8)
        if prev is not None:
            diffs.append(np.abs(frame.astype(np.int16) - prev).mean())
        prev = frame
    proc.stdout.close()
    proc.wait()

    if not diffs:
        raise RuntimeError("No frames decoded")
    motion = np.array(diffs)
    n_seconds = len(motion) // fps
    return motion[: n_seconds * fps].reshape(n_seconds, fps).mean(axis=1)


def video_wind(video: Path):
    """Wind-noise proxy: per-second RMS of 300-3400Hz audio."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(video), "-vn", "-ac", "1", "-ar", "8000",
        "-af", "highpass=f=300,lowpass=f=3400",
        "-f", "s16le", "-"
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    n = len(audio) // 8000
    return np.sqrt((audio[: n * 8000].reshape(n, 8000) ** 2).mean(axis=1))


def gpmf_items(raw: bytes, fourcc: bytes):
    """Iterate GPMF items: yields int16 arrays of shape (n, size/2)."""
    idx = 0
    while True:
        i = raw.find(fourcc, idx)
        if i < 0 or i + 8 > len(raw):
            return
        typ = raw[i + 4:i + 5]
        size = raw[i + 5]
        repeat = int.from_bytes(raw[i + 6:i + 8], "big")
        n = size * repeat
        payload = raw[i + 8:i + 8 + n]
        idx = i + 8 + ((n + 3) // 4) * 4
        if typ == b"s" and size % 2 == 0 and len(payload) == n:
            yield np.frombuffer(payload, dtype=">i2").reshape(-1, size // 2)


def gpmd_raw(video: Path, gpmd_idx: int):
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-codec", "copy", "-map", f"0:{gpmd_idx}", "-f", "rawvideo", "-"
    ]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def video_imu_signal(video: Path, gpmd_idx: int, fourcc: bytes):
    """Per-second mean magnitude of a 3-axis int16 GPMF stream (~1 item/sec)."""
    raw = gpmd_raw(video, gpmd_idx)
    out = []
    for arr in gpmf_items(raw, fourcc):
        mag = np.sqrt((arr.astype(np.float64) ** 2).sum(axis=1))
        out.append(mag.mean())
    return np.array(out)


# ---------- track features ----------

def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return np.degrees(np.arctan2(y, x))


def track_features(track: Path):
    """Return (start_dt_utc, {speed: array, turnrate: array}) on 1Hz grid."""
    ts = gpx_module.load_timeseries(track, units)
    entries = ts.items()
    times = np.array([e.dt.timestamp() for e in entries])
    lat = np.array([e.point.lat for e in entries])
    lon = np.array([e.point.lon for e in entries])
    dt = np.diff(times)

    if all(e.speed is not None for e in entries):
        speeds = np.array([e.speed.magnitude for e in entries])
        speed_t = times
    else:
        dist = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
        speeds = np.where(dt > 0, dist / np.maximum(dt, 1e-9), 0.0)
        speeds = np.clip(speeds, 0, 40)
        speed_t = times[:-1] + np.maximum(dt, 1e-9) / 2

    head = bearing_deg(lat[:-1], lon[:-1], lat[1:], lon[1:])
    dhead = np.abs(np.diff(head))
    dhead = np.minimum(dhead, 360 - dhead)
    turn = np.where(dt[1:] > 0, dhead / np.maximum(dt[1:], 1e-9), 0.0)
    turn = np.clip(turn, 0, 90)
    turn_t = times[1:-1]

    t0 = float(int(times[0] // 1))
    grid = np.arange(t0, float(int(times[-1] // 1)))
    speed_1hz = np.interp(grid, speed_t, speeds)
    turn_1hz = np.interp(grid, turn_t, turn)
    # only trust turn rate while actually moving
    turn_1hz = np.where(speed_1hz > 1.5, turn_1hz, 0.0)

    start_dt = datetime.datetime.fromtimestamp(t0, tz=datetime.timezone.utc)
    return start_dt, {"speed": speed_1hz, "turnrate": turn_1hz}


# ---------- correlation ----------

def zscore(a):
    a = np.asarray(a, dtype=np.float64)
    s = a.std()
    return (a - a.mean()) / (s if s > 0 else 1.0)


def valid_corr(track_z, signal):
    m = zscore(signal)
    return correlate(track_z, m, mode="valid") / len(m)


SIGNAL_FEATURE = {
    "wind": "speed",
    "vibration": "speed",
    "motion": "speed",
    "yawrate": "turnrate",
}


def extract_signals(video, vw, vh, gpmd_idx, args):
    signals = {}
    cached = cache_path(video)
    if cached.exists() and not args.no_cache:
        print(f"Using cached signals: {cached.name}")
        return {k: v for k, v in np.load(cached).items()}

    if not args.no_video:
        print("Extracting motion signal (video decode, slow)...")
        signals["motion"] = video_motion(video, vw, vh, args.fps, args.width)
        print(f"  motion: {len(signals['motion'])}s")
    if not args.no_audio:
        print("Extracting wind signal...")
        try:
            signals["wind"] = video_wind(video)
            print(f"  wind: {len(signals['wind'])}s")
        except Exception as ex:
            print(f"  wind unavailable: {ex}")
    if not args.no_imu:
        print("Extracting IMU signals...")
        try:
            signals["vibration"] = video_imu_signal(video, gpmd_idx, b"ACCL")
            print(f"  vibration: {len(signals['vibration'])}s")
        except Exception as ex:
            print(f"  vibration unavailable: {ex}")
        try:
            signals["yawrate"] = video_imu_signal(video, gpmd_idx, b"GYRO")
            print(f"  yawrate: {len(signals['yawrate'])}s")
        except Exception as ex:
            print(f"  yawrate unavailable: {ex}")

    if signals:
        np.savez(cached, **signals)
        print(f"Signals cached to {cached.name}")
    return signals


def main():
    parser = argparse.ArgumentParser(description="Estimate GPX<->video time offset by correlation")
    parser.add_argument("video", type=Path)
    parser.add_argument("gpx", type=Path)
    parser.add_argument("--fps", type=int, default=4)
    parser.add_argument("--width", type=int, default=160)
    parser.add_argument("--no-imu", action="store_true")
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--around", type=str, default=None,
                        help="Only search GPX window around this UTC datetime 'YYYY-MM-DD HH:MM:SS'")
    parser.add_argument("--window", type=int, default=3600)
    args = parser.parse_args()

    duration, created_dt, vw, vh, gpmd_idx = video_info(args.video)
    print(f"Video: {args.video.name}  ({duration:.1f}s, {vw}x{vh})")
    if created_dt:
        print(f"Video creation_time (camera clock): {created_dt:%Y-%m-%d %H:%M:%S} UTC")

    signals = extract_signals(args.video, vw, vh, gpmd_idx, args)
    if not signals:
        print("ERROR: no signals extracted")
        sys.exit(1)

    print("Loading track...")
    track_start, feats = track_features(args.gpx)
    print(f"Track: {track_start:%Y-%m-%d %H:%M:%S} UTC +{len(feats['speed'])}s")

    corrs = {}
    for name, sig in signals.items():
        feature = feats[SIGNAL_FEATURE[name]]
        if len(sig) > len(feature):
            print(f"ERROR: {name} signal longer than the track")
            sys.exit(1)
        corrs[name] = valid_corr(zscore(feature), sig)

    n_common = min(len(c) for c in corrs.values())
    combined = sum(zscore(c[:n_common]) for c in corrs.values())
    starts = np.arange(n_common)

    if args.around:
        center = datetime.datetime.fromisoformat(args.around).replace(tzinfo=datetime.timezone.utc)
        lo = (center.timestamp() - args.window) - track_start.timestamp()
        hi = (center.timestamp() + args.window) - track_start.timestamp()
        mask = (starts >= lo) & (starts <= hi)
        if not mask.any():
            print("ERROR: --around window does not overlap the track")
            sys.exit(1)
        combined = np.where(mask, combined, -np.inf)

    order = np.argsort(combined)[::-1]
    # top candidates separated by >=60s
    top = []
    for i in order:
        if all(abs(i - j) >= 60 for j in top):
            top.append(i)
        if len(top) == 3:
            break

    best = int(order[0])
    est_start = track_start + datetime.timedelta(seconds=int(best))

    print()
    for name, c in corrs.items():
        own = int(np.argmax(c))
        at_best = c[best] if best < len(c) else float("nan")
        print(f"  {name:10s} own argmax: {track_start + datetime.timedelta(seconds=own):%H:%M:%S}"
              f" (r={c[own]:.3f})   corr at best: {at_best:.3f}")

    print()
    print("Top candidates (GPX-time video start):")
    for i in top:
        print(f"  {track_start + datetime.timedelta(seconds=int(i)):%Y-%m-%d %H:%M:%S}  score={combined[i]:.2f}")

    if created_dt:
        delta = (est_start - created_dt).total_seconds()
        print(f"\nCamera clock bias: {delta:+.1f}s (est_start - creation_time)")

    print()
    print("Command to render with this sync:")
    print(f'  .\\gopro-shorts-video.bat "{args.gpx}" "{args.video}" "{args.video.stem}-shorts.mov" "{est_start:%Y-%m-%d %H:%M:%S}"')


if __name__ == "__main__":
    main()
