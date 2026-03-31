# TripoSR FastAPI (main.py) with Origin Real .tripo-venv + Downloads\TripoSR
#
# Port 8000 in use (WinError 10048):  .\start-engine.ps1 -Port 8001
#   Then set Next.js TRIPOSR_URL=http://127.0.0.1:8001
#
# RTX 50xx (sm_120): if PyTorch warns about CUDA capability, upgrade wheels e.g.
#   .\.tripo-venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
#
param(
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$EngineDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $EngineDir
$VenvPy = Join-Path $RepoRoot ".tripo-venv\Scripts\python.exe"
$DefaultTripo = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads\TripoSR"
if ($env:TRIPOSR_ROOT) {
    $TripoRoot = $env:TRIPOSR_ROOT
} else {
    $TripoRoot = $DefaultTripo
}

if (-not (Test-Path $VenvPy)) {
    Write-Error "Missing venv: $VenvPy`nRun from repo root:`n  .\.tripo-venv\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124`n  .\.tripo-venv\Scripts\pip install -r triposr-server\requirements-tripo-resolve.txt`n  .\.tripo-venv\Scripts\pip install -r triposr-server\requirements.txt"
}
if (-not (Test-Path (Join-Path $TripoRoot "tsr"))) {
    Write-Error "TripoSR not found at $TripoRoot (need tsr\ folder). Set TRIPOSR_ROOT or extract clone to $DefaultTripo"
}

$env:TRIPOSR_ROOT = $TripoRoot
if ($Port -gt 0) {
    $env:PORT = "$Port"
}
if (-not $env:PORT) {
    # 8000 은 다른 앱/이전 uvicorn 에 자주 잡혀 있음 (WinError 10048)
    $env:PORT = "8001"
}
Set-Location $EngineDir
Write-Host "[engine] TRIPOSR_ROOT=$TripoRoot" -ForegroundColor Cyan
Write-Host "[engine] Python=$VenvPy" -ForegroundColor Cyan
Write-Host "[engine] PORT=$($env:PORT)" -ForegroundColor Cyan
& $VenvPy (Join-Path $EngineDir "main.py")
