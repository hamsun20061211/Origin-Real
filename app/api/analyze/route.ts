import { NextRequest, NextResponse } from "next/server";
import { postMultipartLoopbackWithRetry } from "@/lib/triposr-loopback-multipart";
import { triposrLoopbackBaseCandidates } from "@/lib/triposr-loopback-urls";
import { getTriposrEffectiveBaseUrl } from "@/lib/triposr-resolved-base";

export const runtime = "nodejs";
export const maxDuration = 120;

/**
 * TripoSR 로컬 엔진 `POST /analyze` 프록시 → 부품 JSON.
 * 업스트림은 fetch 대신 node:http(family:4) — Windows 루프백 불안정 완화.
 */
export async function POST(req: NextRequest) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "잘못된 폼 데이터입니다." }, { status: 400 });
  }

  const front = formData.get("front");
  if (!(front instanceof File) || front.size === 0) {
    return NextResponse.json(
      { error: "정면 이미지(필드 front)가 필요합니다.", code: "NO_FRONT" },
      { status: 400 },
    );
  }

  const frontBuf = Buffer.from(await front.arrayBuffer());
  const frontName = (front.name || "front.jpg").replace(/[\r\n"]/g, "_");
  const frontType = front.type || "application/octet-stream";

  const seedRaw = req.nextUrl.searchParams.get("seed");
  const seed = seedRaw ? Number.parseInt(seedRaw, 10) : 0;
  const safeSeed = Number.isFinite(seed) ? Math.max(0, Math.min(seed, 2_147_000_000)) : 0;

  const parts = [
    {
      fieldName: "front",
      filename: frontName,
      contentType: frontType,
      data: frontBuf,
    },
  ];

  const bases = triposrLoopbackBaseCandidates(getTriposrEffectiveBaseUrl());
  const timeoutMs = (() => {
    const raw = (process.env.TRIPOSR_ANALYZE_TIMEOUT_MS ?? "").trim();
    if (raw) {
      const n = parseInt(raw, 10);
      if (!Number.isNaN(n) && n >= 15_000) return Math.min(n, 300_000);
    }
    return 120_000;
  })();

  const attemptOpts = {
    attempts: Math.max(3, parseInt(process.env.TRIPOSR_ANALYZE_RETRIES ?? "5", 10) || 5),
    delayMs: Math.max(400, parseInt(process.env.TRIPOSR_ANALYZE_RETRY_DELAY_MS ?? "800", 10) || 800),
  };

  let lastErr = "";
  let result: Awaited<ReturnType<typeof postMultipartLoopbackWithRetry>> | null = null;

  for (const base of bases) {
    const url = `${base}/analyze?seed=${safeSeed}`;
    try {
      result = await postMultipartLoopbackWithRetry(url, parts, timeoutMs, attemptOpts);
      lastErr = "";
      break;
    } catch (e) {
      lastErr = e instanceof Error ? e.message : String(e);
      console.warn("[Origin Real] /analyze loopback POST failed:", base, lastErr);
    }
  }

  if (!result) {
    const base = getTriposrEffectiveBaseUrl();
    console.error("[Origin Real] /analyze unreachable:", lastErr, bases);
    return NextResponse.json(
      {
        error: `분석 엔진에 연결할 수 없습니다. ${base} 에서 npm run engine (main.py) 가 떠 있는지 확인하세요. 브라우저로 ${base}/health 가 열리는지도 확인하세요.`,
        code: "ENGINE_OFFLINE",
        detail: lastErr.slice(0, 500),
      },
      { status: 502 },
    );
  }

  const buf = result.body;
  if (result.statusCode === 404) {
    return NextResponse.json(
      {
        error:
          "엔진에 POST /analyze 가 없습니다. TripoSR 공식 저장소의 main.py 만 실행 중이면 404가 납니다. " +
          "Origin Real 프로젝트의 triposr-server/main.py 로 서버를 띄우세요 (프로젝트 루트에서 npm run engine, TRIPOSR_ROOT 는 TripoSR 클론 경로).",
        code: "ANALYZE_NOT_FOUND",
      },
      { status: 502 },
    );
  }

  if (result.statusCode < 200 || result.statusCode >= 300) {
    let detail = "";
    try {
      detail = buf.subarray(0, 2000).toString("utf8");
    } catch {
      /* ignore */
    }
    return NextResponse.json(
      {
        error: detail || `분석 오류 (HTTP ${result.statusCode})`,
        code: "UPSTREAM_ERROR",
        upstream_status: result.statusCode,
      },
      { status: 502 },
    );
  }

  try {
    const json = JSON.parse(buf.toString("utf8")) as unknown;
    return NextResponse.json(json);
  } catch {
    return NextResponse.json(
      { error: "분석 응답 JSON 파싱 실패", code: "BAD_JSON" },
      { status: 502 },
    );
  }
}
