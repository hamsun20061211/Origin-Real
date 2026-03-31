# 로컬 영상 생성 (Stable Video Diffusion)

**LTX-2 / 기타 Lightricks LTX 계열**은 이 폴더에 포함하지 않았습니다. 공식 저장소·전용 종속성이 따로 있으면 그쪽 `requirements`를 따르세요. 여기서는 **Hugging Face `diffusers` 기반 SVD**만 지원합니다.

## VRAM & “양자화”에 대해

- SVD는 보통 **`variant=fp16` 가중치**(반정밀도)로 받는 것이 표준 VRAM 절약입니다.  
- **INT8/4bit 같은 일반 양자화**는 비디오 UNet 전체에 아직 보편적이지 않고, 환경별로 깨지기 쉽습니다.  
- 대신 스크립트가 **`enable_xformers_memory_efficient_attention`**, **VAE slicing/tiling**, **`enable_sequential_cpu_offload`** 등을 사용합니다.

## 환경 (venv 예시)

```powershell
cd "c:\Users\4080\Downloads\Origin Real\local-video-gen"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip

# GPU (CUDA 버전은 본인 드라이버에 맞게 — https://pytorch.org/get-started/locally/)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

pip install -r requirements.txt

# 선택: VRAM 추가 절약 (Windows에서 실패할 수 있음)
# pip install xformers
```

## Hugging Face

1. 브라우저에서 `stabilityai/stable-video-diffusion-img2vid-xt` 모델 페이지 열기  
2. 약관 동의 후 **Access token** 발급  
3. PowerShell:

```powershell
pip install huggingface_hub
huggingface-cli login
```

또는 환경 변수 `HF_TOKEN`.

## 실행

```powershell
.\.venv\Scripts\Activate.ps1
python run_svd.py --image "C:\path\to\input.png" --output out.mp4 --low-vram
```

- VRAM 여유 있으면: `--med-vram` 또는 `--no-offload`  
- 더 줄이려면: `--decode-chunk-size 2`  
- 비 XT (가벼운 쪽): `--model stabilityai/stable-video-diffusion-img2vid`

## conda 예시

```powershell
conda create -n svd python=3.11 -y
conda activate svd
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

## RTX 5060 Ti 등 최신 GPU

PyTorch가 해당 GPU를 아직 공식 wheel로 완전히 지원하지 않으면 **드라이버/CUDA 조합에 맞는 nightly** 또는 **호환되는 torch 빌드**를 [PyTorch 시작 페이지](https://pytorch.org/get-started/locally/)에서 확인하세요. `run_svd.py`는 torch가 CUDA를 잡기만 하면 동일합니다.
