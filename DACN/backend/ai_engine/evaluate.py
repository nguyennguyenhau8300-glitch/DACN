"""Evaluate exact accepted-plate matches on a user-labeled image manifest."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from hashlib import file_digest
from pathlib import Path
from time import perf_counter

from .detector import detector_status, model_path
from .recognizer import normalize_plate, read_image, recognize
from .split_audit import audit_holdout

def edit_distance(expected, predicted):
    previous = list(range(len(predicted) + 1))
    for i, expected_char in enumerate(expected, 1):
        row = [i]
        for j, predicted_char in enumerate(predicted, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (expected_char != predicted_char)))
        previous = row
    return previous[-1]

def plate_outcome(expected, predicted):
    if expected is None:
        return 'correct_rejection' if predicted is None else 'false_accept'
    if predicted is None:
        return 'review_required'
    return 'exact_read' if expected == predicted else 'wrong_plate_accepted'


def score_image(item, root, *, photo):
    started = perf_counter()
    data = (root / item['image']).read_bytes()
    expected = normalize_plate(item['plate']) if item.get('plate') else None
    expected_type = item.get('vehicle_type')
    condition = item.get('condition')
    if expected_type not in (None, 'CAR', 'MOTORBIKE'):
        raise ValueError(f"Loại xe không hợp lệ trong ảnh {item['image']}.")
    if condition is not None and not isinstance(condition, str):
        raise ValueError(f"Điều kiện chụp phải là chuỗi trong ảnh {item['image']}.")
    source = read_image(data) if expected_type else data
    result = recognize(source, item.get('roi'), uploaded_photo=photo)
    detected = result['plate']
    boxes = result.get('detections') or result.get('candidates') or []
    vehicle = None
    if expected_type:
        from services.ai_service import preview_vehicle

        vehicle = preview_vehicle(source, boxes[0]['box'] if len(boxes) == 1 else None, result)
    return {
        'image': item['image'], 'condition': condition or 'unspecified',
        'expected': expected, 'predicted': detected, 'exact_match': detected == expected,
        'outcome': plate_outcome(expected, detected), 'reason': result['reason'],
        'confidence': result['confidence'], 'elapsed_ms': result['elapsed_ms'],
        'pipeline_ms': round((perf_counter() - started) * 1000, 1),
        'needs_review': result.get('needs_review', detected is None),
        'ocr_candidates': [candidate['plate'] for candidate in result.get('candidates', [])],
        'vehicle_expected': expected_type, 'vehicle_predicted': vehicle['type'] if vehicle else None,
        'vehicle_reason': vehicle['reason'] if vehicle else None,
    }


def summarize(results):
    accepted = [r for r in results if r['predicted'] is not None]
    positives = [r for r in results if r['expected'] is not None]
    characters = sum(len(r['expected']) for r in positives)
    errors = sum(edit_distance(r['expected'], r['predicted'] or '') for r in positives)
    conditions = defaultdict(Counter)
    for row in results:
        conditions[row['condition']][row['outcome']] += 1
    vehicle_labels = [row for row in results if row['vehicle_expected']]
    return {'images':len(results),'exact_matches':sum(r['exact_match'] for r in results),
        'accepted':len(accepted),'wrong_accepts':sum(not r['exact_match'] for r in accepted),
        'positive_images':len(positives),'negative_images':len(results)-len(positives),
        'positive_plate_accuracy':sum(r['exact_match'] for r in positives)/len(positives) if positives else None,
        'negative_false_accepts':sum(r['predicted'] is not None for r in results if r['expected'] is None),
        'character_error_rate':errors/characters if characters else None,
        'mean_elapsed_ms':sum(r['elapsed_ms'] for r in results)/len(results),
        'outcomes':dict(Counter(row['outcome'] for row in results)),
        'conditions':{key:dict(counts) for key, counts in conditions.items()},
        'vehicle_types':{
            'labeled':len(vehicle_labels),
            'correct':sum(row['vehicle_predicted'] == row['vehicle_expected'] for row in vehicle_labels),
            'unknown':sum(row['vehicle_predicted'] is None for row in vehicle_labels),
        },
        'results':results}


def write_errors(path, rows):
    fields = ('image', 'condition', 'expected', 'predicted', 'outcome', 'reason', 'confidence',
              'needs_review', 'vehicle_expected', 'vehicle_predicted', 'vehicle_reason')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            if not row['exact_match'] or row['vehicle_expected'] != row['vehicle_predicted']:
                writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description='Đo đọc đúng toàn biển, yêu cầu kiểm tra lại và phân loại xe trên ảnh có nhãn.',
        epilog=('Với --verify-holdout, thêm split, vehicle_group, capture_session và camera_id cho mỗi ảnh. '
                'Ảnh test cần label_source=manual và không có roi; ảnh không biển có plate=null.'),
    )
    parser.add_argument('manifest', type=Path, help='JSON list: image, plate (or null), optional vehicle_type and condition')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--errors-csv', type=Path)
    parser.add_argument('--photo', action='store_true', help='Use the same pipeline as the photo upload API')
    parser.add_argument('--verify-holdout', action='store_true',
                        help='Audit train/val/test groups and evaluate only the labeled, full-frame test images')
    args = parser.parse_args()
    root = args.manifest.parent
    photo = args.photo or args.verify_holdout
    try:
        labels = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        if not isinstance(labels, list) or not labels or not all(isinstance(item, dict) for item in labels):
            raise ValueError('Manifest cần là danh sách ảnh JSON không rỗng.')
        split_audit = audit_holdout(labels, root) if args.verify_holdout else None
        if split_audit is not None:
            if not split_audit['passed']:
                raise ValueError(f"Các tập dữ liệu trùng nhóm: {json.dumps(split_audit['overlap'])}")
            labels = [item for item in labels if item['split'] == 'test']
        rows = [score_image(item, root, photo=photo) for item in labels]
    except (OSError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    summary = summarize(rows)
    summary['split_audit'] = split_audit
    summary['photo_upload_pipeline'] = photo
    summary['detector'] = detector_status(photo=photo)
    weights = model_path(photo=photo)
    if weights and weights.is_file():
        with weights.open('rb') as model:
            summary['detector']['weights_sha256'] = file_digest(model, 'sha256').hexdigest()
    if args.errors_csv:
        write_errors(args.errors_csv, rows)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
