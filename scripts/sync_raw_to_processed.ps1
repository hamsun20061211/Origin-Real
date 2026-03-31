# Copy data/raw images -> data/processed/images and add simple captions (building_* / car_*).
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$raw = Join-Path $Repo "data\raw"
$img = Join-Path $Repo "data\processed\images"
$cap = Join-Path $Repo "data\processed\captions"
if (-not (Test-Path $raw)) {
    Write-Error "Missing folder: $raw"
}
New-Item -ItemType Directory -Force -Path $img, $cap | Out-Null
$n = 0
Get-ChildItem -Path $raw -File | Where-Object { $_.Extension -match '\.(png|jpg|jpeg|webp)$' } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $img $_.Name) -Force
    $stem = $_.BaseName
    if ($stem -like 'building*') { $t = 'Modern architecture building exterior.' }
    elseif ($stem -like 'car*') { $t = 'Luxury car, automotive vehicle.' }
    else { $t = 'Photograph.' }
    Set-Content -Path (Join-Path $cap "$stem.txt") -Value $t -Encoding utf8
    $n++
}
Write-Host "Synced $n files -> data/processed/images (+ captions/)"
