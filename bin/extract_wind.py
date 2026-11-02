#!/usr/bin/env python3
"""Extract per-second voice-band (300-3400Hz) RMS -> .windsig.npz
Usage: extract_wind.py FILE.MP4 ..."""
import sys, subprocess
from pathlib import Path
import numpy as np

for v in sys.argv[1:]:
    v = Path(v)
    out = v.with_suffix('.windsig.npz')
    if out.exists():
        print(v.name, 'cached'); continue
    cmd = ["ffmpeg","-hide_banner","-loglevel","error","-i",str(v),"-vn","-ac","1","-ar","8000",
           "-af","highpass=f=300,lowpass=f=3400","-f","s16le","-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    n = len(a)//8000
    w = np.sqrt((a[:n*8000].reshape(n,8000)**2).mean(axis=1))
    np.savez(out, wind=w)
    print(v.name, n, 's')
