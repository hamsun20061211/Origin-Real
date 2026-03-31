# SPDX-License-Identifier: MIT
"""
Blender 배치 스크립트: 군용 장비 3D → 학습용 멀티뷰 + PBR 맵 + dataset.json

실행 (Blender 4.x / 3.6+ Cycles 권장):
  blender --background --python render_military_training_data.py -- \\
    --input \"C:/models/plate_carrier.glb\" --output \"C:/dataset/out_run1\" \\
    --resolution 2048 --samples 256 --sharpen 0.45

선택 인자:
  --tag-rules   equipment_tag_rules.json 경로 (기본: 스크립트 동일 폴더)
  --no-bake     PBR 베이크 생략 (멀티뷰만)
  --no-sharpen  샤프닝 생략

주의:
  - bpy 는 Blender 내장 파이썬에서만 로드됩니다.
  - 메쉬가 UV 없으면 Smart UV Project 를 자동 시도합니다 (베이크용).
  - 멀티머티리얼/복잡한 노드는 Emission 알베도 베이크가 일부 실패할 수 있습니다.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from pathlib import Path

try:
    import bpy
    from mathutils import Vector, Matrix
except ImportError:
    bpy = None  # type: ignore


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    if argv is None:
        argv = []
    p = argparse.ArgumentParser(description="Military equipment Blender dataset export")
    p.add_argument("--input", "-i", required=True, type=Path, help="GLB/FBX/OBJ 등 3D 파일")
    p.add_argument("--output", "-o", required=True, type=Path, help="출력 루트 폴더")
    p.add_argument("--resolution", type=int, default=2048)
    p.add_argument("--samples", type=int, default=256)
    p.add_argument("--sharpen", type=float, default=0.4, help="언샤프 마스크 강도 (0 비활성에 가깝)")
    p.add_argument("--tag-rules", type=Path, default=None)
    p.add_argument("--no-bake", action="store_true")
    p.add_argument("--no-sharpen", action="store_true")
    p.add_argument("--seed-name", default="", help="dataset 항목 id 접두어")
    return p.parse_args(argv)


def load_tag_rules(script_dir: Path, override: Path | None) -> dict:
    path = override or (script_dir / "equipment_tag_rules.json")
    if not path.is_file():
        return {"equipment_rules": [], "camouflage_rules": [], "material_hints": []}
    return json.loads(path.read_text(encoding="utf-8"))


def infer_tags(stem: str, rules: dict) -> tuple[str | None, list[str], list[str]]:
    """장비 대표 타입, 모든 태그, PBR 힌트 태그."""
    lower = stem.lower().replace("-", "_")
    tags: set[str] = set()
    pbr_hints: set[str] = set()
    equip_type: str | None = None

    def apply_rule_list(key: str):
        nonlocal equip_type
        for rule in rules.get(key, []):
            for pat in rule.get("match", []):
                if pat.lower() in lower:
                    for t in rule.get("tags", []):
                        tags.add(t)
                    if key == "equipment_rules" and not equip_type:
                        equip_type = rule["tags"][0] if rule.get("tags") else None

    apply_rule_list("equipment_rules")
    apply_rule_list("camouflage_rules")
    apply_rule_list("colorway_rules")
    for rule in rules.get("material_hints", []):
        for pat in rule.get("match", []):
            if pat.lower() in lower:
                for t in rule.get("tags", []):
                    tags.add(t)
                note = rule.get("pbr_notes")
                if note:
                    pbr_hints.add(note)

    tags.add("military_equipment")
    tags.add("synthetic_render")
    return equip_type, sorted(tags), sorted(pbr_hints)


def sharpen_rgba_numpy(arr: "object", strength: float) -> "object":
    """HxWx4 float32 0..1, 언샤프 마스크 (4-이웃 블러 기준). 위장 패턴 경계 보존용."""
    import numpy as np

    if strength <= 1e-6:
        return arr
    p = np.pad(arr.astype(np.float32, copy=False), ((1, 1), (1, 1), (0, 0)), mode="edge")
    blur = (
        p[:-2, 1:-1]
        + p[2:, 1:-1]
        + p[1:-1, :-2]
        + p[1:-1, 2:]
    ) * 0.25
    return np.clip(arr + strength * (arr - blur), 0.0, 1.0)


def sharpen_png_on_disk(filepath: Path, strength: float) -> None:
    """렌더 저장 후 디스크 PNG 를 로드해 샤프닝 (Blender 내장 numpy)."""
    if strength <= 1e-6:
        return
    import numpy as np

    fp = str(filepath.resolve())
    if not Path(fp).is_file():
        return
    name = "__sharpen_work"
    prev = bpy.data.images.get(name)
    if prev:
        bpy.data.images.remove(prev, do_unlink=True)
    img = bpy.data.images.load(filepath=fp)
    img.name = name
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    px = np.flipud(px)
    px = sharpen_rgba_numpy(px, strength)
    px = np.flipud(px)
    img.pixels = px.ravel().tolist()
    img.filepath_raw = fp
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img, do_unlink=True)


def materials_used_by_object(obj: bpy.types.Object) -> list[bpy.types.Material]:
    out: list[bpy.types.Material] = []
    for slot in obj.material_slots:
        m = slot.material
        if m is not None and m not in out:
            out.append(m)
    return out


def attach_bake_image_all_slots(obj: bpy.types.Object, image: bpy.types.Image) -> bpy.types.ShaderNodeTexImage | None:
    """Cycles 멀티머티리얼 베이크: 모든 슬롯에 동일 Image Texture 를 연결해 한 번에 베이크."""
    last_tex: bpy.types.ShaderNodeTexImage | None = None
    for mat in materials_used_by_object(obj):
        if not mat.use_nodes:
            mat.use_nodes = True
        nt = mat.node_tree
        tex = nt.nodes.new(type="ShaderNodeTexImage")
        tex.image = image
        tex.label = "_PBRBakeTarget"
        tex.select = True
        nt.nodes.active = tex
        last_tex = tex
        obj.active_material = mat
    return last_tex


def remove_bake_image_nodes(obj: bpy.types.Object) -> None:
    for mat in materials_used_by_object(obj):
        nt = mat.node_tree
        for n in list(nt.nodes):
            if getattr(n, "label", "") == "_PBRBakeTarget":
                nt.nodes.remove(n)


def new_bake_image(name: str, resolution: int, colorspace: str) -> bpy.types.Image:
    img = bpy.data.images.new(name, width=resolution, height=resolution, alpha=True, float_buffer=False)
    img.colorspace_settings.name = colorspace
    return img


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)


def import_model(path: Path) -> list[bpy.types.Object]:
    suf = path.suffix.lower()
    path_str = str(path.resolve())
    if suf == ".glb" or suf == ".gltf":
        bpy.ops.import_scene.gltf(filepath=path_str)
    elif suf == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path_str)
    elif suf == ".obj":
        bpy.ops.wm.obj_import(filepath=path_str)
    else:
        raise ValueError(f"지원 확장자: .glb .gltf .fbx .obj 만: {path}")
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def mesh_bounds_world(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    mw = obj.matrix_world
    corners = [mw @ Vector(corner) for corner in obj.bound_box]
    min_c = Vector((min(v[i] for v in corners) for i in range(3)))
    max_c = Vector((max(v[i] for v in corners) for i in range(3)))
    return min_c, max_c


def combined_mesh_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    mins: list[float] = []
    maxs: list[float] = []
    for axis in range(3):
        lo = min(mesh_bounds_world(o)[0][axis] for o in objects)
        hi = max(mesh_bounds_world(o)[1][axis] for o in objects)
        mins.append(lo)
        maxs.append(hi)
    return Vector(mins), Vector(maxs)


def scene_center_and_radius(objects: list[bpy.types.Object]) -> tuple[Vector, float]:
    mn, mx = combined_mesh_bounds(objects)
    center = (mn + mx) * 0.5
    radius = (mx - mn).length * 0.5
    return center, max(radius, 1e-4)


def normalize_scene(objects: list[bpy.types.Object], target_radius: float = 1.0) -> tuple[Vector, float]:
    """월드 원점 기준 스케일 + 중심 이동."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    center, radius = scene_center_and_radius(objects)
    scale = target_radius / radius if radius > 1e-6 else 1.0
    for o in objects:
        o.matrix_world = Matrix.Translation(-center) @ o.matrix_world
        o.matrix_world = Matrix.Diagonal((scale, scale, scale, 1.0)) @ o.matrix_world
    center2, radius2 = scene_center_and_radius(objects)
    return center2, radius2


