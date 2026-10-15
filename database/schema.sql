-- =========================================================
-- SMART PARKING SYSTEM
-- Database: smart_parking_db
-- =========================================================


-- =========================================================
-- 1. USERS - TÀI KHOẢN
-- =========================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,

    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    date_of_birth DATE,
    hometown VARCHAR(200),

    role VARCHAR(20) NOT NULL DEFAULT 'CUSTOMER'
        CHECK (role IN ('ADMIN', 'MANAGER', 'SECURITY', 'CUSTOMER')),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 2. VEHICLES - PHƯƠNG TIỆN
-- =========================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id SERIAL PRIMARY KEY,

    user_id INTEGER REFERENCES users(id)
        ON DELETE SET NULL,

    license_plate VARCHAR(20) UNIQUE NOT NULL,

    vehicle_type VARCHAR(20) NOT NULL
        CHECK (vehicle_type IN ('MOTORBIKE', 'CAR', 'ELECTRIC_CAR')),

    brand VARCHAR(50),
    color VARCHAR(50),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 3. PARKING LOTS - BÃI XE
-- =========================================================
CREATE TABLE IF NOT EXISTS parking_lots (
    id SERIAL PRIMARY KEY,

    name VARCHAR(150) NOT NULL,
    address TEXT NOT NULL,

    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),

    description TEXT,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 4. PARKING AREAS - KHU VỰC/TẦNG
-- =========================================================
CREATE TABLE IF NOT EXISTS parking_areas (
    id SERIAL PRIMARY KEY,

    parking_lot_id INTEGER NOT NULL
        REFERENCES parking_lots(id)
        ON DELETE CASCADE,

    name VARCHAR(100) NOT NULL,

    floor_number INTEGER DEFAULT 1,

    description TEXT
);


-- =========================================================
-- 5. PARKING SPOTS - Ô ĐỖ
-- =========================================================
CREATE TABLE IF NOT EXISTS parking_spots (
    id SERIAL PRIMARY KEY,

    parking_area_id INTEGER NOT NULL
        REFERENCES parking_areas(id)
        ON DELETE CASCADE,

    spot_code VARCHAR(30) NOT NULL,

    spot_type VARCHAR(20) NOT NULL DEFAULT 'CAR'
        CHECK (spot_type IN (
            'MOTORBIKE',
            'CAR',
            'ELECTRIC_CAR',
            'DISABLED'
        )),

    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE'
        CHECK (status IN (
            'AVAILABLE',
            'OCCUPIED',
            'RESERVED',
            'MAINTENANCE'
        )),

    position_x DECIMAL(10,2),
    position_y DECIMAL(10,2),

    sensor_code VARCHAR(100),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (parking_area_id, spot_code)
);


-- =========================================================
-- 6. RESERVATIONS - ĐẶT CHỖ
-- =========================================================
CREATE TABLE IF NOT EXISTS reservations (
    id SERIAL PRIMARY KEY,

    user_id INTEGER NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    vehicle_id INTEGER NOT NULL
        REFERENCES vehicles(id)
        ON DELETE CASCADE,

    parking_spot_id INTEGER NOT NULL
        REFERENCES parking_spots(id)
        ON DELETE CASCADE,

    start_time TIMESTAMP NOT NULL,
    expiry_time TIMESTAMP NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING',
            'CONFIRMED',
            'COMPLETED',
            'CANCELLED',
            'EXPIRED'
        )),

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (expiry_time > start_time)
);


-- =========================================================
-- 7. PARKING SESSIONS - LƯỢT GỬI XE
-- =========================================================
CREATE TABLE IF NOT EXISTS parking_sessions (
    id SERIAL PRIMARY KEY,

    vehicle_id INTEGER NOT NULL
        REFERENCES vehicles(id),

    parking_spot_id INTEGER
        REFERENCES parking_spots(id)
        ON DELETE SET NULL,

    reservation_id INTEGER
        REFERENCES reservations(id)
        ON DELETE SET NULL,

    entry_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    exit_time TIMESTAMP,

    entry_plate_image TEXT,
    exit_plate_image TEXT,

    entry_plate_confidence DECIMAL(5,4),
    exit_plate_confidence DECIMAL(5,4),

    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'COMPLETED')),

    total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,

    CHECK (exit_time IS NULL OR exit_time >= entry_time)
);


