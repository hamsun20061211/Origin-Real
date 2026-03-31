"use client";

import { useCallback, useId, useMemo, useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { motion } from "framer-motion";
import type { ViewKey } from "@/lib/pipeline-types";
import { VIEW_LABELS, VIEW_ORDER } from "@/lib/pipeline-types";

export type MultiViewState = Record<ViewKey, File | null>;

type MultiViewUploadZoneProps = {
  views: MultiViewState;
  previewUrls: Record<ViewKey, string | null>;
  onViewChange: (key: ViewKey, file: File | null) => void;
  disabled?: boolean;
};

export function MultiViewUploadZone({
  views,
  previewUrls,
  onViewChange,
  disabled,
}: MultiViewUploadZoneProps) {
  const baseId = useId();
  const [dragTarget, setDragTarget] = useState<ViewKey | null>(null);

  const handleFile = useCallback(
    (key: ViewKey, list: FileList | null) => {
      if (!list?.length) return;
      const f = list[0];
      if (!f.type.startsWith("image/")) return;
      onViewChange(key, f);
    },
    [onViewChange],
  );

  const glassSlot =
    "relative overflow-hidden rounded-xl border border-white/[0.1] bg-gradient-to-br from-white/[0.07] to-white/[0.02] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md";

  const slots = useMemo(() => VIEW_ORDER, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-500">
        <ImagePlus className="h-3.5 w-3.5 text-[#00D4FF]" />
        Multi-view source
      </div>
      <p className="text-[11px] leading-relaxed text-zinc-600">
        정면은 필수입니다. 좌·우·후면을 추가하면 서버에서{" "}
        <span className="text-zinc-400">seamless fusion</span> 후 TripoSR로 보냅니다.
      </p>

      <div className="grid grid-cols-2 gap-2.5 sm:gap-3">
        {slots.map((key) => {
          const id = `${baseId}-${key}`;
          const prev = previewUrls[key];
          const file = views[key];
          const { title, hint } = VIEW_LABELS[key];
          const isDrag = dragTarget === key;

          return (
            <motion.label
              key={key}
              htmlFor={id}
              className={`${glassSlot} group flex min-h-[132px] cursor-pointer flex-col p-2 transition ${
                isDrag
                  ? "border-[#00D4FF]/55 shadow-[0_0_28px_rgba(0,212,255,0.22)]"
                  : "hover:border-[#00D4FF]/25"
              } ${disabled ? "pointer-events-none opacity-45" : ""}`}
              onDragEnter={(e) => {
                e.preventDefault();
                setDragTarget(key);
              }}
              onDragOver={(e) => e.preventDefault()}
              onDragLeave={() => setDragTarget(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDragTarget(null);
                handleFile(key, e.dataTransfer.files);
              }}
              whileTap={{ scale: disabled ? 1 : 0.99 }}
            >
              <div className="mb-1.5 flex items-center justify-between gap-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-[#7dd3fc]">
                  {title}
                </span>
                <span className="text-[9px] text-zinc-500">{hint}</span>
              </div>
              {prev ? (
                <div className="relative flex flex-1 flex-col">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={prev}
                    alt={title}
                    className="mx-auto h-[88px] w-full max-w-[160px] rounded-lg border border-white/10 object-contain"
                  />
                  <p className="mt-1 truncate text-center text-[9px] text-zinc-500">{file?.name}</p>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      onViewChange(key, null);
                    }}
                    disabled={disabled}
                    className="absolute right-0 top-0 rounded-lg border border-white/15 bg-black/55 p-1 text-zinc-300 backdrop-blur-md transition hover:border-red-400/40 hover:text-red-200"
                    aria-label={`${title} 제거`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center gap-1 py-2 text-center">
                  <span className="rounded-lg border border-cyan-400/25 bg-cyan-400/10 px-2 py-1 text-[9px] font-medium text-cyan-100">
                    드롭 또는 클릭
                  </span>
                  <span className="text-[9px] text-zinc-600">PNG · JPG · WebP</span>
                </div>
              )}
              <input
                id={id}
                type="file"
                accept="image/*"
                className="sr-only"
                disabled={disabled}
                onChange={(e) => handleFile(key, e.target.files)}
              />
            </motion.label>
          );
        })}
      </div>
    </div>
  );
}