def setup_world_cycles():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    try:
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"
    scene.cycles.use_adaptive_sampling = True
    world = bpy.data.worlds.new("NeutralWorld")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value = (0.55, 0.56, 0.58, 1.0)
    bg.inputs["Strength"].default_value = 0.35
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    # 소프트 에어리어 라이트 — 군복(나일론)·무광 도장·무광 금속이 과포화되지 않게 낮은 대비
    bpy.ops.object.light_add(type="AREA", location=(2.2, -1.8, 2.4))
    key = bpy.context.active_object
    key.data.energy = 4500
    key.data.shape = "SQUARE"
    key.data.size = 2.5
    key.data.color = (1.0, 0.98, 0.95)

    bpy.ops.object.light_add(type="AREA", location=(-2.0, -1.2, 1.2))
    fill = bpy.context.active_object
    fill.data.energy = 2200
    fill.data.size = 3.0
    fill.data.color = (0.85, 0.92, 1.0)

    bpy.ops.object.light_add(type="AREA", location=(0.2, 2.6, 1.6))
    rim = bpy.context.active_object
    rim.data.energy = 1200
    rim.data.size = 4.0
    rim.data.color = (0.9, 0.9, 1.0)


def create_camera(name: str, location: Vector, target: Vector) -> bpy.types.Object:
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.active_object
    cam.name = name
    direction = target - location
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam.rotation_euler = rot_quat.to_euler()
    cam.data.lens = 50
    cam.data.clip_end = 500.0
    return cam


