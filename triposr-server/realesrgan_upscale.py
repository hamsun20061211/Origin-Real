"""
TripoSR 3D 입력 직전 Real-ESRGAN 2배 업스케일 (CUDA + FP16 권장).

BasicSR 구버전은 torchvision>=0.17 에서 제거된 `functional_tensor` 를 import 하므로,
import 전에 호환 shim 을 넣습니다.
"""

from __future__ import annotations

import logging
import os
import sys
import types
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger("origin_real.triposr.realesrgan")

_THIS = Path(__file__).resolve().parent
_WEIGHTS_DIR = _THIS / "weights"
_DEFAULT_CKPT = _WEIGHTS_DIR / "RealESRGAN_x2plus.pth"
_CKPT_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"

_upsampler: object | None = None


def enabled(default_on_cuda: bool = True) -> bool:
    v = (os.environ.get("TRIPOSR_REALESRGAN") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    if not default_on_cuda:
        return False
    import torch

    return bool(torch.cuda.is_available())


def upsampler_loaded() -> bool:
    return _upsampler is not None


def _ensure_torchvision_shim() -> None:
    name = "torchvision.transforms.functional_tensor"
    if name in sys.modules:
        return
    try:
        import torchvision.transforms.functional as TVF
    except ImportError:
        return
    m = types.ModuleType(name)
    m.rgb_to_grayscale = TVF.rgb_to_grayscale
    sys.modules[name] = m


def _ensure_weights(path: Path = _DEFAULT_CKPT) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 1_000_000:
        return str(path)
    logger.info("Real-ESRGAN weights download: %s", path.name)
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        urllib.request.urlretrieve(_CKPT_URL, str(tmp))
        tmp.replace(path)
    except Exception:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise
    return str(path)


def _import_rrdb_and_inferencer():
    _ensure_torchvision_shim()
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    return RRDBNet, RealESRGANer


def get_upsampler(*, device: str) -> object:
    global _upsampler
    if _upsampler is not None:
        return _upsampler
    import torch

    RRDBNet, RealESRGANer = _import_rrdb_and_inferencer()
    weights_env = (os.environ.get("TRIPOSR_REALESRGAN_WEIGHTS") or "").strip()
    model_path = str(Path(weights_env).expanduser()) if weights_env else _ensure_weights()

    tile = int(os.environ.get("TRIPOSR_REALESRGAN_TILE", "0") or 0)
    tile_pad = int(os.environ.get("TRIPOSR_REALESRGAN_TILE_PAD", "10") or 10)
    pre_pad = int(os.environ.get("TRIPOSR_REALESRGAN_PRE_PAD", "0") or 0)
    use_cuda = str(device).startswith("cuda") and torch.cuda.is_available()
    dev = torch.device(device if use_cuda else "cpu")
    half = use_cuda and (os.environ.get("TRIPOSR_REALESRGAN_FP16", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )

    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
    _upsampler = RealESRGANer(
        scale=2,
        model_path=model_path,
        model=model,
        tile=tile,
        tile_pad=tile_pad,
        pre_pad=pre_pad,
        half=half,
        device=dev,
        gpu_id=None,
    )
    logger.info(
        "Real-ESRGAN x2plus loaded (tile=%s pre_pad=%s half=%s device=%s)",
        tile,
        pre_pad,
        half,
        dev,
    )
    return _upsampler


def preload_if_requested(*, device: str) -> None:
    if (os.environ.get("TRIPOSR_REALESRGAN_PRELOAD") or "").strip().lower() not in ("1", "true", "yes", "on"):
        return
    if not enabled():
        return
    if not str(device).startswith("cuda"):
        return
    try:
        get_upsampler(device=device)
        logger.info("Real-ESRGAN preload done")
    except Exception:
        logger.exception("Real-ESRGAN preload failed — will retry on first request")


def maybe_upscale_before_triposr(pil: Image.Image, *, device: str) -> Image.Image:
    if not enabled():
        return pil
    cpu_ok = (os.environ.get("TRIPOSR_REALESRGAN_CPU") or "").strip().lower() in ("1", "true", "yes", "on")
    if not str(device).startswith("cuda") and not cpu_ok:
        return pil

    try:
        upsampler = get_upsampler(device=device)
    except Exception as e:
        logger.warning("Real-ESRGAN init failed — skipping upscale: %s", e)
        return pil

    outscale = float(os.environ.get("TRIPOSR_REALESRGAN_OUTSCALE", "2") or 2)
    arr = np.asarray(pil.convert("RGB"), dtype=np.uint8)
    img_bgr = arr[:, :, ::-1].copy()

    import torch

    try:
        output, _ = upsampler.enhance(img_bgr, outscale=outscale)
    except Exception:
        logger.exception("Real-ESRGAN enhance failed — using original image")
        return pil
    finally:
        if (os.environ.get("TRIPOSR_REALESRGAN_EMPTY_CACHE", "1") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        ):
            if torch.cuda.is_available() and str(device).startswith("cuda"):
                try:
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                except Exception:
                    pass

    out_rgb = np.ascontiguousarray(output[:, :, ::-1])
    return Image.fromarray(out_rgb, mode="RGB")
