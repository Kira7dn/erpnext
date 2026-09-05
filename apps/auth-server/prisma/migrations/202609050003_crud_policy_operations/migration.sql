-- Normalize policies created before CRUD-only capabilities were introduced.
-- PostgreSQL jsonb preserves array order; operation order is canonicalized below.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

WITH normalized AS (
    SELECT
        ap.id,
        jsonb_set(
            ap.policy,
            '{entitlements}',
            COALESCE((
                SELECT jsonb_agg(
                    jsonb_set(
                        entitlement,
                        '{rules}',
                        COALESCE((
                            SELECT jsonb_agg(
                                jsonb_set(
                                    rule,
                                    '{operations}',
                                    COALESCE((
                                        SELECT jsonb_agg(mapped.operation ORDER BY mapped.operation)
                                        FROM (
                                            SELECT DISTINCT CASE operation.value
                                                WHEN 'submit' THEN 'update'
                                                WHEN 'reconcile' THEN 'update'
                                                WHEN 'unreconcile' THEN 'update'
                                                WHEN 'cancel' THEN 'delete'
                                                ELSE operation.value
                                            END AS operation
                                            FROM jsonb_array_elements_text(rule->'operations') AS operation(value)
                                            WHERE operation.value IN (
                                                'list', 'read', 'create', 'update', 'delete',
                                                'submit', 'cancel', 'reconcile', 'unreconcile'
                                            )
                                        ) AS mapped
                                    ), '[]'::jsonb)
                                )
                            )
                            FROM jsonb_array_elements(entitlement->'rules') AS rule
                        ), '[]'::jsonb)
                    )
                )
                FROM jsonb_array_elements(ap.policy->'entitlements') AS entitlement
            ), '[]'::jsonb)
        ) AS policy
    FROM access_policy AS ap
    WHERE ap.policy ? 'entitlements'
)
UPDATE access_policy AS ap
SET
    policy = normalized.policy,
    sha256 = encode(digest(normalized.policy::text, 'sha256'), 'hex')
FROM normalized
WHERE ap.id = normalized.id;
