# Blender material assembly

## Run the builder

Target Blender 4.5 or later. Check the installed version and the actual node API before adapting for other versions. Use a working `.blend` copy and an existing mesh with a verified active UV map. The script does not generate geometry, unwrap objects, build a lighting rig, or render a poster.

Run from a terminal, replacing the example paths and object name:

```bash
blender scene.blend --background --python /path/to/skill/scripts/build_blender_material.py -- \
  --maps /path/to/material --object Surface --mode game --pack-images --output material-game.blend
```

For a Cycles render, request a deliberately budgeted amount of geometry:

```bash
blender scene.blend --background --python /path/to/skill/scripts/build_blender_material.py -- \
  --maps /path/to/material --object Surface --mode render \
  --subdivision-levels 3 --face-budget 250000 --output material-render.blend
```

Treat subdivision level 3 as an example, not a recommendation for every mesh. Start from the source mesh count and the needed silhouette detail. Unsupported topology-changing modifiers require an explicit working copy or zero added subdivision; the builder avoids evaluating an unknown heavy stack to guess its cost.

Use the same code from Blender's Python Console or Scripting workspace:

```python
import runpy
builder = runpy.run_path('/path/to/skill/scripts/build_blender_material.py', run_name='reference_pbr')
builder['main'](['--maps', '/path/to/material', '--object', 'Surface', '--mode', 'game'])
```

Omit `--object` only when the intended mesh is active. Run the script with `--help` to inspect current options. `--output` is optional and refuses to replace an existing file without `--overwrite`.

Use `--pack-images` for a portable saved `.blend`: it embeds only the managed images used by this material, leaving unrelated images alone. Without this flag, image files stay external at their existing paths; ship the map directory and resolve those paths before moving the file. Keep the original map set and manifest as separate deliverables even when the `.blend` is packed.

## Preserve the scene

The builder owns the material tagged for the target object and manifest. Rerunning rebuilds that managed material, including any manual edits to it. Duplicate the material first if those edits need preserving. The builder replaces only the object's active material slot, uses an object-level slot assignment when a slot exists, and preserves other slots. For a mesh with multiple materials, select the intended active slot; polygon assignments do not change.

The builder never clears the scene, deletes existing materials, replaces unrelated modifiers, applies transforms, or saves a file unless `--output` is supplied. Render mode explicitly switches the current scene engine to Cycles. Managed images use separate datablocks so changing their color space does not change an unrelated material. A managed subdivision modifier is reused; switching to game mode disables that modifier. Any other existing subdivision remains your responsibility. Game mode does not automatically reduce the source mesh or certify its performance.

## Match physical scale

`material.json` records the size of one tile in metres and the full height range in metres. Verify the UV layout so one repeat covers that area on the actual surface. Do not infer this from the object bounding box alone, especially on a sphere, rotated UV islands, or irregular mesh.

In render mode the builder requires unit effective object scale, including parents, with no reflection or shear. It uses object-space displacement and calculates:

```text
displacement scale in Blender units = height_range_m / scene.unit_settings.scale_length
offset in metres = (height - height_midlevel) × height_range_m
```

A 0.01 m range and midlevel 0.5 allow a nominal −5 mm to +5 mm offset for height values 0–1. The actual range is smaller if the map does not use both endpoints. Do not use a universal node scale of 0.1: its effect depends on scene units and the object's scale. Changing a tile's physical footprint also changes the normal-map slope calculation; regenerate normals using the intended dimensions.

Use `height_range_m: 0` for a flat surface. Both modes accept this; render mode connects a zero-amplitude displacement. The tile dimensions must still be positive.

## Choose shading by target

| Target | Connections | Consequence |
| --- | --- | --- |
| Game | Base color → Principled Base Color; roughness → Roughness; optional metallic → Metallic; +Y tangent normal → Normal Map → Normal | No displacement is connected. No new subdivision is added. |
| Render | Base color, roughness and optional metallic as above; height → Displacement → Material Output; Cycles `BOTH` | Cycles handles true displacement plus remaining bump detail. The full normal derived from that same height is deliberately not applied again. |

Use sRGB only for base color. Use Non-Color for height, normals, roughness, metallic, masks and packed channels. The normal node and all texture nodes use the same named UV map. The builder keeps AO separate rather than baking it into the base color or introducing a second darkening contribution.

For a more specialized render setup, divide large displacement and fine normal detail by frequency deliberately, or use a normal map containing independent detail. Do not layer the same full-height normal over true displacement just to make it stronger.

## Add mixed materials deliberately

The base builder implements one Principled material. Treat moss, exposed metal, damp dirt or other mixtures as a reviewed extension rather than guessed automatic behavior:

1. Inspect `mask_preview.png` at full resolution and in a repeated tile.
2. Use `mask_shade.png` to mix physically justified parameters or separate BSDFs. Do not assume every green pixel is moss or every dark pixel is water.
3. For extra relief, use `mask_height.png` with a documented height contribution in metres, combine it with the base height, and inspect the result for narrow spikes.
4. Regenerate the game normal from the final combined height. Preserve its zero point and amplitude; do not silently normalize after adding material relief.
5. If the rendered blend needs separate sheen, transmission or subsurface behavior, validate support in the target engine and bake a simplified portable material where necessary.

Do not claim arbitrary Blender shader graphs export as-is to glTF. Keep the game graph simple, use baked UV textures where required, and inspect the exported GLB in the actual renderer. ORM convention is R = occlusion, G = roughness, B = metallic. The builder leaves AO/ORM wiring to the target-specific export workflow; its AO file is not automatically exported simply because it exists beside the `.blend` file.

## Inspect and present

Render an isolated material plane at a grazing angle and a UV sphere with soft neutral light. A plane checks relief and tiling; a sphere exposes wrapping and silhouette problems but also has UV distortion at its poles. Examine at least two light directions. Use neutral backgrounds and label the rendering transform (for example AgX), map resolution, actual physical tile size, and displacement range.

Include a labelled map strip and a 2×2 tile view. Record actual render and engine checks. Do not call an unrendered node graph visually verified. Do not apply AgX or display transforms to normal, height, roughness or other data textures.

## Primary references

- [Blender 4.5 Material API: displacement_method](https://docs.blender.org/api/4.5/bpy.types.Material.html)
- [Blender 4.5 Displacement node API: object and world space](https://docs.blender.org/api/4.5/bpy.types.ShaderNodeDisplacement.html)
- [Blender 4.5 Normal Map node API: tangent space and UV map](https://docs.blender.org/api/4.5/bpy.types.ShaderNodeNormalMap.html)
- [Blender manual: displacement methods](https://docs.blender.org/manual/en/4.5/render/materials/components/displacement.html)
- [Blender manual: glTF export](https://docs.blender.org/manual/en/4.5/addons/import_export/scene_gltf2.html)
