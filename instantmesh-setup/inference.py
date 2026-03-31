#!/usr/bin/env python3
"""
InstantMesh 전술 장비용 래퍼: 고해상도 infer_config, VRAM 프리셋, 메쉬 좌우 대칭.

- 공식 파이프라인은 run.py 이며, Stage2 입력 멀티뷰는 기본 320으로 리사이즈(업스트림 고정)입니다.
  디테일(몰리·버클)은 diffusion_steps·텍스처 해상도·렌더 해상도 조합으로 올리는 것이 현실적입니다.
- Stable Diffusion 의 Tiled VAE 와 구조가 다릅니다. Zero123++ 파이프라인 VAE 타일링은
  docs/run_py_vae_tiling_snippet.py 스니펫을 run.py 에 수동 병합하세요.
- INT8/양자화(bitsandbytes 등)는 Windows 에서 제한적이며, VRAM 은 --low-vram 과 단계/비디오 생략으로 우선 완화합니다.

사용 (venv 의 python 권장):
  set INSTANTMESH_ROOT=%USERPROFILE%\\InstantMesh\\InstantMesh
  python inference.py helmet.png --preset tactical_hi --symmetry --out .\\out

  python inference.py rifle.png --texture-resolution 2048 --render-resolution 768 --low-vram --no-video
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from inference_glb import find_latest_obj, find_repo_root, obj_to_glb, run_instantmesh


def patch_infer_config_yaml(text: str, texture_resolution: int | None, render_resolution: int | None) -> str:
    """infer_config 블록 내 숫자만 교체 (PyYAML 불필요)."""
    if texture_resolution is not None:
        text = re.sub(
            r"(?m)^(\s*texture_resolution:\s*)\d+(\s*)$",
            rf"\g<1>{texture_resolution}\g<2>",
            text,
        )
    if render_resolution is not None:
        text = re.sub(
            r"(?m)^(\s*render_resolution:\s*)\d+(\s*)$",
            rf"\g<1>{render_resolution}\g<2>",
            text,
        )
    return text


PRESETS: dict[str, tuple[int | None, int | None]] = {
    # (texture_resolution, render_resolution) — large 체크포인트 기준 VRAM 여유 필요
    "tactical_hi": (2048, 768),
    "tactical_balanced": (1536, 512),
    "default": (None, None),
}


def resolve_hi_res_args(
    preset: str,
    texture_res: int | None,
    render_res: int | None,
    low_vram: bool,
) -> tuple[int | None, int | None]:
    pt, pr = PRESETS.get(preset, (None, None))
    tr = texture_res if texture_res is not None else pt
    rr = render_res if render_res is not None else pr
    if low_vram:
        # 텍스처 해상도는 유지하고, 비디오/합성 부하에 쓰이는 render_resolution 만 낮춤
        if rr is not None and rr > 384:
            rr = min(rr, 384)
        elif rr is None:
            rr = 384
    return tr, rr


def materialize_config(
    repo: Path,
    base_config: str,
    texture_res: int | None,
    render_res: int | None,
) -> tuple[str, Path | None]:
    """패치된 yaml 경로와 (실행 후 삭제할 런타임 파일, 없으면 None)."""
    if texture_res is None and render_res is None:
        return base_config, None

    base_path = Path(base_config)
    if not base_path.is_absolute():
        base_path = repo / base_path
    if not base_path.is_file():
        raise FileNotFoundError(f"config 없음: {base_path}")

    raw = base_path.read_text(encoding="utf-8")
    patched = patch_infer_config_yaml(raw, texture_res, render_res)
    if patched == raw:
        return str(base_path), None

    runtime = repo / "configs" / f"{base_path.stem}.tactical_runtime.yaml"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(patched, encoding="utf-8")
    return str(runtime), runtime


def _axis_index(axis: str) -> int:
    axis = axis.strip().lower()
    if axis in ("x", "0"):
        return 0
    if axis in ("y", "1"):
        return 1
    if axis in ("z", "2"):
        return 2
    raise ValueError(f"axis 는 x|y|z 이어야 함: {axis!r}")


def apply_bilateral_symmetry_trimesh(mesh, axis: str = "x", chunk: int | None = None) -> None:
    """
    정면 기준 좌우 대칭을 한 단계로 강화: 각 정점 i 에 대해 R(v_i) 에 가장 가까운 정점 v_j 를 찾고
    v_i' = 0.5 * (v_i + R(v_j)) 로 이동. 총기·헬멧 등 대칭 축이 명확할 때 유리.

    topology/UV 는 유지되며 정점만 이동합니다 (텍스처 왜곡 가능).

    scipy.spatial.cKDTree 필요.
    """
    try:
        from scipy.spatial import cKDTree
    except ImportError as e:
        raise RuntimeError(
            "대칭 후처리에 scipy 가 필요합니다: pip install scipy"
        ) from e

    import numpy as np

    vi = _axis_index(axis)
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    if verts.size == 0:
        return

    mirrored_query = verts.copy()
    mirrored_query[:, vi] *= -1.0
    tree = cKDTree(verts)
    n = verts.shape[0]
    chunk = int(chunk or min(max(n // 4, 4096), 65536))
    idx_parts: list = []
    for start in range(0, n, chunk):
        end = min(start + chunk, n)
        _, idx = tree.query(mirrored_query[start:end], k=1, workers=-1)
        idx_parts.append(idx)
    pair_idx = np.concatenate(idx_parts, axis=0)

    partner = verts[pair_idx]
    r_partner = partner.copy()
    r_partner[:, vi] *= -1.0
    sym = 0.5 * (verts + r_partner)
    mesh.vertices[:, :] = sym


def load_mesh_for_export(obj_path: Path):
    import trimesh

    return trimesh.load(str(obj_path), force=None, process=False)


def export_scene_glb(scene_or_mesh, glb_path: Path) -> None:
    glb_path.parent.mkdir(parents=True, exist_ok=True)
    scene_or_mesh.export(str(glb_path), file_type="glb")


def main() -> int:
    p = argparse.ArgumentParser(
        description="InstantMesh 전술/고해상도/대칭 래퍼 (run.py + 선택 후처리)"
    )
    p.add_argument("image", type=Path, help="입력 이미지 (.png/.jpg)")
    p.add_argument("--out", type=Path, default=Path("./outputs_glb_tactical"))
    p.add_argument("--config", default="configs/instant-mesh-large.yaml")
    p.add_argument("--glb-name", default="", help="출력 glb 파일명 (기본: 입력 베이스명)")
    p.add_argument("--preset", default="default", choices=list(PRESETS.keys()))
    p.add_argument("--texture-resolution", type=int, default=None, help="infer_config.texture_resolution")
    p.add_argument("--render-resolution", type=int, default=None, help="infer_config.render_resolution")
    p.add_argument("--low-vram", action="store_true", help="render_resolution 만 상한(384)으로 제한, 텍스처는 유지")
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--no-texmap", action="store_true")
    p.add_argument("--diffusion-steps", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--no-rembg", action="store_true")
    p.add_argument("--symmetry", action="store_true", help="내보내기 전 메쉬에 좌우 대칭 후처리")
    p.add_argument("--symmetry-axis", default="x", help="대칭면 법선 축: x|y|z (기본 x)")
    p.add_argument("--extra", nargs="*", default=[], help="run.py 에 그대로 넘길 인자")
    args = p.parse_args()

    if not args.image.is_file():
        print("이미지를 찾을 수 없습니다:", args.image, file=sys.stderr)
        return 1

    repo = find_repo_root()
    tr, rr = resolve_hi_res_args(
        args.preset, args.texture_resolution, args.render_resolution, args.low_vram
    )
    config_path, tmp_yaml = materialize_config(repo, args.config, tr, rr)
    try:
        work = args.out.resolve()
        run_instantmesh(
            repo,
            args.image.resolve(),
            work,
            config_path,
            export_texmap=not args.no_texmap,
            save_video=not args.no_video,
            diffusion_steps=args.diffusion_steps,
            seed=args.seed,
            no_rembg=args.no_rembg,
            extra=args.extra,
        )
    finally:
        if tmp_yaml and tmp_yaml.is_file():
            try:
                tmp_yaml.unlink()
            except OSError:
                pass

    # run.py 출력: output_path / basename(config).replace('.yaml','') / meshes
    out_cfg_stem = Path(config_path).stem
    mesh_dir = work / out_cfg_stem / "meshes"
    obj_path = find_latest_obj(mesh_dir)
    if not obj_path:
        print("생성된 .obj 를 찾지 못했습니다:", mesh_dir, file=sys.stderr)
        return 2

    import re as re_mod

    base = args.glb_name.strip() or args.image.stem
    safe = re_mod.sub(r"[^\w\-]+", "_", base)[:80] or "out"
    glb_path = work / out_cfg_stem / f"{safe}.glb"

    if args.symmetry:
        scene_or_mesh = load_mesh_for_export(obj_path)
        import trimesh

        if isinstance(scene_or_mesh, trimesh.Scene):
            geoms = [g for g in scene_or_mesh.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not geoms:
                print("Scene 내 Trimesh 없음; 기본 GLB 내보내기 사용", file=sys.stderr)
                obj_to_glb(obj_path, glb_path)
                return 0
            for g in geoms:
                apply_bilateral_symmetry_trimesh(g, axis=args.symmetry_axis)
            export_scene_glb(scene_or_mesh, glb_path)
        else:
            apply_bilateral_symmetry_trimesh(scene_or_mesh, axis=args.symmetry_axis)
            export_scene_glb(scene_or_mesh, glb_path)
        print("[inference] 대칭 후처리 GLB 저장:", glb_path)
    else:
        obj_to_glb(obj_path, glb_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
