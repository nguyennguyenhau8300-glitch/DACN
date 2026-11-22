ALTER TABLE iot_devices ADD COLUMN IF NOT EXISTS simulation_only BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE barrier_commands ADD COLUMN IF NOT EXISTS opened_at TIMESTAMP;
CREATE TABLE IF NOT EXISTS internal_demo_runs (
 id VARCHAR(40) PRIMARY KEY,
 parking_lot_id INTEGER NOT NULL REFERENCES parking_lots(id),
 user_id INTEGER NOT NULL REFERENCES users(id),
 kind VARCHAR(20) NOT NULL,
 status VARCHAR(30) NOT NULL,
 parking_session_id INTEGER REFERENCES parking_sessions(id),
 sandbox_order_id VARCHAR(40) REFERENCES sandbox_orders(id),
 request_spec JSON NOT NULL,
 steps JSON NOT NULL DEFAULT '[]',
 result JSON NOT NULL DEFAULT '{}',
 created_at TIMESTAMP NOT NULL,
 completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_internal_demo_lot ON internal_demo_runs(parking_lot_id,created_at);
