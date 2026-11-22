"""Build a labelled synthetic moving-input clip, never a pre-annotated AI result."""
import json
from pathlib import Path
import math
import cv2
import numpy as np
from ai_engine.synthetic_dataset import scene


def build():
    output=Path(__file__).resolve().parent/'assets';output.mkdir(exist_ok=True)
    writer=cv2.VideoWriter(str(output/'camera-demo.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),10,(640,384))
    if not writer.isOpened():raise RuntimeError('Không tạo được đầu vào camera mô phỏng')
    plates=[]
    try:
        for index in (152,153,154):
            image,plate,_=scene(index);plates.append(plate)
            source=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
            for frame in range(40):
                # A small continuous pan changes the genuine detection coordinates each frame.
                matrix=np.float32([[1,0,18*math.sin(frame/8)],[0,1,5*math.cos(frame/8)]])
                writer.write(cv2.warpAffine(source,matrix,(640,384),borderMode=cv2.BORDER_REFLECT_101))
            for _ in range(10):writer.write(np.zeros((384,640,3),dtype=np.uint8))
    finally:writer.release()
    (output/'camera-demo.json').write_text(json.dumps({'synthetic':True,'plates':plates,'moving_input':True,'fps':10,'frames':150},indent=2))


if __name__=='__main__':build()
