ALTER TABLE parking_sessions ADD COLUMN IF NOT EXISTS fee_breakdown JSON;

CREATE TABLE IF NOT EXISTS routing_maps (
    parking_lot_id INTEGER PRIMARY KEY REFERENCES parking_lots(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    graph JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS sandbox_orders (
    id VARCHAR(40) PRIMARY KEY,
    parking_session_id INTEGER NOT NULL REFERENCES parking_sessions(id),
    provider VARCHAR(20) NOT NULL CHECK (provider IN ('INTERNAL','VNPAY')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','SUCCESS','FAILED','EXPIRED','CANCELLED')),
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    transaction_code VARCHAR(100) UNIQUE
);
CREATE INDEX IF NOT EXISTS ix_sandbox_orders_session ON sandbox_orders(parking_session_id);
CREATE TABLE IF NOT EXISTS tariff_schedules (
    pricing_rule_id INTEGER PRIMARY KEY REFERENCES pricing_rules(id) ON DELETE CASCADE,
    bands JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS barrier_commands (
    id VARCHAR(40) PRIMARY KEY,
    parking_lot_id INTEGER NOT NULL REFERENCES parking_lots(id),
    parking_session_id INTEGER NOT NULL REFERENCES parking_sessions(id),
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('ENTRY','EXIT')),
    status VARCHAR(20) NOT NULL DEFAULT 'SIMULATED',
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_barrier_commands_lot ON barrier_commands(parking_lot_id);
