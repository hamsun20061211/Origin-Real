# TencentARC/InstantMesh run.py 에 병합할 VAE 타일링 스니펫
# --------------------------------------------------------------
# Zero123++ 는 DiffusionPipeline 이며, 내부 VAE 가 있을 때 타일 디코딩으로 VRAM 피크를 줄일 수 있습니다.
# (파이프라인/버전에 따라 속성명이 다를 수 있으니 AttributeError 시 생략하세요.)
#
# 삽입 위치: run.py 에서
#   pipeline = pipeline.to(device)
# 바로 다음 줄.

_SNIPPET = r'''
# --- Tactical / low-VRAM: VAE tiling (optional) ---
try:
    vae = getattr(pipeline, "vae", None)
    if vae is not None:
        if hasattr(vae, "enable_tiling"):
            vae.enable_tiling()
        elif hasattr(vae, "enable_slicing"):
            vae.enable_slicing()
except Exception as _e:
    print("VAE tiling/slicing skip:", _e)
# --- end ---
'''

if __name__ == "__main__":
    print(_SNIPPET)
