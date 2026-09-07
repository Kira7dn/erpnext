import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { AssetsShell } from "@/components/assets-shell";
import { AssetResourceTable } from "@/components/asset-resource-table";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ASSET_RESOURCES, GatewayAccessDeniedError, GatewayAuthenticationRequiredError, isAssetResource, listAssetResource } from "@/lib/letron-api";

export const dynamic = "force-dynamic";
const title = (resource: string) => resource.split("-").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
export function generateStaticParams() { return ASSET_RESOURCES.map((resource) => ({ resource })); }
export default async function AssetResourcePage({ params }: { params: Promise<{ resource: string }> }) { const { resource } = await params; if (!isAssetResource(resource)) notFound(); let rows: Record<string, unknown>[] = []; let error: string | null = null; let login = false; let denied = false; try { rows = await listAssetResource(resource, (await cookies()).toString()); } catch (cause) { login = cause instanceof GatewayAuthenticationRequiredError; denied = cause instanceof GatewayAccessDeniedError; error = cause instanceof Error ? cause.message : "Không thể tải dữ liệu tài sản"; } return <AssetsShell><main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Assets / API resource</div><h1 className="text-3xl font-bold tracking-tight">{title(resource)}</h1><p className="mt-2 text-muted-foreground">Dữ liệu live từ Letron Gateway.</p></div><Button asChild><Link href={`/assets/${resource}/new`}>New record</Link></Button></div>{error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>{login ? "Đăng nhập qua Global Portal" : denied ? "Chưa được cấp quyền" : "Không lấy được dữ liệu"}</AlertTitle><AlertDescription>{error}{login ? <a className="mt-3 block underline" href="/api/auth/login">Đăng nhập bằng Lark</a> : null}</AlertDescription></Alert> : <AssetResourceTable resource={resource} rows={rows} />}</main></AssetsShell>; }
