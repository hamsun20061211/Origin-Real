"""
`prompts/dataset-collection-checklist-and-prompts.md` 의 B(건물)·C(차량) 섹션에서
번호 매겨진 영어 프롬프트를 읽어, 시드 1~8로 각각 생성 → rembg → Real-ESRGAN 업스케일 후 저장.

출력:
  data/train/buildings/building_001.png … (프롬프트 40 × 시드 8 = 320)
  data/train/vehicles/vehicle_001.png …

사용 (프로젝트 루트에서, CUDA PyTorch 가 잡힌 환경):
  pip install -r scripts/image_collector/requirements-generate-train.txt
  python scripts/image_collector/generate_train_from_prompts.py

VRAM 절약:
  --sequential-cpu-offload   # diffusers 순차 CPU 오프로드
  --realesrgan-tile 256      # Real-ESRGAN 타일(작을수록 VRAM↓, 느려짐)
  --clear-every 5            # N장(전체 파이프라인)마다 cuda empty_cache + gc (기본 5)

Real-ESRGAN 가중치는 최초 실행 시 캐시 디렉터리에 자동 다운로드됩니다.
"""

from __future__ import annotations

import argparse
import gc
import io
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Literal


DEFAULT_PROMPTS_MD = Path("prompts/dataset-collection-checklist-and-prompts.md")
DEFAULT_OUT = Path("data/train")

# Official release (xinntao/Real-ESRGAN) — x2 RRDB, matches 512→1024 style upscaling
REALESRGAN_X2_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"
)

NEGATIVE_PROMPT = (
    "text, watermark, signature, logo, brand, low quality, blurry, jpeg artifacts, "
    "deformed, duplicate, cropped, worst quality, people, crowd, license plate text"
)


def extract_numbered_prompts(md_text: str, section: Literal["B", "C"]) -> list[str]:
    if section == "B":
        start = md_text.index("## B.")
        end = md_text.index("## C.")
    else:
        start = md_text.index("## C.")
        tail = md_text[start:]
        if "## 한 줄 요약" in tail:
            end = start + tail.index("## 한 줄 요약")
        else:
            end = len(md_text)
    block = md_text[start:end]
    found: dict[int, str] = {}
    for m in re.finditer(r"(?m)^(\d+)\.\s+(.+)$", block):
        n = int(m.group(1))
        found[n] = m.group(2).strip()
    if not found:
        raise ValueError(f"섹션 {section} 에서 번호 프롬프트를 찾지 못했습니다.")
    ordered = [found[i] for i in range(1, max(found) + 1) if i in found]
    missing = [i for i in range(1, max(found) + 1) if i not in found]
    if missing:
        raise ValueError(f"섹션 {section} 번호 누락: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    return ordered


def global_index(prompt_index_1based: int, seed: int) -> int:
    """1-based prompt index, seed in 1..8 → 1..320"""
    return (prompt_index_1based - 1) * 8 + seed


def rgba_composite_on_white(rgba):
    from PIL import Image

    rgba = rgba.convert("RGBA")
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.split()[3])
    return bg


