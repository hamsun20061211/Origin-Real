#!/usr/bin/env python3
"""
dataset.json 후처리(Windows Python):
 - OpenCV로 모든 렌더 이미지 선명화(위장 패턴/버클 엣지 보존)
 - 파일명/태그 규칙 기반 Auto-Tagging 보강 (Helmet/Vest/Gun + Multicam/Black/Tan 등)
 - dataset.json 업데이트 저장

사용:
  pip install opencv-python
  python postprocess_dataset_opencv.py --dataset "D:/dataset/out_run1/<model>/dataset.json" --inplace

또는 폴더(재귀):
  python postprocess_dataset_opencv.py --root "D:/dataset/out_run1" --inplace
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load_rules(path: Path | None) -> dict:
    if path and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    here = Path(__file__).resolve().parent / "equipment_tag_rules.json"
    if here.is_file():
        return json.loads(here.read_text(encoding="utf-8"))
    return {"equipment_rules": [], "camouflage_rules": [], "colorway_rules": [], "material_hints": []}


def apply_rule_list(lower: str, rules: dict, key: str, tags: set[str]) -> None:
    for rule in rules.get(key, []):
        for pat in rule.get("match", []):
            if pat.lower() in lower:
                for t in rule.get("tags", []):
                    tags.add(t)


def infer_equipment_kind(tags: set[str]) -> str | None:
    # 요구: Helmet, Vest, Gun
    if "helmet" in tags:
        return "Helmet"
    if "plate_carrier" in tags or "body_armor" in tags:
        return "Vest"
    if "weapon" in tags or "firearm" in tags:
        return "Gun"
    return None


def infer_pattern_name(tags: set[str]) -> str | None:
    if "multicam" in tags:
        return "Multicam"
    if "digital_pattern" in tags:
        return "Digital"
    if "woodland_pattern" in tags:
        return "Woodland"
    if "camouflage" in tags:
        return "Camo"
    return None


def infer_colorway(tags: set[str]) -> str | None:
    if "black" in tags:
        return "Black"
    if "tan" in tags:
        return "Tan"
    return None


def sharpen_opencv(path: Path, amount: float, radius: float) -> bool:
    """
    Unsharp mask (OpenCV):
      sharpened = (1 + amount) * img - amount * gaussian_blur(img, sigma)
    """
    import cv2
    import numpy as np

    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        return False

    # Preserve alpha if present
    if img.ndim == 3 and img.shape[2] == 4:
        bgr = img[:, :, :3]
        a = img[:, :, 3:4]
    else:
        bgr = img
        a = None

    sigma = max(0.1, float(radius))
    blur = cv2.GaussianBlur(bgr, ksize=(0, 0), sigmaX=sigma, sigmaY=sigma)
    sharp = cv2.addWeighted(bgr, 1.0 + float(amount), blur, -float(amount), 0)
    sharp = np.clip(sharp, 0, 255).astype(bgr.dtype)

    out = sharp if a is None else np.concatenate([sharp, a], axis=2)
    ok, buf = cv2.imencode(".png", out)
    if not ok:
        return False
    path.write_bytes(buf.tobytes())
    return True


def update_one_dataset(dataset_path: Path, rules: dict, inplace: bool, amount: float, radius: float) -> int:
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    samples = data.get("samples", [])
    if not isinstance(samples, list):
        return 0

    changed = 0
    for s in samples:
        # Auto-tagging based on id + source_file name
        seed = " ".join(
            str(x)
            for x in (
                s.get("id", ""),
                s.get("source_file", ""),
            )
        )
        lower = seed.lower().replace("-", "_")
        tags = set(s.get("tags", []) or [])
        apply_rule_list(lower, rules, "equipment_rules", tags)
        apply_rule_list(lower, rules, "camouflage_rules", tags)
        apply_rule_list(lower, rules, "colorway_rules", tags)
        s["tags"] = sorted(tags)

        kind = infer_equipment_kind(tags)
        pattern = infer_pattern_name(tags)
        color = infer_colorway(tags)
        if kind:
            s["equipment_kind"] = kind
        if pattern:
            s["camouflage_name"] = pattern
        if color:
            s["colorway_name"] = color

        # Sharpen every render image
        renders = s.get("renders", {}) or {}
        for _, p in list(renders.items()):
            fp = Path(p)
            if not fp.is_absolute():
                fp = (dataset_path.parent / fp).resolve()
            if fp.is_file():
                ok = sharpen_opencv(fp, amount=amount, radius=radius)
                if ok:
                    changed += 1

    if inplace:
        dataset_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        out = dataset_path.with_suffix(".post.json")
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return changed


def find_datasets(root: Path) -> list[Path]:
    return sorted(root.rglob("dataset.json"))


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dataset", type=Path, help="단일 dataset.json")
    g.add_argument("--root", type=Path, help="root 아래 dataset.json 재귀 탐색")
    p.add_argument("--tag-rules", type=Path, default=None)
    p.add_argument("--inplace", action="store_true")
    p.add_argument("--amount", type=float, default=0.85, help="샤프닝 강도 (0.5~1.2 권장)")
    p.add_argument("--radius", type=float, default=1.05, help="가우시안 sigma (0.8~1.6 권장)")
    args = p.parse_args()

    try:
        import cv2  # noqa: F401
    except Exception as e:
        print("OpenCV 필요: pip install opencv-python", e, file=sys.stderr)
        return 2

    rules = load_rules(args.tag_rules)
    targets = [args.dataset] if args.dataset else find_datasets(args.root)
    total = 0
    for ds in targets:
        if not ds.is_file():
            continue
        total += update_one_dataset(ds, rules, inplace=args.inplace, amount=args.amount, radius=args.radius)
    print("샤프닝 적용 파일 수:", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

