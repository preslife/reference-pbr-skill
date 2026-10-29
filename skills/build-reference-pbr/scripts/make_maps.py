#!/usr/bin/env python3
"""Create explicitly estimated PBR maps from one registered basecolor/height pair.

Dependencies: numpy, Pillow. All scalar PNGs are numerical data. This tool does
not recover physical height, roughness, or AO from photographs.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageCms


def png_depth(path: Path) -> int | None:
    with path.open('rb') as handle:
        header = handle.read(29)
    if header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        return None
    return header[24]


def check_orientation(im: Image.Image, path: Path) -> None:
    orientation = im.getexif().get(274, 1)
    if orientation != 1:
        raise ValueError(f'{path.name}: EXIF orientation is {orientation}; explicitly apply the same orientation to every source map first')


def load_basecolor(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        check_orientation(im, path)
        if im.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
            raise ValueError(f'{path.name}: expected 8-bit RGB/sRGB image, got {im.mode}; convert explicitly first')
        if png_depth(path) == 16:
            raise ValueError(f'{path.name}: 16-bit basecolor requires an explicit colour-managed conversion to RGB8')
        if 'A' in im.getbands() or 'transparency' in im.info:
            alpha = np.asarray(im.convert('RGBA').getchannel('A'))
            if np.any(alpha != 255):
                raise ValueError(f'{path.name}: transparency is unsupported; provide an explicitly flattened, opaque source')
        profile = im.info.get('icc_profile')
        if profile:
            try:
                description = ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(profile)))
            except Exception as exc:
                raise ValueError(f'{path.name}: unreadable ICC profile; convert explicitly to sRGB') from exc
            if 'srgb' not in description.lower():
                raise ValueError(f'{path.name}: ICC profile {description.strip()!r} is not identified as sRGB; convert explicitly')
        result = np.asarray(im.convert('RGB'), dtype=np.float32) / 255.0
    if min(result.shape[:2]) < 2:
        raise ValueError('Both image dimensions must be at least 2 pixels')
    return result


def load_scalar(path: Path, shape: tuple[int, int] | None = None) -> np.ndarray:
    depth = png_depth(path)
    if depth not in (8, 16):
        raise ValueError(f'{path.name}: scalar inputs must be 8- or 16-bit grayscale PNGs')
    with Image.open(path) as im:
        check_orientation(im, path)
        if im.mode not in ('L', 'I', 'I;16', 'I;16B', 'I;16L'):
            raise ValueError(f'{path.name}: expected single-channel grayscale data, got {im.mode}')
        if 'transparency' in im.info:
            raise ValueError(f'{path.name}: transparency is unsupported in scalar data')
        result = np.asarray(im, dtype=np.float32) / (65535.0 if depth == 16 else 255.0)
    if shape is not None and result.shape != shape:
        raise ValueError(f'{path.name}: dimensions {result.shape[::-1]} differ from basecolor {shape[::-1]}; no implicit resize is allowed')
    if not np.isfinite(result).all() or result.min() < 0 or result.max() > 1:
        raise ValueError(f'{path.name}: invalid scalar data range')
    return result


def blur(a: np.ndarray, radius: float, tileable: bool = False) -> np.ndarray:
    """Three separable box passes; wrap boundaries for periodic material data."""
    r = max(0, int(round(radius)))
    if r == 0:
        return a.copy()
    result = np.asarray(a, dtype=np.float32)
    kernel = 2 * r + 1
    for _ in range(3):
        for axis in (0, 1):
            pads = [(0, 0), (0, 0)]
            pads[axis] = (r, r)
            padded = np.pad(result, pads, mode='wrap' if tileable else 'edge')
            cumulative = np.cumsum(padded, axis=axis, dtype=np.float64)
            zero_shape = list(cumulative.shape)
            zero_shape[axis] = 1
            cumulative = np.concatenate([np.zeros(zero_shape), cumulative], axis=axis)
            high = [slice(None), slice(None)]
            low = [slice(None), slice(None)]
            high[axis] = slice(kernel, None)
            low[axis] = slice(None, -kernel)
            result = ((cumulative[tuple(high)] - cumulative[tuple(low)]) / kernel).astype(np.float32)
    return result


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def normalize_estimate(a: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(a, [1, 99])
    if hi - lo < 1e-7:
        return np.full_like(a, 0.5)
    return np.clip((a - lo) / (hi - lo), 0, 1).astype(np.float32)


def normals_from_height(height: np.ndarray, size_m: tuple[float, float], range_m: float, tileable: bool) -> np.ndarray:
    """Return tangent +Y/OpenGL normals for UV v up and raster row y down."""
    h, w = height.shape
    surface_m = height * range_m
    dx, dy = size_m[0] / w, size_m[1] / h
    if tileable:
        gx = (np.roll(surface_m, -1, axis=1) - np.roll(surface_m, 1, axis=1)) / (2 * dx)
        gy = (np.roll(surface_m, -1, axis=0) - np.roll(surface_m, 1, axis=0)) / (2 * dy)
    else:
        gy, gx = np.gradient(surface_m, dy, dx)
    normal = np.stack((-gx, gy, np.ones_like(height)), axis=-1)
    return normal / np.linalg.norm(normal, axis=-1, keepdims=True)


def save_unit(a: np.ndarray, path: Path, bits: int = 8) -> None:
    scale, dtype = (65535, np.uint16) if bits == 16 else (255, np.uint8)
    Image.fromarray(np.rint(np.clip(a, 0, 1) * scale).astype(dtype)).save(path)


def digest(path: Path) -> dict:
    sha = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            sha.update(chunk)
    return {'file': path.name, 'sha256': sha.hexdigest()}


def prepare_outputs(out: Path, names: list[str], inputs: list[Path], overwrite: bool) -> None:
    input_paths = {p.resolve() for p in inputs}
    targets = [out / name for name in names]
    if any(p.resolve() in input_paths for p in targets):
        raise ValueError('Output would replace a source image; choose a different output directory')
    existing = [p.name for p in targets if p.exists()]
    if existing and not overwrite:
        raise ValueError(f'Outputs already exist: {", ".join(existing)}; choose a new directory or pass --overwrite')
    out.mkdir(parents=True, exist_ok=True)


def finite_float(value: str) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise argparse.ArgumentTypeError('value must be finite')
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path, help='Opaque sRGB basecolor; not a lit scene screenshot')
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--name', required=True)
    p.add_argument('--tile-size-m', required=True, nargs=2, type=finite_float, metavar=('WIDTH', 'HEIGHT'))
    p.add_argument('--height-range-m', required=True, type=finite_float, help='Physical displacement span represented by height 0..1')
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--height-input', type=Path, help='Registered numerical 8/16-bit grayscale PNG; preserve range')
    source.add_argument('--height-source', choices=['luminance'], help='Explicit opt-in to an uncalibrated photo-derived estimate')
    p.add_argument('--invert-height', action='store_true')
    p.add_argument('--height-blur', type=finite_float, default=6, help='Coarse box radius at 1024px; luminance estimates only')
    p.add_argument('--tileable', action='store_true', help='Use wrap filtering/gradients; does NOT make the input seamless')
    p.add_argument('--roughness', type=finite_float, default=0.8)
    p.add_argument('--roughness-input', type=Path)
    p.add_argument('--cavity-strength', type=finite_float, default=0, help='Optional artistic cavity proxy, not physical AO; default 0 gives white AO')
    p.add_argument('--metallic', type=finite_float, default=0)
    p.add_argument('--pack-orm', action='store_true', help='Write RGB: occlusion, roughness, metallic')
    p.add_argument('--overwrite', action='store_true')
    return p


def run(args: argparse.Namespace) -> Path:
    if any(x <= 0 for x in args.tile_size_m) or args.height_range_m < 0:
        raise ValueError('Physical tile dimensions must be positive; height range must be nonnegative')
    if not 0 <= args.roughness <= 1 or not 0 <= args.metallic <= 1:
        raise ValueError('Roughness and metallic must be between 0 and 1')
    if args.height_blur < 0 or args.cavity_strength < 0:
        raise ValueError('Blur and cavity strength must be nonnegative')
    if not args.name.strip():
        raise ValueError('Material name must not be empty')
    rgb = load_basecolor(args.input)
    shape = rgb.shape[:2]
    warnings = []
    if args.height_input:
        height = load_scalar(args.height_input, shape)
        height_description = 'User-supplied registered numerical height; physical range supplied by caller, not inferred.'
    else:
        lum = srgb_to_linear(rgb) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        radius = args.height_blur * min(shape) / 1024
        height = normalize_estimate(0.7 * blur(lum, radius, args.tileable) + 0.3 * blur(lum, radius / 6, args.tileable))
        height_description = 'Heuristic normalized linear luminance; pigment, lighting, and geometry are ambiguous. Not measured height.'
        warnings.append('Height inferred from colour is a heuristic; inspect relief against the reference before accepting it.')
    if args.invert_height:
        height = 1.0 - height
    # Derive normal from the exact quantized height that is saved, keeping maps reproducible.
    height = np.rint(height * 65535).astype(np.float32) / 65535
    normal = normals_from_height(height, tuple(args.tile_size_m), args.height_range_m, args.tileable)
    roughness = load_scalar(args.roughness_input, shape) if args.roughness_input else np.full(shape, args.roughness, dtype=np.float32)
    metallic = np.full(shape, args.metallic, dtype=np.float32)
    if args.cavity_strength:
        local = blur(height, 12 * min(shape) / 1024, args.tileable)
        ao = np.clip(1 + np.minimum(height - local, 0) * args.cavity_strength, 0, 1)
        ao_description = 'Artistic height-cavity approximation; not physically calculated or baked ambient occlusion.'
        warnings.append('AO is an artistic cavity proxy; leave it disconnected in physically lit Blender renders unless justified.')
    else:
        ao = np.ones(shape, dtype=np.float32)
        ao_description = 'Neutral white. No physical occlusion was estimated.'
    if args.tileable:
        warnings.append('Wrap processing is enabled; inspect the 2x2 tile preview because the source may still have seams.')
    maps = {key: {'file': f'{key}.png', 'color_space': 'sRGB' if key == 'basecolor' else 'Non-Color', 'bit_depth': 16 if key == 'height' else 8}
            for key in ['basecolor', 'height', 'normal', 'roughness', 'ao', 'metallic']}
    if args.pack_orm:
        maps['orm'] = {'file': 'orm.png', 'color_space': 'Non-Color', 'bit_depth': 8, 'channels': {'R': 'ao', 'G': 'roughness', 'B': 'metallic'}}
    inputs = [args.input] + [p for p in [args.height_input, args.roughness_input] if p]
    prepare_outputs(args.out, [entry['file'] for entry in maps.values()] + ['material.json'], inputs, args.overwrite)
    for key, data in [('basecolor', rgb), ('height', height), ('normal', normal * 0.5 + 0.5), ('roughness', roughness), ('ao', ao), ('metallic', metallic)]:
        save_unit(data, args.out / maps[key]['file'], maps[key]['bit_depth'])
    if args.pack_orm:
        save_unit(np.stack([ao, roughness, metallic], axis=-1), args.out / 'orm.png')
    manifest = {
        'schema_version': 1, 'material_name': args.name,
        'resolution': {'width': shape[1], 'height': shape[0]},
        'physical_size_m': args.tile_size_m, 'height_range_m': args.height_range_m,
        'height_midlevel': 0.5, 'boundary_mode': 'wrap' if args.tileable else 'edge',
        'normal_convention': 'OpenGL', 'maps': maps,
        'estimates': {'height': height_description,
                      'roughness': 'User-supplied registered data.' if args.roughness_input else 'Artist-selected uniform roughness; not inferred from brightness.',
                      'ao': ao_description},
        'parameters': {'invert_height': args.invert_height, 'height_blur_at_1024px': args.height_blur,
                       'roughness': args.roughness, 'cavity_strength': args.cavity_strength, 'metallic': args.metallic},
        'sources': {'basecolor': digest(args.input), 'basecolor_encoding': 'sRGB (assumed for untagged sources)'},
        'warnings': warnings,
    }
    if args.height_input:
        manifest['sources']['height'] = digest(args.height_input)
    if args.roughness_input:
        manifest['sources']['roughness'] = digest(args.roughness_input)
    path = args.out / 'material.json'
    path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    for warning in warnings:
        print(f'WARNING: {warning}', file=sys.stderr)
    return path


def main() -> int:
    args = parser().parse_args()
    try:
        print(run(args))
        return 0
    except (ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
