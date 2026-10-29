#!/usr/bin/env python3
"""Reproduce the synthetic fixture preview in a fresh background Blender process.

This resets Blender to an empty scene and overwrites this example's generated
previews, blender_checks.json, and material_preview.blend. Run only as documented.
"""
from pathlib import Path
import json
import math
import runpy
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
SKILL_DIR = ROOT.parents[1] / 'skills' / 'build-reference-pbr'
builder = runpy.run_path(str(SKILL_DIR / 'scripts' / 'build_blender_material.py'), run_name='reference_pbr')
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.resolution_x = 960
scene.render.resolution_y = 640
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.image_settings.color_depth = '8'
scene.render.film_transparent = False
scene.view_settings.view_transform = 'AgX'
scene.render.threads_mode = 'FIXED'
scene.render.threads = 6

world = bpy.data.worlds.new('Neutral preview world')
world.use_nodes = True
world.node_tree.nodes.get('Background').inputs['Color'].default_value = (0.3, 0.3, 0.3, 1)
world.node_tree.nodes.get('Background').inputs['Strength'].default_value = 0.3
scene.world = world

def target(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()

bpy.ops.mesh.primitive_plane_add(size=4, location=(-0.9, 0, 0))
plane = bpy.context.object
plane.name = 'RepeatPlane_4m_2x2Tiles'
for loop in plane.data.uv_layers.active.data:
    loop.uv *= 2.0
plane['coverage_note'] = '4m by 4m plane; UV 0..2 in U and V; each tile covers 2m by 2m.'
plane_result = builder['main'](['--maps', str(ROOT/'maps'), '--object', plane.name,
                              '--mode', 'game', '--pack-images'])

radius = 0.7
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius, location=(2.0, 0.1, radius))
sphere = bpy.context.object
sphere.name = 'CurvedUVTest'
for poly in sphere.data.polygons:
    poly.use_smooth = True
for loop in sphere.data.uv_layers.active.data:
    loop.uv.x *= (2*math.pi*radius)/2.0
    loop.uv.y *= (math.pi*radius)/2.0
sphere['coverage_note'] = '2m per UV repeat at equator and along meridian; UV-sphere distortion grows toward poles.'
sphere_result = builder['main'](['--maps', str(ROOT/'maps'), '--object', sphere.name,
                               '--mode', 'game', '--pack-images'])

bpy.ops.object.camera_add(location=(-0.1, -7, 5))
camera = bpy.context.object
camera.name = 'MaterialPreviewCamera'
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 7.1
target(camera, (-0.1, 0, 0.25))
scene.camera = camera

bpy.ops.object.light_add(type='AREA', location=(-3.5, -4, 5))
key = bpy.context.object
key.name = 'MovingNeutralKey'
key.data.energy = 1400
key.data.shape = 'DISK'
key.data.size = 3.0
key.data.color = (1, 1, 1)
target(key, (0, 0, 0))

checks = {
    'blender_version': bpy.app.version_string,
    'engine': 'Cycles CPU',
    'samples': scene.cycles.samples,
    'display_transform': scene.view_settings.view_transform,
    'resolution': [scene.render.resolution_x, scene.render.resolution_y],
    'mode': 'Game normal mapping; no displacement or subdivision',
    'plane': plane_result,
    'sphere': sphere_result,
    'plane_faces': len(plane.data.polygons),
    'sphere_faces': len(sphere.data.polygons),
    'light_positions': [],
    'renders': [],
}
for label, position in [('left', (-3.5, -4, 5)), ('right', (3.5, 2.5, 3))]:
    key.location = position
    target(key, (0, 0, 0))
    path = ROOT / 'previews' / f'blender_{label}.png'
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    checks['light_positions'].append(list(position))
    checks['renders'].append(str(path.relative_to(ROOT)))

key.location = (-3.5, -4, 5)
target(key, (0, 0, 0))
scene.render.filepath = '//previews/blender_left.png'
for im in bpy.data.images:
    if im.get('reference_pbr_owner'):
        if not im.packed_file:
            raise RuntimeError(f'Image not packed: {im.name}')
        im.filepath = '//maps/' + Path(im.filepath).name
scene['preview_note'] = '2m tile; full height encoding 6mm; actual sampled relief 3.120073mm; game shader only.'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'material_preview.blend'), check_existing=False)

# Reopen the actual saved asset and inspect its portable image content and shader.
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'material_preview.blend'))
managed = [im for im in bpy.data.images if im.get('reference_pbr_owner')]
checks['saved_blend_reopened'] = True
checks['packed_image_count_after_reopen'] = len(managed)
checks['all_managed_images_packed'] = all(bool(im.packed_file) for im in managed)
checks['all_managed_paths_relative'] = all(im.filepath.startswith('//') for im in managed)
checks['no_geometry_displacement'] = all(
    len(obj.modifiers) == 0 and
    not next(n for n in obj.active_material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL').inputs['Displacement'].is_linked
    for obj in (bpy.data.objects['RepeatPlane_4m_2x2Tiles'], bpy.data.objects['CurvedUVTest'])
)
(ROOT/'blender_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps({k:v for k,v in checks.items() if k not in ('plane','sphere')},indent=2))
