"""Evaluate exact accepted-plate matches on a user-labeled image manifest."""
import argparse
import json
from pathlib import Path
from .recognizer import recognize,normalize_plate

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('manifest',type=Path,help='JSON list: image, plate (or null), optional roi')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    labels=json.loads(args.manifest.read_text(encoding='utf-8'))
    if not labels: parser.error('Manifest không có ảnh')
    results=[]
    for item in labels:
        image=args.manifest.parent/item['image']
        expected=normalize_plate(item['plate']) if item.get('plate') else None
        result=recognize(image.read_bytes(),item.get('roi'))
        results.append({'image':item['image'],'expected':expected,'predicted':result['plate'],
            'exact_match':result['plate']==expected,'reason':result['reason'],
            'confidence':result['confidence'],'elapsed_ms':result['elapsed_ms']})
    accepted=[r for r in results if r['predicted'] is not None]
    summary={'images':len(results),'exact_matches':sum(r['exact_match'] for r in results),
        'accepted':len(accepted),'wrong_accepts':sum(not r['exact_match'] for r in accepted),
        'results':results}
    text=json.dumps(summary,ensure_ascii=False,indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text+'\n',encoding='utf-8')
if __name__=='__main__':main()
