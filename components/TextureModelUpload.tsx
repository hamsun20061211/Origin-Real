"use client";

import { useCallback, useId, useState } from "react";
import { Box, Trash2, Upload } from "lucide-react";
import { motion } from "framer-motion";

type TextureModelUploadProps = {
  file: File | null;
  previewName: string | null;
  instructions: string;
  onFile: (f: File | null) => void;
  onInstructionsChange: (v: string) => void;
  disabled?: boolean;
};

export function TextureModelUpload({
  file,
  previewName,
  instructions,
  onFile,
  onInstructionsChange,
  disabled,
}: TextureModelUploadProps) {
  const id = useId();
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = useCallback(
    (list: FileList | null) => {
      if (!list?.length) return;
      const f = list[0];
      const name = f.name.toLowerCase();
      if (!name.endsWith(".glb") && f.type !== "model/gltf-binary") {
        return;
      }
      onFile(f);
    },
    [onFile],
  );

  return (
    <div className="space-y-3 rounded-2xl border border-cyan-400/15 bg-[#050810]/90 p-4 shadow-[0_0_32px_rgba(0,212,255,0.06)] backdrop-blur-xl">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200/80">
        <Box className="h-3.5 w-3.5 text-cyan-400" strokeWidth={2.2} />
        AI Texture · GLB 입력
      </div>
      <p className="text-[11px] leading-relaxed text-zinc-500">
        기존 3D 모델(GLB)을 올리면 서버의 `/generate/texture`로 전달됩니다. (엔진 연동 전에는 501 안내)
      </p>

      <motion.label
        htmlFor={id}
        className={`group relative flex min-h-[140px] cursor-pointer flex-col items-center justify-center gap-2 overflow-hidden rounded-xl border border-dashed p-4 transition ${
          dragOver
            ? "border-cyan-400/50 bg-cyan-400/10"
            : "border-white/15 bg-black/30 hover:border-cyan-400/30"
        } ${disabled ? "pointer-events-none opacity-45" : ""}`}
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
      >
        {file ? (
          <div className="flex w-full flex-col items-center gap-2 text-center">
            <p className="text-xs font-medium text-zinc-200">{previewName ?? file.name}</p>
            <p className="text-[10px] text-zinc-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                onFile(null);
              }}
              disabled={disabled}
              className="inline-flex items-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-2 py-1 text-[10px] font-medium text-red-200 hover:bg-red-500/20"
            >
              <Trash2 className="h-3 w-3" />
              제거
            </button>
          </div>
        ) : (
          <>
            <Upload className="h-8 w-8 text-cyan-400/70" strokeWidth={1.5} />
            <p className="text-sm font-medium text-zinc-300">GLB 드래그 앤 드롭</p>
            <p className="text-[10px] text-zinc-600">.glb 전용</p>
          </>
        )}
        <input
          id={id}
          type="file"
          accept=".glb,model/gltf-binary"
          className="sr-only"
          disabled={disabled}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </motion.label>

      <div>
        <label htmlFor={`${id}-inst`} className="mb-1 block text-[10px] font-medium text-zinc-500">
          텍스처 지시문 (선택)
        </label>
        <textarea
          id={`${id}-inst`}
          value={instructions}
          onChange={(e) => onInstructionsChange(e.target.value)}
          disabled={disabled}
          rows={3}
          placeholder="예: 스크래치 메탈릭, 마모된 코듀라, 군용 코요테 탄..."
          className="w-full resize-none rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-400/40 focus:outline-none disabled:opacity-50"
        />
      </div>
    </div>
  );
}
