CREATE TYPE "AccessPolicyStatus" AS ENUM ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PUBLISHED', 'SUPERSEDED', 'ROLLED_BACK');

CREATE TABLE "access_policy" (
    "id" UUID NOT NULL,
    "version" INTEGER NOT NULL,
    "status" "AccessPolicyStatus" NOT NULL DEFAULT 'DRAFT',
    "policy" JSONB NOT NULL,
    "sha256" CHAR(64) NOT NULL,
    "created_by" UUID NOT NULL,
    "approved_by" UUID,
    "approval_reason" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "approved_at" TIMESTAMPTZ(3),
    "published_at" TIMESTAMPTZ(3),
    "superseded_at" TIMESTAMPTZ(3),
    CONSTRAINT "access_policy_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "access_policy_version_key" ON "access_policy"("version");
CREATE INDEX "access_policy_status_idx" ON "access_policy"("status");
CREATE INDEX "access_policy_created_by_idx" ON "access_policy"("created_by");
