export type GenerationMode = "image" | "text" | "texture";

export const MODE_LABELS: Record<GenerationMode, string> = {
  image: "Image",
  text: "Text",
  texture: "Texture",
};

/** 서버 `enhance_keywords`와 동기화할 퀄리티 접미사 (클라이언트 미리보기용) */
export const DEFAULT_PBR_QUALITY_SUFFIX =
  ", ultra high-fidelity 3D asset, PBR materials, clean topology, studio lighting, game-ready";

export function buildEnhancedPrompt(userPrompt: string, appendQuality: boolean): string {
  const base = userPrompt.trim();
  if (!appendQuality) return base;
  if (!base) return DEFAULT_PBR_QUALITY_SUFFIX.trim().replace(/^,\s*/, "");
  return `${base}${DEFAULT_PBR_QUALITY_SUFFIX}`;
}
