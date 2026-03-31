#!/usr/bin/env python3
"""
Watch /workspace/assets_raw for new/changed 3D files and run Blender normalization.

Designed for Salad/Jupyter Linux environment.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

SUPPORTED_EXTS = {".obj", ".fbx", ".glb", ".gltf"}


def file_sig(path: Path) -> str:
    st = path.stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def snapshot(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            out[str(p.resolve())] = file_sig(p)
    return out


def hash_snapshot(snap: dict[str, str]) -> str:
    h = hashlib.sha256()
    for k in sorted(snap.keys()):
        h.update(k.encode("utf-8", errors="ignore"))
        h.update(b"=")
        h.update(snap[k].encode("utf-8", errors="ignore"))
        h.update(b"\n")
    return h.hexdigest()


def run_normalize(blender_bin: str, runner_py: str) -> int:
    cmd = [blender_bin, "-b", "-P", runner_py]
    print(f"[watch] run: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-root", default="/workspace/assets_raw")
    ap.add_argument("--blender-bin", default="blender")
    ap.add_argument("--runner", default="/workspace/run_norm.py")
    ap.add_argument("--interval", type=int, default=15)
    ap.add_argument("--run-on-start", action="store_true")
    args = ap.parse_args()

    assets_root = Path(args.assets_root).resolve()
    if not assets_root.exists():
        print(f"[watch] creating missing assets root: {assets_root}", flush=True)
        assets_root.mkdir(parents=True, exist_ok=True)

    print(f"[watch] watching: {assets_root}", flush=True)
    print(f"[watch] interval: {args.interval}s", flush=True)
    print(f"[watch] runner: {args.runner}", flush=True)

    prev_hash = hash_snapshot(snapshot(assets_root))

    if args.run_on_start:
        rc = run_normalize(args.blender_bin, args.runner)
        print(f"[watch] initial normalize exit={rc}", flush=True)
        prev_hash = hash_snapshot(snapshot(assets_root))

    while True:
        try:
            time.sleep(max(3, args.interval))
            cur = snapshot(assets_root)
            cur_hash = hash_snapshot(cur)
            if cur_hash == prev_hash:
                continue
            print("[watch] change detected in assets_raw -> normalize start", flush=True)
            rc = run_normalize(args.blender_bin, args.runner)
            print(f"[watch] normalize exit={rc}", flush=True)
            prev_hash = hash_snapshot(snapshot(assets_root))
        except KeyboardInterrupt:
            print("\n[watch] stopped by user", flush=True)
            return 0
        except Exception as e:
            # Keep watcher alive even if one cycle fails.
            print(f"[watch] error: {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
