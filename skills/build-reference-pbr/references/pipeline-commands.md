# Pipeline commands

## Contents

- Environment and paths
- Generate map sets
- Generate material masks
- Validate and inspect
- Assemble and deliver
- Helper boundaries

## Environment and paths

Use Python 3.10+ with NumPy and Pillow for the image helpers. Blender runs its own Python; do not assume it shares the shell's packages. The Blender builder needs only Blender's bpy plus its standard library.

Check dependencies before installing anything:

```bash
python3 -c 'import numpy, PIL; print(numpy.__version__, PIL.__version__)'
```

If dependencies are absent and installation is permitted, create a project-local virtual environment and install NumPy and Pillow there. Keep packages and generated outputs outside the skill folder. Record versions used. Do not change global packages just to run this workflow.

Set the skill path to the folder that actually contains this SKILL.md. The following shell examples assume the agent is working in a separate material-project directory:

```bash
PBR_SKILL_DIR="/absolute/path/to/build-reference-pbr"
python3 "$PBR_SKILL_DIR/scripts/make_maps.py" --help
```

Replace placeholders with observed paths. Do not paste an unexpanded example as if it were a completed operation.

## Generate map sets

Prefer a registered authored height map when available:

```bash
python3 "$PBR_SKILL_DIR/scripts/make_maps.py" source/basecolor.png \
  --out output/stone-v1 \
  --name "Stone study" \
  --tile-size-m 2 2 \
  --height-range-m 0.01 \
  --height-input source/height.png \
  --roughness 0.8 \
  --tileable \
  --pack-orm
```

Here, 2×2 m coverage, 10 mm relief range, and roughness 0.8 are illustrative artist-selected parameters. They are not recovered measurements or universal stone settings. Use `--tileable` only for intended repeating materials and then inspect the repeats.

For an explicitly accepted luminance estimate, replace `--height-input source/height.png` with:

```text
--height-source luminance --height-blur 6
```

The blur radius is expressed at a 1024 px reference size and scales with the smaller image dimension. It affects estimated height only. An imported numerical height map is preserved, including its existing range. Use `--invert-height` only after checking feature polarity. The current helper accepts 8/16-bit grayscale PNG height, not EXR; use a suitable data-preserving EXR workflow explicitly if needed.

Use `--roughness-input source/roughness.png` for registered authored roughness. Default metallic is zero. No metallic texture is inferred; the helper accepts a constant `--metallic` value. Mixed metals need an authored extension or bake.

AO defaults to white. `--cavity-strength 2`, for example, enables a local height-cavity approximation; record it as an artistic proxy, not measured or baked ambient occlusion. Do not enable it merely because a map looks more dramatic when darkened.

The helper writes `basecolor.png`, `height.png`, `normal.png`, `roughness.png`, `ao.png`, `metallic.png`, optional `orm.png`, and `material.json`. It refuses to overwrite inputs, to silently resize channels, or to ignore ambiguous EXIF orientation and transparency. Resolve those issues consistently before retrying.

Use a new output directory for another candidate. Pass `--overwrite` only when replacing that generated candidate intentionally. Source hashes and assumptions are recorded; add the generation prompt, original reference provenance, and image-tool version to the delivery notes.

## Generate material masks

Use HSV segmentation only when it fits the actual image. Example green-region selection:

```bash
python3 "$PBR_SKILL_DIR/scripts/make_masks.py" output/stone-v1/basecolor.png \
  --out output/stone-v1-masks \
  --hue 50 110 \
  --saturation 0.25 1 \
  --value 0 0.7 \
  --shade-radius 1 \
  --height-radius 12 \
  --tileable
```

Hue uses degrees; saturation and value use 0–1. A hue interval whose minimum exceeds its maximum wraps through red. Radii are source pixels, so adapt them to resolution and intended physical transition width.

Inspect the overlay and coverage before applying either mask. The helper writes `mask_shade.png`, `mask_height.png`, `mask_preview.png`, and its parameter record. It does not change the source material manifest or add height automatically. Follow the composite-height recipe in `material-decisions.md`, update the physical encoding, and regenerate normals if geometry changes.

## Validate and inspect

```bash
python3 "$PBR_SKILL_DIR/scripts/validate_maps.py" output/stone-v1
```

Read `validation.json` and inspect `contact_sheet.png`. The sheet includes channel views, a repeated base texture, and an offset view. Compare full-resolution images too; small thumbnails can conceal seams or quantization.

Use `--report PATH --preview PATH` for alternate diagnostic destinations. Pass `--overwrite` to refresh existing diagnostics intentionally. The validator refuses to replace declared source maps or the material manifest.

The report's `passed` flag means package integrity and numerical consistency only. Its normal/height comparison expects the full normal to derive from the package's declared height, physical dimensions, and range. A separately baked normal with intentional independent detail needs a correspondingly adapted validation rule and a visual check, not silent acceptance or automatic removal of useful detail.

## Assemble and deliver

Follow `blender-usage.md` for the Blender builder. Run the material on a working copy with a correctly scaled UV layout. Build a separate neutral preview scene for the plane, curved object, and changing-light checks. The helper does not create those scenes automatically.

For a game, export a compatible material, inspect the actual file channels, and load it in the target runtime. AO/ORM files are not exported merely by existing beside the Blender file. Complete the destination-specific connection.

Keep `material.json`, diagnostics, maps, source notes, and requested exports together. Add actual Blender/engine versions, checks performed, exact delivery dimensions, and measured file sizes. If an engine or Blender is unavailable, label the outstanding validation clearly.

## Helper boundaries

These scripts deliberately do not perform semantic de-lighting, perspective correction, optical-flow registration, automatic physical height recovery, water/glass shading, UV unwrapping, automatic scene generation, or engine integration. The agent handles relevant steps using the established workflow and available tools. Do not claim the scripts alone complete them.

Synthetic checks exercised flat and sloped inputs, true 16-bit data, periodic edges, channel packing, source preservation, and invalid-input errors. Blender assembly was exercised in Blender 4.5.3 LTS, including a small Cycles CPU render. Recheck version-sensitive behavior when changing Blender or scripts; a prior test does not visually approve a new material.
