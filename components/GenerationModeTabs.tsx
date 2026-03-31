"use client";

import { motion } from "framer-motion";
import { Box, ImageIcon, Type } from "lucide-react";
import type { GenerationMode } from "@/lib/generation-modes";
import { MODE_LABELS } from "@/lib/generation-modes";

type GenerationModeTabsProps = {
  mode: GenerationMode;
  onModeChange: (m: GenerationMode) => void;
  disabled?: boolean;
};

const MODES: GenerationMode[] = ["image", "text", "texture"];

const ICONS = {
  image: ImageIcon,
  text: Type,
  texture: Box,
} as const;

export function GenerationModeTabs({ mode, onModeChange, disabled }: GenerationModeTabsProps) {
  return (
    <div className="rounded-2xl border border-cyan-400/20 bg-black/35 p-1.5 shadow-[0_0_28px_rgba(0,212,255,0.08)] backdrop-blur-xl">
      <div className="grid grid-cols-3 gap-1">
        {MODES.map((m) => {
          const active = mode === m;
          const Icon = ICONS[m];
          return (
            <motion.button
              key={m}
              type="button"
              disabled={disabled}
              onClick={() => onModeChange(m)}
              className={`relative flex flex-col items-center gap-1 rounded-xl py-2.5 text-[10px] font-semibold uppercase tracking-wider transition ${
                active
                  ? "text-white"
                  : "text-zinc-500 hover:text-zinc-300"
              } ${disabled ? "opacity-40" : ""}`}
              whileTap={{ scale: disabled ? 1 : 0.97 }}
            >
              {active ? (
                <motion.span
                  layoutId="modeTabGlow"
                  className="absolute inset-0 rounded-xl border border-cyan-400/40 bg-gradient-to-b from-cyan-400/20 to-blue-600/10 shadow-[0_0_20px_rgba(0,212,255,0.2)]"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              ) : null}
              <Icon className="relative z-[1] h-4 w-4" strokeWidth={2} />
              <span className="relative z-[1]">{MODE_LABELS[m]}</span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
