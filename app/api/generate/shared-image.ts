import { NextRequest, NextResponse } from "next/server";
import { getTriposrGenerateTimeoutMs, getTriposrImageField } from "@/lib/triposr-config";
import {
  postMultipartLoopbackWithRetry,
  type TriposrMultipartPart,
} from "@/lib/triposr-loopback-multipart";
import { triposrLoopbackBaseCandidates } from "@/lib/triposr-loopback-urls";
import { getTriposrEffectiveBaseUrl } from "@/lib/triposr-resolved-base";

function isLikelyGlbBuf(buf: Buffer) {
  if (buf.length < 4) return false;
  return buf[0] === 0x67 && buf[1] === 0x6c && buf[2] === 0x54 && buf[3] === 0x46;
}

function safeFilename(name: string, fallback: string) {
  return (name || fallback).replace(/[\r\n"]/g, "_");
}

/**
 * 멀티뷰/단일 이미지 폼을 TripoSR `POST /generate` 또는 `/generate/image`로 전달.
 * 업스트림: node:http multipart (Windows 루프백 fetch 실패 완화) + 127.0.0.1/localhost 교차.
 */
export async function handleImageGeneratePost(
  req: NextRequest,
  upstreamPath: "/generate" | "/generate/image",
) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "잘못된 폼 데이터입니다." }, { status: 400 });
  }

  const configuredField = getTriposrImageField();
  const single =
    formData.get(configuredField) ?? formData.get("image") ?? formData.get("file");
  const front = formData.get("front");
  const back = formData.get("back");
  const left = formData.get("left");
  const right = formData.get("right");

  const hasMulti = front instanceof File && front.size > 0;
  const hasSingle = single instanceof File && single.size > 0;

  if (!hasMulti && !hasSingle) {
    return NextResponse.json(
      {
        error: `멀티뷰 필드 front 또는 단일 필드(${configuredField} / image / file)가 필요합니다.`,
        code: "NO_IMAGE",
      },
      { status: 400 },
    );
  }

  const parts: TriposrMultipartPart[] = [];

  if (hasMulti) {
    const push = async (file: File | null, field: string) => {
      if (!(file instanceof File) || file.size === 0) return;
      parts.push({
        fieldName: field,
        filename: safeFilename(file.name, `${field}.png`),
        contentType: file.type || "application/octet-stream",
        data: Buffer.from(await file.arrayBuffer()),
      });
    };
    await push(front as File, "front");
    await push(back instanceof File ? back : null, "back");
    await push(left instanceof File ? left : null, "left");
    await push(right instanceof File ? right : null, "right");
  } else {
    const singleFile = single as File;
    parts.push({
      fieldName: configuredField,
      filename: safeFilename(singleFile.name, "image.png"),
      contentType: singleFile.type || "application/octet-stream",
      data: Buffer.from(await singleFile.arrayBuffer()),
    });
  }

  const base = getTriposrEffectiveBaseUrl();
  const bases = triposrLoopbackBaseCandidates(base);

  /** 공식 TripoSR만 켠 경우 `/generate/image` 없이 `POST /generate` 만 있을 수 있어 404 시 한 번 폴백 */
  const pathTryOrder: ("/generate" | "/generate/image")[] =
    upstreamPath === "/generate/image" ? ["/generate/image", "/generate"] : ["/generate"];

  const timeoutMs = getTriposrGenerateTimeoutMs();
  const retryOpts = {
    attempts: Math.max(3, parseInt(process.env.TRIPOSR_GENERATE_RETRIES ?? "4", 10) || 4),
    delayMs: Math.max(500, parseInt(process.env.TRIPOSR_GENERATE_RETRY_DELAY_MS ?? "900", 10) || 900),
  };

  let best: { statusCode: number; body: Buffer } | null = null;
  let lastNet: string | null = null;

  outer: for (let i = 0; i < pathTryOrder.length; i++) {
    const p = pathTryOrder[i];
    for (const b of bases) {
      try {
        const r = await postMultipartLoopbackWithRetry(`${b}${p}`, parts, timeoutMs, retryOpts);
        best = r;
        if (r.statusCode >= 200 && r.statusCode < 300) {
          break outer;
        }
        const fallback =
          p === "/generate/image" && r.statusCode === 404 && i < pathTryOrder.length - 1;
        if (fallback) {
          continue outer;
        }
        break outer;
      } catch (e) {
        lastNet = e instanceof Error ? e.message : String(e);
        console.warn("[Origin Real] TripoSR generate loopback POST:", b, p, lastNet);
      }
    }
  }

  if (!best) {
    const b = getTriposrEffectiveBaseUrl();
    const isTimeout = lastNet && /ETIMEDOUT|timeout/i.test(lastNet);
    console.error("[Origin Real] TripoSR image generate upstream error:", lastNet, b);
    if (isTimeout) {
      return NextResponse.json(
        {
          error:
            `TripoSR 생성이 ${timeoutMs / 1000}초 안에 끝나지 않았습니다. 엔진은 계속 돌아갈 수 있으니 터미널 로그를 확인하세요. ` +
            `HQ·Real-ESRGAN을 끄거나(.env TRIPOSR_REALESRGAN=0) TRIPOSR_GENERATE_TIMEOUT_MS 를 늘리세요. (${b})`,
          code: "GENERATE_TIMEOUT",
        },
        { status: 504 },
      );
    }
    return NextResponse.json(
      {
        error: `TripoSR 로컬 엔진에 연결할 수 없습니다. ${b} 에서 npm run engine 이 실행 중인지 확인하세요.`,
        code: "ENGINE_OFFLINE",
        detail: (lastNet ?? "").slice(0, 400),
      },
      { status: 502 },
    );
  }

  const buf = best.body;

  if (best.statusCode < 200 || best.statusCode >= 300) {
    let detail = "";
    try {
      detail = buf.subarray(0, 2000).toString("utf8");
    } catch {
      /* ignore */
    }
    return NextResponse.json(
      { error: detail || `TripoSR 오류 (HTTP ${best.statusCode})`, code: "UPSTREAM_ERROR" },
      { status: 502 },
    );
  }

  const looksBinary = isLikelyGlbBuf(buf);
  if (!looksBinary) {
    return NextResponse.json(
      {
        error:
          "응답이 GLB로 보이지 않습니다. TripoSR이 `model/gltf-binary` 또는 바이너리 GLB를 반환하는지 확인하세요.",
        code: "INVALID_MODEL",
      },
      { status: 502 },
    );
  }

  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
  return new NextResponse(ab, {
    status: 200,
    headers: {
      "Content-Type": "model/gltf-binary",
      "Content-Disposition": 'attachment; filename="origin-real-triposr.glb"',
      "Cache-Control": "no-store",
    },
  });
}
