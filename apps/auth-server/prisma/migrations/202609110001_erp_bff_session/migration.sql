CREATE TABLE "erp_handoff" (
    "id" BIGSERIAL NOT NULL,
    "code_hash" CHAR(64) NOT NULL,
    "user_id" UUID NOT NULL,
    "expires_at" TIMESTAMPTZ(3) NOT NULL,
    "consumed_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "erp_handoff_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "erp_handoff_code_hash_key" ON "erp_handoff"("code_hash");
CREATE INDEX "erp_handoff_expires_at_idx" ON "erp_handoff"("expires_at");
ALTER TABLE "erp_handoff" ADD CONSTRAINT "erp_handoff_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth_user"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "erp_gateway_session" (
    "id" BIGSERIAL NOT NULL,
    "token_hash" CHAR(64) NOT NULL,
    "user_id" UUID NOT NULL,
    "policy_version" INTEGER,
    "expires_at" TIMESTAMPTZ(3) NOT NULL,
    "revoked_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "erp_gateway_session_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "erp_gateway_session_token_hash_key" ON "erp_gateway_session"("token_hash");
CREATE INDEX "erp_gateway_session_user_id_idx" ON "erp_gateway_session"("user_id");
CREATE INDEX "erp_gateway_session_expires_at_idx" ON "erp_gateway_session"("expires_at");
ALTER TABLE "erp_gateway_session" ADD CONSTRAINT "erp_gateway_session_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth_user"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "oauth_transaction" ADD COLUMN "handoff" BOOLEAN NOT NULL DEFAULT false;
