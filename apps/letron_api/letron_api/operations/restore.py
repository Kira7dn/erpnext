"""
Production S3 Restore & Disaster Recovery Module for Letron ERP.
Handles:
- Listing available backup sets on AWS S3
- Downloading backup artifacts (database, site_config, files, private_files, manifest)
- Validating SHA-256 checksums against manifest.json
- Preparing local files for Frappe bench restore
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError


def get_aws_client():
    """Create S3 client using environment variables."""
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")
    bucket = os.environ.get("S3_BUCKET_NAME", "letron-erp-backups")

    if not access_key or not secret_key:
        raise ValueError("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be configured.")

    client = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    return client, bucket


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a local file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def list_s3_backups(prefix: str = "backups") -> List[Dict]:
    """
    List all available backup sets on S3.
    Returns list of dicts sorted by timestamp descending.
    """
    s3, bucket = get_aws_client()
    paginator = s3.get_paginator("list_objects_v2")

    backup_objects: Dict[str, List[Dict]] = {}
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Expected pattern: backups/YYYY-MM-DD/YYYYMMDD_HHMMSS/filename
            parts = key.split("/")
            if len(parts) >= 4 and len(parts[2]) == 15 and "_" in parts[2]:
                ts = parts[2]
                backup_objects.setdefault(ts, []).append({
                    "key": key,
                    "filename": parts[-1],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })

    result = []
    for ts in sorted(backup_objects.keys(), reverse=True):
        files = backup_objects[ts]
        total_size = sum(f["size"] for f in files)
        date_str = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
        result.append({
            "timestamp": ts,
            "date": date_str,
            "total_size": total_size,
            "file_count": len(files),
            "files": files,
        })
    return result


def download_backup_set(
    timestamp: str,
    dest_dir: Path,
    prefix: str = "backups",
    verify_checksum: bool = True,
) -> Dict[str, Path]:
    """
    Download all artifacts for a specific timestamp from S3 into dest_dir.
    Verifies SHA-256 against manifest.json if verify_checksum is True.
    Returns dict mapping role -> local file Path.
    """
    s3, bucket = get_aws_client()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Locate files on S3
    date_folder = f"{timestamp[0:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
    s3_prefix = f"{prefix}/{date_folder}/{timestamp}/"

    res = s3.list_objects_v2(Bucket=bucket, Prefix=s3_prefix)
    contents = res.get("Contents", [])
    if not contents:
        # Fallback: search all backups
        all_backups = list_s3_backups(prefix=prefix)
        matched = [b for b in all_backups if b["timestamp"] == timestamp]
        if not matched:
            raise FileNotFoundError(f"Backup timestamp [{timestamp}] not found on S3.")
        contents = matched[0]["files"]

    print(f"Downloading backup [{timestamp}] from s3://{bucket}/{s3_prefix}...")
    downloaded_files: Dict[str, Path] = {}
    manifest_path: Optional[Path] = None

    for obj in contents:
        key = obj.get("Key") or obj.get("key")
        filename = Path(key).name
        target_path = dest_dir / filename
        print(f" - Downloading {filename}...", end=" ", flush=True)
        s3.download_file(bucket, key, str(target_path))
        print("Done [OK]")

        if "manifest.json" in filename:
            manifest_path = target_path
        elif "database.sql.gz" in filename:
            downloaded_files["database"] = target_path
        elif "site_config_backup.json" in filename:
            downloaded_files["site_config"] = target_path
        elif "private-files.tgz" in filename:
            downloaded_files["private_files"] = target_path
        elif "files.tgz" in filename:
            downloaded_files["public_files"] = target_path

    # Verify checksums if manifest exists
    if verify_checksum and manifest_path and manifest_path.exists():
        print("Verifying SHA-256 checksums against manifest.json...")
        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest_data = json.load(mf)
        mf_files = manifest_data.get("files", {})

        for role, local_path in downloaded_files.items():
            if role in mf_files:
                expected_hash = mf_files[role].get("sha256")
                actual_hash = calculate_sha256(local_path)
                if expected_hash and actual_hash != expected_hash:
                    raise ValueError(
                        f"Checksum mismatch for {local_path.name}! (Expected: {expected_hash}, Got: {actual_hash})"
                    )
                print(f"   ✓ Checksum OK: {local_path.name}")

    return downloaded_files


def download_latest_backup(
    dest_dir: Path,
    prefix: str = "backups",
    verify_checksum: bool = True,
) -> Dict[str, Path]:
    """Download the most recent backup set from S3."""
    all_backups = list_s3_backups(prefix=prefix)
    if not all_backups:
        raise FileNotFoundError("No backups found in S3 bucket.")
    latest_ts = all_backups[0]["timestamp"]
    print(f"Latest backup identified: [{latest_ts}] ({all_backups[0]['date']})")
    return download_backup_set(
        timestamp=latest_ts,
        dest_dir=dest_dir,
        prefix=prefix,
        verify_checksum=verify_checksum,
    )
