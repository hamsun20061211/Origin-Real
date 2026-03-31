"""
Origin Real용 TripoSR FastAPI 서버.

배치 방법 (택 1):
  A) VAST-AI-Research/TripoSR 클론을 이 폴더 안에 `TripoSR/` 로 두고 실행
  B) 이 파일을 TripoSR 저장소 루트(tsr/ 가 있는 곳)에 복사해 `python main.py` 실행

필수: TripoSR `pip install -r requirements.txt` + `checkpoints/model.ckpt` 및 `config.yaml`
      (없으면 기본으로 stabilityai/TripoSR 을 HF에서 받음)
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import logging
import os
import re
import secrets
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx


def _merge_repo_env_files_into_environ() -> None:
    """레포 루트 .env → .env.local (로컬이 우선). 이미 셸에 있는 키는 덮어쓰지 않음."""
    root = Path(__file__).resolve().parent.parent
    merged: dict[str, str] = {}
    for name in (".env", ".env.local"):
        p = root / name
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

# -----------------------------------------------------------------------------
# TripoSR 소스 경로 — 반드시 `tsr` 패키지 import 전에 설정
# -----------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
if (_THIS_DIR / "tsr").is_dir():
    TRIPOSR_ROOT = _THIS_DIR
else:
    TRIPOSR_ROOT = Path(os.environ.get("TRIPOSR_ROOT", _THIS_DIR / "TripoSR"))

# TripoSR 루트에 analyze_pipeline.py 등이 있으면 동명 모듈이 먼저 잡혀 Origin Real 래퍼가 무시됨.
# → tsr 는 TRIPOSR_ROOT 에서, 나머지 래퍼는 triposr-server(_THIS_DIR) 가 우선하도록 순서를 맞춤.
def _ensure_sys_path_first(dir_path: Path) -> None:
    s = str(dir_path.resolve())
    while s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)


_ensure_sys_path_first(TRIPOSR_ROOT)
_ensure_sys_path_first(_THIS_DIR)


def _ensure_torchmcubes() -> None:
    """CUDA Toolkit 없이 torchmcubes 빌드가 실패할 때 skimage 기반 CPU marching cubes로 대체."""
    if importlib.util.find_spec("torchmcubes") is not None:
        return
    if (os.environ.get("TRIPOSR_FORCE_TORCHMCUBES") or "").lower() in ("1", "true", "yes"):
        raise ImportError(
            "torchmcubes 패키지가 없고 TRIPOSR_FORCE_TORCHMCUBES=1 입니다. "
            "CUDA Toolkit 설치 후: pip install git+https://github.com/tatsy/torchmcubes.git"
        )
    import numpy as np
    import torch
    from skimage.measure import marching_cubes as sk_mc

    def marching_cubes(vol: torch.Tensor, level: float):
        arr = np.ascontiguousarray(vol.detach().cpu().float().numpy())
        verts, faces, _, _ = sk_mc(arr, level=float(level))
        v = torch.from_numpy(np.ascontiguousarray(verts.astype(np.float32, copy=False)))
        f = torch.from_numpy(
            np.ascontiguousarray(faces.astype(np.int64, copy=False))
        )
        return v, f

    mod = types.ModuleType("torchmcubes")
    mod.marching_cubes = marching_cubes
    sys.modules["torchmcubes"] = mod
    print(
        "[TripoSR] torchmcubes 미설치 -> skimage.measure.marching_cubes (CPU, 느릴 수 있음). "
        "GPU MC는 CUDA Toolkit + torchmcubes 빌드 권장.",
        flush=True,
    )


_ensure_torchmcubes()

try:
    from tsr.system import TSR
    from tsr.utils import remove_background, resize_foreground
except ImportError as e:
    root_display = TRIPOSR_ROOT.as_posix()
    missing_mod = getattr(e, "name", None)
    if missing_mod == "tsr" or "No module named 'tsr'" in str(e):
        raise ImportError(
            "TripoSR(tsr) 패키지를 찾을 수 없습니다. Origin Real 레포에는 TripoSR 본체가 포함되지 않습니다.\n"
            "해결:\n"
            "  1) 공식 저장소를 클론: git clone https://github.com/VAST-AI-Research/TripoSR.git\n"
            f"  2) 폴더를 여기에 두거나 TRIPOSR_ROOT 환경 변수로 지정 (안에 `tsr` 폴더가 있어야 함):\n"
            f"     기본 경로: {_THIS_DIR / 'TripoSR'}\n"
            "  3) 해당 TripoSR 폴더에서 venv 활성화 후: pip install -r requirements.txt\n"
            "  4) UI만 볼 때는: npm run engine:stub (메쉬 생성 불가)\n"
            f"(현재 tsr 루트: {root_display}, 원인: {e})"
        ) from e
    raise ImportError(
        f"TripoSR 의존성 import 실패: {e}\n"
        f"→ TripoSR 폴더({root_display})에서 사용 중인 가상환경을 켠 뒤:\n"
        "     pip install -r requirements.txt\n"
        "   그 다음 **같은 터미널**에서 TRIPOSR_ROOT 설정 후 npm run engine 을 다시 실행하세요.\n"
        "   (npm run engine 이 그 venv의 python 을 쓰려면 activate 후 PATH에 venv가 우선이어야 합니다.)"
    ) from e

import numpy as np
import rembg
import torch
import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from PIL import Image

from analyze_pipeline import analyze_image_parts
from inference_queue import generation_slot, queue_snapshot
from lora_utils import apply_lora_safetensors, resolve_default_lora_paths

try:
    from realesrgan_upscale import (
        enabled as realesrgan_enabled,
        maybe_upscale_before_triposr,
        preload_if_requested as realesrgan_preload_if_requested,
        upsampler_loaded as realesrgan_upsampler_loaded,
    )
except ImportError:

    def realesrgan_enabled() -> bool:  # type: ignore[misc]
        return False

    def realesrgan_upsampler_loaded() -> bool:  # type: ignore[misc]
        return False

    def maybe_upscale_before_triposr(pil, *, device: str):  # type: ignore[misc]
        return pil

    def realesrgan_preload_if_requested(*, device: str) -> None:  # type: ignore[misc]
        pass
from multiview_fusion import collect_view_images, seamless_fuse_multiview
from quality_presets import apply_quality_preset, current_preset_label
from text_to_3d_replicate import run_replicate_text_to_glb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("origin_real.triposr")

_REPO_ROOT = _THIS_DIR.parent
_model: TSR | None = None
_device: str = "cpu"
_rembg_session = None
_chunk_size: int = 8192
_mc_resolution: int = 384
_infer_fp16: str = "autocast"
_model_fp16_weights: bool = False
_lora_loaded: bool = False
_glb_downloads: dict[str, Path] = {}
_startup_task: asyncio.Task | None = None

try:
    from hq_pipeline import (
        bake_vertex_colors_to_texture_map,
        clear_torch_memory,
        hq_pipeline_enabled,
        hybrid_enhance_for_triposr,
        release_hq_models,
        texture_bake_resolution,
        texture_bake_enabled,
    )
except ImportError:
    def hybrid_enhance_for_triposr(pil, device):  # type: ignore[misc]
        return pil

    def bake_vertex_colors_to_texture_map(mesh, resolution=None):  # type: ignore[misc]
        return mesh

    def clear_torch_memory(device) -> None:  # type: ignore[misc]
        pass

    def hq_pipeline_enabled() -> bool:  # type: ignore[misc]
        return False

    def texture_bake_enabled() -> bool:  # type: ignore[misc]
        return False

    def texture_bake_resolution() -> int:  # type: ignore[misc]
        return 2048

    def release_hq_models() -> None:  # type: ignore[misc]
        pass


def _resolve_pretrained_dir() -> str:
    """`checkpoints/model.ckpt` + `config.yaml` 디렉터리 또는 HF repo id."""
    env_ckpt = os.environ.get("TRIPOSR_CHECKPOINT_DIR")
    if env_ckpt:
        p = Path(env_ckpt)
        if (p / "model.ckpt").is_file():
            logger.info("Using TRIPOSR_CHECKPOINT_DIR=%s", p)
            return str(p.resolve())
        logger.warning("TRIPOSR_CHECKPOINT_DIR 에 model.ckpt 없음: %s", p)

    local_ckpt = TRIPOSR_ROOT / "checkpoints" / "model.ckpt"
    if local_ckpt.is_file():
        d = str(local_ckpt.parent.resolve())
        logger.info("Using %s (model.ckpt)", d)
        return d

    hub = os.environ.get("TRIPOSR_PRETRAINED", "stabilityai/TripoSR")
    logger.info("Using Hugging Face: %s", hub)
    return hub


def _pick_device() -> str:
    if torch.cuda.is_available():
        d = os.environ.get("TRIPOSR_DEVICE", "cuda:0")
        logger.info("CUDA 사용: %s", d)
        return d
    logger.info("CUDA 없음 — CPU 모드")
    return "cpu"


def _cuda_release_after_inference() -> None:
    """추론 직후 예약 VRAM 해제 — OOM 완화. 퀄리티용 mc_resolution 등은 건드리지 않음."""
    clear_torch_memory(_device)
    if torch.cuda.is_available():
        try:
            torch.cuda.synchronize()
        except Exception:
            pass
        torch.cuda.empty_cache()


def _pil_c_contiguous_rgb(pil: Image.Image) -> Image.Image:
    """PIL/NumPy 뷰가 음수 stride일 때 torch.from_numpy 가 실패하므로 연속 메모리로 복사."""
    arr = np.ascontiguousarray(np.asarray(pil.convert("RGB"), dtype=np.uint8))
    return Image.fromarray(arr, mode="RGB")


def _env_truthy(key: str, default: bool) -> bool:
    v = (os.environ.get(key) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _rembg_remove_kwargs() -> dict:
    """건물·차량 외곽선 정리: alpha_matting (기본 활성, TRIPOSR_REMBG_ALPHA_MATTING=0 으로 끔)."""
    if not _env_truthy("TRIPOSR_REMBG_ALPHA_MATTING", True):
        return {}
    return {
        "alpha_matting": True,
        "alpha_matting_foreground_threshold": int(
            os.environ.get("TRIPOSR_REMBG_ALPHA_MATTING_FG_THRESHOLD", "240")
        ),
        "alpha_matting_background_threshold": int(
            os.environ.get("TRIPOSR_REMBG_ALPHA_MATTING_BG_THRESHOLD", "10")
        ),
        "alpha_matting_erode_size": int(os.environ.get("TRIPOSR_REMBG_ALPHA_MATTING_ERODE", "10")),
    }


def _expand_square_rgba_margin(pil_rgba: Image.Image, margin_ratio: float) -> Image.Image:
    """
    resize_foreground 직후 정사각형 RGBA 주변에 균일 투명 여백을 붙여 다시 정사각형으로.
    3D 모델이 프레임에 너무 꽉 차면 생기는 아티팩트 완화.
    """
    if margin_ratio <= 0:
        return pil_rgba
    img = pil_rgba.convert("RGBA")
    w, h = img.size
    if w < 2 or h < 2:
        return img
    side = max(w, h)
    if w != h:
        sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sq.paste(img, ((side - w) // 2, (side - h) // 2))
        img = sq
        w = h = side
    pad = int(round(side * margin_ratio))
    pad = max(pad, 2)
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    out.paste(img, (pad, pad))
    return out


def _preprocess_image(pil_rgb: Image.Image, do_remove_bg: bool) -> Image.Image:
    """TripoSR 입력 전처리: rembg(옵션) → 전경 비율 → 여백 확장 → RGB 합성."""
    margin_ratio = float(os.environ.get("TRIPOSR_PREPROCESS_MARGIN_RATIO", "0.08"))

    if do_remove_bg:
        if _rembg_session is None:
            raise RuntimeError("rembg session not initialized")
        kw = _rembg_remove_kwargs()
        try:
            rgba = remove_background(pil_rgb, _rembg_session, **kw)
        except TypeError as e:
            logger.warning("rembg alpha_matting 옵션 미지원 → 기본 제거만: %s", e)
            rgba = remove_background(pil_rgb, _rembg_session)
    else:
        rgb = pil_rgb.convert("RGB")
        rgba = rgb.convert("RGBA")

    ratio = float(os.environ.get("TRIPOSR_FOREGROUND_RATIO", "0.85"))
    resized = resize_foreground(rgba, ratio)
    padded = _expand_square_rgba_margin(resized, margin_ratio)

    arr = np.asarray(padded).astype(np.float32) / 255.0
    arr = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
    return Image.fromarray((arr * 255.0).astype(np.uint8))


def _mesh_to_glb_bytes(mesh) -> bytes:
    buf = io.BytesIO()
    mesh.export(file_obj=buf, file_type="glb")
    return buf.getvalue()


def _build_cors_origins() -> list[str]:
    """Origin Real(Next) + Cloudflare Tunnel 도메인은 CORS_ORIGINS / NEXTAUTH_URL 로 지정."""
    out: list[str] = []
    raw = (os.environ.get("CORS_ORIGINS") or "").strip()
    if raw:
        out.extend(x.strip() for x in raw.split(",") if x.strip())
    na = (os.environ.get("NEXTAUTH_URL") or "").strip().rstrip("/")
    if na and na not in out:
        out.append(na)
    for d in (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ):
        if d not in out:
            out.append(d)
    return out


def _public_base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")


def _fetch_url_image_sync(url: str, max_bytes: int = 25_000_000) -> bytes:
    u = url.strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("image_url must be http(s) with a host")
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.get(u, headers={"User-Agent": "OriginReal-TripoSR/1.0"})
        r.raise_for_status()
        ct = (r.headers.get("content-type") or "").lower()
        if "image" not in ct and "octet-stream" not in ct:
            logger.warning("Unexpected content-type for image_url: %s", ct)
        data = r.content
    if len(data) > max_bytes:
        raise ValueError(f"Image too large (>{max_bytes} bytes)")
    if len(data) < 32:
        raise ValueError("Empty or invalid image response")
    return data


def _pil_to_png_bytes(pil: Image.Image) -> bytes:
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def _run_generation_sync(image_bytes: bytes) -> bytes:
    if _model is None:
        raise RuntimeError("모델이 초기화되지 않았습니다.")

    no_rmbg = os.environ.get("TRIPOSR_NO_REMOVE_BG", "").lower() in ("1", "true", "yes")

    try:
        pil = _pil_c_contiguous_rgb(Image.open(io.BytesIO(image_bytes)))
    except Exception as e:
        logger.exception("이미지 디코딩 실패")
        raise ValueError(f"이미지를 열 수 없습니다: {e}") from e

    pil = _pil_c_contiguous_rgb(maybe_upscale_before_triposr(pil, device=_device))

    try:
        processed = _preprocess_image(pil, do_remove_bg=not no_rmbg)
    except Exception:
        logger.exception("전처리 실패")
        raise

    if hq_pipeline_enabled():
        try:
            processed = hybrid_enhance_for_triposr(processed, _device)
        except Exception:
            logger.exception("하이브리드 HQ 전처리 실패 — TripoSR 기본 입력으로 진행")
            clear_torch_memory(_device)

    processed = _pil_c_contiguous_rgb(processed)

    use_cuda = str(_device).startswith("cuda")
    try:
        with torch.no_grad():
            if use_cuda and _infer_fp16 == "autocast" and not _model_fp16_weights:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    scene_codes = _model([processed], device=_device)
                scene_codes = scene_codes.float()
            else:
                scene_codes = _model([processed], device=_device)
                # .half() 가중치 모델은 extract_mesh(렌더러)도 FP16 — scene_codes 를 FP32로 올리면
                # "mat1 Float mat2 Half" RuntimeError 가 난다.
                if not _model_fp16_weights and scene_codes.dtype != torch.float32:
                    scene_codes = scene_codes.float()
            meshes = _model.extract_mesh(
                scene_codes,
                has_vertex_color=True,
                resolution=_mc_resolution,
            )
    except Exception:
        logger.exception("TripoSR 추론 또는 메쉬 추출 실패")
        _cuda_release_after_inference()
        raise

    _cuda_release_after_inference()

    mesh_out = meshes[0]
    if hq_pipeline_enabled() and texture_bake_enabled():
        try:
            mesh_out = bake_vertex_colors_to_texture_map(
                mesh_out, resolution=texture_bake_resolution()
            )
        except Exception:
            logger.exception("PBR 텍스처 베이크 실패 — 버텍스 컬러 메쉬로 보냄")

    try:
        glb = _mesh_to_glb_bytes(mesh_out)
    except Exception:
        logger.exception("GLB보내기 실패")
        _cuda_release_after_inference()
        raise

    _cuda_release_after_inference()
    logger.info("3D Generation... Done")
    logger.info("GLB 생성 완료: %d bytes", len(glb))
    return glb


def _sync_startup_load() -> None:
    """TripoSR·rembg 등 동기 초기화(느림). asyncio.to_thread 에서 실행해 이벤트 루프를 막지 않음."""
    global _model, _device, _rembg_session, _chunk_size, _mc_resolution
    global _infer_fp16, _model_fp16_weights, _lora_loaded

    apply_quality_preset()

    _device = _pick_device()
    _chunk_size = int(os.environ.get("TRIPOSR_CHUNK_SIZE", "8192"))
    _mc_resolution = int(os.environ.get("TRIPOSR_MC_RESOLUTION", "384"))
    _infer_fp16 = (os.environ.get("TRIPOSR_INFER_FP16") or "autocast").strip().lower()
    if _infer_fp16 not in ("autocast", "float32", "half"):
        _infer_fp16 = "autocast"

    pretrained = _resolve_pretrained_dir()
    logger.info("TSR 로드 중: %s (config.yaml + model.ckpt)", pretrained)

    try:
        _model = TSR.from_pretrained(
            pretrained,
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        _model.renderer.set_chunk_size(_chunk_size)
        _model.to(_device)
    except Exception:
        logger.exception("가중치 로드 실패 — checkpoints 와 config.yaml 경로를 확인하세요")
        raise

    skip_lora = (os.environ.get("TRIPOSR_SKIP_LORA") or "").lower() in ("1", "true", "yes")
    lora_st = "" if skip_lora else (os.environ.get("TRIPOSR_LORA_SAFETENSORS") or "").strip()
    lora_cfg = "" if skip_lora else (os.environ.get("TRIPOSR_LORA_CONFIG") or "").strip()
    if not skip_lora and not lora_st:
        d_st, d_cfg = resolve_default_lora_paths(_REPO_ROOT)
        if d_st is not None and d_cfg is not None:
            lora_st, lora_cfg = str(d_st), str(d_cfg)
            logger.info("Default LoRA: %s + %s", lora_st, lora_cfg)
    if lora_st and lora_cfg:
        try:
            apply_lora_safetensors(_model, Path(lora_st), Path(lora_cfg))
            _lora_loaded = True
            _model.to(_device)
        except Exception:
            logger.exception("LoRA 로드 실패 — safetensors / adapter_config 확인 또는 TRIPOSR_SKIP_LORA=1")
            raise
    else:
        logger.info("LoRA 미사용 (TRIPOSR_LORA_SAFETENSORS / 기본 models/checkpoints 없음)")

    if (
        os.environ.get("TRIPOSR_TORCH_COMPILE", "").lower() in ("1", "true", "yes")
        and str(_device).startswith("cuda")
    ):
        try:
            _model.backbone = torch.compile(  # type: ignore[assignment]
                _model.backbone,
                mode=os.environ.get("TRIPOSR_COMPILE_MODE", "reduce-overhead"),
            )
            logger.info("torch.compile(backbone) 활성화 (첫 추론이 느릴 수 있음)")
        except Exception as e:
            logger.warning("torch.compile 건너뜀: %s", e)

    _model_fp16_weights = False
    # LoRA + 전체 .half() 시 TripoSR extract_mesh → grid_sample 에서
    # "expected scalar type Half but found Float" 가 날 수 있음 (렌더러 그리드는 FP32).
    force_fp32_weights = _infer_fp16 == "float32" or (
        _lora_loaded
        and (os.environ.get("TRIPOSR_FORCE_HALF_WITH_LORA") or "").strip().lower()
        not in ("1", "true", "yes")
    )
    if str(_device).startswith("cuda") and not force_fp32_weights:
        try:
            _model.half()
            _model_fp16_weights = True
            logger.info(
                "CUDA 가중치 float16 강제 (.half) — mc_resolution·품질 프리셋 유지, OOM 완화. "
                "순수 FP32 가중치는 TRIPOSR_INFER_FP16=float32"
            )
        except Exception as e:
            logger.warning("모델 .half() 실패 — float32 유지: %s", e)
    elif str(_device).startswith("cuda"):
        if _lora_loaded and _infer_fp16 != "float32":
            logger.info(
                "LoRA 사용 중 — extract_mesh dtype 호환을 위해 가중치 FP32 유지 "
                "(강제 half: TRIPOSR_FORCE_HALF_WITH_LORA=1 또는 비활성화: TRIPOSR_SKIP_LORA=1)"
            )
        else:
            logger.info("TRIPOSR_INFER_FP16=float32 — CUDA 가중치 float32 (최대 VRAM)")

    if os.environ.get("TRIPOSR_NO_REMOVE_BG", "").lower() not in ("1", "true", "yes"):
        _rembg_session = rembg.new_session()
        am_kw = _rembg_remove_kwargs()
        logger.info(
            "rembg 전처리: alpha_matting=%s | TRIPOSR_PREPROCESS_MARGIN_RATIO=%s",
            am_kw.get("alpha_matting", False),
            os.environ.get("TRIPOSR_PREPROCESS_MARGIN_RATIO", "0.08"),
        )
    else:
        _rembg_session = None
        logger.info("배경 제거 비활성화 (TRIPOSR_NO_REMOVE_BG)")

    try:
        realesrgan_preload_if_requested(device=_device)
    except Exception:
        logger.exception("Real-ESRGAN preload 스킵")

    logger.info(
        "TripoSR 준비 완료 (%s) | mc_resolution=%d | infer_fp16=%s | weights_fp16=%s | LoRA=%s | HQ=%s | Real-ESRGAN=%s | OR_QUALITY=%s",
        _device,
        _mc_resolution,
        _infer_fp16,
        _model_fp16_weights,
        _lora_loaded,
        hq_pipeline_enabled(),
        realesrgan_enabled(),
        current_preset_label() or "(미설정, 개별 env만)",
    )


async def _async_startup_load() -> None:
    try:
        await asyncio.to_thread(_sync_startup_load)
    except Exception:
        logger.exception(
            "TripoSR 백그라운드 초기화 실패 — /analyze 는 동작할 수 있으나 메쉬 생성(/generate)은 불가합니다."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_task, _model, _rembg_session

    logger.info(
        "HTTP 수락 시작 — TripoSR 가중치는 백그라운드 로드 중입니다. "
        "완료 전에도 POST /analyze·GET /health 가 응답합니다 (health 의 model_loaded=false 이면 아직 로딩)."
    )
    loop = asyncio.get_running_loop()
    _startup_task = loop.create_task(_async_startup_load())
    try:
        yield
    finally:
        t = _startup_task
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        _model = None
        _rembg_session = None
        release_hq_models()
        clear_torch_memory(_device)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("서버 종료")


app = FastAPI(
    title="Origin Real · TripoSR",
    lifespan=lifespan,
)

_cors_allow_all = (os.environ.get("CORS_ALLOW_ALL") or "").lower() in ("1", "true", "yes")
_cors_origins = _build_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors_allow_all else _cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """브라우저에서 localhost:8000 만 열었을 때 404 대신 안내."""
    return {
        "service": "Origin Real · TripoSR API",
        "docs": "/docs",
        "health": "/health",
        "status": "/status",
        "note": "웹 UI는 Next.js(예: localhost:3000). LoRA·큐: POST /generate-3d, 기존 프록시: POST /generate, /generate/image",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": _device,
        "model_loaded": _model is not None,
        "triposr_root": str(TRIPOSR_ROOT),
        "mc_resolution": _mc_resolution,
        "hq_pipeline": hq_pipeline_enabled(),
        "realesrgan": realesrgan_enabled(),
        "realesrgan_loaded": realesrgan_upsampler_loaded(),
        "texture_bake": texture_bake_enabled(),
        "texture_bake_resolution": texture_bake_resolution(),
        "multiview": True,
        "analyze_endpoint": True,
        "or_quality": current_preset_label(),
        "or_quality_hint": "최고 품질: OR_QUALITY=ultra (VRAM·시간 증가)",
        "text_to_3d": (
            "replicate"
            if (os.environ.get("REPLICATE_API_TOKEN") or "").strip()
            else "off (REPLICATE_API_TOKEN 필요)"
        ),
        "model_loading": _startup_task is not None and not _startup_task.done(),
    }


@app.get("/status")
async def status():
    """서버·GPU·대기 큐(FIFO 단일 슬롯) 상태."""
    q = queue_snapshot()
    return {
        "status": "ok",
        "device": _device,
        "model_loaded": _model is not None,
        "lora_loaded": _lora_loaded,
        "infer_fp16": _infer_fp16,
        "model_weights_fp16": _model_fp16_weights,
        "torch_compile": (os.environ.get("TRIPOSR_TORCH_COMPILE") or "").lower()
        in ("1", "true", "yes"),
        "queue_waiting": q["waiting_jobs"],
        "queue_running": q["running"],
        "queue_total_pending": q["queued_total"],
        "mc_resolution": _mc_resolution,
        "model_loading": _startup_task is not None and not _startup_task.done(),
    }


def _require_model_for_generate() -> None:
    if _model is not None:
        return
    if _startup_task is not None and not _startup_task.done():
        raise HTTPException(
            status_code=503,
            detail=(
                "TripoSR 모델이 아직 로딩 중입니다. GET /health 에서 model_loaded 가 true 가 될 때까지 "
                "잠시 기다린 뒤 다시 시도하세요."
            ),
        )
    raise HTTPException(
        status_code=503,
        detail="TripoSR 모델을 사용할 수 없습니다. 엔진 로그의 초기화 오류를 확인하세요.",
    )


def _register_glb_download(glb: bytes) -> str:
    token = secrets.token_urlsafe(24)
    tmp = Path(os.environ.get("TRIPOSR_TEMP_GLB", str(_THIS_DIR / "temp_glb")))
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / f"{token}.glb"
    path.write_bytes(glb)
    _glb_downloads[token] = path.resolve()
    return token


@app.get("/files/{token}")
async def download_temp_glb(token: str, background_tasks: BackgroundTasks):
    path = _glb_downloads.get(token)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="만료되었거나 없는 토큰입니다.")

    def _cleanup() -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        _glb_downloads.pop(token, None)

    if (os.environ.get("TRIPOSR_DELETE_AFTER_DOWNLOAD") or "1").lower() in (
        "1",
        "true",
        "yes",
    ):
        background_tasks.add_task(_cleanup)

    return FileResponse(
        path,
        media_type="model/gltf-binary",
        filename="origin-real-model.glb",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/generate-3d")
async def generate_3d(
    image: UploadFile | None = File(None),
    image_url: str | None = Form(None),
    response_mode: str = Form("inline"),
):
    """
    차량·건물 LoRA 파이프라인용 메인 엔드포인트.
    - multipart `image` 또는 Form `image_url` (http/https).
    - `response_mode`: `inline`(기본) → GLB 바이너리, `json` → 다운로드 URL/경로.
    """
    has_file = image is not None and bool(image.filename)
    has_url = bool((image_url or "").strip())
    if not has_file and not has_url:
        raise HTTPException(
            status_code=400,
            detail="multipart 필드 `image` 또는 Form 필드 `image_url` 중 하나가 필요합니다.",
        )
    if has_file and has_url:
        raise HTTPException(
            status_code=400,
            detail="`image` 와 `image_url` 은 동시에 사용할 수 없습니다.",
        )

    if has_url:
        try:
            raw = await asyncio.to_thread(_fetch_url_image_sync, image_url.strip())
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        raw = await image.read()
        if not raw:
            raise HTTPException(status_code=400, detail="빈 이미지 파일입니다.")

    _require_model_for_generate()

    async with generation_slot():
        try:
            glb_bytes = await asyncio.to_thread(_run_generation_sync, raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("generate-3d 실패")
            raise HTTPException(
                status_code=500,
                detail=f"{type(e).__name__}: {e}",
            ) from e

    mode = (response_mode or "inline").strip().lower()
    if mode == "json":
        tid = _register_glb_download(glb_bytes)
        base = _public_base_url()
        rel_path = f"/files/{tid}"
        full = f"{base}{rel_path}" if base else ""
        return JSONResponse(
            {
                "ok": True,
                "download_path": rel_path,
                "download_url": full or rel_path,
                "hint": "PUBLIC_BASE_URL 을 설정하면 터널/프록시 절대 URL이 됩니다.",
            }
        )

    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={
            "Content-Disposition": 'attachment; filename="origin-real-model.glb"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/analyze")
async def analyze(
    front: UploadFile = File(...),
    seed: int = Query(0, ge=0, le=2_147_000_000),
):
    """이미지 분석 → 부품 후보(JSON). TripoSR 가중치와 별개로 동작."""
    if not front.filename:
        raise HTTPException(status_code=400, detail="front 파일이 필요합니다.")
    raw = await front.read()
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        pil = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"이미지 디코딩 실패: {e}") from e

    logger.info("Analyze 요청: %s seed=%s", front.filename, seed)

    def _work():
        return analyze_image_parts(pil, seed=seed)

    try:
        payload = await asyncio.to_thread(_work)
    except Exception as e:
        logger.exception("분석 실패")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

    return JSONResponse(content=payload)


class TextGenerateBody(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    enhance_keywords: bool = True


_TEXT_QUALITY_SUFFIX = (
    ", ultra high-fidelity 3D asset, PBR materials, clean topology, "
    "studio lighting, game-ready, film-quality"
)


async def _generate_image_response(
    image: UploadFile | None,
    file: UploadFile | None,
    front: UploadFile | None,
    back: UploadFile | None,
    left: UploadFile | None,
    right: UploadFile | None,
) -> Response:
    upload = image or file
    raw: bytes | None = None
    label = ""

    if front is not None and front.filename:
        fb = await front.read()
        if not fb:
            raise HTTPException(status_code=400, detail="front 파일이 비어 있습니다.")
        bb = await back.read() if back and back.filename else None
        lb = await left.read() if left and left.filename else None
        rb = await right.read() if right and right.filename else None
        try:
            f_img, sides = collect_view_images(
                {"front": fb, "back": bb, "left": lb, "right": rb}
            )
            fused = seamless_fuse_multiview(
                f_img, back=sides["back"], left=sides["left"], right=sides["right"]
            )
            raw = _pil_to_png_bytes(fused)
            label = f"multiview fuse → {len(raw)} bytes"
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    elif upload is not None and upload.filename:
        raw = await upload.read()
        label = upload.filename or "image"
    else:
        raise HTTPException(
            status_code=400,
            detail="`image`/`file` 단일 필드 또는 `front` 멀티뷰 필드가 필요합니다.",
        )

    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    logger.info("Image→3D 요청: %s (%d bytes)", label or "image", len(raw))

    _require_model_for_generate()

    async with generation_slot():
        try:
            glb_bytes = await asyncio.to_thread(_run_generation_sync, raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("생성 중 예외")
            raise HTTPException(
                status_code=500,
                detail=f"{type(e).__name__}: {e}",
            ) from e

    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={
            "Content-Disposition": 'inline; filename="triposr-output.glb"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/generate")
async def generate(
    image: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
    front: UploadFile | None = File(None),
    back: UploadFile | None = File(None),
    left: UploadFile | None = File(None),
    right: UploadFile | None = File(None),
):
    return await _generate_image_response(image, file, front, back, left, right)


@app.post("/generate/image")
async def generate_image(
    image: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
    front: UploadFile | None = File(None),
    back: UploadFile | None = File(None),
    left: UploadFile | None = File(None),
    right: UploadFile | None = File(None),
):
    return await _generate_image_response(image, file, front, back, left, right)


@app.post("/generate/text")
async def generate_text(body: TextGenerateBody):
    p = body.prompt.strip()
    full = f"{p}{_TEXT_QUALITY_SUFFIX}" if body.enhance_keywords else p
    logger.info("Text→3D 요청: %s", full[:240])

    if not (os.environ.get("REPLICATE_API_TOKEN") or "").strip():
        raise HTTPException(
            status_code=501,
            detail=(
                "텍스트→3D는 Replicate(클라우드)로 연결됩니다. "
                "엔진 실행 전 터미널에서: $env:REPLICATE_API_TOKEN='r8_...' "
                "그리고 TripoSR venv 에 pip install -r requirements-text3d.txt 후 서버 재시작. "
                "토큰: https://replicate.com/account/api-tokens"
            ),
        )

    async with generation_slot():
        try:
            glb_bytes = await asyncio.to_thread(run_replicate_text_to_glb, full)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Text→3D 실패")
            raise HTTPException(
                status_code=503,
                detail=f"{type(e).__name__}: {e}",
            ) from e

    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={
            "Content-Disposition": 'inline; filename="origin-real-text.glb"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/generate/texture")
async def generate_texture(
    model: UploadFile = File(...),
    instructions: str = Form(""),
):
    if not model.filename:
        raise HTTPException(status_code=400, detail="model(GLB) 파일이 필요합니다.")
    raw = await model.read()
    if len(raw) < 12:
        raise HTTPException(status_code=400, detail="파일이 너무 작습니다.")
    if raw[:4] != b"glTF":
        raise HTTPException(
            status_code=400,
            detail="GLB 바이너리가 아닙니다. (헤더 magic glTF 필요)",
        )
    hint = (instructions or "").strip()[:200]
    logger.info(
        "Texture 요청 (스텁): %d bytes, instructions=%s",
        len(raw),
        hint or "(없음)",
    )
    raise HTTPException(
        status_code=501,
        detail=(
            "AI Texture 파이프라인이 아직 연결되지 않았습니다. "
            "텍스처 재생성·프롬프트 기반 머티리얼은 별도 서브그래프를 연동하세요."
        ),
    )


if __name__ == "__main__":
    # start-engine.ps1 / npm run engine 과 .env.local TRIPOSR_URL 기본(8001)과 맞춤
    port = int(os.environ.get("PORT", "8001"))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info("uvicorn http://%s:%s (Origin Real → POST /generate)", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
