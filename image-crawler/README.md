## Military gear image collector (CC-friendly)

### 왜 Google Images / Pinterest “직접 크롤링”을 안 넣었나
- 두 서비스는 일반적으로 **자동 수집/스크래핑을 약관(ToS)에서 제한**합니다.
- 대신 이 도구는 **상업적 이용 가능 라이선스 필터가 가능한 공개 소스**(Openverse, Wikimedia Commons)만 기본 제공해 **법적/운영 리스크를 낮춥니다**.

### 설치

```bash
cd "c:\Users\4080\Downloads\Origin Real\image-crawler"
py -3 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### 실행 (카테고리별 폴더 저장)

```bash
.\.venv\Scripts\python.exe collect_cc_images.py ^
  --out "c:\Users\4080\Downloads\Origin Real\downloads" ^
  --min-size 1024 ^
  --max-per-query 120 ^
  --bg-simple-threshold 0.055 ^
  --query "Tactical Plate Carrier MultiCam" --category vest ^
  --query "Ballistic Helmet Detail" --category helmet ^
  --query "AR15 rifle close-up matte metal" --category gun
```

결과 구조:
- `downloads/vest/*`
- `downloads/helmet/*`
- `downloads/gun/*`

### 필터
- **해상도 필터**: `--min-size` 이상(가로/세로 모두)
- **배경 단순도 우선**: `--bg-simple-threshold`는 엣지 밀도 기반(낮을수록 “배경이 단순”)

### 저작권/사용 주의
- 이 도구는 기본적으로 **상업적 이용 가능한 라이선스(CC0/CC BY/CC BY-SA 등)**만 받도록 옵션이 들어있습니다.
- 그래도 최종 사용 전에 `dataset_sources.jsonl`에 기록된 **license / license_url / source_url**을 검토하세요.

