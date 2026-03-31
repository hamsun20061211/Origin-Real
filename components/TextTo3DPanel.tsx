"use client";

import { useMemo, useState } from "react";
import { Sparkles, Type, Wand2 } from "lucide-react";
import { motion } from "framer-motion";
import {
  buildEnhancedPrompt,
  DEFAULT_PBR_QUALITY_SUFFIX,
} from "@/lib/generation-modes";

type TextTo3DPanelProps = {
  prompt: string;
  onPromptChange: (v: string) => void;
  enhanceKeywords: boolean;
  onEnhanceChange: (v: boolean) => void;
  disabled?: boolean;
};

export function TextTo3DPanel({
  prompt,
  onPromptChange,
  enhanceKeywords,
  onEnhanceChange,
  disabled,
}: TextTo3DPanelProps) {
  const [showSuffix, setShowSuffix] = useState(true);

  const preview = useMemo(
    () => buildEnhancedPrompt(prompt, enhanceKeywords),
    [prompt, enhanceKeywords],
  );

  return (
    <div className="space-y-3 rounded-2xl border border-cyan-400/15 bg-[#050810]/90 p-4 shadow-[0_0_32px_rgba(0,212,255,0.06)] backdrop-blur-xl">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200/80">
        <Type className="h-3.5 w-3.5 text-cyan-400" strokeWidth={2.2} />
        Text → 3D
      </div>
      <p className="text-[11px] leading-relaxed text-zinc-500">
        프롬프트를 입력하세요. 켜 두면 PBR·고퀄 키워드가 서버로 함께 전달됩니다. 백엔드는{" "}
        <span className="text-zinc-400">Replicate</span>(Shap-E 등)로 GLB를 받아옵니다 — 엔진 터미널에{" "}
        <span className="font-mono text-zinc-400">REPLICATE_API_TOKEN</span> 이 필요합니다.
      </p>
      <textarea
        value={prompt}
        onChange={(e) => onPromptChange(e.target.value)}
        disabled={disabled}
        rows={5}
        placeholder="예: tactical plate carrier vest, olive drab fabric, molle webbing..."
        className="w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-cyan-400/40 focus:outline-none focus:ring-1 focus:ring-cyan-400/30 disabled:opacity-50"
      />
      <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] p-3 transition hover:border-cyan-400/25">
        <input
          type="checkbox"
          checked={enhanceKeywords}
          onChange={(e) => onEnhanceChange(e.target.checked)}
          disabled={disabled}
          className="mt-1 h-4 w-4 rounded border-white/20 bg-black/50 text-cyan-500 focus:ring-cyan-400/40"
        />
        <div className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-xs font-medium text-zinc-200">
            <Wand2 className="h-3.5 w-3.5 text-cyan-400" />
            High-fidelity · PBR 키워드 자동 추가
          </span>
          <p className="mt-1 text-[10px] leading-relaxed text-zinc-500">
            서버에서 프롬프트 끝에 품질 서픽스를 붙입니다. (미리보기는 아래)
          </p>
        </div>
      </label>
      <button
        type="button"
        onClick={() => setShowSuffix((s) => !s)}
        className="text-[10px] font-medium text-cyan-400/90 hover:text-cyan-300"
      >
        {showSuffix ? "접기" : "펼치기"} · 서픽스 원문
      </button>
      {showSuffix ? (
        <p className="rounded-lg border border-dashed border-cyan-500/20 bg-cyan-500/[0.04] p-2 font-mono text-[9px] leading-relaxed text-zinc-500">
          {DEFAULT_PBR_QUALITY_SUFFIX.trim()}
        </p>
      ) : null}
      <div className="rounded-xl border border-emerald-500/15 bg-emerald-500/[0.04] p-3">
        <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-200/80">
          <Sparkles className="h-3 w-3" />
          전송 미리보기
        </div>
        <p className="max-h-28 overflow-y-auto text-[11px] leading-relaxed text-zinc-300">
          {preview || "(입력 대기)"}
        </p>
      </div>
    </div>
  );
}
