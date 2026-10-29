---
name: build-reference-pbr
description: Create and verify PBR materials from surface references for Blender renders and real-time games. Use for reference-to-texture work, albedo cleanup, height and OpenGL normals, roughness, AO, seamless tiling, moss/dirt masks, Blender scripting, and glTF/Three.js material preparation. Deliver reproducible assets, physical scale metadata, visual checks, and honest execution status.
---

# Reference to PBR Materials

Turn a surface reference into a coherent, inspectable material. Complete the pipeline: inspect, prepare base color, establish height, derive maps, validate, assemble, and inspect in the destination. Treat single-image reconstruction as an artistic estimate unless measured data supports it. Do not promise scan quality from a photograph.

## Operating rules

- Inspect the reference first. Distinguish a surface photograph from a tutorial screenshot, material poster, or whole scene.
- Use the available image generator, Python environment, Blender installation, and game project. Do not require a particular AI model or paid service.
- Execute available work. If a capability is missing, finish the usable deliverables and state exactly which generation, render, or engine check remains unexecuted.
- Preserve originals and existing scene content. Use a new material output directory and a separate preview scene. Make overwrites explicit.
- Resolve bundled paths relative to this SKILL.md. Use included scripts when present. If supplied only this file, implement equivalent helpers from these requirements; never pretend missing helpers were run.

## 1. Establish the brief

Determine the surface, intended use, renderer/engine, tile coverage in metres, repeatability, image dimensions, and geometry/texture budget from the request and project. Ask only about an ambiguity that prevents useful work; otherwise record assumptions and proceed.

Choose a delivery mode:

- **Render:** Cycles with displacement where the shot benefits from it.
- **Game:** ordinary game geometry, tangent-space normals, and export-compatible channels. Add geometric relief only when silhouettes justify it.
- **Both:** shared source maps with separate render and game materials.

For browser/mobile worlds, default to Game. Preserve exact logos, artwork, signs, and road markings as separate authored layers or decals. Maintain consistent physical texture scale across adjacent surfaces. Choose resolution from viewing distance and budget; do not call upscaling newly captured detail.

## 2. Prepare clean base color

Select a representative patch. Remove perspective, cast shadows, highlights, reflections, exposure gradients, and unrelated objects while preserving material variation. Keep the original and record transformations.

Adapt this image-generation prompt:

> Create a material texture matching the supplied [SURFACE] reference. View the surface perpendicular to its plane, with orthographic appearance and uniform diffuse lighting. Preserve its material identity, proportions, grain, and colour variation. Remove cast shadows, directional highlights, reflections, perspective, objects, text, and background. Fill the image with the surface. [If needed: make opposite boundaries join naturally when repeated.] Output clean base colour at [DIMENSIONS]. Do not invent embossed detail or dramatic lighting.

Use an available image tool for generation or semantic editing. If unavailable, provide the exact prompt and continue with a suitable existing texture. Do not generate independent colour, height, and normal images without a correspondence plan.

## 3. Establish coordinates and tiling

Fix dimensions, crop, orientation, UV mapping, and tile coverage before deriving maps. Apply the same convention to every channel.

For tileable materials, inspect a 2×2 or 3×3 repeat and a half-width/half-height offset. Repair the base first, then rebuild dependent maps. Use periodic filters and derivatives for repeating data. A seamless prompt and wrapping arithmetic do not repair a nonseamless source.

For independent maps, compare structural landmarks and overlays. Prefer a known shared transformation. Do not prescribe optical flow as a universal albedo-to-height alignment fix. Rebuild normals after editing, resampling, or transforming height; do not warp normal RGB like ordinary colour.

## 4. Build the map set

| Channel | Storage / interpretation | Required treatment |
| --- | --- | --- |
| Base color | RGB PNG, sRGB | Keep lighting and baked AO out of the authoritative image. |
| Height | 16-bit grayscale PNG or suitable float EXR, data | Record midlevel and displacement range in metres. |
| Normal | RGB tangent-space, data | Default OpenGL/+Y; derive from final height or a consistent bake. |
| Roughness | Grayscale, data | White is rougher; choose from material behaviour, not darkness. |
| AO | Grayscale, data | Default white if unknown; label cavity estimates honestly. |
| Metallic | Grayscale, data | Default zero for nonmetals; identify mixed metals explicitly. |
| Masks | Grayscale, data | Preserve dimensions and inspect coverage. |
| ORM, if needed | RGB, data | Pack R=AO, G=roughness, B=metallic. |

Prefer compatible measured/authored height, then structural/procedural construction, then an explicitly labelled luminance approximation. Dark pigment need not be recessed; bright patches need not protrude. Test mortar, cracks, raised aggregate, and painted areas against intended relief. Make inversion deliberate.

For luminance estimation, decode sRGB before arithmetic. Use controlled smoothing and robust normalization; a constant image must produce flat height and neutral normals. Preserve imported height values instead of automatically stretching their range.

