#!/usr/bin/env python3
"""
Stable Video Diffusion (로컬) — 이미지→짧은 영상.
VRAM 절약: fp16 variant, xformers(가능 시), VAE slicing, CPU/sequential offload.

사전:
  - Hugging Face에서 stabilityai SVD 모델 약관 동의 후 `huggingface-cli login` 권장
  - 입력 이미지 권장 크기: 가로 1024 × 세로 576 근처 (파이프라인 권장)

예:
  python run_svd.py --image path/to.png --output out.mp4 --low-vram
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

import torch

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("svd_local")


def _try_xformers(pipe: Any) -> None:
    try:
        pipe.enable_xformers_memory_efficient_attention()
        logger.info("xFormers memory-efficient attention 활성화")
    except Exception as e:
        logger.warning("xFormers 비활성: %s (메모리 절약이 줄 수 있음)", e)


def _try_vae_optimizations(pipe: Any) -> None:
    for name, fn in (
        ("VAE slicing", getattr(pipe, "enable_vae_slicing", None)),
        ("VAE tiling", getattr(pipe, "enable_vae_tiling", None)),
    ):
        if callable(fn):
            try:
                fn()
                logger.info("%s 활성화", name)
            except Exception as e:
                logger.warning("%s 실패: %s", name, e)


def load_pipeline_safe(
    model_id: str,
    *,
    dtype: torch.dtype,
    local_files_only: bool,
    token: str | None,
    max_retries: int,
) -> Any:
    from diffusers import StableVideoDiffusionPipeline

    base_kw: dict[str, Any] = {
        "local_files_only": local_files_only,
    }
    if token:
        base_kw["token"] = token
    elif os.environ.get("HF_TOKEN"):
        base_kw["token"] = os.environ["HF_TOKEN"]

    # fp16 변형이 없는 스냅샷 대비: fp16 실패 시 variant 없이 재시도
    load_plan: list[dict[str, Any]] = [
        {"torch_dtype": dtype, **({"variant": "fp16"} if dtype == torch.float16 else {})},
        {"torch_dtype": dtype},
    ]
    if dtype == torch.float16:
        load_plan.append({"torch_dtype": torch.float32})

    last_err: Exception | None = None
    for attempt in range(max_retries):
        for extra in load_plan:
            kw = {**base_kw, **extra}
            try:
                logger.info(
                    "체크포인트 로드 시도 %d/%s | %s | keys=%s",
                    attempt + 1,
                    max_retries,
                    model_id,
                    sorted(kw.keys()),
                )
                pipe = StableVideoDiffusionPipeline.from_pretrained(model_id, **kw)
                logger.info("로드 성공: %s", model_id)
                return pipe
            except OSError as e:
                last_err = e
                logger.error("OSError: %s", e)
            except ValueError as e:
                last_err = e
                logger.error("ValueError (variant/스냅샷 불일치 가능): %s", e)
            except Exception as e:
                last_err = e
                logger.exception("로드 오류: %s", e)

        if attempt + 1 < max_retries:
            logger.info("재시도 (%d/%d) — HF 토큰·캐시·네트워크 확인", attempt + 1, max_retries)

    raise RuntimeError(f"파이프라인 로드 실패: {model_id}") from last_err


def main() -> int:
    parser = argparse.ArgumentParser(description="Stable Video Diffusion (local img2vid)")
    parser.add_argument("--image", type=Path, required=True, help="입력 이미지 경로")
    parser.add_argument("--output", type=Path, default=Path("svd_out.mp4"))
    parser.add_argument(
        "--model",
        type=str,
        default="stabilityai/stable-video-diffusion-img2vid-xt",
        help="또는 stabilityai/stable-video-diffusion-img2vid (프레임 수 적음)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--decode-chunk-size", type=int, default=4, help="낮출수록 VRAM↓, 느려질 수 있음")
    parser.add_argument("--motion-bucket-id", type=int, default=127)
    parser.add_argument("--noise-aug-strength", type=float, default=0.02)
    parser.add_argument("--fps", type=int, default=7)
    parser.add_argument("--no-fp16", action="store_true", help="fp32 (VRAM↑)")
    parser.add_argument("--low-vram", action="store_true", help="sequential CPU offload (가장 느리고 가장 VRAM 절약)")
    parser.add_argument("--med-vram", action="store_true", help="model CPU offload")
    parser.add_argument("--no-offload", action="store_true", help="전부 GPU (VRAM 충분할 때)")
    parser.add_argument("--local-files-only", action="store_true", help="캐시에만 있을 때 오프라인 로")
    parser.add_argument("--load-retries", type=int, default=2)
    parser.add_argument("--no-xformers", action="store_true")
    args = parser.parse_args()

    if not args.image.is_file():
        logger.error("입력 이미지가 없습니다: %s", args.image)
        return 2

    dtype = torch.float32 if args.no_fp16 else torch.float16
    if not torch.cuda.is_available():
        logger.warning("CUDA 미사용 — CPU는 매우 느리고 실패할 수 있습니다.")
        dtype = torch.float32

    try:
        pipe = load_pipeline_safe(
            args.model,
            dtype=dtype,
            local_files_only=args.local_files_only,
            token=os.environ.get("HF_TOKEN"),
            max_retries=max(1, args.load_retries),
        )
    except Exception as e:
        logger.error("로드 실패. HF 로그인·모델 약관·디스크 여유를 확인하세요: %s", e)
        return 3

    if not args.no_xformers:
        _try_xformers(pipe)
    _try_vae_optimizations(pipe)

    if args.low_vram:
        try:
            pipe.enable_sequential_cpu_offload()
            logger.info("sequential CPU offload")
        except Exception as e:
            logger.warning("sequential offload 실패, model offload 시도: %s", e)
            pipe.enable_model_cpu_offload()
    elif args.med_vram or not args.no_offload:
        if torch.cuda.is_available() and not args.no_offload:
            try:
                pipe.enable_model_cpu_offload()
                logger.info("model CPU offload")
            except Exception as e:
                logger.warning("CPU offload 실패: %s", e)
                pipe.to("cuda")
    else:
        if torch.cuda.is_available():
            pipe.to("cuda")

    from diffusers.utils import export_to_video, load_image

    image = load_image(str(args.image))
    # 권장 종횡비 근사
    image = image.resize((1024, 576))

    generator = torch.manual_seed(args.seed)
    try:
        result = pipe(
            image,
            decode_chunk_size=max(1, args.decode_chunk_size),
            motion_bucket_id=args.motion_bucket_id,
            noise_aug_strength=args.noise_aug_strength,
            generator=generator,
        )
        frames = result.frames[0]
    except torch.cuda.OutOfMemoryError:
        logger.error(
            "VRAM 부족 — --low-vram, --decode-chunk-size 2, 더 작은 모델(img2vid 비 XT) 시도",
        )
        return 4
    except Exception:
        logger.exception("추론 실패")
        return 5

    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(frames, str(args.output), fps=args.fps)
    logger.info("저장 완료: %s", args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