def build_camera_rig(center: Vector, radius: float, objects: list[bpy.types.Object]) -> list[tuple[str, Vector, Vector]]:
    """최소 16 뷰: 전신 + 어깨/버클/몰리 클로즈업."""
    mn, mx = combined_mesh_bounds(objects)
    up_h = (mx - mn).z
    side_w = max((mx - mn).x, (mx - mn).y) * 0.5
    dist = radius * 3.2
    c = center

    def T(dx, dy, dz):
        return c + Vector((dx, dy, dz))

    views: list[tuple[str, Vector, Vector]] = [
        ("front", T(0, -dist, up_h * 0.12), c),
        ("back", T(0, dist, up_h * 0.12), c),
        ("left_side", T(-dist, 0, up_h * 0.1), c),
        ("right_side", T(dist, 0, up_h * 0.1), c),
        ("top", T(0, 0, dist * 0.85 + up_h * 0.1), c),
        ("bottom", T(0, 0, -dist * 0.55), c + Vector((0, 0, up_h * 0.05))),
        ("three_quarter_fl", T(-dist * 0.72, -dist * 0.72, up_h * 0.14), c),
        ("three_quarter_fr", T(dist * 0.72, -dist * 0.72, up_h * 0.14), c),
        ("three_quarter_bl", T(-dist * 0.72, dist * 0.72, up_h * 0.14), c),
        ("three_quarter_br", T(dist * 0.72, dist * 0.72, up_h * 0.14), c),
        # 어깨 스트랩 (높은 시점에서 살짝 앞·옆)
        (
            "shoulder_strap_left_high",
            T(-dist * 0.35, -dist * 0.52, up_h * 0.62),
            c + Vector((-side_w * 0.35, 0, up_h * 0.38)),
        ),
        (
            "shoulder_strap_right_high",
            T(dist * 0.35, -dist * 0.52, up_h * 0.62),
            c + Vector((side_w * 0.35, 0, up_h * 0.38)),
        ),
        # 버클/가슴 하부 클로즈업
        (
            "buckle_front_low_macro",
            T(0, -dist * 0.42, -up_h * 0.18),
            c + Vector((0, side_w * 0.05, -up_h * 0.12)),
        ),
        (
            "buckle_oblique_side_macro",
            T(dist * 0.38, -dist * 0.35, up_h * 0.02),
            c + Vector((0, 0, -up_h * 0.05)),
        ),
        # 몰리/리깅 측면
        ("molle_webbing_left_close", T(-dist * 0.32, -dist * 0.12, up_h * 0.05), c + Vector((-side_w * 0.4, 0, 0))),
        ("molle_webbing_right_close", T(dist * 0.32, -dist * 0.12, up_h * 0.05), c + Vector((side_w * 0.4, 0, 0))),
        # 추가 디테일: 총기·헬멧용 상단 전방 매크로
        ("upper_front_macro", T(0, -dist * 0.55, up_h * 0.45), c + Vector((0, 0, up_h * 0.22))),
    ]
    return views


