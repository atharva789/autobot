"""
MorphologyVAE — 12-param input, 8-dim latent space.

All torch imports are deferred inside methods so this module can be imported
in environments where torch is not installed (tests will skip via
pytest.importorskip).
"""
from __future__ import annotations

from packages.pipeline.types import MorphologyParams

# ---------------------------------------------------------------------------
# Normalisation tables
# ---------------------------------------------------------------------------

_CONTINUOUS: list[tuple[str, float, float]] = [
    ("torso_length",    0.2,  0.6),
    ("arm_length",      0.3,  0.8),
    ("leg_length",      0.4,  1.0),
    ("joint_damping",   0.01, 1.0),
    ("joint_stiffness", 1.0,  100.0),
    ("friction",        0.3,  1.2),
]

_DISCRETE: list[tuple[str, int, int]] = [
    ("num_arms",  0, 2),
    ("num_legs",  2, 4),
    ("arm_dof",   3, 7),
    ("leg_dof",   3, 6),
    ("spine_dof", 0, 3),
    ("has_torso", 0, 1),
]

INPUT_DIM: int = 12  # len(_CONTINUOUS) + len(_DISCRETE)


# ---------------------------------------------------------------------------
# Tensor ↔ params helpers
# ---------------------------------------------------------------------------

def params_to_tensor(p: MorphologyParams):  # -> torch.Tensor
    """Normalise all 12 params to [0, 1] and return a float32 tensor."""
    import torch

    vals: list[float] = []
    for name, lo, hi in _CONTINUOUS:
        vals.append((getattr(p, name) - lo) / (hi - lo))
    for name, lo, hi in _DISCRETE:
        raw = float(p.has_torso) if name == "has_torso" else float(getattr(p, name))
        vals.append((raw - lo) / max(hi - lo, 1))
    return torch.tensor(vals, dtype=torch.float32)


def tensor_to_params(t) -> MorphologyParams:
    """
    Convert a normalised tensor (or list/numpy array) back to MorphologyParams.
    Works with or without torch attached — `t` just needs to support indexing.
    """
    # Support both torch tensors and plain sequences
    try:
        t = t.detach().cpu().tolist()
    except AttributeError:
        t = list(t)

    vals: dict = {}
    for i, (name, lo, hi) in enumerate(_CONTINUOUS):
        vals[name] = max(lo, min(hi, float(t[i]) * (hi - lo) + lo))

    offset = len(_CONTINUOUS)
    for i, (name, lo, hi) in enumerate(_DISCRETE):
        raw = float(t[offset + i]) * max(hi - lo, 1) + lo
        if name == "has_torso":
            vals[name] = raw > 0.5
        elif name in ("num_arms", "num_legs"):
            vals[name] = int(round(raw))
        else:
            vals[name] = max(lo, min(hi, int(round(raw))))

    return MorphologyParams(**vals)


# ---------------------------------------------------------------------------
# VAE
# ---------------------------------------------------------------------------

class MorphologyVAE:
    """
    Variational Autoencoder over 12-dim morphology space → 8-dim latent.

    Implemented as a plain Python class with lazy torch imports so the module
    is importable without torch.  The internal nn.Sequential layers are stored
    as private attributes; for Modal training a proper nn.Module subclass is
    built inline in modal_vae_train.py.
    """

    def __init__(self, latent_dim: int = 8, hidden: int = 64) -> None:
        import torch.nn as nn

        self.latent_dim = latent_dim

        self._encoder = nn.Sequential(
            nn.Linear(INPUT_DIM, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden),   nn.ReLU(),
        )
        self._fc_mu     = nn.Linear(hidden, latent_dim)
        self._fc_logvar = nn.Linear(hidden, latent_dim)
        self._decoder   = nn.Sequential(
            nn.Linear(latent_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden),     nn.ReLU(),
            nn.Linear(hidden, INPUT_DIM),
        )

    # ------------------------------------------------------------------
    # Forward pass primitives
    # ------------------------------------------------------------------

    def encode(self, x):
        """Return (mu, logvar) tensors."""
        h = self._encoder(x)
        return self._fc_mu(h), self._fc_logvar(h)

    def reparameterize(self, mu, logvar):
        import torch
        std = torch.exp(0.5 * logvar)
        return mu + std * torch.randn_like(std)

    def decode(self, z):
        return self._decoder(z)

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        return self.decode(z), mu, logvar

    # ------------------------------------------------------------------
    # Loss
    # ------------------------------------------------------------------

    def elbo_loss(self, x, beta: float = 0.5):
        import torch
        import torch.nn.functional as F

        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        recon = self.decode(z)
        recon_loss = F.mse_loss(recon, x, reduction="mean")
        kl = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).mean()
        return recon_loss + beta * kl

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def sample(self, seed: int | None = None) -> MorphologyParams:
        """Sample a morphology from the prior."""
        import torch

        if seed is not None:
            torch.manual_seed(seed)
        with torch.no_grad():
            z = torch.randn(1, self.latent_dim)
            t = self.decode(z).squeeze(0).clamp(0.0, 1.0)
        return tensor_to_params(t)

    # ------------------------------------------------------------------
    # Persistence helpers (used by morphology_factory.py)
    # ------------------------------------------------------------------

    def load_state_dict(self, state_dict: dict) -> None:
        """
        Load weights produced by the Modal training script.
        The Modal script uses a proper nn.Module (_VAEModule) whose keys
        map directly to the sub-modules stored here.
        """
        import torch

        prefix_map = {
            "encoder":   self._encoder,
            "fc_mu":     self._fc_mu,
            "fc_logvar": self._fc_logvar,
            "decoder":   self._decoder,
        }
        # Build per-module state dicts
        sub_dicts: dict[str, dict] = {k: {} for k in prefix_map}
        for key, val in state_dict.items():
            for prefix in prefix_map:
                if key.startswith(prefix + "."):
                    sub_dicts[prefix][key[len(prefix) + 1:]] = val
                    break

        for prefix, module in prefix_map.items():
            if sub_dicts[prefix]:
                module.load_state_dict(sub_dicts[prefix])

    def eval(self) -> "MorphologyVAE":
        for m in (self._encoder, self._fc_mu, self._fc_logvar, self._decoder):
            m.eval()
        return self

    def train(self) -> "MorphologyVAE":
        for m in (self._encoder, self._fc_mu, self._fc_logvar, self._decoder):
            m.train()
        return self
