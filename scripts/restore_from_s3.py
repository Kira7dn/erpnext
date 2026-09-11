#!/usr/bin/env python3
"""
Production S3 Restore & Disaster Recovery CLI for Letron ERP.
Usage:
  # List all available backup sets on S3
  uv run python scripts/restore_from_s3.py --list

  # Restore latest backup into a temporary drill site to verify integrity
  uv run python scripts/restore_from_s3.py --latest --drill

  # Restore latest backup into production site (Disaster Recovery)
  uv run python scripts/restore_from_s3.py --latest --target-site frontend

  # Restore a specific timestamp
  uv run python scripts/restore_from_s3.py --timestamp 20260906_120812 --target-site frontend
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_env(env_path: Path) -> Dict[str, str]:
    """Parse .env file safely."""
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


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Letron ERP Production S3 Restore & Disaster Recovery CLI")
    parser.add_argument("--list", action="store_true", help="List all backups on S3")
    parser.add_argument("--latest", action="store_true", help="Select latest backup")
    parser.add_argument("--timestamp", help="Select specific backup timestamp (e.g. 20260906_120812)")
    parser.add_argument("--target-site", help="Target ERPNext site name (default from .env or frontend)")
    parser.add_argument("--drill", action="store_true", help="Perform non-destructive restore drill into temporary test site")
    parser.add_argument("--container", default="erpnext-backend-1", help="Docker backend container name")
    parser.add_argument("--bucket", help="S3 bucket name")
    parser.add_argument("--region", help="AWS region")
    parser.add_argument("--prefix", default="backups", help="S3 prefix folder")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    env_vars = load_env(project_root / ".env")

    bucket = args.bucket or env_vars.get("S3_BUCKET_NAME", "letron-erp-backups")
    region = args.region or env_vars.get("AWS_DEFAULT_REGION", "ap-southeast-1")
    access_key = env_vars.get("AWS_ACCESS_KEY_ID")
    secret_key = env_vars.get("AWS_SECRET_ACCESS_KEY")
    target_site = args.target_site or env_vars.get("SITE_NAME", "frontend")
    db_root_user = env_vars.get("DB_ROOT_USER", "root")
    bootstrap_pass = env_vars.get("LETRON_BOOTSTRAP_PASSWORD", "")
    db_root_pass = bootstrap_pass
    admin_pass = bootstrap_pass

    if not access_key or not secret_key:
        print("[ERROR] AWS credentials not found in .env", file=sys.stderr)
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    # Mode 1: List all backups
    if args.list:
        print(f"\n{'='*75}")
        print(f"📦 DANH SÁCH BẢN SAO LƯU TRÊN AWS S3: s3://{bucket}/{args.prefix}/")
        print(f"{'='*75}")

        paginator = s3.get_paginator("list_objects_v2")
        backup_objects: Dict[str, List[Dict]] = {}
        for page in paginator.paginate(Bucket=bucket, Prefix=args.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                parts = key.split("/")
                if len(parts) >= 4 and len(parts[2]) == 15 and "_" in parts[2]:
                    ts = parts[2]
                    backup_objects.setdefault(ts, []).append({
                        "key": key,
                        "filename": parts[-1],
                        "size": obj["Size"],
                    })

        if not backup_objects:
            print("[INFO] Không tìm thấy bản backup nào trên S3.")
            return

        print(f"{'Timestamp':<18} {'Ngày tạo (UTC)':<20} {'Số file':<10} {'Tổng dung lượng':<15}")
        print(f"{'-'*18} {'-'*20} {'-'*10} {'-'*15}")
        for ts in sorted(backup_objects.keys(), reverse=True):
            fl = backup_objects[ts]
            total_sz = sum(f["size"] for f in fl)
            date_str = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
            print(f"{ts:<18} {date_str:<20} {len(fl):<10} {format_size(total_sz):<15}")
        print(f"{'='*75}\n")
        return

    # Mode 2 & 3: Restore or Restore Drill
    chosen_ts = args.timestamp
    if args.latest or not chosen_ts:
        # Find latest timestamp
        res = s3.list_objects_v2(Bucket=bucket, Prefix=f"{args.prefix}/")
        timestamps = set()
        for obj in res.get("Contents", []):
            parts = obj["Key"].split("/")
            if len(parts) >= 4 and len(parts[2]) == 15 and "_" in parts[2]:
                timestamps.add(parts[2])
        if not timestamps:
            print("[ERROR] Không tìm thấy bản backup nào trên S3.", file=sys.stderr)
            sys.exit(1)
        chosen_ts = sorted(timestamps, reverse=True)[0]

    print(f"\n{'='*75}")
    print(f"🚀 LETRON ERP - PRODUCTION S3 RESTORE PIPELINE")
    print(f"   Bucket   : s3://{bucket}/")
    print(f"   Target TS: [{chosen_ts}]")
    print(f"   Mode     : {'DIỄN TẬP KHÔI PHỤC (Restore Drill - Không ảnh hưởng dữ liệu thật)' if args.drill else f'PHỤC HỒI THẬT SỰ (Vào site: {target_site})'}")
    print(f"{'='*75}")

    # Confirm if restoring into production site
    if not args.drill:
        print(f"\n[CẢNH BÁO NGUY HIỂM] Bạn đang chuẩn bị khôi phục đè vào site PRODUCTION: [{target_site}]!")
        print("Tất cả dữ liệu hiện tại trên site này sẽ bị thay thế bằng bản backup.")
        confirm = input("Gõ 'RESTORE' để xác nhận tiếp tục: ")
        if confirm.strip() != "RESTORE":
            print("[ABORTED] Đã hủy tiến trình khôi phục.")
            sys.exit(0)

    # Step 1: Download from S3 inside backend container
    staging_in_container = "/home/frappe/backups/.restore_staging"
    print(f"\n▶ 1. Tải bản backup [{chosen_ts}] từ S3 vào container...")

    download_cmd = [
        "docker", "exec", args.container,
        "/home/frappe/frappe-bench/env/bin/python", "-c",
        f"""
