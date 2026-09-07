import Link from "next/link";
import { notFound } from "next/navigation";
import { AssetRecordForm } from "@/components/asset-record-form";
import { Button } from "@/components/ui/button";
import { getAssetFormFields, isAssetResource } from "@/lib/letron-api";

export const dynamic = "force-dynamic";
export default async function NewAssetResourcePage({ params }: { params: Promise<{ resource: string }> }) { const { resource } = await params; if (!isAssetResource(resource)) notFound(); return <main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div className="flex items-center justify-between"><div><div className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Assets / New</div><h1 className="mt-1 text-3xl font-bold">Create {resource.replaceAll("-", " ")}</h1></div><Button variant="outline" asChild><Link href={`/assets/${resource}`}>Cancel</Link></Button></div><AssetRecordForm resource={resource} fields={getAssetFormFields(resource)} /></main>; }
