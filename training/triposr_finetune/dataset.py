"""
On-disk dataset for images + captions under data/processed.

Expected layouts (any one):

1) manifest.jsonl — each line: {"image": "relative/path.png", "caption": "..."}
   Paths are relative to processed_root.

2) images/*.png|jpg|webp with optional captions/<stem>.txt or <stem>.txt next to the image.

PEXELS_API_KEY is only required when --require-pexels-key is passed (provenance check);
collection itself uses the collector script, not this loader.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from torch.utils.data import Dataset


def _collect_from_manifest(processed_root: Path) -> list[dict[str, Any]]:
    manifest = processed_root / "manifest.jsonl"
    if not manifest.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with manifest.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            img_rel = obj.get("image") or obj.get("path") or obj.get("file")
            if not img_rel:
                continue
            cap = obj.get("caption") or obj.get("text") or ""
            rows.append(
                {
                    "image_path": (processed_root / img_rel).resolve(),
                    "caption": str(cap).strip(),
                }
            )
    return rows


def _collect_from_image_dir(processed_root: Path) -> list[dict[str, Any]]:
    img_dir = processed_root / "images"
    if not img_dir.is_dir():
        img_dir = processed_root
    if not img_dir.is_dir():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    rows: list[dict[str, Any]] = []
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() not in exts:
            continue
        cap_path_txt = processed_root / "captions" / f"{p.stem}.txt"
        cap_side = p.with_suffix(".txt")
        caption = ""
        if cap_path_txt.is_file():
            caption = cap_path_txt.read_text(encoding="utf-8").strip()
        elif cap_side.is_file():
            caption = cap_side.read_text(encoding="utf-8").strip()
        rows.append({"image_path": p.resolve(), "caption": caption})
    return rows


class ProcessedImageCaptionDataset(Dataset):
    """Loads RGB images and optional text captions from data/processed."""

    def __init__(
        self,
        processed_root: str | Path,
        *,
        require_pexels_key: bool = False,
    ) -> None:
        if require_pexels_key and not (os.environ.get("PEXELS_API_KEY") or "").strip():
            raise RuntimeError(
                "PEXELS_API_KEY is not set. Unset --require-pexels-key for offline training."
            )
        self.processed_root = Path(processed_root).resolve()
        self.samples = _collect_from_manifest(self.processed_root)
        if not self.samples:
            self.samples = _collect_from_image_dir(self.processed_root)
        if not self.samples:
            raise FileNotFoundError(
                f"No training images under {self.processed_root}.\n"
                "Create the folder and add either:\n"
                "  - data/processed/images/*.png (or .jpg), optional data/processed/captions/<name>.txt\n"
                "  - or data/processed/manifest.jsonl (see dataset.py docstring)\n"
                "Copy from data/raw after Pexels collection, or run: "
                "New-Item -ItemType Directory -Force data\\processed\\images"
            )
        missing = [s for s in self.samples if not s["image_path"].is_file()]
        if missing:
            raise FileNotFoundError(
                f"Missing {len(missing)} image files, e.g. {missing[0]['image_path']}"
            )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        s = self.samples[idx]
        path: Path = s["image_path"]
        # TripoSR image tokenizer expects 3-channel input (mean/std are RGB).
        image = Image.open(path).convert("RGB")
        caption: str = s["caption"]
        return {
            "image": image,
            "caption": caption,
            "path": str(path),
        }
