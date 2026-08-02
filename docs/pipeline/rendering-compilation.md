---
description: How robot designs become MJCF, UI scene data, and engineering render payloads.
---

# Rendering And Compilation

Generated bodies have multiple visual and compilation forms.

## Concept render

The fastest path is frontend concept rendering from product candidate fields. This lives in:

```text
apps/web/components/MorphologyViewer.tsx
```

It is useful for immediate review, but it is not a full mechanical export.

## Engineering render

Engineering render helpers live in:

```text
packages/pipeline/engineering_render.py
```

They build richer scene payloads with geometry intent, materials, nodes, and engineering-oriented metadata.

## MJCF compilation

MJCF compilation lives in:

```text
packages/pipeline/compilers/mjcf_compiler.py
```

The key public shape is:

```python
compile_to_mjcf(ir) -> str
```

The compiler expects canonical `RobotDesignIR`, not a raw frontend candidate.

## Export route bridge

`apps/api/routes/exports.py` converts stored design data to IR with `_design_to_ir()` and then calls the compiler.

That bridge is a practical product adapter. If generated candidates start carrying richer component or IR data, this conversion should become less default-heavy.

## UI scene data

UI scene data can be saved alongside MJCF artifacts so the frontend can render engineering details without reparsing every export.

## Important distinction

| Thing | Purpose |
| --- | --- |
| Concept candidate | Fast visual review in UI |
| Grammar HITL | Explain generated structure and validity |
| Component program | Lowered generated body structure |
| `RobotDesignIR` | Canonical robotics representation |
| MJCF | Simulator/export artifact |
| UI scene | Frontend engineering visualization |

Do not assume all generated candidates have all forms at all times.

