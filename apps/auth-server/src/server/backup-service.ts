import { S3Client, ListObjectsV2Command } from "@aws-sdk/client-s3";
import { getEnv } from "./env";

export interface BackupFileItem {
  key: string;
  filename: string;
  size: number;
  sizeHuman: string;
  role: "database" | "site_config" | "public_files" | "private_files" | "manifest" | "other";
}

export interface BackupSetItem {
  timestamp: string;
  dateStr: string;
  isoDate: string;
  totalSize: number;
  totalSizeHuman: string;
  fileCount: number;
  isCompliant: boolean;
  files: BackupFileItem[];
}

export interface ListBackupsOptions {
  limit?: number;
  cursor?: string;
  from?: string; // YYYY-MM-DD
  to?: string;   // YYYY-MM-DD
  search?: string;
}

export interface ListBackupsResult {
  items: BackupSetItem[];
  nextCursor?: string;
  hasMore: boolean;
  totalCount: number;
  filteredCount: number;
}

function formatSize(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

function getS3Client(): { client: S3Client; bucket: string } {
  const env = getEnv();
  const accessKeyId = env.AWS_ACCESS_KEY_ID || process.env.AWS_ACCESS_KEY_ID;
  const secretAccessKey = env.AWS_SECRET_ACCESS_KEY || process.env.AWS_SECRET_ACCESS_KEY;
  const region = env.AWS_DEFAULT_REGION || process.env.AWS_DEFAULT_REGION || "ap-southeast-1";
  const bucket = env.S3_BUCKET_NAME || process.env.S3_BUCKET_NAME || "letron-erp-backups";

  if (!accessKeyId || !secretAccessKey) {
    throw new Error("AWS S3 credentials (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY) are not configured.");
  }

  const client = new S3Client({
    region,
    credentials: {
      accessKeyId,
      secretAccessKey,
    },
  });

  return { client, bucket };
}

export async function fetchAllS3BackupSets(): Promise<BackupSetItem[]> {
  const { client, bucket } = getS3Client();

  const grouped: Record<string, BackupFileItem[]> = {};
  let continuationToken: string | undefined = undefined;

  do {
    const cmd: ListObjectsV2Command = new ListObjectsV2Command({
      Bucket: bucket,
      Prefix: "backups/",
      ContinuationToken: continuationToken,
    });

    const response = await client.send(cmd);
    for (const obj of response.Contents || []) {
      const key = obj.Key || "";
      const parts = key.split("/");
      if (parts.length >= 4 && parts[2]?.length === 15 && parts[2]?.includes("_")) {
        const ts = parts[2];
        const filename = parts[parts.length - 1] || "";
        const size = obj.Size || 0;

        let role: BackupFileItem["role"] = "other";
        if (filename.includes("database.sql.gz")) role = "database";
        else if (filename.includes("site_config_backup.json")) role = "site_config";
        else if (filename.includes("private-files.tgz")) role = "private_files";
        else if (filename.endsWith("files.tgz")) role = "public_files";
        else if (filename.includes("manifest.json")) role = "manifest";

        if (!grouped[ts]) {
          grouped[ts] = [];
        }
        grouped[ts].push({
          key,
          filename,
          size,
          sizeHuman: formatSize(size),
          role,
        });
      }
    }
    continuationToken = response.NextContinuationToken;
  } while (continuationToken);

  const sortedTimestamps = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

  const items: BackupSetItem[] = sortedTimestamps.map((ts) => {
    const files = grouped[ts] || [];
    const totalSize = files.reduce((acc, f) => acc + f.size, 0);

    const year = ts.slice(0, 4);
    const month = ts.slice(4, 6);
    const day = ts.slice(6, 8);
    const hour = ts.slice(9, 11);
    const min = ts.slice(11, 13);
    const sec = ts.slice(13, 15);

    const dateStr = `${day}/${month}/${year} ${hour}:${min}:${sec}`;
    const isoDate = `${year}-${month}-${day}T${hour}:${min}:${sec}Z`;

    const hasDb = files.some((f) => f.role === "database");
    const hasConfig = files.some((f) => f.role === "site_config");
    const hasPub = files.some((f) => f.role === "public_files");
    const hasPriv = files.some((f) => f.role === "private_files");
    const hasManifest = files.some((f) => f.role === "manifest");

    return {
      timestamp: ts,
      dateStr,
      isoDate,
      totalSize,
      totalSizeHuman: formatSize(totalSize),
      fileCount: files.length,
      isCompliant: hasDb && hasConfig && hasPub && hasPriv && hasManifest,
      files,
    };
  });

  return items;
}

export async function listPaginatedBackups(opts: ListBackupsOptions = {}): Promise<ListBackupsResult> {
  const allItems = await fetchAllS3BackupSets();
  const totalCount = allItems.length;

  // Filter by date range (YYYY-MM-DD)
  let filtered = allItems;
  if (opts.from) {
    const fromTs = opts.from.replace(/-/g, "") + "_000000";
    filtered = filtered.filter((item) => item.timestamp >= fromTs);
  }
  if (opts.to) {
    const toTs = opts.to.replace(/-/g, "") + "_235959";
    filtered = filtered.filter((item) => item.timestamp <= toTs);
  }

  // Filter by search term
  if (opts.search && opts.search.trim()) {
    const q = opts.search.trim().toLowerCase();
    filtered = filtered.filter(
      (item) => item.timestamp.toLowerCase().includes(q) || item.dateStr.toLowerCase().includes(q)
    );
  }

  const filteredCount = filtered.length;
  const limit = Math.max(1, Math.min(opts.limit || 8, 50));

  let startIndex = 0;
  if (opts.cursor) {
    const idx = filtered.findIndex((item) => item.timestamp === opts.cursor);
    if (idx !== -1) {
      startIndex = idx + 1;
    }
  }

  const pageItems = filtered.slice(startIndex, startIndex + limit);
  const nextItem = filtered[startIndex + limit];
  const nextCursor = nextItem ? pageItems[pageItems.length - 1]?.timestamp : undefined;
  const hasMore = Boolean(nextCursor);

  return {
    items: pageItems,
    nextCursor,
    hasMore,
    totalCount,
    filteredCount,
  };
}
