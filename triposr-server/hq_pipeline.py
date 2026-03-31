"""
Origin Real — 하이브리드 HQ 파이프라인 (텍스처 4x 업스케일 + DINOv2 기반 형태 선명화 + 2K PBR 베이크).
선택 의존성: requirements-hq.txt (realesrgan, basicsr). 없으면 Lanczos 폴백.
"""

from __future__ import annotations

import gc
import logging
import os
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
import trimesh
from PIL import Image

if TYPE_CHECKING:
    pass

logger = logging.getLogger("origin_real.triposr.hq")

# -----------------------------------------------------------------------------
# 환경 변수
# -----------------------------------------------------------------------------
def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def hq_pipeline_enabled() -> bool:
    return _env_bool("OR_HQ_PIPELINE", True)


def hq_esrgan_enabled() -> bool:
    return _env_bool("OR_HQ_ESRGAN", True)


def hq_dino_enabled() -> bool:
    return _env_bool("OR_HQ_DINO", True)


def texture_bake_resolution() -> int:
    return max(512, int(os.environ.get("OR_TEXTURE_BAKE_RES", "2048")))


def max_upscaled_side() -> int:
    return max(512, int(os.environ.get("OR_MAX_UPSCALED_SIDE", "2048")))


# -----------------------------------------------------------------------------
# 메모리
# -----------------------------------------------------------------------------
def clear_torch_memory(device: str) -> None:
    gc.collect()
    if device.startswith("cuda") and torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def release_hq_models() -> None:
    """HQ 보조 모델(DINOv2, Real-ESRGAN) 언로드 — 서버 종료 시 VRAM 회수."""
    global _DINO_MODEL, _REALESRGANER, _REALESRGAN_WEIGHTS
    _DINO_MODEL = None
    _REALESRGANER = None
    _REALESRGAN_WEIGHTS = None


# -----------------------------------------------------------------------------
# Real-ESRGAN (lazy)
# -----------------------------------------------------------------------------
_REALESRGANER = None
_REALESRGAN_WEIGHTS: Path | None = None

_REALESRGAN_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
)


