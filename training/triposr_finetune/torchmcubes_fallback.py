"""Register a CPU marching-cubes shim if torchmcubes is not built (same idea as triposr-server/main.py)."""

from __future__ import annotations

import importlib.util
import os
import sys
import types


def ensure_torchmcubes_stub() -> None:
    if importlib.util.find_spec("torchmcubes") is not None:
        return
    if (os.environ.get("TRIPOSR_FORCE_TORCHMCUBES") or "").lower() in ("1", "true", "yes"):
        raise ImportError(
            "torchmcubes missing and TRIPOSR_FORCE_TORCHMCUBES=1. "
            "Install CUDA Toolkit and: pip install git+https://github.com/tatsy/torchmcubes.git"
        )
    import numpy as np
    import torch
    from skimage.measure import marching_cubes as sk_mc

    def marching_cubes(vol: torch.Tensor, level: float):
        arr = vol.detach().cpu().float().numpy()
        verts, faces, _, _ = sk_mc(arr, level=float(level))
        v = torch.as_tensor(verts, dtype=torch.float32)
        f = torch.as_tensor(faces.astype(np.int64), dtype=torch.int64)
        return v, f

    mod = types.ModuleType("torchmcubes")
    mod.marching_cubes = marching_cubes
    sys.modules["torchmcubes"] = mod
    print(
        "[train] torchmcubes missing -> skimage marching_cubes (CPU). "
        "For GPU MC install torchmcubes with CUDA Toolkit.",
        flush=True,
    )
