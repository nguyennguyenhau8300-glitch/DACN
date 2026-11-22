"""Preview/apply the requested 95-space lot, keeping every referenced spot."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from database import SessionLocal
from services.layout_service import CAPACITY_FIELDS
from services.layout_resize import plan_resize, apply_resize
from services.realtime import invalidate_on_commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lot-id', type=int, required=True)
    parser.add_argument('--apply', action='store_true', help='Without this flag, only preview.')
    args = parser.parse_args()
    config = SimpleNamespace(car_capacity=30, motorbike_capacity=65,
                             electric_car_capacity=10, electric_motorbike_capacity=25)
    with SessionLocal() as db:
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        lot, remove = plan_resize(db, args.lot_id, config)
        result = {'lot_id': lot.id, 'removed_spots': len(remove),
                  'remove_codes': [s.spot_code for s in remove],
                  'capacity': {f: getattr(config, f) for f in CAPACITY_FIELDS}, 'applied': args.apply}
        if args.apply:
            # A local snapshot exists before any persistent deletion.
            backup = ROOT.parent / 'work' / 'capacity-backups' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
            backup.parent.mkdir(parents=True, exist_ok=True)
            def snapshot(row):
                return {col.name: getattr(row, col.name) for col in row.__table__.columns}
            backup.write_text(json.dumps({'lot': snapshot(lot), 'removed_spots': [snapshot(s) for s in remove]},
                                         ensure_ascii=False, indent=2, default=str), encoding='utf-8')
            result['backup'] = str(backup)
            # DDL and resize commit together. A failed operation rolls everything back.
            db.connection().exec_driver_sql((ROOT / 'backend/database/capacity_defaults.sql').read_text(encoding='utf-8'))
            result['summary'] = apply_resize(db, lot, remove, config)
            invalidate_on_commit(db)
            db.commit()
        else:
            db.rollback()
        print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
