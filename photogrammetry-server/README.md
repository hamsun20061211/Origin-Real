# Photogrammetry server (COLMAP) — MVP

TripoSR 엔진(`triposr-server`, 기본 8001)과 **별도 프로세스**로 둡니다. 실사 다시점 사진 → COLMAP → `mesh.ply` / `mesh.glb`.

## Phase A (로컬 검증, 이 서버 없이)

1. 사진 20~40장 이상, 겹치게 촬영.
2. [COLMAP](https://colmap.github.io/) GUI 또는 `colmap automatic_reconstructor --workspace_path ... --image_path .../images` 로 희소·밀집이 되는지 확인.
3. 무늬 없는 면·흔들림·초점 실패로 여기서 실패하면 **API로 감싸도 품질은 나아지지 않습니다.**

## 설치

- **COLMAP** 본체: PATH에 `colmap` 이 잡히거나, Windows에서는 `COLMAP_EXECUTABLE`에 `COLMAP.bat` 전체 경로.
- **Python 패키지** (TripoSR과 같은 venv를 써도 됨):

```bash
cd photogrammetry-server
pip install -r requirements.txt
```

## 실행

레포 루트에서:

```bash
npm run photogrammetry
```

또는:

```bash
cd photogrammetry-server
uvicorn main:app --host 0.0.0.0 --port 8002
```

- 헬스: `GET http://127.0.0.1:8002/health`
- OpenAPI: `http://127.0.0.1:8002/docs`

## 환경 변수

| 변수 | 설명 |
|------|------|
| `PHOTOGRAMMETRY_PORT` | 기본 `8002` (`npm run photogrammetry`에서 사용) |
| `PHOTOGRAMMETRY_DATA_DIR` | 작업 폴더 루트 (기본 `photogrammetry-server/data`) |
| `COLMAP_EXECUTABLE` | `colmap` 또는 Windows `COLMAP.bat` 경로 |
| `PHOTOGRAMMETRY_MAX_ZIP_MB` | ZIP 업로드 한도 MB (기본 512) |
| `PHOTOGRAMMETRY_EXPORT_GLB` | `1`이면 `mesh.glb` 생성 시도 (trimesh) |
| `PHOTOGRAMMETRY_CLEAN_WORKSPACE` | 성공 후 `database.db`/`sparse`/`dense` 삭제 (기본 0) |
| `PHOTOGRAMMETRY_JOB_TIMEOUT_SEC` | 워커가 `run_colmap_job.py` 전체를 기다리는 초 (0=무제한) |
| `OR_PHOTO_TIMEOUT_SEC` | COLMAP **각 서브프로세스** 타임아웃 (0=무제한) |
| `OR_PHOTO_QUALITY` | `LOW` / `MEDIUM` / `HIGH` / `EXTREME` (`automatic_reconstructor`) |
| `OR_PHOTO_DATA_TYPE` | `INDIVIDUAL` / `VIDEO` / `INTERNET` |
| `OR_PHOTO_SPARSE_ONLY` | `1`이면 희소만 + `output/sparse_points.ply` (표면 메쉬 아님) |
| `PUBLIC_BASE_URL` | `status.download_url` 절대 URL 접두사 |
| `CORS_ALLOW_ALL` | 개발 시 `1`이면 CORS `*` |

레포 루트 `.env.local`은 서버 기동 시 자동 병합됩니다 (`triposr-server`와 동일 패턴).

## API (요약)

### `POST /photogrammetry/jobs`

- **ZIP:** `multipart/form-data` 필드명 `file`, 확장자 `.zip` (내부에 JPG/PNG 등).
- **다중 이미지:** 필드명 `images`로 여러 파일 (동일 폼).

응답 `202`: `{ "id": "<uuid>", "status": "pending", "poll_url": "/photogrammetry/jobs/{id}" }`

### `GET /photogrammetry/jobs/{id}`

`status`: `pending` | `running` | `failed` | `completed`

- `failed`: `message`, `log_excerpt` (있을 수 있음)
- `completed`: `download_path`, `download_url`, `result_file` (`mesh.ply` 또는 희소만일 때 `sparse_points.ply`)

### `GET /photogrammetry/jobs/{id}/download/{name}`

`name`: `mesh.ply` | `mesh.glb` | `sparse_points.ply`

## TripoSR과 공존

- TripoSR: `TRIPOSR_URL=http://127.0.0.1:8001`
- 포토그래메트리: `http://127.0.0.1:8002` — 프론트에서 모드에 따라 호출 URL만 분기.

프록시가 필요하면 Next에서 `PHOTOGRAMMETRY_URL`로 리버스 프록시를 두면 됩니다.

## 운영 시 흔한 문제

- **무늬 없는 벽·금속** → 특징 매칭 실패 → 희소 재구성 실패.
- **장마다 초점·노출 불안정** → 품질 저하.
- **밀집 단계** 중간 파일이 매우 큼 → 디스크·동시 작업 수 제한 (`ThreadPoolExecutor(max_workers=1)`).
- **한 PC에서 COLMAP 여러 개** → RAM/디스크 병목.
- **GPU:** COLMAP 밀집은 CUDA가 있으면 사용; 없으면 CPU로 매우 느릴 수 있음.

## Phase D — Docker (초안)

`Dockerfile` 참고. Ubuntu에 `apt install colmap` 후 Python 의존성 설치. GPU 노드에서는 NVIDIA 런타임으로 밀집만 분리하는 구성이 가능합니다.

## 직접 서비스를 만들지 않을 때

- Polycam / RealityCapture / Metashape 등에서 GLB보내기 후 앱에 업로드.
- 멀티 이미지 → 메쉬 클라우드 API는 약관·가격·품질 비교 후 연동.
