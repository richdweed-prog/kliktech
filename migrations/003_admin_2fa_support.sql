-- Recuperação de 2FA somente pelo painel administrativo de suporte.
BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_2fa_disabled_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_2fa_version BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_users_admin_2fa_disabled
  ON users(admin_2fa_disabled_at)
  WHERE is_admin = 1 AND admin_2fa_disabled_at IS NOT NULL;

COMMIT;
