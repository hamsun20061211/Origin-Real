import { NextRequest, NextResponse } from "next/server";
import { getTriposrGenerateTimeoutMs } from "@/lib/triposr-config";
import { getTriposrEffectiveBaseUrl } from "@/lib/triposr-resolved-base";
import { triposrUpstreamFetch } from "@/lib/triposr-upstream-fetch";

function isLikelyGlb(buf: ArrayBuffer) {
  if (buf.byteLength < 4) return false;
  const u8 = new Uint8Array(buf.slice(0, 4));
  return u8[0] === 0x67 && u8[1] === 0x6c && u8[2] === 0x54 && u8[3] === 0x46;
}

export const runtime = "nodejs";
export const maxDuration = 300;

/**
 * Browser → Next → TripoSR `POST /generate-3d`.
 * This avoids browser CORS / mixed-content issues when the UI is served over https.
 */
export async function POST(req: NextRequest) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data.", code: "BAD_FORM" }, { status: 400 });
  }

  const image = formData.get("image");
  const imageUrl = formData.get("image_url");
  const responseMode = String(formData.get("response_mode") ?? "inline");

  if (!(image instanceof File) && !(typeof imageUrl === "string" && imageUrl.trim())) {
    return NextResponse.json(
      { error: "Provide either multipart field `image` or form field `image_url`.", code: "NO_IMAGE" },
      { status: 400 },
    );
  }

  const upstreamForm = new FormData();
  if (image instanceof File && image.size > 0) {
    upstreamForm.append("image", image, image.name);
  } else if (typeof imageUrl === "string" && imageUrl.trim()) {
    upstreamForm.append("image_url", imageUrl.trim());
  }
  upstreamForm.append("response_mode", responseMode || "inline");

  const base = getTriposrEffectiveBaseUrl();
  const timeoutMs = getTriposrGenerateTimeoutMs();

  let upstream: Response;
  let buf: ArrayBuffer;
  try {
    upstream = await triposrUpstreamFetch(`${base}/generate-3d`, {
      method: "POST",
      body: upstreamForm,
      signal: AbortSignal.timeout(timeoutMs),
    });
    buf = await upstream.arrayBuffer();
  } catch (e) {
    const msg = e instanceof Error ? e.message : "fetch failed";
    const name = e instanceof Error ? e.name : "";
    const isTimeout =
      name === "AbortError" || name === "TimeoutError" || /aborted|timeout|timed out/i.test(msg);
    if (isTimeout) {
      return NextResponse.json(
        {
          error:
            `3D generation did not finish within ${Math.round(timeoutMs / 1000)}s. ` +
            `The engine may still be working — check the engine terminal logs. (${base})`,
          code: "GENERATE_TIMEOUT",
        },
        { status: 504 },
      );
    }
    return NextResponse.json(
      {
        error: `Could not reach the local engine. Make sure \`npm run engine\` is running. (${base})`,
        code: "ENGINE_OFFLINE",
      },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    let detail = "";
    try {
      detail = new TextDecoder().decode(buf.slice(0, 2000));
    } catch {
      /* ignore */
    }
    return NextResponse.json(
      { error: detail || `Engine error (HTTP ${upstream.status})`, code: "UPSTREAM_ERROR" },
      { status: 502 },
    );
  }

  const ct = upstream.headers.get("content-type") ?? "";
  const looksBinary = ct.includes("gltf") || ct.includes("model") || ct.includes("octet-stream");
  if (!looksBinary && !isLikelyGlb(buf)) {
    return NextResponse.json(
      { error: "Response does not look like a GLB model.", code: "INVALID_MODEL" },
      { status: 502 },
    );
  }

  return new NextResponse(buf, {
    status: 200,
    headers: {
      "Content-Type": "model/gltf-binary",
      "Content-Disposition": 'attachment; filename="origin-real-generate-3d.glb"',
      "Cache-Control": "no-store",
    },
  });
}

