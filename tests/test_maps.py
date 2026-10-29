#!/usr/bin/env python3
"""Run the original 26 map-pipeline checks using disposable synthetic fixtures.

From the repository root: python3 tests/test_maps.py
Dependencies: NumPy and Pillow. Generated files live in a temporary directory
that is removed on completion. Blender is not required for these checks.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image


def main():
    scripts = Path(__file__).resolve().parents[1] / 'skills' / 'build-reference-pbr' / 'scripts'
    if not (scripts / 'make_maps.py').is_file():
        raise SystemExit('Cannot locate bundled skill scripts relative to this test runner')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(scripts))
    import make_maps as mm
    import validate_maps as vm

    with tempfile.TemporaryDirectory(prefix='reference-pbr-tests-') as temporary:
        root = Path(temporary)
        checks = []
        def check(name,condition):
         if not condition:
          raise AssertionError(name)
         checks.append(name)
        def cli(name,args,code=0):
         r=subprocess.run([sys.executable,str(scripts/name),*map(str,args)],text=True,capture_output=True,env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
         if r.returncode!=code:
          raise AssertionError((name,r.returncode,r.stdout,r.stderr))
         return r

        shape=(96,128)
        y,x=np.mgrid[:shape[0],:shape[1]]
        h=(.5+.2*np.sin(2*np.pi*x/shape[1])+.1*np.cos(2*np.pi*y/shape[0]))
        hr=np.rint(h*65535).astype(np.uint16)
        Image.fromarray(hr).save(root/'height-source.png')
        rgb=np.dstack([100+30*np.cos(2*np.pi*x/shape[1]),110+40*np.sin(2*np.pi*y/shape[0]),70+20*np.cos(2*np.pi*x/shape[1])]).astype(np.uint8)
        Image.fromarray(rgb).save(root/'base.png')
        args=[root/'base.png','--out',root/'material','--name','Synthetic fixture','--tile-size-m',1,0.75,'--height-range-m',0.2,'--height-input',root/'height-source.png','--tileable','--pack-orm']
        cli('make_maps.py',args)
        material=root/'material'
        manifest=json.loads((material/'material.json').read_text())
        check('16-bit height values preserved',np.array_equal(np.asarray(Image.open(material/'height.png')),hr))
        check('height PNG is genuinely 16 bit',mm.png_depth(material/'height.png')==16)
        check('default AO white',np.asarray(Image.open(material/'ao.png')).min()==255)
        check('default roughness uniform',np.unique(np.asarray(Image.open(material/'roughness.png'))).tolist()==[204])
        check('default metallic zero',np.asarray(Image.open(material/'metallic.png')).max()==0)
        check('ORM channels match',np.array_equal(np.asarray(Image.open(material/'orm.png')),np.stack([np.asarray(Image.open(material/(n+'.png'))) for n in ('ao','roughness','metallic')],axis=-1)))
        cli('validate_maps.py',[material])
        report=json.loads((material/'validation.json').read_text())
        check('validator accepts generated maps',report['passed'])
        check('height-normal agreement below 0.4 degrees',report['maps']['normal']['height_consistency_angle_p99_degrees']<.4)
        check('same-size generation',all(Image.open(material/entry['file']).size==(128,96) for entry in manifest['maps'].values()))
        cli('make_maps.py',args,2)
        check('existing outputs require explicit overwrite',True)
        # Analytical orientation and physical-scale check on a sloped surface.
        yr,xr=np.mgrid[:17,:23]
        ramp=(xr/23)*.6+(yr/17)*.4
        n=mm.normals_from_height(ramp,(2,3),.1,False)
        expected=np.array([-.03,.4*.1/3,1]);expected=expected/np.linalg.norm(expected)
        check('OpenGL slope signs and physical scale',np.allclose(n,expected,atol=1e-12))
        flat=mm.normals_from_height(np.ones((17,23))*.5,(2,3),.1,True)
        check('constant height yields flat unit normal',np.allclose(flat,[0,0,1]))
        impulse=np.zeros((21,25),np.float32);impulse[0,0]=1
        filtered=mm.blur(impulse,1,True)
        check('periodic blur wraps across both edges',filtered[-1,-1]>0 and np.isclose(filtered[-1,0],filtered[1,0]))
        check('periodic blur preserves mean',np.isclose(filtered.sum(),1,atol=1e-6))
        check('sRGB decoded before luminance',np.isclose(mm.srgb_to_linear(np.array([.5]))[0],.21404114048))
        # Flat image luminance fallback.
        Image.new('RGB',(32,48),(128,128,128)).save(root/'flat.png')
        cli('make_maps.py',[root/'flat.png','--out',root/'flat','--name','Flat fallback','--tile-size-m',1,1,'--height-range-m',.01,'--height-source','luminance'])
        check('constant luminance yields midpoint height',np.unique(np.asarray(Image.open(root/'flat/height.png'))).tolist()==[32768])
        # Invalid dimension and nonopaque inputs are rejected before writes.
        Image.new('L',(32,32),128).save(root/'wrongsize.png')
        cli('make_maps.py',[root/'base.png','--out',root/'bad-size','--name','bad','--tile-size-m',1,1,'--height-range-m',.01,'--height-input',root/'wrongsize.png'],2)
        check('mismatched scalar dimensions rejected',not (root/'bad-size').exists())
        Image.new('RGBA',(32,32),(100,100,100,128)).save(root/'alpha.png')
        cli('make_maps.py',[root/'alpha.png','--out',root/'bad-alpha','--name','bad','--tile-size-m',1,1,'--height-range-m',.01,'--height-source','luminance'],2)
        check('nonopaque sources rejected',not (root/'bad-alpha').exists())
        exif=Image.Exif();exif[274]=6
        Image.new('RGB',(32,32),(100,100,100)).save(root/'rotated.jpg',exif=exif)
        cli('make_maps.py',[root/'rotated.jpg','--out',root/'bad-exif','--name','bad','--tile-size-m',1,1,'--height-range-m',.01,'--height-source','luminance'],2)
        check('EXIF orientation ambiguity rejected',not (root/'bad-exif').exists())
        # Sharp masks versus softened height masks and hue wrap.
        maskimg=np.zeros((64,96,3),np.uint8);maskimg[:,:48]=(180,10,10);maskimg[:,48:]=(10,180,10)
        Image.fromarray(maskimg).save(root/'mask-source.png')
        cli('make_masks.py',[root/'mask-source.png','--out',root/'masks','--hue',340,20,'--saturation',.5,1,'--value',0,1,'--shade-radius',0,'--height-radius',3,'--tileable'])
        shade=np.asarray(Image.open(root/'masks/mask_shade.png'))
        soft=np.asarray(Image.open(root/'masks/mask_height.png'))
        check('hue interval wraps through red',shade[:,0].min()==255 and shade[:,-1].max()==0)
        check('separate height mask softened',len(np.unique(soft))>2)
        check('height mask filtering periodic',soft[:,0].max()<255 and soft[:,-1].min()>0)
        # Corrupt each independent invariant in a fresh directory.
        for bad in ['bad-normal','bad-depth','bad-dimensions']:
         shutil.copytree(material,root/bad)
        bad_normal=root/'bad-normal';na=np.array(Image.open(bad_normal/'normal.png'));na[...,1]=255-na[...,1];Image.fromarray(na).save(bad_normal/'normal.png')
        rr,_=vm.validate(bad_normal)
        check('validator catches DirectX-style green flip',not rr['passed'] and any('disagrees' in e for e in rr['errors']))
        bad_depth=root/'bad-depth';Image.fromarray((hr/257).astype(np.uint8)).save(bad_depth/'height.png')
        rr,_=vm.validate(bad_depth)
        check('validator catches fake 16-bit height',not rr['passed'] and any('bit depth' in e for e in rr['errors']))
        bad_dim=root/'bad-dimensions';Image.new('L',(10,10),100).save(bad_dim/'roughness.png')
        rr,_=vm.validate(bad_dim)
        check('validator catches incorrect map dimensions',not rr['passed'] and any('dimensions' in e for e in rr['errors']))
        # Wrong command contracts are user errors, not silent fallback.
        for script in ['make_maps.py','make_masks.py','validate_maps.py']:
         cli(script,['--help'])
        check('all three help commands runnable',True)
        print(json.dumps({'passed':len(checks),'checks':checks},indent=2))
        (root/'test-results.json').write_text(json.dumps({'passed':len(checks),'checks':checks},indent=2)+'\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
