# Windows: NVIDIA GPU / 드라이버가 노출하는 최대 CUDA / (선택) nvcc
# 사용: powershell -ExecutionPolicy Bypass -File .\00_check_gpu.ps1

Write-Host "=== nvidia-smi (GPU 이름, 드라이버, 드라이버가 지원하는 최대 CUDA) ===" -ForegroundColor Cyan
try {
  nvidia-smi
} catch {
  Write-Warning "nvidia-smi 를 찾을 수 없습니다. NVIDIA 드라이버를 설치하세요."
}

Write-Host "`n=== PyTorch (설치된 경우) CUDA 빌드 ===" -ForegroundColor Cyan
try {
  python -c "import torch; print('torch:', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('torch cuda:', getattr(torch.version, 'cuda', None)); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
} catch {
  Write-Host "python 또는 torch 가 없습니다."
}

Write-Host "`n=== nvcc (CUDA Toolkit; 없어도 PyTorch 번들 CUDA 로 추론은 가능) ===" -ForegroundColor Cyan
try {
  nvcc --version
} catch {
  Write-Host "nvcc 없음 — 정상일 수 있음 (PyTorch wheel 전용 런타임만 쓰는 경우)."
}

Write-Host "`n안내: `nvidia-smi` 의 'CUDA Version' 은 드라이버가 지원하는 **상한**입니다." -ForegroundColor Yellow
Write-Host "PyTorch는 보통 cu121 / cu124 등 **별도** 빌드를 깔습니다.pytorch.org 에서 조합을 맞추세요." -ForegroundColor Yellow
