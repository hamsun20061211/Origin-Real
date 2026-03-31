/** 127.0.0.1 ↔ localhost 교차 후보 (Windows 루프백 이슈 완화). */
export function triposrLoopbackBaseCandidates(primary: string): string[] {
  const b = primary.trim().replace(/\/$/, "");
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (x: string) => {
    const y = x.replace(/\/$/, "");
    if (!seen.has(y)) {
      seen.add(y);
      out.push(y);
    }
  };
  add(b);
  try {
    const withProto = b.includes("://") ? b : `http://${b}`;
    const u = new URL(withProto);
    if (u.hostname === "127.0.0.1") {
      u.hostname = "localhost";
      add(u.origin);
    } else if (u.hostname === "localhost") {
      u.hostname = "127.0.0.1";
      add(u.origin);
    }
  } catch {
    /* ignore */
  }
  return out;
}
