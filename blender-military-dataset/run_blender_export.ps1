# Blender CLI로 멀티뷰 + PBR 데이터셋 내보내기
# Blender 실행 파일 경로를 지정하세요.
param(
  [Parameter(Mandatory = $true)][string]$ModelPath,
  [string]$OutDir = "./military_export_out",
  [string]$BlenderExe = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
  [int]$Resolution = 2048,
  [int]$Samples = 256,
  [double]$Sharpen = 0.4
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "render_military_training_data.py"
if (-not (Test-Path $BlenderExe)) {
  Write-Warning "Blender 경로를 확인하세요: $BlenderExe"
}
& $BlenderExe --background --python $script -- `
  --input $ModelPath --output $OutDir --resolution $Resolution --samples $Samples --sharpen $Sharpen
