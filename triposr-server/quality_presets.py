"""
OR_QUALITY 환경 변수로 마칭 큐브·텍스처 베이크·업스케일 상한 등을 한 번에 설정합니다.
이미 설정된 변수는 os.environ.setdefault 로 덮어쓰지 않습니다.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("origin_real.triposr.quality")

_PRESETS: dict[str, dict[str, str]] = {
    "balanced": {
        "TRIPOSR_MC_RESOLUTION": "384",
        "OR_TEXTURE_BAKE_RES": "2048",
        "OR_MAX_UPSCALED_SIDE": "2048",
        "OR_DINO_SHARPEN_STRENGTH": "0.38",
        "OR_FUSION_CANVAS": "1024",
    },
    "high": {
        "TRIPOSR_MC_RESOLUTION": "448",
        "OR_TEXTURE_BAKE_RES": "2560",
        "OR_MAX_UPSCALED_SIDE": "2560",
        "OR_DINO_SHARPEN_STRENGTH": "0.46",
        "OR_FUSION_CANVAS": "1152",
    },
    "ultra": {
        "TRIPOSR_MC_RESOLUTION": "512",
        "OR_TEXTURE_BAKE_RES": "3072",
        "OR_MAX_UPSCALED_SIDE": "2880",
        "OR_DINO_SHARPEN_STRENGTH": "0.52",
        "OR_FUSION_CANVAS": "1280",
    },
}


def apply_quality_preset() -> str | None:
    raw = os.environ.get("OR_QUALITY", "").strip().lower()
    if not raw or raw in ("0", "off", "custom"):
        return None
    if raw not in _PRESETS:
        logger.warning("OR_QUALITY=%s 는 알 수 없습니다. (balanced|high|ultra)", raw)
        return None
    for key, val in _PRESETS[raw].items():
        os.environ.setdefault(key, val)
    logger.info(
        "품질 프리셋 적용: OR_QUALITY=%s (mc=%s bake=%s upscale_max=%s fusion=%s)",
        raw,
        os.environ.get("TRIPOSR_MC_RESOLUTION"),
        os.environ.get("OR_TEXTURE_BAKE_RES"),
        os.environ.get("OR_MAX_UPSCALED_SIDE"),
        os.environ.get("OR_FUSION_CANVAS"),
    )
    return raw


def current_preset_label() -> str | None:
    v = os.environ.get("OR_QUALITY", "").strip().lower()
    return v if v and v in _PRESETS else None
