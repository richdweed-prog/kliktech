-- Endurecimento de segurança para bancos criados antes da Fase 8.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked_at TIMESTAMPTZ;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_balance_nonnegative;
ALTER TABLE users ADD CONSTRAINT users_balance_nonnegative CHECK (balance_cents >= 0);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'purchases_inventory_unique'
      AND conrelid = 'purchases'::regclass
  ) THEN
    ALTER TABLE purchases ADD CONSTRAINT purchases_inventory_unique UNIQUE (inventory_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_inventory_available ON inventory(plan, ddd) WHERE sold_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_charges_provider ON wallet_charges(provider_id);

COMMIT;
