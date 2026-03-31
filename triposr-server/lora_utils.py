"""Load PEFT LoRA weights (safetensors) into TripoSR backbone."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("origin_real.triposr.lora")


def _lora_config_from_json(path: Path, *, LoraConfig: type) -> Any:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    try:
        return LoraConfig(**raw)
    except TypeError:
        fields = getattr(LoraConfig, "__dataclass_fields__", None) or getattr(
            LoraConfig, "model_fields", None
        )
        if fields is None:
            raise
        allowed = set(fields.keys())
        filtered = {k: v for k, v in raw.items() if k in allowed}
        return LoraConfig(**filtered)


def apply_lora_safetensors(tsr: Any, safetensors_path: Path, adapter_config_path: Path) -> None:
    """Wrap tsr.backbone with PEFT and load adapter weights."""
    try:
        from peft import LoraConfig as LC, get_peft_model
        from peft.utils import set_peft_model_state_dict
        from safetensors.torch import load_file
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "LoRA 추론에는 peft, safetensors 가 필요합니다. "
            "pip install peft safetensors"
        ) from e

    if not safetensors_path.is_file():
        raise FileNotFoundError(f"LoRA safetensors not found: {safetensors_path}")
    if not adapter_config_path.is_file():
        raise FileNotFoundError(f"LoRA adapter config not found: {adapter_config_path}")

    lora_cfg = _lora_config_from_json(adapter_config_path, LoraConfig=LC)
    tsr.backbone = get_peft_model(tsr.backbone, lora_cfg)
    state = load_file(str(safetensors_path))
    set_peft_model_state_dict(tsr.backbone, state)
    logger.info("LoRA loaded: %s", safetensors_path)


def _pick_safetensors_in_dir(ckpt_dir: Path) -> Path | None:
    """Prefer final triposr_lora.safetensors; else highest triposr_lora_epochN; else newest mtime."""
    preferred = ckpt_dir / "triposr_lora.safetensors"
    if preferred.is_file():
        return preferred
    candidates = list(ckpt_dir.glob("*.safetensors"))
    if not candidates:
        return None
    epoch_re = re.compile(r"^triposr_lora_epoch(\d+)\.safetensors$", re.IGNORECASE)
    best_ep = (-1, None)
    for p in candidates:
        m = epoch_re.match(p.name)
        if m:
            n = int(m.group(1))
            if n > best_ep[0]:
                best_ep = (n, p)
    if best_ep[1] is not None:
        return best_ep[1]
    return max(candidates, key=lambda p: p.stat().st_mtime)


def resolve_default_lora_paths(repo_root: Path) -> tuple[Path | None, Path | None]:
    """models/checkpoints/triposr_lora.safetensors + triposr_lora_adapter_config.json"""
    ckpt_dir = repo_root / "models" / "checkpoints"
    if not ckpt_dir.is_dir():
        return None, None
    st = _pick_safetensors_in_dir(ckpt_dir)
    if st is None:
        return None, None
    cfg = st.with_name(st.stem + "_adapter_config.json")
    if not cfg.is_file():
        alt = ckpt_dir / "adapter_config.json"
        cfg = alt if alt.is_file() else cfg
    return st, cfg if cfg.is_file() else None
