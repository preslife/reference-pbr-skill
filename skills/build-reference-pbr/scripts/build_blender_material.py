#!/usr/bin/env python3
"""Build an explicitly scaled Blender PBR material from material.json.

Run with Blender 4.5+: blender scene.blend --background --python THIS_FILE --
  --maps /path/to/maps --object Surface --mode game --output result.blend

--help works in ordinary Python; material creation requires Blender's bpy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

OWNER = "reference-pbr-v1"
OWNER_KEY = "reference_pbr_owner"
SOURCE_KEY = "reference_pbr_source"
TARGET_KEY = "reference_pbr_target"
MODIFIER_KEY = "reference_pbr_subdivision"


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps", type=Path, required=True, help="Directory containing material.json")
    parser.add_argument("--object", help="Mesh object name; defaults to the active object")
    parser.add_argument("--mode", choices=("game", "render"), default="game")
    parser.add_argument("--subdivision-levels", type=int, default=0,
                        help="Explicit SIMPLE subdivision for render mode; default 0")
    parser.add_argument("--face-budget", type=int, default=250000,
                        help="Conservative maximum faces when adding subdivision")
    parser.add_argument("--output", type=Path, help="Optional new .blend destination")
    parser.add_argument("--pack-images", action="store_true",
                        help="Embed only the managed images used by this material in the .blend")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing --output")
    ns = parser.parse_args(argv)
    if ns.subdivision_levels < 0 or ns.subdivision_levels > 10:
        parser.error("--subdivision-levels must be in [0, 10]")
    if ns.face_budget < 1:
        parser.error("--face-budget must be positive")
    if ns.mode == "game" and ns.subdivision_levels:
        parser.error("Game mode does not add subdivision; omit --subdivision-levels")
    if ns.output:
        ns.output = ns.output.expanduser().resolve()
        if ns.output.suffix.lower() != ".blend":
            parser.error("--output must end in .blend")
        if ns.output.exists() and not ns.overwrite:
            parser.error("--output already exists; choose a new path or pass --overwrite")
    return ns


def positive_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return float(value)


def read_manifest(directory, mode):
    directory = directory.expanduser().resolve()
    manifest_path = directory / "material.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported material.json schema_version; expected 1")
    if not isinstance(manifest.get("material_name"), str) or not manifest["material_name"].strip():
        raise ValueError("material_name must be a non-empty string")
    required = ("basecolor", "roughness", "normal" if mode == "game" else "height")
    maps = manifest.get("maps", {})
    if not all(key in maps for key in required):
        raise ValueError(f"Manifest must declare maps: {', '.join(required)}")
    dimensions = manifest.get("resolution", {})
    width, height = dimensions.get("width"), dimensions.get("height")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 2 for v in (width, height)):
        raise ValueError("Manifest resolution must contain integer width and height >= 2")
    size = manifest.get("physical_size_m")
    if not isinstance(size, list) or len(size) != 2:
        raise ValueError("physical_size_m must be [width_metres, height_metres]")
    for i, value in enumerate(size):
        positive_number(value, f"physical_size_m[{i}]")
    height_range = manifest.get("height_range_m")
    if (isinstance(height_range, bool) or not isinstance(height_range, (int, float))
            or not math.isfinite(height_range) or height_range < 0):
        raise ValueError("height_range_m must be finite and nonnegative")
    mid = manifest.get("height_midlevel", 0.5)
    if not isinstance(mid, (int, float)) or not math.isfinite(mid) or not 0 <= mid <= 1:
        raise ValueError("height_midlevel must be in [0, 1]")
    if manifest.get("normal_convention") != "OpenGL":
        raise ValueError("Expected OpenGL (+Y) tangent normals; convert DirectX maps explicitly")
    if manifest.get("boundary_mode") not in ("wrap", "edge"):
        raise ValueError("boundary_mode must be 'wrap' or 'edge'")
    paths = {}
    for key, entry in maps.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError(f"Invalid map entry: {key}")
        relative = Path(entry["file"])
        path = (directory / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(directory):
            raise ValueError(f"Map paths must stay inside the material directory: {key}")
        if not path.is_file():
            raise ValueError(f"Missing {key} map: {path}")
        expected_space = "sRGB" if key == "basecolor" else "Non-Color"
        if entry.get("color_space") != expected_space:
            raise ValueError(f"{key} must declare color_space={expected_space!r}")
        paths[key] = path
    return manifest_path, manifest, paths


def socket(node, direction, name):
    result = getattr(node, direction).get(name)
    if result is None:
        raise RuntimeError(f"Unsupported Blender node API: {node.bl_idname}.{direction}[{name!r}]")
    return result


def check_unit_transform(obj):
    # The displacement node is in object space. Parent scale and shear also matter.
    matrix = obj.matrix_world.to_3x3()
    axes = [matrix.col[i] for i in range(3)]
    if any(abs(axis.length - 1.0) > 1e-5 for axis in axes):
        raise ValueError("Render mode needs unit effective object scale, including parents. "
                         "Apply scale on a working copy, then verify its UV scale and rerun.")
    if matrix.determinant() <= 0 or any(abs(axes[i].dot(axes[j])) > 1e-5
                                      for i in range(3) for j in range(i)):
        raise ValueError("Render mode requires a non-mirrored, non-sheared object transform; "
                         "resolve transforms on a working copy first")


def managed_modifier(obj):
    name = obj.get(MODIFIER_KEY)
    modifier = obj.modifiers.get(name) if isinstance(name, str) else None
    if modifier and modifier.type != "SUBSURF":
        raise ValueError("The saved managed modifier name now refers to another modifier type")
    return modifier


def subdivision_estimate(obj, levels, budget, own_modifier):
    """Conservatively bound common modifier stacks without evaluating heavy geometry."""
    if not levels:
        return None
    faces = len(obj.data.polygons)
    if faces == 0:
        raise ValueError("Cannot subdivide an empty mesh")
    # A first subdivision of an n-gon can yield n quads; use this upper bound.
    factor = max(4, max(len(poly.vertices) for poly in obj.data.polygons))
    safe = {
        "ARMATURE", "CAST", "CURVE", "DISPLACE", "HOOK", "LAPLACIANSMOOTH",
        "LAPLACIANDEFORM", "LATTICE", "MESH_CACHE", "MESH_DEFORM", "NORMAL_EDIT",
        "SHRINKWRAP", "SIMPLE_DEFORM", "SMOOTH", "CORRECTIVE_SMOOTH", "SURFACE_DEFORM",
        "WARP", "WAVE", "WEIGHTED_NORMAL", "UV_PROJECT", "UV_WARP", "DATA_TRANSFER",
        "VERTEX_WEIGHT_EDIT", "VERTEX_WEIGHT_MIX", "VERTEX_WEIGHT_PROXIMITY",
    }
    for modifier in obj.modifiers:
        if modifier == own_modifier or not (modifier.show_viewport or modifier.show_render):
            continue
        if modifier.type == "SUBSURF":
            existing = max(modifier.levels, modifier.render_levels)
            if existing:
                faces *= factor * 4 ** (existing - 1)
                factor = 4
        elif modifier.type == "MIRROR":
            faces *= 2 ** sum(modifier.use_axis)
        elif modifier.type == "ARRAY" and modifier.fit_type == "FIXED_COUNT":
            # Array caps can add otherwise unbounded geometry.
            if modifier.start_cap or modifier.end_cap:
                raise ValueError("Cannot safely budget an Array with caps; use a resolved working copy")
            faces *= modifier.count
        elif modifier.type not in safe:
            raise ValueError(f"Cannot conservatively budget {modifier.type} modifier {modifier.name!r}. "
                             "Resolve its geometry on a working copy or use zero added subdivision.")
    faces *= factor * 4 ** (levels - 1)
    if faces > budget:
        raise ValueError(f"Subdivision could produce about {faces:,} faces, exceeding the "
                         f"{budget:,} face budget. Reduce levels or deliberately raise the budget.")
    return faces


def build_material(ns):
    import bpy

    if bpy.app.version < (4, 5, 0):
        raise RuntimeError("This script targets Blender 4.5+; verify a compatible API before adapting it")
    manifest_path, manifest, paths = read_manifest(ns.maps, ns.mode)
    scene = bpy.context.scene
    obj = bpy.data.objects.get(ns.object) if ns.object else bpy.context.object
    if obj is None or obj.type != "MESH":
        raise ValueError("Choose an existing mesh with --object, or select a mesh before running")
    if obj.library or obj.data.library:
        raise ValueError("Use an editable local working copy of the linked object")
    uv = obj.data.uv_layers.active
    if uv is None:
        raise ValueError("The object needs an active UV map. Unwrap and verify physical texture scale first.")
    if not obj.material_slots and obj.data.users > 1:
        raise ValueError("The mesh data is shared and has no material slots. Make an explicit single-user "
                         "working copy before adding a material slot.")
    own_modifier = managed_modifier(obj)
    estimated_faces = None
    if ns.mode == "render":
        check_unit_transform(obj)
        estimated_faces = subdivision_estimate(obj, ns.subdivision_levels, ns.face_budget, own_modifier)
    scene_metres_per_unit = positive_number(scene.unit_settings.scale_length, "scene unit scale_length")

    # Load isolated image datablocks so a color-space change cannot alter another material.
    images = {}
    needed = ["basecolor", "roughness", "normal" if ns.mode == "game" else "height"]
    if "metallic" in paths:
        needed.append("metallic")
    expected_size = (manifest["resolution"]["width"], manifest["resolution"]["height"])
    for key in needed:
        image_key = f"{paths[key]}|{'sRGB' if key == 'basecolor' else 'Non-Color'}"
        im = next((im for im in bpy.data.images if im.get(OWNER_KEY) == OWNER
                   and im.get(SOURCE_KEY) == image_key), None)
        if im is None:
            im = bpy.data.images.load(str(paths[key]), check_existing=False)
            im[OWNER_KEY] = OWNER
            im[SOURCE_KEY] = image_key
        else:
            im.reload()
        if tuple(im.size) != expected_size:
            raise ValueError(f"{key} map size {tuple(im.size)} does not match {expected_size}")
        im.colorspace_settings.name = "sRGB" if key == "basecolor" else "Non-Color"
        images[key] = im

    material = next((m for m in bpy.data.materials if m.library is None
                     and m.get(OWNER_KEY) == OWNER and m.get(SOURCE_KEY) == str(manifest_path)
                     and m.get(TARGET_KEY) == obj.name), None)
    if material is None:
        material = bpy.data.materials.new(f"ReferencePBR · {manifest['material_name']} · {obj.name}")
    material[OWNER_KEY] = OWNER
    material[SOURCE_KEY] = str(manifest_path)
    material[TARGET_KEY] = obj.name
    material["reference_pbr_mode"] = ns.mode
    material["reference_pbr_physical_size_m"] = manifest["physical_size_m"]
    material["reference_pbr_height_range_m"] = manifest["height_range_m"]
    material.use_nodes = True
    if not hasattr(material, "displacement_method"):
        raise RuntimeError("Material.displacement_method is missing in this Blender build")
    nodes, links = material.node_tree.nodes, material.node_tree.links
    # This material belongs to this builder; unrelated materials are never cleared.
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (700, 80)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (380, 160)
    socket(shader, "inputs", "Metallic").default_value = 0.0
    links.new(socket(shader, "outputs", "BSDF"), socket(output, "inputs", "Surface"))
    uv_node = nodes.new("ShaderNodeUVMap")
    uv_node.uv_map = uv.name
    uv_node.location = (-900, 100)

    def texture(key, y):
        node = nodes.new("ShaderNodeTexImage")
        node.name = f"ReferencePBR {key}"
        node.label = f"{key} · {'sRGB' if key == 'basecolor' else 'Non-Color'}"
        node.image = images[key]
        node.extension = "REPEAT" if manifest["boundary_mode"] == "wrap" else "EXTEND"
        node.interpolation = "Linear"
        node.location = (-600, y)
        links.new(socket(uv_node, "outputs", "UV"), socket(node, "inputs", "Vector"))
        return node

    base = texture("basecolor", 500)
    rough = texture("roughness", 180)
    links.new(socket(base, "outputs", "Color"), socket(shader, "inputs", "Base Color"))
    links.new(socket(rough, "outputs", "Color"), socket(shader, "inputs", "Roughness"))
    if "metallic" in images:
        metallic = texture("metallic", -140)
        links.new(socket(metallic, "outputs", "Color"), socket(shader, "inputs", "Metallic"))

    if ns.mode == "game":
        normal_texture = texture("normal", -460)
        normal = nodes.new("ShaderNodeNormalMap")
        normal.space = "TANGENT"
        normal.uv_map = uv.name
        normal.location = (40, -220)
        socket(normal, "inputs", "Strength").default_value = 1.0
        links.new(socket(normal_texture, "outputs", "Color"), socket(normal, "inputs", "Color"))
        links.new(socket(normal, "outputs", "Normal"), socket(shader, "inputs", "Normal"))
        material.displacement_method = "BUMP"
        if own_modifier:
            own_modifier.show_viewport = False
            own_modifier.show_render = False
    else:
        height = texture("height", -460)
        displacement = nodes.new("ShaderNodeDisplacement")
        displacement.space = "OBJECT"
        displacement.location = (380, -220)
        socket(displacement, "inputs", "Midlevel").default_value = manifest.get("height_midlevel", 0.5)
        socket(displacement, "inputs", "Scale").default_value = (
            manifest["height_range_m"] / scene_metres_per_unit)
        links.new(socket(height, "outputs", "Color"), socket(displacement, "inputs", "Height"))
        links.new(socket(displacement, "outputs", "Displacement"), socket(output, "inputs", "Displacement"))
        # Cycles handles the remaining bump detail. Do not also attach the same full-height normal.
        material.displacement_method = "BOTH"
        scene.render.engine = "CYCLES"
        if ns.subdivision_levels:
            if own_modifier is None:
                own_modifier = obj.modifiers.new("ReferencePBR Subdivision", "SUBSURF")
                obj[MODIFIER_KEY] = own_modifier.name
            own_modifier.subdivision_type = "SIMPLE"
            own_modifier.levels = ns.subdivision_levels
            own_modifier.render_levels = ns.subdivision_levels
            own_modifier.show_viewport = True
            own_modifier.show_render = True
        elif own_modifier:
            own_modifier.show_viewport = False
            own_modifier.show_render = False

    # Replace only the active object slot. Other slots and mesh users keep their materials.
    if obj.material_slots:
        slot = obj.material_slots[obj.active_material_index]
        slot.link = "OBJECT"
        slot.material = material
    else:
        obj.data.materials.append(material)
    if ns.pack_images:
        for im in images.values():
            im.pack()
    if ns.output:
        ns.output.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(ns.output), check_existing=False)
    warnings = [
        "UV physical scale is not inferred: one UV tile must cover physical_size_m on the surface.",
        "AO is retained as separate data; no AO has been multiplied into base color.",
        "Inspect lighting, relief, seams, and the target engine; building nodes is not visual approval.",
    ]
    if ns.mode == "render":
        warnings.append("Render mode sets the current scene engine to Cycles. Existing lights and cameras are retained.")
        if not ns.subdivision_levels:
            warnings.append("No subdivision added: insufficient existing geometry limits the displaced silhouette.")
    result = {
        "blender_version": bpy.app.version_string,
        "object": obj.name,
        "material": material.name,
        "mode": ns.mode,
        "physical_size_m": manifest["physical_size_m"],
        "height_range_m": manifest["height_range_m"],
        "scene_metres_per_unit": scene_metres_per_unit,
        "estimated_subdivided_faces": estimated_faces,
        "packed_image_count": len(images) if ns.pack_images else 0,
        "output": str(ns.output) if ns.output else None,
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2))
    return result


def main(argv=None):
    ns = arguments(argv)
    try:
        return build_material(ns)
    except ModuleNotFoundError as exc:
        if exc.name == "bpy":
            raise SystemExit("ERROR: Run material creation inside Blender 4.5+ (bpy is unavailable).") from exc
        raise
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    cli = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(cli)
