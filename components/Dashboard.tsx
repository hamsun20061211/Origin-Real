"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Download, Loader2, ScanLine, Shapes, Sparkles, Wand2 } from "lucide-react";
import { GenerationOverlay } from "@/components/GenerationOverlay";
import { PBRViewer } from "@/components/PBRViewer";
import { MultiViewUploadZone, type MultiViewState } from "@/components/MultiViewUploadZone";
import { PipelineStepper } from "@/components/PipelineStepper";
import { PartReviewPanel } from "@/components/PartReviewPanel";
import { MeshToast } from "@/components/Toast";
import { DashboardPipelineTabs } from "@/components/DashboardPipelineTabs";
import { DirectLoRAGenerateForm } from "@/components/DirectLoRAGenerateForm";
import { GenerationModeTabs } from "@/components/GenerationModeTabs";
import { TextTo3DPanel } from "@/components/TextTo3DPanel";
import { TextureModelUpload } from "@/components/TextureModelUpload";
import { buildEngineOfflineMessage } from "@/lib/api-config";
import { DEFAULT_TRIPOSR_URL } from "@/lib/triposr-config";
import {
  BUILDING_PIPELINE_GUIDE,
  type ImagePipelineTab,
  VEHICLE_PIPELINE_GUIDE,
} from "@/lib/special-pipeline-config";
import type { GenerationMode } from "@/lib/generation-modes";
import type { AnalyzedPart, AnalyzeResponse, PipelinePhase, ViewKey } from "@/lib/pipeline-types";
import { VIEW_ORDER } from "@/lib/pipeline-types";

const emptyViews = (): MultiViewState => ({
  front: null,
  back: null,
  left: null,
  right: null,
});

async function readApiErrorMessage(res: Response): Promise<string> {
  const t = await res.text();
  try {
    const j = JSON.parse(t) as { detail?: unknown; error?: unknown };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return JSON.stringify(j.detail);
    if (typeof j.error === "string") return j.error;
  } catch {
    /* ignore */
  }
  return t.slice(0, 2000) || `HTTP ${res.status}`;
}

type DashboardProps = {
  initialMode?: GenerationMode;
};

