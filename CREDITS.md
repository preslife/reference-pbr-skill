# Credits

## Original technique

This project is **based on the reference-to-PBR technique shared by mukade死神 ([@mukadeshinigami](https://x.com/mukadeshinigami))** in:

**“How to make pro-level PBR textures from a single reference (Blender + Claude)”**

The original technique describes preparing a clean texture from a surface reference, producing related PBR maps, separating mixed materials with shading and softened height masks, assembling a Blender material, tuning displacement, and presenting the result. Credit for sharing that technique belongs to mukade死神.

The article text and author attribution were supplied as the starting material for this project. The exact article/post permalink could not be independently verified; the link above is the author's X profile, not a claimed permalink to the article. No affiliation or endorsement is implied.

## This implementation

Published by [preslife](https://github.com/preslife). The project adapts the technique into a Codex/Claude Code skill and adds a tested implementation with:

- Explicit assumptions for height, roughness and AO.
- Physical scale metadata and OpenGL normals derived from the saved height.
- Periodic processing and repeat/offset diagnostics.
- Genuine 16-bit height handling and map integrity checks.
- Separate Blender render and game workflows.
- Preservation of unrelated Blender materials and scene content.
- Portable synthetic fixtures, test renders and numerical checks.

The repository's MIT licence applies to this implementation and its original documentation. It does not relicense the source article or its author's photographs, images or artwork. The article and social-media screenshot are not included.

## Test images

All images in `examples/synthetic-stone-moss/` are procedural sources or outputs generated during this project's own tests. They demonstrate reproducible material behaviour and are labelled as synthetic. They do not depict the original author's photorealistic material and do not imply equivalent visual quality.

## Technical references

Blender, Khronos, Three.js, OpenCV and agent-skill documentation informed the implementation's conventions. Links are collected in [the skill's sources document](skills/build-reference-pbr/references/sources.md).
