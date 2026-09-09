CREATE TABLE "lark_po_draft_state" (
    "id" BIGSERIAL NOT NULL,
    "orchestration_id" VARCHAR(128) NOT NULL,
    "draft_id" VARCHAR(128),
    "approval_instance_code" VARCHAR(128),
    "approval_attempt" INTEGER NOT NULL DEFAULT 1,
    "snapshot_hash" CHAR(64),
    "status" VARCHAR(32) NOT NULL,
    "erp_purchase_order_name" VARCHAR(140),
    "last_error" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "lark_po_draft_state_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "lark_po_draft_state_orchestration_id_key"
    ON "lark_po_draft_state"("orchestration_id");
CREATE INDEX "lark_po_draft_state_draft_id_idx"
    ON "lark_po_draft_state"("draft_id");
CREATE INDEX "lark_po_draft_state_approval_instance_code_idx"
    ON "lark_po_draft_state"("approval_instance_code");

CREATE TABLE "lark_webhook_event" (
    "id" BIGSERIAL NOT NULL,
    "event_id" VARCHAR(255) NOT NULL,
    "event_type" VARCHAR(128),
    "instance_code" VARCHAR(128),
    "processed_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "lark_webhook_event_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "lark_webhook_event_event_id_key"
    ON "lark_webhook_event"("event_id");
CREATE INDEX "lark_webhook_event_created_at_idx"
    ON "lark_webhook_event"("created_at");
CREATE INDEX "lark_webhook_event_instance_code_idx"
    ON "lark_webhook_event"("instance_code");
