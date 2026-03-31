"""
Origin Real — Photogrammetry job API (COLMAP). Separate from TripoSR (port 8001).

Run: uvicorn main:app --host 0.0.0.0 --port 8002
Or:  npm run photogrammetry

Requires COLMAP on PATH or COLMAP_EXECUTABLE.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(level)s] %(name)s: %(message)s",
)
logger = logging.getLogger("origin_real.photogrammetry")

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent

# -----------------------------------------------------------------------------
# Merge repo .env / .env.local (same idea as triposr-server)
# -----------------------------------------------------------------------------
def _merge_repo_env_files_into_environ() -> None:
    merged: dict[str, str] = {}
    for name in (".env", ".env.local"):
        p = _REPO_ROOT / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if text and ord(text[0]) == 0xFEFF:
            text = text[1:]
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                continue
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            merged[key] = val
    for k, v in merged.items():
        os.environ.setdefault(k, v)


_merge_repo_env_files_into_environ()

DATA_DIR = Path(os.environ.get("PHOTOGRAMMETRY_DATA_DIR", str(_THIS_DIR / "data"))).resolve()
JOBS_DIR = DATA_DIR / "jobs"
MAX_ZIP_BYTES = int(os.environ.get("PHOTOGRAMMETRY_MAX_ZIP_MB", "512")) * 1024 * 1024
MAX_IMAGES = int(os.environ.get("PHOTOGRAMMETRY_MAX_IMAGES", "200"))
COLMAP_EXPORT_GLB = (os.environ.get("PHOTOGRAMMETRY_EXPORT_GLB") or "1").lower() in (
    "1",
    "true",
    "yes",
)
COLMAP_CLEAN = (os.environ.get("PHOTOGRAMMETRY_CLEAN_WORKSPACE") or "0").lower() in (
    "1",
    "true",
    "yes",
)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="colmap")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def _job_paths(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _status_path(job_id: str) -> Path:
    return _job_paths(job_id) / "status.json"


def _write_status(job_id: str, payload: dict[str, Any]) -> None:
    p = _status_path(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(p)


def _read_status(job_id: str) -> dict[str, Any] | None:
    p = _status_path(job_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for member in zf.namelist():
        if member.startswith("/") or ".." in member.replace("\\", "/"):
            raise ValueError(f"Unsafe zip entry: {member!r}")
        target = (dest / member).resolve()
        if not str(target).startswith(str(dest.resolve())):
            raise ValueError(f"Zip slip: {member!r}")
    zf.extractall(dest)


def _flatten_images_to(images_root: Path, out_dir: Path) -> int:
    """Move/copy any images under images_root into out_dir (flat). Returns count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in images_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in IMAGE_EXT:
            continue
        name = f"{n:05d}_{p.name}"
        dest = out_dir / name
        shutil.copy2(p, dest)
        n += 1
    return n


