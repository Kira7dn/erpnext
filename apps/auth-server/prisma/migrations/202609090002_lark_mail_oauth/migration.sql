CREATE TABLE "lark_mail_oauth_transaction" (
    "id" BIGSERIAL NOT NULL,
    "state_hash" CHAR(64) NOT NULL,
    "browser_binding_hash" CHAR(64) NOT NULL,
    "expires_at" TIMESTAMPTZ(3) NOT NULL,
    "consumed_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "lark_mail_oauth_transaction_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "lark_mail_oauth_transaction_state_hash_key" ON "lark_mail_oauth_transaction"("state_hash");
CREATE INDEX "lark_mail_oauth_transaction_expires_at_idx" ON "lark_mail_oauth_transaction"("expires_at");

CREATE TABLE "lark_mail_credential" (
    "id" BIGSERIAL NOT NULL,
    "mailbox_email" VARCHAR(320) NOT NULL,
    "tenant_key" VARCHAR(128) NOT NULL,
    "subject" VARCHAR(256) NOT NULL,
    "encrypted_refresh_token" TEXT NOT NULL,
    "refresh_token_expires_at" TIMESTAMPTZ(3),
    "granted_scopes" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "lark_mail_credential_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "lark_mail_credential_mailbox_email_key" ON "lark_mail_credential"("mailbox_email");
