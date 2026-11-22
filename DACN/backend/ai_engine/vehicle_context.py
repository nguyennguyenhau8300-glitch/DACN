"""Image appearance classifier for a visible vehicle around a plate."""
from pathlib import Path
import threading

MODEL = Path(__file__).resolve().parent/'artifacts/vehicle-yolov8/plate-context.pt'
KINDS = ('CAR', 'MOTORBIKE', 'UNKNOWN')
SIZE = 160
_model = None
_lock = threading.Lock()


def vehicle_context(image, box):
    from PIL import Image, ImageDraw, ImageOps

    x1, y1, x2, y2 = box
    width, height = x2-x1, y2-y1
    if min(width,height)<8 or image.width<width*1.7 or y1<height*.6:
        return None
    margin = max(4,round(width*.9))
    left, top = max(0,x1-margin), max(0,y1-round(width*1.5))
    right, bottom = min(image.width,x2+margin), min(image.height,y2+round(width*.65))
    crop = image.crop((left,top,right,bottom))
    # The classifier sees vehicle appearance while OCR handles the plate text.
    mask = max(2,round(height*.11))
    ImageDraw.Draw(crop).rectangle((x1-left-mask,y1-top-mask,x2-left+mask,y2-top+mask),fill=(110,110,110))
    return ImageOps.pad(crop,(SIZE,SIZE),Image.Resampling.BILINEAR,color=(110,110,110))


def tensor(image):
    import numpy as np
    import torch

    pixels=torch.from_numpy(np.asarray(image,dtype=np.float32).copy()).permute(2,0,1).div(255)
    return (pixels-torch.tensor([.485,.456,.406])[:,None,None])/torch.tensor([.229,.224,.225])[:,None,None]


def classify_context(image, box):
    global _model
    if not MODEL.is_file():
        return None
    crop=vehicle_context(image,box)
    if crop is None:
        return None
    import torch
    from PIL import ImageEnhance

    with _lock,torch.inference_mode():
        if _model is None:
            _model=torch.jit.load(str(MODEL),map_location='cpu').eval()
        batch=torch.stack([tensor(crop),tensor(ImageEnhance.Brightness(crop).enhance(.8))])
        predictions=_model(batch).softmax(1)
    confidence,indices=predictions.max(dim=1)
    idx=int(indices[0])
    if idx==2 or int(indices[1])!=idx or float(confidence.min())<.9:
        return None
    return {'type':KINDS[idx],'box':None,'confidence':round(float(confidence.min()),4),'reason':'plate_context'}
