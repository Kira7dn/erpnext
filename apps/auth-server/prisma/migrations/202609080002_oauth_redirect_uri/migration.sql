ALTER TABLE "oauth_transaction" ADD COLUMN "redirect_uri" TEXT;

UPDATE "oauth_transaction"
SET "redirect_uri" = 'http://localhost:3000/api/auth/lark/callback'
WHERE "redirect_uri" IS NULL;

ALTER TABLE "oauth_transaction" ALTER COLUMN "redirect_uri" SET NOT NULL;
