/**
 * Cross-platform: run TripoSR wrapper (main.py) or health-only stub (minimal_engine.py).
 * Usage: node scripts/run-engine.cjs [--stub]
 *
 * TripoSR 의존성(Pillow 등)은 보통 TripoSR 폴더의 venv 에만 설치되어 있으므로,
 * TRIPOSR_ROOT 가 있으면 그 아래 venv / .venv 의 python 을 먼저 사용합니다.
 */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const stub = process.argv.includes("--stub");
const script = stub ? "minimal_engine.py" : "main.py";
const cwd = path.join(__dirname, "..", "triposr-server");
const isWin = process.platform === "win32";

function venvPythons(rootDir) {
  if (!rootDir || !fs.existsSync(rootDir)) return [];
  const outs = [];
  if (isWin) {
    outs.push(path.join(rootDir, "venv", "Scripts", "python.exe"));
    outs.push(path.join(rootDir, ".venv", "Scripts", "python.exe"));
  } else {
    outs.push(path.join(rootDir, "venv", "bin", "python3"));
    outs.push(path.join(rootDir, "venv", "bin", "python"));
    outs.push(path.join(rootDir, ".venv", "bin", "python3"));
    outs.push(path.join(rootDir, ".venv", "bin", "python"));
  }
  return outs.filter((p) => fs.existsSync(p));
}

/** 우선순위: TRIPOSR_ROOT 의 venv → triposr-server/.venv → PATH 의 python */
function buildPythonCandidates() {
  const list = [];
  const triposrRoot = process.env.TRIPOSR_ROOT;
  if (triposrRoot) {
    list.push(...venvPythons(path.resolve(triposrRoot)));
  }
  list.push(...venvPythons(path.join(__dirname, "..", "triposr-server")));
  const repoRoot = path.join(__dirname, "..");
  const tripoVenvPy = isWin
    ? path.join(repoRoot, ".tripo-venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".tripo-venv", "bin", "python3");
  if (fs.existsSync(tripoVenvPy)) {
    list.push(tripoVenvPy);
  }

  const pathFallbacks = isWin ? ["python", "py", "python3"] : ["python3", "python"];

  const unique = [];
  const seen = new Set();
  for (const c of [...list, ...pathFallbacks]) {
    const key = c.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(c);
  }
  return unique;
}

const candidates = buildPythonCandidates();

const repoRoot = path.join(__dirname, "..");

/**
 * Next.js 는 .env / .env.local 을 읽지만, 이 스크립트는 기본적으로 process.env 만 넘깁니다.
 * TRIPOSR_* 등을 .env.local 에만 적어두면 엔진이 못 받아 dtype/포트 설정이 어긋날 수 있어
 * 레포 루트 .env → .env.local 순으로 읽은 뒤, 항상 process.env 가 우선합니다.
 */
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
  const envPath = path.join(repoRoot, ".env");
  const localPath = path.join(repoRoot, ".env.local");
  try {
    if (fs.existsSync(envPath)) {
      parseEnvLines(fs.readFileSync(envPath, "utf8"), acc);
    }
    if (fs.existsSync(localPath)) {
      parseEnvLines(fs.readFileSync(localPath, "utf8"), acc);
    }
  } catch (e) {
    console.warn("[engine] .env 읽기 실패 (무시):", e.message || e);
  }
  return acc;
}

function hasTsrDir(root) {
  try {
    const tsr = path.join(root, "tsr");
    return fs.existsSync(tsr) && fs.statSync(tsr).isDirectory();
  } catch {
    return false;
  }
}

/** start-engine.ps1 과 같이: Downloads\TripoSR, 레포 TripoSR, 형제 폴더 등 */
function discoverTripoSrRoot() {
  const candidates = [
    path.join(repoRoot, "TripoSR"),
    path.join(repoRoot, "..", "TripoSR"),
  ];
  const home = process.env.USERPROFILE || process.env.HOME;
  if (home) {
    candidates.push(path.join(home, "Downloads", "TripoSR"));
  }
  for (const p of candidates) {
    const abs = path.resolve(p);
    if (hasTsrDir(abs)) return abs;
  }
  return null;
}

