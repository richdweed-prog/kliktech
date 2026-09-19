-- KlikTech — migração inicial PostgreSQL.

CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  balance_cents BIGINT NOT NULL DEFAULT 0 CHECK (balance_cents >= 0),
  is_admin INTEGER NOT NULL DEFAULT 0,
  public_id TEXT UNIQUE,
  profile_photo BYTEA,
  profile_photo_mime TEXT,
  blocked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wallet_charges (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  provider_id TEXT UNIQUE NOT NULL,
  external_reference TEXT UNIQUE NOT NULL,
  amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
  status TEXT NOT NULL DEFAULT 'PENDING',
  pix_copy_paste TEXT,
  expires_at TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paid_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS wallet_ledger (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT UNIQUE NOT NULL,
  user_id BIGINT NOT NULL REFERENCES users(id),
  provider_id TEXT,
  amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
  kind TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS carts (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  session_key TEXT,
  plan TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_catalog (
  id BIGSERIAL PRIMARY KEY,
  plan TEXT UNIQUE NOT NULL,
  gigas TEXT NOT NULL,
  tempo TEXT NOT NULL,
  price_cents BIGINT NOT NULL CHECK (price_cents > 0),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  featured BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory (
  id BIGSERIAL PRIMARY KEY,
  plan TEXT NOT NULL,
  model TEXT NOT NULL,
  line TEXT,
  ddd TEXT,
  photo BYTEA,
  photo_mime TEXT,
  smdp TEXT NOT NULL,
  activation_code TEXT UNIQUE NOT NULL,
  sold_at TIMESTAMPTZ,
  sold_to BIGINT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchases (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  inventory_id BIGINT NOT NULL REFERENCES inventory(id),
  plan TEXT NOT NULL,
  price_cents BIGINT NOT NULL CHECK (price_cents > 0),
  status TEXT NOT NULL DEFAULT 'approved',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT purchases_inventory_unique UNIQUE (inventory_id)
);

CREATE TABLE IF NOT EXISTS access_logs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  ip TEXT NOT NULL,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_events (
  id BIGSERIAL PRIMARY KEY,
  event TEXT NOT NULL,
  detail TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inventory_available ON inventory(plan, ddd) WHERE sold_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_charges_provider ON wallet_charges(provider_id);
