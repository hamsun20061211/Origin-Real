/**
 * TripoSR 로컬 업스트림 POST (multipart).
 * Windows 등에서 undici/fetch 가 127.0.0.1 에서 "fetch failed" 나는 경우가 있어
 * engine-health 와 동일하게 node:http + family:4 를 사용한다.
 */
import { randomBytes } from "node:crypto";
import http from "node:http";
import https from "node:https";

export type TriposrMultipartPart = {
  fieldName: string;
  filename: string;
  contentType: string;
  data: Buffer;
};

export function buildMultipartBody(parts: TriposrMultipartPart[]): {
  contentTypeHeader: string;
  body: Buffer;
} {
  const boundary = "----OriginReal" + randomBytes(16).toString("hex");
  const crlf = "\r\n";
  const chunks: Buffer[] = [];
  for (const p of parts) {
    const safeName = p.fieldName.replace(/[\r\n"]/g, "");
    const safeFn = p.filename.replace(/[\r\n"]/g, "");
    chunks.push(
      Buffer.from(
        `--${boundary}${crlf}` +
          `Content-Disposition: form-data; name="${safeName}"; filename="${safeFn}"${crlf}` +
          `Content-Type: ${p.contentType}${crlf}${crlf}`,
        "utf8",
      ),
    );
    chunks.push(p.data);
    chunks.push(Buffer.from(crlf));
  }
  chunks.push(Buffer.from(`--${boundary}--${crlf}`, "utf8"));
  return {
    contentTypeHeader: `multipart/form-data; boundary=${boundary}`,
    body: Buffer.concat(chunks),
  };
}

export type LoopbackPostResult = {
  statusCode: number;
  body: Buffer;
};

export function httpPostLoopback(
  fullUrl: string,
  body: Buffer,
  extraHeaders: Record<string, string>,
  timeoutMs: number,
): Promise<LoopbackPostResult> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const done = (err: Error | null, res?: LoopbackPostResult) => {
      if (settled) return;
      settled = true;
      if (err) reject(err);
      else resolve(res!);
    };

    try {
      const u = new URL(fullUrl);
      const lib = u.protocol === "https:" ? https : http;
      const portStr = u.port;
      const port = portStr
        ? parseInt(portStr, 10)
        : u.protocol === "https:"
          ? 443
          : 80;
      const chunks: Buffer[] = [];
      const req = lib.request(
        {
          hostname: u.hostname,
          port,
          path: `${u.pathname}${u.search}`,
          method: "POST",
          timeout: timeoutMs,
          family: 4,
          headers: {
            ...extraHeaders,
            "Content-Length": String(body.length),
            Connection: "close",
            Accept: "*/*",
          },
        },
        (incoming) => {
          incoming.on("data", (c: Buffer) => chunks.push(Buffer.from(c)));
          incoming.on("end", () => {
            done(null, { statusCode: incoming.statusCode ?? 0, body: Buffer.concat(chunks) });
          });
          incoming.on("error", (e) => done(e));
        },
      );
      req.on("error", (e) => done(e));
      req.on("timeout", () => {
        req.destroy();
        done(new Error(`ETIMEDOUT after ${timeoutMs}ms`));
      });
      req.write(body);
      req.end();
    } catch (e) {
      done(e instanceof Error ? e : new Error(String(e)));
    }
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function isTransientNetworkError(err: Error): boolean {
  const m = err.message;
  return (
    /ECONNREFUSED|ECONNRESET|ETIMEDOUT|EPIPE|ENOTFOUND|failed/i.test(m) ||
    m === "fetch failed" ||
    /socket|timeout/i.test(m)
  );
}

function bodyLooksLikeModelLoading(buf: Buffer): boolean {
  const s = buf.subarray(0, 800).toString("utf8").toLowerCase();
  return (
    s.includes("로딩") ||
    s.includes("loading") ||
    s.includes("model_loaded") ||
    s.includes("아직") ||
    s.includes("warm") ||
    s.includes("not ready")
  );
}

export type MultipartRetryOpts = {
  /** 전체 시도 횟수 (네트워크 오류·503 로딩 시 재시도) */
  attempts?: number;
  /** 첫 재시도 대기(ms), 이후 선형 증가 */
  delayMs?: number;
};

/**
 * 연결 실패·타임아웃·엔진 503(모델 로딩 중) 시 짧게 재시도.
 */
export async function postMultipartLoopbackWithRetry(
  fullUrl: string,
  parts: TriposrMultipartPart[],
  timeoutMs: number,
  opts?: MultipartRetryOpts,
): Promise<LoopbackPostResult> {
  const { contentTypeHeader, body } = buildMultipartBody(parts);
  const attempts = Math.max(1, opts?.attempts ?? 5);
  const delayMs = Math.max(200, opts?.delayMs ?? 700);
  let lastErr: Error | null = null;

  for (let i = 0; i < attempts; i++) {
    try {
      const r = await httpPostLoopback(
        fullUrl,
        body,
        { "Content-Type": contentTypeHeader },
        timeoutMs,
      );
      const loading503 = r.statusCode === 503 && bodyLooksLikeModelLoading(r.body);
      if (loading503 && i < attempts - 1) {
        await delay(delayMs * (i + 1));
        continue;
      }
      return r;
    } catch (e) {
      lastErr = e instanceof Error ? e : new Error(String(e));
      if (!isTransientNetworkError(lastErr) || i === attempts - 1) {
        throw lastErr;
      }
      await delay(delayMs * (i + 1));
    }
  }
  throw lastErr ?? new Error("TripoSR POST failed");
}
