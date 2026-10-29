#!/usr/bin/env python3
"""Check a material.json package and produce diagnostic previews, not quality certification."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from make_maps import check_orientation, normals_from_height, png_depth


SCALARS = {'height', 'roughness', 'ao', 'metallic', 'mask_shade', 'mask_height'}
REQUIRED = {'basecolor', 'height', 'normal', 'roughness', 'ao', 'metallic'}


def seam_metrics(data: np.ndarray) -> dict:
    """Compare wrap-edge discontinuities with ordinary neighbour differences."""
    if data.ndim == 2:
        data = data[..., None]
    metrics = {}
    for label, axis in [('left_right', 1), ('top_bottom', 0)]:
        edge = np.abs(np.take(data, 0, axis=axis) - np.take(data, -1, axis=axis))
        interior = np.abs(np.diff(data, axis=axis))
        jump = float(np.mean(edge))
        baseline = float(np.mean(interior))
        metrics[label] = {'edge_mean_abs': jump, 'interior_mean_abs': baseline,
                          'ratio': jump / max(baseline, 1 / 65535)}
    return metrics


def make_preview(images: dict[str, Image.Image], output: Path) -> None:
    cards = []
    for name, im in images.items():
        cards.append((name + (' / sRGB' if name == 'basecolor' else ' / data'), im))
    if 'basecolor' in images:
        base = images['basecolor'].convert('RGB')
        tile = ImageOps.contain(base, (256, 256), Image.Resampling.LANCZOS)
        grid = Image.new('RGB', (tile.width * 2, tile.height * 2))
        for x, y in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            grid.paste(tile, (x * tile.width, y * tile.height))
        cards.append(('Basecolor / 2x2 repeat', grid))
        arr = np.asarray(base)
        offset = np.roll(arr, (arr.shape[0] // 2, arr.shape[1] // 2), axis=(0, 1))
        cards.append(('Basecolor / half offset', Image.fromarray(offset)))
    if not cards:
        return
    width, cell_w, cell_h = 900, 300, 332
    canvas = Image.new('RGB', (width, math.ceil(len(cards) / 3) * cell_h + 48), '#22262b')
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 12), 'MAP DIAGNOSTICS | inspect seams, relief and alignment separately', fill='white')
    for index, (label, im) in enumerate(cards):
        x = (index % 3) * cell_w
        y = (index // 3) * cell_h + 40
        tile = ImageOps.contain(im.convert('RGB'), (284, 284), Image.Resampling.LANCZOS)
        canvas.paste(tile, (x + (cell_w - tile.width) // 2, y + (284 - tile.height) // 2))
        draw.text((x + 8, y + 292), label, fill='white')
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def validate(directory: Path) -> tuple[dict, dict[str, Image.Image]]:
    errors: list[str] = []
    warnings: list[str] = []
    statistics: dict = {}
    previews: dict[str, Image.Image] = {}
    arrays: dict[str, np.ndarray] = {}
    result = {'passed': False, 'scope': 'File integrity and declared numerical consistency only; not physical truth or production readiness.',
              'errors': errors, 'warnings': warnings, 'maps': statistics}
    manifest = json.loads((directory / 'material.json').read_text(encoding='utf-8'))
    if not isinstance(manifest, dict):
        raise ValueError('material.json must contain an object')
    if manifest.get('schema_version') != 1:
        errors.append('Unsupported or missing schema_version; expected 1')
    resolution = manifest.get('resolution', {})
    expected_size = (resolution.get('width'), resolution.get('height')) if isinstance(resolution, dict) else (None, None)
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 2 for v in expected_size):
        errors.append('Resolution must contain integer width and height >= 2')
    dimensions = manifest.get('physical_size_m')
    dimensions_ok = isinstance(dimensions, list) and len(dimensions) == 2 and all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in dimensions)
    if not dimensions_ok:
        errors.append('physical_size_m requires two finite positive numbers')
    height_range = manifest.get('height_range_m')
    range_ok = isinstance(height_range, (int, float)) and math.isfinite(height_range) and height_range >= 0
    if not range_ok:
        errors.append('height_range_m requires a finite nonnegative number')
    if manifest.get('normal_convention') != 'OpenGL':
        errors.append('Normal convention must be explicitly OpenGL for this package')
    if manifest.get('boundary_mode') not in ('edge', 'wrap'):
        errors.append('boundary_mode must be edge or wrap')
    maps = manifest.get('maps')
    if not isinstance(maps, dict):
        errors.append('maps must be an object')
        return result, previews
    missing = REQUIRED - set(maps)
    if missing:
        errors.append('Missing map declarations: ' + ', '.join(sorted(missing)))
    root = directory.resolve()
    for name, entry in maps.items():
        try:
            if not isinstance(entry, dict) or not isinstance(entry.get('file'), str):
                raise ValueError('map entry requires a file string')
            path = directory / entry['file']
            if not path.resolve().is_relative_to(root):
                raise ValueError('map file must remain inside the material directory')
            if not path.is_file():
                raise ValueError('declared file is missing')
            depth = png_depth(path)
            if depth != entry.get('bit_depth'):
                raise ValueError(f'PNG bit depth {depth} differs from declared {entry.get("bit_depth")}')
            if name == 'height' and depth != 16:
                raise ValueError('height must be a genuine 16-bit grayscale PNG')
            expected_space = 'sRGB' if name == 'basecolor' else 'Non-Color'
            if entry.get('color_space') != expected_space:
                raise ValueError(f'color_space must be {expected_space}')
            with Image.open(path) as im:
                check_orientation(im, path)
                if im.size != expected_size:
                    raise ValueError(f'dimensions {im.size} differ from declared {expected_size}')
                if name in SCALARS and im.mode not in ('L', 'I', 'I;16', 'I;16B', 'I;16L'):
                    raise ValueError(f'expected grayscale, got {im.mode}')
                if name in ('basecolor', 'normal', 'orm') and im.mode != 'RGB':
                    raise ValueError(f'expected RGB, got {im.mode}')
                if depth not in (8, 16):
                    raise ValueError('only 8/16-bit PNG maps are supported')
                arr = np.asarray(im, dtype=np.float32) / (65535 if depth == 16 else 255)
                if not np.isfinite(arr).all() or arr.min() < 0 or arr.max() > 1:
                    raise ValueError('invalid numerical data')
                arrays[name] = arr
                # Convert actual data range directly; do not stretch height to conceal limited range.
                previews[name] = Image.fromarray(np.rint(arr * 255).astype(np.uint8))
            values = np.unique(arr)
            statistics[name] = {'width': expected_size[0], 'height': expected_size[1], 'bit_depth': depth,
                                'min': float(arr.min()), 'max': float(arr.max()), 'unique_values': int(values.size),
                                'seams': seam_metrics(arr)}
            if name == 'height' and 1 < values.size <= 256:
                warnings.append('height: <=256 unique samples; a 16-bit file alone does not guarantee high precision')
            if name == 'height' and values.size == 1:
                warnings.append('height: constant map; relief is intentionally or accidentally flat')
            if manifest.get('boundary_mode') == 'wrap':
                for edge, metric in statistics[name]['seams'].items():
                    if metric['edge_mean_abs'] > 0.02 and metric['ratio'] > 3:
                        warnings.append(f'{name}: {edge} boundary jump is unusually large; inspect a repeated render')
        except (ValueError, OSError, TypeError) as exc:
            errors.append(f'{name}: {exc}')
    if 'normal' in arrays:
        n = arrays['normal'] * 2 - 1
        lengths = np.linalg.norm(n, axis=-1)
        deviation = float(np.max(np.abs(lengths - 1)))
        statistics['normal']['max_unit_length_error'] = deviation
        if deviation > 0.02:
            errors.append('normal: vectors are not approximately unit length (allowing RGB8 quantization)')
        if np.any(n[..., 2] < -0.005):
            warnings.append('normal: negative tangent Z values; inspect convention and source')
        if 'height' in arrays and dimensions_ok and range_ok:
            expected = normals_from_height(arrays['height'], tuple(dimensions), height_range, manifest.get('boundary_mode') == 'wrap')
            if n.shape == expected.shape:
                unit = n / np.maximum(lengths[..., None], 1e-8)
                angles = np.rad2deg(np.arccos(np.clip(np.sum(unit * expected, axis=-1), -1, 1)))
                p99 = float(np.percentile(angles, 99))
                statistics['normal']['height_consistency_angle_p99_degrees'] = p99
                if p99 > 5:
                    errors.append('normal: disagrees with the declared height, physical scale or tangent convention (>5 degrees at p99)')
                elif p99 > 1:
                    warnings.append('normal: check height consistency; p99 angular difference exceeds 1 degree')
    if 'orm' in arrays and all(key in arrays for key in ['ao', 'roughness', 'metallic']):
        expected = np.stack([arrays['ao'], arrays['roughness'], arrays['metallic']], axis=-1)
        if arrays['orm'].shape != expected.shape or np.max(np.abs(arrays['orm'] - expected)) > 1 / 255 + 1e-6:
            errors.append('orm: channels do not match R=AO, G=roughness, B=metallic')
    warnings.append('Numerical seam checks cannot prove seamless tiling, correct semantic relief, or photographic fidelity.')
    result['passed'] = not errors
    return result, previews


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--report', type=Path, help='Default: DIR/validation.json')
    p.add_argument('--preview', type=Path, help='Default: DIR/contact_sheet.png')
    p.add_argument('--overwrite', action='store_true')
    a = p.parse_args()
    report = a.report or a.directory / 'validation.json'
    preview = a.preview or a.directory / 'contact_sheet.png'
    try:
        if report.resolve() == preview.resolve():
            raise ValueError('Report and preview paths must differ')
        manifest_path = a.directory / 'material.json'
        protected = {manifest_path.resolve()}
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if isinstance(manifest, dict) and isinstance(manifest.get('maps'), dict):
            for entry in manifest['maps'].values():
                if isinstance(entry, dict) and isinstance(entry.get('file'), str):
                    protected.add((a.directory / entry['file']).resolve())
        if report.resolve() in protected or preview.resolve() in protected:
            raise ValueError('Diagnostic output may not replace a source map or material.json')
        if not a.overwrite and (report.exists() or preview.exists()):
            raise ValueError('Diagnostic outputs exist; choose new paths or pass --overwrite')
        result, images = validate(a.directory)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        make_preview(images, preview)
        print(json.dumps({'passed': result['passed'], 'errors': result['errors'], 'warnings': result['warnings'], 'report': str(report), 'preview': str(preview) if images else None}, indent=2))
        return 0 if result['passed'] else 1
    except (ValueError, OSError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
