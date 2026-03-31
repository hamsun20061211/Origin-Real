param(
  [string]$ImageRoot = "c:\Users\4080\Downloads\Origin Real\downloads",
  [string]$CuratedJson = "c:\Users\4080\Downloads\Origin Real\military-3d-automation\curated_dataset.json",
  [string]$InstantMeshPython = "$env:USERPROFILE\InstantMesh\InstantMesh\.venv\Scripts\python.exe",
  [string]$GeneratedOut = "c:\Users\4080\Downloads\Origin Real\generated_glb",
  [int]$TopPerCategory = 40,
  [int]$LimitInference = 24
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== [1] curate images ===" -ForegroundColor Cyan
& py -3 "$root\score_and_curate_images.py" `
  --input-root $ImageRoot `
  --out-json $CuratedJson `
  --top-per-category $TopPerCategory `
  --min-size 1024

Write-Host "=== [2] batch infer + quality report ===" -ForegroundColor Cyan
& py -3 "$root\batch_infer_and_report.py" `
  --curated-json $CuratedJson `
  --instantmesh-python $InstantMeshPython `
  --out-dir $GeneratedOut `
  --limit $LimitInference `
  --diffusion-steps 50

Write-Host "`nDone. report: $GeneratedOut\quality_report.json" -ForegroundColor Green

