-- Global Portal is the only RBAC control plane. Remove the unused relational
-- catalog/workflow model and keep only the published JSON policy projection.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

UPDATE access_policy
SET policy = jsonb_set(
    policy,
    '{entitlements}',
    COALESCE((
        SELECT jsonb_agg(item - 'erpRole' - 'erpRoles' ORDER BY ordinal)
        FROM jsonb_array_elements(policy->'entitlements') WITH ORDINALITY AS entries(item, ordinal)
    ), '[]'::jsonb)
)
WHERE policy ? 'entitlements';

UPDATE access_policy
SET sha256 = encode(digest(policy::text, 'sha256'), 'hex');

ALTER TABLE access_policy
    DROP COLUMN IF EXISTS approved_by,
    DROP COLUMN IF EXISTS approval_reason,
    DROP COLUMN IF EXISTS approved_at;

ALTER TABLE access_policy ALTER COLUMN status DROP DEFAULT;
ALTER TYPE "AccessPolicyStatus" RENAME TO "AccessPolicyStatus_legacy";
CREATE TYPE "AccessPolicyStatus" AS ENUM ('PUBLISHED', 'SUPERSEDED');
ALTER TABLE access_policy
    ALTER COLUMN status TYPE "AccessPolicyStatus"
    USING (
        CASE WHEN status::text = 'SUPERSEDED' THEN 'SUPERSEDED' ELSE 'PUBLISHED' END
    )::"AccessPolicyStatus";
DROP TYPE "AccessPolicyStatus_legacy";
ALTER TABLE access_policy ALTER COLUMN status SET DEFAULT 'PUBLISHED';

DROP TABLE IF EXISTS global_role_permission;
DROP TABLE IF EXISTS global_role_erp_role;
DROP TABLE IF EXISTS global_role_group;
DROP TABLE IF EXISTS global_role;
DROP TABLE IF EXISTS erp_resource_catalog;
DROP TABLE IF EXISTS erp_role_catalog;
DROP TABLE IF EXISTS lark_group_catalog;
