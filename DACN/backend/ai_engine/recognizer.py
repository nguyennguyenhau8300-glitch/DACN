"""YOLOv8 plate detection followed by RapidOCR and conservative grouping."""
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
    is_jpeg = data.startswith(b'\xff\xd8\xff')
    is_png = data.startswith(b'\x89PNG\r\n\x1a\n')
    is_webp = data.startswith(b'RIFF') and data[8:12] == b'WEBP'
    if not (is_jpeg or is_png or is_webp):
        raise ImageError('Chỉ nhận ảnh JPEG, PNG hoặc WebP')
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

def nearby(a,b,*,row_overlap=.35):
    ax,ay,ar,ab=a; bx,by,br,bb=b
    ah,bh=max(1,ab-ay),max(1,bb-by)
    horizontal = abs((ay+ab-by-bb)/2) < .6*max(ah,bh) and 0 <= bx-ar < 2*max(ah,bh)
    overlap = max(0,min(ar,br)-max(ax,bx))
    # Tilted lines can have overlapping axis-aligned bounds even on separate rows.
    row_gap = by-ab
    vertical = -row_overlap*min(ah,bh) <= row_gap < 2.5*max(ah,bh) and overlap > .4*min(ar-ax,br-bx)
    return horizontal or vertical

def collect_candidates(texts,scores,boxes,*,single_plate_crop=False):
    items=[{'text':str(t),'confidence':float(s),'box':rect(b)} for t,s,b in zip(texts,scores,boxes)]
    items=sorted(items,key=lambda x:(x['box'][1],x['box'][0]))[:80]
    candidates={}
    def add(group):
        raw=''.join(x['text'] for x in group)
        if not re.fullmatch(r'[A-Za-z0-9 .·\-\s]+',raw): return
        normalized=normalize_plate(raw)
        if not PLATE.fullmatch(normalized): return
        score=min(x['confidence'] for x in group)
        boxes=[x['box'] for x in group]
        item={'plate':normalized,'confidence':score,
            'raw_text':' '.join(x['text'] for x in group),
            'box':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]}
        if normalized not in candidates or score>candidates[normalized]['confidence']:
            candidates[normalized]=item
    # Inside one detected plate, the OCR boxes are often taller than the letters.
    row_overlap = .5 if single_plate_crop else .35
    neighbors = [
        [j for j, b in enumerate(items) if i != j and nearby(a['box'], b['box'], row_overlap=row_overlap)]
        for i, a in enumerate(items)
    ]
    for i, a in enumerate(items):
        add([a])
        for j in neighbors[i]:
            b = items[j]
            add([a, b])
            for k in neighbors[j]:
                if k != i:
                    add([a, b, items[k]])
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
    from .detector import detector_status
    return {'engine':'RapidOCR / ONNX Runtime (CPU)','loaded':_ready,
        'detector':detector_status(),
        'photo_detector':detector_status(photo=True),
        'confidence_threshold':threshold(),'max_upload_mb':8,'max_pixels':MAX_PIXELS,
        'supported_formats':['JPEG','PNG','WEBP']}

def threshold():
    value=float(os.getenv('AI_MIN_CONFIDENCE','0.85'))
    if not 0.5 <= value <= 1: raise ValueError('AI_MIN_CONFIDENCE phải nằm trong [0.5, 1]')
    return value

def read_plate_text(image,dx=0,dy=0,*,single_plate_crop=False):
    global _ready
    if not _lock.acquire(timeout=5): raise EngineBusy('AI đang bận; thử lại sau')
    try:
        import numpy as np
        pixels=np.asarray(image)[:,:,::-1].copy()
        options={'use_cls':False} if single_plate_crop else {}
        output=_get_engine()(pixels,**options)
        _ready=True
        texts=output.txts if output.txts is not None else []
        scores=output.scores if output.scores is not None else []
        boxes=output.boxes if output.boxes is not None else []
        candidates,lines=collect_candidates(texts,scores,boxes,single_plate_crop=single_plate_crop)
    except Exception as exc:
        raise EngineUnavailable('Không chạy được mô hình OCR; kiểm tra cài đặt AI') from exc
    finally:
        _lock.release()
    for item in candidates+lines:
        x1,y1,x2,y2=item['box'];item['box']=[x1+dx,y1+dy,x2+dx,y2+dy]
    return candidates,lines,len(texts)>80

