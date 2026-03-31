import { DEFAULT_TRIPOSR_URL } from "@/lib/triposr-config";

/**
 * TripoSR 로컬 엔진 오프라인 시 토스트·인라인 에러.
 * `baseUrl`은 `/api/engine-health`의 `baseUrl`과 동일하게 넣으면 Next가 실제로 찍는 주소와 일치합니다.
 */
export function buildEngineOfflineMessage(baseUrl: string): string {
  const b = (baseUrl || "").trim() || DEFAULT_TRIPOSR_URL;
  return [
    `Local Engine Offline — ${b} 에서 엔진이 응답하지 않습니다.`,
    "",
    "가장 흔한 원인: TripoSR 엔진 터미널을 안 켰거나, 켰다가 닫았거나, 포트가 다릅니다.",
    "",
    "· (권장) 프로젝트 폴더에서 한 번에: npm run dev:full  → 웹(next dev) + 엔진(npm run engine) 같이 켜집니다.",
    "",
    "· (수동) 새 PowerShell 창 → cd 프로젝트 폴더 → npm run engine",
    "  → 로그에 Uvicorn running on http://0.0.0.0:8001 이 나와야 합니다. 이 창은 닫지 마세요.",
    "· (별도 창) npm run dev → 터미널에 나온 주소로 접속 (3000·3001·3002 등).",
    "",
    "· 확인: 브라우저에서 " + b + "/health 열기 — 안 열리면 엔진이 안 떠 있는 것입니다.",
    "· 또는 터미널: npm run engine:ping",
    "",
    "· .env.local 의 TRIPOSR_URL 포트 = 엔진 PORT (기본 8001).",
    "· npm run engine:stub 은 /health 만 되고 실제 메쉬 생성은 불가입니다.",
  ].join("\n");
}
