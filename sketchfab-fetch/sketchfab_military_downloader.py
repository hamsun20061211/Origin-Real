#!/usr/bin/env python3
"""
Sketchfab military tactical gear downloader.

Features:
- Search Sketchfab models (downloadable/free oriented)
- Filter by keyword in title/description/tags:
  Plate Carrier, Helmet, Vest, Rifle
- Prefer GLB / glTF download sources
- Save files under raw_assets/<category>/
- Export downloadable links to JSONL manifest

Usage:
  python sketchfab_military_downloader.py ^
    --api-token YOUR_TOKEN ^
    --query "Military Tactical Gear" ^
    --max-models 80 ^
    --out "raw_assets"

Security note:
- Do NOT hardcode your API token in source files.
- Prefer environment variable: SKETCHFAB_API_TOKEN
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.sketchfab.com/v3"
KEYWORDS = ("plate carrier", "helmet", "vest", "rifle")


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def category_for_model(text: str) -> str | None:
    t = normalize_text(text)
    if "plate carrier" in t or "vest" in t:
        return "vest"
    if "helmet" in t:
        return "helmet"
    if "rifle" in t:
        return "gun"
    return None


def contains_required_keyword(title: str, desc: str, tags: list[dict[str, Any]]) -> bool:
    blob = " ".join(
        [
            normalize_text(title),
            normalize_text(desc),
            " ".join(normalize_text(str(t.get("name", ""))) for t in (tags or [])),
        ]
    )
    return any(k in blob for k in KEYWORDS)


def make_session(api_token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Authorization": f"Token {api_token}",
            "User-Agent": "sketchfab-military-downloader/1.0",
        }
    )
    return s


def fetch_models(session: requests.Session, query: str, max_models: int) -> list[dict[str, Any]]:
    """
    Search models from Sketchfab.
    We request downloadable models first; API fields can vary by account/plan, so we keep robust fallbacks.
    """
    out: list[dict[str, Any]] = []
    next_url = f"{BASE_URL}/search?type=models&q={requests.utils.quote(query)}&downloadable=true&staffpicked=false&archives_flavours=false"
    while next_url and len(out) < max_models:
        r = session.get(next_url, timeout=40)
        if r.status_code == 401:
            raise RuntimeError("Sketchfab API unauthorized. Check your API token.")
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        out.extend(results)
        next_url = data.get("next")
    return out[:max_models]


def get_download_info(session: requests.Session, uid: str) -> dict[str, Any] | None:
    """
    Download endpoint commonly returns time-limited URLs.
    """
    url = f"{BASE_URL}/models/{uid}/download"
    r = session.get(url, timeout=40)
    if r.status_code in (403, 404):
        return None
    r.raise_for_status()
    return r.json()


def choose_best_download(download_info: dict[str, Any]) -> tuple[str, str] | None:
    """
    Prefer GLB / glTF flavors when available.
    Returns: (flavor_name, url)
    """
    if not download_info:
        return None

    # Common shapes:
    # - {"glb": {"url": "..."}}
    # - {"gltf": {"url": "..."}}
    # - {"usdz": {...}}, {"source": {...}}
    # - {"archives": {"gltf": {"url": "..."}}}
    # We handle several possibilities robustly.
    candidates: list[tuple[str, str]] = []

    def pick_url(obj: Any) -> str | None:
        if isinstance(obj, dict):
            for k in ("url", "downloadUrl", "href"):
                if obj.get(k):
                    return str(obj[k])
        return None

    # direct keys
    for key in ("glb", "gltf"):
        if key in download_info:
            u = pick_url(download_info.get(key))
            if u:
                candidates.append((key, u))

    # archives/flavors maps
    for key in ("archives", "flavors", "files"):
        d = download_info.get(key)
        if isinstance(d, dict):
            for subk in ("glb", "gltf"):
                if subk in d:
                    u = pick_url(d.get(subk))
                    if u:
                        candidates.append((subk, u))
            # fallback any zip-ish entry
            for subk, subv in d.items():
                u = pick_url(subv)
                if u:
                    candidates.append((str(subk), u))

    # source fallback
    if "source" in download_info:
        u = pick_url(download_info.get("source"))
        if u:
            candidates.append(("source", u))

    # prioritize glb > gltf > everything else
    if not candidates:
        return None
    candidates.sort(key=lambda x: (0 if x[0] == "glb" else 1 if x[0] == "gltf" else 9))
    return candidates[0]


def download_file(session: requests.Session, url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=90) as r:
        r.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def safe_stem(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\- ]+", "_", s).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:100] or "model"


def extension_from_url(url: str, fallback: str = ".bin") -> str:
    path = url.split("?")[0].lower()
    for ext in (".glb", ".gltf", ".zip", ".rar", ".7z", ".fbx", ".obj"):
        if path.endswith(ext):
            return ext
    return fallback


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-token", default="", help="Sketchfab API token (or set SKETCHFAB_API_TOKEN)")
    p.add_argument("--query", default="Military Tactical Gear")
    p.add_argument("--max-models", type=int, default=80)
    p.add_argument("--out", type=Path, default=Path("raw_assets"))
    p.add_argument("--manifest", type=Path, default=Path("raw_assets/sketchfab_manifest.jsonl"))
    p.add_argument("--dry-run", action="store_true", help="Only list links, do not download files")
    args = p.parse_args()

    token = args.api_token.strip() or __import__("os").environ.get("SKETCHFAB_API_TOKEN", "").strip()
    if not token:
        print("API token required: --api-token or SKETCHFAB_API_TOKEN", file=sys.stderr)
        return 2

    session = make_session(token)

    print(f"[1/3] Searching models: {args.query}")
    models = fetch_models(session, args.query, args.max_models)
    print(f"  -> found {len(models)} candidates")

    args.out.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    saved = 0
    listed = 0

    print("[2/3] Filtering + collecting download links")
    with args.manifest.open("a", encoding="utf-8") as mf:
        for m in models:
            uid = str(m.get("uid") or "")
            if not uid:
                continue

            title = str(m.get("name") or "")
            desc = str(m.get("description") or "")
            tags = m.get("tags") or []
            if not contains_required_keyword(title, desc, tags):
                continue

            cat = category_for_model(" ".join([title, desc, " ".join(str(t.get("name", "")) for t in tags)]))
            if not cat:
                continue

            dl = get_download_info(session, uid)
            if not dl:
                continue
            chosen = choose_best_download(dl)
            if not chosen:
                continue

            flavor, dl_url = chosen
            listed += 1

            ext = extension_from_url(dl_url, fallback=".zip" if flavor in ("gltf", "source") else ".bin")
            stem = safe_stem(f"{title}_{uid}")
            out_path = args.out / cat / f"{stem}{ext}"

            row = {
                "uid": uid,
                "title": title,
                "description": desc[:5000],
                "category": cat,
                "flavor": flavor,
                "download_url": dl_url,
                "model_url": m.get("viewerUrl") or f"https://sketchfab.com/3d-models/{uid}",
                "license": (m.get("license") or {}).get("label") if isinstance(m.get("license"), dict) else m.get("license"),
                "saved_path": str(out_path.as_posix()),
            }
            mf.write(json.dumps(row, ensure_ascii=False) + "\n")

            if not args.dry_run:
                try:
                    download_file(session, dl_url, out_path)
                    saved += 1
                    print(f"  downloaded [{cat}] {title} -> {out_path}")
                except Exception as e:
                    print(f"  failed download: {title} ({e})", file=sys.stderr)

    print(f"[3/3] Done. listed={listed}, downloaded={saved}, manifest={args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

