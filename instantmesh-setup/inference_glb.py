#!/usr/bin/env python3
"""
InstantMesh: 이미지 → 텍스처 메쉬 → .glb
공식 엔트리는 run.py 입니다. 이 스크립트는 run.py 를 호출한 뒤 trimesh 로 GLB 로 묶습니다.

사전: 레포 루트에서 instantmesh-setup 을 두거나, INSTANTMESH_ROOT 환경 변수로 클론 경로 지정.

VRAM 절약:
  - 공식 run.py 는 Zero123++ 파이프라인을 이미 torch.float16 으로 로드합니다.
  - diffusion_steps 를 낮추면 VRAM/시간 모두 감소 (기본 75 → 30~50 권장).
  - configs/*.yaml 의 infer_config (render_resolution 등) 를 줄이면 메모리에 유리 (품질↓).
  - 8bit: InstantMesh 본체는 학습용 bitsandbytes 의존성만 있고 run.py 추론 경로에 INT8 통합은 없습니다.
    Windows 에서는 bitsandbytes 가 제한적입니다. INT8 이 필요하면 WSL2 Ubuntu + 공식 bnb 또는
    더 작은 config 변체(instant-nerf 등) 사용을 검토하세요.

사용 예 (레포 루트 = INSTANTMESH_ROOT):
  set INSTANTMESH_ROOT=C:\\Users\\YOU\\InstantMesh\\InstantMesh
  python instantmesh-setup/inference_glb.py path/to/image.png --out ./my_out

  또는 레포 안에서:
  python ../Origin Real/instantmesh-setup/inference_glb.py examples/hatsune_miku.png
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

__all__ = [
    "find_repo_root",
    "run_instantmesh",
    "find_latest_obj",
    "obj_to_glb",
]


def find_repo_root() -> Path:
    env = os.environ.get("INSTANTMESH_ROOT", "").strip()
    if env:
        p = Path(env).resolve()
        if (p / "run.py").is_file():
            return p
        raise FileNotFoundError(f"INSTANTMESH_ROOT 에 run.py 없음: {p}")
    here = Path(__file__).resolve().parent
    cand = here.parent / "InstantMesh"
    if (cand / "run.py").is_file():
        return cand.resolve()
    up = here.parent.parent / "InstantMesh" / "InstantMesh"
    if (up / "run.py").is_file():
        return up.resolve()
    raise FileNotFoundError(
        "InstantMesh 클론 경로를 찾지 못했습니다. "
        "set INSTANTMESH_ROOT=C:\\path\\to\\TencentARC\\InstantMesh 클론 루트"
    )


def run_instantmesh(
    repo: Path,
    image: Path,
    work: Path,
    config: str,
    export_texmap: bool,
    save_video: bool,
    diffusion_steps: int,
    seed: int,
    no_rembg: bool,
    extra: list[str],
) -> None:
    cmd = [
        sys.executable,
        str(repo / "run.py"),
        str(repo / config) if not os.path.isabs(config) else config,
        str(image),
        "--output_path",
        str(work),
        "--seed",
        str(seed),
        "--diffusion_steps",
        str(diffusion_steps),
    ]
    if export_texmap:
        cmd.append("--export_texmap")
    if save_video:
        cmd.append("--save_video")
    if no_rembg:
        cmd.append("--no_rembg")
    cmd.extend(extra)
    print("[inference_glb]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(repo), check=True)


def find_latest_obj(mesh_dir: Path) -> Path | None:
    objs = list(mesh_dir.rglob("*.obj"))
    if not objs:
        return None
    objs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return objs[0]


def obj_to_glb(obj_path: Path, glb_out: Path) -> None:
    import trimesh

    # OBJ+MTL+텍스처가 같은 폴더에 있어야 함 (save_obj_with_mtl 기준)
    scene_or_mesh = trimesh.load(str(obj_path), force=None, process=False)
    glb_out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(scene_or_mesh, trimesh.Scene):
        scene_or_mesh.export(str(glb_out), file_type="glb")
    else:
        scene_or_mesh.export(str(glb_out), file_type="glb")
    print("[inference_glb] GLB 저장:", glb_out)


def main() -> int:
    p = argparse.ArgumentParser(description="InstantMesh → 텍스처 GLB 래퍼")
    p.add_argument("image", type=Path, help="입력 이미지 (.png/.jpg)")
    p.add_argument("--out", type=Path, default=Path("./outputs_glb_run"))
    p.add_argument("--config", default="configs/instant-mesh-large.yaml")
    p.add_argument("--glb-name", default="", help="출력 glb 파일명 (기본: 입력 베이스명)")
    p.add_argument("--no-video", action="store_true", help="비디오 생략 (VRAM·시간 절약)")
    p.add_argument("--no-texmap", action="store_true", help="버텍스 컬러만 (텍스처 맵 미사용)")
    p.add_argument("--diffusion-steps", type=int, default=50, help="낮을수록 VRAM/시간↓ (품질↓)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--no-rembg", action="store_true")
    p.add_argument("--extra", nargs="*", default=[], help="run.py 에 그대로 넘길 인자")
    args = p.parse_args()

    if not args.image.is_file():
        print("이미지를 찾을 수 없습니다:", args.image, file=sys.stderr)
        return 1

    repo = find_repo_root()
    work = args.out.resolve()
    run_instantmesh(
        repo,
        args.image.resolve(),
        work,
        args.config,
        export_texmap=not args.no_texmap,
        save_video=not args.no_video,
        diffusion_steps=args.diffusion_steps,
        seed=args.seed,
        no_rembg=args.no_rembg,
        extra=args.extra,
    )

    config_stem = Path(args.config).stem
    mesh_dir = work / config_stem / "meshes"
    obj_path = find_latest_obj(mesh_dir)
    if not obj_path:
        print("생성된 .obj 를 찾지 못했습니다:", mesh_dir, file=sys.stderr)
        return 2

    base = args.glb_name.strip() or args.image.stem
    safe = re.sub(r"[^\w\-]+", "_", base)[:80] or "out"
    glb_path = work / config_stem / f"{safe}.glb"
    obj_to_glb(obj_path, glb_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
