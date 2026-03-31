import { NextRequest, NextResponse } from "next/server";
import { getTriposrEffectiveBaseUrl } from "@/lib/triposr-resolved-base";
import { triposrUpstreamFetch } from "@/lib/triposr-upstream-fetch";

export const runtime = "nodejs";
export const maxDuration = 300;

/** GLB + 지시문 → TripoSR `POST /generate/texture` (엔진 스텁 시 501) */
export async function POST(req: NextRequest) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "폼 데이터가 필요합니다." }, { status: 400 });
  }

  const model =
    formData.get("model") ?? formData.get("glb") ?? formData.get("file");
  if (!(model instanceof File) || model.size === 0) {
    return NextResponse.json(
      { error: "GLB 파일(필드 model / glb / file)이 필요합니다.", code: "NO_GLB" },
      { status: 400 },
    );
  }

  const instructions = formData.get("instructions");
  const instStr = typeof instructions === "string" ? instructions : "";

  const upstreamForm = new FormData();
  upstreamForm.append("model", model, model.name || "input.glb");
  upstreamForm.append("instructions", instStr);

  const url = `${getTriposrEffectiveBaseUrl()}/generate/texture`;
  let upstream: Response;
  try {
    upstream = await triposrUpstreamFetch(url, {
      method: "POST",
      body: upstreamForm,
      signal: AbortSignal.timeout(280_000),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "fetch failed";
    const base = getTriposrEffectiveBaseUrl();
    console.error("[Origin Real] /generate/texture unreachable:", msg, base);
    return NextResponse.json(
      {
        error: `텍스처 엔진에 연결할 수 없습니다. ${base} 에서 엔진이 떠 있는지 확인하세요.`,
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
        "Content-Disposition": 'attachment; filename="origin-real-textured.glb"',
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

  return NextResponse.json(
    {
      error: detail || `엔진 응답 (HTTP ${upstream.status})`,
      code: upstream.status === 501 ? "NOT_IMPLEMENTED" : "UPSTREAM_ERROR",
      status: upstream.status,
    },
    { status: upstream.status >= 400 ? upstream.status : 502 },
  );
}
