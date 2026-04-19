"""Backward-compatible shim for legacy tests and callers.

The canonical compiler now lives in `packages.pipeline.mjcf_factory` and the
IR-based compilers under `packages.pipeline.compilers`.
"""

from __future__ import annotations

from packages.pipeline.mjcf_factory import build_mjcf, validate_mjcf

build_urdf = build_mjcf
validate_urdf = validate_mjcf

