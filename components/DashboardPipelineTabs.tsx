"use client";

import { motion } from "framer-motion";
import { Building2, Car, Layers } from "lucide-react";
import type { ImagePipelineTab } from "@/lib/special-pipeline-config";
import { PIPELINE_TAB_LABELS } from "@/lib/special-pipeline-config";

type DashboardPipelineTabsProps = {
  tab: ImagePipelineTab;
  onTabChange: (t: ImagePipelineTab) => void;
  disabled?: boolean;
};

const ORDER: ImagePipelineTab[] = ["general", "vehicle", "building"];

const ICONS = {
  general: Layers,
  vehicle: Car,
  building: Building2,
} as const;

export function DashboardPipelineTabs({ tab, onTabChange, disabled }: DashboardPipelineTabsProps) {
  return (
    <div className="rounded-2xl border border-violet-400/20 bg-black/40 p-1.5 shadow-[0_0_24px_rgba(139,92,246,0.1)] backdrop-blur-xl">
      <div className="grid grid-cols-3 gap-1">
        {ORDER.map((t) => {
          const active = tab === t;
          const Icon = ICONS[t];
          return (
            <motion.button
              key={t}
              type="button"
              disabled={disabled}
              onClick={() => onTabChange(t)}
              className={`relative flex flex-col items-center gap-1 rounded-xl py-2.5 text-[9px] font-semibold uppercase tracking-wider transition sm:text-[10px] ${
                active ? "text-white" : "text-zinc-500 hover:text-zinc-300"
              } ${disabled ? "opacity-40" : ""}`}
              whileTap={{ scale: disabled ? 1 : 0.97 }}
            >
              {active ? (
                <motion.span
                  layoutId="pipelineTabGlow"
                  className="absolute inset-0 rounded-xl border border-violet-400/35 bg-gradient-to-b from-violet-500/25 to-cyan-600/10 shadow-[0_0_18px_rgba(139,92,246,0.22)]"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              ) : null}
              <Icon className="relative z-[1] h-4 w-4" strokeWidth={2} />
              <span className="relative z-[1] text-center leading-tight">{PIPELINE_TAB_LABELS[t]}</span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
