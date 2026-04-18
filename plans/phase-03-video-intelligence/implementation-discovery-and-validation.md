# Phase 03: Video Intelligence (Hackathon)

## Scope
Pre-extract SMPL-X motion for 3 curated clips **offline, before the live hackathon hours**, and commit the results. No discovery, no mirroring, no retrieval, no vector index, no live pose estimation at request time. If WHAM / GVHMR install fights back, fall through to AMASS — it ships with SMPL parameters and zero extraction cost.

## Pinned Decisions
- Pose extractor = WHAM (preferred) or GVHMR. Run on a GPU box before the event.
- Output = SMPL-X `.pkl` per clip, trimmed to 2–5 seconds.
- If pose extraction falls apart, swap to pre-existing SMPL sequences from AMASS / Motion-X. The YouTube story becomes aspirational in the pitch.

## Hours 6–10 Checklist (and pre-hackathon prep)
- [ ] Pick 3 clips. Suggested archetypes: whole-body wave, simple walk cycle, upper-body reach. Prefer short clips with clean camera, single subject, minimal occlusion, mostly frontal view.
- [ ] Run WHAM or GVHMR per clip → SMPL-X parameters `.pkl`. If this fails twice, stop and use AMASS/Motion-X.
- [ ] Trim the SMPL sequence to 2–5s. Commit `.pkl` to `data/smpl/<clip_id>.pkl` (LFS if >20MB).
- [ ] Sanity-render each SMPL sequence to a 2D GIF (`data/smpl/<clip_id>.gif`) for quick eyeballing.
- [ ] Verify each `.pkl` loads in Python and the joint tensor shape matches the retargeter's input expectation.

## Fallback Ladder
1. WHAM on hand-picked clips.
2. GVHMR on hand-picked clips.
3. 4DHumans on hand-picked clips.
4. AMASS sequences with matching task labels (walking, waving, reaching).
5. Motion-X sequences.

## Explicitly Out of Scope
- Live pose extraction on user-submitted videos.
- Open-web discovery, YouTube mirroring, yt-dlp pipeline.
- Embedding, vector index, text-to-video retrieval, video-to-video similarity.
- Deduplication, perceptual hashing, frame fingerprinting.
- Confidence scoring, quality filters, reprocessing branches, failure taxonomy.
- Canonical motion representation negotiation — the retarget lib defines the format.

## Exit Criteria
- Three `.pkl` files exist under `data/smpl/` and load without error.
- Each has a matching source video at `data/videos/<clip_id>.mp4`.
- Each has a sanity GIF that visibly resembles the source motion.

## Handoff to Phase 04
- `clip.smpl_path` points at a loadable SMPL-X pkl. Phase 04 consumes it.
