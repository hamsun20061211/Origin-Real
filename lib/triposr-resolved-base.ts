/**
 * 헬스 프로브가 실제로 통과한 베이스 URL (예: localhost vs 127.0.0.1).
 * Next dev 서버 프로세스 안에서만 유지되며, 이후 프록시 fetch 가 동일 호스트를 쓰게 한다.
 */
import { getTriposrBaseUrl } from "@/lib/triposr-config";

let reachable: string | null = null;

export function setTriposrReachableBaseUrl(url: string): void {
  reachable = url.replace(/\/$/, "").trim();
}

export function clearTriposrReachableBaseUrl(): void {
  reachable = null;
}

export function getTriposrEffectiveBaseUrl(): string {
  return reachable ?? getTriposrBaseUrl();
}