Scale derivatives by metres per texel and intended height range. With image columns increasing right and rows increasing down, construct an OpenGL normal proportional to `(-dh/dx, +dh/drow, 1)`, normalize, and encode to RGB. Verify direction with a known ramp and a moving light. Distinguish green-channel errors from inverted height or flipped UVs.

Choose roughness directly or use an authored map. Add variation only when justified. Do not infer metalness, wetness, or physical AO from brightness. Keep artistic cavity darkening optional and separate from base color.

Use `scripts/make_maps.py` and `references/pipeline-commands.md`. Inspect `--help` before changing arguments. Rebuild normals whenever height amplitude, tile coverage, or height pixels change.

## 5. Separate mixed materials

Author masks or use colour thresholds as an initial guess. Inspect an overlay and coverage; not every green pixel is moss.

Create a detailed, antialiased shading mask and a more softly filtered height mask. Express added relief in metres and check for spikes or clipped values. Scale filtering with resolution and use periodic boundaries when repeating.

Use `scripts/make_masks.py` when HSV segmentation suits the image. Blend appropriate material properties; do not impose fixed sheen, subsurface, or specular values on every moss surface. Rebuild game normals from the composite height after adding relief. Use specialized treatment for water, glass, transmission, or complex layered metals.

## 6. Assemble in Blender

Inspect the installed version and API. Use named sockets and capability checks. Set base color to sRGB and data images to Non-Color. Feed consistent UVs to all related channels; interpret normal textures through a tangent-space Normal Map node.

Target an explicit mesh with usable UVs. Create or update only owned materials and modifiers. Preserve unrelated slots, assignments, geometry, and scene settings. Check object/parent transforms and scene units before displacement.

For Render, use Cycles and a supported displacement mode. Convert recorded relief from metres into scene units. Inspect midlevel, texture coverage, silhouettes, and grazing angles. Estimate geometry growth before subdividing and enforce a budget. Do not automatically add six subdivision levels or use a universal strength of 0.1.

Avoid applying the same relief twice through full-height displacement plus a full normal map. Use the renderer's displacement/bump combination appropriately, or separate larger relief from independent fine normal detail.

Use `scripts/build_blender_material.py`; read `references/blender-usage.md` for scope and invocation. Save requested .blend output with portable texture references or packed assets.

## 7. Prepare real-time delivery

Use a simple Principled/metallic-roughness material and sensible geometry. Bake or simplify unsupported layered shaders into compatible channels. Keep Cycles showcase geometry separate from game assets.

Do not assume a .glb carries Blender shader displacement: core glTF has no height/displacement texture channel. Deliberately choose normal mapping, baked geometry, or destination-specific vertex displacement. Inspect the exported/reimported result and actual game scene.

For Three.js, mark colour textures sRGB and data maps NoColorSpace. Check UV selection, texture transforms, orientation, repeats, and packing against the installed version and loader. Use appropriate delivery sizes and mipmaps; assess GPU memory and performance separately from compressed download size.

## 8. Verify before completion

Run `scripts/validate_maps.py`; inspect its contact sheet and report. Check dimensions, actual height bit depth, channel interpretation, finite values, decoded normal lengths, and boundary discontinuities. Edge metrics are diagnostics, not proof of invisible repetition.

Where possible, render a neutral-lit plane and curved test object. Inspect grazing angles and silhouettes, move the light, and check a repeated surface at working distance. Add directional lighting to reveal artifacts. Apply AgX or another display transform only to presentation renders, never to data maps.

Verify crack/relief alignment, mask transitions, normal direction, displacement terraces/spikes, and environment scale. For games, inspect the destination engine and representative device/budget where accessible.

Report completion accurately:

- **Maps generated:** files exist; plausibility remains unchecked.
- **Maps checked:** numeric and visual map checks completed; identify outstanding rendering checks.
- **Blender verified:** material executed and rendered in the reported Blender version.
- **Engine verified:** material inspected in the reported runtime; identify device checks still outstanding.

Stop optional testing when concrete risks and required gates are resolved. Never describe a syntax check as a successful Blender render.

## 9. Deliver reproducible results

Provide maps, material manifest, validation report, map/repeat previews, and requested Blender/game assets. Record provenance, tool/version information, source hashes, actual dimensions, tile coverage, height range, normal convention, colour spaces, parameters, assumptions, and completed checks. Keep source masters separate from delivery variants.

Show useful previews. Explain intended use, physical scale, measured file sizes, actual tests, and remaining issues plainly. Fix actionable artifacts before making a polished poster. Do not use presentation lighting to conceal a broken surface.

## Supporting resources

- `references/pipeline-commands.md`: commands, helper limits, masks, and regeneration.
- `references/blender-usage.md`: Blender assembly and scene handling.
- `references/material-decisions.md`: surface decisions, export checks, and troubleshooting.
- `references/sources.md`: provenance and authoritative conventions.