export function Dashboard({ initialMode = "image" }: DashboardProps) {
  const [mode, setMode] = useState<GenerationMode>(initialMode);

  const [views, setViews] = useState<MultiViewState>(emptyViews);
  const [phase, setPhase] = useState<PipelinePhase>("idle");
  const [parts, setParts] = useState<AnalyzedPart[]>([]);
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const [analyzeSeed, setAnalyzeSeed] = useState(0);

  const [textPrompt, setTextPrompt] = useState("");
  const [enhanceKeywords, setEnhanceKeywords] = useState(true);
  const [textureFile, setTextureFile] = useState<File | null>(null);
  const [textureInstructions, setTextureInstructions] = useState("");

  const [glbUrl, setGlbUrl] = useState<string | null>(null);
  const [modelVersion, setModelVersion] = useState(0);
  const [meshBusy, setMeshBusy] = useState(false);
  const [textGenBusy, setTextGenBusy] = useState(false);
  const [textureGenBusy, setTextureGenBusy] = useState(false);
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [autoRotate, setAutoRotate] = useState(true);
  const [loadingFadeOut, setLoadingFadeOut] = useState(false);
  const [toastOpen, setToastOpen] = useState(false);
  /** Next 서버가 TRIPOSR_URL 로 프로빙하는 주소 (/api/engine-health 의 baseUrl) */
  const [engineDisplayUrl, setEngineDisplayUrl] = useState(DEFAULT_TRIPOSR_URL);
  const progressTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const [imagePipelineTab, setImagePipelineTab] = useState<ImagePipelineTab>("general");
  const [vehicleLoRAFile, setVehicleLoRAFile] = useState<File | null>(null);
  const [vehicleLoRAUrl, setVehicleLoRAUrl] = useState("");
  const [buildingLoRAFile, setBuildingLoRAFile] = useState<File | null>(null);
  const [buildingLoRAUrl, setBuildingLoRAUrl] = useState("");
  const [directLoRABusy, setDirectLoRABusy] = useState(false);
  const [glbSource, setGlbSource] = useState<"general" | "vehicle" | "building" | "text" | "texture" | null>(
    null,
  );

  const generationOverlayBusy = meshBusy || textGenBusy || textureGenBusy || directLoRABusy;

  const previewUrls = useMemo(() => {
    const m: Record<ViewKey, string | null> = {
      front: null,
      back: null,
      left: null,
      right: null,
    };
    VIEW_ORDER.forEach((k) => {
      if (views[k]) m[k] = URL.createObjectURL(views[k]!);
    });
    return m;
  }, [views]);

  useEffect(() => {
    return () => {
      VIEW_ORDER.forEach((k) => {
        const u = previewUrls[k];
        if (u) URL.revokeObjectURL(u);
      });
    };
  }, [previewUrls]);

  useEffect(() => {
    return () => {
      if (glbUrl) URL.revokeObjectURL(glbUrl);
    };
  }, [glbUrl]);

  const checkEngineHealth = useCallback(async (): Promise<{
    ok: boolean;
    baseUrl: string;
  }> => {
    const once = async () => {
      try {
        const res = await fetch("/api/engine-health", { cache: "no-store" });
        if (!res.ok) {
          setEngineDisplayUrl(DEFAULT_TRIPOSR_URL);
          return { ok: false, baseUrl: DEFAULT_TRIPOSR_URL };
        }
        const data = (await res.json()) as { ok?: boolean; baseUrl?: string };
        const baseUrl =
          typeof data.baseUrl === "string" && data.baseUrl.length > 0
            ? data.baseUrl
            : DEFAULT_TRIPOSR_URL;
        setEngineDisplayUrl(baseUrl);
        return { ok: Boolean(data.ok), baseUrl };
      } catch {
        return { ok: false, baseUrl: DEFAULT_TRIPOSR_URL };
      }
    };

    let r = await once();
    if (r.ok) return r;
    await new Promise((resolve) => setTimeout(resolve, 450));
    r = await once();
    if (r.ok) return r;
    await new Promise((resolve) => setTimeout(resolve, 800));
    return await once();
  }, []);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    let cancelled = false;
    let attempt = 0;
    const maxAttempts = 36;

    const scheduleNext = () => {
      if (cancelled || attempt >= maxAttempts) return;
      window.setTimeout(() => void poll(), 5000);
    };

    const poll = async () => {
      if (cancelled) return;
      attempt += 1;
      const { ok } = await checkEngineHealth();
      if (cancelled) return;
      if (ok) {
        setToastOpen(false);
        return;
      }
      // 엔진 기동·모델 로딩이 느리면 첫 헬스만으로 토스트가 뜨는 경우가 있어, 여러 번 실패 후에만 표시
      if (attempt >= 5) setToastOpen(true);
      scheduleNext();
    };

    void poll();
    return () => {
      cancelled = true;
    };
  }, [checkEngineHealth]);

  const clearProgressTimer = useCallback(() => {
    if (progressTimer.current) clearInterval(progressTimer.current);
    progressTimer.current = null;
  }, []);

  useEffect(() => () => clearProgressTimer(), [clearProgressTimer]);

  const setView = useCallback((key: ViewKey, file: File | null) => {
    setViews((v) => ({ ...v, [key]: file }));
  }, []);

  const startGenProgress = useCallback(() => {
    setProgress(12);
    clearProgressTimer();
    progressTimer.current = setInterval(() => {
      setProgress((p) => (p >= 86 ? p : p + Math.random() * 5 + 1.5));
    }, 400);
  }, [clearProgressTimer]);

  const runAnalyze = useCallback(
    async (seed: number) => {
      if (!views.front || analyzeBusy || generationOverlayBusy) return;
      const { ok: engineOk, baseUrl } = await checkEngineHealth();
      if (engineOk) {
        setError(null);
      }
      setAnalyzeBusy(true);
      setPhase("analyze");
      setProgress(8);
      clearProgressTimer();
      progressTimer.current = setInterval(() => {
        setProgress((p) => (p >= 88 ? p : p + 4 + Math.random() * 6));
      }, 320);

      const fd = new FormData();
      fd.append("front", views.front);

      try {
        const res = await fetch(`/api/analyze?seed=${seed}`, { method: "POST", body: fd });
        clearProgressTimer();
        if (!res.ok) {
          const j = (await res.json().catch(() => ({}))) as {
            error?: string;
            code?: string;
            detail?: string;
          };
          const detail = typeof j.detail === "string" && j.detail.trim() ? `\n\n(기술 상세: ${j.detail.trim()})` : "";
          if (j.code === "ENGINE_OFFLINE") {
            // 헬스는 되는데 /analyze 프록시만 실패할 때 같은 문구면 "오프라인" 오해가 남
            if (!engineOk) setToastOpen(true);
            else
              throw new Error(
                `${j.error ?? `분석 요청 실패 (${res.status})`}${detail}\n\n엔진 /health 는 통과했습니다. npm run dev 를 재시작한 뒤 다시 시도하거나, TripoSR 터미널 로그를 확인하세요.`,
              );
          }
          throw new Error((j.error ?? `분석 실패 (${res.status})`) + detail);
        }
        const data = (await res.json()) as AnalyzeResponse;
        const list = Array.isArray(data.parts) ? data.parts : [];
        setParts(list);
        setAccepted(Object.fromEntries(list.map((p) => [p.id, true])));
        setProgress(100);
        setPhase("segment");
      } catch (e) {
        clearProgressTimer();
        setProgress(0);
        setPhase("idle");
        setError(e instanceof Error ? e.message : "분석 오류");
      } finally {
        setAnalyzeBusy(false);
        setTimeout(() => setProgress(0), 400);
      }
    },
    [views.front, analyzeBusy, generationOverlayBusy, checkEngineHealth, clearProgressTimer],
  );

  const runMeshGeneration = async () => {
    if (!views.front || meshBusy || analyzeBusy) return;
    const { ok: engineOk, baseUrl } = await checkEngineHealth();
    // 헬스만 간헐적으로 실패하는 경우(타이밍·부하) 대비: 실제 POST 로 최종 판별
    if (engineOk) {
      setError(null);
    }

    setMeshBusy(true);
    setPhase("mesh");
    setLoadingFadeOut(false);
    setAutoRotate(false);
    startGenProgress();

    const fd = new FormData();
    fd.append("front", views.front);
    if (views.back) fd.append("back", views.back);
    if (views.left) fd.append("left", views.left);
    if (views.right) fd.append("right", views.right);

    try {
      const res = await fetch("/api/generate/image", { method: "POST", body: fd });
      clearProgressTimer();

      if (!res.ok) {
        const text = await res.text();
        let msg = text.slice(0, 2000) || `HTTP ${res.status}`;
        let code: string | undefined;
        try {
          const j = JSON.parse(text) as { error?: string; code?: string };
          if (typeof j.error === "string") msg = j.error;
          if (typeof j.code === "string") code = j.code;
        } catch {
          /* ignore */
        }
        if (code === "GENERATE_TIMEOUT" || res.status === 504) {
          throw new Error(msg);
        }
        const looksUnreachable =
          res.status === 502 ||
          code === "ENGINE_OFFLINE" ||
          /연결|unreachable|ECONNREFUSED|fetch failed|NetworkError/i.test(msg);
        if (looksUnreachable) {
          setToastOpen(true);
          throw new Error(`${buildEngineOfflineMessage(baseUrl)}\n\n---\n서버 응답: ${msg}`);
        }
        throw new Error(msg);
      }

      setError(null);
      const blob = await res.blob();
      setGlbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
      setModelVersion((v) => v + 1);
      setGlbSource("general");
      setProgress(100);
      setLoadingFadeOut(true);
      setPhase("segment");
    } catch (e) {
      clearProgressTimer();
      setMeshBusy(false);
      setLoadingFadeOut(false);
      setProgress(0);
      setPhase(parts.length ? "segment" : "idle");
      setError(e instanceof Error ? e.message : "오류가 발생했습니다.");
    }
  };

  const runTextGeneration = async () => {
    const p = textPrompt.trim();
    if (!p || textGenBusy) return;
    const { ok: engineOk, baseUrl } = await checkEngineHealth();
    if (!engineOk) {
      setToastOpen(true);
      setError(buildEngineOfflineMessage(baseUrl));
      return;
    }
    setError(null);
    setTextGenBusy(true);
    setLoadingFadeOut(false);
    setAutoRotate(false);
    startGenProgress();
    try {
      const res = await fetch("/api/generate/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: p, enhance_keywords: enhanceKeywords }),
      });
      clearProgressTimer();
      const ct = res.headers.get("content-type") ?? "";
      if (res.ok && (ct.includes("gltf") || ct.includes("model") || ct.includes("octet-stream"))) {
        const blob = await res.blob();
        setGlbUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
        setModelVersion((v) => v + 1);
        setGlbSource("text");
        setProgress(100);
        setLoadingFadeOut(true);
      } else {
        const msg = await readApiErrorMessage(res);
        setProgress(0);
        setTextGenBusy(false);
        setAutoRotate(true);
        setError(msg);
      }
    } catch (e) {
      clearProgressTimer();
      setProgress(0);
      setTextGenBusy(false);
      setAutoRotate(true);
      setError(e instanceof Error ? e.message : "요청 실패");
    }
  };

  const runTextureGeneration = async () => {
    if (!textureFile || textureGenBusy) return;
    const { ok: engineOk, baseUrl } = await checkEngineHealth();
    if (!engineOk) {
      setToastOpen(true);
      setError(buildEngineOfflineMessage(baseUrl));
      return;
    }
    setError(null);
    setTextureGenBusy(true);
    setLoadingFadeOut(false);
    setAutoRotate(false);
    startGenProgress();
    const fd = new FormData();
    fd.append("model", textureFile, textureFile.name);
    fd.append("instructions", textureInstructions);
    try {
      const res = await fetch("/api/generate/texture", { method: "POST", body: fd });
      clearProgressTimer();
      const ct = res.headers.get("content-type") ?? "";
      if (res.ok && (ct.includes("gltf") || ct.includes("model") || ct.includes("octet-stream"))) {
        const blob = await res.blob();
        setGlbUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
        setModelVersion((v) => v + 1);
        setGlbSource("texture");
        setProgress(100);
        setLoadingFadeOut(true);
      } else {
        const msg = await readApiErrorMessage(res);
        setProgress(0);
        setTextureGenBusy(false);
        setAutoRotate(true);
        setError(msg);
      }
    } catch (e) {
      clearProgressTimer();
      setProgress(0);
      setTextureGenBusy(false);
      setAutoRotate(true);
      setError(e instanceof Error ? e.message : "요청 실패");
    }
  };

  const handleLoadingFadeOutComplete = useCallback(() => {
    setMeshBusy(false);
    setTextGenBusy(false);
    setTextureGenBusy(false);
    setDirectLoRABusy(false);
    setLoadingFadeOut(false);
    setAutoRotate(true);
  }, []);

  const runDirectLoRAGenerate = async (which: "vehicle" | "building") => {
    const file = which === "vehicle" ? vehicleLoRAFile : buildingLoRAFile;
    const urlField = which === "vehicle" ? vehicleLoRAUrl : buildingLoRAUrl;
    if (!file && !urlField.trim()) {
      setError("이미지 파일을 선택하거나 이미지 URL을 입력하세요.");
      return;
    }
    if (directLoRABusy) return;

    setError(null);
    setDirectLoRABusy(true);
    setLoadingFadeOut(false);
    setAutoRotate(false);
    startGenProgress();

    const fd = new FormData();
    if (file) {
      fd.append("image", file, file.name);
    } else {
      fd.append("image_url", urlField.trim());
    }
    fd.append("response_mode", "inline");

    try {
      const res = await fetch("/api/generate-3d", {
        method: "POST",
        body: fd,
      });
      clearProgressTimer();

      if (!res.ok) {
        const msg = await readApiErrorMessage(res);
        throw new Error(msg);
      }

      const blob = await res.blob();
      if (blob.size < 64) {
        throw new Error("응답이 너무 작습니다. 엔진 로그를 확인하세요.");
      }
      const head4 = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
      const isGlb =
        head4[0] === 0x67 && head4[1] === 0x6c && head4[2] === 0x54 && head4[3] === 0x46;
      if (!isGlb) {
        const headText = await blob.slice(0, 800).text();
        if (headText.trimStart().startsWith("{")) {
          let msg = "서버가 JSON을 반환했습니다.";
          try {
            const j = JSON.parse(headText) as { detail?: unknown };
            if (typeof j.detail === "string") msg = j.detail;
          } catch {
            /* ignore parse errors */
          }
          throw new Error(msg);
        }
        throw new Error(
          "응답이 GLB가 아닙니다. 포트(8000 vs 8001)·URL·CORS를 확인하세요.",
        );
      }

      setGlbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
      setModelVersion((v) => v + 1);
      setGlbSource(which);
      setProgress(100);
      setLoadingFadeOut(true);
    } catch (e) {
      clearProgressTimer();
      setProgress(0);
      setDirectLoRABusy(false);
      setAutoRotate(true);
      const m = e instanceof Error ? e.message : "Request failed";
      if (m.includes("Failed to fetch") || m.includes("NetworkError")) {
        setError(
          `${m}\n— This is usually a browser networking issue. Make sure the engine is running and reachable (try /api/engine-health).`,
        );
      } else {
        setError(m);
      }
    }
  };

  const stepperPhase: PipelinePhase =
    meshBusy || loadingFadeOut ? "mesh" : analyzeBusy ? "analyze" : parts.length ? "segment" : "idle";

  const glassPanel =
    "rounded-2xl border border-cyan-400/15 bg-gradient-to-b from-white/[0.07] to-white/[0.02] p-px shadow-[0_0_40px_rgba(0,212,255,0.1)] backdrop-blur-xl";

  const electricBtn =
    "relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-2xl py-3.5 text-sm font-semibold text-white shadow-[0_0_44px_rgba(0,212,255,0.35)] backdrop-blur-md transition disabled:cursor-not-allowed disabled:opacity-40";
  const electricBtnBg = {
    background: "linear-gradient(125deg, #0090ff 0%, #00d4ff 42%, #3b82f6 100%)",
  };

  const modeLocked = generationOverlayBusy || analyzeBusy;

  const engineCaption = useMemo(() => {
    if (mode === "image") {
      if (glbSource === "vehicle") return "TripoSR · Vehicle LoRA (POST /generate-3d)";
      if (glbSource === "building") return "TripoSR · Building LoRA (POST /generate-3d)";
      return "TripoSR · Multi-view fusion";
    }
    if (mode === "text") return "Text→3D (엔진 연동 시)";
    return "AI Texture (엔진 연동 시)";
  }, [mode, glbSource]);

  const downloadName = useMemo(() => {
    if (mode === "image" && glbSource === "vehicle") return "origin-real-vehicle-lora.glb";
    if (mode === "image" && glbSource === "building") return "origin-real-building-lora.glb";
    if (mode === "image") return "origin-real-image.glb";
    if (mode === "text") return "origin-real-text.glb";
    return "origin-real-textured.glb";
  }, [mode, glbSource]);

  return (
    <div className="flex min-h-screen flex-col bg-[#050505]">
      <MeshToast
        open={toastOpen}
        message={buildEngineOfflineMessage(engineDisplayUrl)}
        onDismiss={() => setToastOpen(false)}
        durationMs={14000}
      />
      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-white/[0.06] bg-[#060608]/98 lg:w-[min(100%,460px)] lg:border-r lg:shadow-[4px_0_48px_rgba(0,0,0,0.45)]">
          <div className="sidebar-scroll flex max-h-[58vh] flex-1 flex-col gap-5 overflow-y-auto p-5 sm:max-h-none sm:p-7 lg:max-h-none">
            <GenerationModeTabs mode={mode} onModeChange={setMode} disabled={modeLocked} />

            {mode === "image" ? (
              <>
                <DashboardPipelineTabs
                  tab={imagePipelineTab}
                  onTabChange={setImagePipelineTab}
                  disabled={modeLocked}
                />

                {imagePipelineTab === "general" ? (
                  <>
                    <div className={glassPanel}>
                      <div className="rounded-[0.95rem] bg-[#050508]/85 p-4">
                        <MultiViewUploadZone
                          views={views}
                          previewUrls={previewUrls}
                          onViewChange={setView}
                          disabled={meshBusy || analyzeBusy}
                        />
                      </div>
                    </div>

                    <PipelineStepper phase={stepperPhase} />

                    {(analyzeBusy || (progress > 0 && progress < 100 && phase === "analyze")) && (
                      <div className="rounded-xl border border-cyan-400/20 bg-black/40 px-3 py-2.5 backdrop-blur-md">
                        <div className="mb-1 flex justify-between text-[10px] font-medium uppercase tracking-wider text-cyan-200/90">
                          <span>분석 진행</span>
                          <span>{Math.round(progress)}%</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-white/10 shadow-inner">
                          <motion.div
                            className="h-full rounded-full bg-gradient-to-r from-sky-500 via-cyan-400 to-blue-500 shadow-[0_0_18px_rgba(0,212,255,0.6)]"
                            initial={{ width: 0 }}
                            animate={{ width: `${progress}%` }}
                            transition={{ type: "spring", stiffness: 120, damping: 22 }}
                          />
                        </div>
                      </div>
                    )}

                    {parts.length > 0 && phase === "segment" && !analyzeBusy ? (
                      <PartReviewPanel
                        parts={parts}
                        accepted={accepted}
                        busy={analyzeBusy}
                        onToggleAccept={(id) => setAccepted((a) => ({ ...a, [id]: a[id] === false }))}
                        onRegeneratePart={() => {
                          const s = analyzeSeed + 1 + Math.floor(Math.random() * 999);
                          setAnalyzeSeed(s);
                          void runAnalyze(s);
                        }}
                        onRegenerateAll={() => {
                          const s = Date.now() % 2_000_000_000;
                          setAnalyzeSeed(s);
                          void runAnalyze(s);
                        }}
                      />
                    ) : null}

                    <div className={`${glassPanel} p-4`}>
                      <p className="text-[11px] leading-relaxed text-zinc-500">
                        General: Next <span className="text-zinc-400">/api/analyze</span>,{" "}
                        <span className="text-zinc-400">/api/generate/image</span> → TripoSR{" "}
                        <span className="text-zinc-400">/generate/image</span> (멀티뷰·부품 검토)
                      </p>
                    </div>

                    <motion.button
                      type="button"
                      onClick={() => {
                        const s = analyzeSeed || Date.now() % 2_000_000_000;
                        setAnalyzeSeed(s);
                        void runAnalyze(s);
                      }}
                      disabled={analyzeBusy || generationOverlayBusy || !views.front}
                      className={electricBtn}
                      style={electricBtnBg}
                      whileTap={{ scale: analyzeBusy || generationOverlayBusy ? 1 : 0.98 }}
                    >
                      <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/25 to-transparent" />
                      {analyzeBusy ? (
                        <Loader2 className="relative h-4 w-4 animate-spin" />
                      ) : (
                        <ScanLine className="relative h-4 w-4" strokeWidth={2.2} />
                      )}
                      <span className="relative">1단계: 이미지 분석</span>
                    </motion.button>

                    <motion.button
                      type="button"
                      onClick={() => void runMeshGeneration()}
                      disabled={meshBusy || analyzeBusy || !views.front || parts.length === 0}
                      className={`${electricBtn} border border-white/10`}
                      style={{
                        background: "linear-gradient(125deg, #1d4ed8 0%, #06b6d4 50%, #2563eb 100%)",
                      }}
                      whileTap={{ scale: meshBusy ? 1 : 0.98 }}
                      animate={
                        meshBusy
                          ? {
                              boxShadow: [
                                "0 0 44px rgba(0,212,255,0.4)",
                                "0 0 56px rgba(56,189,248,0.55)",
                                "0 0 44px rgba(0,212,255,0.4)",
                              ],
                            }
                          : {}
                      }
                      transition={meshBusy ? { duration: 1.4, repeat: Infinity, ease: "easeInOut" } : {}}
                    >
                      <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/20 to-transparent" />
                      {meshBusy ? (
                        <Loader2 className="relative h-4 w-4 animate-spin" />
                      ) : (
                        <Shapes className="relative h-4 w-4" strokeWidth={2.2} />
                      )}
                      <span className="relative">{meshBusy ? "메쉬 생성 중…" : "3단계: 메쉬 생성"}</span>
                    </motion.button>
                  </>
                ) : null}

                {imagePipelineTab === "vehicle" ? (
                  <div className={glassPanel}>
                    <div className="rounded-[0.95rem] bg-[#050508]/85 p-4">
                      <DirectLoRAGenerateForm
                        guide={VEHICLE_PIPELINE_GUIDE}
                        file={vehicleLoRAFile}
                        imageUrl={vehicleLoRAUrl}
                        onFileChange={setVehicleLoRAFile}
                        onImageUrlChange={setVehicleLoRAUrl}
                        onSubmit={() => void runDirectLoRAGenerate("vehicle")}
                        busy={directLoRABusy}
                        disabled={generationOverlayBusy && !directLoRABusy}
                      />
                    </div>
                  </div>
                ) : null}

                {imagePipelineTab === "building" ? (
                  <div className={glassPanel}>
                    <div className="rounded-[0.95rem] bg-[#050508]/85 p-4">
                      <DirectLoRAGenerateForm
                        guide={BUILDING_PIPELINE_GUIDE}
                        file={buildingLoRAFile}
                        imageUrl={buildingLoRAUrl}
                        onFileChange={setBuildingLoRAFile}
                        onImageUrlChange={setBuildingLoRAUrl}
                        onSubmit={() => void runDirectLoRAGenerate("building")}
                        busy={directLoRABusy}
                        disabled={generationOverlayBusy && !directLoRABusy}
                      />
                    </div>
                  </div>
                ) : null}
              </>
            ) : null}

            {mode === "text" ? (
              <>
                <TextTo3DPanel
                  prompt={textPrompt}
                  onPromptChange={setTextPrompt}
                  enhanceKeywords={enhanceKeywords}
                  onEnhanceChange={setEnhanceKeywords}
                  disabled={textGenBusy}
                />
                <div className={`${glassPanel} p-4`}>
                  <p className="text-[11px] leading-relaxed text-zinc-500">
                    Text 모드: Replicate{" "}
                    <span className="text-zinc-400">/generate/text</span> — 엔진에{" "}
                    <span className="text-zinc-400">REPLICATE_API_TOKEN</span> +{" "}
                    <span className="text-zinc-400">requirements-text3d.txt</span>
                  </p>
                </div>
                <motion.button
                  type="button"
                  onClick={() => void runTextGeneration()}
                  disabled={textGenBusy || !textPrompt.trim()}
                  className={electricBtn}
                  style={electricBtnBg}
                  whileTap={{ scale: textGenBusy ? 1 : 0.98 }}
                >
                  <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/25 to-transparent" />
                  {textGenBusy ? (
                    <Loader2 className="relative h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="relative h-4 w-4" strokeWidth={2.2} />
                  )}
                  <span className="relative">{textGenBusy ? "생성 요청 중…" : "텍스트로 3D 생성"}</span>
                </motion.button>
              </>
            ) : null}

            {mode === "texture" ? (
              <>
                <TextureModelUpload
                  file={textureFile}
                  previewName={textureFile?.name ?? null}
                  instructions={textureInstructions}
                  onFile={setTextureFile}
                  onInstructionsChange={setTextureInstructions}
                  disabled={textureGenBusy}
                />
                <div className={`${glassPanel} p-4`}>
                  <p className="text-[11px] leading-relaxed text-zinc-500">
                    Texture 모드: <span className="text-zinc-400">/api/generate/texture</span> →{" "}
                    <span className="text-zinc-400">/generate/texture</span>
                  </p>
                </div>
                <motion.button
                  type="button"
                  onClick={() => void runTextureGeneration()}
                  disabled={textureGenBusy || !textureFile}
                  className={electricBtn}
                  style={{
                    background: "linear-gradient(125deg, #7c3aed 0%, #06b6d4 55%, #2563eb 100%)",
                  }}
                  whileTap={{ scale: textureGenBusy ? 1 : 0.98 }}
                >
                  <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/25 to-transparent" />
                  {textureGenBusy ? (
                    <Loader2 className="relative h-4 w-4 animate-spin" />
                  ) : (
                    <Wand2 className="relative h-4 w-4" strokeWidth={2.2} />
                  )}
                  <span className="relative">{textureGenBusy ? "처리 중…" : "AI 텍스처 적용"}</span>
                </motion.button>
              </>
            ) : null}

            {error ? (
              <div className="rounded-xl border border-red-500/25 bg-red-500/[0.08] px-3 py-2.5 text-xs text-red-200 shadow-[0_0_24px_rgba(239,68,68,0.12)] backdrop-blur-md">
                {error}
              </div>
            ) : null}
          </div>
        </aside>

        <section className="relative flex min-h-[320px] flex-1 flex-col bg-gradient-to-br from-[#040408] via-[#080a10] to-[#051020]">
          <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between border-b border-cyan-500/10 bg-black/30 px-4 py-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-md sm:px-6">
            <p className="text-xs font-medium uppercase tracking-[0.22em] text-cyan-200/70">
              Live PBR viewport
            </p>
            <button
              type="button"
              onClick={() => setAutoRotate((v) => !v)}
              className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-1.5 text-xs text-cyan-100 shadow-[0_0_22px_rgba(0,212,255,0.12)] backdrop-blur-md transition hover:border-cyan-300/40 hover:text-white"
            >
              Auto-rotate: {autoRotate ? "on" : "off"}
            </button>
          </div>

          <div className="relative mt-11 flex min-h-[420px] flex-1 lg:min-h-0">
            <motion.div
              key={glbUrl ?? "viewport-empty"}
              className="h-full min-h-[420px] w-full lg:min-h-[calc(100vh-3.5rem-2.75rem)]"
              initial={
                glbUrl ? { opacity: 0.35, filter: "blur(12px)" } : { opacity: 1, filter: "blur(0px)" }
              }
              animate={{ opacity: 1, filter: "blur(0px)" }}
              transition={{ duration: 1.05, ease: [0.22, 1, 0.36, 1] }}
            >
              <PBRViewer
                className="h-full min-h-[420px] w-full"
                glbUrl={glbUrl}
                modelVersion={modelVersion}
                autoRotate={autoRotate}
              />
            </motion.div>

            {glbUrl ? (
              <div className="pointer-events-none absolute bottom-5 right-5 z-[15] flex flex-col items-end gap-2 sm:bottom-7 sm:right-7">
                <div className="pointer-events-auto rounded-xl border border-cyan-400/20 bg-[#0a0e14]/90 px-3 py-2 text-right shadow-[0_0_32px_rgba(0,212,255,0.15)] backdrop-blur-xl">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-200/60">
                    Engine
                  </p>
                  <p className="text-xs font-medium text-zinc-200">{engineCaption}</p>
                </div>
                <a
                  href={glbUrl}
                  download={downloadName}
                  className="pointer-events-auto inline-flex items-center gap-2 rounded-xl border border-cyan-400/35 bg-cyan-500/15 px-4 py-2.5 text-xs font-semibold text-cyan-50 shadow-[0_0_28px_rgba(0,212,255,0.25)] backdrop-blur-md transition hover:bg-cyan-500/25"
                >
                  <Download className="h-3.5 w-3.5" />
                  GLB 다운로드
                </a>
              </div>
            ) : null}

            <GenerationOverlay
              open={generationOverlayBusy}
              progress={progress}
              fadeOut={loadingFadeOut}
              onFadeOutComplete={handleLoadingFadeOutComplete}
              tripoPulse={generationOverlayBusy && !loadingFadeOut}
            />
          </div>
        </section>
      </main>
    </div>
  );
}
