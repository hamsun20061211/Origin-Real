#!/usr/bin/env python3
"""
Blender Python API: 밀리터리 에셋 멀티 앵글 렌더 자동화

요구사항 충족:
 - 턴테이블 12장: 카메라가 모델 중심을 기준으로 30도 간격 회전 (0..330deg)
 - 고해상도: 1024x1024 PNG
 - Close-up 4장 추가: 어깨끈(좌/우), 옆구리 버클(전면 저각), 몰리 웨빙(측면)
 - 배경: 투명 또는 균일 회색
 - 조명: 3점 조명(3-Point Lighting)

실행 예:
  blender --background --python render_turntable_12plus4.py -- ^
    --input "D:/models/plate_carrier.glb" --output "D:/dataset/pc_turntable" --background transparent
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

try:
    import bpy
    from mathutils import Vector, Matrix
except ImportError:
    bpy = None  # type: ignore


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Turntable 12 + closeups 4 (military assets)")
    p.add_argument("--input", "-i", required=True, type=Path)
    p.add_argument("--output", "-o", required=True, type=Path)
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--samples", type=int, default=192)
    p.add_argument("--background", choices=["transparent", "gray"], default="transparent")
    p.add_argument("--gray", type=float, default=0.55, help="gray bg value when --background gray")
    p.add_argument("--elevation-deg", type=float, default=12.0)
    p.add_argument("--distance-mul", type=float, default=3.2)
    return p.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)


def import_model(path: Path) -> list["bpy.types.Object"]:
    suf = path.suffix.lower()
    fp = str(path.resolve())
    if suf in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=fp)
    elif suf == ".fbx":
        bpy.ops.import_scene.fbx(filepath=fp)
    elif suf == ".obj":
        bpy.ops.wm.obj_import(filepath=fp)
    else:
        raise ValueError(f"지원: .glb/.gltf/.fbx/.obj — got: {path}")
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def combined_bounds(objects: list["bpy.types.Object"]) -> tuple[Vector, Vector]:
    mins = [1e9, 1e9, 1e9]
    maxs = [-1e9, -1e9, -1e9]
    for o in objects:
        mw = o.matrix_world
        for c in o.bound_box:
            v = mw @ Vector(c)
            for i in range(3):
                mins[i] = min(mins[i], v[i])
                maxs[i] = max(maxs[i], v[i])
    return Vector(mins), Vector(maxs)


def center_radius(objects: list["bpy.types.Object"]) -> tuple[Vector, float]:
    mn, mx = combined_bounds(objects)
    c = (mn + mx) * 0.5
    r = (mx - mn).length * 0.5
    return c, max(r, 1e-4)


def normalize(objects: list["bpy.types.Object"], target_radius: float = 1.0) -> tuple[Vector, float, Vector, Vector]:
    c, r = center_radius(objects)
    s = target_radius / r if r > 1e-6 else 1.0
    for o in objects:
        o.matrix_world = Matrix.Translation(-c) @ o.matrix_world
        o.matrix_world = Matrix.Diagonal((s, s, s, 1.0)) @ o.matrix_world
    mn, mx = combined_bounds(objects)
    c2, r2 = center_radius(objects)
    return c2, r2, mn, mx


def setup_render(res: int, samples: int, background: str, gray: float) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    try:
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True

    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 15

    if background == "transparent":
        scene.render.film_transparent = True
    else:
        scene.render.film_transparent = False

    world = bpy.data.worlds.new("UniformWorld")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    if background == "gray":
        g = float(max(0.0, min(1.0, gray)))
        bg.inputs["Color"].default_value = (g, g, g, 1.0)
        bg.inputs["Strength"].default_value = 1.0
    else:
        bg.inputs["Color"].default_value = (0.6, 0.6, 0.6, 1.0)
        bg.inputs["Strength"].default_value = 0.25
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_area_light(name: str, location: tuple[float, float, float], energy: float, size: float, color: tuple[float, float, float]) -> None:
    bpy.ops.object.light_add(type="AREA", location=location)
    l = bpy.context.active_object
    l.name = name
    l.data.energy = energy
    l.data.size = size
    l.data.color = color


def setup_3_point_lighting() -> None:
    # 3-Point Lighting: Key / Fill / Rim
    add_area_light("Key", (2.2, -1.8, 2.4), 4500, 2.5, (1.0, 0.98, 0.95))
    add_area_light("Fill", (-2.0, -1.2, 1.2), 2200, 3.0, (0.85, 0.92, 1.0))
    add_area_light("Rim", (0.2, 2.6, 1.6), 1200, 4.0, (0.9, 0.9, 1.0))


def create_camera(name: str, location: Vector, target: Vector, lens_mm: float) -> "bpy.types.Object":
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.active_object
    cam.name = name
    direction = target - location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens_mm
    cam.data.clip_end = 500.0
    return cam


def pos_on_orbit(center: Vector, radius: float, az_deg: float, el_deg: float) -> Vector:
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    x = math.cos(az) * math.cos(el)
    y = math.sin(az) * math.cos(el)
    z = math.sin(el)
    # Blender 기준: +Y가 전방이므로, -Y 쪽을 front로 보려면 y 부호를 뒤집는 대신
    # az 270을 front로 잡기보다, 여기서는 orbit을 단순화하고 front를 az=270로 정의하지 않고
    # output 이름만 angle 기준으로 둡니다. 학습은 각도 메타데이터로 처리 권장.
    return center + Vector((x, y, z)) * radius


def render_shot(scene, cam, out_path: Path) -> None:
    scene.camera = cam
    scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)


def main() -> int:
    if bpy is None:
        print("Blender에서 실행하세요: blender --background --python ...", file=sys.stderr)
        return 2

    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    args = parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    out_dir = args.output

    clear_scene()
    setup_render(args.resolution, args.samples, args.background, args.gray)
    setup_3_point_lighting()

    meshes = import_model(args.input)
    if not meshes:
        print("메쉬를 찾지 못했습니다:", args.input, file=sys.stderr)
        return 1

    center, r, mn, mx = normalize(meshes, target_radius=1.0)
    scene = bpy.context.scene

    # 12 turntable shots, 30deg increments
    dist = r * args.distance_mul
    el = float(args.elevation_deg)
    lens = 50.0
    for k in range(12):
        az = k * 30.0
        loc = pos_on_orbit(center, dist, az_deg=az, el_deg=el)
        cam = create_camera(f"cam_turn_{k:02d}", loc, center, lens_mm=lens)
        fp = out_dir / f"turntable_{k:02d}_az{int(az):03d}.png"
        render_shot(scene, cam, fp)
        bpy.data.objects.remove(cam, do_unlink=True)

    # Close-ups 4: shoulder straps (L/R), buckle (front low), molle (side)
    size = mx - mn
    side = max(size.x, size.y) * 0.5
    height = max(size.z, 1e-4)

    # heuristics for targets in normalized space
    t_shoulder_L = center + Vector((-side * 0.35, 0.0, height * 0.38))
    t_shoulder_R = center + Vector((side * 0.35, 0.0, height * 0.38))
    t_buckle = center + Vector((0.0, 0.0, -height * 0.12))
    t_molle_L = center + Vector((-side * 0.40, 0.0, 0.0))

    close_dist = dist * 0.55
    close_lens = 85.0  # 디테일 압축(버클/웨빙) + 왜곡 감소

    closeups: list[tuple[str, Vector, Vector]] = [
        ("close_shoulder_left", center + Vector((-close_dist * 0.35, -close_dist * 0.52, height * 0.62)), t_shoulder_L),
        ("close_shoulder_right", center + Vector((close_dist * 0.35, -close_dist * 0.52, height * 0.62)), t_shoulder_R),
        ("close_buckle_front_low", center + Vector((0.0, -close_dist * 0.65, -height * 0.18)), t_buckle),
        ("close_molle_left_side", center + Vector((-close_dist * 0.62, -close_dist * 0.15, height * 0.05)), t_molle_L),
    ]

    for name, loc, tgt in closeups:
        cam = create_camera(f"cam_{name}", loc, tgt, lens_mm=close_lens)
        fp = out_dir / f"{name}.png"
        render_shot(scene, cam, fp)
        bpy.data.objects.remove(cam, do_unlink=True)

    print("완료:", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

