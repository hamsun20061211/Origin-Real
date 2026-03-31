"""
이미지 분석 → 부품 후보 리스트 (SLIC 슈퍼픽셀 클러스터 + 수직 위치 기반 라벨).
SAM 가중치가 있으면 OR_ANALYZE_USE_SAM=1 과 segment_anything 패키지로 확장 가능 (현재는 경량 경로).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger("origin_real.triposr.analyze")


def _heuristic_parts(w: int, h: int, seed: int) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed & 0xFFFFFFFF)
    jitter = lambda v: float(np.clip(v + rng.normal(0, 0.02), 0.05, 0.95))
    return [
        {
            "id": "head",
            "label": "머리 / 상체 상단",
            "confidence": round(jitter(0.88), 2),
            "bbox_norm": [0.22, 0.04, 0.56, 0.30],
        },
        {
            "id": "torso",
            "label": "몸통 / 코어",
            "confidence": round(jitter(0.91), 2),
            "bbox_norm": [0.18, 0.28, 0.64, 0.38],
        },
        {
            "id": "arms",
            "label": "팔 / 장비 측면",
            "confidence": round(jitter(0.76), 2),
            "bbox_norm": [0.06, 0.32, 0.88, 0.42],
        },
        {
            "id": "legs",
            "label": "하체 / 다리",
            "confidence": round(jitter(0.83), 2),
            "bbox_norm": [0.20, 0.62, 0.60, 0.34],
        },
    ]


def _slic_parts(pil: Image.Image, n_seg: int = 48, k_groups: int = 5, seed: int = 0) -> list[dict[str, Any]]:
    try:
        from skimage.segmentation import slic
        from skimage.util import img_as_float
    except ImportError:
        logger.info("scikit-image 없음 — 휴리스틱 부품 목록 사용")
        return _heuristic_parts(pil.width, pil.height, seed)

    img = pil.resize((min(384, pil.width), min(384, pil.height)), Image.Resampling.LANCZOS)
    lab = np.asarray(img)
    # img_as_float 는 기본 float64 — VRAM/시스템 메모리가 빡빡할 때 실패하는 경우가 있어 float32 유지
    if lab.dtype == np.uint8:
        f = np.multiply(lab.astype(np.float32, copy=False), 1.0 / 255.0, dtype=np.float32)
    else:
        f = img_as_float(lab).astype(np.float32, copy=False)
    try:
        seg = slic(
            f, n_segments=n_seg, compactness=10.0, sigma=1, start_label=0, random_seed=seed
        )
    except TypeError:
        seg = slic(f, n_segments=n_seg, compactness=10.0, sigma=1, start_label=0)

    flat = seg.ravel()
    colors = f.reshape(-1, 3)
    unique = np.unique(flat)
    centroids_y = []
    centroids_x = []
    mean_cols = []
    for u in unique:
        m = flat == u
        idx = np.where(m)[0]
        ys, xs = np.unravel_index(idx, seg.shape)
        centroids_y.append(ys.mean() / seg.shape[0])
        centroids_x.append(xs.mean() / seg.shape[1])
        mean_cols.append(colors[idx].mean(axis=0))
    centroids_y = np.array(centroids_y)
    order = np.argsort(centroids_y)
    k = min(k_groups, len(order))
    step = max(1, len(order) // k)
    parts: list[dict[str, Any]] = []
    labels_ko = [
        ("head", "머리 / 상단 디테일"),
        ("upper", "상체 / 가슴·견갑"),
        ("core", "코어 / 장비 중심"),
        ("lower", "하체·골반"),
        ("base", "하단·발 쪽"),
    ]
    for i in range(k):
        chunk = order[i * step : (i + 1) * step if i < k - 1 else len(order)]
        if len(chunk) == 0:
            continue
        yc = centroids_y[chunk].mean()
        xc = np.array(centroids_x)[chunk].mean()
        spread_y = float(np.array(centroids_y)[chunk].max() - np.array(centroids_y)[chunk].min() + 0.15)
        spread_x = float(np.array(centroids_x)[chunk].max() - np.array(centroids_x)[chunk].min() + 0.2)
        bx = float(np.clip(xc - spread_x / 2, 0.02, 0.98))
        by = float(np.clip(yc - spread_y / 2, 0.02, 0.98))
        bw = float(np.clip(spread_x, 0.12, 0.9))
        bh = float(np.clip(spread_y, 0.1, 0.9))
        lid, lko = labels_ko[min(i, len(labels_ko) - 1)]
        conf = float(0.72 + 0.08 * (1.0 - i / max(k, 1)))
        parts.append(
            {
                "id": f"part_{lid}",
                "label": lko,
                "confidence": round(conf, 2),
                "bbox_norm": [bx, by, bw, bh],
            }
        )
    logger.info("SLIC 기반 부품 후보 %d개", len(parts))
    return parts


def analyze_image_parts(pil: Image.Image, seed: int = 0) -> dict[str, Any]:
    use_slic = os.environ.get("OR_ANALYZE_SLIC", "1").lower() in ("1", "true", "yes")
    if use_slic:
        parts = _slic_parts(pil, seed=seed)
    else:
        parts = _heuristic_parts(pil.width, pil.height, seed)
    return {
        "parts": parts,
        "image_size": {"w": pil.width, "h": pil.height},
        "method": "slic" if use_slic else "heuristic",
    }
