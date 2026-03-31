#!/usr/bin/env python3
"""
Phase B: COLMAP job runner (subprocess). Input directory must contain ./images/ with JPG/PNG.

Exit codes:
  0  Success (mesh.ply or mesh written to output/)
  2  Invalid args / no images
  3  COLMAP failed (see colmap.log)
  4  COLMAP ok but no mesh/point cloud found

Env:
  COLMAP_EXECUTABLE  default: colmap  (Windows: full path to COLMAP.bat or colmap.exe)
  OR_PHOTO_QUALITY   LOW|MEDIUM|HIGH|EXTREME  default MEDIUM
  OR_PHOTO_DATA_TYPE INDIVIDUAL|VIDEO|INTERNET default INDIVIDUAL
  OR_PHOTO_SPARSE_ONLY  1 = feature+mappers only, export sparse PLY via model_converter (no dense mesh)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def _log_line(path: Path, msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as f:
        f.write(line)


def _run_colmap(
    log_file: Path,
    colmap_exe: str,
    args: list[str],
    cwd: Path | None,
    timeout_sec: int,
) -> int:
    _log_line(log_file, "RUN " + " ".join([colmap_exe, *args]))
    try:
        p = subprocess.run(
            [colmap_exe, *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout_sec or None,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as e:
        _log_line(log_file, f"TIMEOUT after {timeout_sec}s")
        with log_file.open("a", encoding="utf-8", errors="replace") as f:
            if e.stdout:
                f.write(e.stdout)
            if e.stderr:
                f.write(e.stderr)
        return 124

    out = (p.stdout or "") + (p.stderr or "")
    with log_file.open("a", encoding="utf-8", errors="replace") as f:
        f.write(out)
        if not out.endswith("\n"):
            f.write("\n")
    _log_line(log_file, f"EXIT {p.returncode}")
    return int(p.returncode)


def _count_images(images_dir: Path) -> int:
    n = 0
    if not images_dir.is_dir():
        return 0
    for p in images_dir.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            n += 1
    return n


def _find_mesh_ply(job_dir: Path) -> Path | None:
    """Prefer Poisson / Delaunay mesh; else fused point cloud."""
    dense = job_dir / "dense"
    candidates: list[tuple[int, Path]] = []
    if dense.is_dir():
        for name in ("meshed-poisson.ply", "meshed-delaunay.ply", "fused.ply"):
            for p in dense.rglob(name):
                try:
                    candidates.append((p.stat().st_size, p))
                except OSError:
                    continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    # Prefer mesh over fused by name
    for pref in ("meshed-poisson", "meshed-delaunay"):
        for sz, p in candidates:
            if pref in p.name.lower():
                return p
    return candidates[0][1]


def _export_sparse_ply(
    job_dir: Path,
    colmap_exe: str,
    log_file: Path,
    timeout_sec: int,
) -> int:
    sparse0 = job_dir / "sparse" / "0"
    if not sparse0.is_dir():
        return 1
    out_ply = job_dir / "output" / "sparse_points.ply"
    out_ply.parent.mkdir(parents=True, exist_ok=True)
    return _run_colmap(
        log_file,
        colmap_exe,
        [
            "model_converter",
            "--input_path",
            str(sparse0),
            "--output_path",
            str(out_ply),
            "--output_type",
            "PLY",
        ],
        cwd=None,
        timeout_sec=timeout_sec,
    )


def _maybe_glb(ply_path: Path, out_glb: Path) -> bool:
    try:
        import trimesh
    except ImportError:
        return False
    try:
        loaded = trimesh.load(str(ply_path))
        if isinstance(loaded, trimesh.Scene):
            geom = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not geom:
                return False
            mesh = trimesh.util.concatenate(geom)
        elif isinstance(loaded, trimesh.Trimesh):
            mesh = loaded
        else:
            return False
        data = mesh.export(file_type="glb")
        if not isinstance(data, bytes):
            return False
        out_glb.parent.mkdir(parents=True, exist_ok=True)
        out_glb.write_bytes(data)
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run COLMAP on job_dir/images → output/mesh.ply")
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument(
        "--colmap-exe",
        default=os.environ.get("COLMAP_EXECUTABLE", "colmap"),
        help="COLMAP executable (Windows: path to COLMAP.bat)",
    )
    parser.add_argument("--timeout-sec", type=int, default=0, help="0 = no limit")
    parser.add_argument(
        "--export-glb",
        action="store_true",
        help="Also write output/mesh.glb if trimesh is installed",
    )
    parser.add_argument(
        "--clean-on-success",
        action="store_true",
        help="Remove database.db, sparse/, dense/ after success (keep images/ output/)",
    )
    args = parser.parse_args()

    job_dir: Path = args.job_dir.resolve()
    images_dir = job_dir / "images"
    log_file = job_dir / "colmap.log"
    output_dir = job_dir / "output"

    if not images_dir.is_dir():
        _log_line(log_file, f"ERROR: missing images dir {images_dir}")
        return 2
    n_img = _count_images(images_dir)
    if n_img < 3:
        _log_line(log_file, f"ERROR: need at least 3 images, found {n_img}")
        return 2

    sparse_only = (os.environ.get("OR_PHOTO_SPARSE_ONLY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    quality = (os.environ.get("OR_PHOTO_QUALITY") or "MEDIUM").strip().upper()
    if quality not in ("LOW", "MEDIUM", "HIGH", "EXTREME"):
        quality = "MEDIUM"
    data_type = (os.environ.get("OR_PHOTO_DATA_TYPE") or "INDIVIDUAL").strip().upper()
    if data_type not in ("INDIVIDUAL", "VIDEO", "INTERNET"):
        data_type = "INDIVIDUAL"

    timeout = int(args.timeout_sec or int(os.environ.get("OR_PHOTO_TIMEOUT_SEC") or "0"))

    if sparse_only:
        # Manual sparse pipeline (no dense)
        db = job_dir / "database.db"
        for cmd_args in (
            [
                "feature_extractor",
                "--database_path",
                str(db),
                "--image_path",
                str(images_dir),
            ],
            ["exhaustive_matcher", "--database_path", str(db)],
        ):
            rc = _run_colmap(log_file, args.colmap_exe, cmd_args, cwd=None, timeout_sec=timeout)
            if rc != 0:
                return 3
        sparse_root = job_dir / "sparse"
        sparse_root.mkdir(parents=True, exist_ok=True)
        rc = _run_colmap(
            log_file,
            args.colmap_exe,
            [
                "mapper",
                "--database_path",
                str(db),
                "--image_path",
                str(images_dir),
                "--output_path",
                str(sparse_root),
            ],
            cwd=None,
            timeout_sec=timeout,
        )
        if rc != 0:
            return 3
        rc = _export_sparse_ply(job_dir, args.colmap_exe, log_file, timeout)
        if rc != 0:
            return 3
        _log_line(log_file, "Sparse-only: output/sparse_points.ply (point cloud, not a surface mesh)")
        if args.export_glb:
            ply = output_dir / "sparse_points.ply"
            if ply.is_file() and not _maybe_glb(ply, output_dir / "mesh.glb"):
                _log_line(log_file, "NOTE: trimesh missing or GLB export skipped for point cloud")
        if args.clean_on_success:
            for name in ("database.db", "sparse"):
                p = job_dir / name
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
        return 0

    # Full automatic reconstruction (sparse + dense + mesher per COLMAP build)
    rc = _run_colmap(
        log_file,
        args.colmap_exe,
        [
            "automatic_reconstructor",
            "--workspace_path",
            str(job_dir),
            "--image_path",
            str(images_dir),
            "--quality",
            quality,
            "--data_type",
            data_type,
        ],
        cwd=None,
        timeout_sec=timeout,
    )
    if rc != 0:
        return 3

    best = _find_mesh_ply(job_dir)
    if best is None:
        _log_line(log_file, "ERROR: no fused/meshed PLY under dense/")
        return 4

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "mesh.ply"
    shutil.copy2(best, dest)
    _log_line(log_file, f"COPIED {best} -> {dest}")

    if args.export_glb and _maybe_glb(dest, output_dir / "mesh.glb"):
        _log_line(log_file, f"Wrote {output_dir / 'mesh.glb'}")
    elif args.export_glb:
        _log_line(log_file, "NOTE: pip install trimesh for mesh.glb")

    if args.clean_on_success:
        for name in ("database.db", "sparse", "dense"):
            p = job_dir / name
            if p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
