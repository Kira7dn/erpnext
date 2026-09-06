#!/usr/bin/env python3
"""
Configure S3 Lifecycle Rules for letron-erp-backups.
Implements the 10-year financial audit retention strategy according to Vietnam Accounting Law:
- 0 to 30 days: S3 Standard
- 31 to 180 days: Transition to S3 Glacier Instant Retrieval
- 181 to 3650 days (10 years): Transition to S3 Glacier Deep Archive
- After 3650 days: Expire (Delete)

Uses AWS profile: letron-master (or letron-erp if master not configured)
"""

import sys
import boto3
from botocore.exceptions import ClientError

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def configure_lifecycle(bucket_name: str = "letron-erp-backups", profile: str = "letron-master"):
    print(f"Connecting to AWS with profile [{profile}]...")
    try:
        session = boto3.Session(profile_name=profile)
        s3 = session.client("s3")
    except Exception as e:
        print(f"[ERROR] Failed to initialize session with profile {profile}: {e}")
        return False

    lifecycle_configuration = {
        "Rules": [
            {
                "ID": "Letron-ERP-10-Year-Accounting-Retention",
                "Status": "Enabled",
                "Filter": {"Prefix": "backups/"},
                "Transitions": [
                    {
                        "Days": 30,
                        "StorageClass": "GLACIER_IR",  # Glacier Instant Retrieval (sau 30 ngày)
                    },
                    {
                        "Days": 180,
                        "StorageClass": "DEEP_ARCHIVE",  # Glacier Deep Archive (sau 6 tháng)
                    },
                ],
                "Expiration": {
                    "Days": 3650,  # 10 years
                },
                "AbortIncompleteMultipartUpload": {
                    "DaysAfterInitiation": 7,
                },
            }
        ]
    }

    try:
        print(f"Applying Lifecycle Rules to bucket '{bucket_name}'...")
        s3.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=lifecycle_configuration,
        )
        print("[SUCCESS] Lifecycle configuration successfully applied!")
        print("   - 0-30 days    : S3 Standard (Phuc hoi nhanh RTO < 15 phut)")
        print("   - 31-180 days  : S3 Glacier Instant Retrieval (Tiet kiem chi phi)")
        print("   - 181-3650 days: S3 Glacier Deep Archive (Luu tru 10 nam theo Luat Ke toan)")
        print("   - >3650 days   : Het han (Expire)")
        return True
    except ClientError as e:
        print(f"[ERROR] AWS ClientError: {e}")
        return False


if __name__ == "__main__":
    bucket = sys.argv[1] if len(sys.argv) > 1 else "letron-erp-backups"
    prof = sys.argv[2] if len(sys.argv) > 2 else "letron-master"
    configure_lifecycle(bucket, prof)
