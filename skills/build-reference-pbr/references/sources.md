# Provenance and sources

Adapted from the tutorial supplied by the user, attributed there to **mukade死神 (@mukadeshinigami)**, titled **How to make pro-level PBR textures from a single reference (Blender + Claude)**, and the attached screenshot. No exact post permalink was provided; do not invent one. The bundled code is newly written with explicit estimation limits and operating checks. Do not claim to have verified the author's renders or model claims.

Consult primary documentation for the installed Blender/engine version. These references were checked or located through official documentation on 29 October 2026. A `latest` page can change.

| Topic | Primary source |
| --- | --- |
| Blender 4.5 material/displacement API | https://docs.blender.org/api/4.5/bpy.types.Material.html |
| Blender displacement modes | https://docs.blender.org/manual/en/4.5/render/cycles/material_settings.html |
| Displacement space, scale, midlevel | https://docs.blender.org/manual/en/latest/render/shader_nodes/displacement/displacement.html |
| Supported Blender glTF nodes/channels | https://github.com/KhronosGroup/glTF-Blender-IO/blob/main/docs/blender_docs/scene_gltf2.rst |
| glTF material conventions | https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html |
| Three.js colour/data interpretation | https://threejs.org/manual/pages/color-management.html |
| Optical-flow assumptions | https://docs.opencv.org/4.10.0/d4/dee/tutorial_optical_flow.html |
| Claude skill format and locations | https://code.claude.com/docs/en/skills |

The conservative inference rules, periodic numeric processing, geometry budget, source hashing, and scene-preservation policy are engineering decisions for this skill. They do not guarantee physical reconstruction or imply one source prescribes the entire workflow.
