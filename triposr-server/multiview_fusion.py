"""
Multi-view 이미지를 단일 TripoSR 입력으로 융합 (알파 페더 + 경계 블렌딩).
Hunyuan3D / MVDream 등은 별도 대규모 스택이 필요해 이 레이어에서는 TripoSR 호환 융합만 제공합니다.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import numpy as np
from PIL import Image

logger = logging.getLogger("origin_real.triposr.fusion")


def _fusion_canvas() -> int:
    """요청마다 읽어 OR_QUALITY 프리셋(서버 기동 후 적용)이 반영되게 함."""
    return max(512, int(os.environ.get("OR_FUSION_CANVAS", "1024")))


def _np_rgb(pil: Image.Image) -> np.ndarray:
    return np.asarray(pil.convert("RGB"), dtype=np.float32) / 255.0


def _to_pil(arr: np.ndarray) -> Image.Image:
    a = np.clip(arr, 0.0, 1.0)
    return Image.fromarray((a * 255.0).astype(np.uint8))


def _feather_mask(h: int, w: int, mode: str) -> np.ndarray:
    """mode: center | left | right | top | bottom — 부드러운 알파."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = xx / max(w - 1, 1)
    ny = yy / max(h - 1, 1)
    if mode == "center":
        cx, cy = 0.5, 0.5
        d = np.sqrt((nx - cx) ** 2 + (ny - cy) ** 2) / 0.707
        m = np.cos(np.clip(d * 1.15, 0, 1) * (np.pi / 2)) ** 2
    elif mode == "left":
        m = np.cos(np.clip((1.0 - nx) * (np.pi / 2), 0, np.pi / 2)) ** 2
    elif mode == "right":
        m = np.cos(np.clip(nx * (np.pi / 2), 0, np.pi / 2)) ** 2
    elif mode == "top":
        m = np.cos(np.clip((1.0 - ny) * (np.pi / 2), 0, np.pi / 2)) ** 2
    else:  # bottom
        m = np.cos(np.clip(ny * (np.pi / 2), 0, np.pi / 2)) ** 2
    return np.clip(m, 0.0, 1.0)[..., None]


def _resize_cover(img: Image.Image, tw: int, th: int) -> Image.Image:
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    r = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x0 = (nw - tw) // 2
    y0 = (nh - th) // 2
    return r.crop((x0, y0, x0 + tw, y0 + th))


def seamless_fuse_multiview(
    front: Image.Image,
    back: Optional[Image.Image] = None,
    left: Optional[Image.Image] = None,
    right: Optional[Image.Image] = None,
    canvas: int | None = None,
) -> Image.Image:
    """
    정면을 중심에 두고 좌/우/후면을 스트립으로 부드럽게 합성.
    경계는 코사인 알파로 블렌딩 (seamless feather).
    """
    s = canvas if canvas is not None else _fusion_canvas()
    base = np.ones((s, s, 3), dtype=np.float32) * 0.5

    # 중앙 정면 (~62% 폭)
    cw = int(s * 0.62)
    ch = int(s * 0.88)
    fx0 = (s - cw) // 2
    fy0 = (s - ch) // 2
    f_crop = _resize_cover(front, cw, ch)
    fn = _np_rgb(f_crop)
    fm = _feather_mask(ch, cw, "center")
    region = base[fy0 : fy0 + ch, fx0 : fx0 + cw]
    base[fy0 : fy0 + ch, fx0 : fx0 + cw] = region * (1 - fm) + fn * fm

    side_w = (s - cw) // 2 - 4
    side_h = ch - 8
    if side_w < 24:
        logger.info("Multi-view fusion: 캔버스 대비 측면 공간 부족 — 정면만 사용")
        return _to_pil(base)

    def paste_side(pil_side: Optional[Image.Image], x0: int, feather: str) -> None:
        if pil_side is None:
            return
        sc = _resize_cover(pil_side, side_w, side_h)
        sn = _np_rgb(sc)
        sm = _feather_mask(side_h, side_w, feather)
        sl = base[fy0 + 4 : fy0 + 4 + side_h, x0 : x0 + side_w]
        base[fy0 + 4 : fy0 + 4 + side_h, x0 : x0 + side_w] = sl * (1 - sm) + sn * sm

    paste_side(left, 2, "left")
    paste_side(right, fx0 + cw + 2, "right")

    # 후면: 상단 띠
    if back is not None:
        bh = int(s * 0.18)
        bw = cw + 2 * side_w + 4
        bx0 = (s - bw) // 2
        b_crop = _resize_cover(back, bw, bh)
        bn = _np_rgb(b_crop)
        bm = _feather_mask(bh, bw, "top")
        strip = base[2 : 2 + bh, bx0 : bx0 + bw]
        base[2 : 2 + bh, bx0 : bx0 + bw] = strip * (1 - bm) + bn * bm

    logger.info(
        "Multi-view seamless fusion 완료 (%dx%d) | sides L=%s R=%s B=%s",
        s,
        s,
        bool(left),
        bool(right),
        bool(back),
    )
    return _to_pil(base)


def collect_view_images(
    views: Dict[str, Optional[bytes]],
) -> tuple[Image.Image, Dict[str, Optional[Image.Image]]]:
    import io

    front_raw = views.get("front")
    if not front_raw:
        raise ValueError("정면(front) 이미지가 필요합니다.")

    front = Image.open(io.BytesIO(front_raw)).convert("RGB")

    def dec(key: str) -> Optional[Image.Image]:
        b = views.get(key)
        if not b:
            return None
        return Image.open(io.BytesIO(b)).convert("RGB")

    return front, {
        "back": dec("back"),
        "left": dec("left"),
        "right": dec("right"),
    }
