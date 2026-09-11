"""
Production S3 Backup Module for Letron ERP.
Can be invoked manually or scheduled via Frappe Scheduler at 01:00 AM daily.
- Takes consistent backup of Database, Site Config, Public & Private Files
- Calculates SHA-256 checksums and creates manifest.json
- Uploads to AWS S3 bucket (letron-erp-backups) via least-privilege bot credentials
- Verifies remote object integrity (ContentLength) on S3
- Purges local files immediately to maintain Zero Local Disk Waste
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import boto3
import frappe
from botocore.exceptions import ClientError
from frappe.utils.backups import new_backup


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a local file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def format_size(size_bytes: int | float) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def get_aws_config() -> Dict[str, str]:
    """Retrieve AWS credentials from environment or frappe.conf."""
    access_key = os.environ.get("AWS_ACCESS_KEY_ID") or frappe.conf.get("aws_access_key_id")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY") or frappe.conf.get("aws_secret_access_key")
    region = (
        os.environ.get("AWS_DEFAULT_REGION")
        or frappe.conf.get("aws_default_region")
        or "ap-southeast-1"
    )
    bucket = (
        os.environ.get("S3_BUCKET_NAME")
        or frappe.conf.get("s3_bucket_name")
        or "letron-erp-backups"
    )

    return {
        "access_key": access_key or "",
        "secret_key": secret_key or "",
        "region": region,
        "bucket": bucket,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def scheduled_s3_backup() -> Dict[str, object]:
    """
    Main entry point for Frappe Scheduler (01:00 AM daily cron) or bench execute / API.
    """
    sync_secret = os.environ.get("LETRON_INTERNAL_API_SECRET")
    req_secret = frappe.get_request_header("X-Letron-Sync-Secret")
    if sync_secret and req_secret != sync_secret and getattr(frappe.session, "user", "Guest") == "Guest":
        frappe.throw("Unauthorized access to backup API", frappe.PermissionError)

    logger = frappe.logger("letron_backup")
    site_name = frappe.local.site or "frontend"
    logger.info(f"Starting scheduled S3 backup for site: {site_name}")
    print(f"=== Starting Scheduled S3 Backup for [{site_name}] ===")

    cfg = get_aws_config()
    if not cfg["access_key"] or not cfg["secret_key"]:
        err_msg = "AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not configured. Aborting backup."
        logger.error(err_msg)
        print(f"[ERROR] {err_msg}")
        return {"ok": False, "error": err_msg}

    # Step 1: Run native Frappe backup
    print("▶ 1. Creating consistent ERP backup (DB + Files + Config)...")
    try:
        backup_gen = new_backup(ignore_files=False, compress=True, force=True)
    except Exception as e:
        err_msg = f"Failed to generate Frappe backup: {e}"
        logger.error(err_msg)
        print(f"[ERROR] {err_msg}")
        return {"ok": False, "error": err_msg}

    sites_dir = Path(frappe.get_site_path()).parent

    raw_files = {
        "database": backup_gen.backup_path_db,
        "site_config": backup_gen.backup_path_conf,
        "public_files": backup_gen.backup_path_files,
        "private_files": backup_gen.backup_path_private_files,
    }

    # Resolve absolute paths and extract timestamp
    file_map: Dict[str, Path] = {}
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for role, rel_path in raw_files.items():
        if not rel_path:
            continue
        p = sites_dir / rel_path if not os.path.isabs(rel_path) else Path(rel_path)
        if p.exists():
            file_map[role] = p
            # Try to extract timestamp from database filename if available
            if role == "database" and "-" in p.name:
                parts = p.name.split("-", 1)
                if len(parts[0]) == 15 and "_" in parts[0]:
                    timestamp = parts[0]

    date_folder = f"{timestamp[0:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
    print(f"   Backup set timestamp: [{timestamp}] ({len(file_map)} files found)")

    # Step 2: Compute SHA-256 and generate manifest
    print("▶ 2. Generating SHA-256 checksums and manifest.json...")
    manifest_files = {}
    for role, file_path in file_map.items():
        size = file_path.stat().st_size
        sha256 = calculate_sha256(file_path)
        manifest_files[role] = {
            "filename": file_path.name,
            "size_bytes": size,
            "size_human": format_size(size),
            "sha256": sha256,
        }
        print(f"   - [{role:<13}] {file_path.name:<45} ({format_size(size):<8}) SHA256: {sha256[:12]}...")

    manifest_data = {
        "site": site_name,
        "timestamp": timestamp,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(manifest_files),
        "files": manifest_files,
    }

    manifest_path = file_map["database"].parent / f"{timestamp}-{site_name}-manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest_data, mf, indent=2, ensure_ascii=False)

    upload_targets = list(file_map.values()) + [manifest_path]

    # Step 3: Upload to S3
    bucket = cfg["bucket"]
    s3_dir_key = f"backups/{date_folder}/{timestamp}"
    print(f"▶ 3. Uploading to AWS S3: s3://{bucket}/{s3_dir_key}/")

    s3_client = boto3.client(
        "s3",
        region_name=cfg["region"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
    )

    uploaded_keys: List[Tuple[str, int]] = []
    try:
        for local_file in upload_targets:
            s3_key = f"{s3_dir_key}/{local_file.name}"
            size = local_file.stat().st_size
            print(f"   ^ Uploading {local_file.name} ({format_size(size)})...", end=" ", flush=True)
            s3_client.upload_file(
                str(local_file),
                bucket,
                s3_key,
                ExtraArgs={"Metadata": {"backup_timestamp": timestamp, "site": site_name}},
            )
            print("[OK]")
            uploaded_keys.append((s3_key, size))

        # Step 4: Verify upload integrity via HeadObject
        print("▶ 4. Verifying remote object integrity on S3...")
        for s3_key, expected_size in uploaded_keys:
            head = s3_client.head_object(Bucket=bucket, Key=s3_key)
            remote_size = head.get("ContentLength", 0)
            if remote_size != expected_size:
                raise ValueError(f"Size mismatch for {s3_key}: {remote_size} != {expected_size}")
            print(f"   * {s3_key.split('/')[-1]:<45} -> Verified ({format_size(remote_size)})")

        print("   [SUCCESS] All backup files safely stored and verified on AWS S3!")

        # Step 5: Purge local files (Zero Local Disk Waste)
        print("▶ 5. Purging local storage (Zero Local Disk Waste)...")
        for local_file in upload_targets:
            try:
                if local_file.exists():
                    local_file.unlink()
                    print(f"   - Removed local file: {local_file.name}")
            except Exception as ex:
                print(f"   [WARN] Could not remove {local_file.name}: {ex}")

        print("   [CLEAN] 100% local disk storage freed!")
        logger.info(f"S3 backup completed successfully for [{site_name}] at {s3_dir_key}")
        return {"ok": True, "timestamp": timestamp, "s3_path": f"s3://{bucket}/{s3_dir_key}/"}

    except Exception as e:
        err_msg = f"S3 backup upload failed: {e}"
        logger.error(err_msg)
        print(f"[ERROR] {err_msg}")
        return {"ok": False, "error": err_msg}
