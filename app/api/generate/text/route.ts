import { NextRequest, NextResponse } from "next/server";
import { getTriposrEffectiveBaseUrl } from "@/lib/triposr-resolved-base";
import { triposrUpstreamFetch } from "@/lib/triposr-upstream-fetch";

export const runtime = "nodejs";
export const maxDuration = 300;

type Body = {
  prompt?: string;
  enhance_keywords?: boolean;
};

/** Text → TripoSR `POST /generate/text` (엔진 스텁 시 501) */
export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "JSON 본문이 필요합니다." }, { status: 400 });
  }

  const prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";
  if (!prompt) {
    return NextResponse.json({ error: "prompt가 비어 있습니다.", code: "NO_PROMPT" }, { status: 400 });
  }

  const url = `${getTriposrEffectiveBaseUrl()}/generate/text`;
  let upstream: Response;
  try {
    upstream = await triposrUpstreamFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        enhance_keywords: body.enhance_keywords !== false,
      }),
      signal: AbortSignal.timeout(280_000),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "fetch failed";
    const base = getTriposrEffectiveBaseUrl();
    console.error("[Origin Real] /generate/text unreachable:", msg, base);
    return NextResponse.json(
      {
        error: `텍스트 생성 엔진에 연결할 수 없습니다. ${base} 에서 엔진이 떠 있는지 확인하세요.`,
        code: "ENGINE_OFFLINE",
      },
      { status: 502 },
    );
  }

  const buf = await upstream.arrayBuffer();
  const ct = upstream.headers.get("content-type") ?? "";

  if (upstream.ok && (ct.includes("gltf") || ct.includes("model") || ct.includes("octet-stream"))) {
    return new NextResponse(buf, {
      status: 200,
      headers: {
        "Content-Type": "model/gltf-binary",
        "Content-Disposition": 'attachment; filename="origin-real-text.glb"',
        "Cache-Control": "no-store",
      },
    });
  }

  let detail = "";
  try {
    detail = new TextDecoder().decode(buf.slice(0, 4000));
  } catch {
    /* ignore */
  }

  let message = detail || `엔진 응답 (HTTP ${upstream.status})`;
  try {
    const j = JSON.parse(detail) as { detail?: unknown };
    if (typeof j.detail === "string") message = j.detail;
    else if (Array.isArray(j.detail)) message = JSON.stringify(j.detail);
  } catch {
    /* not JSON */
  }

  return NextResponse.json(
    {
      error: message,
      code: upstream.status === 501 ? "NOT_IMPLEMENTED" : "UPSTREAM_ERROR",
      status: upstream.status,
    },
    { status: upstream.status >= 400 ? upstream.status : 502 },
  );
}
