"""Train YOLOv8 on an explicit real dataset or the separately labelled synthetic demo."""
import argparse
import json
import os
from pathlib import Path
import platform
import time

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path)
    parser.add_argument('--synthetic',action='store_true')
    parser.add_argument('--epochs',type=int,default=30)
    parser.add_argument('--name',default='synthetic-yolov8')
    args=parser.parse_args()
    if bool(args.data)==args.synthetic: parser.error('Chọn đúng một nguồn: --data dataset.yaml hoặc --synthetic')
    os.environ['YOLO_OFFLINE']='true'
    os.environ['YOLO_AUTOINSTALL']='false'
    from ultralytics import YOLO
    import torch
    torch.set_num_threads(4)
    root=Path(__file__).resolve().parents[3]
    output=root/'ket_qua/ai'
    if args.synthetic:
        from ai_engine.synthetic_dataset import generate
        data=generate(root/'du_lieu_ai/synthetic')
    else: data=args.data.resolve()
    model=YOLO('yolov8n.yaml')
    start=time.perf_counter()
    model.train(data=str(data),epochs=args.epochs,imgsz=320,batch=8,workers=0,device='cpu',pretrained=False,
                project=str(output),name=args.name,exist_ok=True,plots=True,seed=20261028,cache=False,patience=10,
                mosaic=.3,fliplr=0,amp=False,save=True)
    best=YOLO(str(output/args.name/'weights/best.pt'))
    metrics=best.val(data=str(data),split='test',imgsz=320,batch=8,workers=0,device='cpu',plots=True)
    metadata={'dataset_kind':'SYNTHETIC_DEMO' if args.synthetic else 'USER_DATASET','dataset':str(data),
              'epochs_requested':args.epochs,'elapsed_seconds':round(time.perf_counter()-start,2),'python':platform.python_version(),
              'torch':torch.__version__,'metrics_test':metrics.results_dict,
              'notice':'Synthetic metrics are not real-camera accuracy.' if args.synthetic else 'Verify dataset provenance and test-set separation.'}
    (output/args.name/'experiment.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata,indent=2))
