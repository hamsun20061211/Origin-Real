/**
 * 클라이언트 컴포넌트용 엔진 주소 표시 (Next는 NEXT_PUBLIC_* 만 브라우저에 넣음).
 * 서버의 TRIPOSR_URL 과 같게 두는 것을 권장합니다.
 */
export function getTriposrDisplayHost(): string {
  const raw = (process.env.NEXT_PUBLIC_TRIPOSR_URL || "").trim();
  if (raw) {
    try {
      const withProto = raw.includes("://") ? raw : `http://${raw}`;
      return new URL(withProto).host;
    } catch {
      return raw.replace(/^https?:\/\//i, "");
    }
  }
  return "127.0.0.1:8001";
}
