"""
Modern Building 등 키워드로 이미지 URL 수집 → 다운로드 → rembg 배경 제거 → PNG 저장.

출처 (--source):
  - pexels   : PEXELS_API_KEY  (Pexels 라이선스 — CC0 아님)
  - unsplash : UNSPLASH_ACCESS_KEY (Unsplash 라이선스 — CC0 아님)
  - openverse: API 키 불필요(익명 할당량). Creative Commons 카탈로그

--license cc0:
  CC0·Public Domain Mark(pdm) 메타데이터만 Openverse에서 가져옵니다.
  Pexels/Unsplash는 작품별 CC0 태그를 API로 주지 않으므로, 이 옵션일 때는
  자동으로 Openverse만 사용합니다.

사용 예:
  $env:PEXELS_API_KEY="..."
  python collect_images.py --source pexels --query "Modern Building" --max 25

  python collect_images.py --license cc0 --query "Modern Building" --max 25
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx
from rembg import remove

# Openverse 공개 API (익명: burst 20/min, sustained 200/day 수준 — 변경될 수 있음)
OPENVERSE_IMAGES = "https://api.openverse.engineering/v1/images/"

USER_AGENT = (
    "OriginRealImageCollector/1.0 (educational; contact: local) "
    "Python-httpx; +https://github.com/WordPress/openverse"
)


def fetch_pexels_image_urls(client: httpx.Client, query: str, need: int) -> list[str]:
    key = (os.environ.get("PEXELS_API_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "PEXELS_API_KEY 가 없습니다. https://www.pexels.com/api/ 에서 발급 후 설정하세요."
        )
    out: list[str] = []
    page_n = 1
    while len(out) < need and page_n <= 10:
        r = client.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": min(80, max(need - len(out), 15)), "page": page_n},
            headers={"Authorization": key},
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        for ph in data.get("photos") or []:
            src = ph.get("src") or {}
            url = src.get("large2x") or src.get("large") or src.get("original")
            if url:
                out.append(url)
        if not data.get("photos"):
            break
        page_n += 1
    return out


def fetch_unsplash_image_urls(client: httpx.Client, query: str, need: int) -> list[str]:
    key = (os.environ.get("UNSPLASH_ACCESS_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "UNSPLASH_ACCESS_KEY 가 없습니다. https://unsplash.com/developers 에서 발급 후 설정하세요."
        )
    out: list[str] = []
    page_n = 1
    while len(out) < need and page_n <= 10:
        r = client.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": min(30, max(need - len(out), 10)), "page": page_n},
            headers={"Authorization": f"Client-ID {key}"},
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        for item in data.get("results") or []:
            urls = item.get("urls") or {}
            url = urls.get("regular") or urls.get("full")
            if url:
                out.append(url)
        if not data.get("results"):
            break
        page_n += 1
    return out


def fetch_openverse_image_urls(
    client: httpx.Client,
    query: str,
    need: int,
    *,
    cc0_only: bool,
) -> tuple[list[str], list[dict[str, object]]]:
    """Openverse에서 이미지 URL과 메타(출처·라이선스) 목록 반환."""
    out_urls: list[str] = []
    meta_rows: list[dict[str, object]] = []
    page = 1
    page_size = min(100, max(need, 20))

    while len(out_urls) < need and page <= 30:
        params: dict[str, str | int] = {
            "q": query,
            "page": page,
            "page_size": page_size,
        }
        if cc0_only:
            # CC0 + Public Domain Mark (저작권 상 퍼블릭 도메인에 가까운 풀)
            params["license"] = "cc0,pdm"

        r = client.get(
            OPENVERSE_IMAGES,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        batch = data.get("results") or []
        if not batch:
            break
        for item in batch:
            url = item.get("url")
            if isinstance(url, str) and url.startswith("http"):
                out_urls.append(url)
                meta_rows.append(
                    {
                        "title": item.get("title"),
                        "creator": item.get("creator"),
                        "license": item.get("license"),
                        "license_url": item.get("license_url"),
                        "foreign_landing_url": item.get("foreign_landing_url"),
                        "attribution": item.get("attribution"),
                    }
                )
            if len(out_urls) >= need:
                break
        page += 1

    return out_urls[:need], meta_rows[:need]


def download_image(client: httpx.Client, url: str, timeout: float, referer: str | None) -> bytes | None:
    try:
        headers: dict[str, str] = {"User-Agent": USER_AGENT}
        if referer:
            headers["Referer"] = referer
        r = client.get(url, timeout=timeout, follow_redirects=True, headers=headers)
        if r.status_code != 200:
            return None
        ct = (r.headers.get("content-type") or "").lower()
        if "image" not in ct and "octet-stream" not in ct:
            if len(r.content) < 500:
                return None
        if len(r.content) < 800:
            return None
        return r.content
    except Exception:
        return None


def safe_stem(prefix: str, n: int) -> str:
    return f"{prefix}_{n:03d}.png"


def referer_for_effective_source(src: str) -> str | None:
    if src == "pexels":
        return "https://www.pexels.com/"
    if src == "unsplash":
        return "https://unsplash.com/"
    return None


def run(
    out_dir: Path,
    source: str,
    license_mode: str,
    query: str,
    prefix: str,
    max_images: int,
    download_delay: float,
    dry_run: bool,
    save_attribution: bool,
) -> None:
    cc0_only = license_mode == "cc0"
    effective = source

    if cc0_only:
        if source in ("pexels", "unsplash"):
            print(
                "\n[안내] --license cc0 는 Pexels/Unsplash API에 CC0 메타데이터가 없어 "
                "Openverse(CC0·PDM)로 전환합니다.\n",
                flush=True,
            )
        effective = "openverse"

    need_urls = max_images * 4
    out_dir.mkdir(parents=True, exist_ok=True)
    seen_raw: set[str] = set()
    seen_png: set[str] = set()
    ref = referer_for_effective_source(effective)

    meta_by_index: list[dict[str, object]] = []

    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        if effective == "pexels":
            urls = fetch_pexels_image_urls(client, query, need_urls)
        elif effective == "unsplash":
            urls = fetch_unsplash_image_urls(client, query, need_urls)
        elif effective == "openverse":
            urls, meta_by_index = fetch_openverse_image_urls(
                client, query, need_urls, cc0_only=cc0_only
            )
        else:
            raise SystemExit(f"알 수 없는 source: {effective}")

        print(f"\n=== 검색어: {query!r} | 실제 출처: {effective} | CC0만: {cc0_only} ===", flush=True)
        print(f"  URL 후보: {len(urls)}", flush=True)

        n_saved = 0
        for i, url in enumerate(urls):
            if n_saved >= max_images:
                break
            time.sleep(download_delay)
            raw = download_image(client, url, timeout=45.0, referer=ref)
            if not raw:
                continue
            rh = hashlib.sha256(raw).hexdigest()
            if rh in seen_raw:
                continue

            if dry_run:
                seen_raw.add(rh)
                print(f"  [dry-run] {safe_stem(prefix, n_saved + 1)} ({len(raw)} bytes)")
                n_saved += 1
                continue

            try:
                png = remove(raw)
            except Exception as e:
                print(f"  rembg skip: {e}", flush=True)
                continue

            ph = hashlib.sha256(png).hexdigest()
            if ph in seen_png:
                continue
            seen_raw.add(rh)
            seen_png.add(ph)

            n_saved += 1
            name = safe_stem(prefix, n_saved)
            path = out_dir / name
            path.write_bytes(png)
            print(f"  저장 {name} ({len(png)} bytes)", flush=True)

            if save_attribution and effective == "openverse" and i < len(meta_by_index):
                stem = f"{prefix}_{n_saved:03d}"
                meta_path = out_dir / f"{stem}.attribution.json"
                meta_path.write_text(
                    json.dumps(meta_by_index[i], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    print(f"\n완료. 출력: {out_dir.resolve()}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Pexels / Unsplash / Openverse 이미지 수집 + rembg"
    )
    ap.add_argument(
        "--source",
        choices=("pexels", "unsplash", "openverse"),
        default="pexels",
        help="이미지 API (기본 pexels)",
    )
    ap.add_argument(
        "--license",
        dest="license_mode",
        choices=("all", "cc0"),
        default="all",
        help="cc0: Openverse에서 CC0+PDM만. all: --source 정책 따름 (Pexels/Unsplash는 각 사 라이선스)",
    )
    ap.add_argument(
        "--query",
        default="Modern Building",
        help='검색어 (기본: "Modern Building")',
    )
    ap.add_argument(
        "--prefix",
        default="building",
        help="저장 파일 접두어 (기본 building → building_001.png)",
    )
    ap.add_argument(
        "--max",
        type=int,
        default=20,
        dest="max_images",
        help="최대 저장 개수",
    )
    ap.add_argument(
        "--per-topic",
        type=int,
        default=None,
        dest="max_images_legacy",
        help=argparse.SUPPRESS,
    )
    ap.add_argument("--delay", type=float, default=0.35, help="다운로드 간 딜레이(초)")
    ap.add_argument("--dry-run", action="store_true", help="rembg/저장 생략(바이트만 확인)")
    ap.add_argument(
        "--save-attribution",
        action="store_true",
        help="Openverse 사용 시 각 이미지 옆에 .attribution.json 저장",
    )
    ap.add_argument("--out", type=Path, default=Path("./collected_images"), help="출력 폴더")

    args = ap.parse_args()
    max_images = (
        args.max_images_legacy if args.max_images_legacy is not None else args.max_images
    )

    try:
        run(
            out_dir=args.out,
            source=args.source,
            license_mode=args.license_mode,
            query=args.query.strip(),
            prefix=args.prefix.strip() or "image",
            max_images=max_images,
            download_delay=args.delay,
            dry_run=args.dry_run,
            save_attribution=args.save_attribution,
        )
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