def ensure_realesrgan_weights(path: Path, url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 1_000_000:
        return
    print(f"[Real-ESRGAN] 가중치 다운로드: {url}", flush=True)
    tmp = path.with_suffix(path.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)  # noqa: S310 — fixed official URL
    tmp.replace(path)


def build_rembg_session(*, force_cpu: bool):
    from rembg import remove as _remove_check  # noqa: F401
    from rembg.session_factory import new_session

    env_cpu = os.environ.get("REMBG_FORCE_CPU", "").strip().lower() in ("1", "true", "yes")
    if force_cpu or env_cpu:
        s = new_session("u2net", providers=["CPUExecutionProvider"])
        print("[rembg] CPU 세션", flush=True)
        return s
    try:
        s = new_session("u2net", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        print("[rembg] CUDA 세션 (실패 시 CPU로 전환)", flush=True)
        return s
    except Exception as e:
        print(f"[rembg] GPU 세션 실패 → CPU: {e}", flush=True)
        return new_session("u2net", providers=["CPUExecutionProvider"])


def build_realesrgan_upsampler(
    weights: Path,
    *,
    device,
    tile: int,
    half: bool,
):
    import torch
    import cv2
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer

    ensure_realesrgan_weights(weights, REALESRGAN_X2_URL)
    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
        scale=2,
    )
    upsampler = RealESRGANer(
        scale=2,
        model_path=str(weights),
        dni_weight=None,
        model=model,
        tile=tile,
        tile_pad=10,
        pre_pad=0,
        half=half,
        gpu_id=0 if device.type == "cuda" else None,
    )
    return upsampler, cv2


def pil_to_bgr_uint8(cv2, pil_rgb):
    import numpy as np

    rgb = np.asarray(pil_rgb.convert("RGB"), dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def bgr_to_pil_rgb(arr_bgr):
    from PIL import Image

    rgb = arr_bgr[:, :, ::-1].copy()
    return Image.fromarray(rgb)


def cuda_gc(*, aggressive: bool) -> None:
    import torch

    gc.collect()
    if not torch.cuda.is_available():
        return
    torch.cuda.empty_cache()
    if aggressive:
        torch.cuda.ipc_collect()


def load_sd_pipeline(
    model_id: str,
    *,
    sequential_cpu_offload: bool,
    device,
):
    import torch
    from diffusers import DPMSolverMultistepScheduler, StableDiffusionPipeline

    dtype = torch.float16 if device.type == "cuda" else torch.float32
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        safety_checker=None,
        requires_safety_checker=False,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    if sequential_cpu_offload and device.type == "cuda":
        pipe.enable_sequential_cpu_offload()
    else:
        pipe = pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    try:
        pipe.enable_attention_slicing()
    except Exception:
        pass
    try:
        pipe.enable_vae_slicing()
    except Exception:
        pass
    return pipe


def unload_sd_pipeline(pipe) -> None:
    del pipe
    cuda_gc(aggressive=True)


def reload_sd_pipeline(
    model_id: str,
    *,
    sequential_cpu_offload: bool,
    device,
):
    return load_sd_pipeline(
        model_id,
        sequential_cpu_offload=sequential_cpu_offload,
        device=device,
    )


def generate_one(
    pipe,
    prompt: str,
    *,
    seed: int,
    num_inference_steps: int,
    height: int,
    width: int,
    guidance: float,
):
    import torch

    gdev = "cuda" if torch.cuda.is_available() else "cpu"
    gen = torch.Generator(device=gdev)
    gen.manual_seed(int(seed))
    out = pipe(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance,
        height=height,
        width=width,
        generator=gen,
    )
    img = out.images[0]
    del out
    return img


def postprocess_rembg_esrgan(
    pil_rgb,
    *,
    rembg_session,
    upsampler,
    cv2,
    skip_esrgan: bool,
):
    from PIL import Image
    from rembg import remove

    buf = io.BytesIO()
    pil_rgb.save(buf, format="PNG")
    cut = remove(buf.getvalue(), session=rembg_session)
    rgba = Image.open(io.BytesIO(cut)).convert("RGBA")
    on_white = rgba_composite_on_white(rgba)
    if skip_esrgan:
        return on_white
    bgr = pil_to_bgr_uint8(cv2, on_white)
    upscaled, _ = upsampler.enhance(bgr, outscale=2)
    return bgr_to_pil_rgb(upscaled)


def run_category(
    *,
    name: str,
    folder: str,
    file_prefix: str,
    prompts: list[str],
    args: argparse.Namespace,
    device,
) -> None:
    from tqdm import tqdm

    out_dir = args.out / folder
    out_dir.mkdir(parents=True, exist_ok=True)

    rembg_session = build_rembg_session(force_cpu=args.rembg_cpu)
    upsampler = cv2 = None
    if not args.skip_real_esrgan:
        wpath = Path(args.realesrgan_weights).expanduser()
        upsampler, cv2 = build_realesrgan_upsampler(
            wpath,
            device=device,
            tile=args.realesrgan_tile,
            half=device.type == "cuda",
        )

    pipe = load_sd_pipeline(
        args.model_id,
        sequential_cpu_offload=args.sequential_cpu_offload,
        device=device,
    )

    jobs: list[tuple[int, int, str]] = []
    for pi, prompt in enumerate(prompts, start=1):
        for seed in range(args.seed_start, args.seed_end + 1):
            idx = global_index(pi, seed)
            jobs.append((idx, seed, prompt))

    desc = f"{name}"
    gen_since_unload = 0
    gen_count = 0

    for idx, seed, prompt in tqdm(jobs, desc=desc, unit="img"):
        out_path = out_dir / f"{file_prefix}_{idx:03d}.png"
        if args.resume and out_path.is_file():
            continue

        pil = generate_one(
            pipe,
            prompt,
            seed=seed,
            num_inference_steps=args.steps,
            height=args.height,
            width=args.width,
            guidance=args.guidance,
        )
        gen_count += 1
        # 생성 직후 N장마다 비우기(rembg/ESRGAN 전 피크 완화)
        if gen_count % args.clear_every == 0:
            cuda_gc(aggressive=True)

        final = postprocess_rembg_esrgan(
            pil,
            rembg_session=rembg_session,
            upsampler=upsampler,
            cv2=cv2,
            skip_esrgan=args.skip_real_esrgan,
        )
        final.save(out_path, format="PNG", optimize=True)

        gen_since_unload += 1

        if args.unload_sd_every > 0 and gen_since_unload >= args.unload_sd_every:
            gen_since_unload = 0
            unload_sd_pipeline(pipe)
            pipe = reload_sd_pipeline(
                args.model_id,
                sequential_cpu_offload=args.sequential_cpu_offload,
                device=device,
            )
            cuda_gc(aggressive=True)

    unload_sd_pipeline(pipe)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="프롬프트 MD → SD 생성 → rembg → Real-ESRGAN → data/train",
    )
    p.add_argument(
        "--prompts-md",
        type=Path,
        default=DEFAULT_PROMPTS_MD,
        help="dataset-collection-checklist-and-prompts.md 경로",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="출력 루트 (기본 data/train)",
    )
    p.add_argument(
        "--model-id",
        type=str,
        default="runwayml/stable-diffusion-v1-5",
        help="diffusers Stable Diffusion 모델 ID",
    )
    p.add_argument("--height", type=int, default=512)
    p.add_argument("--width", type=int, default=512)
    p.add_argument("--steps", type=int, default=28)
    p.add_argument("--guidance", type=float, default=7.5)
    p.add_argument("--seed-start", type=int, default=1)
    p.add_argument("--seed-end", type=int, default=8)
    p.add_argument(
        "--clear-every",
        type=int,
        default=5,
        help="N장 생성 직후(배경 제거·업스케일 전) torch.cuda.empty_cache + gc",
    )
    p.add_argument(
        "--unload-sd-every",
        type=int,
        default=0,
        help="N장마다 SD 파이프라인 완전 내리고 다시 로드 (0=비활성, 매우 느림)",
    )
    p.add_argument(
        "--sequential-cpu-offload",
        action="store_true",
        help="enable_sequential_cpu_offload (VRAM↓, 속도↓)",
    )
    p.add_argument("--rembg-cpu", action="store_true", help="rembg 를 CPU만 사용")
    p.add_argument(
        "--realesrgan-weights",
        type=str,
        default=str(Path.home() / ".cache" / "origin-real" / "RealESRGAN_x2plus.pth"),
        help="RealESRGAN_x2plus.pth 경로",
    )
    p.add_argument(
        "--realesrgan-tile",
        type=int,
        default=256,
        help="RealESRGAN tile 크기 (VRAM 절약: 128~400)",
    )
    p.add_argument(
        "--skip-real-esrgan",
        action="store_true",
        help="업스케일 생략(디버그)",
    )
    p.add_argument("--resume", action="store_true", help="이미 있는 PNG 는 건너뜀")
    p.add_argument(
        "--only",
        choices=("both", "buildings", "vehicles"),
        default="both",
    )
    p.add_argument("--dry-run", action="store_true", help="프롬프트 파싱만 검증")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    md_path = args.prompts_md if args.prompts_md.is_absolute() else root / args.prompts_md
    if not md_path.is_file():
        print(f"프롬프트 파일이 없습니다: {md_path}", file=sys.stderr)
        sys.exit(1)

    text = md_path.read_text(encoding="utf-8")
    building_prompts = extract_numbered_prompts(text, "B")
    vehicle_prompts = extract_numbered_prompts(text, "C")
    print(
        f"[parse] 건물 {len(building_prompts)}개, 차량 {len(vehicle_prompts)}개",
        flush=True,
    )
    if args.dry_run:
        return

    import torch

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        print(
            "[경고] CUDA 가 없습니다. CPU 로 동작하며 매우 느립니다.",
            file=sys.stderr,
        )

    args.out = args.out if args.out.is_absolute() else root / args.out

    try:
        if args.only in ("both", "buildings"):
            run_category(
                name="buildings",
                folder="buildings",
                file_prefix="building",
                prompts=building_prompts,
                args=args,
                device=device,
            )
        if args.only in ("both", "vehicles"):
            run_category(
                name="vehicles",
                folder="vehicles",
                file_prefix="vehicle",
                prompts=vehicle_prompts,
                args=args,
                device=device,
            )
    except KeyboardInterrupt:
        print("\n중단.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
