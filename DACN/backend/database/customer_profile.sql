-- Additive migration; existing accounts can complete their profile later.
ALTER TABLE users ADD COLUMN IF NOT EXISTS date_of_birth DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS hometown VARCHAR(200);
