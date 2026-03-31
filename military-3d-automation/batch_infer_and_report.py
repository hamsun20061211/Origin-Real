#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import trimesh


def run_infer(python_exe: str, inference_py: Path, image: Path, out_dir: Path, category: str, symmetry: bool, diffusion_steps: int) -> Path | None:
    out_cat = out_dir / category
    out_cat.mkdir(parents=True, exist_ok=True)
    cmd = [
        python_exe,
        str(inference_py),
        str(image),
        "--out",
        str(out_cat),
        "--preset",
        "tactical_hi",
        "--diffusion-steps",
        str(diffusion_steps),
        "--no-video",
    ]
    if symmetry:
        cmd += ["--symmetry", "--symmetry-axis", "x"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        return None
    glbs = sorted(out_cat.rglob("*.glb"), key=lambda p: p.stat().st_mtime, reverse=True)
    return glbs[0] if glbs else None


def glb_quality(glb: Path) -> dict:
    try:
        m = trimesh.load(str(glb), force="mesh", process=False)
    except Exception as e:
        return {"path": str(glb), "ok": False, "error": str(e)}
    v = int(len(m.vertices)) if hasattr(m, "vertices") else 0
    f = int(len(m.faces)) if hasattr(m, "faces") else 0
    watertight = bool(getattr(m, "is_watertight", False))
    area = float(getattr(m, "area", 0.0))
    return {
        "path": str(glb.resolve().as_posix()),
        "ok": True,
        "vertices": v,
        "faces": f,
        "watertight": watertight,
        "area": area,
        "size_mb": round(glb.stat().st_size / (1024 * 1024), 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated-json", type=Path, required=True)
    ap.add_argument("--instantmesh-python", required=True, help="InstantMesh .venv python.exe")
    ap.add_argument("--inference-py", type=Path, default=Path(r"c:\Users\4080\Downloads\Origin Real\instantmesh-setup\inference.py"))
    ap.add_argument("--out-dir", type=Path, default=Path(r"c:\Users\4080\Downloads\Origin Real\generated_glb"))
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--diffusion-steps", type=int, default=50)
    args = ap.parse_args()

    data = json.loads(args.curated_json.read_text(encoding="utf-8"))
    samples = data.get("samples", [])[: args.limit]
    results = []
    for s in samples:
        img = Path(s["path"])
        cat = s.get("category_guess", "unknown")
        sym = cat in ("helmet", "gun")
        glb = run_infer(
            args.instantmesh_python,
            args.inference_py,
            img,
            args.out_dir,
            cat,
            symmetry=sym,
            diffusion_steps=args.diffusion_steps,
        )
        row = {
            "input_image": str(img.resolve().as_posix()),
            "category": cat,
            "quality_score": s.get("quality_score"),
            "generated_glb": str(glb.resolve().as_posix()) if glb else None,
        }
        if glb:
            row["glb_quality"] = glb_quality(glb)
        results.append(row)

    report = {
        "version": "1.0",
        "total_inputs": len(samples),
        "total_generated": sum(1 for r in results if r["generated_glb"]),
        "items": results,
    }
    report_path = args.out_dir / "quality_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