def ensure_uv_for_bake(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def principled_emit_for_bake_setup(obj: bpy.types.Object) -> None:
    """Albedo 베이크용: Principled Base Color → Emission (해당 오브젝트 머티리얼만)."""
    for mat in materials_used_by_object(obj):
        if not mat.use_nodes:
            continue
        nt = mat.node_tree
        out = nt.nodes.get("Material Output")
        if not out:
            continue
        old = nt.nodes.get("_BakeEmitHelper")
        if old:
            nt.nodes.remove(old)
        principled = None
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED":
                principled = n
                break
        if not principled:
            continue
        base = principled.inputs.get("Base Color")
        if base is None:
            continue

        emit = nt.nodes.new("ShaderNodeEmission")
        emit.name = "_BakeEmitHelper"
        emit.location = (principled.location.x + 350, principled.location.y)
        if base.is_linked:
            nt.links.new(base.links[0].from_socket, emit.inputs["Color"])
        else:
            emit.inputs["Color"].default_value = base.default_value
        emit.inputs["Strength"].default_value = 1.0

        if out.inputs["Surface"].is_linked:
            nt.links.remove(out.inputs["Surface"].links[0])
        nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])


def restore_material_outputs(obj: bpy.types.Object) -> None:
    for mat in materials_used_by_object(obj):
        if not mat.use_nodes:
            continue
        nt = mat.node_tree
        out = nt.nodes.get("Material Output")
        emit = nt.nodes.get("_BakeEmitHelper")
        if not out or not emit:
            continue
        principled = None
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED":
                principled = n
                break
        if not principled:
            continue
        if out.inputs["Surface"].is_linked:
            nt.links.remove(out.inputs["Surface"].links[0])
        nt.links.new(principled.outputs["BSDF"], out.inputs["Surface"])
        nt.nodes.remove(emit)


