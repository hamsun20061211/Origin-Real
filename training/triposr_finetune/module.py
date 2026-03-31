"""
Lightning module: TripoSR with LoRA on the 1D transformer backbone.

Objective (no 3D ground truth): match scene_codes from the frozen base backbone on a
clean image with scene_codes from base+LoRA on a weakly augmented view — a lightweight
consistency / distillation-style signal. For production 3D fidelity you still need
3D supervision or an objective aligned with mesh quality.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytorch_lightning as pl
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TF
from peft import LoraConfig, get_peft_model, get_peft_model_state_dict
from safetensors.torch import save_file


DEFAULT_LORA_TARGETS = (
    "to_q",
    "to_k",
    "to_v",
    "to_out.0",
    "proj_in",
    "proj_out",
    "proj",
    "net.2",
)


def _json_safe_for_dump(obj: Any) -> Any:
    """PEFT to_dict() may contain set/tuple; json.dump would fail mid-stream and truncate files."""
    if isinstance(obj, dict):
        return {k: _json_safe_for_dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe_for_dump(x) for x in obj]
    if isinstance(obj, set):
        if obj and all(isinstance(x, str) for x in obj):
            return sorted(obj)
        return [_json_safe_for_dump(x) for x in obj]
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return str(obj)


def _set_backbone_gradient_checkpointing(tsr: Any, enabled: bool) -> None:
    bb = getattr(tsr, "backbone", None)
    if bb is None:
        return
    inner = bb
    if hasattr(bb, "base_model") and hasattr(bb.base_model, "model"):
        inner = bb.base_model.model
    elif hasattr(bb, "model"):
        inner = bb.model
    if hasattr(inner, "gradient_checkpointing"):
        inner.gradient_checkpointing = bool(enabled)


def _build_optimizer(trainable: list[torch.nn.Parameter], lr: float, weight_decay: float):
    try:
        import bitsandbytes as bnb

        return bnb.optim.AdamW8bit(trainable, lr=lr, weight_decay=weight_decay)
    except Exception:
        return torch.optim.AdamW(trainable, lr=lr, weight_decay=weight_decay)


class TripoSRLoRALightningModule(pl.LightningModule):
    def __init__(
        self,
        *,
        pretrained_id: str = "stabilityai/TripoSR",
        config_name: str = "config.yaml",
        weight_name: str = "model.ckpt",
        lora_r: int = 8,
        lora_alpha: int = 16,
        lora_dropout: float = 0.05,
        target_modules: tuple[str, ...] = DEFAULT_LORA_TARGETS,
        lr: float = 1e-4,
        weight_decay: float = 0.01,
        use_8bit_adam: bool = True,
        augment_strength: float = 0.12,
        checkpoint_dir: str | Path = "models/checkpoints",
        safetensors_basename: str = "triposr_lora",
    ) -> None:
        super().__init__()
        self.save_hyperparameters(ignore=["tsr"])

        from tsr.system import TSR

        self.tsr = TSR.from_pretrained(pretrained_id, config_name, weight_name)
        lora_cfg = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            target_modules=list(target_modules),
            lora_dropout=lora_dropout,
            bias="none",
        )
        self.tsr.backbone = get_peft_model(self.tsr.backbone, lora_cfg)
        for n, p in self.tsr.named_parameters():
            p.requires_grad = "lora_" in n
        _set_backbone_gradient_checkpointing(self.tsr, True)

        self.lr = lr
        self.weight_decay = weight_decay
        self.use_8bit_adam = use_8bit_adam
        self.augment_strength = augment_strength
        self.checkpoint_dir = Path(checkpoint_dir)
        self.safetensors_basename = safetensors_basename

    def _augment_pil(self, image):
        t = torch.from_numpy(np.array(image.convert("RGB")).copy()).float() / 255.0
        t = t.permute(2, 0, 1)
        s = self.augment_strength
        if s > 0:
            t = TF.adjust_brightness(t, 1.0 + (torch.rand(1).item() * 2 - 1) * s)
            t = TF.adjust_contrast(t, 1.0 + (torch.rand(1).item() * 2 - 1) * s)
            t = TF.adjust_saturation(t, 1.0 + (torch.rand(1).item() * 2 - 1) * s)
            if torch.rand(1).item() < 0.5:
                t = torch.flip(t, dims=[2])
        t = t.clamp(0, 1)
        rgb = (t.permute(1, 2, 0).numpy() * 255.0).round().astype("uint8")
        from PIL import Image as PILImage

        return PILImage.fromarray(rgb)

    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        # batch_size=1: batch["image"] is a list of one PIL image
        clean = batch["image"][0]
        aug = self._augment_pil(clean)
        dev = self.device
        device_str = "cuda" if dev.type == "cuda" else str(dev)

        bb = self.tsr.backbone
        with torch.no_grad():
            with bb.disable_adapter():
                target = self.tsr(clean, device_str)

        pred = self.tsr(aug, device_str)
        loss = F.mse_loss(pred, target)
        self.log(
            "train/loss",
            loss,
            prog_bar=True,
            on_step=True,
            on_epoch=True,
            batch_size=1,
        )
        cap = batch.get("caption", [""])[0] if batch.get("caption") else ""
        if cap and batch_idx % 50 == 0 and self.logger is not None:
            exp = getattr(self.logger, "experiment", None)
            if exp is not None and hasattr(exp, "add_text"):
                exp.add_text("train/caption", cap[:500], self.global_step)
        return loss

    def configure_optimizers(self):
        trainable = [p for p in self.tsr.parameters() if p.requires_grad]
        if not trainable:
            raise RuntimeError("No trainable parameters (LoRA missing?).")
        if self.use_8bit_adam:
            opt = _build_optimizer(trainable, self.lr, self.weight_decay)
        else:
            opt = torch.optim.AdamW(trainable, lr=self.lr, weight_decay=self.weight_decay)
        return opt

    def save_lora_safetensors(self, path: Path | None = None) -> Path:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        out = path or (self.checkpoint_dir / f"{self.safetensors_basename}.safetensors")
        out = Path(out)
        sd = get_peft_model_state_dict(self.tsr.backbone)
        save_file(sd, str(out))
        cfg_path = out.with_name(out.stem + "_adapter_config.json")
        peft_cfg = self.tsr.backbone.peft_config["default"]
        payload = _json_safe_for_dump(peft_cfg.to_dict())
        tmp = cfg_path.with_suffix(cfg_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, cfg_path)
        return out

    def on_train_end(self) -> None:
        if self.trainer.is_global_zero:
            p = self.save_lora_safetensors()
            print(f"[TripoSR LoRA] saved {p}")
