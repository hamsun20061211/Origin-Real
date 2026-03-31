#!/usr/bin/env python3
import os
import csv
import argparse
from pathlib import Path

import bpy
from mathutils import Vector

SUPPORTED_EXTS = {".obj", ".fbx", ".glb", ".gltf"}

# Category target size by longest axis (meters)
TARGET_LONGEST_M = {
    "helmet": 0.30,
    "plate_carrier": 0.55,
    "firearm": 0.95,
    "generic": 1.00,
}

KEYWORDS = {
    "helmet": ["helmet", "헬멧", "kevlar", "pasgt", "mich"],
    "plate_carrier": ["plate", "carrier", "vest", "조끼", "플레이트", "체스트리그"],
    "firearm": ["rifle", "gun", "weapon", "총", "소총", "pistol", "smg", "ak", "m4"],
}


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def infer_category(path: Path) -> str:
    s = str(path).lower()
    for cat, kws in KEYWORDS.items():
        if any(k in s for k in kws):
            return cat
    return "generic"


def import_model(path: Path):
    ext = path.suffix.lower()
    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    else:
        raise ValueError(f"Unsupported extension: {ext}")


def get_mesh_objects():
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def world_bbox(mesh_objs):
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in mesh_objs:
        for c in obj.bound_box:
            wc = obj.matrix_world @ Vector(c)
            mins.x = min(mins.x, wc.x)
            mins.y = min(mins.y, wc.y)
            mins.z = min(mins.z, wc.z)
            maxs.x = max(maxs.x, wc.x)
            maxs.y = max(maxs.y, wc.y)
            maxs.z = max(maxs.z, wc.z)
    return mins, maxs


def normalize_scale_and_pivot(mesh_objs, target_longest_m: float):
    mins, maxs = world_bbox(mesh_objs)
    dims = maxs - mins
    longest = max(dims.x, dims.y, dims.z)
    if longest <= 1e-8:
        return 1.0, dims

    scale = target_longest_m / longest

    for obj in mesh_objs:
        obj.scale = obj.scale * scale

    bpy.context.view_layer.update()

    mins2, maxs2 = world_bbox(mesh_objs)
    center = (mins2 + maxs2) * 0.5
    for obj in mesh_objs:
        obj.location = obj.location - center

    bpy.context.view_layer.update()
    return scale, dims


def find_missing_textures(mesh_objs):
    missing = []
    for obj in mesh_objs:
        mats = obj.data.materials
        for mat in mats:
            if not mat or not mat.use_nodes or not mat.node_tree:
                continue
            for node in mat.node_tree.nodes:
                if node.type != "TEX_IMAGE":
                    continue
                img = getattr(node, "image", None)
                if img is None:
                    missing.append((obj.name, mat.name, "NO_IMAGE_NODE_DATA"))
                    continue
                if img.packed_file:
                    continue
                fp = bpy.path.abspath(img.filepath_raw or img.filepath or "")
                if not fp or not os.path.exists(fp):
                    missing.append((obj.name, mat.name, fp or "MISSING_PATH"))
    return missing


def export_glb(out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=False,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
    )


def scan_models(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            yield p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_root", required=True)
    parser.add_argument("--output_root", required=True)
    parser.add_argument("--missing_log", required=True)
    args, _ = parser.parse_known_args()

    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output_root).resolve()
    missing_log = Path(args.missing_log).resolve()
    missing_log.parent.mkdir(parents=True, exist_ok=True)

    rows = [("source_file", "category", "object_name", "material_name", "missing_texture_path")]
    processed = 0

    for src in scan_models(input_root):
        try:
            clear_scene()
            import_model(src)
            mesh_objs = get_mesh_objects()
            if not mesh_objs:
                continue

            cat = infer_category(src)
            target = TARGET_LONGEST_M.get(cat, TARGET_LONGEST_M["generic"])
            normalize_scale_and_pivot(mesh_objs, target)

            missing = find_missing_textures(mesh_objs)
            for obj_name, mat_name, miss in missing:
                rows.append((str(src), cat, obj_name, mat_name, miss))

            rel = src.relative_to(input_root).with_suffix(".glb")
            out_file = output_root / rel
            export_glb(out_file)
            processed += 1
            print(f"[OK] {src} -> {out_file}")

        except Exception as e:
            rows.append((str(src), "error", "-", "-", f"IMPORT_OR_EXPORT_FAIL: {e}"))
            print(f"[ERR] {src}: {e}")

    with missing_log.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    print(f"\nProcessed: {processed}")
    print(f"Missing texture log: {missing_log}")


if __name__ == "__main__":
    main()
