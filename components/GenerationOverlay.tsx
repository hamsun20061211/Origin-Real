"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

export const loadingMessages: string[] = [
  "👨‍🍳 서버에서 3D 모델을 맛있게 굽고 있습니다...",
  "📐 폴리곤들이 제자리를 찾아가는 중입니다. 잠시만요!",
  "🎨 AI 화가가 8K 텍스처를 정성껏 칠하고 있어요.",
  "🔍 현미경으로 디테일을 검수하는 중입니다...",
  "🚀 현실보다 더 리얼한 데이터를 로딩 중입니다.",
];

function pickRandomMessage(exclude: string): string {
  if (loadingMessages.length <= 1) return loadingMessages[0] ?? "";
  let next = loadingMessages[Math.floor(Math.random() * loadingMessages.length)] ?? "";
  let guard = 0;
  while (next === exclude && guard < 12) {
    next = loadingMessages[Math.floor(Math.random() * loadingMessages.length)] ?? "";
    guard += 1;
  }
  return next;
}

function useTypewriter(text: string, msPerChar = 26) {
  const [out, setOut] = useState("");
  useEffect(() => {
    setOut("");
    if (!text) return;
    let i = 0;
    const t = window.setInterval(() => {
      i += 1;
      setOut(text.slice(0, i));
      if (i >= text.length) window.clearInterval(t);
    }, msPerChar);
    return () => window.clearInterval(t);
  }, [text, msPerChar]);
  return out;
}

function isTextureSparkleMessage(msg: string) {
  return msg.includes("8K") || msg.includes("텍스처");
}

function LoadingParticles({ intense }: { intense: boolean }) {
  const particles = useMemo(
    () =>
      Array.from({ length: intense ? 40 : 20 }, (_, i) => ({
        id: i,
        angle: (Math.PI * 2 * i) / (intense ? 40 : 20) + Math.random() * 0.4,
        dist: 40 + Math.random() * 100,
        delay: Math.random() * 2.2,
        duration: 3.2 + Math.random() * 3.5,
        size: intense ? 2 + Math.random() * 2 : 1 + Math.random(),
      })),
    [intense],
  );

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl">
      {particles.map((p) => (
        <motion.span
          key={p.id}
          className="absolute left-1/2 top-1/2 rounded-full bg-sky-300 shadow-[0_0_14px_rgba(56,189,248,0.95),0_0_28px_rgba(59,130,246,0.45)]"
          style={{
            width: p.size,
            height: p.size,
            marginLeft: -p.size / 2,
            marginTop: -p.size / 2,
          }}
          initial={{ opacity: 0, scale: 0, x: 0, y: 0 }}
          animate={{
            opacity: [0, 1, 0.85, 0],
            scale: [0, 1, 0.7, 0.2],
            x: [0, Math.cos(p.angle) * p.dist * 0.5, Math.cos(p.angle) * p.dist],
            y: [0, Math.sin(p.angle) * p.dist * 0.45 - 20, Math.sin(p.angle) * p.dist - 45],
          }}
          transition={{
            duration: p.duration,
            repeat: Infinity,
            ease: "easeInOut",
            delay: p.delay,
          }}
        />
      ))}
    </div>
  );
}

function RotatingMeshGlyph() {
  return (
    <div className="relative flex h-[4.5rem] w-[4.5rem] items-center justify-center">
      <div className="absolute h-11 w-11 animate-[spin_7s_linear_infinite] rounded-md border-2 border-accent/70 shadow-[0_0_28px_rgba(59,130,246,0.55),inset_0_0_20px_rgba(59,130,246,0.12)]" />
      <div className="absolute h-9 w-9 animate-[spin_5s_linear_infinite_reverse] rounded-sm border border-sky-400/50 shadow-[0_0_22px_rgba(56,189,248,0.4)]" />
      <div className="absolute h-2 w-2 rounded-full bg-accent shadow-[0_0_12px_#60a5fa]" />
    </div>
  );
}

export type GenerationOverlayProps = {
  open: boolean;
  progress: number;
  fadeOut?: boolean;
  onFadeOutComplete?: () => void;
  /** 하단 안내 문구 */
  footerText?: string;
  /** Tripo 스타일 에너지 펄스 (생성 중) */
  tripoPulse?: boolean;
};

const DEFAULT_FOOTER =
  "로컬 TripoSR 엔진이 메쉬를 구워 내고 있습니다. 완료되면 뷰가 부드럽게 열립니다.";

