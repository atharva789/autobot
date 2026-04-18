# GVHMR Modal Endpoint Checklist

## Purpose

This turns the GVHMR probe into a persistent HTTP endpoint that fits the narrowed hackathon plan:

- fixed human-motion extractor
- fixed output schema
- no third-party mocap API dependency
- ready to feed the retargeting and simulation phases

## What Was Done

- [x] Cloned the upstream GVHMR code into `external/upstream-GVHMR`
- [x] Built a Modal app in `scripts/gvhmr_modal_probe.py`
- [x] Installed CUDA-compatible GVHMR dependencies inside the Modal image
- [x] Added explicit `fastapi[standard]` installation so the web endpoint can be deployed
- [x] Added a persistent Modal volume `gvhmr-cache` for checkpoints, videos, and cached preprocessing artifacts
- [x] Pulled required weights from Hugging Face mirrors:
  - GVHMR checkpoint
  - HMR2 checkpoint
  - ViTPose checkpoint
  - YOLO checkpoint
  - SMPL / SMPL-X body model files
- [x] Avoided the `pycolmap` import trap by loading only the tracker / ViTPose / HMR2 feature modules needed for static-camera inference
- [x] Verified end-to-end inference on the public tennis clip
- [x] Added `scaledown_window=900` so the GPU container stays warm for 15 minutes after a request instead of shutting down immediately
- [x] Removed the Move AI scaffolding and credentials flow
- [x] Added `scripts/check_gvhmr_endpoint.py` as a simple endpoint smoke test

## Endpoint Contract

Endpoint function:

- `probe_api(video_url: str, static_cam: bool = True) -> dict`

Deployed URL:

- `https://atharva789--gvhmr-probe-probe-api.modal.run`

Expected query parameters:

- `video_url`: public URL to a video clip
- `static_cam`: `true` or `false`

Current intended mode:

- `static_cam=true`

Response shape includes:

- `run_id`
- `video_url`
- `static_cam`
- `timings_s.preprocess`
- `timings_s.predict`
- `smpl_params_global`
- `smpl_params_incam`

The response is already shaped for downstream verification work because it reports tensor shapes and sample values rather than returning the full tensors inline.

## Verified Output

The tennis clip produced:

- `smpl_params_global.body_pose`: `[312, 63]`
- `smpl_params_global.betas`: `[312, 10]`
- `smpl_params_global.global_orient`: `[312, 3]`
- `smpl_params_global.transl`: `[312, 3]`

This is the expected kind of structured human-motion output for the broader plan: frame-aligned human pose, orientation, and translation that can feed retargeting.

## How This Fits The Broader Plan

### Phase 01: Foundation

- Provides the first working remote service in the stack
- Proves we can package the motion pipeline behind a callable API
- Establishes artifact caching, repeatability, and a narrow service contract

### Phase 03: Video Intelligence

- This is the concrete implementation of the human-motion extraction step
- It replaces vague “pose extraction” with a tested service boundary
- It keeps the plan aligned with the current scope reduction: one fixed model, one fixed human schema

### Phase 04: Retargeting And Simulation

- The endpoint output is the handoff surface into SMPL-to-G1 retargeting
- `global_orient` and `transl` are especially important for replay and locomotion grounding
- The raw tensor artifact remains available in the cache for deeper downstream processing

## Operational Notes

- First cold start is expensive because Modal may need to build the image and download checkpoints
- After the image and checkpoints are cached, repeated requests are much faster
- A fresh new clip still spends most of its time in preprocessing:
  - YOLO tracking
  - ViTPose extraction
  - HMR2 feature extraction
- The GVHMR model prediction stage itself is relatively short compared with preprocessing
- The current endpoint is intentionally scoped to static-camera videos

## Measured Timing Snapshot

- Tennis clip, first deployed HTTP hit after deploy: `25.56s`
  - `preprocess=0.569s`
  - `predict=5.772s`
  - remainder was mostly endpoint / container overhead
- Tennis clip, immediate warm repeat: `5.03s`
  - `preprocess=0.023s`
  - `predict=2.825s`
- CXK clip, fresh preprocessing on warm endpoint: `69.50s`
  - `preprocess=59.420s`
  - `predict=2.737s`

Interpretation:

- No, inference will not always take several minutes
- Yes, new uncached clips can still take around a minute because preprocessing dominates
- Repeated requests for the same clip on a warm container can complete in a few seconds

## Next Recommended Step

- Use this endpoint as the source for offline clip preprocessing
- Store the returned run metadata and tensor artifacts
- Feed the cached GVHMR output into the phase-04 retargeting prototype
