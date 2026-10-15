-- Additive, repeatable migration. No modification to parking or charging states.
CREATE TABLE IF NOT EXISTS iot_devices (
 id SERIAL PRIMARY KEY,
 device_code VARCHAR(100) NOT NULL UNIQUE,
 parking_spot_id INTEGER NOT NULL REFERENCES parking_spots(id) ON DELETE CASCADE,
 kind VARCHAR(20) NOT NULL CHECK(kind IN ('SENSOR','CHARGER')),
 key_hash VARCHAR(64) NOT NULL,
 enabled BOOLEAN NOT NULL DEFAULT TRUE,
 offline_after_seconds INTEGER NOT NULL DEFAULT 90 CHECK(offline_after_seconds BETWEEN 10 AND 3600),
 last_seen_at TIMESTAMP,
 last_telemetry_at TIMESTAMP,
 last_sequence BIGINT NOT NULL DEFAULT 0,
 last_payload JSON,
 CONSTRAINT uq_iot_spot_kind UNIQUE(parking_spot_id,kind)
);
CREATE INDEX IF NOT EXISTS ix_iot_devices_parking_spot_id ON iot_devices(parking_spot_id);
CREATE TABLE IF NOT EXISTS iot_events (
 id BIGSERIAL PRIMARY KEY,
 device_id INTEGER NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
 sequence BIGINT NOT NULL,
 payload JSON NOT NULL,
 result JSON NOT NULL,
 received_at TIMESTAMP NOT NULL,
 CONSTRAINT uq_iot_event_sequence UNIQUE(device_id,sequence)
);
CREATE INDEX IF NOT EXISTS ix_iot_events_device_id ON iot_events(device_id);
