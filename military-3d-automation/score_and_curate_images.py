#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def dhash(gray: np.ndarray, size: int = 8) -> str:
    small = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    bits = "".join("1" if v else "0" for v in diff.flatten())
    return hex(int(bits, 2))[2:].zfill(size * size // 4)


def classify(path: Path) -> tuple[str, str]:
    s = path.stem.lower().replace("-", "_")
    cat = "vest" if ("plate_carrier" in s or "vest" in s or "carrier" in s) else "helmet" if "helmet" in s else "gun" if "rifle" in s or "gun" in s else "unknown"
    pattern = "multicam" if "multicam" in s or "mtp" in s else "black" if "black" in s or "_blk" in s else "tan" if "tan" in s or "coyote" in s else "unknown"
    return cat, pattern


def score_one(path: Path) -> dict:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError("image decode failed")
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = cv2.Canny(gray, 80, 160)
    edge_density = float(edges.mean() / 255.0)
    noise = float(np.std(gray - cv2.GaussianBlur(gray, (5, 5), 0)))
    res_score = min(w, h) / 1024.0
    # weighted score: detail high, too busy bg penalty
    score = 0.45 * min(sharp / 250.0, 1.5) + 0.35 * min(res_score, 1.5) + 0.2 * (1.0 - min(edge_density / 0.2, 1.0))
    cat, pattern = classify(path)
    return {
        "path": str(path.resolve().as_posix()),
        "width": int(w),
        "height": int(h),
        "sharpness": sharp,
        "edge_density": edge_density,
        "noise": noise,
        "resolution_score": res_score,
        "quality_score": float(score),
        "category_guess": cat,
        "pattern_guess": pattern,
        "dhash": dhash(gray),
    }


def hamming_hex(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", type=Path, required=True, help="downloads 또는 이미지 루트")
    ap.add_argument("--out-json", type=Path, default=Path("curated_dataset.json"))
    ap.add_argument("--min-size", type=int, default=1024)
    ap.add_argument("--top-per-category", type=int, default=60)
    ap.add_argument("--dup-hamming", type=int, default=6)
    args = ap.parse_args()

    files = [p for p in args.input_root.rglob("*") if p.suffix.lower() in EXTS]
    scored: list[dict] = []
    for p in files:
        try:
            m = score_one(p)
        except Exception:
            continue
        if m["width"] < args.min_size or m["height"] < args.min_size:
            continue
        scored.append(m)

    # dedupe by dhash
    scored.sort(key=lambda x: x["quality_score"], reverse=True)
    kept: list[dict] = []
    hashes: list[str] = []
    for item in scored:
        h = item["dhash"]
        if any(hamming_hex(h, hh) <= args.dup_hamming for hh in hashes):
            continue
        kept.append(item)
        hashes.append(h)

    by_cat: dict[str, list[dict]] = {"vest": [], "helmet": [], "gun": [], "unknown": []}
    for k in kept:
        by_cat.setdefault(k["category_guess"], []).append(k)
    final: list[dict] = []
    for cat, arr in by_cat.items():
        arr.sort(key=lambda x: x["quality_score"], reverse=True)
        final.extend(arr[: args.top_per_category])

    out = {
        "version": "1.0",
        "source_root": str(args.input_root.resolve().as_posix()),
        "total_scored": len(scored),
        "total_selected": len(final),
        "samples": final,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved: {args.out_json} selected={len(final)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

