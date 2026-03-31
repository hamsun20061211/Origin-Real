/**
 * Next 서버(Node)에서 로컬 TripoSR 헬스 확인.
 * Windows 등에서 undici fetch 가 loopback 에 실패하는 경우가 있어 node:http 를 사용한다.
 */
import http from "node:http";
import https from "node:https";

/** TRIPOSR_URL 기준으로 시도할 베이스 URL 목록 (127.0.0.1 ↔ localhost 교차). */
export function engineProbeBaseUrls(primary: string): string[] {
  let s = primary.trim().replace(/\/$/, "");
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    s = s.slice(1, -1).trim().replace(/\/$/, "");
  }
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (u: string) => {
    const x = u.replace(/\/$/, "");
    if (!seen.has(x)) {
      seen.add(x);
      out.push(x);
    }
  };
  add(s);
  try {
    const withProto = s.includes("://") ? s : `http://${s}`;
    const u = new URL(withProto);
    if (u.protocol !== "http:" && u.protocol !== "https:") {
      return out;
    }
    const port = u.port || (u.protocol === "https:" ? "443" : "8001");
    if (u.protocol === "http:") {
      add(`http://127.0.0.1:${port}`);
      add(`http://localhost:${port}`);
    }
  } catch {
    add("http://127.0.0.1:8001");
    add("http://localhost:8001");
  }
  return out;
}

function requestOnce(
  fullUrl: string,
  timeoutMs: number,
): Promise<{ ok: boolean; status: number }> {
  return new Promise((resolve) => {
    let settled = false;
    const done = (ok: boolean, status: number) => {
      if (settled) return;
      settled = true;
      resolve({ ok, status });
    };
    try {
      const u = new URL(fullUrl);
      const lib = u.protocol === "https:" ? https : http;
      const req = lib.request(
        {
          hostname: u.hostname,
          port: u.port || (u.protocol === "https:" ? 443 : 80),
          path: `${u.pathname}${u.search}` || "/",
          method: "GET",
          timeout: timeoutMs,
          family: 4,
          headers: { Connection: "close", Accept: "*/*" },
        },
        (res) => {
          res.resume();
          const code = res.statusCode ?? 0;
          done(code > 0 && code < 500, code);
        },
      );
      req.on("error", () => done(false, 0));
      req.on("timeout", () => {
        req.destroy();
        done(false, 0);
      });
      req.end();
    } catch {
      done(false, 0);
    }
  });
}

/** 첫 성공한 베이스 URL 반환; 전부 실패 시 null */
export async function probeTriposrEngine(
  baseUrls: string[],
  paths: string[],
  timeoutMsPerRequest: number,
): Promise<{ ok: boolean; baseUrl: string; lastStatus: number }> {
  let lastStatus = 0;
  for (const base of baseUrls) {
    for (const p of paths) {
      const path = p.startsWith("/") ? p : `/${p}`;
      const url = `${base}${path}`;
      const { ok, status } = await requestOnce(url, timeoutMsPerRequest);
      lastStatus = status;
      if (ok) {
        return { ok: true, baseUrl: base, lastStatus: status };
      }
    }
  }
  return { ok: false, baseUrl: baseUrls[0] ?? "http://127.0.0.1:8001", lastStatus };
}
