import { NextResponse } from "next/server";
import { getTriposrBaseUrl } from "@/lib/triposr-config";
import { engineProbeBaseUrls, probeTriposrEngine } from "@/lib/triposr-probe";
import {
  clearTriposrReachableBaseUrl,
  setTriposrReachableBaseUrl,
} from "@/lib/triposr-resolved-base";

export const runtime = "nodejs";
/** TripoSR 첫 기동 시 모델 로딩으로 포트가 늦게 열릴 수 있음 */
export const maxDuration = 120;

const PROBE_PATHS = ["/health", "/", "/openapi.json", "/docs"];

/**
 * 브라우저 → Next → TripoSR 연결 여부 (CORS 없이 서버에서 검사).
 * Windows loopback 에서 fetch(undici) 가 실패하는 경우가 있어 node:http + IPv4(family:4) 로 프로빙한다.
 */
export async function GET() {
  const configured = getTriposrBaseUrl();
  const bases = engineProbeBaseUrls(configured);
  const totalBudget = Math.min(
    90_000,
    Number(process.env.TRIPOSR_HEALTH_TIMEOUT_MS || 45_000) || 45_000,
  );
  const denom = Math.max(1, bases.length * PROBE_PATHS.length);
  const perTry = Math.max(3500, Math.min(15_000, Math.floor(totalBudget / denom)));

  const { ok, baseUrl, lastStatus } = await probeTriposrEngine(bases, PROBE_PATHS, perTry);

  if (ok) {
    setTriposrReachableBaseUrl(baseUrl);
  } else {
    clearTriposrReachableBaseUrl();
  }

  let lastError = "";
  if (!ok && process.env.NODE_ENV === "development") {
    lastError = lastStatus > 0 ? `HTTP ${lastStatus}` : `no response (${bases.join(", ")})`;
  }

  return NextResponse.json({
    ok,
    baseUrl: ok ? baseUrl : configured,
    ...(process.env.NODE_ENV === "development" && !ok && lastError
      ? { lastError: lastError.slice(0, 240) }
      : {}),
  });
}