-- =========================================================
-- 8. PRICING RULES - BẢNG GIÁ
-- =========================================================
CREATE TABLE IF NOT EXISTS pricing_rules (
    id SERIAL PRIMARY KEY,

    parking_lot_id INTEGER NOT NULL
        REFERENCES parking_lots(id)
        ON DELETE CASCADE,

    vehicle_type VARCHAR(20) NOT NULL
        CHECK (vehicle_type IN (
            'MOTORBIKE',
            'CAR',
            'ELECTRIC_CAR'
        )),

    first_hour_price DECIMAL(12,2) NOT NULL,
    additional_hour_price DECIMAL(12,2) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (first_hour_price >= 0),
    CHECK (additional_hour_price >= 0)
);


-- =========================================================
-- 9. PAYMENTS - THANH TOÁN
-- =========================================================
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,

    parking_session_id INTEGER NOT NULL
        REFERENCES parking_sessions(id),

    amount DECIMAL(12,2) NOT NULL,

    payment_method VARCHAR(30) NOT NULL
        CHECK (payment_method IN (
            'CASH',
            'VNPAY',
            'MOMO',
            'VIETQR'
        )),

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING',
            'SUCCESS',
            'FAILED',
            'CANCELLED'
        )),

    transaction_code VARCHAR(100),

    paid_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (amount >= 0)
);


