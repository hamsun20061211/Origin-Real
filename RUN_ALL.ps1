# One-shot runner (Windows PowerShell)
# -----------------------------------
# 이 스크립트는 아래를 순서대로 실행합니다.
# 1) Blender 멀티앵글 렌더(12+4) → D:\dataset\pc_turntable
# 2) (선택) OpenCV 후처리 → dataset.json이 있는 폴더(root) 기준
# 3) (선택) 무결성 검증
# 4) (선택) CC-friendly 이미지 수집(Openverse/Wikimedia) → downloads/vest|helmet|gun
#
# 주의:
# - Google Images/Pinterest 직접 크롤링은 ToS 이슈가 있어 포함하지 않았습니다.
# - Blender 경로/모델 경로/출력 경로는 환경에 맞게 수정하세요.
#
param(
  [string]$BlenderExe = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
  [string]$ModelPath  = "D:\models\plate_carrier.glb",
  [string]$TurntableOut = "D:\dataset\pc_turntable",
  [int]$Resolution = 1024,
  [int]$Samples = 192,
  [ValidateSet("transparent","gray")][string]$Background = "transparent",

  # OpenCV postprocess + validate
  [string]$DatasetRoot = "D:\dataset\out_run1",
  [switch]$RunPostprocess,
  [switch]$RunValidate,

  # Image crawler
  [string]$CrawlerOut = "c:\Users\4080\Downloads\Origin Real\downloads",
  [switch]$RunCrawler
)

$ErrorActionPreference = "Stop"

Write-Host "=== [0] 경로 체크 ===" -ForegroundColor Cyan
if (-not (Test-Path $BlenderExe)) { throw "BlenderExe 없음: $BlenderExe" }
if (-not (Test-Path $ModelPath))  { throw "ModelPath 없음: $ModelPath" }

$repoRoot = $PSScriptRoot
$blenderScript = Join-Path $repoRoot "blender-military-dataset\render_turntable_12plus4.py"
if (-not (Test-Path $blenderScript)) { throw "Blender 스크립트 없음: $blenderScript" }

New-Item -ItemType Directory -Force -Path $TurntableOut | Out-Null
New-Item -ItemType Directory -Force -Path $DatasetRoot | Out-Null
New-Item -ItemType Directory -Force -Path $CrawlerOut | Out-Null

Write-Host "=== [1] Blender 렌더: 12+4 ===" -ForegroundColor Cyan
& $BlenderExe --background --python $blenderScript -- `
  --input $ModelPath `
  --output $TurntableOut `
  --resolution $Resolution `
  --samples $Samples `
  --background $Background

if ($RunPostprocess -or $RunValidate) {
  Write-Host "=== [2] Python(OpenCV) 준비 ===" -ForegroundColor Cyan
  $py = "py"
  $pp = Join-Path $repoRoot "blender-military-dataset\postprocess_dataset_opencv.py"
  $vd = Join-Path $repoRoot "blender-military-dataset\validate_dataset_integrity.py"

  if ($RunPostprocess) {
    Write-Host "=== [3] OpenCV 샤프닝 + AutoTag dataset.json 업데이트 ===" -ForegroundColor Cyan
    & $py -3 -m pip install opencv-python
    & $py -3 $pp --root $DatasetRoot --inplace
  }

  if ($RunValidate) {
    Write-Host "=== [4] 무결성 검증 ===" -ForegroundColor Cyan
    & $py -3 $vd --root $DatasetRoot
  }
}

if ($RunCrawler) {
  Write-Host "=== [5] CC 이미지 수집기 실행 ===" -ForegroundColor Cyan
  $crawlerDir = Join-Path $repoRoot "image-crawler"
  $crawlerPy = Join-Path $crawlerDir "collect_cc_images.py"
  $venv = Join-Path $crawlerDir ".venv"
  $pip = Join-Path $venv "Scripts\pip.exe"
  $python = Join-Path $venv "Scripts\python.exe"

  if (-not (Test-Path $python)) {
    & py -3 -m venv $venv
  }
  & $pip install -r (Join-Path $crawlerDir "requirements.txt")

  & $python $crawlerPy `
    --out $CrawlerOut `
    --min-size 1024 `
    --max-per-query 120 `
    --bg-simple-threshold 0.055 `
    --query "Tactical Plate Carrier MultiCam" --category vest `
    --query "Ballistic Helmet Detail" --category helmet `
    --query "AR15 rifle close-up matte metal" --category gun
}

Write-Host "`n완료." -ForegroundColor Green

