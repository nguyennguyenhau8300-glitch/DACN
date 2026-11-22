-- Allow the smaller lot requested on 2026-10-29. Existing lots retain their data.
ALTER TABLE parking_lots DROP CONSTRAINT IF EXISTS lot_capacity_check;
ALTER TABLE parking_lots ADD CONSTRAINT lot_capacity_check CHECK (
 car_capacity BETWEEN 1 AND 50 AND motorbike_capacity BETWEEN 1 AND 120
 AND electric_car_capacity BETWEEN 0 AND car_capacity
 AND electric_motorbike_capacity BETWEEN 0 AND motorbike_capacity);
ALTER TABLE parking_lots ALTER COLUMN car_capacity SET DEFAULT 30;
ALTER TABLE parking_lots ALTER COLUMN motorbike_capacity SET DEFAULT 65;
ALTER TABLE parking_lots ALTER COLUMN electric_car_capacity SET DEFAULT 10;
ALTER TABLE parking_lots ALTER COLUMN electric_motorbike_capacity SET DEFAULT 25;
