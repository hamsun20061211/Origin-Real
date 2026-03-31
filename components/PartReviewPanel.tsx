"use client";

import { motion } from "framer-motion";
import { CheckCircle2, RefreshCw, Sparkles } from "lucide-react";
import type { AnalyzedPart } from "@/lib/pipeline-types";

type PartReviewPanelProps = {
  parts: AnalyzedPart[];
  accepted: Record<string, boolean>;
  onToggleAccept: (id: string) => void;
  onRegeneratePart: (id: string) => void;
  onRegenerateAll: () => void;
  busy?: boolean;
};

export function PartReviewPanel({
  parts,
  accepted,
  onToggleAccept,
  onRegeneratePart,
  onRegenerateAll,
  busy,
}: PartReviewPanelProps) {
  return (
    <div className="space-y-3 rounded-2xl border border-[#00D4FF]/12 bg-[#070b12]/80 p-3 shadow-[0_0_28px_rgba(0,212,255,0.06)] backdrop-blur-xl">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-[#00D4FF]" />
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#93c5fd]">
            AI 부품 분석
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={onRegenerateAll}
          className="inline-flex items-center gap-1 rounded-lg border border-cyan-400/35 bg-cyan-400/15 px-2 py-1 text-[10px] font-semibold text-cyan-100 shadow-[0_0_16px_rgba(0,212,255,0.12)] transition hover:bg-cyan-400/25 disabled:opacity-40"
        >
          <RefreshCw className={`h-3 w-3 ${busy ? "animate-spin" : ""}`} />
          전체 재생성
        </button>
      </div>
      <p className="text-[10px] leading-relaxed text-zinc-500">
        각 부위를 검토한 뒤 승인하거나, 해당 줄만 다시 분석할 수 있습니다.
      </p>
      <ul className="max-h-[220px] space-y-2 overflow-y-auto pr-0.5">
        {parts.map((p, idx) => {
          const ok = accepted[p.id] !== false;
          const [bx, by, bw, bh] = p.bbox_norm;
          return (
            <motion.li
              key={p.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              className={`rounded-xl border px-2.5 py-2 ${
                ok
                  ? "border-emerald-500/20 bg-emerald-500/[0.04]"
                  : "border-amber-500/25 bg-amber-500/[0.05]"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-zinc-200">{p.label}</p>
                  <p className="mt-0.5 font-mono text-[9px] text-zinc-500">
                    id:{p.id} · 신뢰도 {(p.confidence * 100).toFixed(0)}% · bbox{" "}
                    {bx.toFixed(2)},{by.toFixed(2)},{bw.toFixed(2)},{bh.toFixed(2)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onToggleAccept(p.id)}
                    className={`inline-flex items-center justify-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-semibold transition ${
                      ok
                        ? "border-emerald-400/35 bg-emerald-500/15 text-emerald-200"
                        : "border-white/10 bg-white/[0.04] text-zinc-400"
                    }`}
                  >
                    <CheckCircle2 className="h-3 w-3" />
                    {ok ? "승인됨" : "승인"}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onRegeneratePart(p.id)}
                    className="inline-flex items-center justify-center gap-1 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-2 py-1 text-[10px] font-medium text-sky-200 transition hover:bg-cyan-400/20"
                  >
                    <RefreshCw className="h-3 w-3" />
                    재생성
                  </button>
                </div>
              </div>
            </motion.li>
          );
        })}
      </ul>
    </div>
  );
}
