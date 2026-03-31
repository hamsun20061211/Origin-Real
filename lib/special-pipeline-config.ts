/**
 * Vehicle / Building 전용 탭: 브라우저에서 로컬 FastAPI POST /generate-3d 로 직접 전송.
 * 기본은 사용자 요청대로 8000; 엔진이 8001이면 .env.local 에 NEXT_PUBLIC_DIRECT_GENERATE_3D_URL 설정.
 */
const _rawDirect = process.env.NEXT_PUBLIC_DIRECT_GENERATE_3D_URL?.trim();
export const DIRECT_GENERATE_3D_URL = _rawDirect
  ? _rawDirect.replace(/\/$/, "")
  : "http://localhost:8000/generate-3d";

export type ImagePipelineTab = "general" | "vehicle" | "building";

export const PIPELINE_TAB_LABELS: Record<ImagePipelineTab, string> = {
  general: "General",
  vehicle: "Vehicle Special",
  building: "Building Special",
};

export type PipelineGuide = {
  headline: string;
  bullets: string[];
};

export const VEHICLE_PIPELINE_GUIDE: PipelineGuide = {
  headline: "차량 이미지 가이드",
  bullets: [
    "정측면(운전석 반대쪽 전체 실루엣) 한 장이 가장 안정적입니다. 휠·루프라인이 잘 보이게 촬영하세요.",
    "과한 광각·최광면은 비율이 왜곡되기 쉽습니다. 가능하면 줌으로 평행에 가깝게 찍어주세요.",
    "배경은 단순할수록 배경 제거(rembg) 품질이 좋아집니다. 야간 네온 반사만 과하면 메쉬가 지저분해질 수 있어요.",
    "한 대만 프레임에 담기: 다른 차량 일부가 겹치면 3D가 섞여 나올 수 있습니다.",
  ],
};

export const BUILDING_PIPELINE_GUIDE: PipelineGuide = {
  headline: "건물 이미지 가이드",
  bullets: [
    "정면 파사드가 수직에 가깝게(수평선 평행) 보이도록 촬영하면 창·층선이 살아납니다.",
    "상단이 잘리지 않게 전체 높이가 들어오게 하거나, 최소한 주요 코너·입구 기준점이 보이게 해주세요.",
    "투시가 강한 상단만 보는 앵글은 기하가 납작해지기 쉽습니다. 약간 떨어진 정면~반측면이 무난합니다.",
    "전경 나무·간판이 과하면 그물망 형태가 생길 수 있어, 건물 본체가 차지하는 비율을 크게 하는 편이 좋습니다.",
  ],
};

export function directEngineOrigin(): string {
  try {
    const u = new URL(DIRECT_GENERATE_3D_URL);
    return `${u.protocol}//${u.host}`;
  } catch {
    return "http://localhost:8000";
  }
}
