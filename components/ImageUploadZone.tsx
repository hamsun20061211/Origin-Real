"use client";

import { useCallback, useId, useState } from "react";
import { ImagePlus, Upload } from "lucide-react";
import { motion } from "framer-motion";

type ImageUploadZoneProps = {
  file: File | null;
  previewUrl: string | null;
  onFile: (file: File | null) => void;
  disabled?: boolean;
};

export function ImageUploadZone({
  file,
  previewUrl,
  onFile,
  disabled,
}: ImageUploadZoneProps) {
  const id = useId();
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list?.length) return;
      const f = list[0];
      if (!f.type.startsWith("image/")) return;
      onFile(f);
    },
    [onFile],
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
        <ImagePlus className="h-3.5 w-3.5 text-accent" />
        Source image
      </div>
      <motion.label
        htmlFor={id}
        className={`group relative flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-2xl border p-px transition ${
          dragOver
            ? "border-accent/50 shadow-[0_0_32px_rgba(59,130,246,0.25)]"
            : "border-white/[0.12] shadow-[0_0_24px_rgba(59,130,246,0.06)]"
        } ${disabled ? "pointer-events-none opacity-50" : ""}`}
        style={{
          background:
            "linear-gradient(145deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.02) 100%)",
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        animate={dragOver ? { scale: 1.01 } : { scale: 1 }}
        transition={{ type: "spring", stiffness: 420, damping: 28 }}
      >
        <div className="relative flex min-h-[198px] w-full flex-col items-center justify-center rounded-[0.95rem] bg-[#0A0A0A]/55 px-4 py-6 backdrop-blur-xl">
          {previewUrl ? (
            <div className="relative h-40 w-full max-w-[240px] overflow-hidden rounded-xl border border-white/10 shadow-[inset_0_0_0_1px_rgba(59,130,246,0.15)]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewUrl}
                alt="Upload preview"
                className="h-full w-full object-contain transition duration-500 group-hover:scale-[1.02]"
              />
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-2 py-2">
                <p className="truncate text-center text-[10px] text-zinc-400">
                  {file?.name ?? "image"}
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/25 bg-accent/10 shadow-[0_0_24px_rgba(59,130,246,0.2)]">
                <Upload className="h-6 w-6 text-accent-glow" strokeWidth={1.5} />
              </div>
              <p className="text-center text-sm font-medium text-zinc-300">
                드래그 앤 드롭 또는 클릭하여 업로드
              </p>
              <p className="text-center text-[11px] text-zinc-600">PNG, JPG, WebP</p>
            </>
          )}
        </div>
        <input
          id={id}
          type="file"
          accept="image/*"
          className="sr-only"
          disabled={disabled}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </motion.label>
      {file ? (
        <button
          type="button"
          onClick={() => onFile(null)}
          disabled={disabled}
          className="w-full rounded-xl border border-white/10 bg-white/[0.04] py-2 text-xs text-zinc-400 backdrop-blur-md transition hover:border-red-500/30 hover:text-red-300"
        >
          이미지 제거
        </button>
      ) : null}
    </div>
  );
}
