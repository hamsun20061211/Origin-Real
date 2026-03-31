# TencentARC/InstantMesh 클론 + venv + PyTorch(CUDA) + requirements
# README: Python>=3.10, PyTorch>=2.1, CUDA>=12.1 권장
#
# 사용:
#   cd "...\Origin Real\instantmesh-setup"
#   powershell -ExecutionPolicy Bypass -File .\01_install_instantmesh.ps1
#   powershell -ExecutionPolicy Bypass -File .\01_install_instantmesh.ps1 -CudaTag cu121
#
param(
  [string]$InstallDir = (Join-Path $env:USERPROFILE "InstantMesh"),
  [ValidateSet("cu121", "cu124", "cu118")]
  [string]$CudaTag = "cu124"
)

$ErrorActionPreference = "Stop"
$repoUrl = "https://github.com/TencentARC/InstantMesh.git"
$repoPath = Join-Path $InstallDir "InstantMesh"

Write-Host "[1/6] 폴더: $InstallDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Write-Host "[2/6] Git clone" -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $repoPath ".git"))) {
  git clone $repoUrl $repoPath
} else {
  Push-Location $repoPath
  git pull
  Pop-Location
}

$venv = Join-Path $repoPath ".venv"
Write-Host "[3/6] venv 생성: $venv" -ForegroundColor Cyan
if (-not (Test-Path $venv)) {
  $made = $false
  foreach ($cmd in @(
    @{ Exe = "py"; Args = @("-3.10", "-m", "venv", $venv) },
    @{ Exe = "py"; Args = @("-3.11", "-m", "venv", $venv) },
    @{ Exe = "python"; Args = @("-m", "venv", $venv) }
  )) {
    try {
      & $cmd.Exe @cmd.Args
      if (Test-Path $venv) { $made = $true; break }
    } catch { }
  }
  if (-not $made -or -not (Test-Path $venv)) {
    throw "venv 생성 실패. py -3.10 또는 Python 3.10+ PATH 를 확인하세요."
  }
}

$pip = Join-Path $venv "Scripts\pip.exe"
$python = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $pip)) { throw "venv Scripts\pip.exe 없음" }

& $pip install -U pip setuptools wheel

$index = switch ($CudaTag) {
  "cu118" { "https://download.pytorch.org/whl/cu118" }
  "cu121" { "https://download.pytorch.org/whl/cu121" }
  "cu124" { "https://download.pytorch.org/whl/cu124" }
}

Write-Host "[4/6] PyTorch ($CudaTag) — pytorch.org 조합과 동일" -ForegroundColor Cyan
Write-Host "      실패 시 -CudaTag 를 cu118 / cu121 / cu124 중 바꿔 보세요." -ForegroundColor Yellow
& $pip install torch torchvision torchaudio --index-url $index

Write-Host "[5/6] ninja + xformers(선택)" -ForegroundColor Cyan
& $pip install ninja
try {
  & $pip install xformers --index-url $index
} catch {
  Write-Warning "xformers 실패 시 무시하고 진행합니다(환경에 따라 Windows wheel 없음)."
}

Write-Host "[6/6] requirements.txt (nvdiffrast 빌드는 VS C++ Build Tools 필요할 수 있음)" -ForegroundColor Cyan
Push-Location $repoPath
& $pip install -r requirements.txt
Pop-Location

Write-Host "`n검증:" -ForegroundColor Green
& $python -c "import torch; print('cuda:', torch.cuda.is_available())"

Write-Host "`n다음 (GLB 래퍼):" -ForegroundColor Green
Write-Host "  `$env:INSTANTMESH_ROOT='$repoPath'"
Write-Host "  & `"$python`" `"$((Join-Path $PSScriptRoot 'inference_glb.py'))`" path\to\image.png --out `"$repoPath\outputs_glb`" --no-video --diffusion-steps 40"
Write-Host "`n공식 CLI (OBJ+텍스처):" -ForegroundColor Green
Write-Host "  cd `"$repoPath`""
Write-Host "  .\.venv\Scripts\python.exe run.py configs/instant-mesh-large.yaml examples\hatsune_miku.png --export_texmap"