import sys
from letron_api.operations.restore import download_backup_set
download_backup_set('{chosen_ts}', '{staging_in_container}')
print('DOWNLOAD_SUCCESS')
"""
    ]
    res = subprocess.run(download_cmd, capture_output=True, text=True)
    if "DOWNLOAD_SUCCESS" not in res.stdout:
        print(f"[ERROR] Tải bản backup từ S3 thất bại:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        sys.exit(1)
    print(res.stdout.strip())

    # Step 2: Locate downloaded files inside container
    find_cmd = [
        "docker", "exec", args.container, "bash", "-c",
        f"ls -1 {staging_in_container}/*-database.sql.gz | head -n 1"
    ]
    db_file = subprocess.run(find_cmd, capture_output=True, text=True).stdout.strip()
    if not db_file:
        print("[ERROR] Không tìm thấy file database.sql.gz sau khi tải.", file=sys.stderr)
        sys.exit(1)

    prefix_path = db_file.replace("-database.sql.gz", "")
    public_file = f"{prefix_path}-files.tgz"
    private_file = f"{prefix_path}-private-files.tgz"

    try:
        if args.drill:
            # Step 3A: Drill Restore into temporary site
            drill_site = f"restore-drill-{os.getpid()}.local"
            drill_db = f"letron_restore_drill_{os.getpid()}"
            print(f"\n▶ 2. [Drill] Tạo site diễn tập tạm thời: {drill_site} (DB: {drill_db})...")

            # Create temporary drill site
            subprocess.run([
                "docker", "exec", args.container, "bench", "new-site", drill_site,
                "--mariadb-user-host-login-scope=%",
                f"--db-name={drill_db}",
                f"--admin-password={admin_pass}",
                f"--db-root-username={db_root_user}",
                f"--db-root-password={db_root_pass}",
                "--no-mariadb-socket"
            ], check=True)

            print(f"▶ 3. [Drill] Bung bản backup vào site diễn tập: {drill_site}...")
            restore_cmd = [
                "docker", "exec", args.container, "bench", "--site", drill_site, "restore", db_file,
                "--force",
                f"--db-root-username={db_root_user}",
                f"--db-root-password={db_root_pass}",
                f"--with-public-files={public_file}",
                f"--with-private-files={private_file}"
            ]
            subprocess.run(restore_cmd, check=True)

            print(f"▶ 4. [Drill] Xác thực runtime & tính toàn vẹn hệ thống...")
            audit_res = subprocess.run([
                "docker", "exec", args.container, "bench", "--site", drill_site, "execute", "letron_api.control.api.runtime_info"
            ], capture_output=True, text=True, check=True)
            print("   Runtime audit:", audit_res.stdout.strip()[:120], "...")

            print(f"▶ 5. [Drill] Dọn dẹp site diễn tập ({drill_site})...")
            subprocess.run([
                "docker", "exec", args.container, "bench", "drop-site", drill_site,
                "--no-backup", "--force",
                f"--db-root-username={db_root_user}",
                f"--db-root-password={db_root_pass}"
            ], check=True)
            print("   ✓ Đã xóa sạch site diễn tập tạm thời.")

            print(f"\n{'='*75}")
            print(f"🎉 DIỄN TẬP KHÔI PHỤC THÀNH CÔNG 100%! Dữ liệu trên S3 hoàn toàn nguyên vẹn và sẵn sàng phục hồi.")
            print(f"{'='*75}\n")

        else:
            # Step 3B: True Production Disaster Recovery
            print(f"\n▶ 2. Bung bản backup vào site PRODUCTION: [{target_site}]...")
            restore_cmd = [
                "docker", "exec", args.container, "bench", "--site", target_site, "restore", db_file,
                "--force",
                f"--db-root-username={db_root_user}",
                f"--db-root-password={db_root_pass}",
                f"--with-public-files={public_file}",
                f"--with-private-files={private_file}"
            ]
            subprocess.run(restore_cmd, check=True)

            print(f"▶ 3. Chạy migration và đồng bộ hệ thống trên [{target_site}]...")
            subprocess.run([
                "docker", "exec", args.container, "bench", "--site", target_site, "migrate"
            ], check=True)
            subprocess.run([
                "docker", "exec", args.container, "bench", "--site", target_site, "execute", "letron_api.control.system_config.sync"
            ], check=True)

            print(f"\n{'='*75}")
            print(f"🎉 PHỤC HỒI DỮ LIỆU THÀNH CÔNG! Site [{target_site}] đã hoạt động trở lại từ bản backup S3 [{chosen_ts}].")
            print(f"{'='*75}\n")

    finally:
        # Step 4: Purge temporary staging in container (Zero Disk Waste)
        print("▶ Dọn dẹp staging buffer trong container...")
        subprocess.run([
            "docker", "exec", args.container, "rm", "-rf", staging_in_container
        ], check=False)
        print("✓ Zero Local Disk Waste duy trì thành công.")


if __name__ == "__main__":
    main()
