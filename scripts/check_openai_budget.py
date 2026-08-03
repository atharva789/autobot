"""Daily OpenAI credit check for spec 012's compute plane.

The compute plane stays parked on local substitute providers until OpenAI
credits exceed $500. This script observes; it never spends. Every outcome —
including "no key yet" — is appended to routines/budget-log.md, because a
watcher that only logs successes cannot be audited.

Exit codes: 0 = checked, below threshold or unknown; 3 = credits > $500.

Sources, in order:
1. OPENAI_BUDGET_USD env var or .env entry — manual override; the dashboard
   is the source of truth when the API will not say.
2. https://api.openai.com/dashboard/billing/credit_grants with the API key —
   frequently session-authenticated only; a 401 here is expected and logged
   as "unavailable", not treated as an error.
3. /v1/models sanity ping, so the log at least records whether the key works.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

THRESHOLD_USD = 500.0
LOG = Path("routines/budget-log.md")
HEADER = (
    "# OpenAI budget log\n\nAppended daily by scripts/check_openai_budget.py. "
    f"Compute plane unlocks at > ${THRESHOLD_USD:.0f}.\n\n"
    "| Date (UTC) | Key present | Credits (USD) | Source | Note |\n"
    "| --- | --- | --- | --- | --- |\n"
)


def _env_from_dotenv(name: str) -> str | None:
    if value := os.environ.get(name):
        return value
    try:
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    except FileNotFoundError:
        pass
    return None


def _get(url: str, key: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return 0, {}


def check() -> tuple[bool, float | None, str, str]:
    """Return (key_present, credits_usd, source, note)."""

    if override := _env_from_dotenv("OPENAI_BUDGET_USD"):
        try:
            return True, float(override), "manual OPENAI_BUDGET_USD", "override set by user"
        except ValueError:
            pass

    key = _env_from_dotenv("OPENAI_ADMIN_KEY") or _env_from_dotenv("OPENAI_API_KEY")
    if not key:
        return False, None, "none", "no OPENAI_API_KEY in env or .env yet"

    status, body = _get("https://api.openai.com/dashboard/billing/credit_grants", key)
    if status == 200 and "total_available" in body:
        return True, float(body["total_available"]), "credit_grants", ""

    models_status, _ = _get("https://api.openai.com/v1/models", key)
    if models_status == 200:
        return (
            True,
            None,
            "unavailable",
            f"key live (/v1/models 200) but credit_grants returned {status}; "
            "check dashboard manually or set OPENAI_BUDGET_USD",
        )
    return True, None, "unavailable", f"key present but not usable (/v1/models {models_status})"


def main() -> int:
    key_present, credits, source, note = check()

    if not LOG.exists():
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(HEADER, encoding="utf-8")
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    amount = f"{credits:.2f}" if credits is not None else "?"
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"| {today} | {'yes' if key_present else 'no'} | {amount} | {source} | {note} |\n")

    unlocked = credits is not None and credits > THRESHOLD_USD
    print(json.dumps({
        "key_present": key_present, "credits_usd": credits,
        "source": source, "note": note, "unlocked": unlocked,
    }))
    return 3 if unlocked else 0


if __name__ == "__main__":
    sys.exit(main())
