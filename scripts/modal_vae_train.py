"""One-time VAE training job. Run: modal run scripts/modal_vae_train.py

Estimated time: ~40 min on A10G. Estimated cost: ~$0.73.
Saves checkpoint to Modal volume 'autoresearch-artifacts' at /vol/vae_checkpoint.pt
"""
from __future__ import annotations

import modal

app = modal.App("autoresearch-vae-train")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch>=2.2", "mujoco>=3.1", "numpy>=1.26")
    .add_local_python_source("packages")
)
volume = modal.Volume.from_name("autoresearch-artifacts", create_if_missing=True)


@app.function(
    image=image,
    gpu="A10G",
    volumes={"/vol": volume},
    timeout=3600,
)
def train_vae(n_total: int = 10_000, epochs: int = 200) -> str:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    from packages.pipeline.urdf_generator import generate_filtered_dataset
    from packages.pipeline.vae import MorphologyVAE, params_to_tensor

    print(f"Generating {n_total} synthetic morphologies...")
    dataset = generate_filtered_dataset(n_total=n_total, seed=0)
    print(f"Filtered to {len(dataset)} valid morphologies.")
    if not dataset:
        raise ValueError(
            "No valid morphologies generated — check urdf_generator filter"
        )

    tensors = torch.stack([params_to_tensor(p) for p in dataset])
    loader = DataLoader(TensorDataset(tensors), batch_size=64, shuffle=True)

    # Proper nn.Module for gradient tracking and state_dict compatibility
    class _VAEModule(nn.Module):
        def __init__(self, latent_dim: int = 8, hidden: int = 64) -> None:
            super().__init__()
            self.latent_dim = latent_dim
            self.encoder = nn.Sequential(
                nn.Linear(12, hidden), nn.ReLU(),
                nn.Linear(hidden, hidden), nn.ReLU(),
            )
            self.fc_mu     = nn.Linear(hidden, latent_dim)
            self.fc_logvar = nn.Linear(hidden, latent_dim)
            self.decoder   = nn.Sequential(
                nn.Linear(latent_dim, hidden), nn.ReLU(),
                nn.Linear(hidden, hidden), nn.ReLU(),
                nn.Linear(hidden, 12),
            )

        def forward(self, x):
            h = self.encoder(x)
            mu, logvar = self.fc_mu(h), self.fc_logvar(h)
            std = torch.exp(0.5 * logvar)
            z = mu + std * torch.randn_like(std)
            return self.decoder(z), mu, logvar

        def elbo_loss(self, x: torch.Tensor, beta: float = 0.5) -> torch.Tensor:
            recon, mu, logvar = self(x)
            recon_loss = nn.functional.mse_loss(recon, x)
            kl = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).mean()
            return recon_loss + beta * kl

    vae = _VAEModule(latent_dim=8).cuda()
    opt = torch.optim.Adam(vae.parameters(), lr=1e-3)

    for epoch in range(epochs):
        total = 0.0
        for (batch,) in loader:
            batch = batch.cuda()
            loss = vae.elbo_loss(batch)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item()
        if epoch % 20 == 0:
            print(f"Epoch {epoch:3d} | loss {total / len(loader):.4f}")

    ckpt_path = "/vol/vae_checkpoint.pt"
    torch.save(vae.state_dict(), ckpt_path)
    volume.commit()
    print(f"Saved to {ckpt_path}")
    return ckpt_path


@app.local_entrypoint()
def main() -> None:
    train_vae.remote(n_total=10_000, epochs=200)
