"use client";

import { Loader2, Link2, Upload } from "lucide-react";
import type { PipelineGuide } from "@/lib/special-pipeline-config";
import { DIRECT_GENERATE_3D_URL } from "@/lib/special-pipeline-config";

type DirectLoRAGenerateFormProps = {
  guide: PipelineGuide;
  file: File | null;
  imageUrl: string;
  onFileChange: (f: File | null) => void;
  onImageUrlChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
  disabled?: boolean;
};

export function DirectLoRAGenerateForm({
  guide,
  file,
  imageUrl,
  onFileChange,
  onImageUrlChange,
  onSubmit,
  busy,
  disabled,
}: DirectLoRAGenerateFormProps) {
  const canSubmit = Boolean(file || imageUrl.trim()) && !busy && !disabled;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl border border-violet-400/20 bg-violet-500/[0.06] px-3.5 py-3 backdrop-blur-md">
        <p className="text-[11px] font-semibold text-violet-200/90">{guide.headline}</p>
        <ul className="mt-2 list-inside list-disc space-y-1.5 text-[10px] leading-relaxed text-zinc-400">
          {guide.bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl border border-white/[0.08] bg-black/30 px-3 py-2.5">
        <p className="mb-1 text-[9px] font-medium uppercase tracking-wider text-zinc-500">엔드포인트</p>
        <code className="break-all text-[10px] text-cyan-200/80">{DIRECT_GENERATE_3D_URL}</code>
        <p className="mt-2 text-[10px] text-zinc-500">
          브라우저에서 직접 호출합니다. FastAPI CORS에 이 Next 주소가 허용되어 있어야 합니다.
        </p>
      </div>

      <label className="flex cursor-pointer flex-col gap-2 rounded-xl border border-dashed border-cyan-400/25 bg-black/25 px-3 py-4 transition hover:border-cyan-400/45 hover:bg-black/35">
        <span className="flex items-center gap-2 text-xs font-medium text-cyan-100/90">
          <Upload className="h-4 w-4" />
          이미지 파일
        </span>
        <input
          type="file"
          accept="image/*"
          className="text-[11px] text-zinc-400 file:mr-2 file:rounded-lg file:border-0 file:bg-cyan-500/20 file:px-2 file:py-1 file:text-xs file:text-cyan-100"
          disabled={busy || disabled}
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
        />
        {file ? <p className="text-[10px] text-zinc-500">{file.name}</p> : null}
      </label>

      <div className="flex flex-col gap-1.5">
        <span className="flex items-center gap-2 text-xs font-medium text-zinc-400">
          <Link2 className="h-3.5 w-3.5" />
          또는 이미지 URL (http/https)
        </span>
        <input
          type="url"
          value={imageUrl}
          onChange={(e) => onImageUrlChange(e.target.value)}
          placeholder="https://..."
          disabled={busy || disabled}
          className="rounded-xl border border-white/10 bg-black/40 px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-400/40 focus:outline-none"
        />
        <p className="text-[10px] text-zinc-600">파일을 선택하면 URL은 무시됩니다.</p>
      </div>

      <button
        type="button"
        onClick={onSubmit}
        disabled={!canSubmit}
        className="flex w-full items-center justify-center gap-2 rounded-2xl border border-violet-400/30 bg-gradient-to-r from-violet-600/80 via-fuchsia-600/70 to-cyan-600/80 py-3.5 text-sm font-semibold text-white shadow-[0_0_32px_rgba(139,92,246,0.25)] transition disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        {busy ? "LoRA 파이프라인 생성 중…" : "POST /generate-3d 로 GLB 생성"}
      </button>
    </div>
  );
}
