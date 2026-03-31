/**
 * Next.js(dev) + TripoSR(engine) 를 한 터미널에서 같이 실행합니다.
 * 3D 생성이 "Local Engine Offline" 이면 보통 엔진(8001) 미기동이므로 이 스크립트 사용을 권장합니다.
 *
 * 사용: 프로젝트 루트에서  npm run dev:full
 * 종료: Ctrl+C (양쪽 프로세스 종료 시도)
 */
const { spawn } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const isWin = process.platform === "win32";

/**
 * Windows + Node 22+: `spawn("npm.cmd", …, { shell: false })` 는 EINVAL( spawn EINVAL ) 로 실패하는 경우가 많음.
 * cmd 셸을 통해 `npm run …` 실행.
 */
function runNpmScript(script) {
  if (isWin) {
    return spawn(`npm run ${script}`, {
      cwd: root,
      stdio: "inherit",
      env: process.env,
      shell: true,
    });
  }
  return spawn("npm", ["run", script], {
    cwd: root,
    stdio: "inherit",
    env: process.env,
    shell: false,
  });
}

const dev = runNpmScript("dev");
const engine = runNpmScript("engine");

let shuttingDown = false;

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const c of [dev, engine]) {
    try {
      if (c && !c.killed) {
        if (isWin) {
          spawn("taskkill", ["/pid", String(c.pid), "/T", "/F"], {
            stdio: "ignore",
            shell: true,
          });
        } else {
          c.kill("SIGTERM");
        }
      }
    } catch (_) {
      /* ignore */
    }
  }
  setTimeout(() => process.exit(code ?? 0), 500);
}

dev.on("exit", (code) => {
  if (!shuttingDown) {
    console.error(`\n[dev-stack] next dev 종료 (코드 ${code}). 엔진도 중지합니다.`);
    shutdown(code ?? 1);
  }
});

engine.on("exit", (code) => {
  if (!shuttingDown) {
    console.error(
      `\n[dev-stack] TripoSR 엔진 종료 (코드 ${code}). 웹만 켜진 상태에서는 3D 생성이 안 됩니다.\n` +
        "  TripoSR 경로·venv·로그를 확인한 뒤 다시 npm run dev:full 하세요.\n" +
        "  (UI만 보려면 npm run engine:stub + npm run dev)\n",
    );
    shutdown(code ?? 1);
  }
});

process.on("SIGINT", () => {
  console.log("\n[dev-stack] 중지 중…");
  shutdown(0);
});
process.on("SIGTERM", () => shutdown(0));

console.log(
  "[dev-stack] Next.js + TripoSR 엔진 동시 기동 (엔진 로딩은 수 분 걸릴 수 있음). 브라우저는 터미널에 나온 localhost 주소로 접속하세요.\n",
);
