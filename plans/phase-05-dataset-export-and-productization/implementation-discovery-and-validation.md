# Phase 05: Dataset Export (Hackathon)

## Scope
Write one LeRobot-compatible `.parquet` per approved run. Round-trip load it with the `lerobot` library to prove the schema. Nothing else.

## Pinned Decisions
- Export format = single `.parquet` file per run. No bundle, no manifest, no zip.
- Schema = whatever the pinned `lerobot` version accepts via `LeRobotDataset.from_parquet(...)`.
- Gating = `runs.approved == true`. No provenance completeness checks, no replay-metric gate.
- Delivery = direct browser download from the FastAPI endpoint.

## Hours 18–24 + 30–34 Checklist
- [ ] Pin `huggingface-lerobot` version early in the lockfile. Do not upgrade during the event.
- [ ] Download one official LeRobot example dataset. Print its schema. Copy field names exactly.
- [ ] Build `export_run(run_id: str) -> str`:
  - Load `runs.retarget_npz_path` → joint trajectory.
  - Load metadata: `prompt`, `clip_id`, `created_at`.
  - Construct LeRobot frames: `observation.state` = current joint positions, `action` = next-frame joint positions, `timestamp`, `task` = prompt string.
  - Write `data/exports/<run_id>.parquet`.
- [ ] Implement `POST /runs/{id}/export` → calls `export_run`, writes `exports` row, returns download URL.
- [ ] Implement `GET /exports/{id}/download` → streams the parquet.
- [ ] Frontend: show **Approve** button after replay renders; show **Export** button once approved; **Export** triggers download.
- [ ] Round-trip validation (in a notebook committed as `notebooks/validate_export.ipynb`):
  ```python
  from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
  ds = LeRobotDataset.from_parquet("data/exports/<run_id>.parquet")
  assert len(ds) == 1
  print(ds[0].keys())
  ```

## Explicitly Out of Scope
- Manifest, bundle, zip, versioning, reproducibility guarantees.
- Re-export, takedown, deletion propagation, retention expiry, operator tooling.
- Provenance ledger, audit log, lineage tracking beyond a single `clip_id` column.
- Access control, multi-tenant downloads, signed URLs.
- Customer-visible project status model beyond `runs.status`.

## Exit Criteria
- Judge clicks **Approve** then **Export**; browser downloads `<run_id>.parquet` in under 5 seconds.
- The validation notebook loads the parquet with `LeRobotDataset.from_parquet(...)` and prints `len(ds) == 1` without raising.

## v1 Definition of Done
- Happy path runs end-to-end three times in a row without restart.
- README has a `make demo` command that boots everything.
- One-slide pitch exists.
- Backup prerecorded demo video exists in case the live run blows up.
