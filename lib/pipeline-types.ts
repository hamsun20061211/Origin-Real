export type ViewKey = "front" | "back" | "left" | "right";

export type PipelinePhase = "idle" | "analyze" | "segment" | "mesh";

export type AnalyzedPart = {
  id: string;
  label: string;
  confidence: number;
  bbox_norm: [number, number, number, number];
};

export type AnalyzeResponse = {
  parts: AnalyzedPart[];
  image_size?: { w: number; h: number };
  method?: string;
};

export const VIEW_ORDER: ViewKey[] = ["front", "back", "left", "right"];

export const VIEW_LABELS: Record<ViewKey, { title: string; hint: string }> = {
  front: { title: "Front", hint: "정면" },
  back: { title: "Back", hint: "후면" },
  left: { title: "Left", hint: "좌측" },
  right: { title: "Right", hint: "우측" },
};
