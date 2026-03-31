/**
 * Photogrammetry API (COLMAP) — 기본 포트 8002. TripoSR 엔진(8001)과 별도 터미널.
 *
 * 사전: COLMAP 설치 + photogrammetry-server 에서 pip install -r requirements.txt
 */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const repoRoot = path.join(__dirname, "..");
const cwd = path.join(repoRoot, "photogrammetry-server");
const isWin = process.platform === "win32";

function parseEnvLines(text, into) {
  let s = text;
  if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
  for (let line of s.split("\n")) {
    line = line.replace(/\r$/, "").trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue;
    let val = line.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    into[key] = val;
  }
}

function mergeRepoDotEnvVars() {
  const acc = {};
  for (const name of [".env", ".env.local"]) {
    const p = path.join(repoRoot, name);
    try {
      if (fs.existsSync(p)) parseEnvLines(fs.readFileSync(p, "utf8"), acc);
    } catch (e) {
      console.warn("[photogrammetry] .env 읽기 실패 (무시):", e.message || e);
    }
  }
  return acc;
}

function pythonCandidates() {
  const list = [];
  const tripo = isWin
    ? path.join(repoRoot, ".tripo-venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".tripo-venv", "bin", "python3");
  if (fs.existsSync(tripo)) list.push(tripo);
  const local = isWin
    ? path.join(cwd, ".venv", "Scripts", "python.exe")
    : path.join(cwd, ".venv", "bin", "python3");
  if (fs.existsSync(local)) list.push(local);
  const fallbacks = isWin ? ["python", "py", "python3"] : ["python3", "python"];
  const seen = new Set();
  const out = [];
  for (const c of [...list, ...fallbacks]) {
    const k = c.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(c);
  }
  return out;
}

const fileVars = mergeRepoDotEnvVars();
const env = { ...fileVars, ...process.env };
if (env.PYTHONUNBUFFERED == null || String(env.PYTHONUNBUFFERED).trim() === "") {
  env.PYTHONUNBUFFERED = "1";
}
if (!env.PHOTOGRAMMETRY_PORT) {
  env.PHOTOGRAMMETRY_PORT = "8002";
}

const candidates = pythonCandidates();
const port = env.PHOTOGRAMMETRY_PORT;
const args = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", String(port)];

console.log("[photogrammetry] cwd=%s", cwd);
console.log(
  "[photogrammetry] http://0.0.0.0:%s  (TripoSR 과 별도; COLMAP PATH 또는 COLMAP_EXECUTABLE)",
  port,
);
console.log("[photogrammetry] pip install -r photogrammetry-server/requirements.txt 권장");

function trySpawn(i) {
  if (i >= candidates.length) {
    console.error(
      "[photogrammetry] Python 을 찾지 못했습니다. .tripo-venv 또는 photogrammetry-server/.venv 를 만드세요.",
    );
    process.exit(1);
  }
  const cmd = candidates[i];
  const isAbs =
    path.isAbsolute(cmd) ||
    (!isWin && cmd.startsWith("/")) ||
    (isWin && /^[A-Za-z]:\\/.test(cmd));
  const spawnCmd = cmd === "py" && !isAbs ? "py" : cmd;
  const spawnArgs = cmd === "py" && !isAbs ? ["-3", ...args] : args;

  if (isAbs || cmd === "py") console.log("[photogrammetry] Python:", spawnCmd);

  const child = spawn(spawnCmd, spawnArgs, {
    cwd,
    stdio: "inherit",
    shell: false,
    env,
  });

  child.on("error", (err) => {
    if (err && err.code === "ENOENT") trySpawn(i + 1);
    else {
      console.error(err);
      process.exit(1);
    }
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}

trySpawn(0);
