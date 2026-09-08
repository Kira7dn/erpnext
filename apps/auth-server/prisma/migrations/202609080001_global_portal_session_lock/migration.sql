-- Serialize stale Lark membership refreshes across Auth Server instances.
ALTER TABLE external_identity
    ADD COLUMN IF NOT EXISTS sync_lease_until TIMESTAMPTZ(3);

CREATE INDEX IF NOT EXISTS external_identity_sync_lease_idx
    ON external_identity (sync_lease_until);
