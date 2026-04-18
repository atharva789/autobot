"""
morphology_factory.py — AGENT-EDITABLE

This file is read and modified by the autoresearch agent each iteration.
You may change:
  - Parameter ranges passed to MorphologyParams
  - Which VAE latent dimensions to emphasize
  - Post-processing of sampled params

Do NOT change the function signatures (build, sample_from_vae).
Do NOT import from outside packages/pipeline/.
"""
from __future__ import annotations

import dataclasses

from packages.pipeline.types import MorphologyParams
from packages.pipeline.urdf_factory import build_urdf, validate_urdf

# ---------------------------------------------------------------------------
# AGENT: adjust these overrides to bias exploration towards specific morphologies.
# Keys must be valid MorphologyParams field names.
# ---------------------------------------------------------------------------
PARAM_OVERRIDES: dict = {
    # Example — force biped by fixing num_legs=2:
    # "num_legs": 2,
}

VAE_CKPT_PATH = "/vol/vae_checkpoint.pt"
_vae = None


def _load_vae():
    global _vae
    if _vae is None:
        import torch
        from packages.pipeline.vae import MorphologyVAE

        _vae = MorphologyVAE(latent_dim=8)
        _vae.load_state_dict(torch.load(VAE_CKPT_PATH, map_location="cpu"))
        _vae.eval()
    return _vae


def sample_from_vae(seed: int | None = None) -> MorphologyParams:
    """Sample a morphology from the VAE latent space."""
    import torch

    vae = _load_vae()
    if seed is not None:
        torch.manual_seed(seed)

    # AGENT: modify z here to bias the sample, e.g. set z[0, 2] = 2.0 for longer legs
    with torch.no_grad():
        z = torch.randn(1, vae.latent_dim)
        t = vae.decode(z).squeeze(0).clamp(0.0, 1.0)

    from packages.pipeline.vae import tensor_to_params

    params = tensor_to_params(t)
    if PARAM_OVERRIDES:
        params = MorphologyParams(**{**dataclasses.asdict(params), **PARAM_OVERRIDES})
    return params


def build(
    params: MorphologyParams | None = None,
    seed: int | None = None,
) -> tuple[MorphologyParams, str]:
    """Return (params, urdf_xml). Samples from VAE if params is None."""
    if params is None:
        params = sample_from_vae(seed=seed)
    xml = build_urdf(params)
    return params, xml
