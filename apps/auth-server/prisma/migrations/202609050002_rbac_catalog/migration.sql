CREATE TABLE "lark_group_catalog" (
    "id" VARCHAR(128) NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "member_count" INTEGER NOT NULL DEFAULT 0,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "synced_at" TIMESTAMPTZ(3) NOT NULL,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "lark_group_catalog_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "lark_group_catalog_active_idx" ON "lark_group_catalog"("active");

CREATE TABLE "erp_role_catalog" (
    "name" VARCHAR(140) NOT NULL,
    "managed" BOOLEAN NOT NULL DEFAULT false,
    "protected" BOOLEAN NOT NULL DEFAULT false,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "synced_at" TIMESTAMPTZ(3) NOT NULL,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "erp_role_catalog_pkey" PRIMARY KEY ("name")
);
CREATE INDEX "erp_role_catalog_managed_protected_active_idx" ON "erp_role_catalog"("managed", "protected", "active");

CREATE TABLE "erp_resource_catalog" (
    "key" VARCHAR(180) NOT NULL,
    "module" VARCHAR(80) NOT NULL,
    "resource" VARCHAR(120) NOT NULL,
    "label" VARCHAR(255) NOT NULL,
    "doctype" VARCHAR(140) NOT NULL,
    "operations" JSONB NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "synced_at" TIMESTAMPTZ(3) NOT NULL,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "erp_resource_catalog_pkey" PRIMARY KEY ("key")
);
CREATE INDEX "erp_resource_catalog_module_active_idx" ON "erp_resource_catalog"("module", "active");

CREATE TABLE "global_role" (
    "id" UUID NOT NULL,
    "slug" VARCHAR(120) NOT NULL,
    "name" VARCHAR(200) NOT NULL,
    "description" TEXT,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "created_by" UUID NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,
    CONSTRAINT "global_role_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "global_role_slug_key" ON "global_role"("slug");
CREATE INDEX "global_role_active_idx" ON "global_role"("active");

CREATE TABLE "global_role_group" (
    "role_id" UUID NOT NULL,
    "group_id" VARCHAR(128) NOT NULL,
    CONSTRAINT "global_role_group_pkey" PRIMARY KEY ("role_id", "group_id"),
    CONSTRAINT "global_role_group_role_id_fkey" FOREIGN KEY ("role_id") REFERENCES "global_role"("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "global_role_group_group_id_fkey" FOREIGN KEY ("group_id") REFERENCES "lark_group_catalog"("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE "global_role_erp_role" (
    "role_id" UUID NOT NULL,
    "erp_role" VARCHAR(140) NOT NULL,
    CONSTRAINT "global_role_erp_role_pkey" PRIMARY KEY ("role_id", "erp_role"),
    CONSTRAINT "global_role_erp_role_role_id_fkey" FOREIGN KEY ("role_id") REFERENCES "global_role"("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "global_role_erp_role_erp_role_fkey" FOREIGN KEY ("erp_role") REFERENCES "erp_role_catalog"("name") ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE "global_role_permission" (
    "id" UUID NOT NULL,
    "role_id" UUID NOT NULL,
    "resource" VARCHAR(180) NOT NULL,
    "actions" JSONB NOT NULL,
    "scope" JSONB,
    CONSTRAINT "global_role_permission_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "global_role_permission_role_id_fkey" FOREIGN KEY ("role_id") REFERENCES "global_role"("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "global_role_permission_resource_fkey" FOREIGN KEY ("resource") REFERENCES "erp_resource_catalog"("key") ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE UNIQUE INDEX "global_role_permission_role_id_resource_key" ON "global_role_permission"("role_id", "resource");
CREATE INDEX "global_role_permission_resource_idx" ON "global_role_permission"("resource");
