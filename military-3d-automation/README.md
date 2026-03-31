## Military 3D Quality Pipeline

이미지 -> 선별 -> InstantMesh 배치 생성 -> GLB 품질 리포트까지 자동화.

### 1) 설치
```powershell
cd "c:\Users\4080\Downloads\Origin Real\military-3d-automation"
py -3 -m pip install -r requirements.txt
```

### 2) 원샷 실행
```powershell
powershell -ExecutionPolicy Bypass -File .\RUN_QUALITY_PIPELINE.ps1 `
  -ImageRoot "c:\Users\4080\Downloads\Origin Real\downloads" `
  -InstantMeshPython "$env:USERPROFILE\InstantMesh\InstantMesh\.venv\Scripts\python.exe"
```

### 결과물
- `curated_dataset.json`: 품질/중복 제거 후 상위 샘플
- `generated_glb/**`: 카테고리별 생성 GLB
- `generated_glb/quality_report.json`: 정점수/면수/watertight 등 품질 지표

### 참고
- `helmet`, `gun` 카테고리는 자동으로 symmetry 후처리를 켠 채 추론합니다.
- 품질 우선이므로 기본 추론 개수는 제한(`--limit`)되어 있습니다.

