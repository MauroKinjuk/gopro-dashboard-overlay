#!/usr/bin/env python3
"""Per-second IMU stats from gpmd stream -> save .imusig.npz next to video.
Usage: find_crash.py FILE.MP4"""
import sys, json, subprocess
from pathlib import Path
import numpy as np

def gpmf_items(raw, fourcc):
    idx = 0
    while True:
        i = raw.find(fourcc, idx)
        if i < 0 or i + 8 > len(raw):
            return
        typ = raw[i+4:i+5]; size = raw[i+5]; repeat = int.from_bytes(raw[i+6:i+8], "big")
        n = size*repeat
        payload = raw[i+8:i+8+n]
        idx = i+8+((n+3)//4)*4
        if typ == b"s" and size % 2 == 0 and len(payload) == n:
            yield np.frombuffer(payload, dtype=">i2").reshape(-1, size//2)
        elif typ == b"f" and size % 4 == 0 and len(payload) == n:
            yield np.frombuffer(payload, dtype=">f4").reshape(-1, size//4)

def main():
    video = Path(sys.argv[1])
    meta = json.loads(subprocess.run(["ffprobe","-v","error","-show_streams","-of","json",str(video)],capture_output=True,text=True).stdout)
    gpmd_idx = next(s["index"] for s in meta["streams"] if s.get("codec_tag_string") == "gpmd")
    raw = subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(video),
                          "-codec","copy","-map",f"0:{gpmd_idx}","-f","rawvideo","-"],
                         capture_output=True, check=True).stdout
    accl_max, accl_std, gyro_max = [], [], []
    for arr in gpmf_items(raw, b"ACCL"):
        mag = np.sqrt((arr.astype(np.float64)**2).sum(axis=1))
        accl_max.append(mag.max()); accl_std.append(mag.std())
    for arr in gpmf_items(raw, b"GYRO"):
        mag = np.sqrt((arr.astype(np.float64)**2).sum(axis=1))
        gyro_max.append(mag.max())
    cori = []
    for arr in gpmf_items(raw, b"CORI"):
        # quaternion per sample: take first sample of each packet
        cori.append(arr[0])
    cori = np.array(cori) if cori else np.zeros((0,4))
    # angle change between consecutive orientation samples
    dori = np.zeros(len(cori))
    if len(cori) > 1:
        q = cori/np.linalg.norm(cori,axis=1,keepdims=True)
        dot = np.clip(np.abs((q[1:]*q[:-1]).sum(axis=1)),0,1)
        dori[1:] = 2*np.degrees(np.arccos(dot))
    np.savez(video.with_suffix(".imusig.npz"),
             accl_max=np.array(accl_max), accl_std=np.array(accl_std),
             gyro_max=np.array(gyro_max), dori=dori)
    print(video.name, 'packets:', len(accl_max), 'accl_max top:',
          sorted(np.array(accl_max).round(0).astype(int), reverse=True)[:8])

if __name__ == "__main__":
    main()
