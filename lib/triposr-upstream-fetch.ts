/**
 * Next API 라우트 → 로컬 TripoSR 업스트림.
 * Windows 등에서 global fetch(undici) 가 loopback 에서 불안정할 수 있어
 * IPv4 우선 DNS + undici Agent( family: 4 ) 로 고정한다.
 */
import dns from "node:dns";
import { Agent, fetch as undiciFetch } from "undici";

dns.setDefaultResultOrder("ipv4first");

const triposrAgent = new Agent({ pipelining: 0 });

export async function triposrUpstreamFetch(
  url: string | URL,
  init?: RequestInit,
): Promise<Response> {
  const res = await undiciFetch(url, {
    ...(init ?? {}),
    dispatcher: triposrAgent,
  } as Parameters<typeof undiciFetch>[1]);
  return res as unknown as Response;
}
