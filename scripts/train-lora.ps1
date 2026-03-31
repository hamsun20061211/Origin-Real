# 차량·건물 등 data/processed 기준 TripoSR 백본 LoRA 학습.
# 완료 후 models/checkpoints/triposr_lora.safetensors + triposr_lora_adapter_config.json 생성.
# 엔진(triposr-server)은 같은 경로를 자동으로 읽습니다.
#
# 사용:
#   .\scripts\train-lora.ps1
#   .\scripts\train-lora.ps1 -MaxEpochs 5 -TripoRoot "D:\TripoSR"
#
param(
    [int]$MaxEpochs = 5,
    [string]$TripoRoot = "",
    [int]$SaveLoraEveryNEpochs = 1
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$CkptDir = Join-Path $RepoRoot "models\checkpoints"
$Processed = Join-Path $RepoRoot "data\processed"

if ($TripoRoot) {
    $env:TRIPOSR_ROOT = $TripoRoot
} elseif (-not $env:TRIPOSR_ROOT) {
    $env:TRIPOSR_ROOT = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads\TripoSR"
}

if (-not (Test-Path (Join-Path $env:TRIPOSR_ROOT "tsr"))) {
    Write-Error "TripoSR not found at $($env:TRIPOSR_ROOT) (need tsr\). Clone VAST-AI-Research/TripoSR or set -TripoRoot / TRIPOSR_ROOT."
}

$VenvPy = Join-Path $RepoRoot ".tripo-venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPy) { $VenvPy } else { "python" }

Write-Host "[train-lora] TRIPOSR_ROOT=$($env:TRIPOSR_ROOT)" -ForegroundColor Cyan
Write-Host "[train-lora] Python=$Python" -ForegroundColor Cyan
Write-Host "[train-lora] checkpoint-dir=$CkptDir | processed=$Processed | max_epochs=$MaxEpochs" -ForegroundColor Cyan
Write-Host "[train-lora] Running from repo root (paths match data/processed)." -ForegroundColor DarkGray

Set-Location $RepoRoot
& $Python -m pip install -q -r training/triposr_finetune/requirements.txt
& $Python training/triposr_finetune/train.py `
    --checkpoint-dir $CkptDir `
    --processed-dir $Processed `
    --max-epochs $MaxEpochs `
    --save-lora-every-n-epochs $SaveLoraEveryNEpochs

if ($LASTEXITCODE -ne 0) {
    Write-Error "train.py exited with code $LASTEXITCODE"
}

Write-Host "[train-lora] Done. Check: $CkptDir\triposr_lora.safetensors" -ForegroundColor Green
