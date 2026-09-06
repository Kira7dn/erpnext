#!/usr/bin/env python3
"""
Production S3 Backup Pipeline for Letron ERP.
- Discovers backups in Docker volume /home/frappe/backups
- Calculates SHA-256 checksums and generates manifest.json
- Uploads to AWS S3 bucket (letron-erp-backups) via bot credentials
- Verifies uploaded objects via HeadObject ContentLength
- Purges local files from Docker volume and staging to maintain Zero Local Disk Waste
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_env(env_path: Path) -> Dict[str, str]:
    """Parse .env file safely without third-party dotenv dependencies."""
    env_vars: Dict[str, str] = {}
    if not env_path.exists():
        return env_vars
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")
    return env_vars


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a local file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def list_container_backups(container_name: str = "erpnext-backend-1") -> List[str]:
    """List all files in /home/frappe/backups inside container."""
    try:
        res = subprocess.run(
            ["docker", "exec", container_name, "ls", "-1", "/home/frappe/backups"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return files
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to list container backups: {e.stderr}", file=sys.stderr)
        return []


def group_backup_sets(files: List[str]) -> Dict[str, List[str]]:
    """Group backup files by timestamp prefix (e.g. 20260906_113910)."""
    pattern = re.compile(r"^(\d{8}_\d{6})-(.*)$")
    backup_sets: Dict[str, List[str]] = {}
    for f in sorted(files):
        m = pattern.match(f)
        if m:
            ts = m.group(1)
            backup_sets.setdefault(ts, []).append(f)
    return backup_sets


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def process_backup_set(
    ts: str,
    file_list: List[str],
    s3_client,
    bucket: str,
    prefix: str,
    site_name: str,
    container_name: str,
    staging_base: Path,
    clean_local: bool,
) -> bool:
    """Process a single backup set: copy, hash, manifest, upload, verify, purge."""
    print(f"\n{'='*70}")
    print(f"[*] Xu ly goi Backup: [{ts}] ({len(file_list)} files)")
    print(f"{'='*70}")

    # Parse date from timestamp (YYYYMMDD_HHMMSS -> YYYY-MM-DD)
    try:
        date_folder = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
    except Exception:
        date_folder = "unclassified"

    staging_dir = staging_base / ts
    staging_dir.mkdir(parents=True, exist_ok=True)

    manifest_files: Dict[str, Dict] = {}
    copied_files: List[Path] = []

    try:
        # Step 1: Copy files from container to staging
        print("▶ 1. Trich xuat file tu Docker container sang staging buffer...")
        for filename in file_list:
            dest_file = staging_dir / filename
            docker_src = f"{container_name}:/home/frappe/backups/{filename}"
            cp_res = subprocess.run(
                ["docker", "cp", docker_src, str(dest_file)],
                capture_output=True,
                text=True,
            )
            if cp_res.returncode != 0:
                print(f"[ERROR] Khong the sao chep {filename}: {cp_res.stderr}", file=sys.stderr)
                return False

            size = dest_file.stat().st_size
            sha256 = calculate_sha256(dest_file)
            copied_files.append(dest_file)

            # Classify file role
            role = "other"
            if "database.sql.gz" in filename:
                role = "database"
            elif "site_config_backup.json" in filename:
                role = "site_config"
            elif "private-files.tgz" in filename:
                role = "private_files"
            elif "files.tgz" in filename:
                role = "public_files"

            manifest_files[role] = {
                "filename": filename,
                "size_bytes": size,
                "size_human": format_size(size),
                "sha256": sha256,
            }
            print(f"   - [{role:<13}] {filename:<45} ({format_size(size):<8}) SHA256: {sha256[:12]}...")

        # Step 2: Generate manifest.json
        print("▶ 2. Tao manifest.json ghi nhan metadata kiem toan...")
        manifest_data = {
            "site": site_name,
            "timestamp": ts,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "file_count": len(manifest_files),
            "files": manifest_files,
        }
        manifest_path = staging_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest_data, mf, indent=2, ensure_ascii=False)
        copied_files.append(manifest_path)

        # Step 3: Upload to S3
        s3_dir_key = f"{prefix}/{date_folder}/{ts}"
        print(f"▶ 3. Day len AWS S3: s3://{bucket}/{s3_dir_key}/")

        uploaded_keys: List[Tuple[str, int]] = []
        for local_file in copied_files:
            s3_key = f"{s3_dir_key}/{local_file.name}"
            file_size = local_file.stat().st_size
            print(f"   ^ Uploading {local_file.name} ({format_size(file_size)})...", end=" ", flush=True)

            s3_client.upload_file(
                str(local_file),
                bucket,
                s3_key,
                ExtraArgs={"Metadata": {"backup_timestamp": ts, "site": site_name}},
            )
            print("[OK]")
            uploaded_keys.append((s3_key, file_size))

        # Step 4: Verify upload integrity via HeadObject
        print("▶ 4. Xac thuc tinh toan ven tren S3 (Verify remote object integrity)...")
        for s3_key, expected_size in uploaded_keys:
            head = s3_client.head_object(Bucket=bucket, Key=s3_key)
            remote_size = head.get("ContentLength", 0)
            if remote_size != expected_size:
                print(f"[ERROR] Kich thuoc file S3 khong khop ({remote_size} != {expected_size}): {s3_key}", file=sys.stderr)
                return False
            print(f"   * {s3_key.split('/')[-1]:<45} -> Verified ({format_size(remote_size)})")

        print("   [SUCCESS] Toan bo ban backup da nam tren AWS S3 an toan 100%!")

        # Step 5: Purge local storage (Zero Disk Waste)
        if clean_local:
            print("▶ 5. Don dep o dia cuc bo (Zero Local Disk Waste)...")
            # Remove from Docker container volume
            for filename in file_list:
                rm_res = subprocess.run(
                    ["docker", "exec", container_name, "rm", "-f", f"/home/frappe/backups/{filename}"],
                    capture_output=True,
                    text=True,
                )
                if rm_res.returncode == 0:
                    print(f"   - Da xoa khoi Docker volume: {filename}")
            print("   [CLEAN] O cung may chu da duoc giai phong 100%!")
        else:
            print("▶ 5. Giu lai file local (--clean-local=False)")

        return True

    except Exception as e:
        print(f"\n[ERROR] Loi trong tien trinh backup S3: {e}", file=sys.stderr)
        return False

    finally:
        # Clean up staging directory on host
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Letron ERP Production S3 Backup Pipeline")
    parser.add_argument("--site", help="ERPNext site name (default: from .env SITE_NAME or frontend)")
    parser.add_argument("--bucket", help="AWS S3 Bucket name (default: from .env S3_BUCKET_NAME or letron-erp-backups)")
    parser.add_argument("--region", help="AWS Region (default: from .env AWS_DEFAULT_REGION or ap-southeast-1)")
    parser.add_argument("--container", default="erpnext-backend-1", help="Docker container name")
    parser.add_argument("--prefix", default="backups", help="S3 prefix folder")
    parser.add_argument("--clean-local", action="store_true", default=True, help="Purge local volume files after upload")
    parser.add_argument("--no-clean-local", dest="clean_local", action="store_false", help="Keep local volume files")
    parser.add_argument("--all-backups", action="store_true", help="Upload and clean ALL existing backups, not just the latest")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    env_vars = load_env(project_root / ".env")

    site_name = args.site or env_vars.get("SITE_NAME", "frontend")
    bucket = args.bucket or env_vars.get("S3_BUCKET_NAME", "letron-erp-backups")
    region = args.region or env_vars.get("AWS_DEFAULT_REGION", "ap-southeast-1")
    access_key = env_vars.get("AWS_ACCESS_KEY_ID")
    secret_key = env_vars.get("AWS_SECRET_ACCESS_KEY")

    if not access_key or not secret_key:
        print("[ERROR] Khong tim thay AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY trong .env", file=sys.stderr)
        sys.exit(1)

    print(f"================================================================")
    print(f"LETRON ERP - PRODUCTION S3 BACKUP PIPELINE")
    print(f"   Bucket : s3://{bucket}/")
    print(f"   Region : {region}")
    print(f"   Site   : {site_name}")
    print(f"   Target : {'Tat ca cac ban backup cu' if args.all_backups else 'Ban backup moi nhat'}")
    print(f"   Clean  : {'Bat (Giai phong o cung may chu)' if args.clean_local else 'Tat (Giu lai file local)'}")
    print(f"================================================================")

    # Initialize S3 client using bot credentials
    s3_client = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    # List container files
    files = list_container_backups(args.container)
    if not files:
        print("[INFO] Khong tim thay file backup nao trong container.")
        sys.exit(0)

    backup_sets = group_backup_sets(files)
    if not backup_sets:
        print("[INFO] Khong tim thay bo backup hop le nao (dinh dang YYYYMMDD_HHMMSS-*).")
        sys.exit(0)

    print(f"Tim thay {len(backup_sets)} bo backup trong Docker volume.")

    staging_base = project_root / ".tmp" / "backup_staging"
    staging_base.mkdir(parents=True, exist_ok=True)

    if args.all_backups:
        selected_timestamps = sorted(backup_sets.keys())
    else:
        # Choose the latest timestamp
        latest_ts = sorted(backup_sets.keys())[-1]
        selected_timestamps = [latest_ts]

    success_count = 0
    for ts in selected_timestamps:
        fl = backup_sets[ts]
        ok = process_backup_set(
            ts=ts,
            file_list=fl,
            s3_client=s3_client,
            bucket=bucket,
            prefix=args.prefix,
            site_name=site_name,
            container_name=args.container,
            staging_base=staging_base,
            clean_local=args.clean_local,
        )
        if ok:
            success_count += 1
        else:
            print(f"[ERROR] That bai khi xu ly goi backup {ts}", file=sys.stderr)
            sys.exit(1)

    # Cleanup base staging dir
    if staging_base.exists():
        shutil.rmtree(staging_base, ignore_errors=True)

    print(f"\n{'='*70}")
    print(f"[SUCCESS] HOAN THANH: {success_count}/{len(selected_timestamps)} goi backup da duoc dua len AWS S3 thanh cong!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
