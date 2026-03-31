/** Default matches triposr-server/start-engine.ps1 (8000 is often busy on Windows). */
const DEFAULT_TRIPOSR_URL = "http://127.0.0.1:8001";

/** Base URL for local TripoSR (no trailing slash in usage). */
export function getTriposrBaseUrl(): string {
  let raw = (process.env.TRIPOSR_URL ?? DEFAULT_TRIPOSR_URL).trim();
  if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'"))) {
    raw = raw.slice(1, -1).trim();
  }
  if (!raw.includes("://")) {
    raw = `http://${raw}`;
  }
  return raw.replace(/\/$/, "");
}

export { DEFAULT_TRIPOSR_URL };

/** Form field name forwarded to TripoSR `/generate` (override if your server expects e.g. `file`). */
export function getTriposrImageField(): string {
  return process.env.TRIPOSR_IMAGE_FIELD ?? "image";
}

/** Next → TripoSR `POST /generate` 전체 대기(ms). HQ·Real-ESRGAN 시 10분 기본. */
export function getTriposrGenerateTimeoutMs(): number {
  const raw = (process.env.TRIPOSR_GENERATE_TIMEOUT_MS ?? "").trim();
  if (raw) {
    const n = parseInt(raw, 10);
    if (!Number.isNaN(n) && n >= 30_000) return n;
  }
  return 600_000;
}
