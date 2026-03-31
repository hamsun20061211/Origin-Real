#!/usr/bin/env python3
"""
Military gear image collector (Research-friendly)
------------------------------------------------
IMPORTANT / LEGAL NOTE
 - Google Images / Pinterest 자동 스크래핑은 서비스 약관(ToS)에 의해 제한될 수 있습니다.
 - 본 스크립트는 기본 제공 소스로 "Openverse"와 "Wikimedia Commons"만 사용합니다.
 - 라이선스 필터를 통해 상업적 이용 가능한 이미지(CC0/CC BY/CC BY-SA 등)를 우선 수집합니다.
 - 그래도 최종 사용 책임은 사용자에게 있으며, 각 이미지의 license_url / source_url을 검토하세요.

기능
 - 검색어(쿼리)별 이미지 다운로드
 - 카테고리별 저장: downloads/vest, downloads/helmet, downloads/gun
 - 최소 해상도 필터: 기본 1024x1024 이상만 저장
 - 배경 복잡도(단순도) 우선순위: edge density 기반
 - 메타데이터 기록: dataset_sources.jsonl (라이선스/출처/원본 URL/선정 점수)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image


ALLOWED_CATEGORIES = {"vest", "helmet", "gun"}


@dataclass(frozen=True)
class Candidate:
    provider: str
    title: str
    image_url: str
    source_url: str
    license: str | None
    license_url: str | None
    creator: str | None
    creator_url: str | None


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def safe_filename(stem: str, max_len: int = 120) -> str:
    stem = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem)
    stem = "_".join([p for p in stem.split("_") if p])[:max_len]
    return stem or "img"


def http_get_json(url: str, params: dict, timeout: float = 25.0) -> dict:
    r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "research-image-collector/1.0"})
    r.raise_for_status()
    return r.json()


def iter_openverse(query: str, page_size: int = 50, max_pages: int = 20, license_types: str = "commercial") -> Iterable[Candidate]:
    """
    Openverse API
    - license_types:
        - "commercial": 상업적 이용 가능(비상업 NC 제외)만
        - "all": 모두
    """
    base = "https://api.openverse.engineering/v1/images/"
    for page in range(1, max_pages + 1):
        data = http_get_json(
            base,
            params={
                "q": query,
                "page": page,
                "page_size": page_size,
                "license_type": license_types,
                "mature": "false",
            },
        )
        results = data.get("results") or []
        if not results:
            break
        for it in results:
            yield Candidate(
                provider="openverse",
                title=str(it.get("title") or ""),
                image_url=str(it.get("url") or ""),
                source_url=str(it.get("foreign_landing_url") or it.get("source") or it.get("url") or ""),
                license=str(it.get("license") or None),
                license_url=str(it.get("license_url") or None),
                creator=str(it.get("creator") or None),
                creator_url=str(it.get("creator_url") or None),
            )


def iter_wikimedia(query: str, limit: int = 50) -> Iterable[Candidate]:
    """
    Wikimedia Commons API (imageinfo)
    - license 정밀 필터는 복잡하므로, 여기서는 정보만 수집해 기록하고,
      실제 사용 단계에서 license_url 확인을 권장.
    """
    api = "https://commons.wikimedia.org/w/api.php"
    search = http_get_json(
        api,
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": str(limit),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": "4096",
        },
    )
    pages = ((search.get("query") or {}).get("pages") or {}).values()
    for p in pages:
        ii = (p.get("imageinfo") or [])
        if not ii:
            continue
        info = ii[0]
        meta = info.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value")
        lic_url = (meta.get("LicenseUrl") or {}).get("value")
        artist = (meta.get("Artist") or {}).get("value")
        desc_url = (meta.get("ImageDescription") or {}).get("value")
        yield Candidate(
            provider="wikimedia",
            title=str(p.get("title") or ""),
            image_url=str(info.get("thumburl") or info.get("url") or ""),
            source_url=str(info.get("descriptionshorturl") or info.get("descriptionurl") or ""),
            license=str(lic) if lic else None,
            license_url=str(lic_url) if lic_url else None,
            creator=str(artist) if artist else None,
            creator_url=str(desc_url) if desc_url else None,
        )


def download_image(url: str, timeout: float = 30.0) -> bytes | None:
    if not url:
        return None
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "research-image-collector/1.0"})
    if r.status_code != 200:
        return None
    ct = (r.headers.get("content-type") or "").lower()
    if "image" not in ct and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return None
    return r.content


def decode_image_bytes(raw: bytes) -> Image.Image | None:
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        return im.convert("RGBA")
    except Exception:
        return None


def edge_density_rgba(im: Image.Image) -> float:
    """
    배경 복잡도 프록시: 전체 엣지 밀도(낮을수록 단순).
    """
    import cv2
    import numpy as np

    arr = np.array(im)
    rgb = arr[:, :, :3]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, threshold1=80, threshold2=160)
    return float(edges.mean() / 255.0)


def center_crop_square(im: Image.Image) -> Image.Image:
    w, h = im.size
    s = min(w, h)
    x0 = (w - s) // 2
    y0 = (h - s) // 2
    return im.crop((x0, y0, x0 + s, y0 + s))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True, help="downloads 루트")
    p.add_argument("--min-size", type=int, default=1024)
    p.add_argument("--max-per-query", type=int, default=120)
    p.add_argument("--providers", nargs="+", default=["openverse", "wikimedia"], choices=["openverse", "wikimedia"])
    p.add_argument("--license-type", default="commercial", choices=["commercial", "all"], help="Openverse license_type")
    p.add_argument("--bg-simple-threshold", type=float, default=0.055, help="edge density 상한(낮을수록 더 엄격)")
    p.add_argument("--sleep", type=float, default=0.25)
    p.add_argument("--query", action="append", default=[], help="여러 번 지정 가능")
    p.add_argument("--category", action="append", default=[], help="query와 동일 개수로 지정 (vest/helmet/gun)")
    args = p.parse_args()

    if len(args.query) != len(args.category):
        print("--query와 --category 개수가 같아야 합니다.", file=sys.stderr)
        return 2
    for c in args.category:
        if c not in ALLOWED_CATEGORIES:
            print("category는 vest/helmet/gun 중 하나:", c, file=sys.stderr)
            return 2

    try:
        import cv2  # noqa: F401
    except Exception as e:
        print("필터(배경 복잡도) 계산에 OpenCV가 필요합니다: pip install opencv-python", e, file=sys.stderr)
        return 2

    out_root: Path = args.out
    out_root.mkdir(parents=True, exist_ok=True)
    meta_path = out_root / "dataset_sources.jsonl"

    saved_total = 0
    for q, cat in zip(args.query, args.category):
        cat_dir = out_root / cat
        cat_dir.mkdir(parents=True, exist_ok=True)
        saved = 0

        providers = []
        if "openverse" in args.providers:
            providers.append(("openverse", iter_openverse(q, license_types=args.license_type)))
        if "wikimedia" in args.providers:
            providers.append(("wikimedia", iter_wikimedia(q)))

        for _, it in providers:
            for cand in it:
                if saved >= args.max_per_query:
                    break
                time.sleep(max(0.0, float(args.sleep)))

                raw = download_image(cand.image_url)
                if raw is None:
                    continue
                im = decode_image_bytes(raw)
                if im is None:
                    continue
                w, h = im.size
                if w < args.min_size or h < args.min_size:
                    continue

                # 배경 단순도 우선: threshold 이하면 통과
                ed = edge_density_rgba(im)
                if ed > float(args.bg_simple_threshold):
                    continue

                # 저장: 정사각 crop + 1024+ 유지 (리사이즈는 최소화)
                crop = center_crop_square(im)
                if crop.size[0] < args.min_size:
                    continue
                # 너무 큰 경우만 downscale(품질 유지)
                if crop.size[0] > 2048:
                    crop = crop.resize((2048, 2048), Image.Resampling.LANCZOS)

                stem = safe_filename(f"{cat}_{cand.provider}_{sha1(cand.image_url)[:10]}")
                out_file = cat_dir / f"{stem}.png"
                crop.save(out_file, format="PNG", compress_level=6)

                meta = {
                    "category": cat,
                    "query": q,
                    "provider": cand.provider,
                    "title": cand.title,
                    "saved_path": str(out_file.resolve().as_posix()),
                    "width": w,
                    "height": h,
                    "edge_density": ed,
                    "image_url": cand.image_url,
                    "source_url": cand.source_url,
                    "license": cand.license,
                    "license_url": cand.license_url,
                    "creator": cand.creator,
                    "creator_url": cand.creator_url,
                }
                meta_path.open("a", encoding="utf-8").write(json.dumps(meta, ensure_ascii=False) + "\n")
                saved += 1
                saved_total += 1

        print(f"[OK] {cat}: '{q}' saved {saved}")

    print("총 저장:", saved_total, "메타:", meta_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