def classify_material_suffix(obj: bpy.types.Object) -> str:
    """
    질감 구분 태깅: 군복 나일론(비금속) vs 총기 무광 금속.
    - Principled Metallic 입력값/링크를 기반으로 'metal' 우선 판정.
    - 이름 힌트(weapon/metal/steel/al)도 보조 신호로 사용.
    """
    metal_score = 0.0
    fabric_score = 0.0
    for mat in materials_used_by_object(obj):
        name = (mat.name or "").lower()
        if any(k in name for k in ("metal", "steel", "alum", "weapon", "rifle", "gun", "receiver", "barrel")):
            metal_score += 0.25
        if any(k in name for k in ("fabric", "nylon", "cloth", "uniform", "camo", "multicam", "webbing", "cordura")):
            fabric_score += 0.25
        if not mat.use_nodes:
            continue
        nt = mat.node_tree
        principled = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not principled:
            continue
        m_in = principled.inputs.get("Metallic")
        if m_in is None:
            continue
        if m_in.is_linked:
            # metallic texture 존재 → 금속 가능성 높음
            metal_score += 0.6
        else:
            try:
                m = float(m_in.default_value)
            except Exception:
                m = 0.0
            metal_score += max(0.0, min(1.0, m))
            fabric_score += max(0.0, 1.0 - m) * 0.35
    return "_metal" if metal_score >= max(0.45, fabric_score) else "_fabric"


def find_camouflage_images(obj: bpy.types.Object) -> list[bpy.types.Image]:
    """
    멀티캠/디지털 패턴이 포함된 Base Color 텍스처 후보를 추출.
    - 이름/파일경로 키워드 기반.
    """
    keys = ("multicam", "multi_cam", "mtp", "ucp", "digital", "digicam", "marpat", "woodland", "flecktarn", "atacs", "kryptek")
    out: list[bpy.types.Image] = []
    for mat in materials_used_by_object(obj):
        if not mat.use_nodes:
            continue
        for n in mat.node_tree.nodes:
            if n.type != "TEX_IMAGE":
                continue
            img = getattr(n, "image", None)
            if img is None:
                continue
            s = (img.name or "").lower()
            fp = (getattr(img, "filepath", "") or "").lower()
            if any(k in s for k in keys) or any(k in fp for k in keys):
                if img not in out:
                    out.append(img)
    return out


