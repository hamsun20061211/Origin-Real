import { NextRequest } from "next/server";
import { handleImageGeneratePost } from "@/app/api/generate/shared-image";

export const runtime = "nodejs";
export const maxDuration = 300;

/**
 * 레거시: `POST /generate` → TripoSR `/generate`
 * 신규 UI는 `POST /api/generate/image` → `/generate/image` 권장.
 */
export async function POST(req: NextRequest) {
  return handleImageGeneratePost(req, "/generate");
}
