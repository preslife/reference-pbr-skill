#!/usr/bin/env python3
"""Make registered colour-threshold masks; visually approve them before use."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from make_maps import blur, finite_float, load_basecolor, prepare_outputs, save_unit


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--hue', nargs=2, type=finite_float, required=True, metavar=('MIN', 'MAX'), help='Degrees 0..360; MIN > MAX wraps through red')
    p.add_argument('--saturation', nargs=2, type=finite_float, default=[0.25, 1])
    p.add_argument('--value', nargs=2, type=finite_float, default=[0, 0.7])
    p.add_argument('--shade-radius', type=finite_float, default=1, help='Three-pass box blur radius, source pixels')
    p.add_argument('--height-radius', type=finite_float, default=12, help='Wider transition for any proposed height adjustment')
    p.add_argument('--tileable', action='store_true')
    p.add_argument('--overwrite', action='store_true')
    a = p.parse_args()
    try:
        if any(not 0 <= n <= 360 for n in a.hue):
            raise ValueError('Hue limits must be in 0..360 degrees')
        if any(not 0 <= lo <= hi <= 1 for lo, hi in [a.saturation, a.value]):
            raise ValueError('Saturation and value limits require 0 <= MIN <= MAX <= 1')
        if a.shade_radius < 0 or a.height_radius < a.shade_radius:
            raise ValueError('Require 0 <= shade radius <= height radius')
        rgb = load_basecolor(a.input)
        hsv = np.asarray(Image.fromarray(np.rint(rgb * 255).astype(np.uint8)).convert('HSV'), dtype=np.float32) / 255
        hue, sat, val = hsv[..., 0] * 360, hsv[..., 1], hsv[..., 2]
        lo, hi = a.hue
        select_hue = (hue >= lo) & (hue <= hi) if lo <= hi else (hue >= lo) | (hue <= hi)
        selected = select_hue & (sat >= a.saturation[0]) & (sat <= a.saturation[1]) & (val >= a.value[0]) & (val <= a.value[1])
        sharp = blur(selected.astype(np.float32), a.shade_radius, a.tileable)
        soft = blur(selected.astype(np.float32), a.height_radius, a.tileable)
        names = ['mask_shade.png', 'mask_height.png', 'mask_preview.png', 'masks.json']
        prepare_outputs(a.out, names, [a.input], a.overwrite)
        save_unit(sharp, a.out / names[0])
        save_unit(soft, a.out / names[1])
        blend = sharp[..., None] * 0.45
        overlay = rgb * (1 - blend) + np.array([1, 0, 1], dtype=np.float32) * blend
        save_unit(overlay, a.out / names[2])
        metadata = {'source': a.input.name, 'hue_degrees': a.hue, 'saturation': a.saturation, 'value': a.value,
                    'shade_radius_px': a.shade_radius, 'height_radius_px': a.height_radius,
                    'boundary_mode': 'wrap' if a.tileable else 'edge',
                    'coverage_fraction': float(selected.mean()), 'mask_color_space': 'Non-Color',
                    'note': 'Colour selection is not semantic segmentation. Inspect overlay; masks do not modify height or material.json automatically.'}
        (a.out / names[3]).write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(f'Masks saved to {a.out}; selected {selected.mean():.1%} of pixels. Inspect mask_preview.png.')
        if selected.mean() < 0.001 or selected.mean() > 0.999:
            print('WARNING: Mask is effectively empty or full; verify thresholds.', file=sys.stderr)
        return 0
    except (ValueError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
