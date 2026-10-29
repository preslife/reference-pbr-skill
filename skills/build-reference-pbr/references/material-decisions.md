# Material decisions and troubleshooting

## Surface decisions

Use these as decision rules, not measured presets. Select numeric starting points from scale and appearance; label assumptions.

| Surface | Height decision | Reflectance decision | Main rejection check |
| --- | --- | --- | --- |
| Asphalt | Separate aggregate from paint and stains; use plausible grain size. | Start dielectric; author wet/dry changes separately. | White markings must not become raised rocks. |
| Brick / paving | Identify faces, mortar, and wear structurally; set joint depth explicitly. | Separate dirt and moisture where justified. | Dark bricks must not be recessed solely because of pigment. |
| Concrete | Keep pores small relative to tile coverage; author large cracks. | Use restrained variation rather than noise everywhere. | Rust stains must not become holes. |
| Rock / moss | Separate rock topology from green coloration; soften moss volume. | Treat moss as its own material region. | Mask boundaries must not form needles. |
| Wood | Follow grain and joints; separate colour stripes from depth. | Distinguish varnished from unfinished timber. | Dark grain must not become implausibly deep trenches. |
| Fabric | Establish weave scale and direction. | Use appropriate fibre response; check sheen export support. | Normal intensity must not turn threads into rigid ridges. |
| Sand / soil | Separate slopes from grain and footprints. | Author wet regions explicitly. | Illumination gradients must not tilt the surface. |
| Painted metal | Author coating and metal regions deliberately. | Keep painted regions dielectric. | Shiny does not automatically mean metallic. |
| Water / glass | Use dedicated geometry/transmission treatment. | Do not solve using a dark roughness mask alone. | Verify destination support and lighting. |

For a 2 m square test tile with an artist-selected 0.01 m height range, normalized height spans 10 mm peak to peak. Midlevel 0.5 places the nominal surface near the middle. This is a demonstration, not a recommendation for every surface. Imported height can occupy only part of 0–1; preserve that fraction.

## Mask integration

Use the shading mask to blend justified properties. Preserve canonical base color. Composite relief in physical units:

`z_m = (base_height - base_midlevel) * base_range_m + mask_height * added_height_m`

If the composite exceeds the original encoding range, choose a new range and midlevel that represent it without clipping. Record them. Derive normals from the final height using the same physical tile coverage. Do not add moss to render displacement while retaining a game normal calculated from unchanged rock height.

The mask helper creates two masks, parameters, and an overlay. It does not perform semantic identification, composite height, or alter the Blender node graph automatically. Complete those steps explicitly when needed.

A single Principled shader with blended properties may suffice for mixed dielectrics. Use multiple shaders when the material requires them. Simplify or bake the render setup for the destination exporter.

## Alignment and periodicity

Equal dimensions establish equal grids, not equivalent physical interpretation. Check crop, orientation, and landmarks. Avoid unconstrained optical flow across unrelated map types: matching an albedo shadow to a height ridge can improve numeric alignment while damaging the material.

Assess boundary differences against interior differences. High-frequency texture can have large opposite-edge differences; broad colour gradients can repeat visibly despite modest edge metrics. Inspect repeat and offset previews at working scale.

Repair colour, structure, and masks coherently. Regenerate normals after editing/resampling height. Resize scalar maps as data. To resize normals directly, decode vectors, filter, renormalize, and re-encode. Pack ORM only after dimensions and orientation match.

## Game delivery

Retain source masters. Choose resolution and compression for the destination and devices. Account for normal-map compression needs and decoded GPU memory, including mipmaps.

Inspect exporter-supported nodes. Supply occlusion through its recognized hookup instead of baking it into base colour. Inspect exported channels and UV sets, then reimport or view the asset. Successful export is not visual verification.

For Three.js, inspect installed APIs and loader conventions. Loader-managed glTF textures and manually loaded textures can differ in orientation handling. Do not blindly flip every image or add an obsolete UV attribute.

Compare baseline and candidate with the same lighting. Inspect intended camera distance, shimmer, repetition, geometry, memory, draw calls, and frame time. Retain large displaced meshes for renders unless game silhouettes and budgets justify them.

## Troubleshooting

| Symptom | Investigate | Action |
| --- | --- | --- |
| Plastic stone | Roughness, data colour space, scale, lighting | Correct interpretation before adding noise. |
| Smooth silhouette | Normal-only mode or insufficient geometry | Use budgeted geometric relief where necessary. |
| Moss needles | Hard height mask or excessive amplitude | Soften the height mask and reduce physical relief. |
| Terraces | Height quantization | Check the actual file header; use 16-bit or float data. |
| Inverted grooves | Height polarity, normal convention, UV orientation | Test a known slope under moving light; fix the actual cause. |
| Dark seams | Nonperiodic source/filtering, UVs, tangents | Inspect repeat boundaries separately from mesh seams. |
| Inflated edges | Excessive displacement or poor UV scale | Restore physical scale; refine only needed geometry. |
| Fixed shadow | Baked lighting in base colour | Clean or regenerate base colour. |
| Dirt becomes relief | Luminance treated as geometry | Author height independently of pigment. |
| GLB differs | Unsupported nodes/displacement or missing channels | Simplify/bake and retest the destination. |
| Grain changes size | Inconsistent UV density | Establish shared physical coverage. |

Use a plane for repeatability and scale; use a curved object for shading and UV problems. Recognize UV-sphere pole distortion. Neither substitutes for the destination mesh.
