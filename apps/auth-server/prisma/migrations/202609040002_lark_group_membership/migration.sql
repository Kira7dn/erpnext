ALTER TABLE "external_identity"
ADD COLUMN "subject_type" VARCHAR(32),
ADD COLUMN "group_ids" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
ADD COLUMN "groups_synced_at" TIMESTAMPTZ(3);
