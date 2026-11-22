CREATE TABLE IF NOT EXISTS simulation_sites (
 parking_lot_id INTEGER PRIMARY KEY REFERENCES parking_lots(id),
 created_by INTEGER NOT NULL REFERENCES users(id),
 enabled BOOLEAN NOT NULL DEFAULT FALSE,
 paused_devices JSON NOT NULL DEFAULT '[]',
 desired_states JSON NOT NULL DEFAULT '{}',
 created_at TIMESTAMP NOT NULL
);
ALTER TABLE simulation_sites ADD COLUMN IF NOT EXISTS desired_states JSON NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS simulation_actions (
 id VARCHAR(40) PRIMARY KEY,
 parking_lot_id INTEGER NOT NULL REFERENCES simulation_sites(parking_lot_id),
 device_id INTEGER NOT NULL REFERENCES iot_devices(id),
 sequence BIGINT NOT NULL,
 transport VARCHAR(10) NOT NULL CHECK(transport IN ('HTTP','MQTT')),
 origin VARCHAR(20) NOT NULL,
 payload JSON NOT NULL,
 ack JSON,
 status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
 sent_at TIMESTAMP NOT NULL,
 completed_at TIMESTAMP,
 elapsed_ms DOUBLE PRECISION,
 CONSTRAINT uq_simulation_sequence UNIQUE(device_id,sequence)
);
CREATE TABLE IF NOT EXISTS camera_observations (
 id VARCHAR(40) PRIMARY KEY,
 parking_lot_id INTEGER NOT NULL REFERENCES simulation_sites(parking_lot_id),
 parking_session_id INTEGER REFERENCES parking_sessions(id),
 license_plate VARCHAR(20) NOT NULL,
 confidence DOUBLE PRECISION NOT NULL,
 detection_confidence DOUBLE PRECISION,
 box JSON NOT NULL,
 frame_id INTEGER NOT NULL,
 captured_at TIMESTAMP NOT NULL,
 recorded_at TIMESTAMP NOT NULL,
 direction VARCHAR(10) NOT NULL CHECK(direction IN ('PREVIEW','ENTRY','EXIT')),
 outcome VARCHAR(20) NOT NULL,
 message VARCHAR(250) NOT NULL,
 source_kind VARCHAR(10) NOT NULL DEFAULT 'RTSP'
);
CREATE INDEX IF NOT EXISTS ix_camera_observations_lot ON camera_observations(parking_lot_id,recorded_at);
