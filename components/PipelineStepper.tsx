"use client";

import { motion } from "framer-motion";
import type { PipelinePhase } from "@/lib/pipeline-types";
import { Check, Cpu, Layers, Scan } from "lucide-react";

const STEPS: { phase: PipelinePhase; label: string; sub: string; icon: typeof Scan }[] = [
  { phase: "analyze", label: "이미지 분석", sub: "Image understanding", icon: Scan },
  { phase: "segment", label: "부품 분리", sub: "Segmentation review", icon: Layers },
  { phase: "mesh", label: "메쉬 생성", sub: "TripoSR + fusion", icon: Cpu },
];

function stepIndex(phase: PipelinePhase): number {
  if (phase === "idle") return -1;
  const i = STEPS.findIndex((s) => s.phase === phase);
  return i < 0 ? -1 : i;
}

type PipelineStepperProps = {
  phase: PipelinePhase;
};

export function PipelineStepper({ phase }: PipelineStepperProps) {
  const active = stepIndex(phase);

  return (
    <div className="rounded-2xl border border-cyan-400/20 bg-gradient-to-b from-cyan-400/10 to-transparent p-3 shadow-[0_0_32px_rgba(0,212,255,0.08)] backdrop-blur-xl">
      <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.24em] text-[#7dd3fc]/90">
        Pipeline
      </p>
      <div className="flex flex-col gap-2">
        {STEPS.map((s, i) => {
          const done = active > i;
          const current = active === i;
          const Icon = s.icon;
          return (
            <div key={s.phase} className="flex items-start gap-2.5">
              <div className="relative flex flex-col items-center">
                <motion.div
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-[#00D4FF] shadow-[0_0_20px_rgba(0,212,255,0.15)] ${
                    current
                      ? "border-[#00D4FF]/50 bg-[#00D4FF]/15"
                      : done
                        ? "border-emerald-400/35 bg-emerald-500/10 text-emerald-300"
                        : "border-white/10 bg-white/[0.04] text-zinc-500"
                  }`}
                  animate={current ? { scale: [1, 1.04, 1] } : {}}
                  transition={{ duration: 1.6, repeat: current ? Infinity : 0, ease: "easeInOut" }}
                >
                  {done ? <Check className="h-4 w-4 text-emerald-300" /> : <Icon className="h-4 w-4" />}
                </motion.div>
                {i < STEPS.length - 1 ? (
                  <span
                    className={`my-0.5 block h-6 w-px ${done ? "bg-emerald-500/35" : "bg-white/10"}`}
                  />
                ) : null}
              </div>
              <div className="min-w-0 pt-0.5">
                <p
                  className={`text-xs font-semibold ${current ? "text-white" : done ? "text-zinc-300" : "text-zinc-500"}`}
                >
                  {s.label}
                </p>
                <p className="text-[10px] text-zinc-600">{s.sub}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
