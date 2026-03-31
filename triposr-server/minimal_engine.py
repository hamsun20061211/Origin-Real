"""
TripoSR 없이 /health 만 응답하는 초경량 서버.
Next 앱의 엔진 연결 확인(토스트)을 끄고 UI만 볼 때 사용.

실제 Image→3D 메쉬 생성은 main.py + TripoSR 설치가 필요합니다.

  npm run engine:stub
  # 또는: python minimal_engine.py
"""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Origin Real · Engine stub", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "stub": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"[stub] http://{host}:{port}  (health only, no mesh generation)")
    uvicorn.run(app, host=host, port=port, log_level="info")
