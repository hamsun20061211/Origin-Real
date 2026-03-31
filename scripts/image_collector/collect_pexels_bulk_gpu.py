"""
Pexels API(환경 변수 PEXELS_API_KEY)로 이미지 대량 수집 → rembg(GPU 우선) 배경 제거 → PNG 저장.

키워드 기본:
  - Modern Architecture → building_001.png …
  - Luxury Car         → car_001.png …

사용 (프로젝트 루트 Origin Real 에서):
  pip uninstall -y onnxruntime onnxruntime-gpu
  pip install -r scripts/image_collector/requirements-bulk-gpu.txt
  # 또는: pip install "rembg[gpu]"
  $env:PEXELS_API_KEY = "..."   # 이미 설정돼 있으면 생략
  python scripts/image_collector/collect_pexels_bulk_gpu.py --min-per-topic 500 --out data/raw

"No onnxruntime backend found" 가 나오면: 위 uninstall 후 rembg[gpu] 또는 rembg[cpu] 재설치.
GPU: CUDA 12.x 툴킷(cublasLt64_12.dll 등)이 PATH에 있어야 합니다. 없으면 ONNX가 에러를 내고,
  스크립트는 자동으로 CPU rembg로 바꿉니다. 처음부터 CPU만: --cpu 또는 REMBG_FORCE_CPU=1
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import time
from pathlib import Path

from PIL import Image

import httpx
from rembg import remove
from rembg.session_factory import new_session
from tqdm import tqdm


def _exit_if_no_onnxruntime() -> None:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        print(
            "onnxruntime 이 설치되어 있지 않습니다.\n"
            '  pip uninstall -y onnxruntime onnxruntime-gpu\n'
            '  pip install "rembg[gpu]"    # NVIDIA\n'
            '  pip install "rembg[cpu]"    # CPU만\n',
            file=sys.stderr,
        )
        sys.exit(1)

PEXELS_SEARCH = "https://api.pexels.com/v1/search"
USER_AGENT = "OriginReal-PexelsBulk/1.0"

# (파일 prefix, 검색어)
TOPICS: list[tuple[str, str]] = [
    ("building", "Modern Architecture"),
    ("car", "Luxury Car"),
]


def get_api_key() -> str:
    k = (os.environ.get("PEXELS_API_KEY") or "").strip()
    if not k:
        sys.exit("PEXELS_API_KEY 환경 변수를 설정하세요.")
    return k


def _tiny_png_bytes() -> bytes:
    img = Image.new("RGBA", (64, 64), (120, 80, 60, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_rembg_session(*, force_cpu: bool) -> object:
    """GPU 시도 후 추론 실패(예: cublasLt64_12.dll 없음) 시 CPU 세션으로 전환."""
    env_cpu = os.environ.get("REMBG_FORCE_CPU", "").strip().lower() in ("1", "true", "yes")
    if force_cpu or env_cpu:
        s = new_session("u2net", providers=["CPUExecutionProvider"])
        print("[rembg] 세션: CPU (--cpu 또는 REMBG_FORCE_CPU=1)", flush=True)
        return s

    try:
        s = new_session("u2net", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    except Exception as e:
        print(f"[rembg] GPU 세션 생성 실패 → CPU: {e}", flush=True)
        s = new_session("u2net", providers=["CPUExecutionProvider"])
        print("[rembg] 세션: CPU", flush=True)
        return s

    try:
        remove(_tiny_png_bytes(), session=s)
        print("[rembg] 세션: GPU(CUDA) (스모크 테스트 통과)", flush=True)
        return s
    except Exception as e:
        print(
            f"[rembg] GPU 추론 실패(CUDA DLL/드라이버 문제 가능) → CPU 전환: {e}",
            flush=True,
        )
        s = new_session("u2net", providers=["CPUExecutionProvider"])
        print("[rembg] 세션: CPU", flush=True)
        return s


def iter_pexels_photos(
    client: httpx.Client,
    api_key: str,
    query: str,
    min_photos: int,
) -> list[tuple[int, str]]:
    """(photo_id, image_url) 목록. min_photos 이상 확보 시도."""
    out: list[tuple[int, str]] = []
    seen_ids: set[int] = set()
    page = 1
    per_page = 80

    while len(out) < min_photos:
        r = client.get(
            PEXELS_SEARCH,
            params={"query": query, "per_page": per_page, "page": page},
            headers={"Authorization": api_key},
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        photos = data.get("photos") or []
        if not photos:
            print(f"  [pexels] 더 없음 (page={page}, 누적 {len(out)}장)", flush=True)
            break
        for ph in photos:
            pid = int(ph["id"])
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            src = ph.get("src") or {}
            url = src.get("large2x") or src.get("large") or src.get("original")
            if url:
                out.append((pid, url))
            if len(out) >= min_photos:
                break
        if len(out) >= min_photos:
            break
        page += 1
        # 안전 상한 (비정상 루프 방지)
        if page > 500:
            print("  [pexels] page 상한 도달", flush=True)
            break
        time.sleep(0.2)

    return out


def download_bytes(client: httpx.Client, url: str) -> bytes | None:
    try:
        resp = client.get(
            url,
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Referer": "https://www.pexels.com/"},
        )
        if resp.status_code != 200:
            return None
        data = resp.content
        if len(data) < 500:
            return None
        return data
    except Exception:
        return None


def safe_name(prefix: str, n: int) -> str:
    return f"{prefix}_{n:03d}.png"


def run(
    out_dir: Path,
    min_per_topic: int,
    delay: float,
    force_cpu: bool,
) -> None:
    _exit_if_no_onnxruntime()
    out_dir.mkdir(parents=True, exist_ok=True)
    api_key = get_api_key()
    session = build_rembg_session(force_cpu=force_cpu)

    seen_raw_hashes: set[str] = set()
    seen_png_hashes: set[str] = set()
    seen_pexels_ids: set[int] = set()

    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for prefix, query in TOPICS:
            print(f"\n=== [{prefix}] 검색: {query!r} (목표 ≥{min_per_topic}장) ===", flush=True)
            candidates = iter_pexels_photos(client, api_key, query, min_per_topic)
            print(f"  API 후보: {len(candidates)} 건", flush=True)

            saved = 0
            attempted = 0
            pbar = tqdm(
                total=min_per_topic,
                desc=f"{prefix}",
                unit="img",
                ncols=100,
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            )

            for photo_id, url in candidates:
                if saved >= min_per_topic:
                    break
                if photo_id in seen_pexels_ids:
                    continue
                seen_pexels_ids.add(photo_id)

                time.sleep(delay)
                attempted += 1
                raw = download_bytes(client, url)
                if not raw:
                    continue

                rh = hashlib.sha256(raw).hexdigest()
                if rh in seen_raw_hashes:
                    continue

                try:
                    png = remove(raw, session=session)
                except Exception as e:
                    tqdm.write(f"  rembg 실패 id={photo_id}: {e}")
                    continue

                ph = hashlib.sha256(png).hexdigest()
                if ph in seen_png_hashes:
                    continue

                seen_raw_hashes.add(rh)
                seen_png_hashes.add(ph)

                saved += 1
                path = out_dir / safe_name(prefix, saved)
                path.write_bytes(png)
                pbar.update(1)
                pbar.set_postfix_str(f"ok={saved} try={attempted}")

            pbar.close()

            if saved < min_per_topic:
                print(
                    f"  [경고] {prefix}: 목표 {min_per_topic}장 중 {saved}장만 저장 "
                    f"(API 결과 부족 또는 다운로드·중복·rembg 실패)",
                    flush=True,
                )

    print(f"\n완료. 출력: {out_dir.resolve()}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pexels 대량 수집 + rembg GPU")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("data/raw"),
        help="저장 폴더 (기본: 프로젝트 루트 기준 data/raw)",
    )
    ap.add_argument(
        "--min-per-topic",
        type=int,
        default=500,
        help="키워드당 최소 저장 장수 (기본 500)",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="요청 간 딜레이(초) — 레이트리밋 완화",
    )
    ap.add_argument(
        "--cpu",
        action="store_true",
        help="rembg 를 CPU 전용으로만 사용 (CUDA/cublas DLL 없을 때)",
    )
    args = ap.parse_args()

    try:
        run(
            out_dir=args.out,
            min_per_topic=args.min_per_topic,
            delay=args.delay,
            force_cpu=args.cpu,
        )
    except KeyboardInterrupt:
        print("\n중단.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
