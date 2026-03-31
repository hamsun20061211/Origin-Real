# NVIDIA GPU + PyTorch(CUDA) 정렬 설치 — InstantMesh / 전술 3D 워크플로
#
# 목표: driver 표시 "CUDA Version" 과 무관하게, pytorch.org wheel 조합(cu124 등)을
#       단일 인덱스 URL 로 설치해 torch / torchvision / torchaudio 버전 충돌을 줄임.
#
# 사용:
#   cd "...\Origin Real\instantmesh-setup"
#   powershell -ExecutionPolicy Bypass -File .\install_cuda_torch_tactical.ps1
#   powershell -ExecutionPolicy Bypass -File .\install_cuda_torch_tactical.ps1 -CudaTag cu121 -SkipInstantMeshClone
#
param(
  [string]$InstallDir = (Join-Path $env:USERPROFILE "InstantMesh"),
  [ValidateSet("cu121", "cu124", "cu118")]
  [string]$CudaTag = "cu124",
  [switch]$SkipInstantMeshClone,
  [switch]$IncludeSf3dNoteOnly
)

$ErrorActionPreference = "Stop"

Write-Host "=== [0] 드라이버 확인 (nvidia-smi) ===" -ForegroundColor Cyan
try {
  & nvidia-smi
} catch {
  Write-Warning "nvidia-smi 실패. NVIDIA 드라이버 설치 후 재실행하세요."
}

$index = switch ($CudaTag) {
  "cu118" { "https://download.pytorch.org/whl/cu118" }
  "cu121" { "https://download.pytorch.org/whl/cu121" }
  "cu124" { "https://download.pytorch.org/whl/cu124" }
}

$repoPath = Join-Path $InstallDir "InstantMesh"
$venv = Join-Path $repoPath ".venv"
$pip = Join-Path $venv "Scripts\pip.exe"
$python = Join-Path $venv "Scripts\python.exe"

if (-not $SkipInstantMeshClone) {
  Write-Host "`n=== [1] InstantMesh 클론 + venv (01_install_instantmesh.ps1 위임) ===" -ForegroundColor Cyan
  $installScript = Join-Path $PSScriptRoot "01_install_instantmesh.ps1"
  if (-not (Test-Path $installScript)) { throw "01_install_instantmesh.ps1 없음: $installScript" }
  & powershell -ExecutionPolicy Bypass -File $installScript -InstallDir $InstallDir -CudaTag $CudaTag
} else {
  if (-not (Test-Path $pip)) { throw "venv 없음: $venv — SkipInstantMeshClone 사용 시 먼저 venv 생성" }
}

Write-Host "`n=== [2] 전술 래퍼 의존성 (trimesh / scipy) ===" -ForegroundColor Cyan
& $pip install -U trimesh scipy

Write-Host "`n=== [3] 검증 ===" -ForegroundColor Green
& $python -c @"
import torch
print('torch', torch.__version__)
print('cuda_available', torch.cuda.is_available())
if torch.cuda.is_available():
    print('device', torch.cuda.get_device_name(0))
"@

Write-Host "`n환경 변수 (GLB/전술 추론):" -ForegroundColor Green
Write-Host "  `$env:INSTANTMESH_ROOT='$repoPath'"

Write-Host "`n추론 예:" -ForegroundColor Green
Write-Host "  & `"$python`" `"$(Join-Path $PSScriptRoot 'inference.py')`" path\to\plate_carrier.png --preset tactical_hi --symmetry --no-video --out `"$repoPath\outputs_tactical`""

if ($IncludeSf3dNoteOnly) {
  Write-Host "`nSF3D 는 별도 레포입니다. Windows 에서도 git clone 후 동일한 PyTorch 인덱스(cu124 등)로 venv 를 맞추면 충돌이 적습니다." -ForegroundColor Yellow
}

Write-Host "`n완료." -ForegroundColor Green
