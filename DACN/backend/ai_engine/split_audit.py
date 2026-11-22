"""Check that test images do not reuse identities or captures declared in other splits."""

from hashlib import file_digest
from itertools import combinations

from .recognizer import normalize_plate


def audit_holdout(labels, root):
    fields = ('image_sha256', 'plate', 'vehicle_group', 'capture_session', 'camera_id')
    groups = {split: {field: set() for field in fields} for split in ('train', 'val', 'test')}
    counts = dict.fromkeys(groups, 0)
    for index, row in enumerate(labels, 1):
        split = row.get('split')
        if not isinstance(split, str) or split not in groups or not isinstance(row.get('image'), str) or not row['image'].strip():
            raise ValueError(f'Dòng {index} cần image và split là train, val hoặc test.')
        if 'plate' not in row or (row['plate'] is not None and not isinstance(row['plate'], str)):
            raise ValueError(f'Dòng {index} cần plate hoặc null cho ảnh không có biển.')
        plate = normalize_plate(row['plate']) if row['plate'] else None
        if row['plate'] is not None and not plate:
            raise ValueError(f'Dòng {index} có nhãn biển số rỗng.')
        for field in ('vehicle_group', 'capture_session', 'camera_id'):
            value = row.get(field)
            if field == 'vehicle_group' and plate is None and value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Dòng {index} thiếu {field}.')
            groups[split][field].add(value.strip().casefold())
        if split == 'test' and (row.get('label_source') != 'manual' or row.get('roi') is not None):
            raise ValueError(f'Dòng {index} cần nhãn kiểm tay và ảnh nguyên khung.')
        if plate:
            groups[split]['plate'].add(plate)
        with (root / row['image']).open('rb') as image:
            groups[split]['image_sha256'].add(file_digest(image, 'sha256').hexdigest())
        counts[split] += 1

    if not all(counts.values()):
        raise ValueError('Cần ít nhất một ảnh trong mỗi tập train, val và test.')
    overlaps = {}
    for left, right in combinations(groups, 2):
        matches = {field: len(groups[left][field] & groups[right][field]) for field in fields}
        overlaps[f'{left}:{right}'] = matches
    return {
        'counts': counts,
        'overlap': overlaps,
        'passed': not any(count for pairs in overlaps.values() for count in pairs.values()),
        'scope': 'Checks supplied grouping labels and exact image hashes across splits.',
    }
