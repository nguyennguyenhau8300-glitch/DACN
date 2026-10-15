"""Text detection + OCR and conservative grouping for common VN plates.
This is a pretrained general OCR pipeline, not a custom-trained plate detector.
"""
import io
import os
import re
import threading
import time
import warnings
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000
PLATE = re.compile(r'[1-9][0-9][A-Z]{1,2}[0-9]{4,6}')
_engine = None
_lock = threading.Lock()
_ready = False

class ImageError(ValueError):
    pass

class EngineUnavailable(RuntimeError):
    pass

class EngineBusy(RuntimeError):
    pass

def normalize_plate(text):
    # No O->0/B->8 guessing: never silently change the vehicle identity.
    return re.sub(r'[^A-Z0-9]', '', text.upper())

def read_image(data):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not data or len(data) > MAX_BYTES:
        raise ImageError('Ảnh phải có dung lượng từ 1 byte đến 8 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ImageError('Chỉ nhận ảnh JPEG, PNG hoặc WebP')
                if source.width * source.height > MAX_PIXELS:
                    raise ImageError('Ảnh tối đa 16 triệu pixel')
                if min(source.size) < 32:
                    raise ImageError('Ảnh quá nhỏ, mỗi chiều cần ít nhất 32 pixel')
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.load()
                return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageError('Ảnh hỏng hoặc kích thước vượt giới hạn') from exc

def rect(box):
    xs, ys = zip(*box)
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

def nearby(a,b):
    ax,ay,ar,ab=a; bx,by,br,bb=b
    ah,bh=max(1,ab-ay),max(1,bb-by)
    horizontal = abs((ay+ab-by-bb)/2) < .6*max(ah,bh) and 0 <= bx-ar < 2*max(ah,bh)
    overlap = max(0,min(ar,br)-max(ax,bx))
    vertical = 0 <= by-ab < 2.5*max(ah,bh) and overlap > .4*min(ar-ax,br-bx)
    return horizontal or vertical

def collect_candidates(texts,scores,boxes):
    items=[{'text':str(t),'confidence':float(s),'box':rect(b)} for t,s,b in zip(texts,scores,boxes)]
    items=sorted(items,key=lambda x:(x['box'][1],x['box'][0]))[:80]
    candidates={}
    def add(group):
        raw=''.join(x['text'] for x in group)
        if not re.fullmatch(r'[A-Za-z0-9 .\-\s]+',raw): return
        normalized=normalize_plate(raw)
        if not PLATE.fullmatch(normalized): return
        score=min(x['confidence'] for x in group)
        boxes=[x['box'] for x in group]
        item={'plate':normalized,'confidence':score,
            'raw_text':' '.join(x['text'] for x in group),
            'box':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]}
        if normalized not in candidates or score>candidates[normalized]['confidence']:
            candidates[normalized]=item
    for a in items:
        add([a])
        for b in items:
            if a is b or not nearby(a['box'],b['box']): continue
            add([a,b])
            for c in items:
                if c is a or c is b or not nearby(b['box'],c['box']): continue
                add([a,b,c])
    return sorted(candidates.values(),key=lambda x:x['confidence'],reverse=True),items

def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR
        _engine=RapidOCR(params={'Global.text_score':0.35,'Global.log_level':'error',
            'Det.limit_type':'max','Det.limit_side_len':960,
            'EngineConfig.onnxruntime.intra_op_num_threads':2,
            'EngineConfig.onnxruntime.inter_op_num_threads':2})
    return _engine

def status():
    return {'engine':'RapidOCR / ONNX Runtime (CPU)','loaded':_ready,
        'confidence_threshold':threshold(),'max_upload_mb':8,'max_pixels':MAX_PIXELS,
        'supported_formats':['JPEG','PNG','WEBP']}

def threshold():
    value=float(os.getenv('AI_MIN_CONFIDENCE','0.85'))
    if not 0.5 <= value <= 1: raise ValueError('AI_MIN_CONFIDENCE phải nằm trong [0.5, 1]')
    return value

def recognize(data,roi=None):
    global _ready
    image=read_image(data)
    width,height=image.size
    dx=dy=0
    if roi is not None:
        if len(roi)!=4: raise ImageError('ROI gồm x, y, width, height')
        dx,dy,w,h=roi
        if min(dx,dy)<0 or min(w,h)<32 or dx+w>width or dy+h>height:
            raise ImageError('ROI phải nằm trong ảnh, mỗi chiều ít nhất 32 pixel')
        image=image.crop((dx,dy,dx+w,dy+h))
    if not _lock.acquire(timeout=5): raise EngineBusy('AI đang bận; thử lại sau')
    started=time.perf_counter()
    try:
        import numpy as np
        output=_get_engine()(np.asarray(image)[:,:,::-1].copy())
        _ready=True
        texts=output.txts if output.txts is not None else []
        scores=output.scores if output.scores is not None else []
        boxes=output.boxes if output.boxes is not None else []
        too_many = len(texts)>80
        candidates,lines=collect_candidates(texts,scores,boxes)
    except Exception as exc:
        raise EngineUnavailable('Không chạy được mô hình OCR; kiểm tra cài đặt AI') from exc
    finally:
        _lock.release()
    for item in candidates+lines:
        x1,y1,x2,y2=item['box'];item['box']=[x1+dx,y1+dy,x2+dx,y2+dy]
    # Even a low-confidence second plate is ambiguity, not permission to choose a car.
    accepted=not too_many and len(candidates)==1 and candidates[0]['confidence']>=threshold()
    reason='too_many_regions' if too_many else 'accepted' if accepted else ('no_plate' if not candidates else ('multiple_plates' if len(candidates)>1 else 'low_confidence'))
    return {'plate':candidates[0]['plate'] if accepted else None,
        'confidence':candidates[0]['confidence'] if candidates else 0.0,
        'needs_review':not accepted,'reason':reason,'candidates':candidates,'text_lines':lines,
        'image_size':[width,height],'elapsed_ms':round((time.perf_counter()-started)*1000,1)}
