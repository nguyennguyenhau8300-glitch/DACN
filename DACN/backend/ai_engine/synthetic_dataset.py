"""Reproducible SYNTHETIC dataset, YOLO labels, manifest and camera demo video.
Never report its metrics as accuracy on Vietnamese traffic or real cameras.
"""
import argparse
import json
import random
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter

ROOT=Path(__file__).resolve().parent

def scene(index,seed=20261028):
    rng=random.Random(seed+index)
    image=Image.new('RGB',(640,384),tuple(rng.randrange(50,180) for _ in range(3)))
    draw=ImageDraw.Draw(image)
    draw.rectangle((30,50,610,354),fill=tuple(rng.randrange(20,100) for _ in range(3)))
    two=index%3==0
    plate=f'{rng.randrange(11,99):02d}'+('B1' if two else 'F')+f'{rng.randrange(10000,99999):05d}'
    w,h=(rng.randrange(160,230),rng.randrange(120,160)) if two else (rng.randrange(250,390),rng.randrange(65,100))
    x,y=rng.randrange(60,580-w),rng.randrange(110,340-h)
    draw.rounded_rectangle((x,y,x+w,y+h),radius=7,fill=(246,246,237),outline=(20,20,20),width=3)
    font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',int(h*.36 if two else h*.58))
    lines=[plate[:4],plate[4:7]+'.'+plate[7:]] if two else [plate[:3]+'-'+plate[3:6]+'.'+plate[6:]]
    for i,line in enumerate(lines):
        draw.text((x+w/2,y+h*(.24+.48*i) if two else y+h*.48),line,font=font,fill='black',anchor='mm')
    if index%5==0: image=image.filter(ImageFilter.GaussianBlur(.35))
    return image,plate,[x,y,w,h]

def generate(output,train=128,val=24,test=24):
    output.mkdir(parents=True,exist_ok=True)
    manifest=[]
    offset=0
    for split,count in [('train',train),('val',val),('test',test)]:
        (output/'images'/split).mkdir(parents=True,exist_ok=True)
        (output/'labels'/split).mkdir(parents=True,exist_ok=True)
        for i in range(count):
            image,plate,roi=scene(offset+i)
            # Negative examples are separate scenes without plates.
            negative=i%12==11
            if negative: image=Image.new('RGB',image.size,(80,100,110))
            stem=f'{offset+i:05d}'
            image.save(output/'images'/split/f'{stem}.jpg',quality=95)
            x,y,w,h=roi
            (output/'labels'/split/f'{stem}.txt').write_text('' if negative else f'0 {(x+w/2)/640:.7f} {(y+h/2)/384:.7f} {w/640:.7f} {h/384:.7f}\n')
            manifest.append({'image':f'images/{split}/{stem}.jpg','plate':None if negative else plate,'roi':None if negative else roi,'split':split,'synthetic':True})
        offset+=count
    (output/'dataset.yaml').write_text(f'path: {output.resolve().as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: license_plate\n',encoding='utf-8')
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'manifest-test.json').write_text(json.dumps([{k:v for k,v in r.items() if k in ['image','plate']} for r in manifest if r['split']=='test'],indent=2),encoding='utf-8')
    (output/'PROVENANCE.md').write_text('# SYNTHETIC DEMO ONLY\nImages and labels generated in code; not photographs, not evidence of real-world accuracy. Train/val/test use different generated plates/scenes.\n',encoding='utf-8')
    import cv2
    import numpy as np
    video=cv2.VideoWriter(str(output/'camera-demo.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,384))
    for index in [train+val,train+val+1,train+val+2]:
        image,_,_=scene(index)
        for _ in range(30): video.write(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR))
        for _ in range(10): video.write(np.zeros((384,640,3),dtype=np.uint8))
    video.release()
    return output/'dataset.yaml'

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT.parent.parent.parent/'du_lieu_ai/synthetic')
    args=parser.parse_args();print(generate(args.output))