function buildEngineEnv() {
  const fileVars = mergeRepoDotEnvVars();
  const env = { ...fileVars, ...process.env };
  if (!env.PORT) {
    env.PORT = "8001";
  }
  // Windows 에서 Python 출력이 한꺼번에만 보여 "멈춘 것처럼" 보이는 것 방지
  if (env.PYTHONUNBUFFERED == null || String(env.PYTHONUNBUFFERED).trim() === "") {
    env.PYTHONUNBUFFERED = "1";
  }

  if (!stub) {
    let root = env.TRIPOSR_ROOT && String(env.TRIPOSR_ROOT).trim();
    if (root) {
      root = path.resolve(root);
      if (!hasTsrDir(root)) {
        console.error(
          "[engine] TRIPOSR_ROOT 에 tsr 폴더가 없습니다:",
          root,
          "\n  git clone https://github.com/VAST-AI-Research/TripoSR.git\n" +
            "  또는 올바른 경로로 set TRIPOSR_ROOT=..."
        );
        process.exit(1);
      }
      env.TRIPOSR_ROOT = root;
    } else {
      const found = discoverTripoSrRoot();
      if (!found) {
        console.error(
          "[engine] TripoSR(tsr) 을 찾지 못했습니다. 다음 중 하나:\n" +
            "  1) git clone https://github.com/VAST-AI-Research/TripoSR.git\n" +
            "  2) 폴더를 " +
            path.join(process.env.USERPROFILE || "%USERPROFILE%", "Downloads", "TripoSR") +
            " 에 두기\n" +
            "  3) 또는: set TRIPOSR_ROOT=C:\\실제\\TripoSR경로\n" +
            "  UI만: npm run engine:stub"
        );
        process.exit(1);
      }
      env.TRIPOSR_ROOT = found;
    }
    console.log("[engine] TRIPOSR_ROOT=%s", env.TRIPOSR_ROOT);
  }

  console.log("[engine] PORT=%s (Next .env.local TRIPOSR_URL 과 맞추세요)", env.PORT);
  console.log(
    "[engine] TRIPOSR_INFER_FP16=%s (미설정 시 main.py 기본 autocast; FP32 는 float32)",
    env.TRIPOSR_INFER_FP16 || "(unset)",
  );
  return env;
}

const engineEnv = buildEngineEnv();

const triposrRoot = !stub ? engineEnv.TRIPOSR_ROOT : "";
if (triposrRoot && venvPythons(path.resolve(triposrRoot)).length === 0) {
  console.log(
    "[engine] TRIPOSR_ROOT 에 venv/.venv 가 없습니다. TripoSR 폴더에서:\n" +
      "  python -m venv venv\n" +
      "  .\\venv\\Scripts\\pip install -r requirements.txt\n" +
      "후 다시 npm run engine 하면 이 venv 가 자동으로 사용됩니다.\n"
  );
}

function trySpawn(i) {
  if (i >= candidates.length) {
    console.error(
      "사용할 Python 을 찾지 못했습니다.\n" +
        "TripoSR 폴더에서 가상환경을 만든 뒤 Pillow 등을 설치하세요:\n" +
        "  cd C:\\Users\\...\\TripoSR-main\n" +
        "  python -m venv venv\n" +
        "  .\\venv\\Scripts\\Activate.ps1\n" +
        "  pip install -r requirements.txt\n" +
        "그 다음 TRIPOSR_ROOT 를 그 폴더로 두고 npm run engine 을 다시 실행하면, 이 스크립트가 venv 의 python 을 자동으로 씁니다."
    );
    process.exit(1);
  }

  const cmd = candidates[i];
  const isAbs =
    path.isAbsolute(cmd) ||
    (!isWin && cmd.startsWith("/")) ||
    (isWin && /^[A-Za-z]:\\/.test(cmd));

  const spawnArgs = cmd === "py" && !isAbs ? ["-3", script] : [script];

  if (isAbs) {
    console.log("[engine] Python:", cmd);
  }
  console.log(
    "[engine] main.py 로딩 중… torch/TripoSR·LoRA·첫 HF 다운로드는 수 분 걸릴 수 있습니다. (오류 시 곧 Traceback)",
  );

  const child = spawn(cmd, spawnArgs, {
    cwd,
    stdio: "inherit",
    shell: false,
    env: engineEnv,
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