export function GenerationOverlay({
  open,
  progress,
  fadeOut = false,
  onFadeOutComplete,
  footerText = DEFAULT_FOOTER,
  tripoPulse = false,
}: GenerationOverlayProps) {
  const [message, setMessage] = useState(() => pickRandomMessage(""));
  const typed = useTypewriter(message);
  const fadeNotified = useRef(false);
  const typingDone = typed.length >= message.length && message.length > 0;

  useEffect(() => {
    if (!open) return;
    setMessage(pickRandomMessage(""));
    const id = window.setInterval(() => {
      setMessage((prev) => pickRandomMessage(prev));
    }, 5000);
    return () => window.clearInterval(id);
  }, [open]);

  useEffect(() => {
    if (!fadeOut) fadeNotified.current = false;
  }, [fadeOut]);

  const pct = Math.min(100, Math.max(0, Math.round(progress)));
  const textureSparkle = isTextureSparkleMessage(message);

  if (!open) return null;

  return (
    <motion.div
      className={`absolute inset-0 z-20 flex items-center justify-center p-4 sm:p-6 ${fadeOut ? "pointer-events-none" : ""}`}
      initial={{ opacity: 1 }}
      animate={{ opacity: fadeOut ? 0 : 1 }}
      transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      onAnimationComplete={() => {
        if (fadeOut && !fadeNotified.current) {
          fadeNotified.current = true;
          onFadeOutComplete?.();
        }
      }}
    >
      <div className="absolute inset-0 bg-[#050508]/72 backdrop-blur-md" />

      <motion.div
        className="relative z-10 w-full max-w-lg overflow-hidden rounded-3xl border border-white/[0.14] bg-gradient-to-b from-white/[0.09] to-white/[0.02] p-px shadow-[0_0_60px_rgba(59,130,246,0.12),0_24px_80px_rgba(0,0,0,0.55)]"
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={
          tripoPulse && !fadeOut
            ? { opacity: 1, y: 0, scale: [1, 1.018, 1] }
            : { opacity: 1, y: 0, scale: 1 }
        }
        transition={
          tripoPulse && !fadeOut
            ? { duration: 1.35, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0.55, ease: [0.22, 1, 0.36, 1] }
        }
      >
        <div className="relative rounded-[1.4rem] bg-[#0a0a0f]/88 px-6 py-8 backdrop-blur-2xl sm:px-8 sm:py-10">
          <LoadingParticles intense={textureSparkle} />

          <div className="relative z-[1] flex flex-col items-center gap-6">
            <RotatingMeshGlyph />

            <div className="relative min-h-[4.5rem] w-full px-1 text-center">
              <p
                className="text-base font-medium leading-relaxed tracking-tight text-zinc-100 sm:text-lg"
                style={{
                  textShadow:
                    "0 0 24px rgba(59, 130, 246, 0.45), 0 0 48px rgba(59, 130, 246, 0.2), 0 0 2px rgba(255,255,255,0.15)",
                }}
              >
                {typed}
                <span className="relative ml-0.5 inline-block w-2 align-middle">
                  <AnimatePresence mode="wait">
                    {typingDone ? (
                      <motion.span
                        key="rest"
                        className="absolute left-0 top-1/2 block h-[1em] w-0.5 -translate-y-1/2 rounded-sm bg-accent/30"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 0.35 }}
                      />
                    ) : (
                      <motion.span
                        key="blink"
                        className="absolute left-0 top-1/2 block h-[1em] w-0.5 -translate-y-1/2 rounded-sm bg-accent shadow-[0_0_12px_#3b82f6]"
                        initial={{ opacity: 1 }}
                        animate={{ opacity: [1, 0.15, 1] }}
                        transition={{ duration: 0.85, repeat: Infinity }}
                      />
                    )}
                  </AnimatePresence>
                </span>
              </p>
            </div>

            <div className="w-full space-y-3">
              <div className="flex items-end justify-between gap-4">
                <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">
                  Origin Real
                </span>
                <span className="font-mono text-2xl font-semibold tabular-nums text-sky-300 drop-shadow-[0_0_12px_rgba(56,189,248,0.5)]">
                  {pct}%
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-zinc-800/90 ring-1 ring-white/[0.06]">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-accent via-sky-400 to-cyan-300 shadow-[0_0_20px_rgba(59,130,246,0.5)]"
                  initial={false}
                  animate={{ width: `${pct}%` }}
                  transition={{ type: "spring", stiffness: 120, damping: 22 }}
                />
              </div>
              <div className="flex gap-2 pt-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="skeleton-shimmer h-2 flex-1 rounded-md opacity-50"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>

            <p className="max-w-sm text-center text-[11px] leading-relaxed text-zinc-500">
              {footerText}
            </p>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
