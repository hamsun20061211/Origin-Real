"""
TripoSR backbone LoRA fine-tuning entrypoint.

Prereq: clone TripoSR and point --triposr-root (or TRIPOSR_ROOT) to that folder so `import tsr` works.

Example:
  set TRIPOSR_ROOT=C:\\path\\to\\TripoSR
  pip install -r training/triposr_finetune/requirements.txt
  python training/triposr_finetune/train.py --processed-dir data/processed --triposr-root %TRIPOSR_ROOT%

Data: put PNG/JPG under data/processed/images/ and optional captions/<stem>.txt,
      or provide data/processed/manifest.jsonl.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytorch_lightning as pl
import torch
from pytorch_lightning.callbacks import Callback, ModelCheckpoint
from torch.utils.data import DataLoader

from training.triposr_finetune.dataset import ProcessedImageCaptionDataset
from training.triposr_finetune.module import TripoSRLoRALightningModule
from training.triposr_finetune.torchmcubes_fallback import ensure_torchmcubes_stub


def _ensure_triposr_on_path(triposr_root: str | None) -> None:
    root = (triposr_root or os.environ.get("TRIPOSR_ROOT") or "").strip()
    if not root:
        print(
            "Set --triposr-root or TRIPOSR_ROOT to your TripoSR repository (folder containing tsr/).",
            file=sys.stderr,
        )
        sys.exit(1)
    p = Path(root).resolve()
    if not (p / "tsr").is_dir():
        print(f"Not a TripoSR repo (missing tsr/): {p}", file=sys.stderr)
        sys.exit(1)
    sys.path.insert(0, str(p))


def _collate(batch: list) -> dict:
    return {
        "image": [b["image"] for b in batch],
        "caption": [b["caption"] for b in batch],
        "path": [b["path"] for b in batch],
    }


class SaveLoRASafetensorsCallback(Callback):
    def __init__(self, every_n_epochs: int, checkpoint_dir: Path, basename: str) -> None:
        self.every_n_epochs = max(1, every_n_epochs)
        self.checkpoint_dir = checkpoint_dir
        self.basename = basename

    def on_train_epoch_end(self, trainer: pl.Trainer, pl_module: TripoSRLoRALightningModule) -> None:
        if not trainer.is_global_zero:
            return
        ep = trainer.current_epoch + 1
        if ep % self.every_n_epochs != 0:
            return
        path = self.checkpoint_dir / f"{self.basename}_epoch{ep}.safetensors"
        pl_module.save_lora_safetensors(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed-dir", type=str, default="data/processed")
    ap.add_argument("--triposr-root", type=str, default="")
    ap.add_argument("--pretrained", type=str, default="stabilityai/TripoSR")
    ap.add_argument("--config-name", type=str, default="config.yaml")
    ap.add_argument("--weight-name", type=str, default="model.ckpt")
    ap.add_argument("--checkpoint-dir", type=str, default="models/checkpoints")
    ap.add_argument("--safetensors-basename", type=str, default="triposr_lora")
    ap.add_argument("--max-epochs", type=int, default=5)
    ap.add_argument("--gradient-accumulation-steps", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lora-r", type=int, default=8)
    ap.add_argument("--lora-alpha", type=int, default=16)
    ap.add_argument("--augment-strength", type=float, default=0.12)
    ap.add_argument("--num-workers", type=int, default=0)
    ap.add_argument("--require-pexels-key", action="store_true")
    ap.add_argument("--precision", type=str, choices=("bf16-mixed", "16-mixed", "32"), default="")
    ap.add_argument("--no-8bit-adam", action="store_true")
    ap.add_argument("--save-lora-every-n-epochs", type=int, default=1)
    args = ap.parse_args()

    _ensure_triposr_on_path(args.triposr_root or None)
    ensure_torchmcubes_stub()

    processed = Path(args.processed_dir)
    ds = ProcessedImageCaptionDataset(
        processed,
        require_pexels_key=args.require_pexels_key,
    )
    dl = DataLoader(
        ds,
        batch_size=1,
        shuffle=True,
        num_workers=args.num_workers,
        collate_fn=_collate,
        pin_memory=torch.cuda.is_available(),
    )

    ckpt_dir = Path(args.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    module = TripoSRLoRALightningModule(
        pretrained_id=args.pretrained,
        config_name=args.config_name,
        weight_name=args.weight_name,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        augment_strength=args.augment_strength,
        lr=args.lr,
        use_8bit_adam=not args.no_8bit_adam,
        checkpoint_dir=ckpt_dir,
        safetensors_basename=args.safetensors_basename,
    )

    if args.precision:
        precision = args.precision
    elif torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        precision = "bf16-mixed"
    elif torch.cuda.is_available():
        precision = "16-mixed"
    else:
        precision = "32"

    callbacks = [
        ModelCheckpoint(
            dirpath=str(ckpt_dir / "lightning_ckpts"),
            filename="triposr-lora-{epoch:02d}",
            every_n_epochs=1,
            save_top_k=-1,
        ),
        SaveLoRASafetensorsCallback(
            every_n_epochs=args.save_lora_every_n_epochs,
            checkpoint_dir=ckpt_dir,
            basename=args.safetensors_basename,
        ),
    ]

    trainer = pl.Trainer(
        max_epochs=args.max_epochs,
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        devices=1,
        precision=precision,
        gradient_clip_val=1.0,
        accumulate_grad_batches=args.gradient_accumulation_steps,
        log_every_n_steps=5,
        callbacks=callbacks,
        default_root_dir=str(ckpt_dir / "lightning_logs"),
    )

    trainer.fit(module, dl)


if __name__ == "__main__":
    main()
