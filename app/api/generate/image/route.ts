import { NextRequest } from "next/server";
import { handleImageGeneratePost } from "@/app/api/generate/shared-image";

export const runtime = "nodejs";
export const maxDuration = 300;

/** Image → TripoSR `POST /generate/image` */
export async function POST(req: NextRequest) {
  return handleImageGeneratePost(req, "/generate/image");
}
