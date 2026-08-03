#!/bin/bash
# Daily OpenAI credit check (installed in crontab by spec-012 setup, 2026-08-03).
# Runs the watcher; on unlock (> $500) fires a macOS notification and drops a
# flag file the next human/agent session can see. Never spends, never commits.
set -u
cd "$(dirname "$0")/.." || exit 1

.venv/bin/python scripts/check_openai_budget.py
if [ $? -eq 3 ]; then
  touch experiments/credits-ready.flag
  osascript -e 'display notification "OpenAI credits > $500. Run: gh secret set OPENAI_API_KEY --repo atharva789/autobot to unlock the compute plane." with title "AutoBot: compute plane ready"' 2>/dev/null
fi
