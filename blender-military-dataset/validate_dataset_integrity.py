#!/usr/bin/env python3
"""
데이터 무결성 최종 검증:
 - dataset.json 안의 renders/pbr_maps/source_file 경로가 실제 파일과 일치하는지 검사
 - 하나라도 누락/깨짐이면 WARNING 출력 + 비정상 종료 코드

사용:
  python validate_dataset_integrity.py --dataset "D:/dataset/out_run1/<model>/dataset.json"
  python validate_dataset_integrity.py --root "D:/dataset/out_run1"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def resolve_path(base_dir: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (base_dir / path).resolve()


def check_dataset(ds: Path) -> tuple[int, int]:
    data = json.loads(ds.read_text(encoding="utf-8"))
    base = ds.parent
    warn = 0
    ok = 0

    samples = data.get("samples", [])
    if not isinstance(samples, list):
        print(f"[WARN] samples 형식 오류: {ds}", file=sys.stderr)
        return 1, 0

    for s in samples:
        sid = s.get("id", "<no-id>")
        # model file
        sf = s.get("source_file")
        if sf:
            p = resolve_path(base, sf)
            if not p.is_file():
                warn += 1
                print(f"[WARN] source_file missing: {sid} -> {p}", file=sys.stderr)
            else:
                ok += 1

        # renders
        renders = s.get("renders", {}) or {}
        if isinstance(renders, dict):
            for k, v in renders.items():
                p = resolve_path(base, str(v))
                if not p.is_file():
                    warn += 1
                    print(f"[WARN] render missing: {sid} {k} -> {p}", file=sys.stderr)
                else:
                    ok += 1
        else:
            warn += 1
            print(f"[WARN] renders not dict: {sid}", file=sys.stderr)

        # pbr maps
        pbr = s.get("pbr_maps", {}) or {}
        if isinstance(pbr, dict):
            for k, v in pbr.items():
                p = resolve_path(base, str(v))
                if not p.is_file():
                    warn += 1
                    print(f"[WARN] pbr missing: {sid} {k} -> {p}", file=sys.stderr)
                else:
                    ok += 1
        else:
            warn += 1
            print(f"[WARN] pbr_maps not dict: {sid}", file=sys.stderr)

    return warn, ok


def find_datasets(root: Path) -> list[Path]:
    return sorted(root.rglob("dataset.json"))


def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dataset", type=Path)
    g.add_argument("--root", type=Path)
    args = p.parse_args()

    targets = [args.dataset] if args.dataset else find_datasets(args.root)
    total_warn = 0
    total_ok = 0
    for ds in targets:
        if not ds.is_file():
            continue
        w, o = check_dataset(ds)
        total_warn += w
        total_ok += o
    print("검사 OK:", total_ok, "WARN:", total_warn)
    return 1 if total_warn else 0


if __name__ == "__main__":
    raise SystemExit(main())

