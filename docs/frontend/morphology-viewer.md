---
description: How generated robot candidates become visible Three.js bodies in the browser.
---

# Morphology Viewer

`apps/web/components/MorphologyViewer.tsx` renders generated robots.

It supports two broad modes:

- concept rendering from candidate fields,
- engineering-oriented rendering when richer scene or MJCF-like data is available.

## Concept generation

The core concept path uses candidate fields such as:

- `embodiment`,
- torso dimensions,
- leg count,
- arm count,
- limb degrees of freedom,
- actuator class,
- mass and payload estimates,
- sensor list.

The viewer then builds Three.js primitives for:

- torso/body,
- limbs,
- joints,
- contacts,
- optional arms or appendages,
- labels and overlays.

This means a candidate can be visible before a complete mechanical export exists.

## MJCF parsing fallback

When MJCF-like XML is available, the viewer can parse geometry fields and render them as primitives. This is useful for exported or compiled bodies.

The viewer does not replace the MJCF compiler. It is a display layer that can visualize available geometry data.

## Engineering overlays

The component supports modes such as:

- concept,
- engineering,
- joints,
- components.

These modes help reviewers inspect different aspects of the generated body without changing the underlying candidate.

## Where body appearance comes from

| Visual feature | Source |
| --- | --- |
| Body shape family | candidate `embodiment` and morphology |
| Limb count | candidate leg/arm fields and grammar HITL |
| Scale | torso/mass/payload estimates |
| Joint display | generated degrees of freedom and optional render payload |
| Component overlays | engineering render or component data when available |

## Common viewer mistakes

Avoid:

- adding generation logic to the viewer,
- hard-coding loop names in viewer components,
- assuming every candidate has full MJCF,
- treating concept rendering as export-grade geometry,
- changing candidate field names without updating backend conversion and tests.

