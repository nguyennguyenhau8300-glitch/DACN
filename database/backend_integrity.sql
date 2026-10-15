CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_vehicle ON parking_sessions(vehicle_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_spot ON parking_sessions(parking_spot_id) WHERE status = 'ACTIVE' AND parking_spot_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_success_payment_session ON payments(parking_session_id) WHERE status = 'SUCCESS';
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_price_category ON pricing_rules(parking_lot_id,vehicle_type,energy_type) WHERE is_active = TRUE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_code ON parking_spots(sensor_code) WHERE sensor_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_live_reservation_spot ON reservations(parking_spot_id) WHERE status IN ('PENDING','CONFIRMED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_plate_normalized ON vehicles (upper(replace(replace(replace(license_plate, '-', ''), '.', ''), ' ', '')));
CREATE UNIQUE INDEX IF NOT EXISTS uq_live_reservation_vehicle ON reservations(vehicle_id) WHERE status IN ('PENDING','CONFIRMED');
