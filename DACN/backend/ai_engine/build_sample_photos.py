"""Synthetic static camera inputs, never precomputed recognition results."""
import json
from pathlib import Path
from PIL import Image, ImageFilter
from ai_engine.synthetic_dataset import scene


def build():
    folder=Path(__file__).resolve().parents[1]/'test_data';folder.mkdir(exist_ok=True)
    rows=[]
    for ident,index,vehicle,energy,label in [
        ('car_gas',152,'CAR','GASOLINE','Ô tô xăng'),('motorbike_gas',153,'MOTORBIKE','GASOLINE','Xe máy xăng'),
        ('car_electric',154,'CAR','ELECTRIC','Ô tô điện'),('motorbike_electric',156,'MOTORBIKE','ELECTRIC','Xe máy điện')]:
        image,plate,_=scene(index)
        for variant,photo,description in [('clear',image,'rõ'),('blurred',image.filter(ImageFilter.GaussianBlur(.7)),'hơi mờ'),('tilted',image.rotate(2,resample=Image.Resampling.BICUBIC),'hơi lệch')]:
            name=f'{ident}_{variant}'
            photo.save(folder/(name+'.jpg'),quality=95)
            rows.append(dict(id=name,filename=name+'.jpg',label=label+' · '+description,vehicle_type=vehicle,energy_type=energy,plate=plate))
    Image.new('RGB',(640,384),'#a2aaa4').save(folder/'blank.jpg')
    rows.append(dict(id='blank',filename='blank.jpg',label='Không có biển số · kiểm tra ngoại lệ',vehicle_type=None,energy_type=None,plate=None))
    (folder/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':build()
