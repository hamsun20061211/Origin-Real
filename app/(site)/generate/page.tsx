import { Dashboard } from "@/components/Dashboard";
import type { GenerationMode } from "@/lib/generation-modes";

function parseMode(raw: string | string[] | undefined): GenerationMode {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (v === "text" || v === "texture" || v === "image") return v;
  return "image";
}

export default function GeneratePage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const initialMode = parseMode(searchParams.mode);
  return <Dashboard initialMode={initialMode} />;
}
