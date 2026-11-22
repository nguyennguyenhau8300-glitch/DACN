-- Additive migration. Simulation thresholds are defined in alert_service.py.
ALTER TABLE iot_devices ADD COLUMN IF NOT EXISTS monitoring_since TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
CREATE TABLE IF NOT EXISTS incidents (
    id BIGSERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES iot_devices(id) ON DELETE SET NULL,
    parking_lot_id INTEGER NOT NULL REFERENCES parking_lots(id) ON DELETE CASCADE,
    parking_spot_id INTEGER REFERENCES parking_spots(id) ON DELETE SET NULL,
    device_code VARCHAR(100) NOT NULL,
    spot_code VARCHAR(30) NOT NULL,
    kind VARCHAR(30) NOT NULL CHECK (kind IN ('OVERHEAT','CHARGER_FAULT','CONNECTION_LOST','WRONG_PARKING')),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('WARNING','CRITICAL')),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    message VARCHAR(500) NOT NULL,
    details JSON NOT NULL,
    opened_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    acknowledged_at TIMESTAMP,
    acknowledged_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    resolution VARCHAR(300)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_open_device_kind ON incidents(device_id, kind) WHERE status != 'RESOLVED';
CREATE INDEX IF NOT EXISTS ix_incident_lot_time ON incidents(parking_lot_id, opened_at DESC);
