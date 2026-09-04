CREATE TYPE "UserStatus" AS ENUM ('ACTIVE', 'DISABLED');

CREATE TABLE "oauth_transaction" (
    "id" BIGSERIAL NOT NULL,
    "state_hash" CHAR(64) NOT NULL,
    "browser_binding_hash" CHAR(64) NOT NULL,
    "interaction_uid" VARCHAR(255),
    "return_to" TEXT,
    "encrypted_code_verifier" TEXT NOT NULL,
    "expires_at" TIMESTAMPTZ(3) NOT NULL,
    "consumed_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "oauth_transaction_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "oauth_transaction_state_hash_key" ON "oauth_transaction"("state_hash");
CREATE INDEX "oauth_transaction_expires_at_idx" ON "oauth_transaction"("expires_at");

CREATE TABLE "auth_user" (
    "id" UUID NOT NULL,
    "email" VARCHAR(320) NOT NULL,
    "display_name" VARCHAR(200) NOT NULL,
    "avatar_url" TEXT,
    "status" "UserStatus" NOT NULL DEFAULT 'ACTIVE',
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "auth_user_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "external_identity" (
    "id" BIGSERIAL NOT NULL,
    "provider" VARCHAR(32) NOT NULL,
    "tenant_key" VARCHAR(128) NOT NULL,
    "subject" VARCHAR(256) NOT NULL,
    "user_id" UUID NOT NULL,
    "email" VARCHAR(320),
    "last_seen_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "external_identity_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "sso_session" (
    "id" BIGSERIAL NOT NULL,
    "token_hash" CHAR(64) NOT NULL,
    "user_id" UUID NOT NULL,
    "expires_at" TIMESTAMPTZ(3) NOT NULL,
    "revoked_at" TIMESTAMPTZ(3),
    "last_seen_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "sso_session_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "oidc_artifact" (
    "model" VARCHAR(64) NOT NULL,
    "id" VARCHAR(255) NOT NULL,
    "payload" JSONB NOT NULL,
    "grant_id" VARCHAR(255),
    "user_code" VARCHAR(255),
    "uid" VARCHAR(255),
    "expires_at" TIMESTAMPTZ(3),
    CONSTRAINT "oidc_artifact_pkey" PRIMARY KEY ("model", "id")
);

CREATE TABLE "oidc_client" (
    "id" BIGSERIAL NOT NULL,
    "client_id" VARCHAR(255) NOT NULL,
    "metadata" JSONB NOT NULL,
    "encrypted_client_secret" TEXT,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "oidc_client_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "audit_event" (
    "id" BIGSERIAL NOT NULL,
    "event_type" VARCHAR(64) NOT NULL,
    "outcome" VARCHAR(32) NOT NULL,
    "user_id" UUID,
    "client_id" VARCHAR(255),
    "request_id" VARCHAR(128),
    "detail" JSONB,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "audit_event_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "auth_user_email_key" ON "auth_user"("email");
CREATE UNIQUE INDEX "external_identity_provider_tenant_key_subject_key" ON "external_identity"("provider", "tenant_key", "subject");
CREATE INDEX "external_identity_user_id_idx" ON "external_identity"("user_id");
CREATE UNIQUE INDEX "sso_session_token_hash_key" ON "sso_session"("token_hash");
CREATE INDEX "sso_session_user_id_idx" ON "sso_session"("user_id");
CREATE INDEX "sso_session_expires_at_idx" ON "sso_session"("expires_at");
CREATE INDEX "sso_session_active_user_idx" ON "sso_session"("user_id", "expires_at") WHERE "revoked_at" IS NULL;
CREATE INDEX "oidc_artifact_grant_id_idx" ON "oidc_artifact"("grant_id");
CREATE INDEX "oidc_artifact_user_code_idx" ON "oidc_artifact"("user_code");
CREATE INDEX "oidc_artifact_uid_idx" ON "oidc_artifact"("uid");
CREATE INDEX "oidc_artifact_expires_at_idx" ON "oidc_artifact"("expires_at");
CREATE UNIQUE INDEX "oidc_client_client_id_key" ON "oidc_client"("client_id");
CREATE INDEX "audit_event_user_id_idx" ON "audit_event"("user_id");
CREATE INDEX "audit_event_client_id_idx" ON "audit_event"("client_id");
CREATE INDEX "audit_event_created_at_idx" ON "audit_event"("created_at");

ALTER TABLE "external_identity" ADD CONSTRAINT "external_identity_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth_user"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "sso_session" ADD CONSTRAINT "sso_session_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth_user"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "audit_event" ADD CONSTRAINT "audit_event_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth_user"("id") ON DELETE SET NULL ON UPDATE CASCADE;
