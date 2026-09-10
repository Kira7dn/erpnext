CREATE TABLE "lark_mail_delivery" (
    "id" BIGSERIAL NOT NULL,
    "idempotency_key" VARCHAR(255) NOT NULL,
    "recipient" VARCHAR(320) NOT NULL,
    "subject" VARCHAR(998) NOT NULL,
    "status" VARCHAR(32) NOT NULL,
    "provider_message_id" VARCHAR(255),
    "last_error" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    "sent_at" TIMESTAMPTZ(3),
    CONSTRAINT "lark_mail_delivery_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "lark_mail_delivery_idempotency_key_key" ON "lark_mail_delivery"("idempotency_key");
CREATE INDEX "lark_mail_delivery_status_updated_at_idx" ON "lark_mail_delivery"("status", "updated_at");