def confirm_photo_read(image, dx, dy, candidates, *, detected_crop, minimum):
    """Check uncertain reads across bounded contrast and sharpness variants."""
    from PIL import Image, ImageFilter, ImageOps

    if len(candidates) > 1 or (not candidates and not detected_crop):
        return candidates, False
    if candidates and candidates[0]['confidence'] >= max(.96, minimum):
        return candidates, False
    if not detected_crop and candidates:
        x1,y1,x2,y2 = candidates[0]['box']
        margin = max(6, round((y2-y1)*.25))
        a,b = max(0,x1-margin-dx),max(0,y1-margin-dy)
        c,d = min(image.width,x2+margin-dx),min(image.height,y2+margin-dy)
        if c-a >= 12 and d-b >= 12:
            image = image.crop((a,b,c,d))
            dx,dy = dx+a,dy+b
    gray = ImageOps.grayscale(image)
    low,high = gray.getextrema()
    if high-low < 10:
        return candidates, False
    scale = min(2, 960/max(gray.size))
    new_size = tuple(max(1,round(value*scale)) for value in gray.size)
    sx,sy = new_size[0]/gray.width,new_size[1]/gray.height
    gray = gray.resize(new_size,Image.Resampling.BICUBIC)
    variants = [
        ImageOps.autocontrast(gray,cutoff=1),
        gray.filter(ImageFilter.UnsharpMask(radius=1.6,percent=160,threshold=2)),
    ]
    evidence = list(candidates)
    for variant in variants:
        readings,_,too_many = read_plate_text(variant.convert('RGB'),single_plate_crop=True)
        if too_many or len(readings)>1:
            return candidates, True
        if readings:
            candidate = readings[0]
            x1,y1,x2,y2 = candidate['box']
            candidate['box'] = [dx+round(x1/sx),dy+round(y1/sy),dx+round(x2/sx),dy+round(y2/sy)]
            evidence.append(candidate)
    if len({r['plate'] for r in evidence}) > 1:
        return candidates, True
    strong = [r for r in evidence if r['confidence'] >= minimum]
    if len(strong) >= 2:
        match = max(strong,key=lambda r:r['confidence'])
        return [{**match,'confidence':min(r['confidence'] for r in strong)}], False
    return candidates, bool(evidence)


def recognize(data,roi=None,*,uploaded_photo=False):
    from PIL.Image import Image

    started=time.perf_counter()
    image=data if isinstance(data, Image) else read_image(data)
    source=image
    width,height=image.size
    dx=dy=0
    detection=None
    if roi is None:
        from .detector import detect
        try:
            detection=detect(image,photo=uploaded_photo)
            if uploaded_photo and detection==[]:
                detection=detect(image,photo=True,size=640)
        except Exception as exc: raise EngineUnavailable('Không chạy được YOLOv8; kiểm tra trọng số và thư viện AI') from exc
        if detection is not None:
            if len(detection)>1 or (not detection and not uploaded_photo):
                return {'plate':None,'confidence':0.0,'needs_review':True,'reason':'multiple_plates' if detection else 'no_plate',
                        'candidates':[],'text_lines':[],'image_size':[width,height],'elapsed_ms':round((time.perf_counter()-started)*1000,1),'detections':detection}
        if detection:
            x1,y1,x2,y2=detection[0]['box']
            if uploaded_photo:
                pad_x,pad_y=round((x2-x1)*.18),round((y2-y1)*.12)
                x1,y1=max(0,x1-pad_x),max(0,y1-pad_y)
                x2,y2=min(width,x2+pad_x),min(height,y2+pad_y)
            if not uploaded_photo or min(x2-x1,y2-y1)>=32:
                roi=[x1,y1,x2-x1,y2-y1]
            else:
                detection=[]
    if roi is not None:
        if len(roi)!=4: raise ImageError('ROI gồm x, y, width, height')
        dx,dy,w,h=roi
        if min(dx,dy)<0 or min(w,h)<32 or dx+w>width or dy+h>height:
            raise ImageError('ROI phải nằm trong ảnh, mỗi chiều ít nhất 32 pixel')
        image=image.crop((dx,dy,dx+w,dy+h))
    detected_crop=uploaded_photo and bool(detection)
    candidates,lines,too_many=read_plate_text(image,dx,dy,single_plate_crop=detected_crop)
    minimum=threshold()
    uncertain=False
    if uploaded_photo and not too_many:
        candidates,uncertain=confirm_photo_read(image,dx,dy,candidates,detected_crop=detected_crop,minimum=minimum)
    if detected_crop and not too_many and not candidates and not uncertain:
        full_candidates,full_lines,full_too_many=read_plate_text(source)
        if len(full_candidates)==1:
            left,top,right,bottom=full_candidates[0]['box']
            center_x,center_y=(left+right)/2,(top+bottom)/2
            if not (dx<=center_x<=dx+w and dy<=center_y<=dy+h):
                full_candidates=[]
        if full_candidates or full_too_many:
            candidates,lines,too_many=full_candidates,full_lines,full_too_many
            detection=[]
            if not too_many:
                candidates,uncertain=confirm_photo_read(source,0,0,candidates,detected_crop=False,minimum=minimum)
    # Even a low-confidence second plate is ambiguity, not permission to choose a car.
    accepted=not too_many and not uncertain and len(candidates)==1 and candidates[0]['confidence']>=minimum
    reason='too_many_regions' if too_many else 'inconsistent_photo_read' if uncertain else 'accepted' if accepted else ('no_plate' if not candidates else ('multiple_plates' if len(candidates)>1 else 'low_confidence'))
    return {'plate':candidates[0]['plate'] if accepted else None,
        'confidence':candidates[0]['confidence'] if candidates else 0.0,
        'needs_review':not accepted,'reason':reason,'candidates':candidates,'text_lines':lines,
        'image_size':[width,height],'elapsed_ms':round((time.perf_counter()-started)*1000,1),'detections':detection or []}
