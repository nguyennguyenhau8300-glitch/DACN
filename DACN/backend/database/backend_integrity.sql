CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_vehicle ON parking_sessions(vehicle_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_spot ON parking_sessions(parking_spot_id) WHERE status = 'ACTIVE' AND parking_spot_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_success_payment_session ON payments(parking_session_id) WHERE status = 'SUCCESS';
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_price_category ON pricing_rules(parking_lot_id,vehicle_type,energy_type) WHERE is_active = TRUE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_code ON parking_spots(sensor_code) WHERE sensor_code IS NOT NULL;
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conrelid = 'reservations'::regclass AND conname = 'ck_reservation_slot_end'
    ) THEN
        ALTER TABLE reservations ADD CONSTRAINT ck_reservation_slot_end
            CHECK (end_time IS NULL OR (start_time < expiry_time AND expiry_time <= end_time));
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_immediate_reservation_spot ON reservations(parking_spot_id) WHERE end_time IS NULL AND status IN ('PENDING','CONFIRMED');
CREATE UNIQUE INDEX IF NOT EXISTS uq_immediate_reservation_vehicle ON reservations(vehicle_id) WHERE end_time IS NULL AND status IN ('PENDING','CONFIRMED');
DROP INDEX IF EXISTS uq_live_reservation_spot;
DROP INDEX IF EXISTS uq_live_reservation_vehicle;
CREATE INDEX IF NOT EXISTS ix_scheduled_reservation_spot ON reservations(parking_spot_id, start_time) WHERE end_time IS NOT NULL AND status IN ('PENDING','CONFIRMED');
CREATE INDEX IF NOT EXISTS ix_scheduled_reservation_vehicle ON reservations(vehicle_id, start_time) WHERE end_time IS NOT NULL AND status IN ('PENDING','CONFIRMED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_plate_normalized ON vehicles (upper(replace(replace(replace(license_plate, '-', ''), '.', ''), ' ', '')));