def _default_weights_path() -> Path:
    base = Path(os.environ.get("OR_HQ_CACHE", Path.home() / ".cache" / "origin_real_hq"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "RealESRGAN_x4plus.pth"


def _ensure_realesrgan_weights(path: Path) -> Path:
    if path.is_file():
        return path
    logger.info("Real-ESRGAN 가중치 다운로드 중: %s", _REALESRGAN_URL)
    urllib.request.urlretrieve(_REALESRGAN_URL, path)  # noqa: S310
    return path


def _get_realesrganer(device: str):
    global _REALESRGANER, _REALESRGAN_WEIGHTS
    if _REALESRGANER is not None:
        return _REALESRGANER

    try:
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
    except ImportError as e:
        logger.warning("Real-ESRGAN 미설치 — Lanczos 4x 폴백 (%s)", e)
        return None

    wpath = Path(os.environ.get("REALESRGAN_WEIGHTS", _default_weights_path()))
    wpath = _ensure_realesrgan_weights(wpath)

    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
        scale=4,
    )
    tile = int(os.environ.get("OR_ESRGAN_TILE", "0"))
    half = _env_bool("OR_ESRGAN_FP16", False) and device.startswith("cuda")

    _REALESRGANER = RealESRGANer(
        scale=4,
        model_path=str(wpath),
        dni_weight=None,
        model=model,
        tile=tile,
        tile_pad=10,
        pre_pad=0,
        half=half,
        device=torch.device(device),
    )
    _REALESRGAN_WEIGHTS = wpath
    logger.info("Real-ESRGAN x4plus 로드 완료 (%s)", device)
    return _REALESRGANER


def _lanczos_4x(pil: Image.Image) -> Image.Image:
    w, h = pil.size
    return pil.resize((w * 4, h * 4), Image.Resampling.LANCZOS)


def upscale_texture_4x(pil: Image.Image, device: str) -> Image.Image:
    """텍스처 전용 4배 업스케일 (Real-ESRGAN v1.4 계열 x4plus)."""
    arr_in = np.array(pil.convert("RGB"), dtype=np.uint8)
    upsampler = _get_realesrganer(device) if hq_esrgan_enabled() else None
    if upsampler is None:
        out = _lanczos_4x(pil)
        logger.info('Texture Scaled ( 4x )... Done [fallback: Lanczos]')
        return out

    try:
        out_arr, _ = upsampler.enhance(arr_in, outscale=4)
        clear_torch_memory(device)
        logger.info('Texture Scaled ( 4x )... Done [Real-ESRGAN x4plus]')
        return Image.fromarray(out_arr.astype(np.uint8))
    except Exception:
        logger.exception("Real-ESRGAN 실패 — Lanczos 폴백")
        clear_torch_memory(device)
        out = _lanczos_4x(pil)
        logger.info('Texture Scaled ( 4x )... Done [fallback: Lanczos]')
        return out


# -----------------------------------------------------------------------------
# DINOv2 — 패치 특징 변화량 기반 형태/경계 강조
# -----------------------------------------------------------------------------
_DINO_MODEL = None
_DINO_NAME = os.environ.get("OR_DINO_MODEL", "dinov2_vits14")


def _get_dinov2(device: str):
    global _DINO_MODEL
    if _DINO_MODEL is not None:
        return _DINO_MODEL
    try:
        _DINO_MODEL = torch.hub.load("facebookresearch/dinov2", _DINO_NAME, pretrained=True)
    except Exception:
        logger.exception("DINOv2 torch.hub 로드 실패")
        return None
    _DINO_MODEL = _DINO_MODEL.to(device)
    _DINO_MODEL.eval()
    logger.info("DINOv2 로드: %s (%s)", _DINO_NAME, device)
    return _DINO_MODEL


def _gaussian_blur_rgb(img: np.ndarray, sigma: float) -> np.ndarray:
    try:
        import cv2

        return cv2.GaussianBlur(img, (0, 0), sigmaX=sigma, sigmaY=sigma)
    except ImportError:
        try:
            from scipy.ndimage import gaussian_filter

            return np.stack(
                [gaussian_filter(img[:, :, c], sigma) for c in range(3)],
                axis=-1,
            )
        except ImportError:
            from PIL import ImageFilter

            p = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
            p = p.filter(ImageFilter.GaussianBlur(radius=max(1, int(sigma))))
            return np.asarray(p).astype(np.float32) / 255.0


def enhance_geometry_dinov2(pil: Image.Image, device: str) -> Image.Image:
    """DINOv2 패치 특징의 공간적 변화(경계)를 이용해 고주파 형태 디테일을 강화."""
    if not hq_dino_enabled():
        logger.info("Geometry Optimized ( 선명화 )... Done [skipped OR_HQ_DINO=0]")
        return pil

    model = _get_dinov2(device)
    if model is None:
        logger.info("Geometry Optimized ( 선명화 )... Done [DINO unavailable]")
        return pil

    strength = float(os.environ.get("OR_DINO_SHARPEN_STRENGTH", "0.38"))
    w, h = pil.size
    side = min(518, max(w, h))
    side = max(14, (int(side) // 14) * 14)

    try:
        import torchvision.transforms as T

        tfm = T.Compose(
            [
                T.Resize((side, side), interpolation=T.InterpolationMode.BICUBIC),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )
        x = tfm(pil.convert("RGB")).unsqueeze(0).to(device)
        with torch.no_grad():
            feats = model.get_intermediate_layers(x, n=1, reshape=True, norm=True)[0]
            # (B, C, H, W)
            f = feats[0].mean(dim=0)
            gx = torch.abs(f[1:, :] - f[:-1, :])
            gy = torch.abs(f[:, 1:] - f[:, :-1])
            gx = torch.nn.functional.pad(gx, (0, 0, 0, 1))
            gy = torch.nn.functional.pad(gy, (0, 1, 0, 0))
            sal = torch.sqrt(gx * gx + gy * gy + 1e-8)
            sal = (sal - sal.min()) / (sal.max() - sal.min() + 1e-8)
            sal = sal.unsqueeze(0).unsqueeze(0)
            sal_up = torch.nn.functional.interpolate(
                sal, size=(h, w), mode="bilinear", align_corners=False
            )
            sal_np = sal_up[0, 0].detach().cpu().numpy().astype(np.float32)

        base = np.array(pil).astype(np.float32) / 255.0
        blur = _gaussian_blur_rgb(base, sigma=1.6)
        high = base - blur
        boost = 1.0 + strength * sal_np[..., None]
        out = np.clip(base + boost * high * 0.55, 0.0, 1.0)
        clear_torch_memory(device)
        logger.info("Geometry Optimized ( 선명화 )... Done [DINOv2 %s]", _DINO_NAME)
        return Image.fromarray((out * 255.0).astype(np.uint8))
    except Exception:
        logger.exception("DINOv2 선명화 실패 — 원본 유지")
        clear_torch_memory(device)
        logger.info("Geometry Optimized ( 선명화 )... Done [error fallback]")
        return pil


def hybrid_enhance_for_triposr(pil: Image.Image, device: str) -> Image.Image:
    """
    1) Real-ESRGAN 4x (텍스처)
    2) DINOv2 경계 강조 (지오메트리)
    3) 최대 변 길이 클램프 (TripoSR 내부 리사이즈 전 초해상 입력)
    """
    if not hq_pipeline_enabled():
        return pil

    img = upscale_texture_4x(pil, device)
    img = enhance_geometry_dinov2(img, device)

    max_side = max_upscaled_side()
    iw, ih = img.size
    if max(iw, ih) > max_side:
        scale = max_side / max(iw, ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        logger.info("OR_MAX_UPSCALED_SIDE 적용: %dx%d", nw, nh)

    return img


# -----------------------------------------------------------------------------
# 2K+ 텍스처 베이크 (xatlas UV + Z-buffer 라스터)
# -----------------------------------------------------------------------------
def _barycentric(px, py, ax, ay, bx, by, cx, cy):
    v0x, v0y = bx - ax, by - ay
    v1x, v1y = cx - ax, cy - ay
    v2x, v2y = px - ax, py - ay
    d00 = v0x * v0x + v0y * v0y
    d01 = v0x * v1x + v0y * v1y
    d11 = v1x * v1x + v1y * v1y
    d20 = v2x * v0x + v2y * v0y
    d21 = v2x * v1x + v2y * v1y
    denom = d00 * d11 - d01 * d01 + 1e-12
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    return u, v, w


def texture_bake_enabled() -> bool:
    return _env_bool("OR_TEXTURE_BAKE", True)


def bake_vertex_colors_to_texture_map(
    mesh: trimesh.Trimesh,
    resolution: int | None = None,
) -> trimesh.Trimesh:
    """
    버텍스 컬러 → xatlas UV + 2K(기본) 디퓨즈 맵 베이크.
    실패 시 원본 메쉬 반환.
    """
    if not texture_bake_enabled():
        return mesh

    res = resolution or texture_bake_resolution()
    if res < 512:
        res = 512

    max_faces = int(os.environ.get("OR_TEXTURE_BAKE_MAX_FACES", "80000"))
    if len(mesh.faces) > max_faces:
        logger.warning(
            "Face count %d > OR_TEXTURE_BAKE_MAX_FACES=%d — 베이크 생략 (버텍스 컬러 GLB 유지)",
            len(mesh.faces),
            max_faces,
        )
        return mesh

    try:
        import xatlas
    except ImportError:
        logger.warning("xatlas 없음 — PBR 텍스처 베이크 생략")
        return mesh

    if mesh.visual is None or mesh.visual.vertex_colors is None:
        logger.warning("버텍스 컬러 없음 — 베이크 생략")
        return mesh

    vc = np.asarray(mesh.visual.vertex_colors[:, :3], dtype=np.float32)
    if float(vc.max()) <= 1.0 + 1e-3:
        vc = np.clip(vc, 0.0, 1.0)
    else:
        vc = np.clip(vc / 255.0, 0.0, 1.0)
    verts = mesh.vertices.astype(np.float64)
    faces = mesh.faces.astype(np.int32)

    try:
        vmapping, indices, uvs = xatlas.parametrize(verts, faces)
    except Exception:
        logger.exception("xatlas.parametrize 실패 — 베이크 생략")
        return mesh

    new_verts = verts[vmapping]
    new_vc = vc[vmapping]
    new_uvs = uvs.astype(np.float64)
    # 삼각형별 깊이(평균 Z)로 UV 겹침 처리
    z_depth = new_verts[:, 2]

    tex = np.zeros((res, res, 3), dtype=np.float32)
    zbuf = np.full((res, res), -np.inf, dtype=np.float64)

    for tri in indices:
        ia, ib, ic = int(tri[0]), int(tri[1]), int(tri[2])
        ua, va = new_uvs[ia]
        ub, vb = new_uvs[ib]
        uc, vc_ = new_uvs[ic]
        ax, ay = ua * (res - 1), (1.0 - va) * (res - 1)
        bx, by = ub * (res - 1), (1.0 - vb) * (res - 1)
        cx, cy = uc * (res - 1), (1.0 - vc_) * (res - 1)
        z_tri = (z_depth[ia] + z_depth[ib] + z_depth[ic]) / 3.0
        ca, cb, cc = new_vc[ia], new_vc[ib], new_vc[ic]

        minx = int(max(0, np.floor(min(ax, bx, cx)) - 1))
        maxx = int(min(res - 1, np.ceil(max(ax, bx, cx)) + 1))
        miny = int(max(0, np.floor(min(ay, by, cy)) - 1))
        maxy = int(min(res - 1, np.ceil(max(ay, by, cy)) + 1))

        for py in range(miny, maxy + 1):
            for px in range(minx, maxx + 1):
                px_f = px + 0.5
                py_f = py + 0.5
                u, v, w = _barycentric(px_f, py_f, ax, ay, bx, by, cx, cy)
                if u < 0 or v < 0 or w < 0:
                    continue
                if z_tri <= zbuf[py, px]:
                    continue
                col = u * ca + v * cb + w * cc
                tex[py, px] = col
                zbuf[py, px] = z_tri

    tex_u8 = (np.clip(tex, 0, 1) * 255.0).astype(np.uint8)
    from trimesh.visual.material import PBRMaterial

    material = PBRMaterial(
        baseColorTexture=Image.fromarray(tex_u8),
        metallicFactor=0.05,
        roughnessFactor=0.65,
    )
    new_mesh = trimesh.Trimesh(
        vertices=new_verts,
        faces=indices,
        visual=trimesh.visual.TextureVisuals(uv=new_uvs, material=material),
        process=False,
    )
    logger.info("PBR diffuse bake 완료: %dx%d", res, res)
    return new_mesh
