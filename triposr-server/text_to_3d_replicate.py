"""
Text → 3D via Replicate (클라우드). 로컬 GPU 없이 사용 가능.

환경 변수:
  REPLICATE_API_TOKEN   필수 (https://replicate.com/account/api-tokens)
  REPLICATE_TEXT_TO_3D_MODEL  선택, 기본 cjwbw/shap-e
  REPLICATE_TEXT_TO_3D_INPUT_EXTRA  선택, JSON 객체 문자열 (모델별 옵션 병합)

pip install -r requirements-text3d.txt
"""

from __future__ import annotations

import io
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("origin_real.text3d")

DEFAULT_MODEL = "cjwbw/shap-e"


def _collect_urls(obj: Any, out: list[str]) -> None:
    if obj is None:
        return
    if isinstance(obj, str) and obj.startswith("http"):
        out.append(obj)
        return
    if isinstance(obj, (list, tuple)):
        for x in obj:
            _collect_urls(x, out)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_urls(v, out)
        return
    url = getattr(obj, "url", None)
    if isinstance(url, str) and url.startswith("http"):
        out.append(url)


def _ply_to_glb(data: bytes) -> bytes:
    import trimesh

    loaded = trimesh.load(io.BytesIO(data), file_type="ply")
    if isinstance(loaded, trimesh.Scene):
        geom = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not geom:
            raise ValueError("PLY Scene 안에 메쉬가 없습니다.")
        mesh = trimesh.util.concatenate(geom)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise ValueError(f"지원하지 않는 PLY 타입: {type(loaded)}")
    out = mesh.export(file_type="glb")
    if not isinstance(out, bytes):
        raise ValueError("trimesh GLB export 가 bytes 를 반환하지 않았습니다.")
    return out


def _download_to_glb(url: str, timeout: float = 300.0) -> bytes:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.content
    if len(data) >= 4 and data[:4] == b"glTF":
        return data
    # Shap-E 등이 PLY만 줄 때
    if data[:3] == b"ply" or url.lower().endswith(".ply"):
        return _ply_to_glb(data)
    raise ValueError(
        f"다운로드한 파일이 GLB가 아닙니다 (magic={data[:12]!r}, url={url[:80]}…)"
    )


def run_replicate_text_to_glb(prompt: str) -> bytes:
    token = (os.environ.get("REPLICATE_API_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("REPLICATE_API_TOKEN 이 설정되지 않았습니다.")

    try:
        import replicate
    except ImportError as e:
        raise RuntimeError(
            "replicate 패키지가 없습니다. triposr-server 에서: pip install -r requirements-text3d.txt"
        ) from e

    model = (os.environ.get("REPLICATE_TEXT_TO_3D_MODEL") or DEFAULT_MODEL).strip()
    extra_raw = os.environ.get("REPLICATE_TEXT_TO_3D_INPUT_EXTRA", "").strip()
    model_input: dict[str, Any] = {"prompt": prompt}
    if extra_raw:
        try:
            extra = json.loads(extra_raw)
            if isinstance(extra, dict):
                model_input.update(extra)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"REPLICATE_TEXT_TO_3D_INPUT_EXTRA JSON 파싱 실패: {e}") from e

    logger.info("Replicate Text→3D model=%s prompt_len=%s", model, len(prompt))

    out = replicate.run(model, input=model_input)

    urls: list[str] = []
    _collect_urls(out, urls)
    if not urls:
        raise RuntimeError(f"Replicate 출력에서 URL 을 찾지 못했습니다: {type(out)!r} {out!r}")

    last_err: Exception | None = None
    for u in urls:
        try:
            return _download_to_glb(u)
        except Exception as e:
            logger.warning("URL GLB 변환 실패, 다음 후보 시도: %s — %s", u[:120], e)
            last_err = e
    if last_err:
        raise RuntimeError(f"모든 출력 URL 처리 실패: {last_err}") from last_err
    raise RuntimeError("GLB 생성 실패")