def estimate_tiling_period_from_pixels(px_rgba, max_period: int = 512) -> tuple[int | None, int | None]:
    """
    간단 타일링 주기 추정(가로/세로): 오토코릴레이션 기반.
    px_rgba: HxWx4 float32(0..1)
    """
    import numpy as np

    if px_rgba is None:
        return None, None
    arr = np.asarray(px_rgba, dtype=np.float32)[..., :3]
    h, w, _ = arr.shape
    if h < 32 or w < 32:
        return None, None
    gray = (arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114).astype(np.float32)
    gray -= float(np.mean(gray))

    def best_period_1d(sig: np.ndarray, limit: int) -> int | None:
        n = sig.shape[0]
        limit = int(min(limit, n // 2))
        if limit < 8:
            return None
        # FFT autocorr
        f = np.fft.rfft(sig, n=2 * n)
        ac = np.fft.irfft(f * np.conj(f))[: n]
        ac = ac / (ac[0] + 1e-8)
        # ignore 0-lag; find first strong peak
        start = 8
        end = limit
        if end <= start:
            return None
        window = ac[start:end]
        k = int(np.argmax(window)) + start
        if ac[k] > 0.35:
            return k
        return None

    # aggregate along rows/cols
    row_sig = np.mean(gray, axis=0)
    col_sig = np.mean(gray, axis=1)
    px = best_period_1d(row_sig, max_period)
    py = best_period_1d(col_sig, max_period)
    return px, py


def save_image_tile_from_render_result(src_img: bpy.types.Image, out_path: Path, tile_w: int, tile_h: int) -> None:
    import numpy as np

    w, h = src_img.size
    if tile_w <= 0 or tile_h <= 0 or tile_w > w or tile_h > h:
        return
    px = np.array(src_img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    # 중앙에서 타일 크기만큼 crop
    x0 = max(0, (w - tile_w) // 2)
    y0 = max(0, (h - tile_h) // 2)
    crop = px[y0 : y0 + tile_h, x0 : x0 + tile_w, :]
    tmp = bpy.data.images.new("__tile_tmp", width=tile_w, height=tile_h, alpha=True, float_buffer=False)
    tmp.pixels = crop.reshape(-1).tolist()
    tmp.filepath_raw = str(out_path.resolve())
    tmp.file_format = "PNG"
    tmp.save()
    bpy.data.images.remove(tmp, do_unlink=True)


def ensure_minimum_material(obj: bpy.types.Object) -> None:
    if materials_used_by_object(obj):
        return
    mat = bpy.data.materials.new(name="IM_DefaultPrincipled")
    mat.use_nodes = True
    obj.data.materials.append(mat)


def bake_pbr_maps(export_dir: Path, obj: bpy.types.Object, resolution: int, suffix: str) -> dict[str, str]:
    """Albedo/Normal/Roughness/Metallic Cycles 베이크 — suffix로 _fabric/_metal 구분."""
    pbr_dir = export_dir / "pbr"
    pbr_dir.mkdir(parents=True, exist_ok=True)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="OBJECT")
    ensure_minimum_material(obj)

    results: dict[str, str] = {}
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"

    def bake_pass(pass_type: str, filename: str, colorspace: str, srgb_save: bool) -> str:
        img = new_bake_image(f"Bake_{pass_type}", resolution, colorspace)
        try:
            attach_bake_image_all_slots(obj, img)
            bpy.ops.object.bake(type=pass_type, use_clear=True, margin=4)
            fp = pbr_dir / filename
            if srgb_save:
                img.colorspace_settings.name = "sRGB"
            img.filepath_raw = str(fp.resolve())
            img.file_format = "PNG"
            img.save()
            return str(fp.as_posix())
        finally:
            remove_bake_image_nodes(obj)
            bpy.data.images.remove(img, do_unlink=True)

    results["normal"] = bake_pass("NORMAL", f"normal{suffix}.png", "Non-Color", False)
    results["roughness"] = bake_pass("ROUGHNESS", f"roughness{suffix}.png", "Non-Color", False)

    try:
        results["metallic"] = bake_pass("METALLIC", f"metallic{suffix}.png", "Non-Color", False)
    except Exception:
        # Blender 버전에 METALLIC 베이크 미지원 시 생략 (총기 금속은 roughness+Base 로 근사)
        pass

    try:
        principled_emit_for_bake_setup(obj)
        # EMIT = Base Color 근사 → Albedo로 저장
        results["albedo"] = bake_pass("EMIT", f"albedo{suffix}.png", "Linear", True)
    finally:
        restore_material_outputs(obj)

    return results


def join_meshes(objects: list[bpy.types.Object]) -> bpy.types.Object | None:
    if not objects:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    return bpy.context.active_object


def main() -> int:
    if bpy is None:
        print("Blender에서 실행하세요: blender --background --python ...", file=sys.stderr)
        return 2

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []

    args = _parse_args(argv)
    script_dir = Path(__file__).resolve().parent
    rules = load_tag_rules(script_dir, args.tag_rules)

    args.output.mkdir(parents=True, exist_ok=True)
    export_root = args.output / args.input.stem
    export_root.mkdir(parents=True, exist_ok=True)
    renders_dir = export_root / "renders"
    renders_dir.mkdir(exist_ok=True)

    clear_scene()
    setup_world_cycles()
    meshes = import_model(args.input)
    if not meshes:
        print("메쉬를 찾지 못했습니다:", args.input, file=sys.stderr)
        return 1

    center, radius = normalize_scene(meshes, target_radius=1.0)
    views = build_camera_rig(center, radius, meshes)

    scene = bpy.context.scene
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.film_transparent = True
    scene.cycles.samples = args.samples

    sample_id = args.seed_name.strip() or args.input.stem
    uid = uuid.uuid4().hex[:8]
    equip_type, tags, pbr_hints = infer_tags(sample_id, rules)

    renders_record: dict[str, str] = {}
    sharpen = 0.0 if args.no_sharpen else args.sharpen

    for view_name, loc, tgt in views:
        cam = create_camera(f"cam_{view_name}", loc, tgt)
        scene.camera = cam
        fp = renders_dir / f"{view_name}.png"
        scene.render.filepath = str(fp)
        bpy.ops.render.render(write_still=True)
        if sharpen > 1e-6:
            try:
                sharpen_png_on_disk(fp, sharpen)
            except Exception:
                pass
        renders_record[view_name] = str(fp.as_posix())
        bpy.data.objects.remove(cam, do_unlink=True)

    pbr_record: dict[str, str] = {}
    if not args.no_bake:
        joined = join_meshes(meshes)
        if joined:
            ensure_uv_for_bake(joined)
            try:
                suffix = classify_material_suffix(joined)
                pbr_record = bake_pbr_maps(export_root, joined, min(args.resolution, 4096), suffix=suffix)

                # 위장 패턴 추출: albedo(베이크 결과)에서 타일링 주기 추정 + 타일 crop 저장
                if "albedo" in pbr_record:
                    import numpy as np

                    albedo_path = Path(pbr_record["albedo"])
                    abs_albedo = (export_root / albedo_path).resolve() if not albedo_path.is_absolute() else albedo_path
                    # Blender 이미지로 로드 후 픽셀 접근
                    img = bpy.data.images.load(filepath=str(abs_albedo))
                    w, h = img.size
                    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
                    tx, ty = estimate_tiling_period_from_pixels(px, max_period=min(512, w // 2, h // 2))
                    bpy.data.images.remove(img, do_unlink=True)

                    camo_imgs = find_camouflage_images(joined)
                    if camo_imgs or (tx is not None and ty is not None):
                        pat_dir = export_root / "pbr" / "patterns"
                        pat_dir.mkdir(parents=True, exist_ok=True)
                        meta = {
                            "tiling_period_px": {"x": tx, "y": ty},
                            "sources": [],
                        }
                        # 소스 텍스처 파일 복사(가능할 때)
                        for ci in camo_imgs:
                            fp = (ci.filepath or "").strip()
                            meta["sources"].append(fp)
                            try:
                                # packed/상대경로 대응은 제한적: 존재하는 파일만
                                src = Path(bpy.path.abspath(fp))
                                if src.is_file():
                                    dst = pat_dir / src.name
                                    if not dst.exists():
                                        dst.write_bytes(src.read_bytes())
                            except Exception:
                                pass

                        # 타일 이미지 저장(추정 성공 시)
                        if tx and ty and tx >= 8 and ty >= 8:
                            # albedo를 다시 load해서 crop 저장
                            img2 = bpy.data.images.load(filepath=str(abs_albedo))
                            tile_path = pat_dir / f"tile_{tx}x{ty}{suffix}.png"
                            save_image_tile_from_render_result(img2, tile_path, tile_w=int(tx), tile_h=int(ty))
                            bpy.data.images.remove(img2, do_unlink=True)
                            meta["tile_image"] = str(tile_path.as_posix())

                        (pat_dir / f"pattern_meta{suffix}.json").write_text(
                            json.dumps(meta, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
            except Exception as e:
                print("[PBR bake warning]", e, file=sys.stderr)

    dataset_path = export_root / "dataset.json"
    entry = {
        "id": f"{sample_id}_{uid}",
        "source_file": str(args.input.resolve().as_posix()),
        "equipment_type_guess": equip_type,
        "tags": tags,
        "pbr_material_hints": pbr_hints,
        "render_engine": "cycles_pbr",
        "resolution": [args.resolution, args.resolution],
        "view_count": len(views),
        "renders": renders_record,
        "pbr_maps": pbr_record,
        "notes": "PBR: normal/roughness/(metallic 지원 시) Cycles 베이크. base_color_emit은 Principled Base Color→Emission 근사. 군복 나일론/무광 금속/헬멧 도장은 roughness·베이스 색 대비로 학습시 구분 권장.",
    }

    manifest = {"version": "1.0", "samples": [entry]}
    dataset_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print("완료:", dataset_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
