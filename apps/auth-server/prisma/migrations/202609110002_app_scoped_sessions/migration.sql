ALTER TABLE "oauth_transaction" ADD COLUMN IF NOT EXISTS "app_key" VARCHAR(32);
ALTER TABLE "erp_handoff" ADD COLUMN IF NOT EXISTS "app_key" VARCHAR(32) NOT NULL DEFAULT 'erp';
ALTER TABLE "erp_gateway_session" ADD COLUMN IF NOT EXISTS "app_key" VARCHAR(32) NOT NULL DEFAULT 'erp';
CREATE INDEX IF NOT EXISTS "erp_gateway_session_app_key_idx" ON "erp_gateway_session"("app_key");
