---
description: CAD assembly, print export, component-slot resolution, and procurement report generation.
---

# CAD And Procurement

CAD and procurement helpers live under:

```text
packages/pipeline/cad/
packages/pipeline/components/
packages/pipeline/procurement/
```

## CAD assembly

CAD helpers translate robot body data into printable or inspectable part structures.

Relevant files include:

- `cad/assembly_builder.py`,
- `cad/cadquery_parts.py`,
- `cad/print_export.py`.

## Print export

The product print export route writes files under:

```text
data/exports/{design_id}
```

This export path should be treated as artifact generation from stored designs, not as a new body-generation algorithm.

## Component slots

Component-slot code maps design needs to physical parts or placeholders.

Examples:

- actuator slot requirements,
- sensor slot requirements,
- contact hardware,
- structural components.

## Procurement reports

Procurement code can produce reports describing the components needed for a design. This is useful for bridging generated robot concepts into build planning.

## Current maturity

CAD and procurement are downstream from generation. They depend on the quality and completeness of the generated body representation.

If a candidate only contains flat product fields, export code may need defaults. If it contains richer IR or component data, CAD and procurement can become more faithful.

