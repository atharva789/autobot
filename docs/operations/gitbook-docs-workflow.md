---
description: How to maintain the Robodex GitBook source without relying on the GitBook web editor.
---

# GitBook Workflow

## Source layout

```text
.gitbook.yaml
docs/
  README.md
  SUMMARY.md
  .gitbook/
    vars.yaml
  architecture/
  product/
  frontend/
  research/
  pipeline/
  operations/
  reference/
```

## Navigation

Every visible page should appear in `docs/SUMMARY.md`.

When adding a page:

1. create the Markdown file,
2. add it to `SUMMARY.md`,
3. validate the link,
4. keep the surrounding section order logical.

## GitBook components

Robodex uses GitBook-friendly Markdown:

- frontmatter descriptions,
- hints,
- cards,
- Mermaid diagrams,
- tables,
- code blocks.

Keep content useful in plain Markdown too. GitBook syntax should enhance the page, not make it unreadable outside GitBook.

## Local validation

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import re

root = Path("docs")
missing = []
for match in re.finditer(r"\]\(([^)]+)\)", (root / "SUMMARY.md").read_text()):
    target = match.group(1)
    if target.startswith(("http://", "https://", "#")):
        continue
    if not (root / target).exists():
        missing.append(target)

if missing:
    raise SystemExit("Missing SUMMARY targets: " + ", ".join(missing))
print("GitBook navigation OK")
PY
```

Also run:

```bash
gitbook whoami
```

before attempting any remote GitBook action.

## Style rules

Write documentation that answers:

- where the code lives,
- what owns the behavior,
- what crosses the boundary,
- how to test it,
- what is production-ready,
- what is a scaffold or roadmap item.

Avoid vague architecture prose that cannot be traced to files.