-- =========================================================
-- 10. SENSOR LOGS - LỊCH SỬ CẢM BIẾN
-- =========================================================
CREATE TABLE IF NOT EXISTS sensor_logs (
    id BIGSERIAL PRIMARY KEY,

    parking_spot_id INTEGER NOT NULL
        REFERENCES parking_spots(id)
        ON DELETE CASCADE,

    sensor_status VARCHAR(20) NOT NULL
        CHECK (sensor_status IN ('AVAILABLE', 'OCCUPIED')),

    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- INDEX
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_vehicle_license_plate
ON vehicles(license_plate);

CREATE INDEX IF NOT EXISTS idx_parking_spot_status
ON parking_spots(status);

CREATE INDEX IF NOT EXISTS idx_reservation_user
ON reservations(user_id);

CREATE INDEX IF NOT EXISTS idx_reservation_spot
ON reservations(parking_spot_id);

CREATE INDEX IF NOT EXISTS idx_parking_session_vehicle
ON parking_sessions(vehicle_id);

CREATE INDEX IF NOT EXISTS idx_parking_session_status
ON parking_sessions(status);

CREATE INDEX IF NOT EXISTS idx_sensor_log_spot
ON sensor_logs(parking_spot_id);
-- Backend concurrency integrity
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_vehicle ON parking_sessions(vehicle_id) WHERE status = 'ACTIVE';
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_spot ON parking_sessions(parking_spot_id) WHERE status = 'ACTIVE' AND parking_spot_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_success_payment_session ON payments(parking_session_id) WHERE status = 'SUCCESS';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_code ON parking_spots(sensor_code) WHERE sensor_code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_live_reservation_spot ON reservations(parking_spot_id) WHERE status IN ('PENDING','CONFIRMED');

CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_plate_normalized ON vehicles (upper(replace(replace(replace(license_plate, '-', ''), '.', ''), ' ', '')));
CREATE UNIQUE INDEX IF NOT EXISTS uq_live_reservation_vehicle ON reservations(vehicle_id) WHERE status IN ('PENDING','CONFIRMED');

-- Energy categories and charging infrastructure

ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS energy_type VARCHAR(20) NOT NULL DEFAULT 'GASOLINE';
ALTER TABLE pricing_rules ADD COLUMN IF NOT EXISTS energy_type VARCHAR(20) NOT NULL DEFAULT 'GASOLINE';
ALTER TABLE parking_spots ADD COLUMN IF NOT EXISTS energy_type VARCHAR(20) NOT NULL DEFAULT 'GASOLINE';
ALTER TABLE parking_spots ADD COLUMN IF NOT EXISTS charger_type VARCHAR(20) NOT NULL DEFAULT 'NONE';
ALTER TABLE parking_spots ADD COLUMN IF NOT EXISTS charging_station_code VARCHAR(100);
ALTER TABLE parking_spots ADD COLUMN IF NOT EXISTS charging_port_code VARCHAR(30);
ALTER TABLE parking_spots ADD COLUMN IF NOT EXISTS charging_power_kw DECIMAL(8,2);
ALTER TABLE parking_spots ADD COLUMN IF NOT EXISTS charger_status VARCHAR(20) NOT NULL DEFAULT 'NOT_APPLICABLE';
ALTER TABLE parking_lots ADD COLUMN IF NOT EXISTS car_capacity INTEGER NOT NULL DEFAULT 50;
ALTER TABLE parking_lots ADD COLUMN IF NOT EXISTS motorbike_capacity INTEGER NOT NULL DEFAULT 120;
ALTER TABLE parking_lots ADD COLUMN IF NOT EXISTS electric_car_capacity INTEGER NOT NULL DEFAULT 20;
ALTER TABLE parking_lots ADD COLUMN IF NOT EXISTS electric_motorbike_capacity INTEGER NOT NULL DEFAULT 50;

DROP INDEX IF EXISTS uq_active_price_type;
UPDATE vehicles SET vehicle_type='CAR',energy_type='ELECTRIC' WHERE vehicle_type='ELECTRIC_CAR';
UPDATE pricing_rules SET vehicle_type='CAR',energy_type='ELECTRIC' WHERE vehicle_type='ELECTRIC_CAR';
UPDATE parking_spots SET spot_type='CAR',energy_type='ELECTRIC',charger_type='EV_CHARGER',
 charging_station_code='LEGACY-'||id,charging_port_code='01',charger_status='PLANNED' WHERE spot_type='ELECTRIC_CAR';
ALTER TABLE vehicles DROP CONSTRAINT IF EXISTS vehicles_vehicle_type_check;
ALTER TABLE vehicles ADD CONSTRAINT vehicles_vehicle_type_check CHECK(vehicle_type IN ('CAR','MOTORBIKE'));
ALTER TABLE pricing_rules DROP CONSTRAINT IF EXISTS pricing_rules_vehicle_type_check;
ALTER TABLE pricing_rules ADD CONSTRAINT pricing_rules_vehicle_type_check CHECK(vehicle_type IN ('CAR','MOTORBIKE'));
ALTER TABLE parking_spots DROP CONSTRAINT IF EXISTS parking_spots_spot_type_check;
ALTER TABLE parking_spots ADD CONSTRAINT parking_spots_spot_type_check CHECK(spot_type IN ('CAR','MOTORBIKE','DISABLED'));
ALTER TABLE vehicles DROP CONSTRAINT IF EXISTS vehicles_energy_check;
ALTER TABLE vehicles ADD CONSTRAINT vehicles_energy_check CHECK(energy_type IN ('GASOLINE','ELECTRIC'));
ALTER TABLE pricing_rules DROP CONSTRAINT IF EXISTS pricing_energy_check;
ALTER TABLE pricing_rules ADD CONSTRAINT pricing_energy_check CHECK(energy_type IN ('GASOLINE','ELECTRIC'));
ALTER TABLE parking_spots DROP CONSTRAINT IF EXISTS spot_charging_check;
ALTER TABLE parking_spots ADD CONSTRAINT spot_charging_check CHECK (
 (energy_type='GASOLINE' AND charger_type='NONE' AND charger_status='NOT_APPLICABLE' AND charging_station_code IS NULL AND charging_port_code IS NULL AND charging_power_kw IS NULL)
 OR (energy_type='ELECTRIC' AND ((spot_type='MOTORBIKE' AND charger_type='SOCKET') OR (spot_type IN ('CAR','DISABLED') AND charger_type='EV_CHARGER'))
 AND charging_station_code IS NOT NULL AND length(trim(charging_station_code))>0 AND charging_port_code IS NOT NULL AND length(trim(charging_port_code))>0
 AND charger_status IN ('PLANNED','READY','OFFLINE','MAINTENANCE') AND (charging_power_kw IS NULL OR charging_power_kw>0)));
ALTER TABLE parking_lots DROP CONSTRAINT IF EXISTS lot_capacity_check;
ALTER TABLE parking_lots ADD CONSTRAINT lot_capacity_check CHECK (
 car_capacity BETWEEN 30 AND 50 AND motorbike_capacity BETWEEN 90 AND 120
 AND electric_car_capacity BETWEEN 0 AND car_capacity AND electric_motorbike_capacity BETWEEN 0 AND motorbike_capacity);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_price_category ON pricing_rules(parking_lot_id,vehicle_type,energy_type) WHERE is_active=TRUE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_charging_port ON parking_spots(charging_station_code,charging_port_code) WHERE charging_station_code IS NOT NULL;

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
