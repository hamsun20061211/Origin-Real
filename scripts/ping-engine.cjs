/**
 * 엔진(기본 8001)이 실제로 떠 있는지 확인. 프로젝트 루트에서: npm run engine:ping
 */
const fs = require("fs");
const http = require("http");
const path = require("path");

function readTripoUrlFromEnvFiles() {
  const root = path.join(__dirname, "..");
  for (const name of [".env.local", ".env"]) {
    const p = path.join(root, name);
    if (!fs.existsSync(p)) continue;
    const text = fs.readFileSync(p, "utf8");
    for (const line of text.split("\n")) {
      const m = line.match(/^\s*TRIPOSR_URL\s*=\s*(.+)$/);
      if (!m) continue;
      let v = m[1].trim();
      if ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'"))) v = v.slice(1, -1);
      return v.trim();
    }
  }
  return null;
}

const urlArg = process.argv[2];
const base =
  urlArg ||
  process.env.TRIPOSR_URL ||
  readTripoUrlFromEnvFiles() ||
  "http://127.0.0.1:8001";
const u = new URL(base.includes("://") ? base : `http://${base}`);
const port = u.port || 80;
const healthPath = "/health";

const req = http.request(
  {
    hostname: u.hostname,
    port,
    path: healthPath,
    method: "GET",
    family: 4,
    timeout: 5000,
  },
  (res) => {
    console.log(`[engine:ping] ${u.protocol}//${u.hostname}:${port}${healthPath} → HTTP ${res.statusCode}`);
    if (res.statusCode >= 200 && res.statusCode < 500) {
      console.log("→ 엔진이 응답합니다. Next 에서만 Offline 이면 npm run dev 재시작 후 다시 시도하세요.");
    } else {
      console.log("→ 비정상 상태 코드입니다. 엔진 터미널 로그를 확인하세요.");
    }
    res.resume();
    process.exit(res.statusCode >= 200 && res.statusCode < 500 ? 0 : 1);
  },
);

req.on("error", (e) => {
  console.error(`[engine:ping] 연결 실패 (${u.hostname}:${port}): ${e.code || e.message}`);
  console.error("→ 별도 터미널에서 프로젝트 루트로 이동 후: npm run engine");
  console.error("→ 로그에 'Uvicorn running on http://0.0.0.0:8001' 가 보여야 합니다.");
  process.exit(1);
});

req.on("timeout", () => {
  req.destroy();
  console.error("[engine:ping] 타임아웃 — 엔진이 느리거나 방화벽 문제일 수 있습니다.");
  process.exit(1);
});

req.end();
