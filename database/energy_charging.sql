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
