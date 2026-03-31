#!/usr/bin/env python3
"""
참조 이미지(실사·수집 이미지) 전처리: 위장 패턴 보존 샤프닝 + dataset.json 태그.
Blender 없이 실행 가능 (시스템 Python 3.10+).

  python preprocess_reference_images.py --input-dir ./refs --output-dir ./out_refs \\
    --dataset ./dataset_refs.json --sharpen 0.35

--merge 기존 dataset.json 이 있으면 samples 배열에 append.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


def load_rules(path: Path | None) -> dict:
    if path and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    here = Path(__file__).resolve().parent / "equipment_tag_rules.json"
    if here.is_file():
        return json.loads(here.read_text(encoding="utf-8"))
    return {"equipment_rules": [], "camouflage_rules": [], "material_hints": []}


def infer_tags(stem: str, rules: dict) -> tuple[str | None, list[str], list[str]]:
    lower = stem.lower().replace("-", "_")
    tags: set[str] = set()
    pbr_hints: set[str] = set()
    equip_type: str | None = None

    def apply_rule_list(key: str):
        nonlocal equip_type
        for rule in rules.get(key, []):
            for pat in rule.get("match", []):
                if pat.lower() in lower:
                    for t in rule.get("tags", []):
                        tags.add(t)
                    if key == "equipment_rules" and not equip_type:
                        equip_type = rule["tags"][0] if rule.get("tags") else None

    apply_rule_list("equipment_rules")
    apply_rule_list("camouflage_rules")
    apply_rule_list("colorway_rules")
    for rule in rules.get("material_hints", []):
        for pat in rule.get("match", []):
            if pat.lower() in lower:
                for t in rule.get("tags", []):
                    tags.add(t)
                note = rule.get("pbr_notes")
                if note:
                    pbr_hints.add(note)
    tags.add("military_equipment")
    tags.add("reference_photo")
    return equip_type, sorted(tags), sorted(pbr_hints)


def sharpen_rgba(arr, strength: float):
    import numpy as np

    if strength <= 1e-6:
        return arr
    p = np.pad(arr.astype(np.float32, copy=False), ((1, 1), (1, 1), (0, 0)), mode="edge")
    blur = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) * 0.25
    return np.clip(arr + strength * (arr - blur), 0.0, 1.0)


def process_image(src: Path, dst: Path, sharpen: float) -> None:
    from PIL import Image
    import numpy as np

    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGBA")
    arr = np.asarray(im, dtype=np.float32) / 255.0
    arr = sharpen_rgba(arr, sharpen)
    out = (np.clip(arr, 0, 1) * 255.0).astype("uint8")
    Image.fromarray(out, "RGBA").save(dst, compress_level=3)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--dataset", type=Path, default=Path("dataset_reference_images.json"))
    p.add_argument("--tag-rules", type=Path, default=None)
    p.add_argument("--sharpen", type=float, default=0.38)
    p.add_argument("--merge", action="store_true")
    args = p.parse_args()

    exts = (".png", ".jpg", ".jpeg", ".webp")
    rules = load_rules(args.tag_rules)
    samples: list[dict] = []

    for src in sorted(args.input_dir.iterdir()):
        if not src.suffix.lower() in exts:
            continue
        rel = src.stem
        dst = args.output_dir / f"{rel}_sharp{src.suffix}"
        try:
            process_image(src, dst, args.sharpen)
        except ImportError as e:
            print("필요: pip install pillow numpy", e, file=sys.stderr)
            return 2
        eq, tags, hints = infer_tags(rel, rules)
        samples.append(
            {
                "id": f"{rel}_{uuid.uuid4().hex[:8]}",
                "source_file": str(src.resolve().as_posix()),
                "processed_image": str(dst.resolve().as_posix()),
                "equipment_type_guess": eq,
                "tags": tags,
                "pbr_material_hints": hints,
                "kind": "reference_image",
                "sharpen": args.sharpen,
            }
        )

    manifest: dict = {"version": "1.0", "samples": samples}
    if args.merge and args.dataset.is_file():
        old = json.loads(args.dataset.read_text(encoding="utf-8"))
        manifest["samples"] = old.get("samples", []) + samples

    args.dataset.parent.mkdir(parents=True, exist_ok=True)
    args.dataset.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print("저장:", args.dataset, "항목:", len(samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
