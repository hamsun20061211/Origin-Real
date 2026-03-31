"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";

type ToastProps = {
  open: boolean;
  message: string;
  onDismiss: () => void;
  durationMs?: number;
};

export function MeshToast({ open, message, onDismiss, durationMs = 6200 }: ToastProps) {
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(t);
  }, [open, durationMs, onDismiss]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="pointer-events-none fixed bottom-6 left-1/2 z-[100] w-[min(92vw,420px)] -translate-x-1/2 px-4 sm:left-auto sm:right-8 sm:translate-x-0"
          initial={{ opacity: 0, y: 16, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.98 }}
          transition={{ type: "spring", stiffness: 380, damping: 28 }}
        >
          <div
            className="pointer-events-auto flex items-start gap-3 rounded-2xl border border-amber-500/25 bg-[#0c0c10]/85 p-4 shadow-[0_0_40px_rgba(245,158,11,0.12),0_16px_48px_rgba(0,0,0,0.5)] backdrop-blur-xl"
            role="alert"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-amber-500/30 bg-amber-500/10">
              <AlertTriangle className="h-5 w-5 text-amber-400" strokeWidth={1.75} />
            </div>
            <div className="min-w-0 flex-1 pt-0.5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200/90">
                Engine
              </p>
              <p className="mt-1 whitespace-pre-line text-sm leading-snug text-zinc-100">
                {message}
              </p>
            </div>
            <button
              type="button"
              onClick={onDismiss}
              className="shrink-0 rounded-lg p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