def _run_job_worker(job_id: str) -> None:
    root = _job_paths(job_id)

    def fail(msg: str, code: str = "failed") -> None:
        log_path = root / "colmap.log"
        if log_path.is_file():
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
            except OSError:
                tail = ""
        else:
            tail = ""
        _write_status(
            job_id,
            {
                "id": job_id,
                "status": code,
                "message": msg,
                "log_excerpt": tail[-2000:] if tail else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    try:
        _write_status(
            job_id,
            {
                "id": job_id,
                "status": "running",
                "message": "COLMAP 실행 중…",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        script = _THIS_DIR / "scripts" / "run_colmap_job.py"
        py = sys.executable
        cmd = [
            py,
            str(script),
            "--job-dir",
            str(root),
        ]
        if COLMAP_EXPORT_GLB:
            cmd.append("--export-glb")
        if COLMAP_CLEAN:
            cmd.append("--clean-on-success")

        env = os.environ.copy()
        job_timeout = int(os.environ.get("PHOTOGRAMMETRY_JOB_TIMEOUT_SEC") or "0")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=job_timeout if job_timeout > 0 else None,
            env=env,
        )
        if proc.stdout:
            (root / "worker_stdout.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
        if proc.stderr:
            (root / "worker_stderr.log").write_text(proc.stderr, encoding="utf-8", errors="replace")

        if proc.returncode != 0:
            fail(
                f"run_colmap_job.py exited {proc.returncode}. 로컬에서 Phase A(COLMAP) 확인하세요.",
                "failed",
            )
            return

        out = root / "output"
        mesh_ply = out / "mesh.ply"
        sparse_ply = out / "sparse_points.ply"
        glb = out / "mesh.glb"
        result_name: str | None = None
        if mesh_ply.is_file():
            result_name = "mesh.ply"
        elif sparse_ply.is_file():
            result_name = "sparse_points.ply"

        if not result_name:
            fail("산출물이 없습니다 (output/mesh.ply). colmap.log 를 확인하세요.")
            return

        base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        rel = f"/photogrammetry/jobs/{job_id}/download/{result_name}"
        download_url = f"{base}{rel}" if base else rel

        payload: dict[str, Any] = {
            "id": job_id,
            "status": "completed",
            "message": "완료",
            "result_file": result_name,
            "download_path": rel,
            "download_url": download_url,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if glb.is_file():
            payload["glb_available"] = True
            payload["glb_path"] = f"/photogrammetry/jobs/{job_id}/download/mesh.glb"
        _write_status(job_id, payload)
    except subprocess.TimeoutExpired:
        fail("타임아웃 (OR_PHOTO_TIMEOUT_SEC). 데이터셋을 줄이거나 품질을 낮추세요.")
    except Exception as e:
        logger.exception("job %s", job_id)
        fail(str(e))


def _kick_colmap_job(job_id: str) -> None:
    """Non-blocking: COLMAP runs in thread pool (do not run heavy work on the event loop)."""
    _executor.submit(_run_job_worker, job_id)


app = FastAPI(title="Origin Real · Photogrammetry", version="0.1.0")

_origins: list[str] = []
if (os.environ.get("CORS_ALLOW_ALL") or "").lower() in ("1", "true", "yes"):
    _origins = ["*"]
else:
    for d in (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ):
        if d not in _origins:
            _origins.append(d)
    nu = (os.environ.get("NEXTAUTH_URL") or "").strip().rstrip("/")
    if nu and nu not in _origins:
        _origins.append(nu)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    colmap = (os.environ.get("COLMAP_EXECUTABLE") or "colmap").strip()
    return {
        "ok": True,
        "service": "photogrammetry",
        "colmap_executable": colmap,
        "data_dir": str(DATA_DIR),
    }


@app.post("/photogrammetry/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    images: list[UploadFile] | None = File(None),
) -> JSONResponse:
    if not file and not images:
        raise HTTPException(400, "ZIP(file) 또는 이미지(images) 중 하나는 필요합니다.")

    job_id = str(uuid.uuid4())
    root = _job_paths(job_id)
    img_dir = root / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    try:
        if file and file.filename:
            raw = await file.read()
            if len(raw) > MAX_ZIP_BYTES:
                raise HTTPException(400, f"ZIP 크기 제한 {MAX_ZIP_BYTES} bytes 초과")
            if not file.filename.lower().endswith(".zip"):
                raise HTTPException(400, "file 필드는 .zip 만 지원합니다.")
            zbuf = Path(root / "upload.zip")
            zbuf.write_bytes(raw)
            extract_to = root / "_zip_extract"
            if extract_to.exists():
                shutil.rmtree(extract_to, ignore_errors=True)
            extract_to.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zbuf, "r") as zf:
                _safe_extract_zip(zf, extract_to)
            n = _flatten_images_to(extract_to, img_dir)
            shutil.rmtree(extract_to, ignore_errors=True)
            if n < 3:
                raise HTTPException(400, f"유효한 이미지가 3장 미만입니다 (발견 {n}).")
        else:
            if not images:
                raise HTTPException(400, "images 가 비었습니다.")
            if len(images) > MAX_IMAGES:
                raise HTTPException(400, f"이미지는 최대 {MAX_IMAGES} 장입니다.")
            n = 0
            for uf in images:
                if not uf.filename:
                    continue
                suf = Path(uf.filename).suffix.lower()
                if suf not in IMAGE_EXT:
                    continue
                data = await uf.read()
                if not data:
                    continue
                (img_dir / f"{n:05d}_{Path(uf.filename).name}").write_bytes(data)
                n += 1
            if n < 3:
                raise HTTPException(400, f"유효한 이미지가 3장 미만입니다 (업로드 {n}).")

        _write_status(
            job_id,
            {
                "id": job_id,
                "status": "pending",
                "message": "대기 중",
                "image_count": n,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        background_tasks.add_task(_kick_colmap_job, job_id)

        return JSONResponse(
            status_code=202,
            content={
                "id": job_id,
                "status": "pending",
                "message": "작업이 큐에 등록되었습니다.",
                "poll_url": f"/photogrammetry/jobs/{job_id}",
            },
        )
    except HTTPException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    except ValueError as e:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        shutil.rmtree(root, ignore_errors=True)
        logger.exception("create_job")
        raise HTTPException(500, str(e)) from e


@app.get("/photogrammetry/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", job_id):
        raise HTTPException(400, "잘못된 job id")
    st = _read_status(job_id)
    if st is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return st


@app.get("/photogrammetry/jobs/{job_id}/download/{name}")
def download(job_id: str, name: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", job_id):
        raise HTTPException(400, "잘못된 job id")
    if name not in ("mesh.ply", "sparse_points.ply", "mesh.glb"):
        raise HTTPException(400, "허용되지 않은 파일명")
    p = _job_paths(job_id) / "output" / name
    if not p.is_file():
        raise HTTPException(404, "파일 없음")
    media = "model/gltf-binary" if name.endswith(".glb") else "application/octet-stream"
    return FileResponse(p, filename=name, media_type=media)
